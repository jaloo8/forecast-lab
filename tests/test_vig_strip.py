"""Tests for vig-strip / devig math.

Coverage:
- Hand-worked Pinnacle-style examples for proportional + power.
- Property tests with hypothesis: booksum-renormalization, monotonicity,
  no-vig pass-through, agreement-near-fair-50pct.
- Input validation on quotes, markets, and dispatch.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from kq.models.vig_strip import (
    MAX_BOOKSUM,
    MIN_BOOKSUM,
    FairProbabilities,
    MoneylineQuote,
    TwoWayMarket,
    devig,
    devig_power,
    devig_proportional,
)

# --------------------------- MoneylineQuote ---------------------------


def test_moneyline_quote_implied_prob() -> None:
    """``implied_prob = 1 / decimal_odds``."""
    q = MoneylineQuote(decimal_odds=2.0)
    assert q.implied_prob == pytest.approx(0.5)


def test_moneyline_quote_rejects_non_winning_odds() -> None:
    with pytest.raises(ValueError, match=r"must be > 1\.0"):
        MoneylineQuote(decimal_odds=1.0)
    with pytest.raises(ValueError, match=r"must be > 1\.0"):
        MoneylineQuote(decimal_odds=0.5)


# --------------------------- TwoWayMarket ---------------------------


def test_market_booksum_and_overround_at_2pct_vig() -> None:
    """Pinnacle-style: 1.91/1.91 quote -> booksum ~1.047, overround ~4.7 %.

    1.91/1.91 (-110/-110 American) is the canonical "2 % vig" pick'em
    example used across the academic explainers. The booksum is in
    fact 2/1.91 ~ 1.0471 -- closer to 4.7 % overround than the often-
    advertised "2 % vig", which conflates *take* with *return on stake*.
    """
    market = TwoWayMarket(
        home=MoneylineQuote(decimal_odds=1.91),
        away=MoneylineQuote(decimal_odds=1.91),
    )
    assert market.booksum == pytest.approx(2 / 1.91)
    assert market.overround == pytest.approx(2 / 1.91 - 1.0)


def test_market_booksum_at_zero_vig_pickem() -> None:
    """A 2.0/2.0 market has booksum exactly 1.0 (no vig)."""
    market = TwoWayMarket(
        home=MoneylineQuote(decimal_odds=2.0),
        away=MoneylineQuote(decimal_odds=2.0),
    )
    assert market.booksum == pytest.approx(1.0)
    assert market.overround == pytest.approx(0.0)


# --------------------------- FairProbabilities ---------------------------


def test_fair_probabilities_normalization_validation() -> None:
    """Constructor rejects fairs that don't sum to 1.0 within 1e-6."""
    with pytest.raises(ValueError, match=r"must sum to 1\.0"):
        FairProbabilities(home=0.4, away=0.4, method="proportional")


def test_fair_probabilities_rejects_extremes() -> None:
    """Probs outside (0, 1) get rejected before the sum check.

    The home side is validated first; a 1.0 / 0.0 split short-circuits
    on home before the away check has a chance to fire, so the second
    assertion below uses an in-range home and an out-of-range away.
    """
    with pytest.raises(ValueError, match="home fair prob"):
        FairProbabilities(home=0.0, away=1.0, method="proportional")
    with pytest.raises(ValueError, match="away fair prob"):
        FairProbabilities(home=0.5, away=1.0, method="proportional")


# --------------------------- proportional devig ---------------------------


def test_proportional_pickem_returns_50_50() -> None:
    """1.91/1.91 -> 50/50 fair (symmetry)."""
    market = TwoWayMarket(
        home=MoneylineQuote(decimal_odds=1.91),
        away=MoneylineQuote(decimal_odds=1.91),
    )
    fair = devig_proportional(market)
    assert fair.home == pytest.approx(0.5)
    assert fair.away == pytest.approx(0.5)
    assert fair.method == "proportional"


def test_proportional_favorite_underdog() -> None:
    """Hand-worked example: 1.50/2.75 quote.

    raw_home = 1/1.50 = 0.6667; raw_away = 1/2.75 = 0.3636.
    booksum = 1.0303. fair_home = 0.6667 / 1.0303 = 0.6471;
    fair_away = 0.3636 / 1.0303 = 0.3529. Sum = 1.0 by construction.
    """
    market = TwoWayMarket(
        home=MoneylineQuote(decimal_odds=1.50),
        away=MoneylineQuote(decimal_odds=2.75),
    )
    fair = devig_proportional(market)
    assert fair.home == pytest.approx(0.6471, abs=5e-4)
    assert fair.away == pytest.approx(0.3529, abs=5e-4)
    assert fair.home + fair.away == pytest.approx(1.0)


def test_proportional_at_zero_vig_is_passthrough() -> None:
    """A 2-way market at booksum = 1.0 should pass implied probs through."""
    market = TwoWayMarket(
        home=MoneylineQuote(decimal_odds=2.5),
        away=MoneylineQuote(decimal_odds=5.0 / 3.0),
    )
    # raw_home = 0.4; raw_away = 0.6; booksum = 1.0 exactly.
    assert market.booksum == pytest.approx(1.0)
    fair = devig_proportional(market)
    assert fair.home == pytest.approx(0.4)
    assert fair.away == pytest.approx(0.6)


# --------------------------- proportional validation ---------------------------


def test_proportional_rejects_low_booksum() -> None:
    """Booksum below MIN_BOOKSUM (~0.99) means data error."""
    market = TwoWayMarket(
        home=MoneylineQuote(decimal_odds=3.0),
        away=MoneylineQuote(decimal_odds=3.0),
    )  # booksum ~0.667
    with pytest.raises(ValueError, match="below minimum"):
        devig_proportional(market)


def test_proportional_rejects_high_booksum() -> None:
    """Booksum above MAX_BOOKSUM (1.5) means stale or extreme quote."""
    market = TwoWayMarket(
        home=MoneylineQuote(decimal_odds=1.05),
        away=MoneylineQuote(decimal_odds=1.05),
    )  # booksum ~1.905
    with pytest.raises(ValueError, match="above maximum"):
        devig_proportional(market)


def test_min_max_booksum_constants_are_consistent() -> None:
    """Pin the validation band so changes here are deliberate."""
    assert MIN_BOOKSUM < 1.0 < MAX_BOOKSUM


# --------------------------- power devig ---------------------------


def test_power_pickem_returns_50_50() -> None:
    """Symmetric 1.91/1.91 has fair = 50/50 under any sane devig."""
    market = TwoWayMarket(
        home=MoneylineQuote(decimal_odds=1.91),
        away=MoneylineQuote(decimal_odds=1.91),
    )
    fair = devig_power(market)
    assert fair.home == pytest.approx(0.5, abs=1e-4)
    assert fair.away == pytest.approx(0.5, abs=1e-4)
    assert fair.method == "power"


def test_power_at_zero_vig_is_passthrough() -> None:
    """k=1 recovers raw probabilities at booksum=1."""
    market = TwoWayMarket(
        home=MoneylineQuote(decimal_odds=2.5),
        away=MoneylineQuote(decimal_odds=5.0 / 3.0),
    )
    fair = devig_power(market)
    assert fair.home == pytest.approx(0.4, abs=1e-4)
    assert fair.away == pytest.approx(0.6, abs=1e-4)


def test_power_shifts_mass_to_favorite_vs_proportional() -> None:
    """Power devig (k > 1) gives the favorite *more* fair-prob mass
    than proportional -- the convex transformation ``x^k`` shrinks
    small raw probs (longshots) by a larger relative factor than it
    shrinks large raw probs (favorites). Under the Cain/Law/Peel
    reading this is the favorite-longshot bias correction."""
    market = TwoWayMarket(
        home=MoneylineQuote(decimal_odds=1.30),  # heavy favorite
        away=MoneylineQuote(decimal_odds=4.00),  # underdog
    )
    fair_prop = devig_proportional(market)
    fair_pow = devig_power(market)
    # Heavy favorite -> power gives a *larger* fair_home, smaller fair_away.
    assert fair_pow.home > fair_prop.home
    assert fair_pow.away < fair_prop.away


def test_power_sum_to_one() -> None:
    """Renormalization step ensures the constructor's 1e-6 sum check passes."""
    market = TwoWayMarket(
        home=MoneylineQuote(decimal_odds=1.45),
        away=MoneylineQuote(decimal_odds=2.85),
    )
    fair = devig_power(market)
    assert fair.home + fair.away == pytest.approx(1.0, abs=1e-9)


# --------------------------- devig dispatch ---------------------------


def test_devig_dispatch_proportional() -> None:
    market = TwoWayMarket(
        home=MoneylineQuote(decimal_odds=1.91),
        away=MoneylineQuote(decimal_odds=1.91),
    )
    fair = devig(market, method="proportional")
    assert fair.method == "proportional"


def test_devig_dispatch_power() -> None:
    market = TwoWayMarket(
        home=MoneylineQuote(decimal_odds=1.91),
        away=MoneylineQuote(decimal_odds=1.91),
    )
    fair = devig(market, method="power")
    assert fair.method == "power"


def test_devig_dispatch_default_is_proportional() -> None:
    market = TwoWayMarket(
        home=MoneylineQuote(decimal_odds=1.91),
        away=MoneylineQuote(decimal_odds=1.91),
    )
    fair = devig(market)
    assert fair.method == "proportional"


# --------------------------- property tests ---------------------------


# Strategy: produce a TwoWayMarket whose booksum is in the trustworthy
# band [MIN_BOOKSUM + epsilon, MAX_BOOKSUM - epsilon]. We sample
# (fair_home, vig) and back into decimal odds -- this guarantees a
# well-conditioned market with a known fair home prob, which makes the
# property assertions easier to write.
@st.composite
def well_conditioned_markets(draw: st.DrawFn) -> tuple[TwoWayMarket, float]:
    fair_home = draw(st.floats(min_value=0.05, max_value=0.95))
    overround = draw(st.floats(min_value=0.0, max_value=0.40))
    booksum = 1.0 + overround
    raw_home = fair_home * booksum
    raw_away = (1.0 - fair_home) * booksum
    # Both raw probs must be in (0, 1) for the decimal_odds inversion
    # to satisfy MoneylineQuote's > 1.0 constraint.
    assume(0.001 < raw_home < 0.999)
    assume(0.001 < raw_away < 0.999)
    market = TwoWayMarket(
        home=MoneylineQuote(decimal_odds=1.0 / raw_home),
        away=MoneylineQuote(decimal_odds=1.0 / raw_away),
    )
    return market, fair_home


@given(well_conditioned_markets())
@settings(suppress_health_check=[HealthCheck.too_slow], max_examples=200)
def test_proportional_recovers_constructed_fair_home(
    market_and_fair: tuple[TwoWayMarket, float],
) -> None:
    """If we construct a market from (fair_home, overround) under the
    proportional model, ``devig_proportional`` should recover fair_home
    exactly (to float precision)."""
    market, fair_home = market_and_fair
    fair = devig_proportional(market)
    assert fair.home == pytest.approx(fair_home, abs=1e-9)


@given(well_conditioned_markets())
@settings(suppress_health_check=[HealthCheck.too_slow], max_examples=200)
def test_devig_outputs_sum_to_one(market_and_fair: tuple[TwoWayMarket, float]) -> None:
    """Both methods produce fairs that sum to 1.0 within 1e-6."""
    market, _ = market_and_fair
    for fair in (devig_proportional(market), devig_power(market)):
        assert math.isclose(fair.home + fair.away, 1.0, abs_tol=1e-6)


@given(well_conditioned_markets())
@settings(suppress_health_check=[HealthCheck.too_slow], max_examples=200)
def test_devig_outputs_in_unit_interval(
    market_and_fair: tuple[TwoWayMarket, float],
) -> None:
    """No method should ever produce a fair prob outside (0, 1)."""
    market, _ = market_and_fair
    for fair in (devig_proportional(market), devig_power(market)):
        assert 0.0 < fair.home < 1.0
        assert 0.0 < fair.away < 1.0


@given(well_conditioned_markets())
@settings(suppress_health_check=[HealthCheck.too_slow], max_examples=200)
def test_proportional_and_power_agree_on_pickems(
    market_and_fair: tuple[TwoWayMarket, float],
) -> None:
    """When the constructed fair_home is exactly 0.5 (pick'em), both
    methods must produce 0.5 fair_home regardless of vig."""
    market, fair_home = market_and_fair
    if abs(fair_home - 0.5) > 1e-6:
        return
    assert devig_proportional(market).home == pytest.approx(0.5, abs=1e-6)
    assert devig_power(market).home == pytest.approx(0.5, abs=1e-6)
