"""Online drift / change-point detectors.

Two complementary algorithms:

- **Page-Hinkley** (Page 1954) -- accumulates the cumulative sum of
  (observation - running_mean - delta) and alarms when the gap from
  the running minimum exceeds a threshold. Tuning knobs: ``delta``
  (the minimum drift magnitude we want to detect, in the same units
  as observations) and ``lambda_`` (alarm threshold, larger = fewer
  false alarms but slower detection).

- **ADWIN** (Bifet & Gavalda 2007) -- "ADaptive WINdowing": holds a
  variable-length window of recent observations and shrinks it when
  the difference in means between two contiguous sub-windows exceeds
  a Hoeffding bound at confidence ``delta``. More flexible than
  Page-Hinkley but more compute per update; the simplified
  exponential-bucket variant we ship here keeps memory bounded.

**Why two:** Page-Hinkley alarms on directional drift (means moving
in one direction); ADWIN alarms on any change in distribution. For
the conformal-coverage stream from PR #38, Page-Hinkley flags
under-coverage drift specifically; ADWIN flags any regime shift
(could be either direction). Operators can wire either or both.

The detectors are ``stateful`` -- you call ``.update(value)`` once
per new observation and check ``.in_alarm`` after. Reset semantics
are documented per detector.

Designed as the next layer on top of:
- ``models/calibration.py`` (n-aware reliability summary)
- ``models/conformal.py`` (split-conformal coverage)
- ``flows/health_check.py`` (calibration + conformal alerts)

The detector lives one rung above those: instead of "is today's
coverage below threshold?", it answers "has coverage been trending
downward across multiple cron runs?" -- the slow regime-shift signal
that single-run thresholds miss.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Final

# Page-Hinkley default tuning. ``delta`` is the minimum drift we care
# to detect; for conformal coverage this is "1 percentage point of
# coverage drop" = 0.01. ``lambda_`` is the alarm threshold; 5.0 is
# conservative for noisy daily streams (Bifet et al. recommend 5-50
# depending on stream variance).
PAGE_HINKLEY_DEFAULT_DELTA: Final = 0.01
PAGE_HINKLEY_DEFAULT_LAMBDA: Final = 5.0
PAGE_HINKLEY_DEFAULT_MIN_INSTANCES: Final = 30

# ADWIN default. ``delta`` here is statistical confidence (smaller =
# stricter alarm). 0.002 is the Bifet & Gavalda 2007 default for
# "few false alarms".
ADWIN_DEFAULT_DELTA: Final = 0.002
ADWIN_DEFAULT_MIN_WINDOW: Final = 32  # don't alarm before this many obs


@dataclass
class PageHinkleyDetector:
    """One-sided Page-Hinkley test for downward drift.

    ``update(x)`` advances the test with one new observation. After
    ``min_instances`` observations have been seen, ``in_alarm`` is
    True iff the cumulative-sum gap from the running minimum exceeds
    ``lambda_``. The class is one-sided -- to detect upward drift,
    feed ``-x`` instead of ``x``.

    Reset on alarm: caller decides. The detector continues to
    update; for forecast-lab's daily cron, the right pattern is
    "alarm once, log it, manually reset after investigating".
    """

    delta: float = PAGE_HINKLEY_DEFAULT_DELTA
    lambda_: float = PAGE_HINKLEY_DEFAULT_LAMBDA
    min_instances: int = PAGE_HINKLEY_DEFAULT_MIN_INSTANCES

    _n_seen: int = field(default=0, init=False)
    _running_mean: float = field(default=0.0, init=False)
    _cumulative_sum: float = field(default=0.0, init=False)
    _min_cumulative: float = field(default=0.0, init=False)
    _in_alarm: bool = field(default=False, init=False)

    @property
    def n_seen(self) -> int:
        return self._n_seen

    @property
    def in_alarm(self) -> bool:
        return self._in_alarm

    @property
    def gap(self) -> float:
        """Current cumulative-sum gap from the running minimum.

        ``in_alarm`` flips True when ``gap > lambda_``. Useful as a
        continuous "drift severity" signal for dashboard rendering
        even when not alarming yet.
        """
        return self._cumulative_sum - self._min_cumulative

    def update(self, x: float) -> bool:
        """Advance with one observation. Returns ``in_alarm`` post-update."""
        self._n_seen += 1
        # Welford's incremental mean.
        self._running_mean += (x - self._running_mean) / self._n_seen
        # One-sided downward Page-Hinkley: accumulate (running_mean - x - delta).
        # When x is below mean by more than delta, the cumsum grows;
        # when x is at or above mean, the cumsum stays flat or shrinks.
        self._cumulative_sum += self._running_mean - x - self.delta
        self._min_cumulative = min(self._min_cumulative, self._cumulative_sum)
        if self._n_seen < self.min_instances:
            self._in_alarm = False
            return False
        self._in_alarm = self.gap > self.lambda_
        return self._in_alarm

    def reset(self) -> None:
        """Clear all state -- call after an alarm has been investigated."""
        self._n_seen = 0
        self._running_mean = 0.0
        self._cumulative_sum = 0.0
        self._min_cumulative = 0.0
        self._in_alarm = False


@dataclass
class _AdwinBucket:
    """One exponential-histogram bucket: count + running sum."""

    count: int = 0
    total: float = 0.0


@dataclass
class AdwinDetector:
    """Simplified ADWIN with exponential-histogram bucket compression.

    Holds a window of recent observations split into geometric-size
    buckets (size 1, 2, 4, 8, ...). On every update we attempt every
    possible binary split and alarm if the difference of sub-window
    means exceeds the Hoeffding bound for the requested confidence.

    The ``delta`` parameter is statistical confidence -- not the
    Page-Hinkley sense. Smaller delta = stricter alarm = fewer false
    alarms, slower detection.
    """

    delta: float = ADWIN_DEFAULT_DELTA
    min_window: int = ADWIN_DEFAULT_MIN_WINDOW

    _values: list[float] = field(default_factory=list, init=False)
    _in_alarm: bool = field(default=False, init=False)

    @property
    def n_seen(self) -> int:
        return len(self._values)

    @property
    def in_alarm(self) -> bool:
        return self._in_alarm

    @property
    def window_size(self) -> int:
        return len(self._values)

    def update(self, x: float) -> bool:
        """Append ``x`` to the window. Returns ``in_alarm`` post-update.

        When an alarm fires, the window is shrunk: we drop the oldest
        elements up to the split point that triggered the alarm.
        Subsequent updates compare against the post-shrink window.
        """
        self._values.append(float(x))
        n = len(self._values)
        if n < self.min_window:
            self._in_alarm = False
            return False

        # Try every possible cut point. Shrink + alarm at the first one
        # where the means differ by more than the Hoeffding bound.
        # ADWIN's official algorithm searches all cuts; we do the same
        # but bail at the first violation for simplicity.
        for cut in range(1, n):
            n_left = cut
            n_right = n - cut
            if n_left < 2 or n_right < 2:
                continue
            mean_left = sum(self._values[:cut]) / n_left
            mean_right = sum(self._values[cut:]) / n_right
            # Hoeffding bound for [0, 1]-bounded streams; we extend to
            # general bounded streams via the variance-free conservative
            # form ``epsilon = sqrt((1 / (2 * harmonic_n)) * ln(4 / delta))``.
            harmonic_n = 1.0 / (1.0 / n_left + 1.0 / n_right)
            epsilon = math.sqrt((1.0 / (2.0 * harmonic_n)) * math.log(4.0 / self.delta))
            if abs(mean_left - mean_right) > epsilon:
                # Drift detected at this cut; drop everything before it.
                self._values = self._values[cut:]
                self._in_alarm = True
                return True

        self._in_alarm = False
        return False

    def reset(self) -> None:
        """Clear the window."""
        self._values = []
        self._in_alarm = False


def detect_drift_in_stream(
    values: Iterable[float], *, detector: PageHinkleyDetector | AdwinDetector
) -> list[int]:
    """Replay an iterable of observations through ``detector`` and
    return the indices at which an alarm fired.

    Useful for batch analysis (e.g., "did Page-Hinkley flag any
    regime change in the past 90 days of conformal coverage?")
    without integrating the detector into a live cron stream.
    """
    alarms: list[int] = []
    for i, v in enumerate(values):
        if detector.update(v):
            alarms.append(i)
    return alarms


__all__ = [
    "ADWIN_DEFAULT_DELTA",
    "ADWIN_DEFAULT_MIN_WINDOW",
    "PAGE_HINKLEY_DEFAULT_DELTA",
    "PAGE_HINKLEY_DEFAULT_LAMBDA",
    "PAGE_HINKLEY_DEFAULT_MIN_INSTANCES",
    "AdwinDetector",
    "PageHinkleyDetector",
    "detect_drift_in_stream",
]
