"""Tests for flow-orchestration loop bodies.

The flows under `kq/flows/*` were under-covered (26-48%) by the targeted
client/parser tests. This file exercises the orchestration logic itself -
loop iteration, per-station error tolerance, partial failure paths,
end-to-end side effects (DuckDB row counts, log calls).

Strategy: monkeypatch the underlying client's network method to return
synthetic data or raise; assert on the DuckDB state and the FlowResult
return shape.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import pytest

from kq.clients.kalshi import KalshiCredentialsError, Market, OrderBookSnapshot
from kq.clients.openmeteo import EnsembleForecast
from kq.flows import backfill_observed as backfill_observed_flow
from kq.flows import backfill_weather as backfill_weather_flow
from kq.flows import ingest_kalshi as ingest_kalshi_flow
from kq.storage.duckdb_store import bootstrap


def _market(ticker: str = "K-1") -> Market:
    return Market(
        ticker=ticker,
        event_ticker="KXTEST",
        title="t",
        status="open",
        category=None,
        yes_ask=0.42,
        yes_bid=0.38,
        last_price=0.40,
        volume=100,
        open_interest=50,
        open_time=datetime(2026, 1, 1, tzinfo=UTC),
        close_time=datetime(2026, 1, 2, tzinfo=UTC),
        expected_expiration_time=None,
        rules_primary=None,
    )


def _book(ticker: str = "K-1") -> OrderBookSnapshot:
    return OrderBookSnapshot(
        snap_time=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        ticker=ticker,
        yes_bid=0.38,
        yes_ask=0.45,
        yes_bid_size=10,
        yes_ask_size=30,
        yes_bids=((38, 10),),
        yes_asks=((45, 30),),
    )


def _ens_row(*, station: str, valid_date: date, hi: float = 75.0) -> EnsembleForecast:
    return EnsembleForecast(
        as_of=datetime(valid_date.year, valid_date.month, valid_date.day),
        run_time=datetime(valid_date.year, valid_date.month, valid_date.day),
        model="gfs_hist",
        member=0,
        station=station,
        valid_date=valid_date,
        forecast_high_f=hi,
        forecast_low_f=hi - 15,
    )


# -------------------------------------------------------------- ingest_kalshi


async def test_ingest_kalshi_credentials_missing_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the user hasn't configured Kalshi creds, ingest must raise cleanly."""

    class _FakeClient:
        @classmethod
        def from_settings(cls, *_args: object, **_kwargs: object) -> _FakeClient:
            raise KalshiCredentialsError("KALSHI_API_KEY_ID is empty")

    monkeypatch.setattr(ingest_kalshi_flow, "KalshiClient", _FakeClient)
    db = tmp_path / "k.duckdb"
    bootstrap(db)
    with pytest.raises(KalshiCredentialsError):
        await ingest_kalshi_flow.ingest_once(db_path=db)


async def test_ingest_kalshi_loop_writes_markets_and_books(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Happy-path orchestration: 6 stations x 2 markets each -> 12 markets, 12 books."""

    class _FakeClient:
        async def __aenter__(self) -> _FakeClient:
            return self

        async def __aexit__(self, *_exc: object) -> None:
            pass

        async def list_markets(
            self, *, event_ticker: str | None = None, series_ticker: str | None = None
        ) -> list[Market]:
            t = series_ticker or event_ticker
            return [_market(f"{t}-A"), _market(f"{t}-B")]

        async def get_orderbook(self, ticker: str) -> OrderBookSnapshot:
            return _book(ticker)

        @classmethod
        def from_settings(cls, *_args: object, **_kwargs: object) -> _FakeClient:
            return cls()

    monkeypatch.setattr(ingest_kalshi_flow, "KalshiClient", _FakeClient)
    db = tmp_path / "k.duckdb"
    bootstrap(db)

    n_markets, n_books = await ingest_kalshi_flow.ingest_once(db_path=db)
    assert n_markets == 12  # 6 stations x 2 markets
    assert n_books == 12

    con = duckdb.connect(str(db))
    try:
        market_count = con.execute("SELECT COUNT(*) FROM kalshi_market").fetchone()
        book_count = con.execute("SELECT COUNT(*) FROM kalshi_book_snap").fetchone()
    finally:
        con.close()
    assert market_count is not None and market_count[0] == 12
    assert book_count is not None and book_count[0] == 12


async def test_ingest_kalshi_per_station_failure_tolerated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If one station's list_markets raises, the others still process."""

    fail_for = "KXHIGHNY"  # JFK's series ticker per stations.py

    class _FakeClient:
        async def __aenter__(self) -> _FakeClient:
            return self

        async def __aexit__(self, *_exc: object) -> None:
            pass

        async def list_markets(
            self, *, event_ticker: str | None = None, series_ticker: str | None = None
        ) -> list[Market]:
            t = series_ticker or event_ticker
            if t == fail_for:
                raise RuntimeError("simulated upstream 502")
            return [_market(f"{t}-A")]

        async def get_orderbook(self, ticker: str) -> OrderBookSnapshot:
            return _book(ticker)

        @classmethod
        def from_settings(cls, *_args: object, **_kwargs: object) -> _FakeClient:
            return cls()

    monkeypatch.setattr(ingest_kalshi_flow, "KalshiClient", _FakeClient)
    db = tmp_path / "k.duckdb"
    bootstrap(db)

    n_markets, n_books = await ingest_kalshi_flow.ingest_once(db_path=db)
    # 6 stations, 1 fails -> 5 markets and 5 books
    assert n_markets == 5
    assert n_books == 5


async def test_ingest_kalshi_orderbook_failure_tolerated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If a single orderbook fetch fails, the market is still upserted."""

    class _FakeClient:
        async def __aenter__(self) -> _FakeClient:
            return self

        async def __aexit__(self, *_exc: object) -> None:
            pass

        async def list_markets(
            self, *, event_ticker: str | None = None, series_ticker: str | None = None
        ) -> list[Market]:
            t = series_ticker or event_ticker
            return [_market(f"{t}-A"), _market(f"{t}-B")]

        async def get_orderbook(self, ticker: str) -> OrderBookSnapshot:
            if ticker.endswith("-B"):
                raise RuntimeError("transient failure on B")
            return _book(ticker)

        @classmethod
        def from_settings(cls, *_args: object, **_kwargs: object) -> _FakeClient:
            return cls()

    monkeypatch.setattr(ingest_kalshi_flow, "KalshiClient", _FakeClient)
    db = tmp_path / "k.duckdb"
    bootstrap(db)
    n_markets, n_books = await ingest_kalshi_flow.ingest_once(db_path=db)
    # 6 x 2 = 12 markets all upserted; 6 books succeed, 6 fail -> 6
    assert n_markets == 12
    assert n_books == 6


async def test_ingest_kalshi_event_ticker_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When event_tickers is supplied, the STATIONS loop is bypassed."""
    seen: list[str] = []

    class _FakeClient:
        async def __aenter__(self) -> _FakeClient:
            return self

        async def __aexit__(self, *_exc: object) -> None:
            pass

        async def list_markets(
            self, *, event_ticker: str | None = None, series_ticker: str | None = None
        ) -> list[Market]:
            seen.append(event_ticker or series_ticker or "")
            return [_market(f"{event_ticker}-A")]

        async def get_orderbook(self, ticker: str) -> OrderBookSnapshot:
            return _book(ticker)

        @classmethod
        def from_settings(cls, *_args: object, **_kwargs: object) -> _FakeClient:
            return cls()

    monkeypatch.setattr(ingest_kalshi_flow, "KalshiClient", _FakeClient)
    db = tmp_path / "k.duckdb"
    bootstrap(db)

    await ingest_kalshi_flow.ingest_once(
        db_path=db, event_tickers=["KXNBAGAME-FOO", "KXMLBGAME-BAR"]
    )
    assert seen == ["KXNBAGAME-FOO", "KXMLBGAME-BAR"]


# ---------------------------------------------------------- backfill_weather


async def test_backfill_weather_rejects_bad_date_range(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="precedes"):
        await backfill_weather_flow.backfill(
            start_date=date(2025, 6, 30),
            end_date=date(2025, 6, 1),
            db_path=tmp_path / "x.duckdb",
        )


async def test_backfill_weather_per_station_failure_tolerated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If one station's fetch raises, the rest still process and write."""

    class _FakeClient:
        async def __aenter__(self) -> _FakeClient:
            return self

        async def __aexit__(self, *_exc: object) -> None:
            pass

        async def fetch_historical_deterministic(
            self,
            station: object,
            *,
            start_date: date,
            end_date: date,
        ) -> list[EnsembleForecast]:
            station_icao = getattr(station, "icao", str(station))
            if station_icao == "KMIA":
                raise RuntimeError("simulated 502 from upstream")
            n_days = (end_date - start_date).days + 1
            return [
                _ens_row(
                    station=station_icao,
                    valid_date=date.fromordinal(start_date.toordinal() + i),
                )
                for i in range(n_days)
            ]

    monkeypatch.setattr(backfill_weather_flow, "OpenMeteoClient", _FakeClient)
    db = tmp_path / "bw.duckdb"
    bootstrap(db)

    n = await backfill_weather_flow.backfill(
        start_date=date(2025, 6, 1),
        end_date=date(2025, 6, 3),
        db_path=db,
    )
    # 6 stations, 1 fails -> 5 stations x 3 days = 15 rows
    assert n == 15


# ---------------------------------------------------------- backfill_observed


async def test_backfill_observed_rejects_bad_date_range(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="precedes"):
        await backfill_observed_flow.backfill(
            start_date=date(2025, 6, 30),
            end_date=date(2025, 6, 1),
            db_path=tmp_path / "x.duckdb",
        )
