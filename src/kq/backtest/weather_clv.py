"""Weather backtest CLV evaluator — diagnostic mirror of ``nba_clv`` for weather.

Given a set of **settled** weather-bracket observations, each carrying:

- our model's ``P(high > threshold)`` (``model_prob_yes``),
- the NDFD/NBM benchmark's ``P(high > threshold)`` (``ndfd_prob_yes``),
- the realized observed daily high (``observed_high_f``),

this module produces a per-bracket evaluation and per-station + overall
aggregates:

- ``edge = model_prob_yes - ndfd_prob_yes`` — positive means we rate the
  YES (high-exceeds-threshold) side higher than the public benchmark does.
- ``realized_yes`` — 1 iff ``observed_high_f > threshold_f``.
- ``correct_side`` — True iff the side our edge picked won (descriptive only).
- Brier score for our model AND for NDFD, on the same realized outcomes —
  this pair is the skill comparison.
- ``mean_edge_vs_ndfd`` — the UNCONDITIONAL mean of ``edge``. A disagreement
  diagnostic, not a skill claim: it says how far we sit from NDFD on average,
  with no outcome in the formula.

The 2026-06-11 audit (root cause #10) retired the old
``mean_signed_edge_vs_ndfd`` — ``mean(+|edge| if picked side won else
-|edge|)`` — whose expectation is ``|edge| * (2p - 1)``: positive for any
zero-skill model that leans toward the likely side. It shared the biased
construction of the NBA ``mean_signed_clv`` and gated nothing honestly.

The evaluator is **read-only** and computes nothing about the model itself —
it takes pre-computed ``(model_prob, ndfd_prob, observed)`` tuples (the
caller / a follow-up flow runs the NGR/router + NDFD engine to produce them).
This is the same split as ``nba_clv`` (which takes a fitted Elo state).

Anchor caveat: unlike NBA (where Pinnacle is a true closing-line anchor),
weather has **no Kalshi market close to anchor against until prod**, so this
is a *Brier-vs-benchmark + mean-edge* diagnostic against NDFD, not literal
closing-line value. It mirrors what the rolling-origin backtest reports, but
runs on accumulating settled live data rather than a CV split — the ongoing
"are we still beating NDFD?" monitor. See ``nba_clv`` for the NBA twin and
docs/research/PASS-1-EXTENSION-EMOS-EXECUTION.md for why NDFD is the bar.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date

from kq.models.calibration import brier_score

# Clip predictive probs into the calibrated band before scoring, matching the
# rest of the codebase (every model produces probabilities in [0.01, 0.99]).
_PROB_FLOOR = 0.01
_PROB_CEIL = 0.99


@dataclass(frozen=True, slots=True)
class SettledBracket:
    """One settled (station, date, threshold) bracket with model + NDFD probs.

    ``model_prob_yes`` / ``ndfd_prob_yes`` are ``P(high > threshold_f)`` from our
    active model and from the NDFD benchmark respectively. Either may be
    ``nan`` when coverage is missing (NDFD history starts ~2024-11, so earlier
    rows legitimately lack it); such rows are skipped by the evaluator rather
    than scored.
    """

    station: str
    valid_date: date
    threshold_f: float
    model_prob_yes: float
    ndfd_prob_yes: float
    observed_high_f: float


@dataclass(frozen=True, slots=True)
class BracketEvaluation:
    """Per-bracket evaluator output."""

    station: str
    valid_date: date
    threshold_f: float
    model_prob_yes: float
    ndfd_prob_yes: float
    edge: float  # model_prob_yes - ndfd_prob_yes
    realized_yes: bool
    correct_side: bool  # descriptive only; True iff edge sign matched the outcome


@dataclass(frozen=True, slots=True)
class StationClvSummary:
    """Per-station aggregate. Weather edge is station-specific, so this is the
    load-bearing breakdown (NBA's twin aggregates only globally)."""

    station: str
    n: int
    brier_model: float
    brier_ndfd: float
    mean_edge_vs_ndfd: float
    win_rate_when_picked: float | None


@dataclass(frozen=True, slots=True)
class WeatherClvSummary:
    """Aggregated weather CLV-vs-NDFD result (overall + per station)."""

    n_evaluated: int
    n_skipped_no_ndfd: int
    n_skipped_no_model: int
    brier_model: float | None
    brier_ndfd: float | None
    mean_edge_vs_ndfd: float | None
    """Unconditional mean(model_prob_yes - ndfd_prob_yes). No outcome in the
    formula — a disagreement diagnostic. Skill lives in the Brier pair."""

    win_rate_when_picked: float | None
    """Fraction of PICKED sides (edge != 0) that won. Descriptive only —
    biased above 0.5 for any likely-side-leaning model; gates nothing."""
    per_station: dict[str, StationClvSummary] = field(default_factory=dict)
    evaluations: list[BracketEvaluation] = field(default_factory=list)


def _correct_side(edge: float, realized_yes: bool) -> bool:
    """edge > 0 -> we'd buy YES; YES wins iff realized_yes. edge < 0 -> buy NO.
    edge == 0 is no-trade, recorded as not-correct (don't reward ties)."""
    if edge > 0:
        return realized_yes
    if edge < 0:
        return not realized_yes
    return False


def evaluate_brackets(brackets: Iterable[SettledBracket]) -> WeatherClvSummary:
    """Evaluate settled brackets vs NDFD. Returns the JSON-safe summary.

    Rows whose ``ndfd_prob_yes`` or ``model_prob_yes`` is ``nan`` are skipped
    (counted separately) — they carry no comparable signal. Everything else is
    scored and aggregated overall + per station.
    """
    evaluations: list[BracketEvaluation] = []
    skipped_no_ndfd = 0
    skipped_no_model = 0

    for b in brackets:
        if math.isnan(b.model_prob_yes):
            skipped_no_model += 1
            continue
        if math.isnan(b.ndfd_prob_yes):
            skipped_no_ndfd += 1
            continue
        edge = b.model_prob_yes - b.ndfd_prob_yes
        realized_yes = b.observed_high_f > b.threshold_f
        evaluations.append(
            BracketEvaluation(
                station=b.station,
                valid_date=b.valid_date,
                threshold_f=b.threshold_f,
                model_prob_yes=b.model_prob_yes,
                ndfd_prob_yes=b.ndfd_prob_yes,
                edge=edge,
                realized_yes=realized_yes,
                correct_side=_correct_side(edge, realized_yes),
            )
        )

    return _aggregate(
        evaluations,
        skipped_no_ndfd=skipped_no_ndfd,
        skipped_no_model=skipped_no_model,
    )


def _score(evals: Sequence[BracketEvaluation]) -> tuple[float, float, float, float | None]:
    """Return (brier_model, brier_ndfd, mean_edge, win_rate) for a group.

    ``mean_edge`` is the unconditional mean of ``model - ndfd`` — the
    realized outcome deliberately does not enter it (2026-06-11 audit).
    ``win_rate`` divides by picked brackets only (edge != 0); None when
    nothing was picked, so the label matches the computation.
    """
    import numpy as np  # noqa: PLC0415 -- lazy import keeps cold-import surface small

    model_probs = np.clip(np.array([e.model_prob_yes for e in evals]), _PROB_FLOOR, _PROB_CEIL)
    ndfd_probs = np.clip(np.array([e.ndfd_prob_yes for e in evals]), _PROB_FLOOR, _PROB_CEIL)
    realized = np.array([1.0 if e.realized_yes else 0.0 for e in evals])
    mean_edge = float(np.array([e.edge for e in evals]).mean())
    n_picked = sum(1 for e in evals if e.edge != 0)
    win_rate = (
        sum(1 for e in evals if e.edge != 0 and e.correct_side) / n_picked if n_picked else None
    )
    return (
        brier_score(model_probs, realized),
        brier_score(ndfd_probs, realized),
        mean_edge,
        win_rate,
    )


def _aggregate(
    evaluations: Sequence[BracketEvaluation],
    *,
    skipped_no_ndfd: int,
    skipped_no_model: int,
) -> WeatherClvSummary:
    if not evaluations:
        return WeatherClvSummary(
            n_evaluated=0,
            n_skipped_no_ndfd=skipped_no_ndfd,
            n_skipped_no_model=skipped_no_model,
            brier_model=None,
            brier_ndfd=None,
            mean_edge_vs_ndfd=None,
            win_rate_when_picked=None,
            per_station={},
            evaluations=[],
        )

    brier_model, brier_ndfd, mean_edge, win_rate = _score(evaluations)

    per_station: dict[str, StationClvSummary] = {}
    by_station: dict[str, list[BracketEvaluation]] = {}
    for e in evaluations:
        by_station.setdefault(e.station, []).append(e)
    for station, evals in sorted(by_station.items()):
        bm, bn, me, wr = _score(evals)
        per_station[station] = StationClvSummary(
            station=station,
            n=len(evals),
            brier_model=bm,
            brier_ndfd=bn,
            mean_edge_vs_ndfd=me,
            win_rate_when_picked=wr,
        )

    return WeatherClvSummary(
        n_evaluated=len(evaluations),
        n_skipped_no_ndfd=skipped_no_ndfd,
        n_skipped_no_model=skipped_no_model,
        brier_model=brier_model,
        brier_ndfd=brier_ndfd,
        mean_edge_vs_ndfd=mean_edge,
        win_rate_when_picked=win_rate,
        per_station=per_station,
        evaluations=list(evaluations),
    )


__all__ = [
    "BracketEvaluation",
    "SettledBracket",
    "StationClvSummary",
    "WeatherClvSummary",
    "evaluate_brackets",
]
