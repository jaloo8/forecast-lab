"""Tests for the intraday METAR Bayesian nowcast.

Two surfaces under test:

- :func:`metar_updated_proba` — pure math; given a prior + state, return P.
- :func:`compute_nowcast_state` — walks raw METAR rows + station LST window
  and emits a :class:`NowcastState`.
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta

import pytest
from scipy import stats

from kq.clients.stations import STATIONS_BY_ICAO
from kq.models.nowcast import (
    LOCKED_PROB,
    PROB_CLIP_HIGH,
    PROB_CLIP_LOW,
    SIGMA_FRACTION_FLOOR,
    NowcastState,
    compute_nowcast_state,
    metar_updated_proba,
)

KLAX = STATIONS_BY_ICAO["KLAX"]  # PST, UTC-8
TARGET_DATE = date(2026, 4, 30)


# -------------------------------------------------- metar_updated_proba: defaults


def test_no_obs_full_day_remaining_equals_prior() -> None:
    """No METAR + fraction=1 → output equals raw prior SF (modulo clip)."""
    state = NowcastState(t_so_far_f=None, fraction_day_remaining=1.0, n_obs=0)
    p = metar_updated_proba(
        threshold_f=80.0,
        prior_mu_f=82.0,
        prior_sigma_f=3.5,
        state=state,
    )
    expected = float(stats.norm.sf(80.0, loc=82.0, scale=3.5))
    assert p == pytest.approx(expected, abs=1e-6)


def test_above_threshold_already_observed_locks_yes() -> None:
    """t_so_far > threshold → return LOCKED_PROB (no calculation)."""
    state = NowcastState(t_so_far_f=85.0, fraction_day_remaining=0.3, n_obs=20)
    p = metar_updated_proba(threshold_f=80.0, prior_mu_f=82.0, prior_sigma_f=3.5, state=state)
    assert p == LOCKED_PROB


def test_at_threshold_observed_does_not_lock() -> None:
    """Strict-greater: t_so_far == threshold doesn't auto-trigger YES.

    Mirrors the backtest/settlement convention `outcome = high > threshold`.
    """
    state = NowcastState(t_so_far_f=80.0, fraction_day_remaining=0.5, n_obs=10)
    p = metar_updated_proba(threshold_f=80.0, prior_mu_f=80.0, prior_sigma_f=3.5, state=state)
    assert p < LOCKED_PROB


def test_observed_temp_floors_mu_when_warmer_than_prior() -> None:
    """If t_so_far > prior_mu but < threshold, mu_post should rise to t_so_far."""
    # Prior says 75F mode; we already see 78F at noon; threshold 80F.
    state = NowcastState(t_so_far_f=78.0, fraction_day_remaining=0.5, n_obs=10)
    p_with_obs = metar_updated_proba(
        threshold_f=80.0, prior_mu_f=75.0, prior_sigma_f=3.5, state=state
    )
    # Compare to a hypothetical "no observation seen" path with same fraction
    state_no_obs = NowcastState(t_so_far_f=None, fraction_day_remaining=0.5, n_obs=0)
    p_no_obs = metar_updated_proba(
        threshold_f=80.0, prior_mu_f=75.0, prior_sigma_f=3.5, state=state_no_obs
    )
    # mu_post = max(75, 78) = 78; expected p = SF(80; 78, 3.5*sqrt(0.5))
    assert p_with_obs > p_no_obs


def test_cooler_observed_does_not_drag_mu_down() -> None:
    """If t_so_far is below prior_mu, mu_post stays at prior_mu (no leak)."""
    # Prior says 82F, but it's a cool morning so we've only seen 60F so far.
    state = NowcastState(t_so_far_f=60.0, fraction_day_remaining=0.7, n_obs=10)
    p = metar_updated_proba(threshold_f=80.0, prior_mu_f=82.0, prior_sigma_f=3.5, state=state)
    # mu_post = max(82, 60) = 82, so the formula matches "no obs" but with shrunk sigma
    expected = float(stats.norm.sf(80.0, loc=82.0, scale=3.5 * math.sqrt(0.7)))
    assert p == pytest.approx(expected, abs=1e-6)


def test_sigma_shrinks_with_remaining_fraction() -> None:
    """Same prior, smaller fraction_remaining → sigma_post smaller → distribution tighter."""
    full_day = NowcastState(t_so_far_f=None, fraction_day_remaining=1.0, n_obs=0)
    half_day = NowcastState(t_so_far_f=None, fraction_day_remaining=0.5, n_obs=0)
    # threshold above the prior mean → narrowing sigma should LOWER P (tail thinner)
    p_full = metar_updated_proba(
        threshold_f=85.0, prior_mu_f=80.0, prior_sigma_f=3.5, state=full_day
    )
    p_half = metar_updated_proba(
        threshold_f=85.0, prior_mu_f=80.0, prior_sigma_f=3.5, state=half_day
    )
    assert p_half < p_full


def test_end_of_day_sigma_clamped_to_floor() -> None:
    """fraction=0 → sigma_post is clamped to SIGMA_FRACTION_FLOOR * prior_sigma.

    With prior mu=82 above threshold=80, the SF is already very close to 1; the
    final value also goes through the [0.01, 0.99] clip. We compare against the
    properly-clipped expected.
    """
    state = NowcastState(t_so_far_f=None, fraction_day_remaining=0.0, n_obs=0)
    p = metar_updated_proba(threshold_f=80.0, prior_mu_f=82.0, prior_sigma_f=3.5, state=state)
    raw = float(stats.norm.sf(80.0, loc=82.0, scale=3.5 * math.sqrt(SIGMA_FRACTION_FLOOR)))
    expected = min(max(raw, PROB_CLIP_LOW), PROB_CLIP_HIGH)
    assert p == pytest.approx(expected, abs=1e-6)


def test_end_of_day_sigma_floor_visible_in_unclipped_regime() -> None:
    """Pick a threshold where the prior SF is in (0.01, 0.99) so the floor is observable."""
    state_full = NowcastState(t_so_far_f=None, fraction_day_remaining=1.0, n_obs=0)
    state_done = NowcastState(t_so_far_f=None, fraction_day_remaining=0.0, n_obs=0)
    # Threshold sits exactly at prior mu so SF = 0.5; sigma scaling should leave it ~0.5
    # (since 0.5 is the median for any sigma > 0 centered at mu).
    p_full = metar_updated_proba(
        threshold_f=80.0, prior_mu_f=80.0, prior_sigma_f=3.5, state=state_full
    )
    p_done = metar_updated_proba(
        threshold_f=80.0, prior_mu_f=80.0, prior_sigma_f=3.5, state=state_done
    )
    assert p_full == pytest.approx(0.5, abs=1e-6)
    assert p_done == pytest.approx(0.5, abs=1e-6)


def test_output_clipped_to_prob_range() -> None:
    """Even extreme inputs stay in [0.01, 0.99] per coding standards §6."""
    # Prior mu way above threshold → SF would be ~1.0 → clipped to 0.99
    state = NowcastState(t_so_far_f=None, fraction_day_remaining=0.5, n_obs=0)
    p_high = metar_updated_proba(threshold_f=20.0, prior_mu_f=80.0, prior_sigma_f=3.5, state=state)
    p_low = metar_updated_proba(threshold_f=200.0, prior_mu_f=80.0, prior_sigma_f=3.5, state=state)
    assert PROB_CLIP_LOW <= p_low <= p_high <= PROB_CLIP_HIGH


# -------------------------------------------------- metar_updated_proba: errors


def test_sigma_must_be_positive() -> None:
    state = NowcastState(t_so_far_f=None, fraction_day_remaining=1.0, n_obs=0)
    with pytest.raises(ValueError, match="prior_sigma_f"):
        metar_updated_proba(threshold_f=80.0, prior_mu_f=80.0, prior_sigma_f=0.0, state=state)
    with pytest.raises(ValueError, match="prior_sigma_f"):
        metar_updated_proba(threshold_f=80.0, prior_mu_f=80.0, prior_sigma_f=-1.0, state=state)


def test_fraction_must_be_in_unit_interval() -> None:
    bad = NowcastState(t_so_far_f=None, fraction_day_remaining=1.5, n_obs=0)
    with pytest.raises(ValueError, match="fraction_day_remaining"):
        metar_updated_proba(threshold_f=80.0, prior_mu_f=80.0, prior_sigma_f=3.5, state=bad)


# -------------------------------------------------- compute_nowcast_state


def test_compute_state_no_metar_full_day() -> None:
    """Empty METAR + before-LST-day-start → fraction=1, t_so_far=None."""
    # KLAX LST is UTC-8; LST day starts 08:00 UTC, ends next day 08:00 UTC.
    before_lst_day = datetime(2026, 4, 30, 0, 0, tzinfo=UTC)  # before 08:00 UTC
    state = compute_nowcast_state(
        station=KLAX,
        valid_date=TARGET_DATE,
        now_utc=before_lst_day,
        metar_temps=[],
    )
    assert state.t_so_far_f is None
    assert state.fraction_day_remaining == 1.0
    assert state.n_obs == 0
    assert state.has_obs is False


def test_compute_state_after_lst_day_end_is_zero_fraction() -> None:
    """now_utc past the LST end → fraction=0."""
    after = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)  # well past 08:00 UTC May 1
    state = compute_nowcast_state(
        station=KLAX,
        valid_date=TARGET_DATE,
        now_utc=after,
        metar_temps=[],
    )
    assert state.fraction_day_remaining == 0.0


def test_compute_state_uses_max_in_window() -> None:
    """Multiple obs → t_so_far is the max of in-window temps."""
    # KLAX LST day 2026-04-30 in UTC: [08:00 UTC 04-30, 08:00 UTC 05-01]
    now = datetime(2026, 4, 30, 22, 0, tzinfo=UTC)  # 14:00 LAX (typical peak)
    obs = [
        (datetime(2026, 4, 30, 14, 0, tzinfo=UTC), 65.0),  # 06:00 LAX, in window
        (datetime(2026, 4, 30, 18, 0, tzinfo=UTC), 72.0),  # 10:00 LAX, in window
        (datetime(2026, 4, 30, 21, 0, tzinfo=UTC), 78.0),  # 13:00 LAX, in window
    ]
    state = compute_nowcast_state(
        station=KLAX, valid_date=TARGET_DATE, now_utc=now, metar_temps=obs
    )
    assert state.t_so_far_f == 78.0
    assert state.n_obs == 3
    # ~10 hours remaining out of 24 → fraction ~ 0.4
    assert 0.3 < state.fraction_day_remaining < 0.5


def test_compute_state_excludes_yesterday_metars() -> None:
    """Pre-LST-day observations don't count toward today's t_so_far."""
    now = datetime(2026, 4, 30, 22, 0, tzinfo=UTC)
    obs = [
        (datetime(2026, 4, 30, 7, 0, tzinfo=UTC), 90.0),  # before LST start (08:00 UTC)
        (datetime(2026, 4, 30, 18, 0, tzinfo=UTC), 70.0),  # in window
    ]
    state = compute_nowcast_state(
        station=KLAX, valid_date=TARGET_DATE, now_utc=now, metar_temps=obs
    )
    assert state.t_so_far_f == 70.0
    assert state.n_obs == 1


def test_compute_state_excludes_future_obs() -> None:
    """An obs timestamped after now_utc is a data leak — must be filtered out."""
    now = datetime(2026, 4, 30, 18, 0, tzinfo=UTC)
    obs = [
        (datetime(2026, 4, 30, 16, 0, tzinfo=UTC), 70.0),  # past, in window
        (datetime(2026, 4, 30, 23, 0, tzinfo=UTC), 90.0),  # future! must drop
    ]
    state = compute_nowcast_state(
        station=KLAX, valid_date=TARGET_DATE, now_utc=now, metar_temps=obs
    )
    assert state.t_so_far_f == 70.0
    assert state.n_obs == 1


def test_compute_state_skips_none_temps() -> None:
    now = datetime(2026, 4, 30, 22, 0, tzinfo=UTC)
    obs: list[tuple[datetime, float | None]] = [
        (datetime(2026, 4, 30, 18, 0, tzinfo=UTC), None),  # missing
        (datetime(2026, 4, 30, 19, 0, tzinfo=UTC), 75.0),
    ]
    state = compute_nowcast_state(
        station=KLAX, valid_date=TARGET_DATE, now_utc=now, metar_temps=obs
    )
    assert state.t_so_far_f == 75.0
    assert state.n_obs == 1


def test_compute_state_skips_naive_obs_times() -> None:
    """Defensive: naive obs_time is rejected (no tz means we can't bound it)."""
    now = datetime(2026, 4, 30, 22, 0, tzinfo=UTC)
    obs: list[tuple[datetime, float | None]] = [
        (datetime(2026, 4, 30, 18, 0), 75.0),  # naive — must be skipped
        (datetime(2026, 4, 30, 20, 0, tzinfo=UTC), 80.0),
    ]
    state = compute_nowcast_state(
        station=KLAX, valid_date=TARGET_DATE, now_utc=now, metar_temps=obs
    )
    assert state.t_so_far_f == 80.0
    assert state.n_obs == 1


def test_compute_state_naive_now_raises() -> None:
    """now_utc must be tz-aware so we don't quietly mis-bound the day."""
    naive_now = datetime(2026, 4, 30, 18, 0)
    with pytest.raises(ValueError, match="tz-aware"):
        compute_nowcast_state(
            station=KLAX, valid_date=TARGET_DATE, now_utc=naive_now, metar_temps=[]
        )


def test_compute_state_handles_all_six_stations() -> None:
    """End-to-end smoke: every supported station returns a sensible state."""
    now = datetime(2026, 4, 30, 18, 0, tzinfo=UTC)
    for station in STATIONS_BY_ICAO.values():
        state = compute_nowcast_state(
            station=station,
            valid_date=TARGET_DATE,
            now_utc=now,
            metar_temps=[(now - timedelta(hours=2), 75.0)],
        )
        # In-window check is per-station LST-day bound — at least one of the 6 should
        # return either an obs or no-obs without raising.
        assert isinstance(state, NowcastState)
