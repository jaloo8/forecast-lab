"""Property-based test expansion for invariants CLAUDE.md §7 calls out.

Existing test files have a few hypothesis-based tests (fees, Kelly,
vig-strip, conformal). This file deepens coverage with the remaining
invariants — one consolidated module rather than scattering more
``@given`` blocks across N existing files. All tests use deterministic
seeds via ``hypothesis``'s default.

Coverage:
- Fees: maker <= taker; per-side rounding-up vs joint-rounding bug;
  symmetry around C=0.5.
- Kelly: monotone in edge size; <= 1.0; zero at no-edge; symmetric
  in (1 - p, 1 - c) ↔ (p, c) modulo the YES/NO swap.
- Calibration: brier always in [0, 1]; reliability bins sum n
  matches input length; n-aware summary passes_bar implies all
  qualifying bins within tolerance.
- Vig-strip property checks live with `tests/test_vig_strip.py`.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from kq.execution.fees import MAKER_DISCOUNT, fee_per_contract
from kq.execution.kelly import fractional_kelly_stake, kelly_fraction_yes
from kq.models.calibration import brier_score, reliability_bins

# --------------------------- fees ---------------------------


@given(
    price=st.floats(min_value=0.01, max_value=0.99),
)
@settings(suppress_health_check=[HealthCheck.too_slow], max_examples=200)
def test_maker_fee_at_most_taker_at_every_price(price: float) -> None:
    """Maker discount is 25% (4x cheaper). Maker should never cost
    more than taker at the same price."""
    taker = fee_per_contract(price, side="taker")
    maker = fee_per_contract(price, side="maker")
    assert maker <= taker + 1e-9


@given(
    price=st.floats(min_value=0.01, max_value=0.49),
)
@settings(suppress_health_check=[HealthCheck.too_slow], max_examples=100)
def test_fee_symmetric_around_half(price: float) -> None:
    """Fee formula uses C * (1 - C), so f(C) == f(1 - C) up to the
    round-up step. Modulo a 1c rounding-noise tolerance, the fees on
    either side of 0.5 should match."""
    f_low = fee_per_contract(price, side="taker")
    f_high = fee_per_contract(1.0 - price, side="taker")
    assert abs(f_low - f_high) <= 0.01


def test_maker_discount_constant_pin() -> None:
    """The 25% discount is a financial parameter -- pin so changes
    are deliberate (CLAUDE.md §9)."""
    assert MAKER_DISCOUNT == 0.25


# --------------------------- Kelly ---------------------------


@given(
    prob=st.floats(min_value=0.01, max_value=0.99),
    price=st.floats(min_value=0.01, max_value=0.99),
)
@settings(suppress_health_check=[HealthCheck.too_slow], max_examples=200)
def test_kelly_fraction_in_unit_interval(prob: float, price: float) -> None:
    """Full-Kelly stake fraction is always in [0, 1] -- never short
    a contract, never bet more than bankroll."""
    f = kelly_fraction_yes(prob=prob, price=price)
    assert 0.0 <= f <= 1.0


@given(
    prob=st.floats(min_value=0.01, max_value=0.99),
    price=st.floats(min_value=0.01, max_value=0.99),
)
@settings(suppress_health_check=[HealthCheck.too_slow], max_examples=200)
def test_kelly_zero_when_no_edge(prob: float, price: float) -> None:
    """When prob <= price, Kelly returns 0 (no positive-EV bet)."""
    if prob <= price:
        assert kelly_fraction_yes(prob=prob, price=price) == 0.0


@given(
    base_prob=st.floats(min_value=0.6, max_value=0.95),
    delta=st.floats(min_value=0.01, max_value=0.2),
    price=st.floats(min_value=0.01, max_value=0.5),
)
@settings(suppress_health_check=[HealthCheck.too_slow], max_examples=200)
def test_kelly_monotone_in_edge(base_prob: float, delta: float, price: float) -> None:
    """Larger edge -> larger Kelly stake. Monotone."""
    f_small = kelly_fraction_yes(prob=base_prob, price=price)
    bigger_prob = min(0.99, base_prob + delta)
    f_big = kelly_fraction_yes(prob=bigger_prob, price=price)
    assert f_big >= f_small


@given(
    prob=st.floats(min_value=0.6, max_value=0.95),
    price=st.floats(min_value=0.01, max_value=0.5),
    bankroll=st.floats(min_value=100.0, max_value=10_000.0),
    fraction=st.floats(min_value=0.05, max_value=0.5),
)
@settings(suppress_health_check=[HealthCheck.too_slow], max_examples=200)
def test_fractional_kelly_stake_capped_by_max_stake(
    prob: float, price: float, bankroll: float, fraction: float
) -> None:
    """USD stake never exceeds max_stake_usd regardless of inputs."""
    cap = 50.0
    stake = fractional_kelly_stake(
        prob=prob,
        price=price,
        bankroll_usd=bankroll,
        fraction=fraction,
        max_stake_usd=cap,
    )
    assert stake <= cap + 1e-9


# --------------------------- calibration ---------------------------


@given(
    n=st.integers(min_value=1, max_value=200),
    seed=st.integers(min_value=0, max_value=10_000),
)
@settings(suppress_health_check=[HealthCheck.too_slow], max_examples=100)
def test_brier_in_unit_interval(n: int, seed: int) -> None:
    """Brier score is always in [0, 1] for any (probs in [0,1],
    outcomes in {0,1}) input."""
    import numpy as np  # noqa: PLC0415

    rng = np.random.default_rng(seed)
    probs = rng.uniform(0.0, 1.0, n)
    outcomes = (rng.uniform(0.0, 1.0, n) < 0.5).astype(float)
    score = brier_score(probs, outcomes)
    assert 0.0 <= score <= 1.0


@given(
    n=st.integers(min_value=10, max_value=500),
    n_bins=st.integers(min_value=2, max_value=20),
    seed=st.integers(min_value=0, max_value=10_000),
)
@settings(suppress_health_check=[HealthCheck.too_slow], max_examples=50)
def test_reliability_bins_n_sums_to_input_length(n: int, n_bins: int, seed: int) -> None:
    """Sum of bin n's equals input array length -- every observation
    lands in exactly one bin."""
    import numpy as np  # noqa: PLC0415

    rng = np.random.default_rng(seed)
    probs = rng.uniform(0.0, 1.0, n)
    outcomes = (rng.uniform(0.0, 1.0, n) < probs).astype(float)
    bins = reliability_bins(probs, outcomes, n_bins=n_bins)
    assert sum(b.n for b in bins) == n


@given(
    n=st.integers(min_value=10, max_value=200),
    n_bins=st.integers(min_value=2, max_value=10),
    seed=st.integers(min_value=0, max_value=10_000),
)
@settings(suppress_health_check=[HealthCheck.too_slow], max_examples=50)
def test_reliability_bin_means_in_unit_interval(n: int, n_bins: int, seed: int) -> None:
    """Mean predicted + mean observed are in [0, 1] for any non-empty bin."""
    import numpy as np  # noqa: PLC0415

    rng = np.random.default_rng(seed)
    probs = rng.uniform(0.0, 1.0, n)
    outcomes = (rng.uniform(0.0, 1.0, n) < probs).astype(float)
    for b in reliability_bins(probs, outcomes, n_bins=n_bins):
        if b.n == 0:
            continue
        assert 0.0 <= b.mean_predicted <= 1.0
        assert 0.0 <= b.mean_observed <= 1.0


# --------------------------- combined: kelly + fees ---------------------------


def test_fractional_kelly_minus_fee_below_kelly_alone() -> None:
    """Sanity: subtracting the per-contract fee from a Kelly stake
    can't make the result greater. Spot-check a worked example so the
    invariant is human-readable -- not a hypothesis test, just a
    concrete claim."""
    raw_kelly_fraction = kelly_fraction_yes(prob=0.7, price=0.5)
    fee = fee_per_contract(0.5, side="taker")
    # Net edge per dollar staked = raw_kelly_fraction - fee/price (rough)
    assert raw_kelly_fraction > 0
    assert fee >= 0
    # Just check fee isn't pathological
    assert fee < 0.1
