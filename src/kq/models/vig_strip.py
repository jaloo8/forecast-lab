"""Vig-strip / "devig" math for 2-way moneyline markets.

Sportsbooks quote each side of a moneyline at odds whose **implied
probabilities sum to more than 1.0**. The excess is the *overround* (or
*vig*); the book's expected take per unit volume. Recovering the
**fair probability** -- the book's view of the true outcome -- requires
inverting the vig.

For Phase 3 we need a fair-value anchor for NBA moneylines, ideally
sourced from Pinnacle (the lowest-vig, highest-volume book in the
business; CLV against Pinnacle is the closest thing to a public
"market-truth" benchmark). This module provides the math layer; the
Odds-API / balldontlie clients in a later PR consume it.

Two methods, each with a different bias correction:

- :func:`devig_proportional` -- the workhorse. Divides each side's
  implied probability by the booksum so the total renormalizes to 1.0.
  Implicitly assumes vig is proportional to the underlying fair odds,
  which holds approximately at Pinnacle (per Levitt 2004, Smith et al.
  2009, and the Pinnacle/Wong 2023 academic explainer). At ~2 % vig
  this is within ~50 bp of the more involved Shin/power methods.

- :func:`devig_power` -- Kuypers/Cain power method. Solves for ``k``
  such that ``sum_i (p_raw_i ** k) = 1``. ``k > 1`` shifts mass toward
  the favorite relative to proportional (because ``x^k`` is convex on
  (0, 1) so larger raw probs shrink less in *relative* terms after
  renormalization). This corrects the favorite-longshot bias under the
  Cain/Law/Peel reading: bettors overbet longshots, books respond by
  shading longshot prices in -- the *true* fair longshot probability is
  smaller than proportional devigging would suggest, so more weight
  belongs on the favorite. Worth using when Pinnacle isn't available
  and we have to devig a higher-vig book (DraftKings, FanDuel) where
  the bias is larger.

We deliberately do not ship the Shin (1993) devig in v1: the closed
form for 2-way markets exists but the parameter ``z`` (insider trader
proportion) is fragile to estimate per-game and the empirical Brier
improvement vs proportional is < 50 bp at Pinnacle's vig levels.
Adding Shin without a calibration pipeline would be theatre.

References:
- Pinnacle. "How does no-vig pricing work?" academic explainer.
- Cain, Law, Peel (2003). "The favourite-longshot bias, bookmaker
  margins, and insider trading in a variety of betting markets."
- Levitt (2004). "Why are gambling markets organised so differently
  from financial markets?"
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Literal

# Float epsilon for booksum / overround validation. Pinnacle vig on NBA
# moneylines is typically ~2 % (booksum ~1.02); a booksum below 1.0
# would mean the book is paying users to bet -- always a data error.
MIN_BOOKSUM: Final = 0.99
# Upper bound on booksum we'll accept. Anything above ~1.5 (50 % vig)
# is almost certainly a stale / off-market quote we should reject.
MAX_BOOKSUM: Final = 1.5

# Power-method solver tolerance. Sub-bp on the resulting fair prob.
POWER_TOL: Final = 1e-9
# Max bisection iterations. With a tolerance of 1e-9 over a 0.5..3.0
# bracket, ~33 iterations suffice; we cap at 100 for safety.
POWER_MAX_ITER: Final = 100

DevigMethod = Literal["proportional", "power"]


@dataclass(frozen=True, slots=True)
class MoneylineQuote:
    """One side of a moneyline market quoted in decimal odds.

    Decimal odds are the European convention: a quote of ``1.91``
    means a winning $1 stake returns $1.91 ($0.91 profit). Other
    conventions (American, fractional) convert into decimal cleanly;
    we accept only decimal here to keep the math layer single-format.
    """

    decimal_odds: float

    def __post_init__(self) -> None:
        if self.decimal_odds <= 1.0:
            raise ValueError(
                f"decimal_odds must be > 1.0 (a winning bet must pay back "
                f"more than the stake), got {self.decimal_odds}"
            )

    @property
    def implied_prob(self) -> float:
        """Raw (vig-inclusive) implied probability ``1 / decimal_odds``."""
        return 1.0 / self.decimal_odds


@dataclass(frozen=True, slots=True)
class TwoWayMarket:
    """A 2-way moneyline market (home vs away, no draws).

    NBA games settle to one of two outcomes -- there are no ties in
    the regulation-or-OT scheme that Kalshi uses. The 2-way assumption
    is structural here; 3-way (with draws) is a separate problem that
    we don't need for v1.
    """

    home: MoneylineQuote
    away: MoneylineQuote

    @property
    def booksum(self) -> float:
        """Sum of raw implied probabilities. ``> 1.0`` for a vigged book."""
        return self.home.implied_prob + self.away.implied_prob

    @property
    def overround(self) -> float:
        """``booksum - 1.0`` -- the book's gross take per unit volume."""
        return self.booksum - 1.0


@dataclass(frozen=True, slots=True)
class FairProbabilities:
    """Devig output: fair probabilities + the method that produced them."""

    home: float
    away: float
    method: DevigMethod

    def __post_init__(self) -> None:
        if not 0.0 < self.home < 1.0:
            raise ValueError(f"home fair prob must be in (0, 1), got {self.home}")
        if not 0.0 < self.away < 1.0:
            raise ValueError(f"away fair prob must be in (0, 1), got {self.away}")
        # Allow a small numerical-error window; both methods sum to 1.0
        # by construction but float roundoff exists.
        delta = abs(self.home + self.away - 1.0)
        if delta > 1e-6:
            raise ValueError(
                f"home + away must sum to 1.0 (within 1e-6), got "
                f"{self.home + self.away} (delta={delta})"
            )


def _validate_market(market: TwoWayMarket) -> None:
    """Reject markets whose booksum lies outside the trustworthy band.

    A booksum below 1.0 means the book is paying users to take both
    sides -- always a stale/erroneous quote. A booksum above 1.5 is
    50 %+ vig, never seen on a real NBA market.
    """
    bs = market.booksum
    if bs < MIN_BOOKSUM:
        raise ValueError(
            f"booksum {bs:.4f} below minimum {MIN_BOOKSUM} -- likely a "
            f"stale or erroneous quote (no real book gives away money)"
        )
    if bs > MAX_BOOKSUM:
        raise ValueError(
            f"booksum {bs:.4f} above maximum {MAX_BOOKSUM} -- likely a "
            f"stale or extreme-vig quote, refuse to devig"
        )


def devig_proportional(market: TwoWayMarket) -> FairProbabilities:
    """Proportional devig: ``fair_p_i = raw_p_i / booksum``.

    Default method. At Pinnacle's typical 2 % NBA-moneyline vig, this
    is within ~50 bp of the power method on liquid games and within
    ~1 % even on edge cases. Cheap, robust, and well-defined for any
    valid 2-way booksum.
    """
    _validate_market(market)
    bs = market.booksum
    return FairProbabilities(
        home=market.home.implied_prob / bs,
        away=market.away.implied_prob / bs,
        method="proportional",
    )


def devig_power(market: TwoWayMarket) -> FairProbabilities:
    """Power-method devig: solve for ``k`` s.t. ``sum_i raw_p_i^k = 1``.

    Bisects ``k`` over the bracket ``[0.5, 3.0]``. ``k = 1`` recovers
    the no-vig case (booksum already 1); ``k > 1`` shifts mass toward
    the favorite relative to proportional, because the convex
    transformation ``x^k`` shrinks small raw probs (longshots) by a
    larger relative factor than it shrinks large raw probs (favorites).
    Per Cain/Law/Peel (2003), this is the direction the favorite-
    longshot bias correction takes for traditional bookmakers; books
    overprice longshots to absorb bettor demand, so the *true* fair
    longshot prob is smaller than proportional devigging suggests.

    At typical NBA vig levels ``k`` lands in [1.02, 1.25] -- the
    bracket easily contains it.
    """
    _validate_market(market)

    p_home = market.home.implied_prob
    p_away = market.away.implied_prob

    def f(k: float) -> float:
        """``sum_i raw_p_i^k - 1`` -- root at the calibrated k."""
        return float(p_home**k + p_away**k - 1.0)

    # Bracket: at k=1, f = booksum - 1 > 0 (vigged book). At k=large,
    # both terms shrink toward 0, so f -> -1 < 0. Bisect.
    lo, hi = 0.5, 3.0
    f_lo, f_hi = f(lo), f(hi)
    if f_lo * f_hi > 0:
        # Bracket failed -- fall back to proportional + flag in method.
        # In practice this should never trigger for booksums in
        # [MIN_BOOKSUM, MAX_BOOKSUM]; the fallback is defense in depth.
        return devig_proportional(market)

    for _ in range(POWER_MAX_ITER):
        mid = 0.5 * (lo + hi)
        f_mid = f(mid)
        if abs(f_mid) < POWER_TOL:
            break
        if f_lo * f_mid < 0:
            hi = mid
            f_hi = f_mid
        else:
            lo = mid
            f_lo = f_mid
    k = 0.5 * (lo + hi)

    fair_home = p_home**k
    fair_away = p_away**k
    # Renormalize to absorb the residual rounding error in the last
    # bisection step. The pre-renorm sum is within POWER_TOL of 1.0
    # but the FairProbabilities constructor wants 1e-6.
    total = fair_home + fair_away
    return FairProbabilities(
        home=fair_home / total,
        away=fair_away / total,
        method="power",
    )


def devig(market: TwoWayMarket, *, method: DevigMethod = "proportional") -> FairProbabilities:
    """Dispatch helper: route ``market`` to the requested devig method.

    Default is ``"proportional"`` -- correct choice for Pinnacle (low
    vig, near-proportional pricing). Use ``"power"`` for higher-vig
    books where the favorite-longshot correction matters.
    """
    if method == "proportional":
        return devig_proportional(market)
    if method == "power":
        return devig_power(market)
    raise ValueError(f"unknown devig method {method!r}")


# --------------------------- N-way outright markets (golf) ---------------------------
#
# Golf tournament-winner ("outright") markets are an entirely different
# shape from the 2-way moneyline: 60-120 players quoted at once, with a
# correspondingly large overround. Observed live 2026-05-24 on the
# Odds API US Open feed: booksum 1.375 (lowvig, 94 players) up to 1.75
# (DraftKings/everygame) -- i.e. 37-75 % vig, vs ~2 % on an NBA 2-way.
# Pinnacle does NOT price golf via the Odds API, so the fair-value anchor
# is the lowest-overround *available* book; see the design doc.
#
# Because the overround is so large, the choice of normalization matters
# materially. The multiplicative method systematically over-weights the
# long tail of no-hope players; the power method corrects the favorite-
# longshot bias and stays bounded, so it is the default here.

# Outright books carry far more overround than 2-way moneylines; widen
# the acceptance band. A booksum < 0.99 is still a data error (a book
# paying out > 100 %); > 3.0 is a broken/lay-contaminated quote.
MIN_OUTRIGHT_BOOKSUM: Final = 0.99
MAX_OUTRIGHT_BOOKSUM: Final = 3.0

# Power-solver bracket for the N-way root. The calibrated exponent for a
# golf field lands comfortably inside [0.05, 5.0]; at k=0.05 the powered
# sum is ~N (huge, positive f), at k=5 it collapses toward 0 (f -> -1),
# so the bracket is guaranteed to straddle the root for any valid booksum.
OUTRIGHT_POWER_LO: Final = 0.05
OUTRIGHT_POWER_HI: Final = 5.0


@dataclass(frozen=True, slots=True)
class OutrightMarket:
    """An N-way outright (tournament-winner) market in decimal odds.

    Maps each outcome name (a player) to its decimal odds. The field is
    large and the overround correspondingly large; this is the golf
    analogue of :class:`TwoWayMarket`. Outcomes priced at or below 1.0
    (a winning bet that returns no profit) are rejected at construction.
    """

    quotes: Mapping[str, float]

    def __post_init__(self) -> None:
        if len(self.quotes) < 2:
            raise ValueError(f"outright market needs >= 2 outcomes, got {len(self.quotes)}")
        for name, odds in self.quotes.items():
            if odds <= 1.0:
                raise ValueError(
                    f"decimal_odds for {name!r} must be > 1.0 (a winning bet must "
                    f"pay back more than the stake), got {odds}"
                )

    @property
    def booksum(self) -> float:
        """Sum of raw implied probabilities across the whole field."""
        return sum(1.0 / o for o in self.quotes.values())

    @property
    def overround(self) -> float:
        """``booksum - 1.0`` -- the book's gross take across the field."""
        return self.booksum - 1.0


@dataclass(frozen=True, slots=True)
class OutrightFairProbabilities:
    """Devig output for an N-way market: fair prob per outcome + provenance."""

    probs: Mapping[str, float]
    method: DevigMethod
    raw_booksum: float

    def __post_init__(self) -> None:
        for name, p in self.probs.items():
            if not 0.0 < p < 1.0:
                raise ValueError(f"fair prob for {name!r} must be in (0, 1), got {p}")
        total = sum(self.probs.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"fair probs must sum to 1.0 (within 1e-6), got {total} (delta={abs(total - 1.0)})"
            )


def _validate_outright(market: OutrightMarket) -> None:
    """Reject outright books whose booksum lies outside the trustworthy band."""
    bs = market.booksum
    if bs < MIN_OUTRIGHT_BOOKSUM:
        raise ValueError(
            f"outright booksum {bs:.4f} below minimum {MIN_OUTRIGHT_BOOKSUM} -- "
            f"likely a stale or erroneous quote (no real book gives away money)"
        )
    if bs > MAX_OUTRIGHT_BOOKSUM:
        raise ValueError(
            f"outright booksum {bs:.4f} above maximum {MAX_OUTRIGHT_BOOKSUM} -- "
            f"likely a broken or lay-contaminated quote, refuse to devig"
        )


def devig_outright_multiplicative(market: OutrightMarket) -> OutrightFairProbabilities:
    """Multiplicative (proportional) N-way devig: ``fair_i = raw_i / booksum``.

    Simplest normalization; ignores favorite-longshot bias and so
    systematically over-weights the long tail of no-hope players on a
    big field. Provided for comparison; :func:`devig_outright_power` is
    the production default for golf.
    """
    _validate_outright(market)
    bs = market.booksum
    return OutrightFairProbabilities(
        probs={name: (1.0 / o) / bs for name, o in market.quotes.items()},
        method="proportional",
        raw_booksum=bs,
    )


def devig_outright_power(market: OutrightMarket) -> OutrightFairProbabilities:
    """Power-method N-way devig: solve ``k`` s.t. ``sum_i raw_i^k = 1``.

    The convex transform ``x^k`` (k > 1) shrinks small raw probs
    (longshots) by a larger relative factor than large ones (the
    favorite), correcting the favorite-longshot bias that is severe on
    big golf fields. Bisects ``k`` over ``[0.05, 5.0]`` and renormalizes
    to absorb residual bisection roundoff. Falls back to multiplicative
    if the bracket somehow fails to straddle the root (defense in depth).
    """
    _validate_outright(market)
    raw = {name: 1.0 / o for name, o in market.quotes.items()}
    vals = list(raw.values())

    def f(k: float) -> float:
        return float(sum(p**k for p in vals) - 1.0)

    lo, hi = OUTRIGHT_POWER_LO, OUTRIGHT_POWER_HI
    f_lo, f_hi = f(lo), f(hi)
    if f_lo * f_hi > 0:
        return devig_outright_multiplicative(market)

    for _ in range(POWER_MAX_ITER):
        mid = 0.5 * (lo + hi)
        f_mid = f(mid)
        if abs(f_mid) < POWER_TOL:
            break
        if f_lo * f_mid < 0:
            hi = mid
            f_hi = f_mid
        else:
            lo = mid
            f_lo = f_mid
    k = 0.5 * (lo + hi)

    powered = {name: p**k for name, p in raw.items()}
    total = sum(powered.values())
    return OutrightFairProbabilities(
        probs={name: v / total for name, v in powered.items()},
        method="power",
        raw_booksum=market.booksum,
    )


def devig_outright(
    market: OutrightMarket, *, method: DevigMethod = "power"
) -> OutrightFairProbabilities:
    """Dispatch helper for N-way outright devig. Default ``"power"``.

    Power is the right default for golf: large fields + large overround
    make the favorite-longshot correction worth applying. Use
    ``"proportional"`` only for comparison/diagnostics.
    """
    if method == "power":
        return devig_outright_power(market)
    if method == "proportional":
        return devig_outright_multiplicative(market)
    raise ValueError(f"unknown devig method {method!r}")
