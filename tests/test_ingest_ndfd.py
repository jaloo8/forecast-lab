"""End-to-end tests for the NDFD/NBM ingest + backfill flows."""

from __future__ import annotations

from collections.abc import Generator
from datetime import date, datetime
from pathlib import Path
from typing import Any, ClassVar

import pytest

from kq.clients.ndfd import DETERMINISTIC_SOURCE, NbmDeterministicForecast
from kq.clients.stations import STATIONS
from kq.flows import backfill_ndfd as backfill_mod
from kq.flows import ingest_ndfd as ingest_mod
from kq.storage.duckdb_store import bootstrap, connect
from kq.storage.repositories.ndfd import fetch_ndfd_forecasts


class _StubNdfdClient:
    """Async-context-manager stand-in for ``NdfdClient`` used in flow tests.

    Configurable via class-level state so a test can hook ``fetch_forecast`` or
    ``fetch_historical`` to return canned rows or raise. Records every call for
    assertions.
    """

    fetch_forecast_impl: ClassVar[Any] = None
    fetch_historical_impl: ClassVar[Any] = None
    calls: ClassVar[list[dict[str, Any]]] = []

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    async def __aenter__(self) -> _StubNdfdClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def fetch_forecast(
        self,
        station: Any,
        *,
        forecast_days: int = 7,
    ) -> list[NbmDeterministicForecast]:
        type(self).calls.append(
            {"kind": "forecast", "station": station, "forecast_days": forecast_days}
        )
        if type(self).fetch_forecast_impl is None:
            return []
        return await type(self).fetch_forecast_impl(station, forecast_days=forecast_days)

    async def fetch_historical(
        self,
        station: Any,
        *,
        start_date: date,
        end_date: date,
    ) -> list[NbmDeterministicForecast]:
        type(self).calls.append(
            {
                "kind": "historical",
                "station": station,
                "start_date": start_date,
                "end_date": end_date,
            }
        )
        if type(self).fetch_historical_impl is None:
            return []
        return await type(self).fetch_historical_impl(
            station, start_date=start_date, end_date=end_date
        )


@pytest.fixture(autouse=True)
def _reset_stub() -> Generator[None, None, None]:
    _StubNdfdClient.fetch_forecast_impl = None
    _StubNdfdClient.fetch_historical_impl = None
    _StubNdfdClient.calls = []
    yield
    _StubNdfdClient.calls = []


def _bootstrap(tmp_path: Path) -> Path:
    db_path = tmp_path / "ingest.duckdb"
    bootstrap(db_path)
    return db_path


def _row(
    station: str,
    valid_date: date,
    *,
    lead: int = 1,
    t: float = 60.0,
) -> NbmDeterministicForecast:
    return NbmDeterministicForecast(
        as_of=datetime(2026, 4, 28),
        station=station,
        valid_date=valid_date,
        lead_days=lead,
        forecast_max_f=t,
    )


# --------------------------- ingest_once ---------------------------


async def test_ingest_once_writes_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _bootstrap(tmp_path)

    async def stub_forecast(station: Any, *, forecast_days: int) -> list[NbmDeterministicForecast]:
        icao = station.icao if hasattr(station, "icao") else station
        return [_row(icao, date(2026, 4, 29), lead=1, t=58.0)]

    _StubNdfdClient.fetch_forecast_impl = stub_forecast
    monkeypatch.setattr(ingest_mod, "NdfdClient", _StubNdfdClient)
    inserted = await ingest_mod.ingest_once(db_path=db_path)

    assert inserted == len(STATIONS)
    # Every station was queried exactly once.
    queried = [c["station"].icao for c in _StubNdfdClient.calls]
    assert sorted(queried) == sorted(s.icao for s in STATIONS)


async def test_ingest_once_isolates_per_station_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A single failing station logs and continues; others still write."""
    db_path = _bootstrap(tmp_path)

    async def flaky_forecast(station: Any, *, forecast_days: int) -> list[NbmDeterministicForecast]:
        icao = station.icao if hasattr(station, "icao") else station
        if icao == "KLAX":
            raise RuntimeError("openmeteo blip for LAX")
        return [_row(icao, date(2026, 4, 29))]

    _StubNdfdClient.fetch_forecast_impl = flaky_forecast
    monkeypatch.setattr(ingest_mod, "NdfdClient", _StubNdfdClient)
    inserted = await ingest_mod.ingest_once(db_path=db_path)

    assert inserted == len(STATIONS) - 1


async def test_ingest_once_inserts_are_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-running ingest_once with the same row data overwrites in place."""
    db_path = _bootstrap(tmp_path)

    async def stub_forecast(station: Any, *, forecast_days: int) -> list[NbmDeterministicForecast]:
        icao = station.icao if hasattr(station, "icao") else station
        return [_row(icao, date(2026, 4, 29), t=60.0)]

    _StubNdfdClient.fetch_forecast_impl = stub_forecast
    monkeypatch.setattr(ingest_mod, "NdfdClient", _StubNdfdClient)
    await ingest_mod.ingest_once(db_path=db_path)
    # Second run should still report rows written but DB should not double-up.
    await ingest_mod.ingest_once(db_path=db_path)

    con = connect(db_path)
    try:
        rows = fetch_ndfd_forecasts(con, source=DETERMINISTIC_SOURCE)
    finally:
        con.close()
    assert len(rows) == len(STATIONS)


# --------------------------- backfill ---------------------------


async def test_backfill_writes_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _bootstrap(tmp_path)

    async def stub_hist(
        station: Any, *, start_date: date, end_date: date
    ) -> list[NbmDeterministicForecast]:
        icao = station.icao if hasattr(station, "icao") else station
        # Two rows per station for the window.
        return [
            _row(icao, start_date, t=55.0),
            _row(icao, end_date, t=58.0),
        ]

    _StubNdfdClient.fetch_historical_impl = stub_hist
    monkeypatch.setattr(backfill_mod, "NdfdClient", _StubNdfdClient)
    inserted = await backfill_mod.backfill(
        start_date=date(2025, 4, 1),
        end_date=date(2025, 4, 5),
        db_path=db_path,
    )

    assert inserted == 2 * len(STATIONS)


async def test_backfill_rejects_inverted_range(tmp_path: Path) -> None:
    db_path = _bootstrap(tmp_path)
    with pytest.raises(ValueError, match="precedes"):
        await backfill_mod.backfill(
            start_date=date(2025, 4, 5),
            end_date=date(2025, 4, 1),
            db_path=db_path,
        )


async def test_backfill_isolates_per_station_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _bootstrap(tmp_path)

    async def flaky_hist(
        station: Any, *, start_date: date, end_date: date
    ) -> list[NbmDeterministicForecast]:
        icao = station.icao if hasattr(station, "icao") else station
        if icao == "KMIA":
            raise RuntimeError("openmeteo blip for MIA")
        return [_row(icao, start_date)]

    _StubNdfdClient.fetch_historical_impl = flaky_hist
    monkeypatch.setattr(backfill_mod, "NdfdClient", _StubNdfdClient)
    inserted = await backfill_mod.backfill(
        start_date=date(2025, 4, 1),
        end_date=date(2025, 4, 1),
        db_path=db_path,
    )

    assert inserted == len(STATIONS) - 1
