"""NBM probabilistic forecast (qmd element) -- Phase 1 (URL primitives + fetcher).

NOAA's National Blend of Models (NBM) publishes probabilistic
forecasts in GRIB2 on AWS Open Data at ``s3://noaa-nbm-grib2-pds``.
The ``qmd`` ("quantile distribution") element gives Tmax quantiles
directly: P10, P25, P50, P75, P90. This is what we need for the
true probabilistic NDFD-vs-our-model Brier comparison that the Pass
1 extension memo +the existing ``backtest_manifest.json`` honest_caveats
both flag as the upgrade path.

**Why now:** the v1 NDFD benchmark (currently in
:mod:`kq.flows.ingest_ndfd`) pulls Open-Meteo's deterministic NBM
Tmax and wraps it in a per-fold-fitted Gaussian sigma. That's a
useful baseline but the Gaussian-wrap mismatch with NBM's true
distribution shape is the load-bearing caveat in every Phase 5 #2
verdict. Switching to the qmd quantiles directly removes the
wrap-and-fit step -- we read NBM's own quantile estimates as the
benchmark, then compute Brier against thresholds without sigma
fitting at all.

**Phase 1 (this PR) -- pure functions, no ingest flow:**

- ``QmdFile`` -- one (cycle, step_hours) GRIB2 file in the AWS bucket.
- URL builder + cycle-string helpers.
- ``fetch_grib2_bytes`` -- async download. Files are ~30-50 MB
  (CONUS at 2.5km, all qmd elements packed), small enough not to
  need byte-range subsetting at v1 cadence.
- ``extract_station_quantiles`` -- xarray + cfgrib parse with
  ``filter_by_keys={'shortName': 'tmax'}`` plus the qmd-specific
  ``typeOfStatisticalProcessing`` mask, sample at station-nearest
  grid point, return a ``(p10, p25, p50, p75, p90)`` tuple per ICAO.

**Phase 2 (future PR) -- ingest flow:**

- Wire-up into the existing ``ndfd_forecast`` table by populating
  the ``p10_max_f`` ... ``p90_max_f`` columns with the qmd readings
  (currently always NULL on v1's deterministic path).
- Set ``source='nbm_qmd_s3'`` so the qmd path coexists with v1's
  ``source='nbm_deterministic_openmeteo'`` rows.
- Backtest engine consumes the qmd source for Brier-vs-NDFD when
  configured; falls back to deterministic when qmd missing.

The split mirrors PR #33 (ECMWF Open Data Phase 1 -> Phase 2
ingest) -- same scope rationale.

URL pattern (verified live 2026-05-04):

    https://noaa-nbm-grib2-pds.s3.amazonaws.com/
        blend.{YYYYMMDD}/{HH}/qmd/blend.t{HH}z.qmd.f{LLL}.co.grib2

Where ``co`` is "CONUS" (2.5km), ``HH`` is the cycle hour
(00/06/12/18), ``LLL`` is the forecast step in hours. NBM publishes
these about 90 minutes after each init cycle.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Final

import httpx

# NBM AWS Open Data bucket. No auth, no egress fees.
DISSEMINATION_BASE: Final = "https://noaa-nbm-grib2-pds.s3.amazonaws.com"

# CONUS resolution code in the NBM filename. NBM publishes other
# domains (Alaska 'ak', Hawaii 'hi', Puerto Rico 'pr') but for our
# 6-station universe (all CONUS), we only ever pull 'co'.
CONUS_DOMAIN_CODE: Final = "co"

# Cycles published. NBM is 4x/day same as ECMWF.
CYCLE_HOURS: Final[tuple[int, ...]] = (0, 6, 12, 18)

# Forecast hour for the lead-1 day's Tmax. NBM accumulates the
# tomorrow daily-Tmax field at step f048 under a 00z init (same
# logic as ECMWF Open Data PR #33 -- step=48h spans tomorrow's
# calendar day at the right local-time anchor).
LEAD_1_STEP_HOURS: Final = 48

# Default publish buffer. NBM publishes step files ~90 minutes after
# each init cycle; we use a 2.5h buffer to be safe.
DEFAULT_PUBLISH_BUFFER_HOURS: Final = 2.5

# Quantile labels NBM emits in the qmd element. NBM's GRIB2 'qmd'
# message contains ``percentileValue`` field that takes one of these
# integer values; cfgrib exposes them via the ``percentile_value``
# coordinate after parsing.
SUPPORTED_PERCENTILES: Final[tuple[int, ...]] = (10, 25, 50, 75, 90)


@dataclass(frozen=True, slots=True)
class QmdFile:
    """One (cycle, step_hours) GRIB2 file in the NBM qmd bucket."""

    cycle: datetime  # UTC, hour in CYCLE_HOURS
    step_hours: int  # forecast lead time in hours from cycle init
    domain: str = CONUS_DOMAIN_CODE

    def __post_init__(self) -> None:
        if self.cycle.tzinfo is None:
            raise ValueError("cycle must be timezone-aware")
        if self.cycle.tzinfo.utcoffset(self.cycle) != timedelta(0):
            raise ValueError(f"cycle must be UTC, got tz={self.cycle.tzinfo}")
        if self.cycle.hour not in CYCLE_HOURS:
            raise ValueError(
                f"cycle hour {self.cycle.hour} not in {CYCLE_HOURS}; "
                f"NBM publishes 00/06/12/18 UTC only"
            )
        if self.step_hours < 0:
            raise ValueError(f"step_hours must be non-negative, got {self.step_hours}")

    @property
    def date_part(self) -> str:
        """``blend.YYYYMMDD`` directory component."""
        return f"blend.{self.cycle.strftime('%Y%m%d')}"

    @property
    def cycle_part(self) -> str:
        """``HH`` cycle component (zero-padded)."""
        return f"{self.cycle.hour:02d}"

    @property
    def filename(self) -> str:
        """Per NBM's bucket convention. Live-verified 2026-05-04."""
        return f"blend.t{self.cycle_part}z.qmd.f{self.step_hours:03d}.{self.domain}.grib2"

    @property
    def url(self) -> str:
        return f"{DISSEMINATION_BASE}/{self.date_part}/{self.cycle_part}/qmd/{self.filename}"


def make_cycle_dt(cycle_date: date, hour: int = 0) -> datetime:
    """Build a UTC-aware cycle datetime."""
    if hour not in CYCLE_HOURS:
        raise ValueError(f"hour {hour} not in published cycles {CYCLE_HOURS}")
    return datetime.combine(cycle_date, time(hour=hour), tzinfo=UTC)


def latest_published_cycle(
    *,
    now: datetime,
    publish_buffer_hours: float = DEFAULT_PUBLISH_BUFFER_HOURS,
) -> datetime:
    """Return the most recent NBM cycle that has plausibly published
    its step=f048 by ``now``.

    NBM publishes step files ~90 minutes after init; we use a 2.5h
    buffer (configurable) so a fetch at 02:30 UTC pulls 00z confidently.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if publish_buffer_hours < 0:
        raise ValueError(f"publish_buffer_hours must be >= 0, got {publish_buffer_hours}")
    candidate = now.astimezone(UTC) - timedelta(hours=publish_buffer_hours)
    candidate_hour = max(h for h in CYCLE_HOURS if h <= candidate.hour)
    return candidate.replace(hour=candidate_hour, minute=0, second=0, microsecond=0)


@dataclass(frozen=True, slots=True)
class StationCoord:
    """Station lat/lon for nearest-grid-point sampling. Mirrors the
    type from :mod:`kq.clients.ecmwf_opendata` so callers can share."""

    icao: str
    latitude: float
    longitude: float

    @property
    def longitude_e(self) -> float:
        """Longitude in [0, 360), east-positive. NBM's CONUS grid is a
        Lambert-conformal projection: cfgrib emits ``latitude`` /
        ``longitude`` as *2-D* auxiliary coordinates over the (y, x)
        grid dims. Sampling therefore goes through a 2-D distance
        argmin (:func:`_nearest_grid_indices`), and the wrap convention
        here only needs to match whatever the file stores."""
        return self.longitude % 360.0


@dataclass(frozen=True, slots=True)
class StationQuantiles:
    """Per-station Tmax quantile readings extracted from one qmd file."""

    icao: str
    p10_kelvin: float
    p25_kelvin: float
    p50_kelvin: float
    p75_kelvin: float
    p90_kelvin: float


async def fetch_grib2_bytes(
    client: httpx.AsyncClient, file: QmdFile, *, timeout_s: float = 600.0
) -> bytes:
    """Download a single qmd GRIB2 file in full.

    NBM CONUS qmd files are ~30-50 MB at 2.5km. Small enough that
    byte-range subsetting via the .idx companion isn't worth the
    code complexity at v1's 4x/day cadence. Errors propagate; cron
    handles retry.
    """
    resp = await client.get(file.url, timeout=timeout_s)
    resp.raise_for_status()
    return resp.content


# WMO short name for max 2m temperature in NBM qmd. cfgrib emits this
# as ``mx2t`` (not ``2t``) because qmd files contain the accumulated
# max field, not a snapshot.
SHORT_NAME_TMAX: Final = "mx2t"


def extract_station_quantiles(
    record_bytes: bytes,
    *,
    stations: Sequence[StationCoord],
    cfgrib_engine: str = "cfgrib",
) -> dict[str, StationQuantiles]:
    """Parse a qmd GRIB2 file and sample Tmax quantiles at each station.

    Uses ``filter_by_keys={'shortName': 'mx2t'}`` to pick out the max
    2m temperature messages. The qmd file packs P10/P25/P50/P75/P90
    as separate GRIB2 messages distinguished by the ``percentileValue``
    field (5, 25, 50, 75, 90 -- NBM uses ``5`` for P10 historically;
    we accept both).

    Returns ``{icao: StationQuantiles}`` -- per-ICAO Kelvin readings
    at all five quantiles. Caller converts to Fahrenheit + writes to
    the ``ndfd_forecast`` table's ``p10_max_f`` ... ``p90_max_f``
    columns at the persistence layer.

    Station sampling is a 2-D distance argmin over the grid's lat/lon
    arrays (2026-07-01 audit, Tier 2): NBM's CONUS grid is a
    Lambert-conformal projection, so cfgrib exposes ``latitude`` /
    ``longitude`` as 2-D coordinates over the (y, x) dims —
    ``.sel(latitude=..., method='nearest')`` raises on such non-index
    coordinates, which killed the first real (non-mocked) use.
    """
    import xarray as xr  # noqa: PLC0415 -- lazy: cfgrib loads eccodes lib

    with tempfile.NamedTemporaryFile(suffix=".grib2", delete=False) as f:
        f.write(record_bytes)
        path = f.name
    try:
        ds = xr.open_dataset(
            path,
            engine=cfgrib_engine,
            backend_kwargs={"filter_by_keys": {"shortName": SHORT_NAME_TMAX}},
        )
        # cfgrib emits the percentile axis as a coord. Iterate and
        # sample at each station nearest grid point.
        var_name = next(iter(ds.data_vars))
        var = ds[var_name]
        out: dict[str, StationQuantiles] = {}
        for st in stations:
            dim_indices = _nearest_grid_indices(var, station=st)
            sampled = var.isel(dim_indices)
            quantile_values: dict[int, float] = {}
            # NBM's "percentileValue" coordinate after cfgrib parsing.
            # When cfgrib emits the percentile axis under a different
            # name in a future schema, this lookup will need updating;
            # we look up by attribute first to stay tolerant.
            pcoord_name = next(
                (c for c in ("percentileValue", "percentile_value") if c in sampled.coords),
                None,
            )
            if pcoord_name is None:
                # Single-quantile file (rare); fall back to median.
                v = float(sampled.values)
                quantile_values = {p: v for p in SUPPORTED_PERCENTILES}
            else:
                pvalues = _to_list(sampled.coords[pcoord_name].values)
                vvalues = _to_list(sampled.values)
                for p, v in zip(pvalues, vvalues, strict=False):
                    quantile_values[int(p)] = float(v)
            out[st.icao] = StationQuantiles(
                icao=st.icao,
                p10_kelvin=quantile_values.get(10, quantile_values.get(5, float("nan"))),
                p25_kelvin=quantile_values.get(25, float("nan")),
                p50_kelvin=quantile_values.get(50, float("nan")),
                p75_kelvin=quantile_values.get(75, float("nan")),
                p90_kelvin=quantile_values.get(90, float("nan")),
            )
        return out
    finally:
        if os.path.exists(path):
            os.unlink(path)
        parent = os.path.dirname(path)
        for sibling in os.listdir(parent):
            if sibling.startswith(os.path.basename(path) + "."):
                with contextlib.suppress(OSError):
                    os.unlink(os.path.join(parent, sibling))


def _nearest_grid_indices(var: object, *, station: StationCoord) -> dict[str, int]:
    """Nearest grid point for a station via a wrap-safe 2-D distance argmin.

    numpy only — no scipy KD-trees, no pyproj. Handles both grid layouts
    cfgrib can emit:

    - Lambert-conformal (NBM CONUS): ``latitude`` / ``longitude`` are 2-D
      auxiliary coordinates over the (y, x) dims. ``.sel(...,
      method='nearest')`` raises on these non-index coords, so we argmin
      the squared degree distance over the full arrays instead.
    - Regular lat/lon grids: 1-D index coords, meshgridded here so a
      single code path serves both.

    Distance metric is squared degrees with the longitude delta wrapped to
    [-180, 180) — nearest-neighbor selection at station scale (same
    convention as ``method='nearest'`` on the regular ECMWF/GEFS grids),
    not great-circle geodesy.

    Returns ``{dim_name: index}`` suitable for ``var.isel(...)``, leaving
    any non-spatial dims (e.g. the percentile axis) untouched.
    """
    import numpy as np  # noqa: PLC0415 -- lazy: only needed on the cfgrib path

    lat_coord = var.coords["latitude"]  # type: ignore[attr-defined]
    lon_coord = var.coords["longitude"]  # type: ignore[attr-defined]
    lat = np.asarray(lat_coord.values, dtype=float)
    lon = np.asarray(lon_coord.values, dtype=float)
    if lat.ndim == 1:
        dims: tuple[str, ...] = (str(lat_coord.dims[0]), str(lon_coord.dims[0]))
        lon, lat = np.meshgrid(lon, lat)
    else:
        dims = tuple(str(d) for d in lat_coord.dims)
    dlat = lat - station.latitude
    dlon = (lon - station.longitude_e + 180.0) % 360.0 - 180.0
    dist2 = dlat * dlat + dlon * dlon
    flat_index = int(np.argmin(dist2))
    indices = np.unravel_index(flat_index, dist2.shape)
    return {d: int(i) for d, i in zip(dims, indices, strict=True)}


def kelvin_to_fahrenheit(k: float) -> float:
    """Convert Kelvin to Fahrenheit. Mirrors gefs_reforecast + ecmwf_opendata."""
    return (k - 273.15) * 9.0 / 5.0 + 32.0


def _to_list(values: object) -> list[float]:
    """Coerce numpy / xarray / list / scalar values to a flat Python list.

    Production cfgrib output gives numpy arrays (have ``.tolist()``);
    test mocks may pass lists or scalars directly. Single tolerant entry
    point keeps the extract path readable.
    """
    if isinstance(values, list):
        return [float(v) for v in values]
    if hasattr(values, "tolist"):
        out = values.tolist()
        if not isinstance(out, list):
            return [float(out)]
        return [float(v) for v in out]
    # Single scalar fallback.
    return [float(values)]  # type: ignore[arg-type]


__all__ = [
    "CONUS_DOMAIN_CODE",
    "CYCLE_HOURS",
    "DEFAULT_PUBLISH_BUFFER_HOURS",
    "DISSEMINATION_BASE",
    "LEAD_1_STEP_HOURS",
    "SHORT_NAME_TMAX",
    "SUPPORTED_PERCENTILES",
    "QmdFile",
    "StationCoord",
    "StationQuantiles",
    "extract_station_quantiles",
    "fetch_grib2_bytes",
    "kelvin_to_fahrenheit",
    "latest_published_cycle",
    "make_cycle_dt",
]
