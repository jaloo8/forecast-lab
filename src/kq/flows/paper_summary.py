"""Paper-trading summary — read-only operational status pull.

Run via ``kq paper-summary`` to check paper-trading progress. Two distinct
bars are reported, labeled for what they actually are (the 2026-06-11 audit
caught the old output calling the Phase 2 numbers "Phase 5 gates"):

  * **Phase 2 exit criteria** (CLAUDE.md Phase 2): ≥ 50 settled paper trades
    and 14 days of paper-trading activity.
  * **Phase 5 gate #1 progress** (CLAUDE.md §5 #1): ≥ 500 settled paper
    trades across weather + NBA. Shown as a progress counter, never as a
    pass/fail we could confuse with the Phase 2 exit.

"Days of activity" is computed — and labeled — as DISTINCT UTC dates with at
least one filled trade. It is NOT a consecutive-day streak; gaps don't reset
it.

Designed for two consumers:

  * **Human inspection** — pretty-printed table to stdout, color-free, safe
    to copy into runbook notes.
  * **Cron / alerting** — ``--json`` emits a single JSON object on stdout
    so a downstream watchdog can compare against thresholds without parsing
    the human format.

The flow is **read-only**. No DB writes, no external HTTP calls. Safe to
run from any machine that can reach the DuckDB file.

Schema source: ``paper_trade`` + ``signal`` + ``settlement`` tables, all
defined in ``src/kq/storage/schemas.sql``.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import structlog

from kq.config import get_settings
from kq.flows.ingest_weather import _db_path_from_settings

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PerStation:
    """Per-station rollup — what a single station's paper-trade record looks like."""

    station: str  # ICAO derived from ticker prefix (KXHIGHLAX → KLAX, etc.)
    n_filled: int
    n_settled: int
    n_won: int
    win_rate: float  # n_won / n_settled (0 when n_settled == 0)
    total_pnl_usd: float


@dataclass(frozen=True, slots=True)
class PaperSummary:
    """Top-level paper-trading rollup. Used both as the JSON shape and as
    the input to the pretty-printer.

    Fields are deliberately flat / JSON-safe; per-station rollups go in
    ``per_station`` so the cron alerting can read them without recursion.
    """

    start_date: date | None  # filter range (inclusive)
    end_date: date | None
    n_signals: int  # rows in `signal` overlapping the range
    n_filled: int  # paper_trade rows with filled_at != NULL
    n_settled: int  # paper_trade rows with settled_at != NULL
    n_won: int  # paper_trade rows with pnl_usd > 0
    win_rate: float
    total_pnl_usd: float
    starting_bankroll_usd: float  # the snapshot the user passed in (or paper.py default)
    current_bankroll_usd: float  # starting + total_pnl
    roi_pct: float  # 100 * total_pnl / starting (0 when starting <= 0)
    n_distinct_trade_days: int
    """DISTINCT UTC dates with >= 1 filled trade. NOT a consecutive streak —
    the label matches the computation (2026-06-11 audit)."""

    phase2_passes_settled_count: bool  # n_settled >= PHASE2_MIN_SETTLED (50)
    phase2_passes_distinct_days: bool  # n_distinct_trade_days >= PHASE2_MIN_DISTINCT_DAYS (14)
    phase5_settled_target: int  # PHASE5_MIN_SETTLED (500) — the §5 #1 denominator
    phase5_settled_progress_pct: float  # 100 * n_settled / phase5_settled_target
    per_station: list[PerStation] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Round-trippable JSON representation."""
        out = asdict(self)
        # asdict serializes date → date; JSON needs str.
        out["start_date"] = self.start_date.isoformat() if self.start_date else None
        out["end_date"] = self.end_date.isoformat() if self.end_date else None
        return out


# Phase 2 exit criteria per CLAUDE.md Phase 2 ("Paper trading live ... for 14
# consecutive days, >= 50 settled paper trades"), and the Phase 5 gate #1
# target per CLAUDE.md §5 #1 (>= 500 settled paper trades). Pinned here so
# the assertion logic is one place; if the criteria change, update here + the
# ROADMAP table together.
PHASE2_MIN_SETTLED: int = 50
PHASE2_MIN_DISTINCT_DAYS: int = 14
PHASE5_MIN_SETTLED: int = 500


def summarize(
    con: duckdb.DuckDBPyConnection,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    starting_bankroll_usd: float = 1_000.0,
) -> PaperSummary:
    """Aggregate paper_trade + signal + settlement rows into a summary.

    Date filtering is on ``submitted_at`` (when the bet went on the books),
    not ``settled_at`` — a trade booked yesterday but not yet settled still
    counts as "in the window". This matches the operational view where
    "did I trade today" is the primary signal.

    Stations are derived from the Kalshi event-ticker prefix
    (``KXHIGHLAX`` → ``KLAX``). When the prefix doesn't match any of our
    six target stations, the trade is grouped under ``OTHER``.
    """
    where_clauses: list[str] = []
    params: list[Any] = []
    if start_date is not None:
        where_clauses.append("DATE(submitted_at) >= ?")
        params.append(start_date)
    if end_date is not None:
        where_clauses.append("DATE(submitted_at) <= ?")
        params.append(end_date)
    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    # Pre-aggregate at the paper_trade grain. The signal table lives one
    # row deeper (signal:trade is 1:1 in our schema, but we still join in
    # case future changes break that), so we count distinct signal_ids.
    # NOTE: `where_sql` is interpolated into the f-string but only contains `?`
    # placeholders built above; user values are passed via `params`. B608 is
    # globally suppressed in pyproject.toml [tool.bandit] for this reason.
    rollup = con.execute(
        f"""
        WITH agg AS (
            SELECT
                ticker,
                COUNT(*) AS n_filled,
                SUM(CASE WHEN settled_at IS NOT NULL THEN 1 ELSE 0 END) AS n_settled,
                SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) AS n_won,
                COALESCE(SUM(pnl_usd), 0.0) AS total_pnl_usd
            FROM paper_trade
            {where_sql}
            GROUP BY ticker
        )
        SELECT ticker, n_filled, n_settled, n_won, total_pnl_usd FROM agg
        """,
        params,
    ).fetchall()

    per_station_map: dict[str, dict[str, int | float]] = {}
    for ticker, n_filled, n_settled, n_won, total_pnl in rollup:
        station = _station_from_ticker(ticker)
        bucket = per_station_map.setdefault(
            station, {"n_filled": 0, "n_settled": 0, "n_won": 0, "total_pnl_usd": 0.0}
        )
        bucket["n_filled"] = int(bucket["n_filled"]) + int(n_filled or 0)
        bucket["n_settled"] = int(bucket["n_settled"]) + int(n_settled or 0)
        bucket["n_won"] = int(bucket["n_won"]) + int(n_won or 0)
        bucket["total_pnl_usd"] = float(bucket["total_pnl_usd"]) + float(total_pnl or 0.0)

    per_station: list[PerStation] = []
    for station, bucket in sorted(per_station_map.items()):
        n_settled = int(bucket["n_settled"])
        n_won = int(bucket["n_won"])
        per_station.append(
            PerStation(
                station=station,
                n_filled=int(bucket["n_filled"]),
                n_settled=n_settled,
                n_won=n_won,
                win_rate=(n_won / n_settled) if n_settled > 0 else 0.0,
                total_pnl_usd=round(float(bucket["total_pnl_usd"]), 2),
            )
        )

    totals = con.execute(
        f"""
        SELECT
            COUNT(*) AS n_filled,
            SUM(CASE WHEN settled_at IS NOT NULL THEN 1 ELSE 0 END) AS n_settled,
            SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) AS n_won,
            COALESCE(SUM(pnl_usd), 0.0) AS total_pnl_usd,
            COUNT(DISTINCT DATE(submitted_at)) AS n_distinct_trade_days
        FROM paper_trade
        {where_sql}
        """,
        params,
    ).fetchone()
    # COUNT(*) on an empty table returns (0, NULL, NULL, NULL, 0) so totals
    # is never None in practice, but mypy can't see that — be explicit.
    if totals is None:  # pragma: no cover — defensive
        n_filled = n_settled = n_won = n_distinct_trade_days = 0
        total_pnl = 0.0
    else:
        n_filled = int(totals[0] or 0)
        n_settled = int(totals[1] or 0)
        n_won = int(totals[2] or 0)
        total_pnl = float(totals[3] or 0.0)
        n_distinct_trade_days = int(totals[4] or 0)

    signals_row = con.execute(
        f"""
        SELECT COUNT(*) FROM signal
        WHERE signal_id IN (SELECT signal_id FROM paper_trade {where_sql})
        """,
        params,
    ).fetchone()
    n_signals = int(signals_row[0] or 0) if signals_row else 0

    win_rate = (n_won / n_settled) if n_settled > 0 else 0.0
    current_bankroll = starting_bankroll_usd + total_pnl
    roi = 100.0 * total_pnl / starting_bankroll_usd if starting_bankroll_usd > 0 else 0.0

    return PaperSummary(
        start_date=start_date,
        end_date=end_date,
        n_signals=n_signals,
        n_filled=n_filled,
        n_settled=n_settled,
        n_won=n_won,
        win_rate=win_rate,  # full precision; callers format
        total_pnl_usd=round(total_pnl, 2),
        starting_bankroll_usd=round(starting_bankroll_usd, 2),
        current_bankroll_usd=round(current_bankroll, 2),
        roi_pct=round(roi, 2),
        n_distinct_trade_days=n_distinct_trade_days,
        phase2_passes_settled_count=n_settled >= PHASE2_MIN_SETTLED,
        phase2_passes_distinct_days=n_distinct_trade_days >= PHASE2_MIN_DISTINCT_DAYS,
        phase5_settled_target=PHASE5_MIN_SETTLED,
        phase5_settled_progress_pct=round(100.0 * n_settled / PHASE5_MIN_SETTLED, 1),
        per_station=per_station,
    )


def _station_from_ticker(ticker: str) -> str:
    """Map ``KXHIGHLAX-YY-MMDD-XXXX`` → ``KLAX``.

    Falls back to ``OTHER`` when the prefix doesn't match a known station.
    The mapping is the inverse of ``kq.clients.stations.STATIONS[i].kalshi_series_ticker``.
    """
    # Lazy import to avoid a circular dep with the stations module if any future
    # caller wires this in the other direction. STATIONS is a small constant.
    from kq.clients.stations import STATIONS  # noqa: PLC0415 — intentional, see above

    for s in STATIONS:
        if ticker.startswith(s.kalshi_series_ticker):
            return s.icao
    return "OTHER"


def render_human(summary: PaperSummary) -> str:
    """Pretty-print to a plain ASCII string. No colors, no unicode boxes.

    Designed to be paste-friendly into a runbook + grep-friendly for cron
    log-scraping. Each metric on its own line with a colon-aligned label.
    Phase 2 exit criteria and Phase 5 #1 progress are separate sections so
    the 50-trade bar can never masquerade as the 500-trade gate again.
    """
    lines: list[str] = []
    rng_label = _format_range(summary.start_date, summary.end_date)
    lines.append(f"=== Paper Trading Summary ({rng_label}) ===")
    lines.append("")
    lines.append("Trade counts:")
    lines.append(f"  Signals generated      : {summary.n_signals:>5}")
    lines.append(f"  Trades filled          : {summary.n_filled:>5}")
    lines.append(f"  Trades settled         : {summary.n_settled:>5}")
    lines.append(
        f"  Distinct trade days    : {summary.n_distinct_trade_days:>5}  "
        f"(distinct UTC dates with a fill; not a consecutive streak)"
    )
    lines.append("")
    lines.append("Phase 2 exit criteria (paper-trading exit, CLAUDE.md Phase 2):")
    lines.append(
        f"  Settled trades         : {summary.n_settled:>5} / {PHASE2_MIN_SETTLED}   "
        f"{'PASS' if summary.phase2_passes_settled_count else 'not yet'}"
    )
    lines.append(
        f"  Distinct trade days    : {summary.n_distinct_trade_days:>5} / "
        f"{PHASE2_MIN_DISTINCT_DAYS}   "
        f"{'PASS' if summary.phase2_passes_distinct_days else 'not yet'}"
    )
    lines.append("")
    lines.append("Phase 5 gate #1 progress (real-money gate, CLAUDE.md section 5 #1):")
    lines.append(
        f"  Settled trades         : {summary.n_settled:>5} / {summary.phase5_settled_target}  "
        f"({summary.phase5_settled_progress_pct:.1f}% of the 500-trade gate)"
    )
    lines.append("")
    lines.append("Performance:")
    lines.append(f"  Win rate (settled only): {summary.win_rate * 100:>5.1f}%")
    lines.append(f"  Total PnL              : ${summary.total_pnl_usd:>+10.2f}")
    lines.append(
        f"  Bankroll               : ${summary.current_bankroll_usd:>10.2f} "
        f"(started ${summary.starting_bankroll_usd:.2f})"
    )
    lines.append(f"  ROI                    : {summary.roi_pct:>+5.2f}%")
    lines.append("")
    if summary.per_station:
        lines.append("Per-station breakdown:")
        for ps in summary.per_station:
            lines.append(
                f"  {ps.station:<6}: {ps.n_settled:>3} settled, "
                f"{ps.n_won:>3} wins ({ps.win_rate * 100:>5.1f}%), "
                f"pnl ${ps.total_pnl_usd:>+9.2f}"
            )
    else:
        lines.append("Per-station breakdown:")
        lines.append("  (no trades in window)")
    return "\n".join(lines)


def _format_range(start: date | None, end: date | None) -> str:
    if start is None and end is None:
        return "all time"
    if start is None:
        return f"through {end}"
    if end is None:
        return f"from {start}"
    days = (end - start).days + 1
    return f"{start} to {end}, {days} days"


def run(
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    starting_bankroll_usd: float = 1_000.0,
    db_path: Path | None = None,
    json_output: bool = False,
) -> tuple[PaperSummary, str]:
    """Entry point: connect, summarize, render. Returns (summary, rendered).

    The rendered string is the JSON object when `json_output=True`, otherwise
    the human-readable table. Caller (the CLI) prints; this function does not
    write to stdout itself, which keeps it test-friendly.
    """
    settings = get_settings()
    path = db_path or _db_path_from_settings(settings.database_url)
    con = duckdb.connect(str(path), read_only=True)
    try:
        summary = summarize(
            con,
            start_date=start_date,
            end_date=end_date,
            starting_bankroll_usd=starting_bankroll_usd,
        )
    finally:
        con.close()

    rendered = json.dumps(summary.to_dict()) if json_output else render_human(summary)
    log.info(
        "paper_summary.computed",
        n_signals=summary.n_signals,
        n_filled=summary.n_filled,
        n_settled=summary.n_settled,
        n_distinct_trade_days=summary.n_distinct_trade_days,
        phase2_passes_settled=summary.phase2_passes_settled_count,
        phase2_passes_days=summary.phase2_passes_distinct_days,
        phase5_settled_progress_pct=summary.phase5_settled_progress_pct,
    )
    return summary, rendered


def main(
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    starting_bankroll_usd: float = 1_000.0,
    json_output: bool = False,
) -> int:
    """`python -m kq paper-summary` entrypoint.

    Returns a Unix exit code:
        0 — no errors
        1 — the Phase 2 exit criteria don't both pass yet (informational,
            not failure)
        2 — DB unreachable / fundamental error

    The non-zero exits with `1` are deliberately informational — a crontab
    can `&& echo OK || alert` to surface progress without treating "still
    accumulating" as a failure.
    """
    try:
        summary, rendered = run(
            start_date=start_date,
            end_date=end_date,
            starting_bankroll_usd=starting_bankroll_usd,
            json_output=json_output,
        )
    except Exception as exc:
        log.error("paper_summary.failed", error=str(exc))
        print(f"paper_summary failed: {exc}")
        return 2

    print(rendered)
    if not (summary.phase2_passes_settled_count and summary.phase2_passes_distinct_days):
        return 1
    return 0


# Helper kept exported for tests + scripting.
__all__ = [
    "PHASE2_MIN_DISTINCT_DAYS",
    "PHASE2_MIN_SETTLED",
    "PHASE5_MIN_SETTLED",
    "PaperSummary",
    "PerStation",
    "main",
    "render_human",
    "run",
    "summarize",
]
