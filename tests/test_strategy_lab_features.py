from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime, time

import numpy as np
import pandas as pd
import pytest

from kq.equities.strategy_lab.features import score_candidates
from kq.equities.strategy_lab.registry import SelectionSpec, selection_specs


def bars() -> pd.DataFrame:
    records = []
    for i, day in enumerate(pd.bdate_range("2026-01-02", periods=24)):
        for symbol, close in (("SPY", 100 + i), ("AAA", 100 + 2 * i), ("BBB", 100 - i)):
            records.append(
                dict(
                    symbol=symbol,
                    session_date=day.date(),
                    open=close,
                    high=close + 1,
                    low=close - 1,
                    close=close,
                    volume=2_000_000,
                    as_of=datetime.combine(day.date(), time(21), UTC),
                )
            )
    return pd.DataFrame(records)


def score(frame: pd.DataFrame, family: str = "momentum") -> pd.DataFrame:
    return score_candidates(frame, date(2026, 2, 3), family, 10).set_index("symbol")


def test_registry_is_unique_immutable_and_complete() -> None:
    specs = selection_specs()
    assert len(specs) == len({spec.selection_id for spec in specs}) == 100
    assert {spec.lookback for spec in specs} == {10, 20, 40, 60}
    assert {spec.size for spec in specs} == {1, 3, 5, 10, 20}
    with pytest.raises(FrozenInstanceError):
        specs[0].size = 2  # type: ignore[misc]
    with pytest.raises(ValueError):
        SelectionSpec("unknown", 10, 1)


@pytest.mark.parametrize(
    "family", ["momentum", "risk_momentum", "reversal", "low_volatility", "breakout"]
)
def test_scores_match_hand_calculations(family: str) -> None:
    result = score(bars(), family)
    prices = np.arange(124, 145, 2, dtype=float)
    volatility = np.std(np.log(prices[1:] / prices[:-1]), ddof=1)
    expected = {
        "momentum": 144 / 124 - 122 / 112,
        "risk_momentum": (np.log(144 / 124) - np.log(122 / 112)) / (volatility * np.sqrt(10)),
        "reversal": -(78 / 88 - 1),
        "low_volatility": -volatility,
        "breakout": 144 / 142 - 1,
    }
    symbol = "BBB" if family == "reversal" else "AAA"
    assert result.loc[symbol, "score"] == pytest.approx(expected[family])
    assert result.loc[symbol, "eligible"]
    assert "SPY" not in result.index
    assert result.loc[symbol, "as_of"] == datetime(2026, 2, 3, 21, tzinfo=UTC)


def test_future_bars_do_not_change_scores_and_ties_use_symbol() -> None:
    frame = bars()
    duplicate = frame[frame.symbol == "AAA"].assign(symbol="AAC")
    frame = pd.concat([duplicate, frame], ignore_index=True)
    original = score(frame)
    frame.loc[frame.session_date > date(2026, 2, 3), "close"] = 1e9
    pd.testing.assert_frame_equal(original, score(frame))
    assert list(original.index[:2]) == ["AAA", "AAC"]


@pytest.mark.parametrize(
    "kind,reason",
    [
        ("missing", "insufficient_history"),
        ("duplicate", "duplicate_session"),
        ("invalid", "invalid_bar"),
        ("zero_volume", "invalid_bar"),
        ("cheap", "below_minimum_price"),
        ("illiquid", "insufficient_liquidity"),
        ("synthetic", "invalid_bar"),
        ("late", "unavailable_as_of"),
    ],
)
def test_exclusions_remain_explicit(kind: str, reason: str) -> None:
    frame = bars()
    mask = (frame.symbol == "AAA") & (frame.session_date == date(2026, 2, 3))
    if kind == "missing":
        frame = frame[~mask]
    elif kind == "duplicate":
        frame = pd.concat([frame, frame[mask]], ignore_index=True)
    elif kind == "invalid":
        frame.loc[mask, "high"] = 1
    elif kind == "zero_volume":
        frame.loc[mask, "volume"] = 0
    elif kind == "cheap":
        frame.loc[mask, ["open", "close", "low", "high"]] = 4
    elif kind == "illiquid":
        frame.loc[frame.symbol == "AAA", "volume"] = 1
    elif kind == "synthetic":
        frame["synthetic"] = False
        frame.loc[mask, "synthetic"] = True
    else:
        frame.loc[mask, "as_of"] = datetime(2026, 2, 4, tzinfo=UTC)
    result = score(frame)
    assert not result.loc["AAA", "eligible"]
    assert result.loc["AAA", "reason"] == reason
    assert pd.isna(result.loc["AAA", "score"])


def test_flat_stock_is_unavailable_for_risk_momentum_but_valid_low_volatility() -> None:
    frame = bars()
    frame.loc[frame.symbol == "AAA", ["open", "close", "low", "high"]] = 100
    assert score(frame, "risk_momentum").loc["AAA", "reason"] == "zero_volatility"
    low_vol = score(frame, "low_volatility")
    assert low_vol.loc["AAA", "eligible"]
    assert low_vol.loc["AAA", "score"] == 0


def test_missing_benchmark_and_short_history_are_unavailable() -> None:
    frame = bars()
    assert set(score(frame[frame.symbol != "SPY"]).reason) == {"unavailable_benchmark"}
    short = score_candidates(frame, date(2026, 1, 15), "momentum", 10)
    assert not short.eligible.any()


def test_wrong_direction_is_excluded() -> None:
    assert score(bars()).loc["BBB", "reason"] == "signal_not_positive"
    assert score(bars(), "reversal").loc["AAA", "reason"] == "signal_not_positive"


def test_boolean_ohlcv_is_not_a_real_price() -> None:
    frame = bars()
    frame["volume"] = frame.volume.astype(object)
    frame.loc[frame.symbol == "AAA", "volume"] = True
    assert score(frame).loc["AAA", "reason"] == "invalid_bar"


def test_price_and_liquidity_thresholds_are_inclusive() -> None:
    frame = bars()
    mask = frame.symbol == "AAA"
    frame.loc[mask, ["open", "high", "low", "close"]] = 5
    frame.loc[mask, "volume"] = 4_000_000
    assert score(frame, "low_volatility").loc["AAA", "eligible"]


def test_invalid_benchmark_blocks_all_candidates() -> None:
    frame = bars()
    frame.loc[frame.symbol == "SPY", "volume"] = 0
    assert set(score(frame).reason) == {"unavailable_benchmark"}
