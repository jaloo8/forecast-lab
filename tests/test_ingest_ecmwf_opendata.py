"""Tests for the ECMWF Open Data ingest flow.

Coverage:
- ``latest_published_cycle`` rounds down to the most recent cycle
  whose step=48h fc.grib2 has plausibly published given the ~2.5h
  publish buffer.
- ``_build_forecast_rows`` shapes per-station Kelvin readings into
  ``EnsembleForecast`` rows with the correct model tag, member, and
  Kelvin->F conversion.
- The end-to-end flow round-trips through ``httpx.MockTransport``
  (no live ECMWF fetch) plus a patched ``xarray.open_dataset`` (no
  real GRIB2 fixture), and the cycle-not-yet-published 404 fallback
  path is exercised.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import duckdb
import httpx
import pytest

from kq.flows.ingest_ecmwf_opendata import (
    LEAD_1_STEP_HOURS,
    MODEL_TAG,
    SHORT_NAME_MX2T24,
    _build_forecast_rows,
    fetch_and_upsert,
    latest_published_cycle,
)
from kq.storage.duckdb_store import bootstrap

# --------------------- latest_published_cycle ---------------------


def test_latest_published_cycle_picks_00z_at_03z() -> None:
    """At 03:00 UTC, 00z is the most recent cycle whose step=48h has
    plausibly published (publish buffer is 2.5h)."""
    now = datetime(2026, 5, 3, 3, 0, tzinfo=UTC)
    cycle = latest_published_cycle(now=now)
    assert cycle.hour == 0
    assert cycle.date() == now.date()


def test_latest_published_cycle_picks_prior_18z_just_after_00z() -> None:
    """At 00:30 UTC the buffer rolls back to yesterday's 18z."""
    now = datetime(2026, 5, 3, 0, 30, tzinfo=UTC)
    cycle = latest_published_cycle(now=now)
    assert cycle.hour == 18
    assert cycle.date() == (now - timedelta(days=1)).date()


def test_latest_published_cycle_picks_06z_at_09z() -> None:
    now = datetime(2026, 5, 3, 9, 0, tzinfo=UTC)
    cycle = latest_published_cycle(now=now)
    assert cycle.hour == 6


def test_latest_published_cycle_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        latest_published_cycle(now=datetime(2026, 5, 3, 3, 0))


# --------------------- _build_forecast_rows ---------------------


def test_build_forecast_rows_tags_model_and_converts_kelvin() -> None:
    cycle = datetime(2026, 5, 3, 0, 0, tzinfo=UTC)
    valid_date = (cycle + timedelta(hours=LEAD_1_STEP_HOURS)).date()
    as_of = cycle + timedelta(hours=3)
    rows = _build_forecast_rows(
        station_kelvin={"KLAX": 290.0, "KJFK": 280.0},
        cycle=cycle,
        valid_date=valid_date,
        as_of=as_of,
    )
    assert len(rows) == 2
    by_icao = {r.station: r for r in rows}
    # KLAX 290K = 62.33 F; KJFK 280K = 44.33 F.
    assert by_icao["KLAX"].forecast_high_f == pytest.approx(62.33, abs=0.05)
    assert by_icao["KJFK"].forecast_high_f == pytest.approx(44.33, abs=0.05)
    for row in rows:
        assert row.model == MODEL_TAG
        assert row.member == 0
        assert row.forecast_low_f is None  # mx2t24 is daily MAX only
        # Naive UTC for DuckDB.
        assert row.as_of.tzinfo is None
        assert row.run_time.tzinfo is None
    assert all(r.valid_date == valid_date for r in rows)


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
    code path without a real xarray.Dataset / GRIB2."""
    fake_var = MagicMock()
    fake_var.sel.return_value = MagicMock(__float__=lambda _self: kelvin_value)
    fake_ds = MagicMock()
    fake_ds.data_vars = {"mx2t24": fake_var}
    fake_ds.__getitem__.side_effect = lambda _key: fake_var
    return fake_ds


@pytest.mark.asyncio
async def test_fetch_and_upsert_round_trip(tmp_path: Path) -> None:
    """Mock the HTTP layer + xarray and verify rows land in DuckDB
    tagged with ``MODEL_TAG`` for the requested cycle's valid_date."""
    db = tmp_path / "wx.duckdb"
    bootstrap(db)
    cycle = datetime(2026, 5, 3, 0, 0, tzinfo=UTC)
    expected_valid_date = (cycle + timedelta(hours=LEAD_1_STEP_HOURS)).date()

    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, content=b"stand-in grib2 bytes")

    transport = httpx.MockTransport(handler)
    fake_ds = _stub_dataset(kelvin_value=295.0)

    async with httpx.AsyncClient(transport=transport) as client:
        with patch("xarray.open_dataset", new=lambda *_a, **_k: fake_ds):
            n = await fetch_and_upsert(db_path=db, cycle=cycle, http_client=client)

    assert n == 6  # six STATIONS
    # URL composed from the requested cycle + step=48h.
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
    assert len(rows) == 6
    icaos = {r[1] for r in rows}
    assert icaos == {"KLAX", "KJFK", "KMDW", "KMIA", "KDEN", "KAUS"}
    for _model, _icao, vd, high_f, member in rows:
        assert vd == expected_valid_date
        assert member == 0
        # 295 K = 71.33 F.
        assert high_f == pytest.approx(71.33, abs=0.05)


@pytest.mark.asyncio
async def test_fetch_and_upsert_falls_back_to_prior_cycle_on_404(tmp_path: Path) -> None:
    """First fetch returns 404 (cycle not yet published) -> the flow
    retries with cycle - 6h and succeeds. Verifies the URL on the
    second attempt is for the prior cycle."""
    db = tmp_path / "wx.duckdb"
    bootstrap(db)
    cycle = datetime(2026, 5, 3, 6, 0, tzinfo=UTC)
    prior = cycle - timedelta(hours=6)  # 00z
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

    assert n == 6
    # Two attempts: failed + retried at the prior cycle.
    assert len(urls_seen) == 2
    assert "20260503060000-" in urls_seen[0]  # failed cycle
    assert "20260503000000-" in urls_seen[1]  # prior cycle
    # Stored valid_date should be from the prior cycle.
    expected_vd = (prior + timedelta(hours=LEAD_1_STEP_HOURS)).date()
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
    assert vds == {expected_vd}


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


# --------------------- constants pin ---------------------


def test_short_name_mx2t24_is_pinned() -> None:
    """Pin the WMO short name -- changing this is a semantic change to
    what we extract (e.g. swapping mx2t24 for mx2t6 changes the
    aggregation window)."""
    assert SHORT_NAME_MX2T24 == "mx2t24"


def test_lead_1_step_hours_is_pinned() -> None:
    """Pin step=48h -- this is what makes the (00z init, +48h) span
    the full lead-1 calendar day."""
    assert LEAD_1_STEP_HOURS == 48
