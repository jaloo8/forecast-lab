"""Weather ensemble post-processing model — re-exports the NGR implementation.

Kept as an entry point so older imports (`from kq.models.weather_ensemble import
WeatherEnsembleModel`) keep working. The real model lives in `weather_ngr.py`.
"""

from __future__ import annotations

from kq.models.weather_ngr import (
    NGRParameters,
    WeatherNGRModel,
    raw_brier_score,
)

# Backward-compat alias
WeatherEnsembleModel = WeatherNGRModel

__all__ = [
    "NGRParameters",
    "WeatherEnsembleModel",
    "WeatherNGRModel",
    "raw_brier_score",
]
