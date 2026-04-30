"""Verdict-deepening diagnostics for the NDFD/NBM Brier comparison.

Pure functions that consume the parallel arrays the engine already
accumulates per evaluation (model prob, NDFD prob, outcome, bracket
index, valid_date) and produce two breakdowns:

1. **Per-bracket-band Brier** — center bands (±1 around the forecast
   mean) vs. wing bands (±2..±3). Diagnoses where in the price
   distribution our model gains or loses vs. NDFD.

2. **Per-month metrics** — monthly Brier (model on subset, NDFD) and
   monthly mean CLV proxy (model_prob - ndfd_prob). Diagnoses whether
   verdict gaps (e.g., KMDW -60% overall) are uniform across the year
   or driven by a specific regime (winter lake-effect, sea-breeze
   season, chinook events).

Both functions operate strictly on the **NDFD-matched subset** — rows
where ``ndfd_probs`` is not NaN — mirroring how ``_aggregate_results``
in ``engine.py`` computes the headline Brier-vs-NDFD numbers. That
keeps every comparison apples-to-apples.

No I/O, no engine state. Tested in isolation in
``tests/test_diagnostics.py``.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date as date_t
from typing import Any, Final, Literal

import numpy as np

from kq.models.calibration import brier_score

# Match the engine's brier_score input clamp.
_PROB_CLIP: Final[tuple[float, float]] = (0.01, 0.99)


def bracket_band(idx: int, n_brackets: int) -> Literal["center", "wing"]:
    """Classify a 0-indexed bracket position as ``center`` or ``wing``.

    The center band is the middle bracket plus its two immediate
    neighbors (``|idx - center| ≤ 1``). The wing band is everything
    else. For odd ``n_brackets`` the center is unambiguous; for the
    7-bracket default that yields {2,3,4} center and {0,1,5,6} wing.
    """
    if n_brackets <= 0:
        raise ValueError(f"n_brackets must be > 0, got {n_brackets}")
    if not 0 <= idx < n_brackets:
        raise ValueError(f"idx {idx} out of range for n_brackets={n_brackets}")
    center = (n_brackets - 1) // 2
    return "center" if abs(idx - center) <= 1 else "wing"


def per_band_brier(
    *,
    bracket_idx: np.ndarray,
    model_probs: np.ndarray,
    ndfd_probs: np.ndarray,
    outcomes: np.ndarray,
    n_brackets: int,
) -> dict[str, dict[str, float | int | None]]:
    """Compute Brier-vs-NDFD per (center | wing) band on the matched subset.

    Returns a dict keyed by band name with rounded numerics. Bands with
    fewer than 1 NDFD-covered evaluation report ``None`` for the Brier
    fields and 0 for ``n_with_ndfd``.
    """
    if not (
        bracket_idx.shape == model_probs.shape == ndfd_probs.shape == outcomes.shape
    ):
        raise ValueError("bracket_idx / model_probs / ndfd_probs / outcomes shape mismatch")

    out: dict[str, dict[str, float | int | None]] = {}
    for band_name in ("center", "wing"):
        band_mask = np.array(
            [bracket_band(int(i), n_brackets) == band_name for i in bracket_idx],
            dtype=bool,
        )
        ndfd_mask = ~np.isnan(ndfd_probs)
        mask = band_mask & ndfd_mask
        n = int(mask.sum())
        if n == 0:
            out[band_name] = {
                "n_with_ndfd": 0,
                "brier_model_subset": None,
                "brier_ndfd": None,
                "brier_improvement_vs_ndfd_pct": None,
            }
            continue
        brier_model = brier_score(
            np.clip(model_probs[mask], *_PROB_CLIP), outcomes[mask]
        )
        brier_ndfd = brier_score(
            np.clip(ndfd_probs[mask], *_PROB_CLIP), outcomes[mask]
        )
        improvement = (
            (brier_ndfd - brier_model) / brier_ndfd * 100.0 if brier_ndfd > 0 else None
        )
        out[band_name] = {
            "n_with_ndfd": n,
            "brier_model_subset": round(float(brier_model), 4),
            "brier_ndfd": round(float(brier_ndfd), 4),
            "brier_improvement_vs_ndfd_pct": (
                None if improvement is None else round(float(improvement), 2)
            ),
        }
    return out


def per_month_metrics(
    *,
    valid_dates: list[date_t],
    model_probs: np.ndarray,
    ndfd_probs: np.ndarray,
    outcomes: np.ndarray,
) -> list[dict[str, Any]]:
    """Group the matched subset by ``YYYY-MM`` and compute Brier + mean CLV.

    Returns a list (one entry per month with ≥ 1 NDFD-covered row),
    sorted by month ascending. Entries:

      ``{month, n_with_ndfd, brier_model_subset, brier_ndfd,
        brier_improvement_vs_ndfd_pct, mean_clv_pp}``

    where ``mean_clv_pp = mean(model_prob - ndfd_prob) * 100`` over
    the matched subset for that month. Rows missing NDFD are dropped
    before the group-by.
    """
    if not (len(valid_dates) == model_probs.size == ndfd_probs.size == outcomes.size):
        raise ValueError("valid_dates / probs / outcomes length mismatch")

    ndfd_mask = ~np.isnan(ndfd_probs)
    if not ndfd_mask.any():
        return []

    by_month: dict[str, list[int]] = defaultdict(list)
    for i, vd in enumerate(valid_dates):
        if not ndfd_mask[i]:
            continue
        key = f"{vd.year:04d}-{vd.month:02d}"
        by_month[key].append(i)

    rows: list[dict[str, Any]] = []
    for month in sorted(by_month):
        idx = np.array(by_month[month], dtype=int)
        m_probs = np.clip(model_probs[idx], *_PROB_CLIP)
        n_probs = np.clip(ndfd_probs[idx], *_PROB_CLIP)
        outs = outcomes[idx]
        brier_model = brier_score(m_probs, outs)
        brier_ndfd = brier_score(n_probs, outs)
        improvement = (
            (brier_ndfd - brier_model) / brier_ndfd * 100.0 if brier_ndfd > 0 else None
        )
        clv_pp = float((model_probs[idx] - ndfd_probs[idx]).mean() * 100.0)
        rows.append(
            {
                "month": month,
                "n_with_ndfd": int(idx.size),
                "brier_model_subset": round(float(brier_model), 4),
                "brier_ndfd": round(float(brier_ndfd), 4),
                "brier_improvement_vs_ndfd_pct": (
                    None if improvement is None else round(float(improvement), 2)
                ),
                "mean_clv_pp": round(clv_pp, 3),
            }
        )
    return rows
