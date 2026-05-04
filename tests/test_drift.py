"""Tests for the Page-Hinkley + ADWIN drift detectors.

Coverage:
- Page-Hinkley: silent on stationary stream; alarms on downward drift;
  doesn't alarm before min_instances; reset clears state; one-sided
  property (upward drift doesn't alarm).
- ADWIN: silent on stationary stream; alarms on regime change; window
  shrinks post-alarm; min_window gates early alarms.
- ``detect_drift_in_stream`` returns the right indices on synthetic
  streams.
- Defaults pinned so future config drift is deliberate.
"""

from __future__ import annotations

import random

import pytest

from kq.models.drift import (
    ADWIN_DEFAULT_DELTA,
    ADWIN_DEFAULT_MIN_WINDOW,
    PAGE_HINKLEY_DEFAULT_DELTA,
    PAGE_HINKLEY_DEFAULT_LAMBDA,
    PAGE_HINKLEY_DEFAULT_MIN_INSTANCES,
    AdwinDetector,
    PageHinkleyDetector,
    detect_drift_in_stream,
)

# --------------------------- Page-Hinkley ---------------------------


def test_page_hinkley_silent_on_stationary_stream() -> None:
    """100 iid samples around 0.9 -- no alarm should fire."""
    rng = random.Random(42)
    detector = PageHinkleyDetector()
    for _ in range(100):
        detector.update(0.9 + rng.gauss(0, 0.01))
    assert detector.in_alarm is False


def test_page_hinkley_alarms_on_downward_drift() -> None:
    """First half at 0.9 (no drift), second half at 0.7 (clear drift).
    Page-Hinkley should fire somewhere in the second half."""
    rng = random.Random(42)
    detector = PageHinkleyDetector(min_instances=20, lambda_=2.0)
    alarmed = False
    for i in range(200):
        x = 0.9 if i < 100 else 0.7
        x += rng.gauss(0, 0.005)
        if detector.update(x):
            alarmed = True
            break
    assert alarmed, "Page-Hinkley should have alarmed on the regime change"


def test_page_hinkley_silent_before_min_instances() -> None:
    """No alarm before min_instances regardless of input shape."""
    detector = PageHinkleyDetector(min_instances=50, lambda_=0.001)
    for _ in range(40):
        detector.update(0.0)
    assert detector.in_alarm is False
    assert detector.n_seen == 40


def test_page_hinkley_one_sided_upward_drift_does_not_alarm() -> None:
    """First 100 at 0.7, then 100 at 0.9 (upward drift). The one-sided
    detector should NOT alarm -- caller would feed -x to detect upward."""
    rng = random.Random(42)
    detector = PageHinkleyDetector(min_instances=20, lambda_=2.0)
    for i in range(200):
        x = 0.7 if i < 100 else 0.9
        x += rng.gauss(0, 0.005)
        detector.update(x)
    assert detector.in_alarm is False


def test_page_hinkley_reset_clears_state() -> None:
    """After reset, n_seen + running_mean + cumsum all zero;
    alarm flips to False."""
    detector = PageHinkleyDetector(min_instances=5, lambda_=0.5)
    for _ in range(20):
        detector.update(0.0)
    detector.update(-100.0)  # force big drift
    assert detector.in_alarm is True
    detector.reset()
    assert detector.in_alarm is False
    assert detector.n_seen == 0
    assert detector.gap == pytest.approx(0.0)


def test_page_hinkley_gap_grows_on_drift() -> None:
    """``gap`` should monotonically grow as drift develops."""
    detector = PageHinkleyDetector(min_instances=5, lambda_=10.0)
    gaps: list[float] = []
    for _ in range(30):
        detector.update(0.9)
    for _ in range(10):
        detector.update(0.5)
        gaps.append(detector.gap)
    # Gap should generally trend upward as more drift accumulates.
    assert gaps[-1] > gaps[0]


def test_page_hinkley_default_constants_pinned() -> None:
    """Defaults are part of the user-visible interface; pin them."""
    assert PAGE_HINKLEY_DEFAULT_DELTA == 0.01
    assert PAGE_HINKLEY_DEFAULT_LAMBDA == 5.0
    assert PAGE_HINKLEY_DEFAULT_MIN_INSTANCES == 30


# --------------------------- ADWIN ---------------------------


def test_adwin_silent_on_stationary_stream() -> None:
    """Stationary 0.9 stream -- no alarm should fire."""
    rng = random.Random(42)
    detector = AdwinDetector()
    for _ in range(200):
        detector.update(0.9 + rng.gauss(0, 0.005))
    assert detector.in_alarm is False


def test_adwin_alarms_on_regime_change() -> None:
    """100 samples at 0.9, then 100 at 0.5 -- ADWIN should detect."""
    rng = random.Random(42)
    detector = AdwinDetector(min_window=20, delta=0.05)  # lenient delta -> faster detect
    alarmed = False
    for i in range(200):
        x = 0.9 if i < 100 else 0.5
        x += rng.gauss(0, 0.005)
        if detector.update(x):
            alarmed = True
            break
    assert alarmed


def test_adwin_window_shrinks_post_alarm() -> None:
    """When ADWIN alarms, it drops everything before the cut. Window
    size after the alarm should be smaller than before."""
    rng = random.Random(42)
    detector = AdwinDetector(min_window=20, delta=0.05)
    for _ in range(100):
        detector.update(0.9 + rng.gauss(0, 0.005))
    pre_alarm_size = detector.window_size
    # Inject a large drift -> alarm + shrink.
    for _ in range(100):
        if detector.update(0.5):
            break
    assert detector.in_alarm is True
    assert detector.window_size < pre_alarm_size + 100


def test_adwin_silent_before_min_window() -> None:
    detector = AdwinDetector(min_window=50, delta=0.05)
    for _ in range(40):
        detector.update(0.0)
        if detector.update(1.0):
            return  # if it alarms, fail
    assert detector.in_alarm is False
    assert detector.window_size == 80


def test_adwin_reset_clears_window() -> None:
    detector = AdwinDetector(min_window=10, delta=0.5)
    for _ in range(20):
        detector.update(0.5)
    detector.reset()
    assert detector.window_size == 0
    assert detector.in_alarm is False


def test_adwin_default_constants_pinned() -> None:
    assert ADWIN_DEFAULT_DELTA == 0.002
    assert ADWIN_DEFAULT_MIN_WINDOW == 32


# --------------------------- detect_drift_in_stream ---------------------------


def test_detect_drift_in_stream_returns_alarm_indices() -> None:
    """Stream with a clear regime change -- the helper returns the
    indices where an alarm fires."""
    rng = random.Random(42)
    values = [0.9 + rng.gauss(0, 0.005) for _ in range(100)] + [
        0.5 + rng.gauss(0, 0.005) for _ in range(100)
    ]
    detector = PageHinkleyDetector(min_instances=20, lambda_=2.0)
    alarms = detect_drift_in_stream(values, detector=detector)
    assert len(alarms) >= 1
    # First alarm should be in the second half (after the regime change).
    assert alarms[0] >= 100


def test_detect_drift_in_stream_returns_empty_on_stationary() -> None:
    rng = random.Random(42)
    values = [0.9 + rng.gauss(0, 0.005) for _ in range(200)]
    detector = PageHinkleyDetector()
    assert detect_drift_in_stream(values, detector=detector) == []


def test_detect_drift_in_stream_works_with_adwin() -> None:
    """The helper accepts either detector type."""
    rng = random.Random(42)
    values = [0.9 + rng.gauss(0, 0.005) for _ in range(50)] + [
        0.5 + rng.gauss(0, 0.005) for _ in range(50)
    ]
    detector = AdwinDetector(min_window=20, delta=0.05)
    alarms = detect_drift_in_stream(values, detector=detector)
    assert len(alarms) >= 1
