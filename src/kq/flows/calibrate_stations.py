"""Measure per-station lead-1 forecast bias and spread; write the manifest.

One tick reads the true lead-1 archive (the ``*_prevday1`` models) joined to
``weather_observed`` settlement truth, and writes
``models/station_calibration.json``.

WHY (measured 2026-07-29, 14,599 station-days over 2 years, 20 stations):
the raw ensemble mean is systematically COLD -- pooled bias **+1.78F**, with
every station but KLAX positive -- and its realised spread is **2.55F** against
the 3.5F constant the raw path assumed. Kalshi brackets are 2F wide, so an
uncorrected 1.8F offset displaces almost a full bracket of probability mass on
every station, every day. Correcting both improves bracket Brier **8.9%**
overall and on **19 of 20 stations**, validated causally (expanding window,
153,588 bracket predictions).

Read by :func:`kq.models.station_calibration.load_calibrations`, which the
strategy router consults when building raw models.

**Recommended cron** (UTC): monthly is ample -- the statistics move slowly and
the archive only extends daily. Run it after ``kq ingest-observed`` so the
newest truth is included::

    30 10 1 * *    kq calibrate-stations

Failure posture: a missing/short archive yields a manifest with
``usable: false`` per station rather than invented numbers, and the router then
falls back to its previous behaviour. Nothing silently fabricates a bias.
"""

from __future__ import annotations

from pathlib import Path

import structlog

from kq.config import get_settings
from kq.flows.ingest_weather import _db_path_from_settings
from kq.models.station_calibration import (
    DEFAULT_MANIFEST,
    MIN_PAIRS,
    fit_station_calibrations,
    write_manifest,
)

log = structlog.get_logger(__name__)


def main(
    *,
    db_path: Path | None = None,
    manifest_path: Path = DEFAULT_MANIFEST,
    min_pairs: int = MIN_PAIRS,
) -> int:
    """Fit and persist per-station calibrations. Returns the usable count."""
    settings = get_settings()
    db = db_path or _db_path_from_settings(settings.database_url)

    calibrations, fitted_through = fit_station_calibrations(db, min_pairs=min_pairs)
    if not calibrations:
        log.warning(
            "station_calibration.no_data",
            db=str(db),
            hint="no lead-1 archive rows joined to observed truth; nothing written",
        )
        return 0

    path = write_manifest(calibrations, fitted_through=fitted_through, path=manifest_path)
    usable = [c for c in calibrations.values() if c.usable]
    skipped = [c.station for c in calibrations.values() if not c.usable]

    for cal in sorted(usable, key=lambda c: -abs(c.bias_f)):
        log.info(
            "station_calibration.fitted",
            station=cal.station,
            n_pairs=cal.n_pairs,
            bias_f=cal.bias_f,
            sigma_f=cal.sigma_f,
        )
    log.info(
        "station_calibration.done",
        n_usable=len(usable),
        n_skipped_low_evidence=len(skipped),
        skipped=skipped,
        fitted_through=fitted_through,
        manifest=str(path),
    )
    return len(usable)
