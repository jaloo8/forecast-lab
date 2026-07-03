"""Tests for the TRUE lead-1 previous-runs backfill path (PR-F).

Replaces the deleted ``test_historical_forecast.py``: the old historical
path served the freshest archived run (~lead-0) and BACKDATED ``as_of`` to
fake lead-1 — 2026-06-11 audit root cause #8. The fixture here is a real
recorded payload from previous-runs-api.open-meteo.com (KLAX, 2024-11-01 →
2024-11-03, hourly ``temperature_2m_previous_day1``, ``timezone=Etc/GMT+8``,
``models=gfs_seamless``), captured 2026-07-01.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx
import pytest

import kq.clients.openmeteo as openmeteo_pkg
from kq.clients.openmeteo import (
    PREV_DAY1_MEMBER,
    PREV_DAY1_MODEL_NAME,
    PREV_DAY1_MODELS,
    PREV_DAY1_SUFFIX,
    OpenMeteoClient,
    parse_previous_runs_payload,
    previous_day1_as_of,
)
from kq.clients.stations import STATIONS_BY_ICAO, lst_timezone_name

FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES_DIR / "openmeteo_previous_runs_klax.json"

KLAX = STATIONS_BY_ICAO["KLAX"]

# Recorded payloads per new model lane (previous-runs-api.open-meteo.com,
# KLAX, 2024-11-01 → 2024-11-03, hourly temperature_2m_previous_day1,
# timezone=Etc/GMT+8, captured 2026-07-02) with hand-pinned per-LST-day
# max/min of the 24 hourly samples for 2024-11-01 and 2024-11-03.
LANE_FIXTURES: dict[str, tuple[str, float, float, float]] = {
    # model_id: (fixture stem, nov1_high, nov1_low, nov3_high)
    "ecmwf_ifs025": ("openmeteo_previous_runs_klax_ecmwf_ifs025.json", 72.9, 50.3, 76.9),
    "icon_seamless": ("openmeteo_previous_runs_klax_icon_seamless.json", 68.5, 43.8, 77.8),
    "gem_seamless": ("openmeteo_previous_runs_klax_gem_seamless.json", 66.6, 38.1, 76.1),
    "meteofrance_seamless": (
        "openmeteo_previous_runs_klax_meteofrance_seamless.json",
        61.2,
        51.9,
        73.0,
    ),
    "jma_seamless": ("openmeteo_previous_runs_klax_jma_seamless.json", 63.6, 49.7, 72.3),
}


def _load() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


# ------------------------------------------------- fixture-pinned parsing


def test_parse_produces_one_row_per_lst_day() -> None:
    rows = parse_previous_runs_payload(_load(), station=KLAX)
    assert len(rows) == 3
    assert [r.valid_date for r in rows] == [
        date(2024, 11, 1),
        date(2024, 11, 2),
        date(2024, 11, 3),
    ]
    assert {r.model for r in rows} == {PREV_DAY1_MODEL_NAME}
    assert {r.member for r in rows} == {PREV_DAY1_MEMBER}
    assert {r.station for r in rows} == {"KLAX"}


def test_parse_aggregates_max_min_over_lst_day() -> None:
    """Values pinned against the recorded payload (max/min of each LST day's
    24 hourly previous_day1 samples)."""
    rows = parse_previous_runs_payload(_load(), station=KLAX)
    by_date = {r.valid_date: r for r in rows}
    assert by_date[date(2024, 11, 1)].forecast_high_f == pytest.approx(67.1)
    assert by_date[date(2024, 11, 1)].forecast_low_f == pytest.approx(46.5)
    assert by_date[date(2024, 11, 2)].forecast_high_f == pytest.approx(65.9)
    assert by_date[date(2024, 11, 3)].forecast_high_f == pytest.approx(75.0)


def test_parse_empty_payload_returns_empty() -> None:
    assert parse_previous_runs_payload({"hourly": {"time": []}}, station=KLAX) == []
    assert parse_previous_runs_payload({}, station=KLAX) == []


def test_parse_partial_day_yields_null_high() -> None:
    """A day with fewer than MIN_HOURLY_SAMPLES non-null samples could
    understate the daily extreme — store NULL, never a truncated max."""
    times = [f"2025-01-01T{h:02d}:00" for h in range(10)]  # only 10 samples
    payload = {"hourly": {"time": times, "temperature_2m_previous_day1": [60.0] * 10}}
    rows = parse_previous_runs_payload(payload, station=KLAX)
    assert len(rows) == 1
    assert rows[0].forecast_high_f is None
    assert rows[0].forecast_low_f is None


# ------------------------------------------------- LST-day aggregation


def test_lst_day_aggregation_spans_utc_boundary() -> None:
    """The killer case for the UTC-vs-LST finding: at KLAX, 17:00 LST is
    01:00 UTC of the NEXT calendar day. A UTC-day aggregation would move an
    evening maximum onto the wrong settlement day; LST aggregation must not.
    """
    times: list[str] = []
    values: list[float] = []
    for day in (1, 2):
        for h in range(24):
            times.append(f"2025-01-{day:02d}T{h:02d}:00")
            if day == 1 and h == 17:  # 17:00 LST = 01:00 UTC Jan 2
                values.append(80.0)
            else:
                values.append(50.0 if day == 1 else 60.0)
    payload = {"hourly": {"time": times, "temperature_2m_previous_day1": values}}

    rows = parse_previous_runs_payload(payload, station=KLAX)
    by_date = {r.valid_date: r for r in rows}
    # The 80F spike belongs to LST Jan 1 (its settlement day), NOT UTC Jan 2.
    assert by_date[date(2025, 1, 1)].forecast_high_f == pytest.approx(80.0)
    assert by_date[date(2025, 1, 2)].forecast_high_f == pytest.approx(60.0)


def test_lst_timezone_name_is_fixed_offset() -> None:
    assert lst_timezone_name(KLAX) == "Etc/GMT+8"
    assert lst_timezone_name(STATIONS_BY_ICAO["KNYC"]) == "Etc/GMT+5"
    assert lst_timezone_name(STATIONS_BY_ICAO["KDEN"]) == "Etc/GMT+7"


# ------------------------------------------------- honest-as_of regression


def test_as_of_is_the_prediction_instant_not_a_backdate() -> None:
    """2026-06-11 audit root cause #8 regression: ``as_of`` must be the
    actual prediction-availability instant derived from the API's documented
    semantics (last hourly sample of the LST day, minus the 24h previous_day1
    offset) — NEVER midnight-of-valid_date-minus-1 backdating."""
    rows = parse_previous_runs_payload(_load(), station=KLAX)
    for r in rows:
        expected = (
            datetime(r.valid_date.year, r.valid_date.month, r.valid_date.day, 23, 0)
            - timedelta(hours=KLAX.lst_offset_hours)  # LST -> UTC
            - timedelta(hours=24)  # previous_day1 offset
        )
        assert r.as_of == expected
        assert r.as_of == previous_day1_as_of(r.valid_date, KLAX)
        # The old hack stamped midnight UTC of valid_date - 1. The honest
        # instant is NOT that.
        backdated = datetime(r.valid_date.year, r.valid_date.month, r.valid_date.day) - timedelta(
            days=1
        )
        assert r.as_of != backdated


def test_run_time_is_the_prediction_instant_not_a_floored_cycle() -> None:
    """2026-07-01 audit (Tier 2): ``run_time`` used to be fabricated by
    flooring ``as_of`` to a 00/06/12/18Z pseudo-cycle. For previous-runs
    rows the honest value IS ``as_of``: by the API's definition each
    ``previous_day1`` sample was predicted exactly 24h before its valid
    time, so the newest contributing prediction instant equals
    (last sample valid time) - 24h = ``as_of``."""
    rows = parse_previous_runs_payload(_load(), station=KLAX)
    for r in rows:
        assert r.run_time == r.as_of
        # KLAX as_of is 07:00Z; the old fabrication floored it to 06:00Z.
        assert r.run_time.hour == 7
        assert r.run_time != r.as_of.replace(hour=6)


def test_lead_derives_from_as_of_in_station_local_time() -> None:
    """Lead-1 must FALL OUT of the honest as_of (station-local date of as_of
    is valid_date - 1), not be asserted independently of it."""
    rows = parse_previous_runs_payload(_load(), station=KLAX)
    for r in rows:
        local_as_of = r.as_of + timedelta(hours=KLAX.lst_offset_hours)
        assert local_as_of.date() == r.valid_date - timedelta(days=1)


def test_previous_day1_as_of_pinned_example() -> None:
    """KLAX 2024-11-01: last sample 23:00 LST = 2024-11-02T07:00Z; minus 24h
    = 2024-11-01T07:00Z. (UTC date == valid_date — which is exactly why the
    lead computation is LST-aware.)"""
    assert previous_day1_as_of(date(2024, 11, 1), KLAX) == datetime(2024, 11, 1, 7, 0)
    knyc = STATIONS_BY_ICAO["KNYC"]
    assert previous_day1_as_of(date(2024, 11, 1), knyc) == datetime(2024, 11, 1, 4, 0)


def test_backdating_api_is_gone() -> None:
    """The backdating hack must never return: neither the parser nor the
    client exposes the old lead-0 'historical deterministic' path."""
    assert not hasattr(openmeteo_pkg, "HIST_MODEL_NAME")
    assert not hasattr(openmeteo_pkg, "_parse_historical_payload")
    assert not hasattr(OpenMeteoClient, "fetch_historical_deterministic")
    # The old sentinel would silently blend lead-0 rows back into training.
    assert PREV_DAY1_MODEL_NAME != "gfs_hist"


# ------------------------------------------------- client end-to-end (mock)


def test_fetch_previous_day1_end_to_end_with_mock() -> None:
    async def _run() -> None:
        captured: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["host"] = request.url.host
            for key in ("start_date", "end_date", "hourly", "models", "timezone"):
                captured[key] = request.url.params.get(key, "") or ""
            return httpx.Response(200, json=_load())

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http:
            client = OpenMeteoClient(http)
            rows = await client.fetch_previous_day1(
                "KLAX",
                start_date=date(2024, 11, 1),
                end_date=date(2024, 11, 3),
            )

        assert captured["host"] == "previous-runs-api.open-meteo.com"
        assert captured["start_date"] == "2024-11-01"
        assert captured["end_date"] == "2024-11-03"
        assert captured["hourly"] == "temperature_2m_previous_day1"
        assert captured["models"] == "gfs_seamless"
        assert captured["timezone"] == "Etc/GMT+8"
        assert len(rows) == 3

    asyncio.run(_run())


def test_fetch_previous_day1_passes_model_id_and_tags_lane() -> None:
    """Each verified model becomes its own lane: the API `models=` param and
    the stored `model` tag must both follow the requested model_id."""

    async def _run() -> None:
        captured: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["models"] = request.url.params.get("models", "") or ""
            return httpx.Response(
                200,
                json=json.loads(
                    (FIXTURES_DIR / LANE_FIXTURES["ecmwf_ifs025"][0]).read_text(encoding="utf-8")
                ),
            )

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http:
            client = OpenMeteoClient(http)
            rows = await client.fetch_previous_day1(
                "KLAX",
                start_date=date(2024, 11, 1),
                end_date=date(2024, 11, 3),
                model_id="ecmwf_ifs025",
            )

        assert captured["models"] == "ecmwf_ifs025"
        assert {r.model for r in rows} == {"ecmwf_prevday1"}

    asyncio.run(_run())


def test_fetch_previous_day1_rejects_unverified_model_id() -> None:
    """Only live-verified Previous Runs models may become lanes — an
    unverified id must fail loudly BEFORE any network contact."""

    async def _run() -> None:
        async with OpenMeteoClient() as c:
            with pytest.raises(ValueError, match="unsupported previous-runs model"):
                await c.fetch_previous_day1(
                    "KLAX",
                    start_date=date(2024, 11, 1),
                    end_date=date(2024, 11, 3),
                    model_id="ukmo_seamless",  # probed: archive too shallow
                )

    asyncio.run(_run())


def test_fetch_previous_day1_rejects_reversed_date_range() -> None:
    async def _run() -> None:
        async with OpenMeteoClient() as c:
            with pytest.raises(ValueError, match="precedes"):
                await c.fetch_previous_day1(
                    "KLAX",
                    start_date=date(2025, 6, 10),
                    end_date=date(2025, 6, 1),
                )

    asyncio.run(_run())


def test_fetch_previous_day1_unknown_station_raises() -> None:
    async def _run() -> None:
        async with OpenMeteoClient() as c:
            with pytest.raises(ValueError, match="unknown station"):
                await c.fetch_previous_day1(
                    "KZZZ",
                    start_date=date(2025, 6, 1),
                    end_date=date(2025, 6, 3),
                )

    asyncio.run(_run())


# ------------------------------------------------- multi-model lanes (Phase A)


@pytest.mark.parametrize("model_id", sorted(LANE_FIXTURES))
def test_lane_fixture_parses_with_honest_semantics(model_id: str) -> None:
    """Fixture-pinned parsing per new model lane: 3 LST-day rows, correct
    lane tag, hand-pinned max/min, and the SAME honest as_of/run_time/lead
    semantics as the original GFS lane (the 24h previous_day1 offset is
    model-independent)."""
    stem, nov1_high, nov1_low, nov3_high = LANE_FIXTURES[model_id]
    payload = json.loads((FIXTURES_DIR / stem).read_text(encoding="utf-8"))
    lane = PREV_DAY1_MODELS[model_id]

    rows = parse_previous_runs_payload(payload, station=KLAX, model=lane)

    assert [r.valid_date for r in rows] == [
        date(2024, 11, 1),
        date(2024, 11, 2),
        date(2024, 11, 3),
    ]
    assert {r.model for r in rows} == {lane}
    assert {r.member for r in rows} == {PREV_DAY1_MEMBER}
    by_date = {r.valid_date: r for r in rows}
    assert by_date[date(2024, 11, 1)].forecast_high_f == pytest.approx(nov1_high)
    assert by_date[date(2024, 11, 1)].forecast_low_f == pytest.approx(nov1_low)
    assert by_date[date(2024, 11, 3)].forecast_high_f == pytest.approx(nov3_high)
    for r in rows:
        assert r.as_of == previous_day1_as_of(r.valid_date, KLAX)
        assert r.run_time == r.as_of
        local_as_of = r.as_of + timedelta(hours=KLAX.lst_offset_hours)
        assert local_as_of.date() == r.valid_date - timedelta(days=1)


def test_lane_names_follow_the_prevday1_convention() -> None:
    """Every lane ends in '_prevday1' (the feature pooler keys on this
    suffix), no lane collides with another, and the poisoned 'gfs_hist'
    sentinel is not among them."""
    lanes = list(PREV_DAY1_MODELS.values())
    assert len(set(lanes)) == len(lanes)
    assert all(lane.endswith(PREV_DAY1_SUFFIX) for lane in lanes)
    assert "gfs_hist" not in lanes
    assert PREV_DAY1_MODELS["gfs_seamless"] == PREV_DAY1_MODEL_NAME


def test_default_parse_still_tags_the_gfs_lane() -> None:
    """Backward compatibility: omitting `model` keeps PR-F's behavior."""
    rows = parse_previous_runs_payload(_load(), station=KLAX)
    assert {r.model for r in rows} == {PREV_DAY1_MODEL_NAME}
