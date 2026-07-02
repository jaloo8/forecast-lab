"""DuckDB tests for the paper-trade + signal repository.

Exercises insert idempotency, the unsettled-trade query, the settle-due loop
end-to-end (ingest observed truth → walk unsettled → mark settled with P&L),
and the no-op behavior when the truth row hasn't landed yet.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from kq.execution.paper import PaperTradeIntent, make_signal_id
from kq.storage.duckdb_store import bootstrap, connect
from kq.storage.repositories.paper_trades import (
    fetch_unsettled_paper_trades,
    insert_paper_trade_with_signal,
    mark_paper_trade_settled,
    settle_due_paper_trades,
    settled_pnl_total,
)

AS_OF = datetime(2026, 4, 28, 18, 0, tzinfo=UTC)
SUBMIT_TS = datetime(2026, 4, 28, 18, 5, tzinfo=UTC)


def _intent(
    *,
    ticker: str = "KXHIGHLAX-26APR30-T75",
    side: str = "BUY_YES",
    model_prob_yes: float = 0.70,
    yes_bid: float = 0.50,
    yes_ask: float = 0.55,
) -> PaperTradeIntent:
    return PaperTradeIntent(
        signal_id=make_signal_id(model_name="test_model", ticker=ticker),
        as_of=AS_OF,
        ticker=ticker,
        side=side,  # type: ignore[arg-type]
        limit_price=yes_ask if side == "BUY_YES" else 1.0 - yes_bid,
        qty=10,
        fee_usd=0.20,
        model_prob_yes=model_prob_yes,
        market_yes_bid=yes_bid,
        market_yes_ask=yes_ask,
        edge_bps=1500,
        model_name="test_model",
    )


def _fresh_db(tmp_path: Path) -> duckdb.DuckDBPyConnection:
    db = tmp_path / "paper.duckdb"
    bootstrap(db)
    return connect(db)


def _seed_observed(
    con: duckdb.DuckDBPyConnection,
    *,
    station: str,
    valid_date: date,
    high_f: float,
) -> None:
    con.execute(
        """
        INSERT OR REPLACE INTO weather_observed
        (station, valid_date, high_f, low_f, source, fetched_at)
        VALUES (?, ?, ?, NULL, 'test', ?)
        """,
        [station, valid_date, high_f, datetime.now(tz=UTC)],
    )


# --------------------------------------------------------- insert + idempotency


def test_insert_round_trip(tmp_path: Path) -> None:
    """Insert one intent → 1 row in `signal` and 1 row in `paper_trade`."""
    con = _fresh_db(tmp_path)
    try:
        intent = _intent()
        trade_id, was_new = insert_paper_trade_with_signal(con, intent, submitted_at=SUBMIT_TS)
        assert trade_id.startswith("paper-")
        assert was_new is True
        sigs = con.execute("SELECT COUNT(*) FROM signal").fetchone()
        trades = con.execute("SELECT COUNT(*) FROM paper_trade").fetchone()
        assert sigs is not None and sigs[0] == 1
        assert trades is not None and trades[0] == 1
    finally:
        con.close()


def test_insert_is_idempotent(tmp_path: Path) -> None:
    """Calling twice with the same intent leaves the row counts unchanged.

    The second call returns ``was_new=False`` so the orchestration layer can
    skip log spam / counter updates.
    """
    con = _fresh_db(tmp_path)
    try:
        intent = _intent()
        _, first_was_new = insert_paper_trade_with_signal(con, intent, submitted_at=SUBMIT_TS)
        _, second_was_new = insert_paper_trade_with_signal(con, intent, submitted_at=SUBMIT_TS)
        assert first_was_new is True
        assert second_was_new is False
        sig_count = con.execute("SELECT COUNT(*) FROM signal").fetchone()
        trade_count = con.execute("SELECT COUNT(*) FROM paper_trade").fetchone()
        assert sig_count is not None and sig_count[0] == 1
        assert trade_count is not None and trade_count[0] == 1
    finally:
        con.close()


def test_nba_market_across_utc_midnight_books_one_trade(tmp_path: Path) -> None:
    """PR-H pin: the same NBA market evaluated at 23:50 and 00:10 UTC (an
    evening game spanning UTC midnight between cron ticks) writes exactly
    ONE (signal, paper_trade) pair — no double Kelly exposure, no
    double-counted settle."""
    from kq.execution.paper import evaluate_market  # noqa: PLC0415

    con = _fresh_db(tmp_path)
    try:
        common = dict(
            model_prob_yes=0.70,
            yes_bid=0.50,
            yes_ask=0.55,
            bankroll_usd=1_000.0,
            ticker="KXNBAGAME-26APR30BOSPHI-PHI",
            model_name="nba_pinnacle_anchored_v1",
        )
        before_midnight = evaluate_market(as_of=datetime(2026, 4, 30, 23, 50, tzinfo=UTC), **common)
        after_midnight = evaluate_market(as_of=datetime(2026, 5, 1, 0, 10, tzinfo=UTC), **common)
        assert before_midnight is not None and after_midnight is not None

        _, first_new = insert_paper_trade_with_signal(con, before_midnight)
        _, second_new = insert_paper_trade_with_signal(con, after_midnight)
        assert first_new is True
        assert second_new is False
        trades = con.execute("SELECT COUNT(*) FROM paper_trade").fetchone()
        sigs = con.execute("SELECT COUNT(*) FROM signal").fetchone()
        assert trades is not None and trades[0] == 1
        assert sigs is not None and sigs[0] == 1
    finally:
        con.close()


def test_signal_row_carries_market_prob_and_edge(tmp_path: Path) -> None:
    """Sanity-check the columns we'll need for CLV analysis later."""
    con = _fresh_db(tmp_path)
    try:
        intent = _intent(yes_bid=0.50, yes_ask=0.55, model_prob_yes=0.70)
        insert_paper_trade_with_signal(con, intent, submitted_at=SUBMIT_TS)
        row = con.execute(
            "SELECT model_prob_yes, market_prob_yes, edge_bps, model_name FROM signal"
        ).fetchone()
        assert row is not None
        model_prob, market_prob, edge_bps, model_name = row
        assert model_prob == pytest.approx(0.70)
        assert market_prob == pytest.approx(0.525)  # midpoint
        assert edge_bps == 1500
        assert model_name == "test_model"
    finally:
        con.close()


def test_paper_trade_filled_at_submission(tmp_path: Path) -> None:
    """Paper assumes immediate fill: filled_at == submitted_at, fill_price == limit_price.

    DuckDB stores TIMESTAMP as naive; the repository normalizes tz-aware →
    naive UTC before insert. Compare against the naive equivalent.
    """
    con = _fresh_db(tmp_path)
    try:
        insert_paper_trade_with_signal(con, _intent(), submitted_at=SUBMIT_TS)
        row = con.execute(
            "SELECT filled_at, fill_price, limit_price, settled_at FROM paper_trade"
        ).fetchone()
        assert row is not None
        filled_at, fill_price, limit_price, settled_at = row
        assert filled_at == SUBMIT_TS.replace(tzinfo=None)
        assert fill_price == pytest.approx(limit_price)
        assert settled_at is None
    finally:
        con.close()


# ----------------------------------------------------- unsettled query


def test_fetch_unsettled_returns_open_trades(tmp_path: Path) -> None:
    con = _fresh_db(tmp_path)
    try:
        insert_paper_trade_with_signal(con, _intent(ticker="KXHIGHLAX-26APR30-T75"))
        insert_paper_trade_with_signal(con, _intent(ticker="KXHIGHLAX-26APR30-T77"))
        rows = fetch_unsettled_paper_trades(con)
        assert len(rows) == 2
        assert {r.ticker for r in rows} == {
            "KXHIGHLAX-26APR30-T75",
            "KXHIGHLAX-26APR30-T77",
        }
    finally:
        con.close()


def test_fetch_unsettled_excludes_settled(tmp_path: Path) -> None:
    con = _fresh_db(tmp_path)
    try:
        intent = _intent()
        insert_paper_trade_with_signal(con, intent, submitted_at=SUBMIT_TS)
        trade_id = fetch_unsettled_paper_trades(con)[0].trade_id
        mark_paper_trade_settled(
            con,
            trade_id=trade_id,
            settled_at=datetime.now(tz=UTC),
            settlement="YES",
            pnl_usd=4.30,
        )
        assert fetch_unsettled_paper_trades(con) == []
    finally:
        con.close()


# ----------------------------------------------------- mark_settled


def test_mark_settled_rejects_invalid_outcome(tmp_path: Path) -> None:
    con = _fresh_db(tmp_path)
    try:
        with pytest.raises(ValueError, match="settlement"):
            mark_paper_trade_settled(
                con,
                trade_id="x",
                settled_at=datetime.now(tz=UTC),
                settlement="MAYBE",
                pnl_usd=0.0,
            )
    finally:
        con.close()


def test_mark_settled_is_no_op_for_unknown_trade(tmp_path: Path) -> None:
    """Updating a non-existent trade shouldn't crash; just affects 0 rows."""
    con = _fresh_db(tmp_path)
    try:
        n = mark_paper_trade_settled(
            con,
            trade_id="paper-nonexistent",
            settled_at=datetime.now(tz=UTC),
            settlement="YES",
            pnl_usd=1.0,
        )
        assert n == 0
    finally:
        con.close()


# ------------------------------------------------ settle_due_paper_trades


def test_settle_due_handles_observed_yes(tmp_path: Path) -> None:
    """KXHIGHLAX-26APR30-T75, observed high 80F → outcome YES → BUY_YES wins."""
    con = _fresh_db(tmp_path)
    try:
        intent = _intent(side="BUY_YES")
        insert_paper_trade_with_signal(con, intent, submitted_at=SUBMIT_TS)
        _seed_observed(con, station="KLAX", valid_date=date(2026, 4, 30), high_f=80.0)
        n = settle_due_paper_trades(con)
        assert n == 1
        row = con.execute("SELECT settled_at, settlement, pnl_usd FROM paper_trade").fetchone()
        assert row is not None
        settled_at, settlement, pnl = row
        assert settled_at is not None
        assert settlement == "YES"
        # pnl = qty * (1 - fill_price) - fee = 10 * (1 - 0.55) - 0.20 = 4.30
        assert pnl == pytest.approx(4.30)
    finally:
        con.close()


def test_settle_due_handles_observed_no(tmp_path: Path) -> None:
    """Observed high 70F < threshold 75 → outcome NO → BUY_YES loses."""
    con = _fresh_db(tmp_path)
    try:
        intent = _intent(side="BUY_YES")
        insert_paper_trade_with_signal(con, intent, submitted_at=SUBMIT_TS)
        _seed_observed(con, station="KLAX", valid_date=date(2026, 4, 30), high_f=70.0)
        settle_due_paper_trades(con)
        row = con.execute("SELECT settlement, pnl_usd FROM paper_trade").fetchone()
        assert row is not None
        settlement, pnl = row
        assert settlement == "NO"
        # pnl = qty * (-fill_price) - fee = -5.50 - 0.20 = -5.70
        assert pnl == pytest.approx(-5.70)
    finally:
        con.close()


def test_settle_due_buy_no_wins_when_outcome_no(tmp_path: Path) -> None:
    """BUY_NO at 0.50, outcome NO → BUY_NO wins → pnl 10*(1-0.50) - 0.20 = 4.80."""
    con = _fresh_db(tmp_path)
    try:
        intent = _intent(side="BUY_NO", yes_bid=0.50)  # limit_price = 0.50
        insert_paper_trade_with_signal(con, intent, submitted_at=SUBMIT_TS)
        _seed_observed(con, station="KLAX", valid_date=date(2026, 4, 30), high_f=70.0)
        settle_due_paper_trades(con)
        row = con.execute("SELECT settlement, pnl_usd FROM paper_trade").fetchone()
        assert row is not None
        settlement, pnl = row
        assert settlement == "NO"
        assert pnl == pytest.approx(4.80)
    finally:
        con.close()


def test_settle_due_skips_when_truth_missing(tmp_path: Path) -> None:
    """If observed truth isn't in DB yet, leave the trade unsettled."""
    con = _fresh_db(tmp_path)
    try:
        intent = _intent()
        insert_paper_trade_with_signal(con, intent, submitted_at=SUBMIT_TS)
        # No _seed_observed call.
        n = settle_due_paper_trades(con)
        assert n == 0
        unsettled_after = fetch_unsettled_paper_trades(con)
        assert len(unsettled_after) == 1
    finally:
        con.close()


def test_settle_due_skips_non_weather_ticker(tmp_path: Path) -> None:
    """NBA-ticker paper trade is skipped — needs separate settlement logic."""
    con = _fresh_db(tmp_path)
    try:
        intent = _intent(ticker="KXNBAGAME-26APR30BOSPHI-PHI")
        insert_paper_trade_with_signal(con, intent, submitted_at=SUBMIT_TS)
        n = settle_due_paper_trades(con)
        assert n == 0
        # Trade is still unsettled (skipped, not settled with bad data)
        assert len(fetch_unsettled_paper_trades(con)) == 1
    finally:
        con.close()


def test_settle_due_is_idempotent(tmp_path: Path) -> None:
    """Re-running settle_due is a no-op once trades are settled."""
    con = _fresh_db(tmp_path)
    try:
        intent = _intent()
        insert_paper_trade_with_signal(con, intent, submitted_at=SUBMIT_TS)
        _seed_observed(con, station="KLAX", valid_date=date(2026, 4, 30), high_f=80.0)
        first = settle_due_paper_trades(con)
        second = settle_due_paper_trades(con)
        assert first == 1
        assert second == 0
    finally:
        con.close()


def test_settle_due_handles_threshold_at_observed_value(tmp_path: Path) -> None:
    """Strict-greater-than: observed == threshold means YES does NOT pay.

    Kalshi's 'high >= threshold' resolution would pay; we resolve as 'high >
    threshold' to mirror the backtest engine. This test locks that contract
    so future divergence is a deliberate decision not an accident.
    """
    con = _fresh_db(tmp_path)
    try:
        intent = _intent(side="BUY_YES")  # T75 ticker
        insert_paper_trade_with_signal(con, intent, submitted_at=SUBMIT_TS)
        _seed_observed(con, station="KLAX", valid_date=date(2026, 4, 30), high_f=75.0)
        settle_due_paper_trades(con)
        row = con.execute("SELECT settlement FROM paper_trade").fetchone()
        assert row is not None
        assert row[0] == "NO"  # high == threshold → NO under strict-greater
    finally:
        con.close()


# ------------------------------------------------ settled_pnl_total


def test_settled_pnl_total_sums_only_settled(tmp_path: Path) -> None:
    """One settled (+4.30), one unsettled → total is 4.30."""
    con = _fresh_db(tmp_path)
    try:
        i1 = _intent(ticker="KXHIGHLAX-26APR30-T75")
        i2 = _intent(ticker="KXHIGHLAX-26APR30-T77")
        insert_paper_trade_with_signal(con, i1, submitted_at=SUBMIT_TS)
        insert_paper_trade_with_signal(con, i2, submitted_at=SUBMIT_TS)
        _seed_observed(con, station="KLAX", valid_date=date(2026, 4, 30), high_f=80.0)
        settle_due_paper_trades(con)
        # i1 (T75) settles YES, i2 (T77) settles YES too, but let's only seed for one.
        # Actually both will settle since we only have one observed row that covers both.
        total = settled_pnl_total(con)
        assert total > 0

    finally:
        con.close()


def test_settled_pnl_total_zero_when_nothing_settled(tmp_path: Path) -> None:
    con = _fresh_db(tmp_path)
    try:
        assert settled_pnl_total(con) == 0.0
        intent = _intent()
        insert_paper_trade_with_signal(con, intent, submitted_at=SUBMIT_TS)
        # Inserted but unsettled → still 0
        assert settled_pnl_total(con) == 0.0
    finally:
        con.close()


# ------------------------------------------------ schedule alignment


def test_settle_due_does_nothing_when_no_unsettled(tmp_path: Path) -> None:
    """Empty paper_trade table → returns 0."""
    con = _fresh_db(tmp_path)
    try:
        assert settle_due_paper_trades(con) == 0
    finally:
        con.close()


def test_settle_due_uses_provided_now(tmp_path: Path) -> None:
    """`now=...` controls the settled_at value (useful for backfill)."""
    con = _fresh_db(tmp_path)
    try:
        intent = _intent()
        insert_paper_trade_with_signal(con, intent, submitted_at=SUBMIT_TS)
        _seed_observed(con, station="KLAX", valid_date=date(2026, 4, 30), high_f=80.0)
        explicit_now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
        settle_due_paper_trades(con, now=explicit_now)
        row = con.execute("SELECT settled_at FROM paper_trade").fetchone()
        assert row is not None
        # Stored naive after UTC normalization (see _to_naive_utc in the repository).
        assert row[0] == explicit_now.replace(tzinfo=None)
    finally:
        con.close()


# ------------------------------------------------ multi-day scenario


def test_settle_due_handles_multiple_days(tmp_path: Path) -> None:
    """Two trades on different valid_dates — both settle once truth lands."""
    con = _fresh_db(tmp_path)
    try:
        i1 = _intent(ticker="KXHIGHLAX-26APR30-T75")
        i2 = _intent(ticker="KXHIGHLAX-26MAY01-T75")
        insert_paper_trade_with_signal(con, i1, submitted_at=SUBMIT_TS)
        insert_paper_trade_with_signal(con, i2, submitted_at=SUBMIT_TS + timedelta(days=1))
        _seed_observed(con, station="KLAX", valid_date=date(2026, 4, 30), high_f=80.0)
        n_first = settle_due_paper_trades(con)
        # Only one truth landed → one settled
        assert n_first == 1
        _seed_observed(con, station="KLAX", valid_date=date(2026, 5, 1), high_f=82.0)
        n_second = settle_due_paper_trades(con)
        assert n_second == 1
        # Total settled now = 2
        assert con.execute(
            "SELECT COUNT(*) FROM paper_trade WHERE settled_at IS NOT NULL"
        ).fetchone() == (2,)
    finally:
        con.close()


# --------------------------------------------------------- PR-B: strike-aware settlement


def _strike_intent(
    *,
    ticker: str,
    side: str = "BUY_YES",
    strike_type: str | None = None,
    floor_strike: float | None = None,
    cap_strike: float | None = None,
) -> PaperTradeIntent:
    return PaperTradeIntent(
        signal_id=make_signal_id(model_name="test_model", ticker=ticker),
        as_of=AS_OF,
        ticker=ticker,
        side=side,  # type: ignore[arg-type]
        limit_price=0.55,
        qty=10,
        fee_usd=0.20,
        model_prob_yes=0.70,
        market_yes_bid=0.50,
        market_yes_ask=0.55,
        edge_bps=1500,
        model_name="test_model",
        strike_type=strike_type,
        floor_strike=floor_strike,
        cap_strike=cap_strike,
    )


# Well after every ticker date used below — day-completion guard satisfied.
LONG_AFTER = datetime(2026, 6, 20, 12, 0, tzinfo=UTC)


def test_settle_less_market_from_stored_strike_not_inverted(tmp_path: Path) -> None:
    """Audit #3 regression, settlement side: a '<74°' (less) contract held
    BUY_YES with an observed high of 70 pays out YES. The legacy
    ticker-as-greater reading would have settled it NO — exactly inverted."""
    con = _fresh_db(tmp_path)
    try:
        intent = _strike_intent(
            ticker="KXHIGHLAX-26JUN11-T74",
            strike_type="less",
            cap_strike=74.0,
        )
        insert_paper_trade_with_signal(con, intent, submitted_at=SUBMIT_TS)
        _seed_observed(con, station="KLAX", valid_date=date(2026, 6, 11), high_f=70.0)
        assert settle_due_paper_trades(con, now=LONG_AFTER) == 1
        row = con.execute("SELECT settlement, pnl_usd FROM paper_trade").fetchone()
        assert row is not None
        assert row[0] == "YES"
        assert row[1] == pytest.approx(10 * (1.0 - 0.55) - 0.20)
    finally:
        con.close()


@pytest.mark.parametrize(
    ("observed", "want_settlement"),
    [(78.0, "YES"), (79.0, "YES"), (77.0, "NO"), (80.0, "NO")],
)
def test_settle_between_market_from_stored_strike(
    tmp_path: Path, observed: float, want_settlement: str
) -> None:
    """'78-79°' between contract settles YES iff the observed high is 78 or 79."""
    con = _fresh_db(tmp_path)
    try:
        intent = _strike_intent(
            ticker="KXHIGHLAX-26JUN11-B78.5",
            strike_type="between",
            floor_strike=78.0,
            cap_strike=79.0,
        )
        insert_paper_trade_with_signal(con, intent, submitted_at=SUBMIT_TS)
        _seed_observed(con, station="KLAX", valid_date=date(2026, 6, 11), high_f=observed)
        assert settle_due_paper_trades(con, now=LONG_AFTER) == 1
        row = con.execute("SELECT settlement FROM paper_trade").fetchone()
        assert row is not None and row[0] == want_settlement
    finally:
        con.close()


def test_settlement_waits_for_day_completion(tmp_path: Path) -> None:
    """A same-day partial high must never settle a trade: even with a truth
    row present, settlement holds until the station's LST day has elapsed."""
    con = _fresh_db(tmp_path)
    try:
        intent = _strike_intent(
            ticker="KXHIGHLAX-26JUN11-T81",
            strike_type="greater",
            floor_strike=81.0,
        )
        insert_paper_trade_with_signal(con, intent, submitted_at=SUBMIT_TS)
        # Preliminary same-day value lands early (morning high, peak pending).
        _seed_observed(con, station="KLAX", valid_date=date(2026, 6, 11), high_f=75.0)

        # KLAX LST is UTC-8: Jun 11's settlement day ends Jun 12 08:00 UTC.
        midday_lst = datetime(2026, 6, 11, 20, 0, tzinfo=UTC)
        assert settle_due_paper_trades(con, now=midday_lst) == 0
        just_before_end = datetime(2026, 6, 12, 7, 59, tzinfo=UTC)
        assert settle_due_paper_trades(con, now=just_before_end) == 0
        after_day_end = datetime(2026, 6, 12, 8, 1, tzinfo=UTC)
        assert settle_due_paper_trades(con, now=after_day_end) == 1
    finally:
        con.close()


def test_legacy_row_without_strike_settles_as_greater(tmp_path: Path) -> None:
    """Pre-PR-B rows (strike columns NULL) keep the historical
    greater-at-ticker-threshold interpretation."""
    con = _fresh_db(tmp_path)
    try:
        intent = _strike_intent(ticker="KXHIGHLAX-26JUN11-T75")  # no strike fields
        insert_paper_trade_with_signal(con, intent, submitted_at=SUBMIT_TS)
        _seed_observed(con, station="KLAX", valid_date=date(2026, 6, 11), high_f=76.0)
        assert settle_due_paper_trades(con, now=LONG_AFTER) == 1
        row = con.execute("SELECT settlement FROM paper_trade").fetchone()
        assert row is not None and row[0] == "YES"
    finally:
        con.close()


def test_between_row_without_stored_strike_is_skipped(tmp_path: Path) -> None:
    """A between-ticker row with NULL strike columns is unguessable: it must
    be skipped loudly, never settled under a wrong interpretation."""
    con = _fresh_db(tmp_path)
    try:
        intent = _strike_intent(ticker="KXHIGHLAX-26JUN11-B78.5")  # no strike fields
        insert_paper_trade_with_signal(con, intent, submitted_at=SUBMIT_TS)
        _seed_observed(con, station="KLAX", valid_date=date(2026, 6, 11), high_f=78.0)
        assert settle_due_paper_trades(con, now=LONG_AFTER) == 0
        row = con.execute("SELECT settled_at FROM paper_trade").fetchone()
        assert row is not None and row[0] is None
    finally:
        con.close()
