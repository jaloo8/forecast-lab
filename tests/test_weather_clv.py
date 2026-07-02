"""Tests for the weather CLV evaluator (vs NDFD).

The 2026-06-11 audit (root cause #10) replaced the outcome-conditioned
``mean_signed_edge_vs_ndfd`` with the unconditional ``mean_edge_vs_ndfd``;
the outcome-invariance test here fails under the old definition.
"""

from __future__ import annotations

import math
from datetime import date

import pytest

from kq.backtest.weather_clv import (
    BracketEvaluation,
    SettledBracket,
    WeatherClvSummary,
    evaluate_brackets,
)


def _b(
    station: str,
    threshold: float,
    model: float,
    ndfd: float,
    observed: float,
    d: date = date(2025, 1, 1),
) -> SettledBracket:
    return SettledBracket(
        station=station,
        valid_date=d,
        threshold_f=threshold,
        model_prob_yes=model,
        ndfd_prob_yes=ndfd,
        observed_high_f=observed,
    )


# A: YES side, we agree higher, YES wins -> correct.   edge +0.2
# B: NO side, we rate lower, NO wins -> correct.        edge -0.2
# C: YES side, we rate higher, YES loses -> wrong.      edge +0.05
_THREE = [
    _b("KJFK", 75.0, 0.70, 0.50, 80.0),
    _b("KJFK", 90.0, 0.30, 0.50, 80.0),
    _b("KLAX", 70.0, 0.60, 0.55, 65.0),
]


def test_per_bracket_edge_and_correct_side() -> None:
    summ = evaluate_brackets(_THREE)
    evs = {(e.station, e.threshold_f): e for e in summ.evaluations}
    a = evs[("KJFK", 75.0)]
    assert a.edge == pytest.approx(0.20)
    assert a.realized_yes is True
    assert a.correct_side is True
    b = evs[("KJFK", 90.0)]
    assert b.edge == pytest.approx(-0.20)
    assert b.realized_yes is False
    assert b.correct_side is True
    c = evs[("KLAX", 70.0)]
    assert c.realized_yes is False
    assert c.correct_side is False


def test_overall_aggregates() -> None:
    summ = evaluate_brackets(_THREE)
    assert summ.n_evaluated == 3
    assert summ.win_rate_when_picked == pytest.approx(2 / 3)
    # UNCONDITIONAL mean edge: (+0.2 - 0.2 + 0.05) / 3 -- outcomes play
    # no part. (The retired signed metric was (+0.2 + 0.2 - 0.05) / 3.)
    assert summ.mean_edge_vs_ndfd == pytest.approx(0.05 / 3)
    # model is sharper than NDFD on these outcomes
    assert summ.brier_model == pytest.approx(0.18)
    assert summ.brier_ndfd == pytest.approx(0.2675)
    assert summ.brier_model is not None and summ.brier_ndfd is not None
    assert summ.brier_model < summ.brier_ndfd


def test_mean_edge_is_outcome_free() -> None:
    """THE audit property: flipping every realized outcome must leave
    mean_edge_vs_ndfd untouched. The retired mean_signed_edge_vs_ndfd
    flipped sign under this transformation -- this test fails under the
    old outcome-conditioned definition."""
    base = [
        _b("KJFK", 75.0, 0.70, 0.50, 80.0),  # YES realized
        _b("KJFK", 85.0, 0.65, 0.50, 90.0),  # YES realized
    ]
    flipped = [
        _b("KJFK", 75.0, 0.70, 0.50, 70.0),  # NO realized
        _b("KJFK", 85.0, 0.65, 0.50, 80.0),  # NO realized
    ]
    s_base = evaluate_brackets(base)
    s_flip = evaluate_brackets(flipped)
    assert s_base.mean_edge_vs_ndfd == pytest.approx(0.175)
    assert s_flip.mean_edge_vs_ndfd == pytest.approx(s_base.mean_edge_vs_ndfd)
    # The descriptive win rate DOES move -- that's fine, it's labeled as
    # descriptive and gates nothing.
    assert s_base.win_rate_when_picked == pytest.approx(1.0)
    assert s_flip.win_rate_when_picked == pytest.approx(0.0)
    # And the retired construction would have flipped sign:
    old_base = (
        sum((abs(e.edge) if e.correct_side else -abs(e.edge)) for e in s_base.evaluations) / 2
    )
    old_flip = (
        sum((abs(e.edge) if e.correct_side else -abs(e.edge)) for e in s_flip.evaluations) / 2
    )
    assert old_base == pytest.approx(-old_flip)
    assert old_base != pytest.approx(old_flip)


def test_per_station_breakdown() -> None:
    summ = evaluate_brackets(_THREE)
    assert set(summ.per_station) == {"KJFK", "KLAX"}
    jfk = summ.per_station["KJFK"]
    assert jfk.n == 2
    assert jfk.win_rate_when_picked == pytest.approx(1.0)
    # (+0.2 - 0.2) / 2 -- the station's edges cancel unconditionally.
    assert jfk.mean_edge_vs_ndfd == pytest.approx(0.0)
    assert jfk.brier_model == pytest.approx(0.09)
    lax = summ.per_station["KLAX"]
    assert lax.n == 1
    assert lax.win_rate_when_picked == pytest.approx(0.0)
    assert lax.mean_edge_vs_ndfd == pytest.approx(0.05)


def test_zero_edge_is_not_picked() -> None:
    # model == ndfd -> edge 0 -> no trade -> excluded from the win-rate
    # denominator (label matches computation: "when picked").
    summ = evaluate_brackets([_b("KMIA", 80.0, 0.50, 0.50, 85.0)])
    assert summ.n_evaluated == 1
    assert summ.evaluations[0].correct_side is False
    assert summ.win_rate_when_picked is None
    assert summ.mean_edge_vs_ndfd == pytest.approx(0.0)


def test_skips_nan_rows() -> None:
    rows = [
        _b("KJFK", 75.0, math.nan, 0.5, 80.0),  # no model
        _b("KJFK", 75.0, 0.7, math.nan, 80.0),  # no ndfd
        _b("KJFK", 75.0, 0.7, 0.5, 80.0),  # good
    ]
    summ = evaluate_brackets(rows)
    assert summ.n_evaluated == 1
    assert summ.n_skipped_no_model == 1
    assert summ.n_skipped_no_ndfd == 1


def test_empty_input() -> None:
    summ = evaluate_brackets([])
    assert isinstance(summ, WeatherClvSummary)
    assert summ.n_evaluated == 0
    assert summ.brier_model is None
    assert summ.brier_ndfd is None
    assert summ.mean_edge_vs_ndfd is None
    assert summ.win_rate_when_picked is None
    assert summ.per_station == {}


def test_all_skipped_yields_empty_summary() -> None:
    summ = evaluate_brackets([_b("KJFK", 75.0, math.nan, math.nan, 80.0)])
    assert summ.n_evaluated == 0
    assert summ.n_skipped_no_model == 1  # model checked first
    assert summ.brier_model is None


def test_evaluations_are_typed() -> None:
    summ = evaluate_brackets(_THREE)
    assert all(isinstance(e, BracketEvaluation) for e in summ.evaluations)
