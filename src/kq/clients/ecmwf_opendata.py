"""ECMWF Open Data direct integration -- Phase 1 (URL primitives + station extraction).

ECMWF Open Data is the European Centre for Medium-Range Weather Forecasts'
publicly-released subset of IFS HRES (deterministic) and IFS ENS (51-member)
forecasts. Free, no auth, updated 4x per day. The dissemination has been
public since October 2025 and is the canonical first-party feed for IFS
data at 0.25 degree resolution.

We already ingest ECMWF IFS through Open-Meteo's `ecmwf_ifs025` lane
(``model='ecmwf'`` rows in ``weather_forecast``). Going direct adds:

- **Lower latency**: 1-2 hour vs Open-Meteo cache refresh (~6 hours).
- **Operational resilience**: removes the third-party caching dependency.
- **Per-cycle access**: 4 cycles/day (00/06/12/18 UTC) vs Open-Meteo's
  once-per-day refresh on the free tier.

We do NOT pick up additional resolution -- both Open-Meteo's `ecmwf_ifs025`
and ECMWF Open Data publish the same 0.25-degree grid for the publicly
disseminated subset. The 0.1-degree HRES native run is paid-only.

**Phase 1 (this PR) -- pure functions, no ingest flow:**

- ``OpenDataFile`` -- one (cycle, stream, type, step) GRIB2 file.
- URL builder + cycle-string helpers.
- ``fetch_grib2_bytes`` -- async download of a full file. ECMWF Open
  Data ``fc`` files are bigger than the GEFSv12 reforecast ones
  (~130 MB at 0.25 degree, all surface variables packed into one
  file); the GEFSv12 byte-range trick using ``.index`` companions is
  the natural Phase 2 optimization. For Phase 1 we accept the bandwidth.
- ``extract_station_tmax`` -- xarray + cfgrib parse with explicit
  ``filter_by_keys={'shortName': '2t'}`` to pick out 2m temperature
  cleanly. Without the filter, cfgrib chokes on the multi-level
  ``heightAboveGround`` coord conflict between 2m (temp), 10m (wind),
  100m (high-altitude wind), etc., and silently returns whichever
  variable happens to parse first -- typically wind, which produces
  Kelvin values around 10 (not 290).

**Phase 2 (future PR) -- ingest flow:**

- ``ingest_ecmwf_opendata`` flow on a 4x/day cron.
- New tag ``model='ecmwf_opendata'`` in ``weather_forecast`` so an A/B
  Brier comparison vs the existing Open-Meteo ``model='ecmwf'`` rows is
  possible without disrupting the active ingest.
- Optional 51-member ENS in the same shape as the GEFSv12 reforecast
  loader.

The split mirrors the GEFSv12 reforecast PR #19 (pure functions) -> PR #21
(ingest flow) sequence; same rationale: keep the diff small enough to
review without burning Phase-2-extension scope discipline.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Final, Literal

import httpx

# Public dissemination root. Path layout:
#   {DISSEMINATION_BASE}/{YYYYMMDD}/{HH}z/{resolution}/{stream}/{filename}
DISSEMINATION_BASE: Final = "https://data.ecmwf.int/forecasts"

# Default resolution for the publicly disseminated subset. ECMWF also
# ships `0p4-beta` (0.4 degree) for testing; we don't use it.
DEFAULT_RESOLUTION: Final = "0p25"

# Streams: "oper" = HRES (deterministic), "enfo" = ENS (51 members).
Stream = Literal["oper", "enfo"]

# Forecast types we use:
#   "fc" -- the deterministic forecast in the oper stream.
#   "pf" -- ENS perturbed members (1..50) in the enfo stream.
#   "cf" -- ENS control member (0) in the enfo stream.
#   "ef" -- ENS combined file when ECMWF publishes one. We default to the
#           split fc / cf+pf layout because it's the documented one.
ForecastType = Literal["fc", "pf", "cf", "ef"]

# Cycles published. ECMWF Open Data is 4x/day; cycles are 00/06/12/18 UTC.
CYCLE_HOURS: Final[tuple[int, ...]] = (0, 6, 12, 18)

# Forecast-step granularity. HRES publishes hourly out to ~144h then 3-hourly
# to 240h; ENS publishes 3-hourly to 144h then 6-hourly to 360h. For the
# v1 daily-Tmax use case we pull every 3 hours through 48h, which gives us
# enough samples to compute the lead-1 calendar-day max.
LEAD_1_STEPS_HOURS: Final[tuple[int, ...]] = tuple(range(3, 49, 3))


@dataclass(frozen=True, slots=True)
class OpenDataFile:
    """One (cycle, stream, type, step, resolution) GRIB2 file."""

    cycle: datetime  # UTC, hour in CYCLE_HOURS
    stream: Stream  # "oper" | "enfo"
    type: ForecastType  # "fc" | "pf" | "cf" | "ef"
    step_hours: int  # forecast lead time in hours from the cycle
    resolution: str = DEFAULT_RESOLUTION

    def __post_init__(self) -> None:
        if self.cycle.tzinfo is None:
            raise ValueError("cycle must be timezone-aware")
        if self.cycle.tzinfo.utcoffset(self.cycle) != timedelta(0):
            raise ValueError(f"cycle must be UTC, got tz={self.cycle.tzinfo}")
        if self.cycle.hour not in CYCLE_HOURS:
            raise ValueError(
                f"cycle hour {self.cycle.hour} not in {CYCLE_HOURS}; ECMWF Open Data "
                "publishes 00/06/12/18 UTC only"
            )
        if self.step_hours < 0:
            raise ValueError(f"step_hours must be non-negative, got {self.step_hours}")

    @property
    def date_part(self) -> str:
        """``YYYYMMDD`` directory component."""
        return self.cycle.strftime("%Y%m%d")

    @property
    def cycle_part(self) -> str:
        """``HHz`` cycle component, e.g. ``00z``."""
        return f"{self.cycle.hour:02d}z"

    @property
    def filename(self) -> str:
        """File-name layout per ECMWF's open-data convention.

        Example: ``20260503000000-3h-oper-fc.grib2`` -- cycle timestamp,
        step, stream, type. Verified against the public dissemination as
        of 2026-05.
        """
        cycle_ts = self.cycle.strftime("%Y%m%d%H%M%S")
        return f"{cycle_ts}-{self.step_hours}h-{self.stream}-{self.type}.grib2"

    @property
    def url(self) -> str:
        return (
            f"{DISSEMINATION_BASE}/{self.date_part}/{self.cycle_part}/"
            f"ifs/{self.resolution}/{self.stream}/{self.filename}"
        )


def make_cycle_dt(cycle_date: date, hour: int = 0) -> datetime:
    """Build a UTC-aware datetime for a given calendar date + cycle hour."""
    if hour not in CYCLE_HOURS:
        raise ValueError(f"hour {hour} not in published cycles {CYCLE_HOURS}")
    return datetime.combine(cycle_date, time(hour=hour), tzinfo=UTC)


def files_for_lead_1(*, cycle: datetime, stream: Stream = "oper") -> list[OpenDataFile]:
    """Yield the GRIB2 files needed to compute next-calendar-day Tmax.

    For an init cycle at 00 UTC, lead-1 (today's local-day max for a
    station depending on tz) requires hourly samples through ~36-48h
    forecast hour. We use 3-hourly samples 3..48h, which covers all six
    stations in the universe (lst offsets -8 to -5).
    """
    forecast_type: ForecastType = "fc" if stream == "oper" else "ef"
    return [
        OpenDataFile(cycle=cycle, stream=stream, type=forecast_type, step_hours=h)
        for h in LEAD_1_STEPS_HOURS
    ]


@dataclass(frozen=True, slots=True)
class StationCoord:
    """Minimal station record needed for nearest-grid-point sampling."""

    icao: str
    latitude: float
    longitude: float
    """Longitude in [-180, 180]. ECMWF Open Data publishes on a
    [0, 360] east-positive grid, so callers must convert via
    ``longitude_e`` before sampling."""

    @property
    def longitude_e(self) -> float:
        """Longitude in [0, 360], east-positive -- ECMWF grid convention."""
        return self.longitude % 360.0


async def fetch_grib2_bytes(
    client: httpx.AsyncClient, file: OpenDataFile, *, timeout_s: float = 600.0
) -> bytes:
    """Download a single GRIB2 file in full.

    ECMWF Open Data ``fc`` files at 0.25 degree run ~130 MB (all
    surface variables packed together; only ~1 MB of that is 2m
    temperature). Phase 2's byte-range optimization will use the
    ``.index`` companion file to fetch only the 2t record; Phase 1
    accepts the full-file bandwidth in exchange for simplicity.

    Default timeout is 600 s -- 130 MB at 1 MB/s is ~130 s; we leave
    headroom for the slow tail of mobile/airport Wi-Fi.
    """
    resp = await client.get(file.url, timeout=timeout_s)
    resp.raise_for_status()
    return resp.content


# 2m temperature short name in the WMO GRIB2 / ECMWF parameter database.
# cfgrib's MARS-style filter accepts short names directly; this is the
# canonical key. (See https://codes.ecmwf.int/grib/param-db/?id=167.)
SHORT_NAME_2T: Final = "2t"


def extract_station_tmax(
    record_bytes: bytes,
    *,
    stations: Sequence[StationCoord],
    cfgrib_engine: str = "cfgrib",
) -> dict[str, float]:
    """Parse a GRIB2 record and sample 2m temperature at each station.

    ECMWF Open Data publishes 2m temperature as ``2t`` (paramId 167).
    We pass ``filter_by_keys={'shortName': '2t'}`` to cfgrib so it only
    builds the 2m-temperature dataset and ignores the multi-level
    ``heightAboveGround`` conflict that arises when cfgrib tries to
    merge 2m (temp), 10m (wind), and 100m variables into a single
    dataset. Without the filter cfgrib silently emits whichever
    variable happens to parse first, returning wind speeds as if they
    were temperatures.

    Returns Kelvin per ICAO; callers convert with
    :func:`kelvin_to_fahrenheit` at the persistence layer.

    The temp file dance mirrors ``gefs_reforecast.extract_station_values``
    -- cfgrib expects a path, not bytes, and leaves an idx sidecar that
    we sweep generically because the suffix pattern is unstable across
    cfgrib versions.
    """
    import xarray as xr  # noqa: PLC0415 -- lazy: cfgrib loads eccodes lib

    with tempfile.NamedTemporaryFile(suffix=".grib2", delete=False) as f:
        f.write(record_bytes)
        path = f.name
    try:
        ds = xr.open_dataset(
            path,
            engine=cfgrib_engine,
            backend_kwargs={"filter_by_keys": {"shortName": SHORT_NAME_2T}},
        )
        # cfgrib renames the GRIB2 short name '2t' -> 't2m' in the dataset
        # variable namespace. Pull the only data variable (the filter
        # guarantees there's exactly one) rather than hard-coding 't2m'
        # in case a future cfgrib version changes the convention.
        var_name = next(iter(ds.data_vars))
        out: dict[str, float] = {}
        for st in stations:
            value = ds[var_name].sel(
                latitude=st.latitude,
                longitude=st.longitude_e,
                method="nearest",
            )
            out[st.icao] = float(value)
        return out
    finally:
        if os.path.exists(path):
            os.unlink(path)
        parent = os.path.dirname(path)
        for sibling in os.listdir(parent):
            if sibling.startswith(os.path.basename(path) + "."):
                with contextlib.suppress(OSError):
                    os.unlink(os.path.join(parent, sibling))


def kelvin_to_fahrenheit(k: float) -> float:
    """Convert Kelvin to Fahrenheit. Mirrors ``gefs_reforecast``."""
    return (k - 273.15) * 9.0 / 5.0 + 32.0
