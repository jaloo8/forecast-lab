"""Tests for the historical weather backfill flow (true lead-1, PR-F;
multi-model lanes, Phase A)."""

from __future__ import annotations

import asyncio
import itertools
import json
from datetime import date, timedelta
from pathlib import Path
from typing import ClassVar

import pytest

import kq.flows.backfill_weather as backfill_weather_flow
from kq.clients.openmeteo import (
    PREV_DAY1_MODEL_NAME,
    PREV_DAY1_MODELS,
    EnsembleForecast,
    parse_previous_runs_payload,
    previous_day1_as_of,
)
from kq.clients.stations import STATIONS, STATIONS_BY_ICAO, Station
from kq.flows.backfill_weather import _chunks, backfill
from kq.storage.duckdb_store import bootstrap, connect
from kq.storage.repositories.forecasts import insert_forecasts

FIXTURE = Path(__file__).parent / "fixtures" / "openmeteo_previous_runs_klax.json"


def test_backfill_rejects_reversed_date_range(tmp_path: Path) -> None:
    async def _run() -> None:
        with pytest.raises(ValueError, match="precedes"):
            await backfill(
                start_date=date(2025, 6, 10),
                end_date=date(2025, 6, 1),
                db_path=tmp_path / "b.duckdb",
            )

    asyncio.run(_run())


def test_chunks_cover_range_without_overlap() -> None:
    chunks = _chunks(date(2024, 11, 1), date(2025, 6, 30), days=90)
    # Contiguous, non-overlapping, inclusive cover of the window.
    assert chunks[0][0] == date(2024, 11, 1)
    assert chunks[-1][1] == date(2025, 6, 30)
    for (_, prev_end), (next_start, _) in itertools.pairwise(chunks):
        assert next_start == prev_end + timedelta(days=1)
    assert all((end - start).days + 1 <= 90 for start, end in chunks)


def test_chunks_single_day() -> None:
    assert _chunks(date(2025, 1, 1), date(2025, 1, 1)) == [(date(2025, 1, 1), date(2025, 1, 1))]


def test_prevday1_rows_coexist_with_ensemble_in_pk(tmp_path: Path) -> None:
    """The model='gfs_prevday1' tag keeps the PK distinct from ensemble rows
    with the same (member, station, valid_date)."""
    db_path = tmp_path / "hist.duckdb"
    bootstrap(db_path)

    rows = parse_previous_runs_payload(
        json.loads(FIXTURE.read_text(encoding="utf-8")),
        station=STATIONS_BY_ICAO["KLAX"],
    )

    con = connect(db_path)
    try:
        n_hist = insert_forecasts(con, rows)

        # Hand-insert an ensemble row with the SAME member=0, station=KLAX,
        # valid_date=2024-11-01 but model='gefs' — must coexist, not collide.
        as_of = rows[0].as_of
        con.execute(
            """
            INSERT INTO weather_forecast
            (as_of, run_time, model, member, station, valid_date,
             forecast_high_f, forecast_low_f)
            VALUES (?, ?, 'gefs', 0, 'KLAX', '2024-11-01', 67.5, 47.0)
            """,
            (as_of, as_of),
        )

        counts = con.execute(
            """
            SELECT model, COUNT(*) FROM weather_forecast
            GROUP BY model ORDER BY model
            """
        ).fetchall()
    finally:
        con.close()

    assert n_hist == 3
    assert counts == [("gefs", 1), (PREV_DAY1_MODEL_NAME, 3)]


def test_backfill_is_idempotent_because_as_of_is_deterministic(tmp_path: Path) -> None:
    """as_of derives from valid_date (the honest prediction instant), not
    fetch time — so re-inserting the same window overwrites in place."""
    db_path = tmp_path / "idem.duckdb"
    bootstrap(db_path)
    rows = parse_previous_runs_payload(
        json.loads(FIXTURE.read_text(encoding="utf-8")),
        station=STATIONS_BY_ICAO["KLAX"],
    )
    con = connect(db_path)
    try:
        insert_forecasts(con, rows)
        insert_forecasts(con, rows)  # second run must not duplicate
        (n,) = con.execute("SELECT COUNT(*) FROM weather_forecast").fetchone()  # type: ignore[misc]
    finally:
        con.close()
    assert n == 3


# ------------------------------------------------- multi-model lanes (Phase A)


class _FakeLaneClient:
    """Fake OpenMeteoClient: one deterministic row per (station, model, day).

    ``fail_on`` is a set of (station_icao, model_id) pairs that simulate a
    persistent upstream failure for that lane only.
    """

    calls: ClassVar[list[tuple[str, str]]] = []
    fail_on: ClassVar[set[tuple[str, str]]] = set()

    async def __aenter__(self) -> _FakeLaneClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        pass

    async def fetch_previous_day1(
        self,
        station: Station,
        *,
        start_date: date,
        end_date: date,
        model_id: str = "gfs_seamless",
    ) -> list[EnsembleForecast]:
        type(self).calls.append((station.icao, model_id))
        if (station.icao, model_id) in self.fail_on:
            raise RuntimeError("simulated upstream failure")
        out: list[EnsembleForecast] = []
        d = start_date
        while d <= end_date:
            as_of = previous_day1_as_of(d, station)
            out.append(
                EnsembleForecast(
                    as_of=as_of,
                    run_time=as_of,
                    model=PREV_DAY1_MODELS[model_id],
                    member=0,
                    station=station.icao,
                    valid_date=d,
                    forecast_high_f=70.0,
                    forecast_low_f=55.0,
                )
            )
            d += timedelta(days=1)
        return out


def test_backfill_defaults_to_every_verified_lane(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Default model_ids = all verified lanes; each lane lands under its own
    model tag with the shared honest as_of."""
    _FakeLaneClient.calls = []
    _FakeLaneClient.fail_on = set()
    monkeypatch.setattr(backfill_weather_flow, "OpenMeteoClient", _FakeLaneClient)
    db = tmp_path / "lanes.duckdb"
    bootstrap(db)

    n = asyncio.run(backfill(start_date=date(2025, 6, 1), end_date=date(2025, 6, 2), db_path=db))
    assert n == len(STATIONS) * len(PREV_DAY1_MODELS) * 2

    con = connect(db)
    try:
        lanes = con.execute(
            "SELECT model, COUNT(*) FROM weather_forecast GROUP BY model ORDER BY model"
        ).fetchall()
    finally:
        con.close()
    assert dict(lanes) == {lane: len(STATIONS) * 2 for lane in PREV_DAY1_MODELS.values()}
    # every (station, model) pair was requested exactly once (single chunk)
    assert sorted(_FakeLaneClient.calls) == sorted(
        (s.icao, m) for s in STATIONS for m in PREV_DAY1_MODELS
    )


def test_backfill_drops_only_the_failing_lane(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failing (station, model) lane is dropped whole; the station's other
    lanes and every other station still write."""
    _FakeLaneClient.calls = []
    _FakeLaneClient.fail_on = {("KMIA", "ecmwf_ifs025")}
    monkeypatch.setattr(backfill_weather_flow, "OpenMeteoClient", _FakeLaneClient)
    db = tmp_path / "lanefail.duckdb"
    bootstrap(db)

    n = asyncio.run(backfill(start_date=date(2025, 6, 1), end_date=date(2025, 6, 1), db_path=db))
    assert n == len(STATIONS) * len(PREV_DAY1_MODELS) - 1

    con = connect(db)
    try:
        kmia = con.execute(
            "SELECT model FROM weather_forecast WHERE station = 'KMIA' ORDER BY model"
        ).fetchall()
    finally:
        con.close()
    assert [m for (m,) in kmia] == sorted(set(PREV_DAY1_MODELS.values()) - {"ecmwf_prevday1"})


def test_backfill_rejects_unverified_model_id(tmp_path: Path) -> None:
    async def _run() -> None:
        with pytest.raises(ValueError, match="unknown previous-runs model ids"):
            await backfill(
                start_date=date(2025, 6, 1),
                end_date=date(2025, 6, 2),
                db_path=tmp_path / "bad.duckdb",
                model_ids=("ncep_nbm_conus",),  # benchmark, not an input lane
            )

    asyncio.run(_run())
