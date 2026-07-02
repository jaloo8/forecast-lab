"""Tests for the Phase 1 GEFSv12 reforecast scaffolding + batch fetcher."""

from __future__ import annotations

import asyncio

import pytest

from kq.clients import gefs_reforecast as gefs_mod
from kq.clients.gefs_reforecast import (
    ARCHIVE_FIRST_YEAR,
    ARCHIVE_LAST_YEAR,
    BUCKET,
    DEFAULT_MEMBERS,
    TMAX_VARIABLE,
    IdxRecord,
    ReforecastFile,
    StationCoord,
    StationRecord,
    byte_range_for_record,
    estimate_pull_volume,
    fetch_records_for_files,
    iter_reforecast_files,
    make_cycle_string,
    parse_idx_text,
    s3_url_for,
)

# --------------------------- URL builder ---------------------------


def test_s3_url_for_well_formed() -> None:
    """URL matches the verified S3 path structure (2026-04-30 spike)."""
    url = s3_url_for(year=2019, month=1, day=1, member="c00", variable=TMAX_VARIABLE)
    assert url == (
        f"https://{BUCKET}.s3.amazonaws.com/GEFSv12/reforecast/2019/2019010100/c00/"
        f"Days:1-10/{TMAX_VARIABLE}_2019010100_c00.grib2"
    )


def test_s3_url_for_rejects_year_outside_archive() -> None:
    with pytest.raises(ValueError, match="archive bounds"):
        s3_url_for(year=2024, month=1, day=1, member="c00", variable=TMAX_VARIABLE)
    with pytest.raises(ValueError, match="archive bounds"):
        s3_url_for(year=1999, month=1, day=1, member="c00", variable=TMAX_VARIABLE)


def test_s3_url_for_rejects_unknown_member() -> None:
    with pytest.raises(ValueError, match="unknown member"):
        s3_url_for(year=2019, month=1, day=1, member="p99", variable=TMAX_VARIABLE)


def test_s3_url_for_rejects_unknown_days_range() -> None:
    with pytest.raises(ValueError, match="days_range"):
        s3_url_for(
            year=2019,
            month=1,
            day=1,
            member="c00",
            variable=TMAX_VARIABLE,
            days_range="Days:7-12",
        )


def test_make_cycle_string_zero_pads() -> None:
    assert make_cycle_string(2010, 3, 5, 0) == "2010030500"
    assert make_cycle_string(2019, 12, 31, 18) == "2019123118"


# --------------------------- ReforecastFile dataclass ---------------------------


def test_reforecast_file_keys_match_url() -> None:
    rf = ReforecastFile(
        year=2019,
        cycle="2019010100",
        member="c00",
        days_range="Days:1-10",
        variable=TMAX_VARIABLE,
    )
    assert rf.grib2_key.endswith(f"/{TMAX_VARIABLE}_2019010100_c00.grib2")
    assert rf.idx_key == rf.grib2_key + ".idx"
    assert rf.idx_url == rf.grib2_url + ".idx"


# --------------------------- key iterator ---------------------------


def test_iter_reforecast_files_count_matches_grid() -> None:
    """1 year * 5 members * 1 var * 1 days_range * 365 days = 1825."""
    files = list(
        iter_reforecast_files(
            start_year=2010,
            end_year=2010,
            members=DEFAULT_MEMBERS,
            variables=(TMAX_VARIABLE,),
            days_per_year=365,
        )
    )
    assert len(files) == 5 * 365
    # Multi-year sanity: no overlaps in (year, cycle, member, var) keys.
    files_2yr = list(
        iter_reforecast_files(
            start_year=2010,
            end_year=2011,
            members=DEFAULT_MEMBERS,
            variables=(TMAX_VARIABLE,),
            days_per_year=365,
        )
    )
    keys = {f.grib2_key for f in files_2yr}
    assert len(keys) == len(files_2yr)


def test_iter_reforecast_files_handles_leap_year() -> None:
    """2012 is a leap year — should produce 366 files per (member, var)."""
    files = list(
        iter_reforecast_files(
            start_year=2012,
            end_year=2012,
            members=("c00",),
            variables=(TMAX_VARIABLE,),
        )
    )
    assert len(files) == 366


def test_iter_reforecast_files_366_on_non_leap_year_does_not_crash() -> None:
    """2026-07-01 audit (Tier 2 low): the docstring recommends passing
    days_per_year=366 for leap-year-correct accounting, but doing so on a
    non-leap year used to iterate to a nonexistent Feb-29-shifted ordinal
    and crash. 366 is a CAP, clamped to the year's real length."""
    files = list(
        iter_reforecast_files(
            start_year=2011,  # non-leap
            end_year=2011,
            members=("c00",),
            variables=(TMAX_VARIABLE,),
            days_per_year=366,
        )
    )
    assert len(files) == 365
    cycles = {f.cycle for f in files}
    assert "2011022800" in cycles
    assert "2011022900" not in cycles  # no fabricated Feb 29
    assert "2011123100" in cycles  # full year covered


def test_iter_reforecast_files_366_on_leap_year_includes_feb_29() -> None:
    files = list(
        iter_reforecast_files(
            start_year=2012,
            end_year=2012,
            members=("c00",),
            variables=(TMAX_VARIABLE,),
            days_per_year=366,
        )
    )
    assert len(files) == 366
    assert "2012022900" in {f.cycle for f in files}


def test_iter_reforecast_files_366_mixed_years() -> None:
    """A leap + non-leap span yields 366 + 365 without crashing."""
    files = list(
        iter_reforecast_files(
            start_year=2012,
            end_year=2013,
            members=("c00",),
            variables=(TMAX_VARIABLE,),
            days_per_year=366,
        )
    )
    assert len(files) == 366 + 365


def test_iter_reforecast_files_validates_bounds() -> None:
    with pytest.raises(ValueError, match="archive start"):
        list(iter_reforecast_files(start_year=1999, end_year=2000))
    with pytest.raises(ValueError, match="archive end"):
        list(iter_reforecast_files(start_year=2018, end_year=2025))
    with pytest.raises(ValueError, match="precedes"):
        list(iter_reforecast_files(start_year=2015, end_year=2010))


def test_iter_full_archive_count() -> None:
    """Smoke test: 20 years * 5 members * ~365.25 days ≈ 36,525 files for tmax."""
    files = list(
        iter_reforecast_files(
            start_year=ARCHIVE_FIRST_YEAR,
            end_year=ARCHIVE_LAST_YEAR,
            members=DEFAULT_MEMBERS,
            variables=(TMAX_VARIABLE,),
        )
    )
    # 20 years x 5 members x ~365.25 ~ 36,525
    assert 36_500 <= len(files) <= 36_550


# --------------------------- idx parser ---------------------------


def test_parse_idx_text_well_formed_record() -> None:
    """Standard NOAA .idx line: ``record:offset:date:var:level:fcst_label``."""
    text = (
        "1:0:d=2019010100:TMAX:2 m above ground:24-30 hour max fcst:\n"
        "2:1234:d=2019010100:TMAX:2 m above ground:30-36 hour max fcst:\n"
    )
    records = parse_idx_text(text)
    assert len(records) == 2
    assert records[0] == IdxRecord(
        record_no=1,
        byte_offset=0,
        valid_time="d=2019010100",
        variable="TMAX",
        level="2 m above ground",
        forecast_hour_label="24-30 hour max fcst",
    )
    assert records[1].byte_offset == 1234


def test_parse_idx_text_drops_malformed_lines() -> None:
    """Defensive parsing: short or non-numeric lines are silently skipped."""
    text = (
        "1:0:d=2019010100:TMAX:2 m above ground:24-30 hour max fcst:\n"
        "garbage line with no colons\n"
        ":not:a:number\n"
        "two-fields:only\n"
    )
    records = parse_idx_text(text)
    assert len(records) == 1
    assert records[0].record_no == 1


def test_parse_idx_text_empty_input_returns_empty() -> None:
    assert parse_idx_text("") == []
    assert parse_idx_text("\n\n   \n") == []


# --------------------------- byte-range helper ---------------------------


def test_byte_range_for_record_spans_to_next() -> None:
    idx = [
        IdxRecord(1, 0, "d=2019", "TMAX", "2 m", "fc"),
        IdxRecord(2, 100, "d=2019", "TMAX", "2 m", "fc"),
        IdxRecord(3, 250, "d=2019", "TMAX", "2 m", "fc"),
    ]
    # Record 1: bytes [0, 99] inclusive.
    assert byte_range_for_record(idx, record_no=1) == (0, 99)
    # Record 2: bytes [100, 249].
    assert byte_range_for_record(idx, record_no=2) == (100, 249)
    # Record 3 has no next: returns (250, -1) for "open-ended".
    assert byte_range_for_record(idx, record_no=3) == (250, -1)


def test_byte_range_for_unknown_record_returns_none() -> None:
    idx = [IdxRecord(1, 0, "d", "TMAX", "2 m", "fc")]
    assert byte_range_for_record(idx, record_no=99) is None


# --------------------------- volume estimator ---------------------------


def test_estimate_pull_volume_grows_with_archive_window() -> None:
    """Doubling the year window roughly doubles the byte budget."""
    one_year = estimate_pull_volume(start_year=2010, end_year=2010)
    two_years = estimate_pull_volume(start_year=2010, end_year=2011)
    assert two_years.n_files == pytest.approx(2 * one_year.n_files, rel=0.01)
    # Bytes scale linearly with file count.
    assert two_years.bytes_total / one_year.bytes_total == pytest.approx(2.0, rel=0.05)


def test_estimate_pull_volume_full_archive_under_2gb() -> None:
    """Sanity: full 20-year archive at 1 record/file is ~660 MB — well under 2 GB."""
    plan = estimate_pull_volume(
        start_year=ARCHIVE_FIRST_YEAR,
        end_year=ARCHIVE_LAST_YEAR,
        n_stations=6,
        n_target_records_per_file=1,
    )
    # Order of magnitude check; precise value depends on per-record assumption.
    assert 0.3 < plan.gigabytes_total < 2.0


def test_estimate_pull_volume_scales_with_records_per_file() -> None:
    """Pulling 7 forecast hours per file = 7x the range bytes (idx unchanged)."""
    one_record = estimate_pull_volume(start_year=2010, end_year=2010)
    seven_records = estimate_pull_volume(
        start_year=2010, end_year=2010, n_target_records_per_file=7
    )
    # idx bytes are constant per file (one fetch); range bytes scale 7x.
    assert seven_records.bytes_idx == one_record.bytes_idx
    assert seven_records.bytes_records == pytest.approx(7 * one_record.bytes_records)


# --------------------------- batch fetcher failure accounting ---------------------------


def _rf(day: int) -> ReforecastFile:
    return ReforecastFile(
        year=2019,
        cycle=make_cycle_string(2019, 1, day),
        member="c00",
        days_range="Days:1-10",
        variable=TMAX_VARIABLE,
    )


_KAUS = StationCoord(icao="KAUS", latitude=30.19, longitude_e=262.33)


def test_fetch_records_for_files_collects_per_file_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """2026-07-01 audit (Tier 2 high): a failing file must surface in
    ``BatchFetchResult.failures`` — not silently become an empty list that
    leaves an undetectable hole in the training pull."""
    good, bad = _rf(1), _rf(2)

    async def fake_fetch_one(
        _client: object,
        rf: ReforecastFile,
        *,
        stations: object,
        target_record_nos: object = None,
    ) -> list[StationRecord]:
        if rf is bad:
            raise RuntimeError("simulated S3 blip")
        return [StationRecord("KAUS", rf.cycle, rf.member, 9, "24-27 hour max fcst", 285.0)]

    monkeypatch.setattr(gefs_mod, "fetch_records_for_file", fake_fetch_one)
    result = asyncio.run(fetch_records_for_files([good, bad], stations=[_KAUS]))

    assert len(result.records) == 1
    assert result.records[0].cycle == good.cycle
    assert result.n_failed == 1
    assert result.failures[0].file == bad
    assert "simulated S3 blip" in result.failures[0].error


def test_fetch_records_for_files_all_success_has_no_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_fetch_one(
        _client: object,
        rf: ReforecastFile,
        *,
        stations: object,
        target_record_nos: object = None,
    ) -> list[StationRecord]:
        return [StationRecord("KAUS", rf.cycle, rf.member, 9, "24-27 hour max fcst", 285.0)]

    monkeypatch.setattr(gefs_mod, "fetch_records_for_file", fake_fetch_one)
    result = asyncio.run(fetch_records_for_files([_rf(1), _rf(2)], stations=[_KAUS]))
    assert result.n_failed == 0
    assert result.failures == []
    assert len(result.records) == 2
