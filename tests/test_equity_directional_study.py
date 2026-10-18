import numpy as np
import pandas as pd
import pytest

from kq.equities.directional_study import simulate_directional


def bars() -> pd.DataFrame:
    dates = pd.bdate_range("2004-12-01", periods=900)
    return pd.concat(
        [
            pd.DataFrame({"symbol": symbol, "session_date": dates, "open": prices, "close": prices})
            for symbol, prices in [("SPY", np.full(900, 100.0)), ("AAPL", 100 + np.arange(900))]
        ],
        ignore_index=True,
    )


def first(frame: pd.DataFrame, rule: str = "S20", horizon: str = "5s") -> pd.Series:
    result = simulate_directional(frame)
    return result[(result.rule == rule) & (result.horizon == horizon)].iloc[0]


@pytest.mark.parametrize("cost_bps", [10.0, 25.0, 50.0])
def test_next_open_exact_endpoint_and_two_sided_costs(cost_bps: float) -> None:
    frame = bars()
    dates = frame[frame.symbol == "SPY"].session_date.reset_index(drop=True)
    decision = int(dates.searchsorted(pd.Timestamp("2006-01-01")))
    stock = frame.symbol == "AAPL"
    frame.loc[stock & (frame.session_date == dates[decision + 1]), "open"] = 200.0
    frame.loc[stock & (frame.session_date == dates[decision + 6]), "open"] = 220.0
    frame.loc[stock & (frame.session_date == dates[decision + 6]), "close"] = 999.0
    result = simulate_directional(frame, cost_bps=cost_bps)
    row = result[(result.rule == "S20") & (result.horizon == "5s")].iloc[0]
    cost = cost_bps / 10000
    assert row.decision_date == dates[decision]
    assert row.entry_date == dates[decision + 1]
    assert row.exit_date == dates[decision + 6]
    assert row.gross_return == pytest.approx(0.1)
    assert row.net_return == pytest.approx(1.1 * (1 - cost) / (1 + cost) - 1)
    assert row.spy_net_return == pytest.approx((1 - cost) / (1 + cost) - 1)
    assert row.excess_vs_spy == pytest.approx(row.net_return - row.spy_net_return)
    assert row.as_of == row.decision_date.tz_localize("America/New_York") + pd.Timedelta(hours=16)
    assert str(row.as_of.tz) == "UTC"


@pytest.mark.parametrize("spy_trend", [0, 2])
def test_all_rules_fixed_cadence_and_feature_formulas(spy_trend: int) -> None:
    frame = bars()
    frame.loc[frame.symbol == "SPY", "close"] += spy_trend * np.arange(900)
    result = simulate_directional(frame, cost_bps=25.0)
    assert set(zip(result.rule, result.horizon, strict=True)) == {
        ("S20", "5s"),
        ("S20", "20s"),
        ("S5", "5s"),
        ("S5", "20s"),
        ("L12-1", "6m"),
        ("L12-1", "12m"),
        ("L12-1", "18m"),
    }
    dates = frame[frame.symbol == "SPY"].session_date.reset_index(drop=True)
    index = int(dates.searchsorted(pd.Timestamp("2006-01-01")))
    for rule, stride in [("S20", 5), ("S5", 5), ("L12-1", 21)]:
        assert (
            result[result.rule == rule].decision_date.unique().tolist()
            == dates[index::stride].tolist()
        )
    for rule, lookback, skip, horizon in [
        ("S20", 20, 0, "5s"),
        ("S5", 5, 0, "5s"),
        ("L12-1", 252, 21, "6m"),
    ]:
        start, end = index - lookback, index - skip
        expected = (100 + end) / (100 + start) / (
            (100 + spy_trend * end) / (100 + spy_trend * start)
        ) - 1
        row = first(frame, rule, horizon)
        assert row.feature_value == pytest.approx(expected)
        assert row.signal == np.sign(expected) * (-1 if rule == "S5" else 1)


def test_calendar_month_roll_uses_first_observed_session() -> None:
    frame = bars()
    frame = frame[~frame.session_date.between("2006-01-01", "2006-08-29")]
    result = simulate_directional(frame)
    row = result[(result.rule == "L12-1") & (result.horizon == "6m")].iloc[0]
    assert row.entry_date == pd.Timestamp("2006-08-31")
    assert row.exit_date == pd.Timestamp("2007-02-28")
    dates = frame[frame.symbol == "SPY"].session_date
    target = row.entry_date + pd.DateOffset(months=6)
    assert row.exit_date == dates[dates >= target].iloc[0]
    assert row.gross_return == pytest.approx(
        frame[(frame.symbol == "AAPL") & (frame.session_date == row.exit_date)].open.iloc[0]
        / frame[(frame.symbol == "AAPL") & (frame.session_date == row.entry_date)].open.iloc[0]
        - 1
    )


def test_future_price_perturbation_preserves_features() -> None:
    frame = bars()
    cutoff = pd.Timestamp("2006-06-01")
    original = simulate_directional(frame)
    frame.loc[frame.session_date > cutoff, ["open", "close"]] *= 7
    changed = simulate_directional(frame)
    columns = ["rule", "horizon", "symbol", "decision_date", "signal", "feature_value", "as_of"]
    pd.testing.assert_frame_equal(
        original.loc[original.decision_date <= cutoff, columns],
        changed.loc[changed.decision_date <= cutoff, columns],
    )


def test_missing_mature_prices_and_ipo_are_retained() -> None:
    frame = bars()
    row = first(frame)
    missing = frame[~((frame.symbol == "AAPL") & (frame.session_date == row.exit_date))]
    outcome = first(missing)
    assert outcome.status == "unavailable"
    assert outcome.exit_date == row.exit_date
    assert pd.isna(outcome.net_return)
    late = frame[~((frame.symbol == "AAPL") & (frame.session_date < row.decision_date))]
    assert first(late).status == "excluded"
    assert first(late).reason == "insufficient_history"
    assert simulate_directional(frame).iloc[-1].status == "pending"
    missing_entry = frame[~((frame.symbol == "AAPL") & (frame.session_date == row.entry_date))]
    assert first(missing_entry).status == "unavailable"
    missing_day = row.decision_date - pd.Timedelta(days=7)
    missing_warmup = frame[~((frame.symbol == "AAPL") & (frame.session_date == missing_day))]
    assert first(missing_warmup).status == "excluded"


@pytest.mark.parametrize("rising", [True, False])
def test_bearish_is_long_outcome_and_absolute_relative_hits_differ(rising: bool) -> None:
    frame = bars()
    row = first(frame, "S5")
    frame.loc[(frame.symbol == "AAPL") & (frame.session_date == row.entry_date), "open"] = 100
    frame.loc[(frame.symbol == "AAPL") & (frame.session_date == row.exit_date), "open"] = (
        110 if rising else 90
    )
    frame.loc[(frame.symbol == "SPY") & (frame.session_date == row.exit_date), "open"] = 120
    row = first(frame, "S5")
    assert row.signal == -1
    assert row.gross_return == pytest.approx(0.1 if rising else -0.1)
    assert bool(row.absolute_hit) is (not rising)
    assert bool(row.relative_hit)


def test_zero_feature_and_outcome_ties_are_not_hits() -> None:
    frame = bars()
    frame.loc[frame.symbol == "SPY", ["open", "close"]] = (
        frame.loc[frame.symbol == "AAPL", ["open", "close"]].to_numpy() * 2
    )
    result = simulate_directional(frame)
    assert set(result.signal) == {0}
    complete = result[result.status == "complete"]
    assert not complete.absolute_hit.any() and not complete.relative_hit.any()
    frame = bars()
    frame["open"] = 100.0
    row = first(frame)
    assert row.signal == 1 and not row.absolute_hit and not row.relative_hit


@pytest.mark.parametrize(
    "mutation",
    [
        "empty",
        "duplicate",
        "date",
        "price",
        "zero",
        "negative",
        "nan",
        "schema",
        "intraday",
        "boolean",
        "unaligned",
        "symbol",
        "spy",
        "future",
    ],
)
def test_invalid_inputs_rejected(mutation: str) -> None:
    frame = bars()
    if mutation == "empty":
        frame = frame.iloc[:0]
    elif mutation == "duplicate":
        frame = pd.concat([frame, frame.iloc[:1]])
    elif mutation == "date":
        frame.loc[0, "session_date"] = pd.NaT
    elif mutation in {"price", "zero", "negative", "nan"}:
        frame.loc[0, "open"] = {"price": np.inf, "zero": 0, "negative": -1, "nan": np.nan}[mutation]
    elif mutation == "schema":
        frame = frame.drop(columns="open")
    elif mutation == "intraday":
        frame.loc[0, "session_date"] += pd.Timedelta(hours=1)
    elif mutation == "boolean":
        frame["open"] = frame.open.astype(object)
        frame.loc[0, "open"] = True
    elif mutation == "unaligned":
        frame.loc[900, "session_date"] = pd.Timestamp("2004-12-04")
    elif mutation == "symbol":
        frame.loc[0, "symbol"] = "bad symbol"
    elif mutation == "spy":
        frame = frame[frame.symbol != "SPY"]
    else:
        frame.loc[0, "session_date"] = pd.Timestamp("2026-01-01")
    with pytest.raises(ValueError):
        simulate_directional(frame)


@pytest.mark.parametrize("cost", [-1.0, float("nan"), float("inf"), 10000.0, True])
def test_invalid_costs_rejected(cost: float) -> None:
    with pytest.raises(ValueError):
        simulate_directional(bars(), cost_bps=cost)
