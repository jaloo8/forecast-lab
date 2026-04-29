"""Paper-trading orchestration flow.

One invocation of :func:`run_once` performs both passes:

1. **Submit** — fetch live Kalshi weather markets, look up the latest
   forecast per station, run those through the strategy router, evaluate
   each (bracket, market_quote) pair via the paper executor, and insert any
   resulting (signal, paper_trade) row pair into DuckDB.
2. **Settle** — walk every unsettled paper trade, look up the matching
   weather_observed truth, and write back the realized P&L.

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
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import structlog

from kq.backtest.bracket_match import find_matching_market, parsed_weather_markets
from kq.backtest.brackets import generate_brackets
from kq.clients.kalshi import KalshiClient, KalshiCredentialsError, Market
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
from kq.models.router import StrategyRouter, StrategyRouterConfig
from kq.storage.duckdb_store import connect
from kq.storage.repositories.paper_trades import (
    insert_paper_trade_with_signal,
    settle_due_paper_trades,
    settled_pnl_total,
)

log = structlog.get_logger(__name__)

MODELS_DIR = REPO_ROOT / "models"
ROUTER_CONFIG_PATH = MODELS_DIR / "router_config.json"
DEFAULT_STARTING_BANKROLL_USD = 1_000.0
DEFAULT_N_BRACKETS = 7
DEFAULT_BRACKET_SPACING_F = 2.0
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
    n_brackets: int = DEFAULT_N_BRACKETS,
    bracket_spacing_f: float = DEFAULT_BRACKET_SPACING_F,
    min_edge_pct: float = DEFAULT_MIN_EDGE_PCT,
    kelly_fraction: float = DEFAULT_KELLY_FRACTION,
    max_stake_usd: float = DEFAULT_MAX_STAKE_USD,
    settle_only: bool = False,
) -> PaperRunSummary:
    """Run one full paper-trading cycle (submit + settle).

    Returns a `PaperRunSummary` for logging; never raises on missing
    credentials or empty markets — instead reports via `skipped_reason`.

    `settle_only=True` skips the submit pass entirely (useful for cron
    splitting submit on a market-hours schedule from settle on a daily one).
    """
    settings = get_settings()
    db = db_path or _db_path_from_settings(settings.database_url)
    config_path = router_config_path or ROUTER_CONFIG_PATH
    models = models_dir or MODELS_DIR
    target = target_date or (datetime.now(tz=UTC).date() + timedelta(days=DEFAULT_LEAD_DAYS))

    con = connect(db)
    try:
        bankroll = starting_bankroll_usd + settled_pnl_total(con)
        n_eval = 0
        n_recorded = 0
        skipped: str | None = None

        if not settle_only:
            try:
                n_eval, n_recorded = _submit_pass(
                    con,
                    target_date=target,
                    config_path=config_path,
                    models_dir=models,
                    bankroll_usd=bankroll,
                    n_brackets=n_brackets,
                    bracket_spacing_f=bracket_spacing_f,
                    min_edge_pct=min_edge_pct,
                    kelly_fraction=kelly_fraction,
                    max_stake_usd=max_stake_usd,
                )
            except KalshiCredentialsError as exc:
                log.warning("paper.submit.skipped_no_creds", detail=str(exc))
                skipped = "no_kalshi_creds"
            except _RouterUnavailableError as exc:
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
    target_date: date,
    config_path: Path,
    models_dir: Path,
    bankroll_usd: float,
    n_brackets: int,
    bracket_spacing_f: float,
    min_edge_pct: float,
    kelly_fraction: float,
    max_stake_usd: float,
) -> tuple[int, int]:
    """Returns (n_evaluated, n_recorded). Raises on missing router config."""
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
    markets_by_event = asyncio.run(_pull_kalshi_markets(settings))
    if not any(markets_by_event.values()):
        log.warning("paper.submit.no_kalshi_weather_markets")
        return 0, 0

    executor = PaperExecutor(
        bankroll_usd=bankroll_usd,
        model_name=f"weather_router_v1@{router_cfg.generated_at[:10] or 'unset'}",
        min_edge_pct=min_edge_pct,
        kelly_fraction=kelly_fraction,
        max_stake_usd=max_stake_usd,
    )

    n_eval = 0
    n_recorded = 0
    submit_ts = datetime.now(tz=UTC)
    for icao, forecast_mean in forecasts.items():
        station = STATIONS_BY_ICAO.get(icao)
        if station is None:
            continue
        markets = markets_by_event.get(station.kalshi_event_ticker, [])
        if not markets:
            continue
        parsed = parsed_weather_markets(markets)
        if not parsed:
            continue
        for bracket in generate_brackets(
            forecast_mean, n_brackets=n_brackets, spacing_f=bracket_spacing_f
        ):
            n_eval += 1
            market = find_matching_market(
                bracket,
                icao=icao,
                valid_date=target_date,
                weather_markets=parsed,
            )
            if market is None:
                continue
            # `router.predict_proba` returns a scalar 0-d array when given a
            # scalar mean — wrap in a 1-d array so indexing works uniformly.
            forecast_arr = np.array([forecast_mean])
            model_prob = float(
                np.asarray(router.predict_proba(icao, forecast_arr, bracket.threshold_f))[0]
            )
            intent = executor.evaluate(
                model_prob_yes=model_prob,
                yes_bid=market.yes_bid,
                yes_ask=market.yes_ask,
                ticker=market.ticker,
                as_of=submit_ts,
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
                )

    return n_eval, n_recorded


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
    """Fetch open weather markets per station event ticker.

    Returns an empty dict (not raises) on credential errors so the caller can
    decide whether to skip the submit pass or continue with settle-only.
    """
    out: dict[str, list[Market]] = {}
    targets = [s.kalshi_event_ticker for s in STATIONS]
    async with KalshiClient.from_settings(settings) as client:  # type: ignore[arg-type]
        for event_ticker in targets:
            try:
                markets = await client.list_markets(event_ticker=event_ticker)
            except Exception:
                log.exception("paper.kalshi.list_markets_failed", event_ticker=event_ticker)
                out[event_ticker] = []
                continue
            out[event_ticker] = list(markets)
    return out


class _RouterUnavailableError(RuntimeError):
    """Internal sentinel so `run_once` can render a friendly skipped_reason."""


def main(
    *,
    settle_only: bool = False,
    starting_bankroll_usd: float = DEFAULT_STARTING_BANKROLL_USD,
    target_date_iso: str | None = None,
) -> int:
    """`python -m kq paper` entrypoint. Returns exit code (0 = success)."""
    target = date.fromisoformat(target_date_iso) if target_date_iso else None
    summary = run_once(
        starting_bankroll_usd=starting_bankroll_usd,
        target_date=target,
        settle_only=settle_only,
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
