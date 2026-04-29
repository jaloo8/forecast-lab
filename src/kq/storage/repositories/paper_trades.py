"""Paper-trading + signal repository.

Two tables, written together as a unit by :func:`insert_paper_trade_with_signal`
because every paper trade must reference its source signal (FK constraint).

Idempotency: ``signal_id`` and ``trade_id`` are deterministic content hashes
emitted by ``kq.execution.paper.make_signal_id`` / ``make_trade_id``, so
re-running the submit pass on the same forecast row is a no-op via
``INSERT OR IGNORE``. We use OR IGNORE rather than OR REPLACE so a partially
filled trade isn't accidentally stomped by a newer evaluation.

The settlement helper (:func:`settle_due_paper_trades`) walks every unsettled
weather paper trade, looks up the matching observed truth row, and writes the
settlement back to ``paper_trade``. Trades whose ticker doesn't parse as a
weather contract (NBA / MLB / unknown) are left alone — those will need their
own settlement logic when those verticals come online.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

from kq.clients.kalshi._ticker_parser import parse_weather_market_ticker
from kq.execution.paper import (
    PaperTradeIntent,
    Side,
    make_trade_id,
    settlement_pnl,
)

if TYPE_CHECKING:
    import duckdb

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PaperTradeRow:
    """Hydrated paper_trade row, used by the settlement loop."""

    trade_id: str
    signal_id: str
    submitted_at: datetime
    ticker: str
    side: Side
    limit_price: float
    qty: int
    fee_usd: float
    filled_at: datetime | None
    fill_price: float | None
    settled_at: datetime | None
    settlement: str | None
    pnl_usd: float | None


def insert_paper_trade_with_signal(
    con: duckdb.DuckDBPyConnection,
    intent: PaperTradeIntent,
    *,
    submitted_at: datetime | None = None,
    source_urls: Sequence[str] | None = None,
    reasoning: str | None = None,
) -> tuple[str, bool]:
    """Insert (signal, paper_trade) row pair atomically.

    Returns ``(trade_id, was_new)`` so the caller can distinguish a fresh
    bet from a re-run that hit the idempotent OR IGNORE path.

    Paper trades fill instantly at the limit price (which mirrors the backtest
    assumption — the market quote we evaluated against IS the fill). Both
    `filled_at` and `fill_price` are populated on insert.

    Idempotent: the underlying IDs are deterministic, so calling twice with the
    same intent leaves the row count unchanged.

    Timestamps are normalized to naive UTC before insert. DuckDB's TIMESTAMP
    column converts tz-aware datetimes to local-clock-naive on store, which
    silently corrupts UTC. We strip tzinfo after `.astimezone(UTC)` so the
    stored value matches the project's "naive UTC" storage convention.
    """
    submitted = _to_naive_utc(submitted_at or datetime.now(tz=UTC))
    as_of = _to_naive_utc(intent.as_of)
    trade_id = make_trade_id(intent.signal_id)
    market_prob_yes = 0.5 * (intent.market_yes_bid + intent.market_yes_ask)
    pre_existing = con.execute(
        "SELECT 1 FROM paper_trade WHERE trade_id = ?", [trade_id]
    ).fetchone()
    was_new = pre_existing is None

    # Signal first — paper_trade has a FK on signal(signal_id).
    con.execute(
        """
        INSERT OR IGNORE INTO signal
        (signal_id, as_of, ticker, model_prob_yes, market_prob_yes, edge_bps,
         model_name, source_urls, reasoning)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            intent.signal_id,
            as_of,
            intent.ticker,
            intent.model_prob_yes,
            market_prob_yes,
            intent.edge_bps,
            intent.model_name,
            list(source_urls) if source_urls else [],
            reasoning,
        ],
    )
    con.execute(
        """
        INSERT OR IGNORE INTO paper_trade
        (trade_id, signal_id, submitted_at, ticker, side, limit_price, qty,
         fee_usd, filled_at, fill_price, settled_at, settlement, pnl_usd)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)
        """,
        [
            trade_id,
            intent.signal_id,
            submitted,
            intent.ticker,
            intent.side,
            intent.limit_price,
            intent.qty,
            intent.fee_usd,
            submitted,  # paper fills instantly
            intent.limit_price,  # at the price we evaluated against
        ],
    )
    return trade_id, was_new


def fetch_unsettled_paper_trades(
    con: duckdb.DuckDBPyConnection,
) -> list[PaperTradeRow]:
    """Return every paper trade with no settlement recorded yet."""
    rows = con.execute(
        """
        SELECT trade_id, signal_id, submitted_at, ticker, side, limit_price,
               qty, fee_usd, filled_at, fill_price, settled_at, settlement, pnl_usd
        FROM paper_trade
        WHERE settled_at IS NULL
        ORDER BY submitted_at ASC
        """
    ).fetchall()
    return [
        PaperTradeRow(
            trade_id=str(r[0]),
            signal_id=str(r[1]),
            submitted_at=_as_dt(r[2]),
            ticker=str(r[3]),
            side=_as_side(r[4]),
            limit_price=float(r[5]),
            qty=int(r[6]),
            fee_usd=float(r[7]),
            filled_at=_as_optional_dt(r[8]),
            fill_price=float(r[9]) if r[9] is not None else None,
            settled_at=_as_optional_dt(r[10]),
            settlement=str(r[11]) if r[11] is not None else None,
            pnl_usd=float(r[12]) if r[12] is not None else None,
        )
        for r in rows
    ]


def mark_paper_trade_settled(
    con: duckdb.DuckDBPyConnection,
    *,
    trade_id: str,
    settled_at: datetime,
    settlement: str,  # "YES" | "NO" | "VOID"
    pnl_usd: float,
) -> int:
    """Update one row; returns 1 if updated, 0 if no matching unsettled row."""
    if settlement not in {"YES", "NO", "VOID"}:
        raise ValueError(f"settlement must be YES/NO/VOID, got {settlement!r}")
    con.execute(
        """
        UPDATE paper_trade
        SET settled_at = ?, settlement = ?, pnl_usd = ?
        WHERE trade_id = ? AND settled_at IS NULL
        """,
        [_to_naive_utc(settled_at), settlement, pnl_usd, trade_id],
    )
    rowcount = con.execute(
        "SELECT COUNT(*) FROM paper_trade WHERE trade_id = ? AND settled_at IS NOT NULL",
        [trade_id],
    ).fetchone()
    return int(rowcount[0]) if rowcount else 0


def settle_due_paper_trades(
    con: duckdb.DuckDBPyConnection,
    *,
    now: datetime | None = None,
) -> int:
    """Settle every unsettled weather paper trade whose truth has landed.

    For each unsettled trade:
        1. Parse the ticker via `parse_weather_market_ticker`. Skip if it
           isn't a weather contract.
        2. Look up `weather_observed.high_f` for (icao, valid_date). Skip if
           the truth hasn't been ingested yet.
        3. Compute outcome (YES if high > threshold) + P&L; mark settled.

    Returns the number of trades newly settled. Idempotent — already-settled
    trades are not in the candidate set.
    """
    settled_now = now or datetime.now(tz=UTC)
    unsettled = fetch_unsettled_paper_trades(con)
    n_settled = 0
    for trade in unsettled:
        ref = parse_weather_market_ticker(trade.ticker)
        if ref is None:
            log.warning("paper.settle.skip_non_weather", ticker=trade.ticker)
            continue
        observed_row = con.execute(
            "SELECT high_f FROM weather_observed WHERE station = ? AND valid_date = ?",
            [ref.icao, ref.valid_date],
        ).fetchone()
        if observed_row is None or observed_row[0] is None:
            continue  # truth not in DB yet — try again next pass
        observed_high = float(observed_row[0])
        outcome_yes = observed_high > ref.threshold_f
        pnl = settlement_pnl(
            side=trade.side,
            fill_price=trade.limit_price,
            qty=trade.qty,
            fee_usd=trade.fee_usd,
            outcome_yes=outcome_yes,
        )
        mark_paper_trade_settled(
            con,
            trade_id=trade.trade_id,
            settled_at=settled_now,
            settlement="YES" if outcome_yes else "NO",
            pnl_usd=pnl,
        )
        n_settled += 1
        log.info(
            "paper.settle.done",
            trade_id=trade.trade_id,
            ticker=trade.ticker,
            outcome="YES" if outcome_yes else "NO",
            pnl_usd=pnl,
        )
    return n_settled


def settled_pnl_total(con: duckdb.DuckDBPyConnection) -> float:
    """Sum of realized P&L across every settled paper trade. Defaults to 0."""
    row = con.execute(
        "SELECT COALESCE(SUM(pnl_usd), 0.0) FROM paper_trade WHERE settled_at IS NOT NULL"
    ).fetchone()
    return float(row[0]) if row and row[0] is not None else 0.0


def _as_dt(val: object) -> datetime:
    if isinstance(val, datetime):
        return val
    raise TypeError(f"expected datetime, got {type(val).__name__}")


def _as_optional_dt(val: object) -> datetime | None:
    if val is None:
        return None
    return _as_dt(val)


def _as_side(val: object) -> Side:
    s = str(val)
    if s not in ("BUY_YES", "BUY_NO"):
        raise ValueError(f"unsupported side {s!r} (only BUY_YES / BUY_NO in v1)")
    return s  # type: ignore[return-value]


def _to_naive_utc(dt: datetime) -> datetime:
    """Normalize tz-aware → naive UTC; pass naive through unchanged.

    DuckDB's TIMESTAMP type stores naive datetimes. When given a tz-aware
    value, the driver converts to the local timezone *clock time* and
    silently drops the tz — corrupting UTC values. By converting to UTC and
    stripping tz before insert, the stored value matches the source UTC.
    """
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(UTC).replace(tzinfo=None)
