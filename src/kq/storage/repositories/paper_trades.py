"""Paper-trading + signal repository.

Two tables, written together as a unit by :func:`insert_paper_trade_with_signal`
because every paper trade must reference its source signal (FK constraint).

Idempotency: ``signal_id`` and ``trade_id`` are deterministic content hashes
emitted by ``kq.execution.paper.make_signal_id`` / ``make_trade_id``, so
re-running the submit pass on the same forecast row is a no-op via
``INSERT OR IGNORE``. We use OR IGNORE rather than OR REPLACE so a partially
filled trade isn't accidentally stomped by a newer evaluation.

The settlement helpers walk every unsettled paper trade for their vertical,
look up the matching observed truth row, and write the settlement back to
``paper_trade``:

* :func:`settle_due_paper_trades` handles weather contracts. Trades whose
  ticker isn't a weather contract are left alone.
* :func:`settle_due_nba_paper_trades` handles NBA-game-winner contracts.
  Trades whose ticker isn't an NBA-game contract are left alone.

The split is deliberate: each vertical has its own truth source
(``weather_observed`` vs ``nba_game``) and its own ticker parser; mixing
them in one function would force the truth-lookup branch on every iteration.
The flow layer (``flows/paper_trade.py`` / ``flows/paper_nba_trade.py``) is
responsible for calling the right settle for the trades it produces.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

from kq.clients.kalshi._ticker_parser import WeatherMarketRef, parse_weather_market_ticker
from kq.clients.kalshi._ticker_parser_nba import NbaMarketRef, parse_nba_market_ticker
from kq.clients.kalshi.strikes import Strike, yes_outcome
from kq.clients.stations import STATIONS_BY_ICAO
from kq.execution.paper import (
    PaperTradeIntent,
    Side,
    make_trade_id,
    settlement_pnl,
)
from kq.storage._tz import to_naive_utc as _to_naive_utc
from kq.utils.kalshi_dates import settlement_day_bounds

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
    # PR-B: contract resolution semantics captured at submit time. NULL only
    # on legacy rows (pre-PR-B) and demo payloads — those settle under the
    # historical greater-at-ticker-threshold rule.
    strike_type: str | None = None
    floor_strike: float | None = None
    cap_strike: float | None = None


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
         fee_usd, filled_at, fill_price, settled_at, settlement, pnl_usd,
         strike_type, floor_strike, cap_strike)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?, ?)
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
            intent.strike_type,
            intent.floor_strike,
            intent.cap_strike,
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
               qty, fee_usd, filled_at, fill_price, settled_at, settlement, pnl_usd,
               strike_type, floor_strike, cap_strike
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
            strike_type=str(r[13]) if r[13] is not None else None,
            floor_strike=float(r[14]) if r[14] is not None else None,
            cap_strike=float(r[15]) if r[15] is not None else None,
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
        2. **Day-completion guard (PR-B):** skip unless the station's LST
           settlement day has fully elapsed. A same-day partial high (e.g. a
           preliminary morning value with the afternoon peak still to come)
           must never settle a trade — settlement is irreversible.
        3. Look up `weather_observed.high_f` for (icao, valid_date). Skip if
           the truth hasn't been ingested yet.
        4. Compute the outcome from the trade's **stored strike fields**
           (greater / less / between — `kq.clients.kalshi.strikes`), falling
           back to the legacy greater-at-ticker-threshold rule only for
           pre-PR-B rows. Mark settled with P&L.

    Returns the number of trades newly settled. Idempotent — already-settled
    trades are not in the candidate set.
    """
    settled_now = now or datetime.now(tz=UTC)
    now_utc = settled_now if settled_now.tzinfo is not None else settled_now.replace(tzinfo=UTC)
    unsettled = fetch_unsettled_paper_trades(con)
    n_settled = 0
    for trade in unsettled:
        ref = parse_weather_market_ticker(trade.ticker)
        if ref is None:
            log.warning("paper.settle.skip_non_weather", ticker=trade.ticker)
            continue
        station = STATIONS_BY_ICAO.get(ref.icao)
        if station is not None:
            _, day_end_utc = settlement_day_bounds(station, ref.valid_date)
            if now_utc < day_end_utc:
                continue  # settlement day still in progress — high not final
        strike = _strike_for_settlement(trade, ref)
        if strike is None:
            log.warning(
                "paper.settle.skip_no_strike",
                trade_id=trade.trade_id,
                ticker=trade.ticker,
                detail="no stored strike fields and ticker is not a tail market",
            )
            continue
        observed_row = con.execute(
            "SELECT high_f FROM weather_observed WHERE station = ? AND valid_date = ?",
            [ref.icao, ref.valid_date],
        ).fetchone()
        if observed_row is None or observed_row[0] is None:
            continue  # truth not in DB yet — try again next pass
        observed_high = float(observed_row[0])
        outcome_yes = yes_outcome(strike, observed_high)
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
            strike=f"{strike.kind}[{strike.floor},{strike.cap}]",
            observed_high_f=observed_high,
            outcome="YES" if outcome_yes else "NO",
            pnl_usd=pnl,
        )
    return n_settled


def _strike_for_settlement(trade: PaperTradeRow, ref: WeatherMarketRef) -> Strike | None:
    """Reconstruct the contract's resolution semantics for settlement.

    Stored strike fields win (captured at submit time from the prod API).
    Legacy rows (pre-PR-B, strike columns NULL) settle under the historical
    interpretation — ``-T<int>`` as a *greater* contract at the ticker
    threshold. A ``-B`` row without stored fields is unguessable.
    """
    if trade.strike_type is not None:
        try:
            return Strike(
                kind=trade.strike_type,  # type: ignore[arg-type]
                floor=trade.floor_strike,
                cap=trade.cap_strike,
            )
        except ValueError:
            log.warning(
                "paper.settle.bad_stored_strike",
                trade_id=trade.trade_id,
                strike_type=trade.strike_type,
                floor=trade.floor_strike,
                cap=trade.cap_strike,
            )
            return None
    if ref.kind == "T":
        return Strike(kind="greater", floor=float(ref.threshold_f), cap=None)
    return None


def settle_due_nba_paper_trades(
    con: duckdb.DuckDBPyConnection,
    *,
    now: datetime | None = None,
) -> int:
    """Settle every unsettled NBA paper trade whose game has resolved.

    For each unsettled trade:
        1. Parse the ticker via :func:`parse_nba_market_ticker`. Skip if it
           isn't an NBA-game contract (left to the weather settler).
        2. Look up the matching row in ``nba_game`` keyed on
           ``(game_date, home_team_abbr, away_team_abbr)``. Skip if the game
           isn't on the schedule yet (ingest hasn't picked it up).
        3. Skip if ``home_won`` is still NULL (game in progress / not yet
           ingested as finished).
        4. Compute YES outcome by aligning the ticker's YES side with the
           actual winner; settle P&L via :func:`settlement_pnl`.

    Returns the count of newly settled trades. Idempotent — already-settled
    trades are excluded from the candidate set.

    Pairs with :func:`settle_due_paper_trades` (the weather version). Each
    settle ignores tickers belonging to the other vertical, so calling both
    in succession on the same unsettled pool is safe.
    """
    settled_now = now or datetime.now(tz=UTC)
    unsettled = fetch_unsettled_paper_trades(con)
    n_settled = 0
    for trade in unsettled:
        ref = parse_nba_market_ticker(trade.ticker)
        if ref is None:
            # Not an NBA contract — leave for weather settler (or future verticals).
            continue
        outcome = _lookup_nba_home_won(con, ref)
        if outcome is None:
            continue  # game not on schedule yet, or still in progress
        outcome_yes = outcome if ref.yes_is_home else not outcome
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
            "paper.settle.nba_done",
            trade_id=trade.trade_id,
            ticker=trade.ticker,
            outcome="YES" if outcome_yes else "NO",
            home_won=outcome,
            pnl_usd=pnl,
        )
    return n_settled


def _lookup_nba_home_won(
    con: duckdb.DuckDBPyConnection,
    ref: NbaMarketRef,
) -> bool | None:
    """Look up ``nba_game.home_won`` for the game referenced by an NBA ticker.

    Returns ``True`` (home won), ``False`` (away won), or ``None`` (game not
    on schedule yet, or finished but ``home_won`` still NULL).

    The ``nba_game`` row identification uses ``(game_date, home_team_abbr,
    away_team_abbr)`` rather than ``game_id`` because the Kalshi ticker
    doesn't carry the nba_api game_id. We accept the small risk that two
    games with the same home/away/date exist (almost never happens in
    practice; a doubleheader is the only realistic edge case).
    """
    row = con.execute(
        """
        SELECT home_won
        FROM nba_game
        WHERE game_date = ?
          AND home_team_abbr = ?
          AND away_team_abbr = ?
        LIMIT 1
        """,
        [ref.game_date, ref.home_team_abbr, ref.away_team_abbr],
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return bool(row[0])


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
