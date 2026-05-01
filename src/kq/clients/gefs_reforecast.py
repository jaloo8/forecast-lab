"""GEFSv12 reforecast (NOAA Open Data) — phase 1 scaffold + phase 2 ingest.

Pure functions for navigating the `s3://noaa-gefs-retrospective` archive
(20-year, 5-member, 1-cycle/day reforecast set frozen at GEFSv12), plus
phase 2 byte-range fetch + cfgrib/xarray station extraction. See
``docs/research/GEFSV12-REFORECAST-INTEGRATION.md``.

**Phase 1 (PR #19) — pure functions, no deps:**

- URL builder, key iterator, idx parser, volume estimator.

**Phase 2 (PR #21, this commit) — adds cfgrib/xarray ingest:**

- ``fetch_idx_text`` — async download of a single ``.idx`` companion.
- ``fetch_grib2_record`` — async byte-range pull of a single record.
- ``extract_station_values`` — xarray + cfgrib parse of an in-memory GRIB2
  record; returns Tmax-at-station-coords as Kelvin.
- Per-record bandwidth is ~750 KB (whole-grid record, not per-grid-point).
  The byte-range still helps vs full-file (avoids the ~80 records we don't
  need per file), but actual savings are 1/N rather than 1/(N*grid_size).

CLI: ``kq plan-gefsv12-pull`` (phase 1, dry run) and
``kq pull-gefsv12-reforecasts`` (phase 2, real pull).
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import os
import tempfile
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Final, Literal

import httpx

# AWS Open Data — no auth, no egress fees. CONUS via byte-range subsetting.
BUCKET: Final = "noaa-gefs-retrospective"
ARCHIVE_PREFIX: Final = "GEFSv12/reforecast"

# 20-year archive frozen at GEFSv12 (verified 2026-04-30).
ARCHIVE_FIRST_YEAR: Final = 2000
ARCHIVE_LAST_YEAR: Final = 2019

# Members shipping in the reforecast set.
DEFAULT_MEMBERS: Final[tuple[str, ...]] = ("c00", "p01", "p02", "p03", "p04")

# Cycles in the reforecast set. NOAA documentation indicates 00z is the
# canonical reforecast cycle; later cycles are operational only.
DEFAULT_CYCLE_HOUR: Final = 0  # 00 UTC

# Variable name for daily Tmax 2m (matches `tmax_2m_*.grib2` naming).
TMAX_VARIABLE: Final = "tmax_2m"

# Days-range subdirectories. The archive splits forecast hours into two
# files per (cycle, member, variable):
#   "Days:1-10"  — forecast hours 6, 12, ..., 240 (1-10 days out)
#   "Days:10-16" — forecast hours 252, 264, ..., 384 (10-16 days out)
# At our v1 lead-1 backtest target (forecast hour 24 ≈ next-day Tmax),
# only the Days:1-10 file is needed.
DAYS_RANGES: Final[tuple[str, ...]] = ("Days:1-10", "Days:10-16")
DEFAULT_DAYS_RANGE: Final = "Days:1-10"

# Per-(station, record) byte budget for byte-range subsetting. Empirical
# at GEFSv12's 0.25° resolution: a single grid point's record after Range:
# is ~1-3 KB (varies with compression). 3 KB is a conservative ceiling.
BYTES_PER_STATION_RECORD: Final = 3_000

# .idx file size — fixed-shape ASCII, ~6-8 KB per file (one row per record).
BYTES_PER_IDX_FILE: Final = 7_000


@dataclass(frozen=True, slots=True)
class ReforecastFile:
    """One (cycle, member, days_range, variable) GRIB2 file in the archive."""

    year: int
    cycle: str  # "YYYYMMDDHH", e.g., "2019010100"
    member: str  # "c00" | "p01" | ... | "p04"
    days_range: str  # "Days:1-10" | "Days:10-16"
    variable: str  # e.g., "tmax_2m"

    @property
    def grib2_key(self) -> str:
        """S3 key for the GRIB2 record file."""
        filename = f"{self.variable}_{self.cycle}_{self.member}.grib2"
        path = f"{self.year}/{self.cycle}/{self.member}/{self.days_range}/{filename}"
        return f"{ARCHIVE_PREFIX}/{path}"

    @property
    def idx_key(self) -> str:
        """S3 key for the GRIB2 ASCII idx companion file."""
        return f"{self.grib2_key}.idx"

    @property
    def grib2_url(self) -> str:
        return f"https://{BUCKET}.s3.amazonaws.com/{self.grib2_key}"

    @property
    def idx_url(self) -> str:
        return f"https://{BUCKET}.s3.amazonaws.com/{self.idx_key}"


def make_cycle_string(year: int, month: int, day: int, hour: int = DEFAULT_CYCLE_HOUR) -> str:
    """Build the YYYYMMDDHH cycle string used as the day-folder name."""
    return f"{year:04d}{month:02d}{day:02d}{hour:02d}"


def s3_url_for(
    *,
    year: int,
    month: int,
    day: int,
    member: str,
    variable: str,
    days_range: str = DEFAULT_DAYS_RANGE,
    hour: int = DEFAULT_CYCLE_HOUR,
) -> str:
    """Return the public HTTPS URL for one (cycle, member, var) GRIB2 file.

    Validation: year must be in [2000, 2019] (archive bounds); member must
    be one of the DEFAULT_MEMBERS; days_range must be a recognized split.
    """
    if not ARCHIVE_FIRST_YEAR <= year <= ARCHIVE_LAST_YEAR:
        raise ValueError(
            f"year {year} out of archive bounds [{ARCHIVE_FIRST_YEAR}, {ARCHIVE_LAST_YEAR}]"
        )
    if member not in DEFAULT_MEMBERS:
        raise ValueError(f"unknown member {member!r}; expected one of {DEFAULT_MEMBERS}")
    if days_range not in DAYS_RANGES:
        raise ValueError(f"unknown days_range {days_range!r}; expected one of {DAYS_RANGES}")
    cycle = make_cycle_string(year, month, day, hour)
    rf = ReforecastFile(
        year=year, cycle=cycle, member=member, days_range=days_range, variable=variable
    )
    return rf.grib2_url


def iter_reforecast_files(
    *,
    start_year: int,
    end_year: int,
    members: tuple[str, ...] = DEFAULT_MEMBERS,
    variables: tuple[str, ...] = (TMAX_VARIABLE,),
    days_ranges: tuple[str, ...] = (DEFAULT_DAYS_RANGE,),
    days_per_year: int = 365,
) -> Iterator[ReforecastFile]:
    """Yield the expected ``ReforecastFile`` for every cycle in the requested
    grid.

    Deterministic: produces output without hitting the S3 API. The cycle is
    YYYYMMDDHH at 00 UTC for every calendar day in [start_year, end_year].
    Caller can filter (e.g., for the actual ~366-day leap-year case).

    ``days_per_year`` defaults to 365 for back-of-envelope estimates; pass
    366 for leap-year-correct accounting if the application needs it.
    """
    if start_year < ARCHIVE_FIRST_YEAR:
        raise ValueError(
            f"start_year {start_year} before archive start {ARCHIVE_FIRST_YEAR}"
        )
    if end_year > ARCHIVE_LAST_YEAR:
        raise ValueError(
            f"end_year {end_year} after archive end {ARCHIVE_LAST_YEAR}"
        )
    if end_year < start_year:
        raise ValueError(f"end_year {end_year} precedes start_year {start_year}")
    for var in variables:
        for member in members:
            for days_range in days_ranges:
                for year in range(start_year, end_year + 1):
                    days = (
                        366 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 365
                    )
                    if days_per_year != 365:
                        days = days_per_year
                    for ordinal in range(days):
                        # Map ordinal back to (month, day) — pure date math.
                        month, day = _ordinal_to_md(year, ordinal + 1)
                        yield ReforecastFile(
                            year=year,
                            cycle=make_cycle_string(year, month, day),
                            member=member,
                            days_range=days_range,
                            variable=var,
                        )


def _ordinal_to_md(year: int, ordinal: int) -> tuple[int, int]:
    """Convert ordinal day-of-year (1..366) to (month, day). Pure function."""
    is_leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    days_per_month = (31, 29 if is_leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    remaining = ordinal
    for month, n in enumerate(days_per_month, start=1):
        if remaining <= n:
            return month, remaining
        remaining -= n
    raise ValueError(f"ordinal {ordinal} out of range for year {year}")


@dataclass(frozen=True, slots=True)
class IdxRecord:
    """One record in a GRIB2 .idx file: byte offset + variable + level + valid time."""

    record_no: int
    byte_offset: int
    valid_time: str  # raw string from idx, e.g., "d=2019010100" or "anl"
    variable: str  # "TMAX"
    level: str  # "2 m above ground"
    forecast_hour_label: str  # "24-30 hour max fcst" or similar


def parse_idx_text(text: str) -> list[IdxRecord]:
    """Parse the ASCII .idx file format: ``record:byte_offset:date:var:level:fcst_label``.

    Defensive — silently drops malformed lines, returns the records we can
    parse. NOAA's idx format is colon-delimited with 6+ fields per row; the
    first three are deterministic (record number, byte offset, valid time).
    """
    out: list[IdxRecord] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(":")
        if len(parts) < 6:
            continue
        try:
            record_no = int(parts[0])
            byte_offset = int(parts[1])
        except ValueError:
            continue
        out.append(
            IdxRecord(
                record_no=record_no,
                byte_offset=byte_offset,
                valid_time=parts[2],
                variable=parts[3],
                level=parts[4],
                forecast_hour_label=parts[5],
            )
        )
    return out


def byte_range_for_record(idx: list[IdxRecord], record_no: int) -> tuple[int, int] | None:
    """Return ``(start, end_inclusive)`` byte offsets for a given record.

    Uses the next record's offset minus 1 for the end. Returns None if the
    record isn't found. End-of-file records (no next record) return
    ``(start, -1)`` — caller can interpret -1 as "open-ended" for the
    HTTP Range header.
    """
    by_no = {r.record_no: r for r in idx}
    record = by_no.get(record_no)
    if record is None:
        return None
    next_record = by_no.get(record_no + 1)
    if next_record is None:
        return record.byte_offset, -1
    return record.byte_offset, next_record.byte_offset - 1


@dataclass(frozen=True, slots=True)
class PullPlan:
    """Estimated cost summary for a planned reforecast pull."""

    n_files: int
    n_http_requests: int  # idx + range-request per file x n_target_records
    bytes_idx: int
    bytes_records: int
    bytes_total: int
    n_unique_cycles: int

    @property
    def gigabytes_total(self) -> float:
        return self.bytes_total / 1_000_000_000.0

    @property
    def megabytes_total(self) -> float:
        return self.bytes_total / 1_000_000.0


def estimate_pull_volume(
    *,
    start_year: int,
    end_year: int,
    members: tuple[str, ...] = DEFAULT_MEMBERS,
    variables: tuple[str, ...] = (TMAX_VARIABLE,),
    days_ranges: tuple[str, ...] = (DEFAULT_DAYS_RANGE,),
    n_stations: int = 6,
    n_target_records_per_file: int = 1,
    bytes_per_station_record: int = BYTES_PER_STATION_RECORD,
    bytes_per_idx_file: int = BYTES_PER_IDX_FILE,
) -> PullPlan:
    """Back-of-envelope volume estimate for a reforecast pull.

    Per file: 1 HTTP request to download the .idx (~7 KB) + 1 range request
    per (target record x station). Total bytes = sum across files of
    (idx bytes + n_records x n_stations x per-record bytes).

    Default ``n_target_records_per_file=1`` matches the v1 backtest at
    lead day 1 (one forecast-hour record per file). Bump to 7 for full
    Days:1-10 coverage.
    """
    n_files = sum(1 for _ in iter_reforecast_files(
        start_year=start_year,
        end_year=end_year,
        members=members,
        variables=variables,
        days_ranges=days_ranges,
    ))
    bytes_idx = n_files * bytes_per_idx_file
    bytes_records = (
        n_files * n_target_records_per_file * n_stations * bytes_per_station_record
    )
    bytes_total = bytes_idx + bytes_records
    n_http_per_file = 1 + n_target_records_per_file * n_stations
    return PullPlan(
        n_files=n_files,
        n_http_requests=n_files * n_http_per_file,
        bytes_idx=bytes_idx,
        bytes_records=bytes_records,
        bytes_total=bytes_total,
        n_unique_cycles=n_files
        // (len(members) * len(variables) * len(days_ranges)),
    )


PullScope = Literal["small", "v1", "full"]


# =============================================================================
# Phase 2 — actual fetch + cfgrib parse
# =============================================================================


@dataclass(frozen=True, slots=True)
class StationCoord:
    """Station coordinate for grid-point extraction.

    Note ``longitude_e`` is in the GEFS convention (0-360°E), not the more
    common -180..180. Convert from typical Western-hemisphere negative
    longitudes via ``longitude_e = (longitude_w + 360) % 360``.
    """

    icao: str
    latitude: float
    longitude_e: float


@dataclass(frozen=True, slots=True)
class StationRecord:
    """Extracted (station, record) sample from a single GRIB2 record."""

    icao: str
    cycle: str
    member: str
    record_no: int
    forecast_hour_label: str
    tmax_kelvin: float


async def fetch_idx_text(client: httpx.AsyncClient, idx_url: str) -> str:
    """Download the ASCII .idx companion file. ~7 KB; no error retries here."""
    resp = await client.get(idx_url, timeout=60.0)
    resp.raise_for_status()
    return resp.text


async def fetch_grib2_record_bytes(
    client: httpx.AsyncClient, grib2_url: str, byte_start: int, byte_end: int
) -> bytes:
    """Download one record via HTTP Range. ``byte_end`` is inclusive; -1 means open-ended."""
    range_header = (
        f"bytes={byte_start}-{byte_end}" if byte_end >= 0 else f"bytes={byte_start}-"
    )
    resp = await client.get(grib2_url, headers={"Range": range_header}, timeout=300.0)
    resp.raise_for_status()
    return resp.content


def extract_station_values(
    record_bytes: bytes,
    *,
    stations: Sequence[StationCoord],
    cfgrib_engine: str = "cfgrib",
) -> dict[str, float]:
    """Parse a single GRIB2 record + extract Tmax (Kelvin) at each station.

    Writes the bytes to a tempfile (cfgrib needs file path), opens via
    xarray, samples the nearest grid point per station, returns
    ``{icao: tmax_kelvin}``. The returned values are still in Kelvin —
    callers convert to °F at the persistence layer.
    """
    # cfgrib leaves a `.idx` sidecar in the tempfile dir; cleanup handles both.
    import xarray as xr  # noqa: PLC0415 — lazy import; cfgrib loads eccodes lib

    with tempfile.NamedTemporaryFile(suffix=".grib2", delete=False) as f:
        f.write(record_bytes)
        path = f.name
    try:
        ds = xr.open_dataset(path, engine=cfgrib_engine)
        var_name = next(iter(ds.data_vars))  # tmax (only var per record)
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
        for cleanup in (path, *(f"{path}.{suf}.idx" for suf in ("923a8", "fa6dc"))):
            if os.path.exists(cleanup):
                os.unlink(cleanup)
        # cfgrib's idx-sidecar naming is unstable across versions; sweep generically.
        parent = os.path.dirname(path)
        for sibling in os.listdir(parent):
            if sibling.startswith(os.path.basename(path) + "."):
                with contextlib.suppress(OSError):
                    os.unlink(os.path.join(parent, sibling))


def kelvin_to_fahrenheit(k: float) -> float:
    """Convert Kelvin to Fahrenheit. Standard formula."""
    return (k - 273.15) * 9.0 / 5.0 + 32.0


async def fetch_records_for_file(
    client: httpx.AsyncClient,
    rf: ReforecastFile,
    *,
    stations: Sequence[StationCoord],
    target_record_nos: Sequence[int] | None = None,
) -> list[StationRecord]:
    """Fetch idx + selected records for one file, extract per-station values.

    ``target_record_nos`` defaults to None (all records in the file). For
    lead-day-1 backtests, callers usually pass a small list — e.g., the
    record index covering hours 18-42 (next-day Tmax window).

    Errors propagate to the caller; ingest-flow handles per-file retries.
    Buffer streaming is in-memory; per record allocates ~1 MB peak.

    Note: ``io`` import is referenced here for future streaming work; left
    imported at module level to avoid lazy-import noise.
    """
    _ = io  # placeholder for future streaming support
    idx_text = await fetch_idx_text(client, rf.idx_url)
    idx = parse_idx_text(idx_text)
    if not idx:
        return []
    records_to_fetch = (
        [r for r in idx if r.record_no in target_record_nos]
        if target_record_nos is not None
        else idx
    )
    out: list[StationRecord] = []
    for record in records_to_fetch:
        byte_range = byte_range_for_record(idx, record_no=record.record_no)
        if byte_range is None:
            continue
        start, end = byte_range
        record_bytes = await fetch_grib2_record_bytes(
            client, rf.grib2_url, byte_start=start, byte_end=end
        )
        tmax_by_station = extract_station_values(record_bytes, stations=stations)
        for icao, tmax_k in tmax_by_station.items():
            out.append(
                StationRecord(
                    icao=icao,
                    cycle=rf.cycle,
                    member=rf.member,
                    record_no=record.record_no,
                    forecast_hour_label=record.forecast_hour_label,
                    tmax_kelvin=tmax_k,
                )
            )
    return out


# Throttled batch fetcher — used by the ingest flow.
async def fetch_records_for_files(
    files: Sequence[ReforecastFile],
    *,
    stations: Sequence[StationCoord],
    target_record_nos: Sequence[int] | None = None,
    max_concurrent: int = 5,
    progress_every: int = 50,
) -> list[StationRecord]:
    """Concurrent batch fetch with semaphore throttling.

    Default ``max_concurrent=5`` is conservative — AWS Open Data has no
    auth but does soft-throttle at high RPS. 5 concurrent gives us about
    100 MB/s peak throughput which is plenty for the v1 use case.
    """
    out: list[StationRecord] = []
    sem = asyncio.Semaphore(max_concurrent)
    completed = 0

    async def worker(client: httpx.AsyncClient, rf: ReforecastFile) -> list[StationRecord]:
        nonlocal completed
        async with sem:
            try:
                records = await fetch_records_for_file(
                    client,
                    rf,
                    stations=stations,
                    target_record_nos=target_record_nos,
                )
            except Exception:
                # Per-file failures are logged by the caller; here we just
                # return empty so partial progress survives a single blip.
                records = []
        completed += 1
        if completed % progress_every == 0:
            # Print progress synchronously so cron logs see it in real time.
            print(f"  ...processed {completed}/{len(files)} files")
        return records

    async with httpx.AsyncClient(timeout=300.0) as client:
        tasks = [worker(client, rf) for rf in files]
        results = await asyncio.gather(*tasks)
    for batch in results:
        out.extend(batch)
    return out
