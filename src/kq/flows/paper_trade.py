"""Paper-trading orchestration flow.

One invocation of :func:`run_once` performs both passes:

1. **Submit** — fetch live Kalshi weather markets, look up the latest
   forecast per station, and price every open market with authoritative
   strike semantics (greater / less / between — PR-B) via the strategy
   router's exceedance function, inserting any resulting
   (signal, paper_trade) row pair into DuckDB with its strike fields.
2. **Settle** — walk every unsettled paper trade whose LST settlement day
   has fully elapsed, look up the matching weather_observed truth, and
   write back the realized P&L from the stored strike semantics.

The two passes are independent: settling needs nothing from Kalshi, so a
missing API key or empty production weather book does not block settlement
of trades booked on previous days.

Scope intentionally narrow for v1:
- Submits only at lead-day = 1 (the same horizon the NGR models train on).
- Uses today's most recent ensemble forecast per station ("most recent" =
  largest `as_of` with `valid_date == today + 1 day` UTC).
- Bankroll is `starting + sum(realized pnl)` snapshotted at the start of
  the submit pass (matches the backtest's compounding behaviour).

Wire-up: invoke via `kq paper` (one-shot) or schedule it under cron.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import structlog

from kq.backtest.bracket_match import parsed_weather_markets
from kq.clients.kalshi import KalshiClient, KalshiCredentialsError, Market
from kq.clients.kalshi.strikes import yes_prob
from kq.clients.stations import STATIONS, STATIONS_BY_ICAO
from kq.config import REPO_ROOT, get_settings
from kq.execution.paper import (
    DEFAULT_KELLY_FRACTION,
    DEFAULT_MAX_STAKE_USD,
    DEFAULT_MIN_EDGE_PCT,
    PaperExecutor,
)
from kq.features.weather import build_ensemble_features
from kq.flows.ingest_weather import _db_path_from_settings
from kq.models.nowcast import (
    NowcastState,
    compute_nowcast_state,
    metar_updated_proba,
)
from kq.models.router import StrategyRouter, StrategyRouterConfig
from kq.storage.duckdb_store import connect
from kq.storage.repositories.paper_trades import (
    insert_paper_trade_with_signal,
    settle_due_paper_trades,
    settled_pnl_total,
)
from kq.utils.kalshi_dates import settlement_day_bounds

log = structlog.get_logger(__name__)

MODELS_DIR = REPO_ROOT / "models"
ROUTER_CONFIG_PATH = MODELS_DIR / "router_config.json"
DEFAULT_STARTING_BANKROLL_USD = 1_000.0
DEFAULT_LEAD_DAYS = 1


@dataclass(frozen=True, slots=True)
class PaperRunSummary:
    """What `run_once` did. Used for logging + tests."""

    submit_evaluated: int
    submit_recorded: int
    settle_processed: int
    bankroll_snapshot_usd: float
    skipped_reason: str | None = None  # e.g. "no_kalshi_creds"


def run_once(
    *,
    db_path: Path | None = None,
    router_config_path: Path | None = None,
    models_dir: Path | None = None,
    starting_bankroll_usd: float = DEFAULT_STARTING_BANKROLL_USD,
    target_date: date | None = None,
    min_edge_pct: float = DEFAULT_MIN_EDGE_PCT,
    kelly_fraction: float = DEFAULT_KELLY_FRACTION,
    max_stake_usd: float = DEFAULT_MAX_STAKE_USD,
    settle_only: bool = False,
    use_nowcast: bool = True,
    now_utc: datetime | None = None,
) -> PaperRunSummary:
    """Run one full paper-trading cycle (submit + settle).

    Returns a `PaperRunSummary` for logging; never raises on missing
    credentials or empty markets — instead reports via `skipped_reason`.

    `settle_only=True` skips the submit pass entirely (useful for cron
    splitting submit on a market-hours schedule from settle on a daily one).

    `use_nowcast=True` (default) layers the intraday METAR Bayesian update
    (``kq.models.nowcast``) on top of the router's prior. The nowcast
    naturally degenerates to the unmodified prior when no METAR for the
    target_date exists yet (e.g. lead-1 forecast for tomorrow), so leaving
    this on costs nothing for the next-day submit case.

    `now_utc` overrides the wall-clock used to bound the LST settlement
    day for the nowcast — primarily a test seam.
    """
    settings = get_settings()
    db = db_path or _db_path_from_settings(settings.database_url)
    config_path = router_config_path or ROUTER_CONFIG_PATH
    models = models_dir or MODELS_DIR
    now = now_utc or datetime.now(tz=UTC)
    target = target_date or (now.date() + timedelta(days=DEFAULT_LEAD_DAYS))

    n_eval = 0
    n_recorded = 0
    skipped: str | None = None

    # Fetch the live Kalshi book BEFORE opening the DB connection: DuckDB
    # holds a single-writer file lock, and holding it across venue network
    # I/O (seconds, worst-case timeout tens of seconds) deterministically
    # collided with the every-minute ingest cron (2026-07-01 audit). The
    # connection below is opened only around actual DB work.
    markets_by_event: dict[str, list[Market]] | None = None
    if not settle_only:
        if not config_path.exists():
            log.warning(
                "paper.submit.skipped_no_router",
                detail=f"router config not found at {config_path}; run `kq decide-router` first",
            )
            skipped = "no_router_config"
        else:
            try:
                markets_by_event = asyncio.run(_pull_kalshi_markets(settings))
            except KalshiCredentialsError as exc:
                log.warning("paper.submit.skipped_no_creds", detail=str(exc))
                skipped = "no_kalshi_creds"

    con = connect(db)
    try:
        bankroll = starting_bankroll_usd + settled_pnl_total(con)

        if markets_by_event is not None:
            try:
                n_eval, n_recorded = _submit_pass(
                    con,
                    markets_by_event=markets_by_event,
                    target_date=target,
                    config_path=config_path,
                    models_dir=models,
                    bankroll_usd=bankroll,
                    min_edge_pct=min_edge_pct,
                    kelly_fraction=kelly_fraction,
                    max_stake_usd=max_stake_usd,
                    use_nowcast=use_nowcast,
                    now_utc=now,
                )
            except _RouterUnavailableError as exc:
                # Config vanished between the pre-fetch check and the load.
                log.warning("paper.submit.skipped_no_router", detail=str(exc))
                skipped = "no_router_config"

        n_settled = settle_due_paper_trades(con)
    finally:
        con.close()

    summary = PaperRunSummary(
        submit_evaluated=n_eval,
        submit_recorded=n_recorded,
        settle_processed=n_settled,
        bankroll_snapshot_usd=bankroll,
        skipped_reason=skipped,
    )
    log.info(
        "paper.run_once.done",
        evaluated=summary.submit_evaluated,
        recorded=summary.submit_recorded,
        settled=summary.settle_processed,
        bankroll=summary.bankroll_snapshot_usd,
        skipped=summary.skipped_reason,
    )
    return summary


def _submit_pass(
    con: object,  # duckdb.DuckDBPyConnection (kept loose to avoid extra import)
    *,
    markets_by_event: dict[str, list[Market]],
    target_date: date,
    config_path: Path,
    models_dir: Path,
    bankroll_usd: float,
    min_edge_pct: float,
    kelly_fraction: float,
    max_stake_usd: float,
    use_nowcast: bool,
    now_utc: datetime,
) -> tuple[int, int]:
    """Returns (n_evaluated, n_recorded). Raises on missing router config.

    ``markets_by_event`` is fetched by the caller BEFORE the DB connection
    opens (lock-scope discipline — never hold the DuckDB write lock across
    Kalshi network I/O); this pass does DB work only.

    PR-B: the pass is driven by the *live book*, not synthetic brackets —
    every open market with authoritative strike semantics (greater, less,
    between) is priced via ``kq.clients.kalshi.strikes.yes_prob`` against
    the model's exceedance function. This covers the 4/6 center ``-B``
    brackets the legacy threshold-matching path could never see.
    """
    if not config_path.exists():
        raise _RouterUnavailableError(
            f"router config not found at {config_path}; run `kq decide-router` first"
        )
    router_cfg = StrategyRouterConfig.load(config_path)
    router = StrategyRouter.from_disk(config_path, models_dir, lead_days=DEFAULT_LEAD_DAYS)

    forecasts = _latest_forecasts_for(con, target_date=target_date)
    if not forecasts:
        log.warning("paper.submit.no_forecasts", target_date=target_date.isoformat())
        return 0, 0

    settings = get_settings()
    # Demo payloads never carried strike fields, so the historical
    # -T-as-greater fallback stays available there. On prod the fallback is
    # OFF: a market without strike fields is payload drift and gets refused
    # (kq doctor keeps the ineligible count loud) rather than silently
    # re-enabling the inverted-less bug PR-B fixed.
    allow_legacy_strikes = settings.kalshi_env == "demo"
    if not any(markets_by_event.values()):
        log.warning("paper.submit.no_kalshi_weather_markets")
        return 0, 0

    nowcast_states = _build_nowcast_states(
        con, target_date=target_date, now_utc=now_utc, enabled=use_nowcast
    )

    executor = PaperExecutor(
        bankroll_usd=bankroll_usd,
        model_name=_model_name_with_nowcast(router_cfg, use_nowcast),
        min_edge_pct=min_edge_pct,
        kelly_fraction=kelly_fraction,
        max_stake_usd=max_stake_usd,
    )

    n_eval = 0
    n_recorded = 0
    submit_ts = now_utc
    for icao, forecast_mean in forecasts.items():
        station = STATIONS_BY_ICAO.get(icao)
        if station is None:
            continue
        markets = markets_by_event.get(station.kalshi_series_ticker, [])
        if not markets:
            continue
        parsed = parsed_weather_markets(markets, allow_legacy_ticker_semantics=allow_legacy_strikes)
        if not parsed:
            continue
        forecast_arr = np.array([forecast_mean])
        nowcast_state = nowcast_states.get(icao) if use_nowcast else None
        prob_gt = _make_prob_gt(
            router=router,
            icao=icao,
            forecast_arr=forecast_arr,
            nowcast_state=nowcast_state,
        )

        for market, ref, strike in parsed:
            if ref.icao != icao or ref.valid_date != target_date:
                continue
            n_eval += 1
            model_prob = yes_prob(strike, prob_gt)
            intent = executor.evaluate(
                model_prob_yes=model_prob,
                yes_bid=market.yes_bid,
                yes_ask=market.yes_ask,
                yes_bid_size=market.yes_bid_size,
                yes_ask_size=market.yes_ask_size,
                ticker=market.ticker,
                as_of=submit_ts,
                strike_type=strike.kind,
                floor_strike=strike.floor,
                cap_strike=strike.cap,
            )
            if intent is None:
                continue
            _trade_id, was_new = insert_paper_trade_with_signal(
                con,  # type: ignore[arg-type]
                intent,
                submitted_at=submit_ts,
            )
            if was_new:
                n_recorded += 1
                log.info(
                    "paper.submit.recorded",
                    ticker=intent.ticker,
                    side=intent.side,
                    qty=intent.qty,
                    limit_price=intent.limit_price,
                    edge_bps=intent.edge_bps,
                    strike=f"{strike.kind}[{strike.floor},{strike.cap}]",
                    nowcast_obs=nowcast_state.n_obs if nowcast_state else 0,
                )

    return n_eval, n_recorded


def _make_prob_gt(
    *,
    router: StrategyRouter,
    icao: str,
    forecast_arr: np.ndarray,
    nowcast_state: NowcastState | None,
) -> Callable[[float], float]:
    """Exceedance function ``x -> P(daily_high > x)`` for one station/day.

    Routes through the METAR nowcast when it carries information, else the
    router's vanilla ``predict_proba`` — the same dispatch the legacy
    per-threshold path used, packaged as a closure so strike-aware pricing
    (greater/less/between) can evaluate it at arbitrary boundaries.
    """
    if nowcast_state is None or not nowcast_state.has_obs:
        return lambda x: float(np.asarray(router.predict_proba(icao, forecast_arr, x))[0])

    prior_mu_arr, prior_sigma_arr = router.predict_distribution(icao, forecast_arr)
    prior_mu = float(np.asarray(prior_mu_arr)[0])
    # Numeric floor matches RawForecastModel.
    prior_sigma = max(float(np.asarray(prior_sigma_arr)[0]), 0.5)
    state = nowcast_state
    return lambda x: metar_updated_proba(
        threshold_f=x,
        prior_mu_f=prior_mu,
        prior_sigma_f=prior_sigma,
        state=state,
    )


def _build_nowcast_states(
    con: object,
    *,
    target_date: date,
    now_utc: datetime,
    enabled: bool,
) -> dict[str, NowcastState]:
    """Pull METAR rows once and build a per-station :class:`NowcastState`.

    Returns ``{}`` when ``enabled`` is False; otherwise keyed by ICAO with a
    state for every supported station (no-obs states included so callers can
    reason uniformly).
    """
    if not enabled:
        return {}
    metar_by_station = _fetch_settlement_day_metars(con, target_date=target_date, now_utc=now_utc)
    out: dict[str, NowcastState] = {}
    for station in STATIONS:
        out[station.icao] = compute_nowcast_state(
            station=station,
            valid_date=target_date,
            now_utc=now_utc,
            metar_temps=metar_by_station.get(station.icao, []),
        )
    return out


def _fetch_settlement_day_metars(
    con: object,  # duckdb.DuckDBPyConnection
    *,
    target_date: date,
    now_utc: datetime,
) -> dict[str, list[tuple[datetime, float | None]]]:
    """Read METAR rows that fall inside any station's LST window for `target_date`.

    The query union-bounds across the 6 stations so we make one trip to the
    DB. Returns a dict keyed by station ICAO; values are lists of
    ``(obs_time_utc, temp_f)`` ready for ``compute_nowcast_state``.
    """
    bounds = [(s.icao, settlement_day_bounds(s, target_date)) for s in STATIONS]
    out: dict[str, list[tuple[datetime, float | None]]] = {s.icao: [] for s in STATIONS}
    for icao, (start_utc, end_utc) in bounds:
        # Strip tzinfo for DuckDB TIMESTAMP columns (storage convention).
        start_naive = start_utc.replace(tzinfo=None)
        end_naive = end_utc.replace(tzinfo=None)
        now_naive = now_utc.astimezone(UTC).replace(tzinfo=None)
        rows = con.execute(  # type: ignore[attr-defined]
            """
            SELECT obs_time, temp_f FROM metar_obs
            WHERE station = ? AND obs_time >= ? AND obs_time < ? AND obs_time <= ?
            ORDER BY obs_time
            """,
            [icao, start_naive, end_naive, now_naive],
        ).fetchall()
        out[icao] = [
            (
                _add_utc_tz(_as_dt_or_none(obs_time)),
                float(temp) if temp is not None else None,
            )
            for obs_time, temp in rows
        ]
    return out


def _add_utc_tz(dt: datetime | None) -> datetime:
    """Re-attach UTC tz to a naive datetime read from DuckDB. Required for the nowcast."""
    if dt is None:
        # Defensive — pre-validated by the SQL filter, but type-narrow for mypy.
        raise RuntimeError("expected non-null obs_time")
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _as_dt_or_none(val: object) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    raise TypeError(f"expected datetime from DB, got {type(val).__name__}")


def _model_name_with_nowcast(cfg: StrategyRouterConfig, use_nowcast: bool) -> str:
    """Tag the model name in the signal log so we can A/B nowcast vs not later."""
    suffix = "+nowcast" if use_nowcast else ""
    stamp = cfg.generated_at[:10] or "unset"
    return f"weather_router_v1{suffix}@{stamp}"


def _latest_forecasts_for(
    con: object,  # duckdb.DuckDBPyConnection
    *,
    target_date: date,
) -> dict[str, float]:
    """Most-recent ensemble mean per station for the target valid_date.

    Returns a dict keyed by station ICAO. Missing stations are omitted.
    """
    df = build_ensemble_features(
        con,  # type: ignore[arg-type]
        start_date=target_date,
        end_date=target_date,
    )
    if df.is_empty():
        return {}
    # Per station, pick the row with the largest `as_of`; collapse to mean if ties.
    latest = (
        df.sort(["station", "as_of"], descending=[False, True])
        .group_by("station")
        .agg(pl.col("ens_mean_high_f").first().alias("ens_mean_high_f"))
    )
    return {
        str(row["station"]): float(row["ens_mean_high_f"])
        for row in latest.iter_rows(named=True)
        if row["ens_mean_high_f"] is not None
    }


async def _pull_kalshi_markets(settings: object) -> dict[str, list[Market]]:
    """Fetch open weather markets per station, keyed by Kalshi series ticker.

    Queries each station's SERIES ticker (`series_ticker=`), which returns all
    current markets across its open dated events — `event_ticker=<series>`
    matches nothing. Returns an empty dict (not raises) on credential errors so
    the caller can decide whether to skip the submit pass or continue settle-only.
    """
    out: dict[str, list[Market]] = {}
    targets = [s.kalshi_series_ticker for s in STATIONS]
    async with KalshiClient.from_settings(settings) as client:  # type: ignore[arg-type]
        for series_ticker in targets:
            try:
                markets = await client.list_markets(series_ticker=series_ticker)
            except Exception:
                log.exception("paper.kalshi.list_markets_failed", series_ticker=series_ticker)
                out[series_ticker] = []
                continue
            out[series_ticker] = list(markets)
    return out


class _RouterUnavailableError(RuntimeError):
    """Internal sentinel so `run_once` can render a friendly skipped_reason."""


def main(
    *,
    settle_only: bool = False,
    starting_bankroll_usd: float = DEFAULT_STARTING_BANKROLL_USD,
    target_date_iso: str | None = None,
    use_nowcast: bool = True,
) -> int:
    """`python -m kq paper` entrypoint. Returns exit code (0 = success)."""
    target = date.fromisoformat(target_date_iso) if target_date_iso else None
    summary = run_once(
        starting_bankroll_usd=starting_bankroll_usd,
        target_date=target,
        settle_only=settle_only,
        use_nowcast=use_nowcast,
    )
    if summary.skipped_reason:
        print(f"paper run skipped submit pass: {summary.skipped_reason}")
    print(
        "paper run done — "
        f"evaluated {summary.submit_evaluated}, "
        f"recorded {summary.submit_recorded}, "
        f"settled {summary.settle_processed}; "
        f"bankroll snapshot ${summary.bankroll_snapshot_usd:.2f}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    main()
