"""GEFSv12 reforecast (NOAA Open Data) — phase 1 scaffold.

Pure functions for navigating the `s3://noaa-gefs-retrospective` archive
(20-year, 5-member, 1-cycle/day reforecast set frozen at GEFSv12). This
module deliberately ships **without** GRIB2 parsing — phase 2 adds
``cfgrib``/``xarray``/``eccodes`` after explicit user signoff per CLAUDE.md
§9. See ``docs/research/GEFSV12-REFORECAST-INTEGRATION.md`` for the full
scoping.

What's here in phase 1:

- **URL builder** — construct S3 paths for any (year, cycle, member,
  days-range, variable). Pure function, no I/O.
- **Key iterator** — yield expected S3 keys across a date/member/variable
  grid without listing the bucket (deterministic from inputs).
- **Idx parser** — parse the ASCII ``.idx`` companion file format that
  ships alongside each ``.grib2``. Returns byte-offset ranges per record.
- **Volume estimator** — back-of-envelope on bytes pulled given a config,
  using ~3 KB per (station, record) for byte-range subsetting.

What's NOT here (phase 2):

- Actual S3 fetching (just URL strings here).
- GRIB2 record parsing (needs ``cfgrib``/``eccodes``).
- DuckDB persistence (defer until phase 2).

CLI: ``kq plan-gefsv12-pull`` invokes the volume estimator + key iterator
to print a dry-run summary. No data is downloaded.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Final, Literal

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
