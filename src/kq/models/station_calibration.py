"""Per-station lead-1 calibration: how wrong is the ensemble mean, and by how much?

READ THIS FIRST — THE ARCHIVE AND THE LIVE FEED ARE NOT THE SAME FORECAST
------------------------------------------------------------------------
**2026-07-29, measured on the host and then reverted.** Fitting on the
``*_prevday1`` ARCHIVE gives a large cold bias (pooled **+1.78F** over 14,599
station-days; KATL +3.00). Applying that correction to production made live
accuracy WORSE, not better:

    settlement-window Brier on 201 settled markets, 2,545 records
        before:  0.1680        after applying archive calibration:  0.1902
        (market, for reference: 0.1148)

The reason, measured directly on the same host:

    ARCHIVE  *_prevday1  (what the bias was fitted on)  bias +1.78F
    LIVE     ecmwf       (what production prices with)  bias +0.21F  sigma 3.29
    LIVE     gefs        (what production prices with)  bias -0.63F  sigma 3.45

**The live feed is essentially unbiased, and its spread is close to the 3.5F
fallback that was already in use.** The archive's cold bias is real but belongs
to a different forecast product. Correcting the live feed with an archive-fitted
number injects an error that was not there.

So this module now fits on the LIVE models only, and refuses (``usable=False``)
when live history is too thin -- which it currently is (n≈31 lead-1 pairs). It
therefore writes nothing usable today, and pricing keeps its previous behaviour.

The deeper implication, which outlives this module: **backtest and training
evidence derived from the archive may not transfer to live trading.** Any claim
of the form "the model scores X historically" needs to state which forecast
source it was measured on before it can be trusted for live pricing.

WHY THIS EXISTS
---------------
Measured 2026-07-29 on the true lead-1 archive (the ``*_prevday1`` models --
14,599 station-days, 20 stations, 2024-07 .. 2026-07), the raw ensemble mean is
**systematically cold**:

    pooled bias +1.78F      (KATL +3.00, KPHX +2.70, KPHL +2.54; only KLAX < 0)
    pooled sigma  2.55F     (against the 3.5F fallback the raw model assumed)

Kalshi weather brackets are 2F wide, so an uncorrected +1.8F offset displaces
almost a full bracket of probability mass -- on every station, every day. Until
this module existed, any station without a fitted NGR entry in the router config
priced with ``N(ensemble_mean, 3.5)``: no bias correction at all, and a spread
~37% too wide.

Applying both corrections improves bracket Brier by **8.9%** overall and on
**19 of 20 stations** (KPHX +21.8%, KLAS +18.8%, KMIA +16.2%), validated with a
strictly causal expanding window over 153,588 bracket predictions.

HONEST LIMITS
-------------
* This corrects the *marginal* distribution of forecast error. It does not make
  the forecast smarter on any individual day, and it is not a substitute for a
  properly fitted NGR/EMOS model -- it is the floor every station should have.
* Bias is fitted on the historical archive, whose model mix may differ slightly
  from the live ingest. Re-fit periodically (`kq calibrate-stations`) and watch
  the manifest's ``fitted_through`` date.
* Whether this is enough to beat the *market* is a separate, unresolved
  question -- the settled-market sample at our decision horizon is still only
  ~82 markets. `kq study-nowcast-edge` is the referee as data accumulates.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from kq.storage.duckdb_store import connect

# Fit ONLY on the models production actually prices with. Fitting on the
# `*_prevday1` archive and applying it here made live Brier worse (see the
# module header) because the two sources have different biases. Their lead-1
# coverage is thin, which is exactly why this module currently declines to
# emit a usable fit rather than emitting a confident wrong one.
LIVE_MODELS: Final = ("ecmwf", "gefs")

MIN_PAIRS: Final = 90  # ~3 months before a station's fit is trusted
MIN_MODELS_PER_DAY: Final = 2  # both live models must agree a day exists
SIGMA_FLOOR_F: Final = 0.75
DEFAULT_MANIFEST: Final = Path("models/station_calibration.json")


@dataclass(frozen=True)
class StationCalibration:
    """Measured lead-1 error statistics for one station."""

    station: str
    n_pairs: int
    bias_f: float
    sigma_f: float
    usable: bool

    def corrected(self, ens_mean: float) -> float:
        return ens_mean + self.bias_f


def fit_station_calibrations(
    db_path: Path,
    *,
    min_pairs: int = MIN_PAIRS,
) -> tuple[dict[str, StationCalibration], str | None]:
    """Measure (bias, sigma) per station from the lead-1 archive.

    Returns ``(calibrations, fitted_through)``. Stations with fewer than
    ``min_pairs`` observations are returned with ``usable=False`` rather than
    silently dropped -- a caller must be able to tell "not enough evidence"
    apart from "station unknown".
    """
    con = connect(db_path, read_only=True)
    try:
        rows = con.execute(
            """
            WITH ens AS (
              SELECT station, valid_date,
                     avg(forecast_high_f) AS fc,
                     count(DISTINCT model) AS n_models
              FROM weather_forecast
              WHERE forecast_high_f IS NOT NULL
                AND model IN (?, ?)
                -- genuine day-ahead only; the live pulls also carry leads 2-7
                AND valid_date - CAST(as_of AS DATE) = 1
              GROUP BY 1, 2
            )
            SELECT e.station, e.valid_date, e.fc, o.high_f
            FROM ens e
            JOIN weather_observed o
              ON o.station = e.station AND o.valid_date = e.valid_date
            WHERE o.high_f IS NOT NULL AND e.n_models >= ?
            ORDER BY e.valid_date
            """,
            [*LIVE_MODELS, MIN_MODELS_PER_DAY],
        ).fetchall()
    finally:
        con.close()

    errors: dict[str, list[float]] = {}
    latest: str | None = None
    for station, valid_date, fc, high_f in rows:
        errors.setdefault(station, []).append(float(high_f) - float(fc))
        latest = str(valid_date)

    out: dict[str, StationCalibration] = {}
    for station, errs in errors.items():
        usable = len(errs) >= min_pairs
        bias = statistics.mean(errs) if errs else 0.0
        sigma = statistics.pstdev(errs) if len(errs) > 1 else 0.0
        out[station] = StationCalibration(
            station=station,
            n_pairs=len(errs),
            bias_f=round(bias, 4),
            sigma_f=round(max(sigma, SIGMA_FLOOR_F), 4),
            usable=usable,
        )
    return out, latest


def write_manifest(
    calibrations: dict[str, StationCalibration],
    *,
    fitted_through: str | None,
    path: Path = DEFAULT_MANIFEST,
) -> Path:
    """Persist calibrations; the manifest is committed so reviews can see the fit."""
    usable = [c for c in calibrations.values() if c.usable]
    payload: dict[str, Any] = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "fitted_through": fitted_through,
        "lead_days": 1,
        "source_models": ",".join(LIVE_MODELS),
        "min_pairs": MIN_PAIRS,
        "n_stations_usable": len(usable),
        "pooled_bias_f": round(statistics.mean([c.bias_f for c in usable]), 4) if usable else None,
        "pooled_sigma_f": round(statistics.mean([c.sigma_f for c in usable]), 4)
        if usable
        else None,
        "stations": {s: asdict(c) for s, c in sorted(calibrations.items())},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_calibrations(path: Path = DEFAULT_MANIFEST) -> dict[str, StationCalibration]:
    """Load usable calibrations. Missing/unreadable manifest -> empty mapping.

    Deliberately forgiving: a missing manifest must degrade to the previous
    (uncalibrated) behaviour rather than break the trading path. Callers decide
    what to do with an absent entry.
    """
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, StationCalibration] = {}
    for station, raw in (payload.get("stations") or {}).items():
        try:
            cal = StationCalibration(
                station=str(raw["station"]),
                n_pairs=int(raw["n_pairs"]),
                bias_f=float(raw["bias_f"]),
                sigma_f=float(raw["sigma_f"]),
                usable=bool(raw["usable"]),
            )
        except (KeyError, TypeError, ValueError):
            continue
        if cal.usable:
            out[station] = cal
    return out
