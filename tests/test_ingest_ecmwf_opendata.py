"""Tests for the ECMWF Open Data ingest flow.

Coverage (rewritten for the 2026-07-01 audit fixes):
- ``latest_published_cycle`` uses a realistic ~8.5h open-data publish
  buffer (open data lands at the END of the real-time dissemination
  schedule, ~7.5-8h after init — not the 1-2h the flow once assumed).
- ``step_hours_for_cycle`` / ``valid_date_for_cycle`` pin the mx2t24
  date attribution: the field is a max over the 24h ENDING at the valid
  time, so a day-aligned step covers ``cycle.date() + 1`` — NOT the
  valid-time date (the off-by-one).
- ``fetch_and_upsert`` genuinely walks back up to 4 prior cycles on
  404s (the docstring-promised lookback that used to be dead code).
- End-to-end round-trips go through ``httpx.MockTransport`` (no live
  ECMWF fetch) plus a patched ``xarray.open_dataset`` (no real GRIB2
  fixture).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import duckdb
import httpx
import pytest

from kq.clients.stations import STATIONS
from kq.flows.ingest_ecmwf_opendata import (
    DEFAULT_PUBLISH_BUFFER_HOURS,
    LEAD_1_STEP_HOURS,
    MODEL_TAG,
    SHORT_NAME_MX2T24,
    _build_forecast_rows,
    fetch_and_upsert,
    latest_published_cycle,
    step_hours_for_cycle,
    valid_date_for_cycle,
)
from kq.storage.duckdb_store import bootstrap

# --------------------- latest_published_cycle ---------------------


def test_latest_published_cycle_picks_00z_at_09z() -> None:
    """00z open data lands ~07:30-08:00 UTC; at 09:00 with the 8.5h
    buffer, 00z is the newest plausibly-published cycle."""
    now = datetime(2026, 5, 3, 9, 0, tzinfo=UTC)
    cycle = latest_published_cycle(now=now)
    assert cycle.hour == 0
    assert cycle.date() == now.date()


def test_latest_published_cycle_does_not_pick_unpublished_00z_at_03z() -> None:
    """The old 2.5h buffer picked 00z at 03:00 UTC — five hours before
    its open data publishes (2026-07-01 audit: 'picks unpublished
    cycles'). The realistic buffer rolls back to yesterday's 18z."""
    now = datetime(2026, 5, 3, 3, 0, tzinfo=UTC)
    cycle = latest_published_cycle(now=now)
    assert cycle.hour == 18
    assert cycle.date() == (now - timedelta(days=1)).date()


def test_latest_published_cycle_picks_06z_at_15z() -> None:
    now = datetime(2026, 5, 3, 15, 0, tzinfo=UTC)
    cycle = latest_published_cycle(now=now)
    assert cycle.hour == 6
    assert cycle.date() == now.date()


def test_latest_published_cycle_picks_12z_at_21z() -> None:
    now = datetime(2026, 5, 3, 21, 0, tzinfo=UTC)
    cycle = latest_published_cycle(now=now)
    assert cycle.hour == 12


def test_latest_published_cycle_never_yields_cycle_younger_than_buffer() -> None:
    """Property sweep across a full day of tick times."""
    for hour in range(24):
        for minute in (0, 30):
            now = datetime(2026, 5, 3, hour, minute, tzinfo=UTC)
            cycle = latest_published_cycle(now=now)
            age_h = (now - cycle).total_seconds() / 3600.0
            assert age_h >= DEFAULT_PUBLISH_BUFFER_HOURS, (now, cycle)
            assert cycle.hour in (0, 6, 12, 18)


def test_latest_published_cycle_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        latest_published_cycle(now=datetime(2026, 5, 3, 3, 0))


def test_latest_published_cycle_rejects_negative_buffer() -> None:
    with pytest.raises(ValueError, match="publish_buffer_hours"):
        latest_published_cycle(
            now=datetime(2026, 5, 3, 3, 0, tzinfo=UTC), publish_buffer_hours=-1.0
        )


def test_default_publish_buffer_pinned() -> None:
    """Open data publishes ~7.5-8h after init (end of the real-time
    dissemination schedule); 8.5h adds margin. Pin so changes are
    deliberate."""
    assert DEFAULT_PUBLISH_BUFFER_HOURS == 8.5


# --------------------- mx2t24 date attribution ---------------------


def test_step_hours_for_cycle_is_day_aligned() -> None:
    """step = 48 - init_hour makes the trailing-24h window end at the
    second UTC midnight after the init date, for every cycle."""
    expected = {0: 48, 6: 42, 12: 36, 18: 30}
    for hour, step in expected.items():
        cycle = datetime(2026, 5, 3, hour, tzinfo=UTC)
        assert step_hours_for_cycle(cycle) == step
        # Window ENDS at the valid time; window START is 24h earlier == D+1 00z.
        window_start = cycle + timedelta(hours=step - 24)
        assert window_start == datetime(2026, 5, 4, 0, 0, tzinfo=UTC), hour


def test_step_hours_for_cycle_rejects_unpublished_hour() -> None:
    with pytest.raises(ValueError, match="not in published cycles"):
        step_hours_for_cycle(datetime(2026, 5, 3, 3, tzinfo=UTC))


def test_valid_date_is_the_day_covered_not_the_valid_time_date() -> None:
    """THE off-by-one (2026-07-01 audit, Tier 2 high): mx2t24 at a
    day-aligned step from day-D init covers calendar day D+1; the old
    code stored ``(cycle + step).date()`` = D+2."""
    for hour in (0, 6, 12, 18):
        cycle = datetime(2026, 5, 3, hour, tzinfo=UTC)
        vd = valid_date_for_cycle(cycle)
        assert vd == date(2026, 5, 4), hour  # tomorrow, every cycle
        old_wrong = (cycle + timedelta(hours=step_hours_for_cycle(cycle))).date()
        assert vd == old_wrong - timedelta(days=1)


def test_lead_1_step_hours_is_pinned() -> None:
    """Pin the 00z anchor step — 48h is what makes (00z init, step-24h)
    span the full next UTC calendar day. Other cycles derive from it."""
    assert LEAD_1_STEP_HOURS == 48


def test_short_name_mx2t24_is_pinned() -> None:
    """Pin the WMO short name -- changing this is a semantic change to
    what we extract (e.g. swapping mx2t24 for mx2t6 changes the
    aggregation window)."""
    assert SHORT_NAME_MX2T24 == "mx2t24"


# --------------------- _build_forecast_rows ---------------------


def test_build_forecast_rows_tags_model_and_converts_kelvin() -> None:
    cycle = datetime(2026, 5, 3, 0, 0, tzinfo=UTC)
    valid_date = valid_date_for_cycle(cycle)
    as_of = cycle + timedelta(hours=9)
    rows = _build_forecast_rows(
        station_kelvin={"KLAX": 290.0, "KNYC": 280.0},
        cycle=cycle,
        valid_date=valid_date,
        as_of=as_of,
    )
    assert len(rows) == 2
    by_icao = {r.station: r for r in rows}
    # KLAX 290K = 62.33 F; KNYC 280K = 44.33 F.
    assert by_icao["KLAX"].forecast_high_f == pytest.approx(62.33, abs=0.05)
    assert by_icao["KNYC"].forecast_high_f == pytest.approx(44.33, abs=0.05)
    for row in rows:
        assert row.model == MODEL_TAG
        assert row.member == 0
        assert row.forecast_low_f is None  # mx2t24 is daily MAX only
        # Naive UTC for DuckDB.
        assert row.as_of.tzinfo is None
        assert row.run_time.tzinfo is None
    assert all(r.valid_date == date(2026, 5, 4) for r in rows)


def test_build_forecast_rows_empty_input_is_empty_output() -> None:
    cycle = datetime(2026, 5, 3, 0, 0, tzinfo=UTC)
    rows = _build_forecast_rows(
        station_kelvin={},
        cycle=cycle,
        valid_date=cycle.date(),
        as_of=cycle,
    )
    assert rows == []


# --------------------- end-to-end with MockTransport + patched xarray ---------------------


def _stub_dataset(kelvin_value: float = 290.0) -> MagicMock:
    """Build a minimal MagicMock that satisfies the ``ds[var].sel(...)``
    code path without a real xarray.Dataset / GRIB2. (The ECMWF 0.25 deg
    open-data grid is a regular lat/lon grid with 1-D index coords, so
    ``.sel(..., method='nearest')`` is valid there — unlike NBM's
    Lambert grid.)"""
    fake_var = MagicMock()
    fake_var.sel.return_value = MagicMock(__float__=lambda _self: kelvin_value)
    fake_ds = MagicMock()
    fake_ds.data_vars = {"mx2t24": fake_var}
    fake_ds.__getitem__.side_effect = lambda _key: fake_var
    return fake_ds


@pytest.mark.asyncio
async def test_fetch_and_upsert_round_trip(tmp_path: Path) -> None:
    """Mock the HTTP layer + xarray and verify rows land in DuckDB
    tagged with ``MODEL_TAG`` under the UTC day the mx2t24 window
    actually covers (init date + 1 — NOT the valid-time date)."""
    db = tmp_path / "wx.duckdb"
    bootstrap(db)
    cycle = datetime(2026, 5, 3, 0, 0, tzinfo=UTC)

    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, content=b"stand-in grib2 bytes")

    transport = httpx.MockTransport(handler)
    fake_ds = _stub_dataset(kelvin_value=295.0)

    async with httpx.AsyncClient(transport=transport) as client:
        with patch("xarray.open_dataset", new=lambda *_a, **_k: fake_ds):
            n = await fetch_and_upsert(db_path=db, cycle=cycle, http_client=client)

    assert n == len(STATIONS)
    # URL composed from the requested cycle + its day-aligned step (00z -> 48h).
    assert "20260503000000-48h-oper-fc.grib2" in str(captured["url"])
    # Verify rows landed.
    con = duckdb.connect(str(db), read_only=True)
    try:
        rows = con.execute(
            "SELECT model, station, valid_date, forecast_high_f, member "
            "FROM weather_forecast WHERE model = ? ORDER BY station",
            [MODEL_TAG],
        ).fetchall()
    finally:
        con.close()
    assert len(rows) == len(STATIONS)
    icaos = {r[1] for r in rows}
    # KNYC not KJFK since PR-C (audit root cause #4: NY settles on Central Park).
    assert "KNYC" in icaos and "KJFK" not in icaos
    assert icaos == {s.icao for s in STATIONS}
    for _model, _icao, vd, high_f, member in rows:
        # 00z 2026-05-03 covers calendar day 2026-05-04 (the old code
        # stored 2026-05-05 — the valid-time date).
        assert vd == date(2026, 5, 4)
        assert member == 0
        # 295 K = 71.33 F.
        assert high_f == pytest.approx(71.33, abs=0.05)


@pytest.mark.asyncio
async def test_fetch_and_upsert_falls_back_to_prior_cycle_on_404(tmp_path: Path) -> None:
    """First fetch returns 404 (cycle not yet published) -> the flow
    retries with cycle - 6h and succeeds. Each candidate uses its own
    day-aligned step, and both same-day candidates target the SAME
    valid_date."""
    db = tmp_path / "wx.duckdb"
    bootstrap(db)
    cycle = datetime(2026, 5, 3, 6, 0, tzinfo=UTC)
    urls_seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        urls_seen.append(url)
        if "20260503060000-" in url:
            return httpx.Response(404, content=b"Not Found")
        return httpx.Response(200, content=b"stand-in")

    transport = httpx.MockTransport(handler)
    fake_ds = _stub_dataset()

    async with httpx.AsyncClient(transport=transport) as client:
        with patch("xarray.open_dataset", new=lambda *_a, **_k: fake_ds):
            n = await fetch_and_upsert(db_path=db, cycle=cycle, http_client=client)

    assert n == len(STATIONS)
    # Two attempts: failed 06z (42h step) + retried 00z (48h step).
    assert len(urls_seen) == 2
    assert "20260503060000-42h-oper-fc" in urls_seen[0]
    assert "20260503000000-48h-oper-fc" in urls_seen[1]
    # Both cycles cover the same UTC day: 2026-05-04.
    con = duckdb.connect(str(db), read_only=True)
    try:
        vds = {
            row[0]
            for row in con.execute(
                "SELECT DISTINCT valid_date FROM weather_forecast WHERE model = ?",
                [MODEL_TAG],
            ).fetchall()
        }
    finally:
        con.close()
    assert vds == {date(2026, 5, 4)}


@pytest.mark.asyncio
async def test_fetch_and_upsert_walks_back_up_to_four_cycles(tmp_path: Path) -> None:
    """The docstring always promised 4 cycles of lookback; the loop used
    to be dead code (`for ...: return`) so a SECOND consecutive 404 was
    fatal. Three misses then a hit must now succeed."""
    db = tmp_path / "wx.duckdb"
    bootstrap(db)
    cycle = datetime(2026, 5, 3, 12, 0, tzinfo=UTC)
    urls_seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        urls_seen.append(url)
        # 12z, 06z, 00z all missing; yesterday's 18z is there.
        if "20260502180000-" in url:
            return httpx.Response(200, content=b"stand-in")
        return httpx.Response(404, content=b"Not Found")

    transport = httpx.MockTransport(handler)
    fake_ds = _stub_dataset()

    async with httpx.AsyncClient(transport=transport) as client:
        with patch("xarray.open_dataset", new=lambda *_a, **_k: fake_ds):
            n = await fetch_and_upsert(db_path=db, cycle=cycle, http_client=client)

    assert n == len(STATIONS)
    assert len(urls_seen) == 4
    assert "20260502180000-30h-oper-fc" in urls_seen[3]
    # 18z 2026-05-02 covers UTC day 2026-05-03.
    con = duckdb.connect(str(db), read_only=True)
    try:
        vds = {
            row[0]
            for row in con.execute(
                "SELECT DISTINCT valid_date FROM weather_forecast WHERE model = ?",
                [MODEL_TAG],
            ).fetchall()
        }
    finally:
        con.close()
    assert vds == {date(2026, 5, 3)}


@pytest.mark.asyncio
async def test_fetch_and_upsert_raises_after_exhausting_lookback(tmp_path: Path) -> None:
    """All four candidates 404 -> a loud RuntimeError, no silent no-op."""
    db = tmp_path / "wx.duckdb"
    bootstrap(db)
    cycle = datetime(2026, 5, 3, 12, 0, tzinfo=UTC)
    urls_seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls_seen.append(str(request.url))
        return httpx.Response(404, content=b"Not Found")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(RuntimeError, match="no published ECMWF Open Data cycle"):
            await fetch_and_upsert(db_path=db, cycle=cycle, http_client=client)
    assert len(urls_seen) == 4  # tried the full promised lookback


@pytest.mark.asyncio
async def test_fetch_and_upsert_rejects_bad_lookback(tmp_path: Path) -> None:
    db = tmp_path / "wx.duckdb"
    bootstrap(db)
    with pytest.raises(ValueError, match="max_lookback_cycles"):
        await fetch_and_upsert(
            db_path=db,
            cycle=datetime(2026, 5, 3, 0, tzinfo=UTC),
            max_lookback_cycles=0,
        )


@pytest.mark.asyncio
async def test_fetch_and_upsert_propagates_non_404_errors(tmp_path: Path) -> None:
    """A 500 is NOT the cycle-not-yet-published case; it should
    surface to the cron retry layer rather than silently falling back."""
    db = tmp_path / "wx.duckdb"
    bootstrap(db)
    cycle = datetime(2026, 5, 3, 0, 0, tzinfo=UTC)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=b"upstream broken")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_and_upsert(db_path=db, cycle=cycle, http_client=client)
