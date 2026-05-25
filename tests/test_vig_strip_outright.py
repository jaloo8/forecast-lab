"""Tests for N-way outright (golf) devig: multiplicative + power.

The 2-way moneyline devig lives in ``test_vig_strip.py``; this file covers
only the large-field outright additions used for golf tournament winners.
"""

from __future__ import annotations

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from kq.models.vig_strip import (
    OutrightFairProbabilities,
    OutrightMarket,
    devig_outright,
    devig_outright_multiplicative,
    devig_outright_power,
)

# A golf-like book: short-ish favorites, 35% overround (booksum 1.35).
_FIELD = {"A": 2.0, "B": 2.5, "C": 4.0, "D": 5.0}


# --------------------------- OutrightMarket validation ---------------------------


def test_market_rejects_single_outcome() -> None:
    with pytest.raises(ValueError, match=">= 2 outcomes"):
        OutrightMarket(quotes={"A": 2.0})


def test_market_rejects_non_profitable_odds() -> None:
    with pytest.raises(ValueError, match="must be > 1"):
        OutrightMarket(quotes={"A": 2.0, "B": 1.0})


def test_market_booksum_and_overround() -> None:
    m = OutrightMarket(quotes=_FIELD)
    assert m.booksum == pytest.approx(0.5 + 0.4 + 0.25 + 0.2)
    assert m.overround == pytest.approx(m.booksum - 1.0)


# --------------------------- multiplicative ---------------------------


def test_multiplicative_sums_to_one_and_renormalizes() -> None:
    fair = devig_outright_multiplicative(OutrightMarket(quotes=_FIELD))
    assert isinstance(fair, OutrightFairProbabilities)
    assert fair.method == "proportional"
    assert sum(fair.probs.values()) == pytest.approx(1.0)
    bs = sum(1.0 / o for o in _FIELD.values())
    assert fair.probs["A"] == pytest.approx((1.0 / 2.0) / bs)


# --------------------------- power ---------------------------


def test_power_sums_to_one() -> None:
    fair = devig_outright_power(OutrightMarket(quotes=_FIELD))
    assert fair.method == "power"
    assert sum(fair.probs.values()) == pytest.approx(1.0, abs=1e-9)


def test_power_shifts_mass_toward_favorite() -> None:
    """Power devig must give the favorite MORE weight and the longshot LESS
    than multiplicative — the favorite-longshot bias correction."""
    market = OutrightMarket(quotes=_FIELD)
    mult = devig_outright_multiplicative(market)
    powr = devig_outright_power(market)
    assert powr.probs["A"] > mult.probs["A"]  # favorite gains
    assert powr.probs["D"] < mult.probs["D"]  # longshot loses


def test_dispatch_default_is_power() -> None:
    market = OutrightMarket(quotes=_FIELD)
    assert devig_outright(market).method == "power"
    assert devig_outright(market, method="proportional").method == "proportional"


def test_dispatch_unknown_method_raises() -> None:
    with pytest.raises(ValueError, match="unknown devig method"):
        devig_outright(OutrightMarket(quotes=_FIELD), method="shin")  # type: ignore[arg-type]


# --------------------------- booksum band validation ---------------------------


def test_rejects_booksum_below_floor() -> None:
    # 3 longshots: booksum well under 1.0 -> rejected.
    with pytest.raises(ValueError, match="below minimum"):
        devig_outright_power(OutrightMarket(quotes={"A": 10.0, "B": 12.0, "C": 15.0}))


def test_rejects_booksum_above_ceiling() -> None:
    # Many short-priced outcomes -> booksum way over 3.0.
    fat = {f"P{i}": 1.5 for i in range(10)}  # booksum = 10 * (1/1.5) ~ 6.67
    with pytest.raises(ValueError, match="above maximum"):
        devig_outright_power(OutrightMarket(quotes=fat))


# --------------------------- property: any valid field normalizes ---------------------------


@given(
    odds=st.lists(
        st.floats(min_value=1.2, max_value=50.0, allow_nan=False, allow_infinity=False),
        min_size=3,
        max_size=15,
    )
)
def test_power_devig_always_normalizes(odds: list[float]) -> None:
    quotes = {f"P{i}": o for i, o in enumerate(odds)}
    booksum = sum(1.0 / o for o in odds)
    assume(0.99 <= booksum <= 3.0)  # only test valid books
    fair = devig_outright_power(OutrightMarket(quotes=quotes))
    assert sum(fair.probs.values()) == pytest.approx(1.0, abs=1e-6)
    assert all(0.0 < p < 1.0 for p in fair.probs.values())
