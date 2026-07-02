"""Intraday METAR-conditioned update of the daily-high prior.

Per CLAUDE.md §5 Phase 2 and Pass 1 §1b, the largest remaining edge source
on weather markets is updating our morning forecast as the day progresses.
Once it's 2pm and we've already observed 71F, the daily high distribution
shifts: it's at least 71F, and the residual variance shrinks because most
of the day's heating has already happened.

This module is intentionally simple-but-honest:

    P(daily_high > threshold | METAR_today, prior) =
        1.0,                                    if t_so_far > threshold
        SF(threshold; mu_post, sigma_post),     otherwise

    sigma_post = prior_sigma * sqrt(fraction_day_remaining)
    mu_post    = max(prior_mu, t_so_far)

Brownian-style sigma scaling overstates morning uncertainty resolution and
underestimates evening (the diurnal cycle is non-linear), but it's a clean
v1 baseline that gracefully degrades:

- ``t_so_far is None`` (no in-window METAR yet — early morning, tomorrow's
  market, or a station outage): output equals the unmodified prior. The
  clock alone carries no information about the daily max, so sigma is NOT
  shrunk without observations (2026-07-01 audit fix).
- ``fraction_day_remaining = 0`` with obs (day finished): sigma collapses
  to the numeric floor; if t_so_far <= threshold the YES probability
  bottoms out.

A future PR can replace the Brownian shrink with a per-station diurnal
profile fit from historical METARs.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Final

from scipy import stats

from kq.clients.stations import Station
from kq.utils.kalshi_dates import settlement_day_bounds

PROB_CLIP_LOW: Final = 0.01
PROB_CLIP_HIGH: Final = 0.99
SIGMA_FRACTION_FLOOR: Final = 0.05  # don't let posterior sigma go below 5% of prior
LOCKED_PROB: Final = PROB_CLIP_HIGH  # already-exceeded threshold → near-certainty
SECONDS_PER_DAY: Final = 86_400.0


@dataclass(frozen=True, slots=True)
class NowcastState:
    """Snapshot of today's intraday observations for one station/day.

    Built by :func:`compute_nowcast_state` from raw METAR rows; consumed by
    :func:`metar_updated_proba` to update a calibrated prior.
    """

    t_so_far_f: float | None  # max observed temp during the LST settlement day so far
    fraction_day_remaining: float  # in [0, 1]: 1=day not started, 0=day finished
    n_obs: int  # how many in-window obs were considered (debugging / logging)

    @property
    def has_obs(self) -> bool:
        return self.n_obs > 0


def metar_updated_proba(
    *,
    threshold_f: float,
    prior_mu_f: float,
    prior_sigma_f: float,
    state: NowcastState,
) -> float:
    """Updated ``P(daily_high > threshold)`` clipped to ``[0.01, 0.99]``.

    Degenerates to the unmodified prior when ``state`` carries no
    information (no observations), so callers can route every station
    through this function unconditionally.

    2026-07-01 audit (Tier 2): with ZERO observations the elapsed-day
    fraction conveys nothing about the daily max — the old code still
    shrank sigma by ``sqrt(fraction_day_remaining)``, manufacturing
    confidence out of a clock. With no obs we now return the prior
    EXACTLY, honoring the documented contract; the time-based shrink
    only applies once at least one in-window METAR exists.
    """
    if prior_sigma_f <= 0:
        raise ValueError(f"prior_sigma_f must be > 0, got {prior_sigma_f}")
    if not 0.0 <= state.fraction_day_remaining <= 1.0:
        raise ValueError(
            f"fraction_day_remaining must be in [0, 1], got {state.fraction_day_remaining}"
        )

    if state.t_so_far_f is None:
        # No intraday information — the prior is all we honestly have.
        p = float(stats.norm.sf(threshold_f, loc=prior_mu_f, scale=prior_sigma_f))
        return min(max(p, PROB_CLIP_LOW), PROB_CLIP_HIGH)

    if state.t_so_far_f > threshold_f:
        return LOCKED_PROB

    fraction = max(state.fraction_day_remaining, SIGMA_FRACTION_FLOOR)
    sigma_post = prior_sigma_f * math.sqrt(fraction)
    mu_post = max(prior_mu_f, state.t_so_far_f)
    p = float(stats.norm.sf(threshold_f, loc=mu_post, scale=sigma_post))
    return min(max(p, PROB_CLIP_LOW), PROB_CLIP_HIGH)


def compute_nowcast_state(
    *,
    station: Station,
    valid_date: date,
    now_utc: datetime,
    metar_temps: Sequence[tuple[datetime, float | None]],
) -> NowcastState:
    """Build a :class:`NowcastState` from raw METAR rows.

    ``metar_temps`` is an iterable of ``(obs_time_utc, temp_f)`` pairs (any
    None temps are filtered out). Only observations inside the station's
    LST settlement window for ``valid_date`` AND no later than ``now_utc``
    are considered — never use a future obs to predict, that's a leak.
    """
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be tz-aware (use datetime.now(tz=UTC))")

    start_utc, end_utc = settlement_day_bounds(station, valid_date)
    in_window: list[float] = []
    for ts, temp in metar_temps:
        if temp is None:
            continue
        if ts.tzinfo is None:
            continue  # defensive — naive timestamps aren't trusted
        if ts < start_utc or ts >= end_utc:
            continue
        if ts > now_utc:
            continue  # future obs would be a leak
        in_window.append(float(temp))

    t_so_far = max(in_window) if in_window else None

    if now_utc >= end_utc:
        fraction = 0.0
    elif now_utc <= start_utc:
        fraction = 1.0
    else:
        fraction = (end_utc - now_utc).total_seconds() / SECONDS_PER_DAY
        fraction = max(0.0, min(1.0, fraction))

    return NowcastState(
        t_so_far_f=t_so_far,
        fraction_day_remaining=fraction,
        n_obs=len(in_window),
    )
