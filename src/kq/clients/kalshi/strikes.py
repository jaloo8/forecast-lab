"""Strike-aware pricing + settlement for Kalshi weather contracts.

The authoritative contract semantics live in the API's ``strike_type`` /
``floor_strike`` / ``cap_strike`` fields (see ``_types.Market``), never in
ticker text. Verified against prod 2026-06-11 (recorded fixture
``tests/fixtures/kalshi_prod_markets_weather.json``):

* ``greater`` (``-T81``): floor=81, YES iff settle value > 81 — ">81°"
* ``less``    (``-T74``): cap=74,   YES iff settle value < 74 — "<74°"
* ``between`` (``-B74.5``): floor=74, cap=75, YES iff 74 <= value <= 75 — "74-75°"

Settlement values are whole °F (NWS Climatological Report Daily), so a
continuous predictive distribution must be evaluated at **half-integer
boundaries**: the event ladder ``<74 | 74-75 | 76-77 | 78-79 | 80-81 | >81``
partitions the reals exactly at ``73.5 / 75.5 / 77.5 / 79.5 / 81.5`` and the
priced probabilities sum to 1 across the book. Pricing ``greater`` at
``P(T > floor)`` instead of ``P(T > floor + 0.5)`` silently overprices YES
(it counts the (floor, floor+0.5] mass that settles NO); pricing ``between``
at ``P(floor <= T <= cap)`` without the half-degree widening halves the true
probability of a 2-degree bracket. Both were latent in the pre-PR-B
threshold-exceedance path.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from kq.clients.kalshi._ticker_parser import WeatherMarketRef
from kq.clients.kalshi._types import Market

StrikeKind = Literal["greater", "less", "between"]

# Models must emit calibrated probabilities in [0.01, 0.99] (CLAUDE.md §6).
PROB_CLIP_LO = 0.01
PROB_CLIP_HI = 0.99

# Settlement is in whole °F; the half-degree offset maps integer contract
# semantics onto a continuous predictive distribution (module docstring).
# This is the WEATHER default: the offset is half the settlement grid's
# resolution, so other verticals riding the same Strike machinery pass
# their own ``half_width`` (index brackets settle on 2-decimal prints with
# API-encoded .9999 caps — see kq.clients.kalshi._ticker_parser_index.
# INDEX_STRIKE_HALF_WIDTH).
_HALF = 0.5


@dataclass(frozen=True, slots=True)
class Strike:
    """Resolution semantics of one weather binary, from API strike fields."""

    kind: StrikeKind
    floor: float | None
    cap: float | None

    def __post_init__(self) -> None:
        if self.kind not in ("greater", "less", "between"):
            raise ValueError(f"unknown strike kind {self.kind!r}")
        if self.kind == "greater" and self.floor is None:
            raise ValueError("greater strike requires floor")
        if self.kind == "less" and self.cap is None:
            raise ValueError("less strike requires cap")
        if self.kind == "between" and (self.floor is None or self.cap is None):
            raise ValueError("between strike requires floor and cap")
        if (
            self.kind == "between"
            and self.floor is not None
            and self.cap is not None
            and self.floor > self.cap
        ):
            raise ValueError(f"between strike floor {self.floor} > cap {self.cap}")


def strike_from_market(
    market: Market,
    ref: WeatherMarketRef | None = None,
    *,
    allow_legacy_ticker_semantics: bool = False,
) -> Strike | None:
    """Build the authoritative :class:`Strike` for a weather market.

    API strike fields win. When they're present but disagree with the ticker
    text (``ref``), return ``None`` — refuse to guess, same posture as the
    PR-A interim guard.

    When the API fields are absent entirely, the market is refused by
    default. The historical interpretation of a ``-T<int>`` ticker as a
    *greater* contract at the ticker threshold exists only for the demo
    environment (whose payloads never carried strike fields) and must be
    opted into via ``allow_legacy_ticker_semantics`` at the flow boundary
    (``KALSHI_ENV == "demo"``). On prod, payload drift that drops
    ``strike_type`` would otherwise silently re-enable the inverted-*less*
    bug PR-B fixed (low-tail ``-T<n>`` markets are *less*, not greater);
    refusing keeps the failure loud — ``kq doctor`` counts ineligible
    markets per series. ``-B`` tickers without API fields are never
    guessable in either environment.
    """
    if market.strike_type is not None:
        strike = _strike_from_api_fields(market)
        if strike is None:
            return None
        if ref is not None and not _ticker_agrees(strike, ref):
            return None
        return strike
    # No strike fields on the wire: demo-only legacy fallback, opt-in.
    if allow_legacy_ticker_semantics and ref is not None and ref.kind == "T":
        return Strike(kind="greater", floor=float(ref.threshold_f), cap=None)
    return None


def _strike_from_api_fields(market: Market) -> Strike | None:
    if market.strike_type == "greater" and market.floor_strike is not None:
        return Strike(kind="greater", floor=float(market.floor_strike), cap=None)
    if market.strike_type == "less" and market.cap_strike is not None:
        return Strike(kind="less", floor=None, cap=float(market.cap_strike))
    if (
        market.strike_type == "between"
        and market.floor_strike is not None
        and market.cap_strike is not None
        and market.floor_strike <= market.cap_strike
    ):
        return Strike(
            kind="between", floor=float(market.floor_strike), cap=float(market.cap_strike)
        )
    return None


def _ticker_agrees(strike: Strike, ref: WeatherMarketRef) -> bool:
    """Cross-check API strike fields against the number in the ticker text.

    ``-T81`` greater → floor == 81; ``-T74`` less → cap == 74;
    ``-B74.5`` between → midpoint of (floor, cap) == 74.5.
    """
    if strike.kind == "greater":
        return ref.kind == "T" and strike.floor == float(ref.threshold_f)
    if strike.kind == "less":
        return ref.kind == "T" and strike.cap == float(ref.threshold_f)
    if strike.floor is None or strike.cap is None:  # pragma: no cover — guarded upstream
        return False
    return ref.kind == "B" and (strike.floor + strike.cap) / 2.0 == float(ref.threshold_f)


def yes_prob(
    strike: Strike, prob_gt: Callable[[float], float], *, half_width: float = _HALF
) -> float:
    """P(contract settles YES) from an exceedance function ``prob_gt(x) = P(T > x)``.

    Half-integer boundaries (module docstring). The result is clipped to
    ``[0.01, 0.99]`` per the project probability convention. For ``between``
    the two exceedance calls may each be clipped by the underlying model;
    the residual distortion is bounded by the clip width (≤ 2pp) and only
    affects far-tail brackets.

    ``half_width`` is half the settlement grid's resolution: 0.5 (default)
    for whole-°F weather settlement, ``INDEX_STRIKE_HALF_WIDTH`` for index
    brackets (2-decimal prints, API-encoded .9999 caps). Pricing and
    settlement (:func:`yes_outcome`) must use the SAME value.
    """
    if strike.kind == "greater":
        p = prob_gt(_require(strike.floor) + half_width)
    elif strike.kind == "less":
        p = 1.0 - prob_gt(_require(strike.cap) - half_width)
    else:
        p = prob_gt(_require(strike.floor) - half_width) - prob_gt(
            _require(strike.cap) + half_width
        )
    return min(max(p, PROB_CLIP_LO), PROB_CLIP_HI)


def yes_outcome(strike: Strike, observed_high_f: float, *, half_width: float = _HALF) -> bool:
    """Did the contract settle YES given the observed settlement value?

    NWS reports whole °F, so with real weather data the half-degree
    boundaries never bind; they're kept identical to :func:`yes_prob` so
    pricing and settlement can never disagree about which side of a bracket
    a value falls on (fractional observed values round half-up, matching
    NWS convention). Index consumers pass ``half_width=
    INDEX_STRIKE_HALF_WIDTH`` so 2-decimal prints on a round boundary
    (e.g. 7825.00 against a 7824.9999 cap) land in the correct bracket.
    """
    if strike.kind == "greater":
        return observed_high_f >= _require(strike.floor) + half_width
    if strike.kind == "less":
        return observed_high_f < _require(strike.cap) - half_width
    return (
        _require(strike.floor) - half_width <= observed_high_f < _require(strike.cap) + half_width
    )


def _require(value: float | None) -> float:
    """Type-narrow a strike bound that ``Strike.__post_init__`` guarantees non-None."""
    if value is None:  # pragma: no cover — unreachable past __post_init__
        raise ValueError("strike bound unexpectedly None")
    return value
