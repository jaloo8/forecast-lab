"""Settlement-window nowcast edge study — measure hypothesized edge #1.

The strategy spine (docs/research/STRATEGY-2026-07-01-SCALING.md §2) ranks
settlement-window nowcasting as the project's #1 hypothesized edge: by
early afternoon local time the daily high is often known within ~1F while
Kalshi brackets lag. The machinery exists (``kq.models.nowcast`` Bayesian
METAR update, wired into ``kq.flows.paper_trade``) but until this flow
NOTHING measured whether the edge is actually there.

For every settled weather market with orderbook history, the study
reconstructs — at the last usable snapshot in each of the final N hours
(default 8) before the market's LST settlement-day end:

    (a) the nowcast model probability, from the SAME production path the
        paper trader uses (:func:`kq.flows.paper_trade._make_prob_gt` →
        ``compute_nowcast_state`` + ``metar_updated_proba`` →
        strike-aware :func:`kq.clients.kalshi.strikes.yes_prob`), fed only
        METAR obs with ``obs_time <= snap_time`` and only forecasts with
        ``as_of <= snap_time`` (point-in-time — never a future row);
    (b) the market's mid price from the snapshot (two-sided books only);
    (c) the eventual settlement outcome from the stored strike semantics
        (``kalshi_market`` fields, ticker-legacy fallback for -T markets —
        identical to the paper settle pass) + the ``weather_observed`` high.

One record per (market, hour-bucket): taking only the LAST usable snapshot
per hour keeps ``n`` honest — 30-second snapshots would otherwise inflate
sample counts ~120x with near-duplicate rows.

Aggregates land in ``models/nowcast_edge_manifest.json`` per
hours-to-settlement bucket: mean |edge|, mean signed edge conditioned on
NOTHING (outcome-free — the PR-E lesson; skill lives in the Brier pair,
never in an outcome-conditioned edge), Brier(model) vs
Brier(market-mid-as-forecast), and the money view — realized after-fee
capture per contract at the taker fee for edges clearing the same 4pp gate
the paper executor uses.

Zero-data safe by design: the always-on box may run this the day it pulls
main, before much history accumulates. Empty DB (or missing DB file) →
clean manifest with n=0 + a friendly message, exit 0.
"""

from __future__ import annotations

import json
from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import structlog

from kq.clients.kalshi._ticker_parser import WeatherMarketRef, parse_weather_market_ticker
from kq.clients.kalshi.strikes import Strike, yes_outcome, yes_prob
from kq.clients.stations import STATIONS_BY_ICAO, Station
from kq.config import REPO_ROOT, get_settings
from kq.execution.fees import fee_per_contract
from kq.execution.paper import DEFAULT_MIN_EDGE_PCT
from kq.flows.ingest_weather import _db_path_from_settings

# Reuse the paper trader's exceedance-closure builder so the study prices
# markets EXACTLY like production (router prior + METAR nowcast dispatch).
from kq.flows.paper_trade import _make_prob_gt
from kq.models.nowcast import NowcastState, compute_nowcast_state
from kq.models.router import StrategyRouter, StrategyRouterConfig
from kq.storage.duckdb_store import connect
from kq.utils.kalshi_dates import settlement_day_bounds

if TYPE_CHECKING:
    import duckdb

log = structlog.get_logger(__name__)

MODELS_DIR: Path = REPO_ROOT / "models"
MANIFEST_PATH: Path = MODELS_DIR / "nowcast_edge_manifest.json"
ROUTER_CONFIG_PATH: Path = MODELS_DIR / "router_config.json"

DEFAULT_WINDOW_HOURS = 8
SECONDS_PER_HOUR = 3600.0

EMPTY_DATA_MESSAGE = (
    "No settled weather markets with orderbook history yet — normal on a "
    "fresh machine or right after pulling main. Keep the ingest cron "
    "running (`kq ingest`); once markets settle with a few hours of "
    "snapshots behind them, re-run `kq study-nowcast-edge` and this fills in."
)


@dataclass(frozen=True, slots=True)
class EdgeRecord:
    """One reconstructed (market, hour-bucket) evaluation.

    ``edge`` is ``model_prob - market_mid`` with NO outcome anywhere in the
    formula. ``after_fee_capture_usd`` is the realized per-contract P&L of
    the hypothetical taker trade and is only set when ``actionable``.
    """

    ticker: str
    station: str
    valid_date: date
    snap_time: datetime  # tz-aware UTC
    hours_to_settlement: int  # bucket index; 0 = the final hour
    model_prob: float
    market_mid: float
    outcome_yes: bool
    edge: float
    actionable: bool
    after_fee_capture_usd: float | None


@dataclass(frozen=True, slots=True)
class BucketStats:
    """Aggregates for one hours-to-settlement bucket (or overall)."""

    n: int
    mean_abs_edge: float | None
    mean_edge: float | None
    brier_model: float | None
    brier_market: float | None
    n_actionable: int
    mean_after_fee_capture_usd: float | None


@dataclass(frozen=True)
class StudyResult:
    """Everything the study produced: per-record detail + skip accounting."""

    window_hours: int
    prior_source: str  # 'router_config' | 'raw_fallback'
    n_markets_studied: int
    records: list[EdgeRecord] = field(default_factory=list)
    skips: dict[str, int] = field(default_factory=dict)


_SKIP_KEYS: tuple[str, ...] = (
    "non_weather_ticker",
    "unknown_station",
    "day_not_elapsed",
    "no_truth",
    "no_strike",
    "no_gaussian_prior",
    "no_usable_book",
    "no_prior_forecast",
)


def run_study(
    con: duckdb.DuckDBPyConnection,
    *,
    window_hours: int = DEFAULT_WINDOW_HOURS,
    router_config_path: Path | None = None,
    models_dir: Path | None = None,
    now_utc: datetime | None = None,
) -> StudyResult:
    """Reconstruct nowcast-vs-market records for every settled weather market.

    Pure DB reads — never writes. ``now_utc`` bounds the "settlement day has
    fully elapsed" guard (test seam; defaults to the wall clock).
    """
    if window_hours < 1:
        raise ValueError(f"window_hours must be >= 1, got {window_hours}")
    now = now_utc or datetime.now(tz=UTC)
    if now.tzinfo is None:
        raise ValueError("now_utc must be tz-aware (use datetime.now(tz=UTC))")

    router, prior_source = _load_router(
        router_config_path or ROUTER_CONFIG_PATH, models_dir or MODELS_DIR
    )
    skips: dict[str, int] = dict.fromkeys(_SKIP_KEYS, 0)
    records: list[EdgeRecord] = []
    n_markets = 0

    metar_cache: dict[tuple[str, date], list[tuple[datetime, float | None]]] = {}
    prior_cache: dict[tuple[str, date], list[tuple[datetime, float]]] = {}

    for ticker in _distinct_snap_tickers(con):
        ref = parse_weather_market_ticker(ticker)
        if ref is None:
            skips["non_weather_ticker"] += 1
            continue
        station = STATIONS_BY_ICAO.get(ref.icao)
        if station is None:
            skips["unknown_station"] += 1
            continue
        start_utc, end_utc = settlement_day_bounds(station, ref.valid_date)
        if now < end_utc:
            skips["day_not_elapsed"] += 1
            continue  # high not final — the market isn't settled yet
        observed_high = _observed_high(con, station=ref.icao, valid_date=ref.valid_date)
        if observed_high is None:
            skips["no_truth"] += 1
            continue
        strike = _strike_for(con, ticker=ticker, ref=ref)
        if strike is None:
            skips["no_strike"] += 1
            continue

        key = (ref.icao, ref.valid_date)
        if key not in metar_cache:
            metar_cache[key] = _metar_rows(con, station=ref.icao, start=start_utc, end=end_utc)
        if key not in prior_cache:
            prior_cache[key] = _prior_forecasts(con, station=ref.icao, valid_date=ref.valid_date)

        try:
            market_records = _study_one_market(
                con,
                ref=ref,
                station=station,
                strike=strike,
                observed_high=observed_high,
                end_utc=end_utc,
                window_hours=window_hours,
                router=router,
                metar_rows=metar_cache[key],
                priors=prior_cache[key],
                skips=skips,
            )
        except RuntimeError as exc:
            # Analog-routed stations have no Gaussian (mu, sigma) prior; the
            # router refuses to substitute raw (audit root cause #11) and so
            # do we — skip loudly rather than measure a substitute model.
            log.warning("study_nowcast_edge.no_gaussian_prior", ticker=ticker, detail=str(exc))
            skips["no_gaussian_prior"] += 1
            continue
        if market_records:
            n_markets += 1
            records.extend(market_records)

    return StudyResult(
        window_hours=window_hours,
        prior_source=prior_source,
        n_markets_studied=n_markets,
        records=records,
        skips=skips,
    )


def _study_one_market(
    con: duckdb.DuckDBPyConnection,
    *,
    ref: WeatherMarketRef,
    station: Station,
    strike: Strike,
    observed_high: float,
    end_utc: datetime,
    window_hours: int,
    router: StrategyRouter,
    metar_rows: list[tuple[datetime, float | None]],
    priors: list[tuple[datetime, float]],
    skips: dict[str, int],
) -> list[EdgeRecord]:
    """Records for one market: last usable snap per hour bucket."""
    window_start = end_utc - timedelta(hours=window_hours)
    snaps = _snaps_in_window(con, ticker=ref.raw_ticker, start=window_start, end=end_utc)
    outcome_yes = yes_outcome(strike, observed_high)

    # Last usable (two-sided, uncrossed) snapshot per hour bucket.
    chosen: dict[int, tuple[datetime, float, float]] = {}
    seen_buckets: set[int] = set()
    for snap_time, yes_bid, yes_ask in snaps:
        bucket = int((end_utc - snap_time).total_seconds() // SECONDS_PER_HOUR)
        if not 0 <= bucket < window_hours:
            continue  # exact window-start boundary
        seen_buckets.add(bucket)
        two_sided = _two_sided_quote(yes_bid, yes_ask)
        if two_sided is None:
            continue
        chosen[bucket] = (snap_time, *two_sided)  # snaps arrive time-ordered
    skips["no_usable_book"] += len(seen_buckets - set(chosen))

    out: list[EdgeRecord] = []
    for bucket in sorted(chosen, reverse=True):
        snap_time, bid, ask = chosen[bucket]
        prior_mu = _latest_prior_at(priors, snap_time)
        if prior_mu is None:
            skips["no_prior_forecast"] += 1
            continue
        state: NowcastState = compute_nowcast_state(
            station=station,
            valid_date=ref.valid_date,
            now_utc=snap_time,  # PIT: obs after the snapshot are excluded inside
            metar_temps=metar_rows,
        )
        prob_gt = _make_prob_gt(
            router=router,
            icao=ref.icao,
            forecast_arr=np.array([prior_mu]),
            nowcast_state=state,
        )
        model_prob = yes_prob(strike, prob_gt)
        mid = 0.5 * (bid + ask)
        actionable, capture = _money_view(
            model_prob=model_prob, bid=bid, ask=ask, outcome_yes=outcome_yes
        )
        out.append(
            EdgeRecord(
                ticker=ref.raw_ticker,
                station=ref.icao,
                valid_date=ref.valid_date,
                snap_time=snap_time,
                hours_to_settlement=bucket,
                model_prob=model_prob,
                market_mid=mid,
                outcome_yes=outcome_yes,
                edge=model_prob - mid,
                actionable=actionable,
                after_fee_capture_usd=capture,
            )
        )
    return out


def _money_view(
    *,
    model_prob: float,
    bid: float,
    ask: float,
    outcome_yes: bool,
) -> tuple[bool, float | None]:
    """Hypothetical taker trade under the paper executor's decision rule.

    BUY_YES at the ask when ``model_prob > ask``; BUY_NO at ``1 - bid`` when
    ``model_prob < bid``; inside the spread = no trade. Actionable only when
    the after-fee edge clears the same ``DEFAULT_MIN_EDGE_PCT`` (4pp) gate
    the paper executor applies. Returns ``(actionable,
    realized_after_fee_capture_per_contract)`` — capture carries the outcome
    (it's the money view, i.e. realized P&L), never the edge metrics.
    """
    if model_prob > ask:
        fill_price = ask
        prob_at_fill = model_prob
        won = outcome_yes
    elif model_prob < bid:
        fill_price = 1.0 - bid
        prob_at_fill = 1.0 - model_prob
        won = not outcome_yes
    else:
        return False, None
    fee = fee_per_contract(fill_price, side="taker")
    edge_after_fee_pct = (prob_at_fill - fill_price - fee) * 100.0
    if edge_after_fee_pct < DEFAULT_MIN_EDGE_PCT:
        return False, None
    payout = 1.0 if won else 0.0
    return True, round(payout - fill_price - fee, 6)


def _two_sided_quote(yes_bid: float | None, yes_ask: float | None) -> tuple[float, float] | None:
    """Normalize a snapshot quote; ``None`` unless both sides are real.

    Kalshi one-sided-book sentinels (bid 0.0 = no resting bid, ask 1.0 = no
    resting ask — same encoding ``kq.execution.paper.evaluate_market``
    normalizes) and crossed books yield no honest mid, so those snapshots
    are unusable for a market-as-forecast comparison.
    """
    if yes_bid is None or yes_ask is None:
        return None
    if not (0.0 < yes_bid < 1.0 and 0.0 < yes_ask < 1.0):
        return None
    if yes_bid > yes_ask:
        return None
    return yes_bid, yes_ask


# --------------------------------------------------------------- DB reads


def _distinct_snap_tickers(con: duckdb.DuckDBPyConnection) -> list[str]:
    rows = con.execute("SELECT DISTINCT ticker FROM kalshi_book_snap ORDER BY ticker").fetchall()
    return [str(r[0]) for r in rows]


def _observed_high(
    con: duckdb.DuckDBPyConnection, *, station: str, valid_date: date
) -> float | None:
    row = con.execute(
        "SELECT high_f FROM weather_observed WHERE station = ? AND valid_date = ?",
        [station, valid_date],
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return float(row[0])


def _strike_for(
    con: duckdb.DuckDBPyConnection, *, ticker: str, ref: WeatherMarketRef
) -> Strike | None:
    """Resolution semantics for the settled market — settle-pass parity.

    Stored ``kalshi_market`` strike fields win (captured point-in-time while
    the market was live). Legacy rows without stored fields fall back to the
    historical greater-at-ticker-threshold rule for ``-T`` markets only —
    exactly the posture of ``paper_trades._strike_for_settlement``. A ``-B``
    market without stored fields is unguessable.
    """
    row = con.execute(
        "SELECT strike_type, floor_strike, cap_strike FROM kalshi_market WHERE ticker = ?",
        [ticker],
    ).fetchone()
    if row is not None and row[0] is not None:
        try:
            return Strike(
                kind=str(row[0]),  # type: ignore[arg-type]
                floor=float(row[1]) if row[1] is not None else None,
                cap=float(row[2]) if row[2] is not None else None,
            )
        except ValueError:
            log.warning(
                "study_nowcast_edge.bad_stored_strike",
                ticker=ticker,
                strike_type=str(row[0]),
            )
            return None
    if ref.kind == "T":
        return Strike(kind="greater", floor=float(ref.threshold_f), cap=None)
    return None


def _snaps_in_window(
    con: duckdb.DuckDBPyConnection, *, ticker: str, start: datetime, end: datetime
) -> list[tuple[datetime, float | None, float | None]]:
    """Time-ordered ``(snap_time_utc, yes_bid, yes_ask)`` in ``[start, end)``."""
    rows = con.execute(
        """
        SELECT snap_time, yes_bid, yes_ask FROM kalshi_book_snap
        WHERE ticker = ? AND snap_time >= ? AND snap_time < ?
        ORDER BY snap_time
        """,
        [ticker, _naive(start), _naive(end)],
    ).fetchall()
    return [
        (
            _aware(r[0]),
            float(r[1]) if r[1] is not None else None,
            float(r[2]) if r[2] is not None else None,
        )
        for r in rows
    ]


def _metar_rows(
    con: duckdb.DuckDBPyConnection, *, station: str, start: datetime, end: datetime
) -> list[tuple[datetime, float | None]]:
    """All settlement-window METAR rows; PIT filtering happens per snapshot
    inside ``compute_nowcast_state`` (obs_time > snap_time is excluded)."""
    rows = con.execute(
        """
        SELECT obs_time, temp_f FROM metar_obs
        WHERE station = ? AND obs_time >= ? AND obs_time < ?
        ORDER BY obs_time
        """,
        [station, _naive(start), _naive(end)],
    ).fetchall()
    return [(_aware(r[0]), float(r[1]) if r[1] is not None else None) for r in rows]


def _prior_forecasts(
    con: duckdb.DuckDBPyConnection, *, station: str, valid_date: date
) -> list[tuple[datetime, float]]:
    """``(as_of_utc, ensemble_mean_high_f)`` per forecast pull, time-ordered.

    Members (and models) sharing an ``as_of`` collapse to one mean — the
    deterministic analogue of the paper flow's latest-``as_of`` lookup.
    """
    rows = con.execute(
        """
        SELECT as_of, AVG(forecast_high_f) FROM weather_forecast
        WHERE station = ? AND valid_date = ? AND forecast_high_f IS NOT NULL
        GROUP BY as_of ORDER BY as_of
        """,
        [station, valid_date],
    ).fetchall()
    return [(_aware(r[0]), float(r[1])) for r in rows if r[1] is not None]


def _latest_prior_at(priors: list[tuple[datetime, float]], snap_time: datetime) -> float | None:
    """Most recent ensemble mean with ``as_of <= snap_time`` — PIT, never a
    forecast pulled after the snapshot."""
    idx = bisect_right(priors, snap_time, key=lambda p: p[0])
    if idx == 0:
        return None
    return priors[idx - 1][1]


def _naive(dt: datetime) -> datetime:
    """Bind-ready naive UTC (the storage convention for TIMESTAMP columns)."""
    return dt.astimezone(UTC).replace(tzinfo=None)


def _aware(val: object) -> datetime:
    if not isinstance(val, datetime):
        raise TypeError(f"expected datetime from DB, got {type(val).__name__}")
    return val if val.tzinfo is not None else val.replace(tzinfo=UTC)


# --------------------------------------------------------------- aggregation


def _load_router(config_path: Path, models_dir: Path) -> tuple[StrategyRouter, str]:
    """Production router when its config exists; raw-sigma fallback otherwise.

    The fallback (`StrategyRouterConfig()` with no decisions) dispatches every
    station to ``RawForecastModel`` at ``DEFAULT_RAW_SIGMA_F`` — so the study
    still runs on a machine that never ran ``kq decide-router``, with the
    prior source recorded in the manifest for honest comparison.
    """
    if config_path.exists():
        try:
            return (
                StrategyRouter.from_disk(config_path, models_dir, lead_days=1),
                "router_config",
            )
        except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
            log.warning("study_nowcast_edge.router_load_failed_fallback", detail=str(exc))
    return StrategyRouter(config=StrategyRouterConfig()), "raw_fallback"


def _bucket_stats(records: list[EdgeRecord]) -> BucketStats:
    n = len(records)
    if n == 0:
        return BucketStats(
            n=0,
            mean_abs_edge=None,
            mean_edge=None,
            brier_model=None,
            brier_market=None,
            n_actionable=0,
            mean_after_fee_capture_usd=None,
        )
    outcomes = [1.0 if r.outcome_yes else 0.0 for r in records]
    captures = [
        r.after_fee_capture_usd
        for r in records
        if r.actionable and r.after_fee_capture_usd is not None
    ]
    return BucketStats(
        n=n,
        mean_abs_edge=sum(abs(r.edge) for r in records) / n,
        # Outcome-free by construction: mean(model - mid), nothing conditioned
        # on the settlement (the PR-E lesson — audit root cause #10).
        mean_edge=sum(r.edge for r in records) / n,
        brier_model=sum((r.model_prob - y) ** 2 for r, y in zip(records, outcomes, strict=True))
        / n,
        brier_market=sum((r.market_mid - y) ** 2 for r, y in zip(records, outcomes, strict=True))
        / n,
        n_actionable=len(captures),
        mean_after_fee_capture_usd=(sum(captures) / len(captures)) if captures else None,
    )


def aggregate(result: StudyResult) -> tuple[dict[int, BucketStats], BucketStats]:
    """Per hours-to-settlement bucket stats + the overall roll-up."""
    by_bucket: dict[int, BucketStats] = {}
    for bucket in range(result.window_hours):
        by_bucket[bucket] = _bucket_stats(
            [r for r in result.records if r.hours_to_settlement == bucket]
        )
    return by_bucket, _bucket_stats(result.records)


def _round(v: float | None) -> float | None:
    return round(v, 6) if v is not None else None


def write_manifest(result: StudyResult, *, out_path: Path = MANIFEST_PATH) -> Path:
    """Serialize the study as JSON. Always writes a complete schema — a
    zero-data run produces the same keys with n=0 plus a friendly message."""
    by_bucket, overall = aggregate(result)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    def stats_dict(s: BucketStats) -> dict[str, Any]:
        return {
            "n": s.n,
            "mean_abs_edge": _round(s.mean_abs_edge),
            "mean_edge": _round(s.mean_edge),
            "brier_model": _round(s.brier_model),
            "brier_market": _round(s.brier_market),
            "n_actionable": s.n_actionable,
            "mean_after_fee_capture_usd": _round(s.mean_after_fee_capture_usd),
        }

    payload: dict[str, Any] = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "window_hours": result.window_hours,
        "prior_source": result.prior_source,
        "min_edge_gate_pct": DEFAULT_MIN_EDGE_PCT,
        "fee_side": "taker",
        "n_markets_studied": result.n_markets_studied,
        "n_records": len(result.records),
        "skips": dict(result.skips),
        "by_hours_to_settlement": {str(b): stats_dict(s) for b, s in sorted(by_bucket.items())},
        "overall": stats_dict(overall),
        "message": EMPTY_DATA_MESSAGE if not result.records else None,
        "honest_caveats": [
            "mean_edge is mean(model_prob - market_mid) with NO outcome in the "
            "formula — a disagreement diagnostic, not a skill claim (the PR-E "
            "lesson / 2026-06-11 audit root cause #10). Skill is the Brier "
            "pair: brier_model < brier_market = the nowcast beats the price.",
            "One record per (market, hour-bucket): the LAST two-sided snapshot "
            "in each hour. 30s snapshots would otherwise pseudo-replicate n "
            "~120x with near-duplicate rows.",
            "Point-in-time discipline: each record uses only METAR obs with "
            "obs_time <= snap_time and only forecasts with as_of <= snap_time. "
            "The prior's model artifacts (router config + pickles) are static "
            "committed files, not time-versioned — near-PIT, noted honestly.",
            "mean_after_fee_capture_usd is the realized per-contract P&L of "
            "hypothetical taker trades whose after-fee edge cleared the same "
            "4pp gate the paper executor uses. Realized P&L legitimately "
            "carries the outcome; at small n_actionable it is mostly noise.",
            "One-sided/crossed books are excluded (no honest mid); the skip "
            "counters keep the denominators visible.",
        ],
    }
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
    return out_path


def _empty_result(window_hours: int, *, prior_source: str = "raw_fallback") -> StudyResult:
    return StudyResult(
        window_hours=window_hours,
        prior_source=prior_source,
        n_markets_studied=0,
        records=[],
        skips=dict.fromkeys(_SKIP_KEYS, 0),
    )


def main(
    *,
    db_path: Path | None = None,
    window_hours: int = DEFAULT_WINDOW_HOURS,
    manifest_path: Path | None = None,
    router_config_path: Path | None = None,
    models_dir: Path | None = None,
    now_utc: datetime | None = None,
) -> int:
    """``kq study-nowcast-edge`` entrypoint. Returns the record count (>= 0).

    0 is a normal pre-accumulation state, not an error — the manifest is
    still written (n=0 + friendly message) so the dashboard's empty state
    can point at real provenance.
    """
    settings = get_settings()
    path = db_path or _db_path_from_settings(settings.database_url)
    out_path = manifest_path or MANIFEST_PATH

    result: StudyResult
    if not path.exists():
        log.warning("study_nowcast_edge.db_missing", db_path=str(path))
        result = _empty_result(window_hours)
    else:
        # Read-only: the study observes, never writes, and must not hold the
        # DuckDB write lock against the cron writers (2026-07-01 audit).
        with connect(path, read_only=True) as con:
            try:
                result = run_study(
                    con,
                    window_hours=window_hours,
                    router_config_path=router_config_path,
                    models_dir=models_dir,
                    now_utc=now_utc,
                )
            except Exception as exc:
                # A pre-bootstrap DB (tables missing) is a normal fresh-box
                # state, not a crash — duckdb raises CatalogException, which
                # we detect by name to avoid a hard duckdb import here.
                if type(exc).__name__ != "CatalogException":
                    raise
                log.warning("study_nowcast_edge.tables_missing", detail=str(exc))
                result = _empty_result(window_hours)

    written = write_manifest(result, out_path=out_path)
    _, overall = aggregate(result)
    log.info(
        "study_nowcast_edge.done",
        n_markets=result.n_markets_studied,
        n_records=len(result.records),
        n_actionable=overall.n_actionable,
        brier_model=overall.brier_model,
        brier_market=overall.brier_market,
        prior_source=result.prior_source,
        manifest=str(written),
    )
    if not result.records:
        print(f"study-nowcast-edge: {EMPTY_DATA_MESSAGE}")
        print(f"manifest (n=0) -> {written}")
    else:
        print(
            f"study-nowcast-edge: {len(result.records)} records across "
            f"{result.n_markets_studied} settled markets "
            f"(window {result.window_hours}h, prior={result.prior_source}); "
            f"Brier model={_fmt(overall.brier_model)} vs market={_fmt(overall.brier_market)}; "
            f"{overall.n_actionable} cleared the {DEFAULT_MIN_EDGE_PCT:.0f}pp gate, "
            f"mean after-fee capture "
            f"{_fmt(overall.mean_after_fee_capture_usd)} USD/contract -> {written}"
        )
    return len(result.records)


def _fmt(v: float | None) -> str:
    return f"{v:.4f}" if v is not None else "n/a"


__all__ = [
    "DEFAULT_WINDOW_HOURS",
    "MANIFEST_PATH",
    "BucketStats",
    "EdgeRecord",
    "StudyResult",
    "aggregate",
    "main",
    "run_study",
    "write_manifest",
]
