"""End-to-end tests for `kq.flows.paper_trade.run_once`.

These tests exercise the full paper-trade orchestration pipeline with mocked
Kalshi market data and synthetic forecasts seeded into a tmp DuckDB. They
guard the wiring between:

    forecast lookup → router dispatch → bracket generation → market match
    → executor evaluation → repository insert → settlement pass

The Kalshi credential path is intercepted (no real network call). The router
is built on the fly so we don't need any pickled NGR models on disk — see
`_write_router_config_with_pickles` for the fixture setup.
"""

from __future__ import annotations

import json
import pickle
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from kq.clients.kalshi import Market
from kq.clients.kalshi._ticker_parser import build_weather_market_ticker
from kq.clients.stations import STATIONS
from kq.flows import paper_trade as paper_trade_flow
from kq.flows.paper_trade import PaperRunSummary, run_once
from kq.flows.paper_trade import main as run_paper_main
from kq.models.weather_ngr import NGRParameters, WeatherNGRModel
from kq.storage.duckdb_store import bootstrap, connect

FORECAST_AS_OF = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)
TARGET_DATE = date(2026, 4, 30)


def _seed_forecast(
    db_path: Path,
    *,
    station: str,
    valid_date: date,
    forecast_high_f: float,
    n_members: int = 30,
) -> None:
    """Insert n_members ensemble rows that average to forecast_high_f."""
    bootstrap(db_path)
    con = connect(db_path)
    try:
        for i in range(n_members):
            jitter = (i - n_members / 2) * 0.1  # tight spread around the mean
            con.execute(
                """
                INSERT INTO weather_forecast
                (as_of, run_time, model, member, station, valid_date,
                 forecast_high_f, forecast_low_f)
                VALUES (?, ?, 'gefs', ?, ?, ?, ?, NULL)
                """,
                [
                    FORECAST_AS_OF,
                    FORECAST_AS_OF,
                    i,
                    station,
                    valid_date,
                    forecast_high_f + jitter,
                ],
            )
    finally:
        con.close()


def _make_market(
    ticker: str,
    *,
    yes_bid: float,
    yes_ask: float,
    open_time: datetime | None = None,
) -> Market:
    return Market(
        ticker=ticker,
        event_ticker=ticker.rsplit("-", 1)[0],
        title=f"market {ticker}",
        status="active",
        category="WEATHER",
        yes_ask=yes_ask,
        yes_bid=yes_bid,
        last_price=0.5 * (yes_bid + yes_ask),
        volume=100,
        open_interest=50,
        open_time=open_time,
        close_time=None,
        expected_expiration_time=None,
        rules_primary=None,
    )


def _write_router_config_with_pickles(
    *,
    models_dir: Path,
    station: str,
    use_ngr: bool,
) -> Path:
    """Write a router_config.json + matching NGR pickle when needed."""
    models_dir.mkdir(parents=True, exist_ok=True)
    config_path = models_dir / "router_config.json"
    config_path.write_text(
        json.dumps(
            {
                "generated_at": "2026-04-28T00:00:00+00:00",
                "decision_threshold_pct": 1.0,
                "decisions": {
                    station: {
                        "strategy": "ngr" if use_ngr else "raw",
                        "brier_improvement_pct": 5.0 if use_ngr else 0.0,
                        "raw_residual_std_f": 3.5,
                        "reason": "test",
                    }
                },
            }
        )
    )
    if use_ngr:
        pickle_path = models_dir / f"weather_ngr_{station}_lead1.pkl"
        # Identity NGR (a=0, b=1, c=12.25=3.5^2) so model probs match raw pricing closely.
        ngr = WeatherNGRModel(params=NGRParameters(a=0.0, b=1.0, c=12.25, d=0.0))
        with pickle_path.open("wb") as fh:
            pickle.dump(ngr, fh)
    return config_path


def _settings_with_db(db_path: Path) -> object:
    """Build a Settings-like sentinel that points the flow at the tmp DB."""

    class _S:
        database_url = f"duckdb:///{db_path}"
        kalshi_api_key_id = "test"

    return _S()


# ----------------------------------------------------- happy path: end-to-end


def test_run_once_records_paper_trade_when_edge_present(tmp_path: Path) -> None:
    """Forecast 80F, market for T74 priced way too low → BUY_YES recorded.

    ``generate_brackets(80.0)`` emits {74, 76, 78, 80, 82, 84, 86} so we seed
    a Kalshi market at T74 (deeply ITM relative to forecast) at 0.20 ask.
    Raw Gaussian P(T>74 | mean=80, sigma=3.5) is roughly 0.96 -> edge vs the
    0.20 ask is about 76 percentage points.
    """
    db = tmp_path / "paper.duckdb"
    models_dir = tmp_path / "models"
    _seed_forecast(db, station="KLAX", valid_date=TARGET_DATE, forecast_high_f=80.0)
    _write_router_config_with_pickles(models_dir=models_dir, station="KLAX", use_ngr=False)

    markets = [
        _make_market(
            build_weather_market_ticker("KLAX", TARGET_DATE, 74),
            yes_bid=0.18,
            yes_ask=0.20,  # huge underprice vs 80F forecast
        ),
        _make_market(
            build_weather_market_ticker("KLAX", TARGET_DATE, 80),
            yes_bid=0.45,
            yes_ask=0.50,  # roughly fair near the mode → no trade
        ),
    ]

    async def _fake_pull(_settings: object) -> dict[str, list[Market]]:
        return {"KXHIGHLAX": markets}

    with patch("kq.flows.paper_trade._pull_kalshi_markets", _fake_pull):
        summary = run_once(
            db_path=db,
            router_config_path=models_dir / "router_config.json",
            models_dir=models_dir,
            target_date=TARGET_DATE,
        )

    assert isinstance(summary, PaperRunSummary)
    assert summary.skipped_reason is None
    assert summary.submit_recorded >= 1, "T74 was severely underpriced — should trade"

    # Verify a paper_trade row landed for T74 specifically
    con = connect(db)
    try:
        rows = con.execute(
            "SELECT ticker, side, qty FROM paper_trade WHERE settled_at IS NULL"
        ).fetchall()
    finally:
        con.close()
    tickers = {r[0] for r in rows}
    assert build_weather_market_ticker("KLAX", TARGET_DATE, 74) in tickers


def test_run_once_settles_after_truth_lands(tmp_path: Path) -> None:
    """Submit pass records a trade, then truth lands, then settle pass closes it."""
    db = tmp_path / "paper.duckdb"
    models_dir = tmp_path / "models"
    _seed_forecast(db, station="KLAX", valid_date=TARGET_DATE, forecast_high_f=80.0)
    _write_router_config_with_pickles(models_dir=models_dir, station="KLAX", use_ngr=False)

    markets = [
        _make_market(
            build_weather_market_ticker("KLAX", TARGET_DATE, 74),
            yes_bid=0.18,
            yes_ask=0.20,
        )
    ]

    async def _fake_pull(_settings: object) -> dict[str, list[Market]]:
        return {"KXHIGHLAX": markets}

    with patch("kq.flows.paper_trade._pull_kalshi_markets", _fake_pull):
        first = run_once(
            db_path=db,
            router_config_path=models_dir / "router_config.json",
            models_dir=models_dir,
            target_date=TARGET_DATE,
        )
    assert first.submit_recorded >= 1
    assert first.settle_processed == 0  # no truth yet

    # Now truth lands
    con = connect(db)
    try:
        con.execute(
            """
            INSERT INTO weather_observed
            (station, valid_date, high_f, low_f, source, fetched_at)
            VALUES ('KLAX', ?, 82.0, NULL, 'test', ?)
            """,
            [TARGET_DATE, datetime.now(tz=UTC).replace(tzinfo=None)],
        )
    finally:
        con.close()

    # Second pass: re-running submit is idempotent, settle picks up the truth
    with patch("kq.flows.paper_trade._pull_kalshi_markets", _fake_pull):
        second = run_once(
            db_path=db,
            router_config_path=models_dir / "router_config.json",
            models_dir=models_dir,
            target_date=TARGET_DATE,
        )
    assert second.settle_processed == first.submit_recorded
    # Idempotent submit — no new trades
    assert second.submit_recorded == 0


# ----------------------------------------------------- defensive paths


def test_run_once_skips_when_router_config_missing(tmp_path: Path) -> None:
    """No router config → submit pass skipped with reason; settle still runs."""
    db = tmp_path / "paper.duckdb"
    models_dir = tmp_path / "models"
    _seed_forecast(db, station="KLAX", valid_date=TARGET_DATE, forecast_high_f=80.0)

    async def _fake_pull(_settings: object) -> dict[str, list[Market]]:
        return {}  # never reached

    with patch("kq.flows.paper_trade._pull_kalshi_markets", _fake_pull):
        summary = run_once(
            db_path=db,
            router_config_path=models_dir / "missing.json",
            models_dir=models_dir,
            target_date=TARGET_DATE,
        )
    assert summary.skipped_reason == "no_router_config"
    assert summary.submit_recorded == 0
    assert summary.settle_processed == 0


def test_run_once_no_markets_returns_zero_recorded(tmp_path: Path) -> None:
    """Kalshi returns no markets → 0 trades, no error."""
    db = tmp_path / "paper.duckdb"
    models_dir = tmp_path / "models"
    _seed_forecast(db, station="KLAX", valid_date=TARGET_DATE, forecast_high_f=80.0)
    _write_router_config_with_pickles(models_dir=models_dir, station="KLAX", use_ngr=False)

    async def _empty_pull(_settings: object) -> dict[str, list[Market]]:
        return {"KXHIGHLAX": []}

    with patch("kq.flows.paper_trade._pull_kalshi_markets", _empty_pull):
        summary = run_once(
            db_path=db,
            router_config_path=models_dir / "router_config.json",
            models_dir=models_dir,
            target_date=TARGET_DATE,
        )
    assert summary.submit_recorded == 0
    assert summary.skipped_reason is None


def test_run_once_no_forecasts_returns_zero(tmp_path: Path) -> None:
    """No forecasts in DB for target_date → submit early-exits with 0."""
    db = tmp_path / "paper.duckdb"
    models_dir = tmp_path / "models"
    bootstrap(db)  # empty DB
    _write_router_config_with_pickles(models_dir=models_dir, station="KLAX", use_ngr=False)

    async def _fake_pull(_settings: object) -> dict[str, list[Market]]:
        return {"KXHIGHLAX": []}

    with patch("kq.flows.paper_trade._pull_kalshi_markets", _fake_pull):
        summary = run_once(
            db_path=db,
            router_config_path=models_dir / "router_config.json",
            models_dir=models_dir,
            target_date=TARGET_DATE,
        )
    assert summary.submit_recorded == 0
    assert summary.submit_evaluated == 0


def test_run_once_settle_only_skips_submit(tmp_path: Path) -> None:
    """`settle_only=True` short-circuits before any Kalshi call."""
    db = tmp_path / "paper.duckdb"
    models_dir = tmp_path / "models"
    _seed_forecast(db, station="KLAX", valid_date=TARGET_DATE, forecast_high_f=80.0)
    _write_router_config_with_pickles(models_dir=models_dir, station="KLAX", use_ngr=False)
    pull_called = False

    async def _track(_settings: object) -> dict[str, list[Market]]:
        nonlocal pull_called
        pull_called = True
        return {}

    with patch("kq.flows.paper_trade._pull_kalshi_markets", _track):
        summary = run_once(
            db_path=db,
            router_config_path=models_dir / "router_config.json",
            models_dir=models_dir,
            target_date=TARGET_DATE,
            settle_only=True,
        )
    assert pull_called is False, "settle-only must not contact Kalshi"
    assert summary.submit_evaluated == 0
    assert summary.settle_processed == 0


# ----------------------------------------------------- bankroll snapshot


def test_run_once_bankroll_includes_settled_pnl(tmp_path: Path) -> None:
    """Snapshot bankroll = starting + sum of settled pnl at start of run."""
    db = tmp_path / "paper.duckdb"
    bootstrap(db)
    # Seed a settled trade with +$10 pnl
    con = connect(db)
    try:
        signal_id = "sig-pre-existing"
        trade_id = "paper-pre-existing"
        as_of = datetime(2026, 4, 27, tzinfo=UTC).replace(tzinfo=None)
        con.execute(
            """
            INSERT INTO signal (signal_id, as_of, ticker, model_prob_yes, market_prob_yes,
                                edge_bps, model_name, source_urls, reasoning)
            VALUES (?, ?, 'KXHIGHLAX-26APR29-T70', 0.7, 0.5, 2000, 'test', [], NULL)
            """,
            [signal_id, as_of],
        )
        con.execute(
            """
            INSERT INTO paper_trade (trade_id, signal_id, submitted_at, ticker, side,
                                     limit_price, qty, fee_usd, filled_at, fill_price,
                                     settled_at, settlement, pnl_usd)
            VALUES (?, ?, ?, 'KXHIGHLAX-26APR29-T70', 'BUY_YES', 0.50, 10, 0.20,
                    ?, 0.50, ?, 'YES', 10.0)
            """,
            [trade_id, signal_id, as_of, as_of, as_of + timedelta(days=1)],
        )
    finally:
        con.close()

    async def _fake_pull(_settings: object) -> dict[str, list[Market]]:
        return {}

    with patch("kq.flows.paper_trade._pull_kalshi_markets", _fake_pull):
        summary = run_once(
            db_path=db,
            router_config_path=tmp_path / "missing.json",  # skip submit
            models_dir=tmp_path / "models",
            starting_bankroll_usd=1_000.0,
            target_date=TARGET_DATE,
        )
    assert summary.bankroll_snapshot_usd == pytest.approx(1_010.0)


# ----------------------------------------------------- nowcast integration


def _seed_metar(
    db_path: Path,
    *,
    station: str,
    obs: list[tuple[datetime, float]],
) -> None:
    """Insert METAR rows into a (presumably already bootstrapped) DB."""
    con = connect(db_path)
    try:
        for ts, temp in obs:
            con.execute(
                """
                INSERT OR REPLACE INTO metar_obs
                (obs_time, station, temp_f, dewpoint_f, wind_kt, pressure_mb)
                VALUES (?, ?, ?, NULL, NULL, NULL)
                """,
                [ts.replace(tzinfo=None), station, temp],
            )
    finally:
        con.close()


def test_nowcast_locks_yes_when_today_already_above_threshold(tmp_path: Path) -> None:
    """Today's METAR has 90F observed; T74 ticker → P(YES) = 0.99 regardless of prior."""
    db = tmp_path / "paper.duckdb"
    models_dir = tmp_path / "models"
    today = TARGET_DATE  # treat target as "today"
    _seed_forecast(db, station="KLAX", valid_date=today, forecast_high_f=80.0)
    _write_router_config_with_pickles(models_dir=models_dir, station="KLAX", use_ngr=False)

    # KLAX LST window for today: 08:00 UTC today → 08:00 UTC tomorrow
    in_window = datetime(2026, 4, 30, 21, 0, tzinfo=UTC)  # 13:00 LAX
    _seed_metar(db, station="KLAX", obs=[(in_window, 90.0)])

    markets = [
        _make_market(
            build_weather_market_ticker("KLAX", today, 74),
            yes_bid=0.40,
            yes_ask=0.45,
        )
    ]

    async def _fake_pull(_settings: object) -> dict[str, list[Market]]:
        return {"KXHIGHLAX": markets}

    now = datetime(2026, 4, 30, 22, 0, tzinfo=UTC)  # after the obs
    with patch("kq.flows.paper_trade._pull_kalshi_markets", _fake_pull):
        summary = run_once(
            db_path=db,
            router_config_path=models_dir / "router_config.json",
            models_dir=models_dir,
            target_date=today,
            now_utc=now,
        )

    # 90F observed, T74 — locked YES → 0.99 prob, market at 0.45 → big edge → trade
    assert summary.submit_recorded >= 1
    con = connect(db)
    try:
        row = con.execute("SELECT model_prob_yes FROM signal WHERE ticker LIKE '%T74'").fetchone()
    finally:
        con.close()
    assert row is not None
    # Locked → 0.99 cap exactly
    assert row[0] == pytest.approx(0.99, abs=1e-6)


def test_no_nowcast_falls_back_to_router_only(tmp_path: Path) -> None:
    """`use_nowcast=False` → hot METAR observation does NOT lock YES."""
    db = tmp_path / "paper.duckdb"
    models_dir = tmp_path / "models"
    _seed_forecast(db, station="KLAX", valid_date=TARGET_DATE, forecast_high_f=80.0)
    _write_router_config_with_pickles(models_dir=models_dir, station="KLAX", use_ngr=False)
    in_window = datetime(2026, 4, 30, 21, 0, tzinfo=UTC)
    _seed_metar(db, station="KLAX", obs=[(in_window, 95.0)])

    markets = [
        _make_market(
            build_weather_market_ticker("KLAX", TARGET_DATE, 80),
            yes_bid=0.45,
            yes_ask=0.50,  # roughly fair vs raw forecast 80F
        )
    ]

    async def _fake_pull(_settings: object) -> dict[str, list[Market]]:
        return {"KXHIGHLAX": markets}

    now = datetime(2026, 4, 30, 22, 0, tzinfo=UTC)
    with patch("kq.flows.paper_trade._pull_kalshi_markets", _fake_pull):
        summary_off = run_once(
            db_path=db,
            router_config_path=models_dir / "router_config.json",
            models_dir=models_dir,
            target_date=TARGET_DATE,
            now_utc=now,
            use_nowcast=False,
        )
    # With nowcast off, the model_prob is just SF(80; 80, 3.5) = 0.5 — no edge vs 0.45/0.50
    # spread, so no trade should land.
    con = connect(db)
    try:
        recorded_off = con.execute("SELECT COUNT(*) FROM paper_trade").fetchone()
    finally:
        con.close()
    assert summary_off.submit_recorded == 0
    assert recorded_off is not None and recorded_off[0] == 0


def test_nowcast_default_on_in_main(tmp_path: Path) -> None:
    """The CLI defaults `use_nowcast=True`; smoke check via main()."""
    db = tmp_path / "paper.duckdb"
    bootstrap(db)
    with patch("kq.flows.paper_trade.get_settings", return_value=_settings_with_db(db)):
        rc = run_paper_main(settle_only=True)
    assert rc == 0


def test_nowcast_no_metar_data_keeps_router_behavior(tmp_path: Path) -> None:
    """With no METAR seeded, nowcast layer is inert — same trade decision as use_nowcast=False."""
    db = tmp_path / "paper.duckdb"
    models_dir = tmp_path / "models"
    _seed_forecast(db, station="KLAX", valid_date=TARGET_DATE, forecast_high_f=80.0)
    _write_router_config_with_pickles(models_dir=models_dir, station="KLAX", use_ngr=False)
    # NO METAR seeded.

    markets = [
        _make_market(
            build_weather_market_ticker("KLAX", TARGET_DATE, 74),
            yes_bid=0.18,
            yes_ask=0.20,  # huge underprice
        )
    ]

    async def _fake_pull(_settings: object) -> dict[str, list[Market]]:
        return {"KXHIGHLAX": markets}

    now = datetime(2026, 4, 30, 22, 0, tzinfo=UTC)
    with patch("kq.flows.paper_trade._pull_kalshi_markets", _fake_pull):
        on = run_once(
            db_path=db,
            router_config_path=models_dir / "router_config.json",
            models_dir=models_dir,
            target_date=TARGET_DATE,
            now_utc=now,
            use_nowcast=True,
        )
    # Identical model_prob path as use_nowcast=False because no obs to update with
    assert on.submit_recorded >= 1


# ----------------------------------------------------- CLI surface


def test_main_returns_zero_exit_code(tmp_path: Path) -> None:
    """`run_paper_trade(...)` returns 0 when nothing to do (cron-friendly)."""
    db = tmp_path / "paper.duckdb"
    bootstrap(db)
    # Patch settings so the flow uses our tmp DB
    with patch("kq.flows.paper_trade.get_settings", return_value=_settings_with_db(db)):
        rc = run_paper_main(settle_only=True)
    assert rc == 0


# ----------------------------------------------------- _pull_kalshi_markets


async def test_pull_kalshi_markets_queries_by_series_ticker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_pull_kalshi_markets` must query each station by SERIES ticker, never
    event_ticker (the prod bug — see fix/kalshi-series-ticker-ingest). The other
    paper-flow tests patch this function out, so this is its only direct
    coverage. Drives the real body with a fake KalshiClient (no network)."""
    seen: list[tuple[str | None, str | None]] = []

    class _FakeClient:
        async def __aenter__(self) -> _FakeClient:
            return self

        async def __aexit__(self, *_exc: object) -> None:
            pass

        async def list_markets(
            self, *, event_ticker: str | None = None, series_ticker: str | None = None
        ) -> list[Market]:
            seen.append((event_ticker, series_ticker))
            return [_make_market(f"{series_ticker}-26MAY31-T70", yes_bid=0.40, yes_ask=0.42)]

        @classmethod
        def from_settings(cls, *_a: object, **_k: object) -> _FakeClient:
            return cls()

    monkeypatch.setattr(paper_trade_flow, "KalshiClient", _FakeClient)
    out = await paper_trade_flow._pull_kalshi_markets(object())

    expected = [s.kalshi_series_ticker for s in STATIONS]
    # Every query used series_ticker; none used event_ticker.
    assert [s for _e, s in seen] == expected
    assert all(e is None for e, _s in seen)
    # Result is keyed by series ticker, one market each.
    assert set(out) == set(expected)
    assert all(len(v) == 1 for v in out.values())
