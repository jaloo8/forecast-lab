"""Tests for the NBM qmd Phase 1 scaffolding.

Mirrors PR #33's pattern: unit-test the URL primitives + cycle
validation + lat/lon wrap directly. The cfgrib-touching path
(``fetch_grib2_bytes``, ``extract_station_quantiles``) is tested
via ``httpx.MockTransport`` + patched ``xarray.open_dataset`` --
no real GRIB2 fixture needed.
"""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import httpx
import pytest

from kq.clients.nbm_qmd import (
    CYCLE_HOURS,
    DEFAULT_PUBLISH_BUFFER_HOURS,
    DISSEMINATION_BASE,
    LEAD_1_STEP_HOURS,
    SHORT_NAME_TMAX,
    SUPPORTED_PERCENTILES,
    QmdFile,
    StationCoord,
    StationQuantiles,
    extract_station_quantiles,
    fetch_grib2_bytes,
    kelvin_to_fahrenheit,
    latest_published_cycle,
    make_cycle_dt,
)

# --------------------------- URL builder ---------------------------


def test_url_well_formed_lead_1_oper() -> None:
    """URL matches the path live-verified 2026-05-04."""
    cycle = datetime(2026, 5, 2, 0, tzinfo=UTC)
    f = QmdFile(cycle=cycle, step_hours=LEAD_1_STEP_HOURS)
    assert f.url == (f"{DISSEMINATION_BASE}/blend.20260502/00/qmd/blend.t00z.qmd.f048.co.grib2")


def test_url_pads_step_hours_to_three_digits() -> None:
    """Single-digit step hours zero-pad to f003 not f3."""
    cycle = datetime(2026, 5, 2, 0, tzinfo=UTC)
    f = QmdFile(cycle=cycle, step_hours=3)
    assert "f003" in f.url


def test_url_uses_conus_domain_by_default() -> None:
    cycle = datetime(2026, 5, 2, 0, tzinfo=UTC)
    f = QmdFile(cycle=cycle, step_hours=24)
    assert ".co.grib2" in f.url


def test_url_domain_is_overridable() -> None:
    """NBM publishes Alaska (ak), Hawaii (hi), Puerto Rico (pr)."""
    cycle = datetime(2026, 5, 2, 0, tzinfo=UTC)
    f = QmdFile(cycle=cycle, step_hours=24, domain="ak")
    assert ".ak.grib2" in f.url


def test_filename_distinguishes_cycle_hour() -> None:
    """06z and 12z files should not collide on the same date."""
    f06 = QmdFile(cycle=datetime(2026, 5, 2, 6, tzinfo=UTC), step_hours=24)
    f12 = QmdFile(cycle=datetime(2026, 5, 2, 12, tzinfo=UTC), step_hours=24)
    assert f06.filename == "blend.t06z.qmd.f024.co.grib2"
    assert f12.filename == "blend.t12z.qmd.f024.co.grib2"


# --------------------------- cycle validation ---------------------------


def test_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match=r"timezone-aware"):
        QmdFile(cycle=datetime(2026, 5, 2, 0), step_hours=24)


def test_rejects_non_utc_datetime() -> None:
    cet = timezone(timedelta(hours=2))
    with pytest.raises(ValueError, match=r"UTC"):
        QmdFile(cycle=datetime(2026, 5, 2, 0, tzinfo=cet), step_hours=24)


def test_rejects_unsupported_cycle_hour() -> None:
    with pytest.raises(ValueError, match=r"NBM publishes"):
        QmdFile(cycle=datetime(2026, 5, 2, 3, tzinfo=UTC), step_hours=24)


def test_rejects_negative_step_hours() -> None:
    with pytest.raises(ValueError, match=r"step_hours"):
        QmdFile(cycle=datetime(2026, 5, 2, 0, tzinfo=UTC), step_hours=-1)


# --------------------------- make_cycle_dt ---------------------------


def test_make_cycle_dt_accepts_published_cycles() -> None:
    for h in CYCLE_HOURS:
        cycle = make_cycle_dt(date(2026, 5, 2), hour=h)
        assert cycle.tzinfo == UTC
        assert cycle.hour == h


def test_make_cycle_dt_rejects_unpublished_hour() -> None:
    with pytest.raises(ValueError, match=r"not in published cycles"):
        make_cycle_dt(date(2026, 5, 2), hour=3)


# --------------------------- latest_published_cycle ---------------------------


def test_latest_published_cycle_at_03z_picks_00z() -> None:
    """At 03:00 UTC with the default 2.5h buffer, 00z is the most
    recent fully-published cycle."""
    now = datetime(2026, 5, 2, 3, 0, tzinfo=UTC)
    cycle = latest_published_cycle(now=now)
    assert cycle.hour == 0


def test_latest_published_cycle_at_00_30_rolls_back_to_18z() -> None:
    """At 00:30 UTC the buffer rolls back to yesterday's 18z."""
    now = datetime(2026, 5, 2, 0, 30, tzinfo=UTC)
    cycle = latest_published_cycle(now=now)
    assert cycle.hour == 18
    assert cycle.date() == (now - timedelta(days=1)).date()


def test_latest_published_cycle_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match=r"timezone-aware"):
        latest_published_cycle(now=datetime(2026, 5, 2, 0))


def test_latest_published_cycle_rejects_negative_buffer() -> None:
    now = datetime(2026, 5, 2, 0, tzinfo=UTC)
    with pytest.raises(ValueError, match=r"publish_buffer_hours"):
        latest_published_cycle(now=now, publish_buffer_hours=-1.0)


def test_default_publish_buffer_pinned() -> None:
    """NBM ~90min publish lag + safety -> 2.5h. Pin so changes are deliberate."""
    assert DEFAULT_PUBLISH_BUFFER_HOURS == 2.5


# --------------------------- StationCoord ---------------------------


def test_longitude_e_wraps_west_negative() -> None:
    """KLAX is at -118.4 -- east-positive convention requires +360."""
    klax = StationCoord(icao="KLAX", latitude=33.94, longitude=-118.4085)
    assert klax.longitude_e == pytest.approx(360.0 - 118.4085)


def test_longitude_e_passthrough_for_east_positive() -> None:
    p = StationCoord(icao="UTAA", latitude=0.0, longitude=120.0)
    assert p.longitude_e == 120.0


# --------------------------- temperature math ---------------------------


def test_kelvin_to_fahrenheit_freezing_point() -> None:
    assert kelvin_to_fahrenheit(273.15) == pytest.approx(32.0)


def test_kelvin_to_fahrenheit_negative_celsius() -> None:
    assert kelvin_to_fahrenheit(233.15) == pytest.approx(-40.0)


# --------------------------- supported percentiles pin ---------------------------


def test_supported_percentiles_pinned() -> None:
    """The five canonical NBM qmd quantiles. Pin so adding a new one
    is a deliberate schema change."""
    assert SUPPORTED_PERCENTILES == (10, 25, 50, 75, 90)


def test_short_name_tmax_pinned() -> None:
    """Mx2t is the WMO short name for max 2m temperature in qmd files;
    cfgrib's filter_by_keys depends on this exact spelling."""
    assert SHORT_NAME_TMAX == "mx2t"


# --------------------------- fetch_grib2_bytes (HTTP) ---------------------------


@pytest.mark.asyncio
async def test_fetch_grib2_bytes_returns_response_body() -> None:
    """fetch_grib2_bytes GETs file.url and passes raw body through.
    Verified via httpx.MockTransport so we don't hit the real S3 bucket."""
    payload = b"GRIB2 stand-in"
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, content=payload)

    transport = httpx.MockTransport(handler)
    file = QmdFile(cycle=datetime(2026, 5, 2, 0, tzinfo=UTC), step_hours=48)
    async with httpx.AsyncClient(transport=transport) as client:
        body = await fetch_grib2_bytes(client, file)
    assert body == payload
    assert captured["url"] == file.url


@pytest.mark.asyncio
async def test_fetch_grib2_bytes_propagates_http_error() -> None:
    """A 404 (cycle not yet published) surfaces as HTTPStatusError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=b"Not Found")

    transport = httpx.MockTransport(handler)
    file = QmdFile(cycle=datetime(2026, 5, 2, 0, tzinfo=UTC), step_hours=48)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_grib2_bytes(client, file)


# --------------------- extract_station_quantiles (cfgrib orchestration) ---------------------


def _make_fake_dataset_with_percentiles(
    quantile_values: dict[int, float],
) -> MagicMock:
    """Build a MagicMock that mimics an xarray Dataset with a
    'percentileValue' coordinate and a tmax data variable."""
    sampled = MagicMock()
    sampled.values = list(quantile_values.values())
    sampled.coords = {"percentileValue": MagicMock(values=list(quantile_values.keys()))}

    fake_var = MagicMock()
    fake_var.sel.return_value = sampled

    fake_ds = MagicMock()
    fake_ds.data_vars = {"mx2t": fake_var}
    fake_ds.__getitem__.side_effect = lambda _key: fake_var
    return fake_ds


def test_extract_station_quantiles_returns_all_five_quantiles() -> None:
    """A typical qmd payload with all five percentiles -> all
    populated in StationQuantiles."""
    fake_ds = _make_fake_dataset_with_percentiles(
        {10: 285.0, 25: 287.0, 50: 290.0, 75: 293.0, 90: 295.0}
    )
    stations = (StationCoord(icao="KLAX", latitude=33.94, longitude=-118.4085),)
    with patch("xarray.open_dataset", new=lambda *_a, **_k: fake_ds):
        out = extract_station_quantiles(b"stand-in", stations=stations)
    assert "KLAX" in out
    sq = out["KLAX"]
    assert sq.p10_kelvin == pytest.approx(285.0)
    assert sq.p50_kelvin == pytest.approx(290.0)
    assert sq.p90_kelvin == pytest.approx(295.0)


def test_extract_station_quantiles_uses_filter_by_keys() -> None:
    """The cfgrib filter must specify shortName='mx2t' so we don't
    pick up unrelated qmd messages (e.g. wind, dewpoint)."""
    captured_kwargs: dict[str, object] = {}

    fake_ds = _make_fake_dataset_with_percentiles(
        {10: 285.0, 25: 287.0, 50: 290.0, 75: 293.0, 90: 295.0}
    )

    def fake_open(_path: str, **kwargs: object) -> MagicMock:
        captured_kwargs.update(kwargs)
        return fake_ds

    stations = (StationCoord(icao="KLAX", latitude=33.94, longitude=-118.4085),)
    with patch("xarray.open_dataset", new=fake_open):
        extract_station_quantiles(b"stand-in", stations=stations)

    backend_kwargs = captured_kwargs.get("backend_kwargs")
    assert backend_kwargs == {"filter_by_keys": {"shortName": SHORT_NAME_TMAX}}


def test_extract_station_quantiles_handles_p5_alias_for_p10() -> None:
    """Some NBM cycles emit P5 instead of P10 -- we accept both."""
    fake_ds = _make_fake_dataset_with_percentiles(
        {5: 280.0, 25: 287.0, 50: 290.0, 75: 293.0, 90: 295.0}
    )
    stations = (StationCoord(icao="KLAX", latitude=33.94, longitude=-118.4085),)
    with patch("xarray.open_dataset", new=lambda *_a, **_k: fake_ds):
        out = extract_station_quantiles(b"stand-in", stations=stations)
    # Falls back to P5 when P10 not present.
    assert out["KLAX"].p10_kelvin == pytest.approx(280.0)


def test_extract_station_quantiles_cleans_up_tempfile() -> None:
    """The function writes bytes to a temp file (cfgrib needs a path)
    + cleans up on exit."""
    fake_ds = _make_fake_dataset_with_percentiles(
        {10: 285.0, 25: 287.0, 50: 290.0, 75: 293.0, 90: 295.0}
    )
    stations = (StationCoord(icao="KLAX", latitude=33.94, longitude=-118.4085),)

    parent = tempfile.gettempdir()
    before = {p for p in os.listdir(parent) if p.endswith(".grib2")}
    with patch("xarray.open_dataset", new=lambda *_a, **_k: fake_ds):
        extract_station_quantiles(b"stand-in", stations=stations)
    after = {p for p in os.listdir(parent) if p.endswith(".grib2")}
    assert after - before == set()  # no leaked files


def test_station_quantiles_dataclass_is_frozen() -> None:
    sq = StationQuantiles(
        icao="KLAX",
        p10_kelvin=285.0,
        p25_kelvin=287.0,
        p50_kelvin=290.0,
        p75_kelvin=293.0,
        p90_kelvin=295.0,
    )
    with pytest.raises(AttributeError):
        sq.icao = "mutated"  # type: ignore[misc]
