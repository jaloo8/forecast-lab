from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from kq.equities.option_spread import CallQuote, spread_cashflow

NOW = datetime(2026, 10, 19, 14, 0, tzinfo=UTC)


def quotes():
    long = CallQuote("SPY", date(2026, 10, 20), 600, NOW, 1.1, 1.2, 5, 5)
    return long, replace(long, strike=601, bid=0.7, ask=0.8)


def test_hand_calculated_entry_and_exit_include_both_legs_and_fees():
    a, b = quotes()
    entry = spread_cashflow(a, b, NOW, entering=True, signal_at=NOW - timedelta(minutes=1))
    closing = spread_cashflow(a, b, NOW, entering=False)
    assert entry == pytest.approx(-53.3)
    assert closing == pytest.approx(26.7)
    assert entry + closing == pytest.approx(-26.6)


@pytest.mark.parametrize(
    "change",
    [
        {"as_of": NOW + timedelta(seconds=1)},
        {"as_of": NOW - timedelta(seconds=6)},
        {"bid": float("nan")},
        {"bid": 2},
        {"ask_size": 0},
        {"multiplier": 10},
        {"symbol": "QQQ"},
        {"expiry": date(2026, 10, 21)},
        {"strike": 601},
    ],
)
def test_invalid_entry_evidence_fails_closed(change):
    a, b = quotes()
    with pytest.raises(ValueError):
        spread_cashflow(
            replace(a, **change), b, NOW, entering=True, signal_at=NOW - timedelta(minutes=1)
        )


def test_unsynchronized_quotes_and_pre_signal_quotes_rejected():
    a, b = quotes()
    with pytest.raises(ValueError, match="synchron"):
        spread_cashflow(
            replace(a, as_of=NOW - timedelta(seconds=2)),
            b,
            NOW,
            entering=True,
            signal_at=NOW - timedelta(minutes=1),
        )
    with pytest.raises(ValueError, match="signal"):
        spread_cashflow(a, b, NOW, entering=True, signal_at=NOW)


def test_missing_exit_quote_does_not_create_zero_or_profitable_return():
    a, b = quotes()
    with pytest.raises(ValueError):
        spread_cashflow(replace(a, bid_size=0), b, NOW, entering=False)


def test_debit_and_round_trip_fee_reserve_must_fit_research_cash_limit():
    a, b = quotes()
    with pytest.raises(ValueError, match="cash"):
        spread_cashflow(
            a, b, NOW, entering=True, signal_at=NOW - timedelta(minutes=1), cash_limit=54
        )
