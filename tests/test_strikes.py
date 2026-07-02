"""Strike-aware pricing + settlement (``kq.clients.kalshi.strikes``, PR-B).

The load-bearing regression here is audit root-cause #3 (2026-06-11): prod
low-tail ``-T<n>`` markets are ``strike_type='less'`` — the legacy
ticker-text path priced AND settled them as *greater*, i.e. exactly
inverted. These tests pin the corrected semantics against the recorded prod
fixture and the analytic Gaussian so the inversion can never come back.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from kq.clients.kalshi._parsers import _parse_market
from kq.clients.kalshi._ticker_parser import parse_weather_market_ticker
from kq.clients.kalshi._types import Market
from kq.clients.kalshi.strikes import (
    Strike,
    strike_from_market,
    yes_outcome,
    yes_prob,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _gaussian_prob_gt(mu: float, sigma: float):
    """Analytic P(T > x) for a Gaussian — the model shape NGR/raw emit."""

    def prob_gt(x: float) -> float:
        return 0.5 * math.erfc((x - mu) / (sigma * math.sqrt(2.0)))

    return prob_gt


def _mk_market(**overrides: object) -> Market:
    base: dict[str, object] = {
        "ticker": "KXHIGHLAX-26JUN12-T81",
        "event_ticker": "KXHIGHLAX-26JUN12",
        "title": "",
        "status": "active",
        "category": None,
        "yes_ask": 0.02,
        "yes_bid": 0.01,
        "last_price": None,
        "volume": None,
        "open_interest": None,
        "open_time": None,
        "close_time": None,
        "expected_expiration_time": None,
        "rules_primary": None,
        "strike_type": "greater",
        "floor_strike": 81.0,
        "cap_strike": None,
    }
    base.update(overrides)
    return Market(**base)  # type: ignore[arg-type]


# --------------------------- Strike construction ---------------------------


def test_strike_from_recorded_prod_fixture_all_three_kinds() -> None:
    """Every market in the recorded prod payload yields an authoritative Strike."""
    payload = json.loads((FIXTURES / "kalshi_prod_markets_weather.json").read_text())
    kinds: dict[str, int] = {}
    for raw in payload["markets"]:
        market = _parse_market(raw)
        ref = parse_weather_market_ticker(market.ticker)
        assert ref is not None, market.ticker
        strike = strike_from_market(market, ref)
        assert strike is not None, market.ticker
        kinds[strike.kind] = kinds.get(strike.kind, 0) + 1
    # The prod ladder carries all three semantics; between dominates.
    assert kinds["greater"] >= 2
    assert kinds["less"] >= 2
    assert kinds["between"] >= 4


def test_strike_refuses_ticker_api_disagreement() -> None:
    m = _mk_market(strike_type="greater", floor_strike=79.0)  # ticker says T81
    ref = parse_weather_market_ticker(m.ticker)
    assert strike_from_market(m, ref) is None


def test_legacy_payload_falls_back_to_greater_only_in_demo_mode() -> None:
    """Demo payloads carry no strike fields; the historical T-as-greater
    reading survives there, but only behind the explicit opt-in flag."""
    m = _mk_market(strike_type=None, floor_strike=None)
    ref = parse_weather_market_ticker(m.ticker)
    strike = strike_from_market(m, ref, allow_legacy_ticker_semantics=True)
    assert strike == Strike(kind="greater", floor=81.0, cap=None)


def test_missing_strike_fields_refused_under_prod_semantics() -> None:
    """Fail-closed guard: without the demo opt-in, a payload that lost its
    strike fields is refused. Guessing greater on prod would re-enable the
    inverted-less bug (audit #3) on any low-tail -T ticker."""
    m = _mk_market(strike_type=None, floor_strike=None)
    ref = parse_weather_market_ticker(m.ticker)
    assert strike_from_market(m, ref) is None
    assert strike_from_market(m, ref, allow_legacy_ticker_semantics=False) is None


def test_legacy_payload_never_guesses_between_tickers() -> None:
    m = _mk_market(ticker="KXHIGHLAX-26JUN12-B78.5", strike_type=None)
    ref = parse_weather_market_ticker(m.ticker)
    assert ref is not None and ref.kind == "B"
    # Unguessable even in demo mode.
    assert strike_from_market(m, ref, allow_legacy_ticker_semantics=True) is None
    assert strike_from_market(m, ref) is None


def test_between_ticker_midpoint_crosscheck() -> None:
    m = _mk_market(
        ticker="KXHIGHLAX-26JUN12-B78.5",
        strike_type="between",
        floor_strike=78.0,
        cap_strike=79.0,
    )
    ref = parse_weather_market_ticker(m.ticker)
    strike = strike_from_market(m, ref)
    assert strike == Strike(kind="between", floor=78.0, cap=79.0)
    # Disagreeing midpoint is refused.
    m_bad = _mk_market(
        ticker="KXHIGHLAX-26JUN12-B78.5",
        strike_type="between",
        floor_strike=80.0,
        cap_strike=81.0,
    )
    assert strike_from_market(m_bad, parse_weather_market_ticker(m_bad.ticker)) is None


def test_strike_rejects_unknown_kind_and_missing_bounds() -> None:
    with pytest.raises(ValueError):
        Strike(kind="weird", floor=1.0, cap=2.0)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        Strike(kind="greater", floor=None, cap=None)
    with pytest.raises(ValueError):
        Strike(kind="between", floor=80.0, cap=78.0)


# --------------------------- Pricing ---------------------------


def test_less_market_prices_below_mass_not_inverted() -> None:
    """Audit #3 regression: '<74°' with the forecast far BELOW the cap must be
    near-certain YES — the legacy greater-interpretation gave near-certain NO."""
    prob_gt = _gaussian_prob_gt(mu=65.0, sigma=3.0)
    less = Strike(kind="less", floor=None, cap=74.0)
    assert yes_prob(less, prob_gt) > 0.95
    # And the inverted reading would have been < 0.05:
    greater_misread = Strike(kind="greater", floor=74.0, cap=None)
    assert yes_prob(greater_misread, prob_gt) < 0.05


def test_between_market_gets_full_two_degree_mass() -> None:
    """'74-75°' spans integer temps {74, 75} → continuous mass on
    [73.5, 75.5), not the 1-degree naive [74, 75] slice."""
    mu, sigma = 74.5, 2.0
    prob_gt = _gaussian_prob_gt(mu, sigma)
    between = Strike(kind="between", floor=74.0, cap=75.0)
    got = yes_prob(between, prob_gt)
    want = prob_gt(73.5) - prob_gt(75.5)
    assert got == pytest.approx(want)
    naive_one_degree = prob_gt(74.0) - prob_gt(75.0)
    assert got > 1.8 * naive_one_degree  # the naive slice halves the true mass


def test_greater_market_uses_half_degree_boundary() -> None:
    prob_gt = _gaussian_prob_gt(mu=81.0, sigma=2.0)
    greater = Strike(kind="greater", floor=81.0, cap=None)
    # ">81°" = integer 82+ = continuous mass above 81.5, NOT above 81.
    assert yes_prob(greater, prob_gt) == pytest.approx(prob_gt(81.5))


@given(
    mu=st.floats(min_value=40.0, max_value=110.0),
    sigma=st.floats(min_value=0.5, max_value=8.0),
)
def test_full_ladder_probabilities_tile_to_one(mu: float, sigma: float) -> None:
    """A prod-shaped ladder (less | 4 betweens | greater) must sum to ~1
    before clipping — the strike boundaries partition the real line."""
    prob_gt = _gaussian_prob_gt(mu, sigma)
    ladder = [
        Strike(kind="less", floor=None, cap=74.0),
        Strike(kind="between", floor=74.0, cap=75.0),
        Strike(kind="between", floor=76.0, cap=77.0),
        Strike(kind="between", floor=78.0, cap=79.0),
        Strike(kind="between", floor=80.0, cap=81.0),
        Strike(kind="greater", floor=81.0, cap=None),
    ]
    total = sum(yes_prob(s, prob_gt) for s in ladder)
    # Clipping floors each leg at 0.01, so allow the ladder-size margin.
    assert total == pytest.approx(1.0, abs=0.01 * len(ladder))


def test_yes_prob_clipped_to_project_range() -> None:
    prob_gt = _gaussian_prob_gt(mu=100.0, sigma=1.0)
    far_below = Strike(kind="less", floor=None, cap=50.0)
    far_above = Strike(kind="greater", floor=50.0, cap=None)
    assert yes_prob(far_below, prob_gt) == 0.01
    assert yes_prob(far_above, prob_gt) == 0.99


# --------------------------- Settlement ---------------------------


@pytest.mark.parametrize(
    ("strike", "observed", "want_yes"),
    [
        # greater '>81°': YES iff integer settle value >= 82
        (Strike(kind="greater", floor=81.0, cap=None), 82.0, True),
        (Strike(kind="greater", floor=81.0, cap=None), 81.0, False),
        # less '<74°': YES iff integer settle value <= 73
        (Strike(kind="less", floor=None, cap=74.0), 73.0, True),
        (Strike(kind="less", floor=None, cap=74.0), 74.0, False),
        (Strike(kind="less", floor=None, cap=74.0), 70.0, True),
        # between '74-75°': YES iff settle value in {74, 75}
        (Strike(kind="between", floor=74.0, cap=75.0), 74.0, True),
        (Strike(kind="between", floor=74.0, cap=75.0), 75.0, True),
        (Strike(kind="between", floor=74.0, cap=75.0), 73.0, False),
        (Strike(kind="between", floor=74.0, cap=75.0), 76.0, False),
    ],
)
def test_yes_outcome_integer_semantics(strike: Strike, observed: float, want_yes: bool) -> None:
    assert yes_outcome(strike, observed) is want_yes


def test_settlement_and_pricing_boundaries_agree() -> None:
    """The same half-degree boundary drives pricing and settlement, so an
    integer settle value can never be priced on one side and settled on the
    other. (Exact half-degree observations are excluded — they're measure
    zero for the continuous model and impossible in whole-°F NWS reports.)"""
    strike = Strike(kind="between", floor=74.0, cap=75.0)
    for observed in (73.0, 73.4, 74.0, 74.9, 75.0, 75.4, 76.0, 77.0):
        prob_gt = lambda x, obs=observed: 1.0 if x < obs else 0.0  # noqa: E731
        priced_in = yes_prob(strike, prob_gt) > 0.5
        assert priced_in == yes_outcome(strike, observed), observed
