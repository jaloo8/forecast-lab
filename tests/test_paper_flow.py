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

import dataclasses
import json
import math
import pickle
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from scipy import stats

from kq.clients.kalshi import KalshiCredentialsError, Market
from kq.clients.kalshi._ticker_parser import build_weather_market_ticker
from kq.clients.stations import STATIONS
from kq.flows import paper_trade as paper_trade_flow
from kq.flows.paper_trade import PaperRunSummary, run_once
from kq.flows.paper_trade import main as run_paper_main
from kq.models.nowcast import NowcastState
from kq.models.router import StrategyRouter
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


def _seed_forecast_members(
    db_path: Path,
    *,
    station: str,
    valid_date: date,
    members_by_model: dict[str, list[float]],
    as_of: datetime = FORECAST_AS_OF,
) -> None:
    """Insert explicit per-model member values as one batch (shared as_of)."""
    bootstrap(db_path)
    con = connect(db_path)
    try:
        for model, values in members_by_model.items():
            for i, value in enumerate(values):
                con.execute(
                    """
                    INSERT INTO weather_forecast
                    (as_of, run_time, model, member, station, valid_date,
                     forecast_high_f, forecast_low_f)
                    VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                    """,
                    [as_of, as_of, model, i, station, valid_date, value],
                )
    finally:
        con.close()


def _make_market(
    ticker: str,
    *,
    yes_bid: float,
    yes_ask: float,
    open_time: datetime | None = None,
    strike_type: str | None = None,
    floor_strike: float | None = None,
    cap_strike: float | None = None,
) -> Market:
    """Build a market fixture. Pass strike fields for prod-shaped payloads;
    omit them to model the demo environment (legacy, no strike fields)."""
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
        strike_type=strike_type,
        floor_strike=floor_strike,
        cap_strike=cap_strike,
    )


def _make_greater_market(
    ticker: str,
    *,
    threshold: float,
    yes_bid: float,
    yes_ask: float,
) -> Market:
    """Prod-shaped greater market whose API strike fields match the ticker."""
    return _make_market(
        ticker,
        yes_bid=yes_bid,
        yes_ask=yes_ask,
        strike_type="greater",
        floor_strike=float(threshold),
    )


def _write_router_config_with_pickles(
    *,
    models_dir: Path,
    station: str,
    use_ngr: bool,
    ngr_params: NGRParameters | None = None,
) -> Path:
    """Write a router_config.json + matching NGR pickle when needed.

    ``ngr_params`` overrides the default identity/degenerate NGR — pass a
    full-form (d > 0) parameter set to exercise the spread-aware sigma path.
    """
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
        params = ngr_params or NGRParameters(a=0.0, b=1.0, c=12.25, d=0.0)
        ngr = WeatherNGRModel(params=params)
        with pickle_path.open("wb") as fh:
            pickle.dump(ngr, fh)
    return config_path


def _settings_with_db(db_path: Path, *, kalshi_env: str = "demo") -> object:
    """Build a Settings-like sentinel that points the flow at the tmp DB."""

    class _S:
        database_url = f"duckdb:///{db_path}"
        kalshi_api_key_id = "test"

    _S.kalshi_env = kalshi_env  # type: ignore[attr-defined]
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
        _make_greater_market(
            build_weather_market_ticker("KLAX", TARGET_DATE, 74),
            threshold=74.0,
            yes_bid=0.18,
            yes_ask=0.20,  # huge underprice vs 80F forecast
        ),
        _make_greater_market(
            build_weather_market_ticker("KLAX", TARGET_DATE, 80),
            threshold=80.0,
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
        _make_greater_market(
            build_weather_market_ticker("KLAX", TARGET_DATE, 74),
            threshold=74.0,
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


def test_submit_pass_legacy_fallback_gated_by_kalshi_env(tmp_path: Path) -> None:
    """PR-H: markets WITHOUT API strike fields (legacy/demo payload shape)
    are tradeable only under KALSHI_ENV=demo. Under prod settings the same
    book is refused wholesale — strike-field payload drift on prod must fail
    closed instead of silently reviving the T-as-greater guess (the
    inverted-less bug PR-B killed)."""
    legacy_markets = [
        _make_market(  # deep underprice vs 80F forecast, but NO strike fields
            build_weather_market_ticker("KLAX", TARGET_DATE, 74),
            yes_bid=0.18,
            yes_ask=0.20,
        )
    ]

    async def _fake_pull(_settings: object) -> dict[str, list[Market]]:
        return {"KXHIGHLAX": legacy_markets}

    def _run(env: str, db: Path) -> PaperRunSummary:
        models_dir = tmp_path / f"models_{env}"
        _seed_forecast(db, station="KLAX", valid_date=TARGET_DATE, forecast_high_f=80.0)
        _write_router_config_with_pickles(models_dir=models_dir, station="KLAX", use_ngr=False)
        with (
            patch("kq.flows.paper_trade._pull_kalshi_markets", _fake_pull),
            patch(
                "kq.flows.paper_trade.get_settings",
                return_value=_settings_with_db(db, kalshi_env=env),
            ),
        ):
            return run_once(
                db_path=db,
                router_config_path=models_dir / "router_config.json",
                models_dir=models_dir,
                target_date=TARGET_DATE,
            )

    prod = _run("prod", tmp_path / "prod.duckdb")
    assert prod.submit_evaluated == 0, "prod must refuse strike-field-less markets"
    assert prod.submit_recorded == 0

    demo = _run("demo", tmp_path / "demo.duckdb")
    assert demo.submit_recorded >= 1, "demo keeps the legacy T-as-greater fallback"


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
        _make_greater_market(
            build_weather_market_ticker("KLAX", today, 74),
            threshold=74.0,
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
        _make_greater_market(
            build_weather_market_ticker("KLAX", TARGET_DATE, 80),
            threshold=80.0,
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
        _make_greater_market(
            build_weather_market_ticker("KLAX", TARGET_DATE, 74),
            threshold=74.0,
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


# ----------------------------------------------------- PR-B: prod-style strike ladder


def test_run_once_trades_between_and_less_markets_with_correct_sides(
    tmp_path: Path,
) -> None:
    """PR-B e2e: a prod-shaped ladder (between + less markets with API strike
    fields) is priced and traded. The less market is the audit-#3 regression:
    forecast 75F makes '<72F' unlikely (~16%), so against a 0.70 bid the flow
    must BUY_NO — the legacy greater-misread (P(T>72) ~ 80%) would have
    bought YES on the same quote, the exactly-inverted side."""

    db = tmp_path / "paper.duckdb"
    models_dir = tmp_path / "models"
    _seed_forecast(db, station="KLAX", valid_date=TARGET_DATE, forecast_high_f=75.0)
    _write_router_config_with_pickles(models_dir=models_dir, station="KLAX", use_ngr=False)

    between_ticker = "KXHIGHLAX-26APR30-B74.5"
    less_ticker = build_weather_market_ticker("KLAX", TARGET_DATE, 72)
    markets = [
        dataclasses.replace(
            # True P(74-75F | mu=75, sigma=3.5) ~ 0.22; ask 0.10 -> big YES edge.
            _make_market(between_ticker, yes_bid=0.08, yes_ask=0.10),
            strike_type="between",
            floor_strike=74.0,
            cap_strike=75.0,
        ),
        dataclasses.replace(
            # True P(<72F | mu=75, sigma=3.5) ~ 0.16; bid 0.70 -> big NO edge.
            _make_market(less_ticker, yes_bid=0.70, yes_ask=0.75),
            strike_type="less",
            cap_strike=72.0,
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
            use_nowcast=False,
        )

    assert summary.submit_recorded == 2

    con = connect(db)
    try:
        rows = con.execute(
            """
            SELECT ticker, side, strike_type, floor_strike, cap_strike
            FROM paper_trade ORDER BY ticker
            """
        ).fetchall()
    finally:
        con.close()
    by_ticker = {r[0]: r for r in rows}

    b_row = by_ticker[between_ticker]
    assert b_row[1] == "BUY_YES"
    assert (b_row[2], b_row[3], b_row[4]) == ("between", 74.0, 75.0)

    l_row = by_ticker[less_ticker]
    assert l_row[1] == "BUY_NO", "less market must trade the NO side here"
    assert (l_row[2], l_row[4]) == ("less", 72.0)


# ----------------------------------------------------- lock scope (2026-07-01 audit)


def test_run_once_fetches_markets_before_opening_db(tmp_path: Path) -> None:
    """The DuckDB write lock must never be held across Kalshi network I/O:
    run_once pulls the live book FIRST, then opens the connection only
    around the DB work (pre-audit, connect() happened before the async
    fetch and the every-minute ingest cron deterministically collided)."""
    db = tmp_path / "paper.duckdb"
    models_dir = tmp_path / "models"
    _seed_forecast(db, station="KLAX", valid_date=TARGET_DATE, forecast_high_f=80.0)
    _write_router_config_with_pickles(models_dir=models_dir, station="KLAX", use_ngr=False)

    order: list[str] = []

    async def _tracking_pull(_settings: object) -> dict[str, list[Market]]:
        order.append("fetch")
        return {"KXHIGHLAX": []}

    real_connect = paper_trade_flow.connect

    def _tracking_connect(path: Path, **kwargs: object) -> object:
        order.append("connect")
        return real_connect(path, **kwargs)  # type: ignore[arg-type]

    with (
        patch("kq.flows.paper_trade._pull_kalshi_markets", _tracking_pull),
        patch("kq.flows.paper_trade.connect", _tracking_connect),
    ):
        run_once(
            db_path=db,
            router_config_path=models_dir / "router_config.json",
            models_dir=models_dir,
            target_date=TARGET_DATE,
        )
    assert order == ["fetch", "connect"], (
        f"Kalshi fetch must complete before the DB lock is taken; got {order}"
    )


def test_run_once_skips_submit_when_credentials_missing(tmp_path: Path) -> None:
    """KalshiCredentialsError from the pre-connect fetch reports the
    'no_kalshi_creds' skip reason and still runs the settle pass."""
    db = tmp_path / "paper.duckdb"
    models_dir = tmp_path / "models"
    bootstrap(db)
    _write_router_config_with_pickles(models_dir=models_dir, station="KLAX", use_ngr=False)

    async def _raise(_settings: object) -> dict[str, list[Market]]:
        raise KalshiCredentialsError("KALSHI_API_KEY_ID is empty")

    with patch("kq.flows.paper_trade._pull_kalshi_markets", _raise):
        summary = run_once(
            db_path=db,
            router_config_path=models_dir / "router_config.json",
            models_dir=models_dir,
            target_date=TARGET_DATE,
        )
    assert summary.skipped_reason == "no_kalshi_creds"
    assert summary.submit_evaluated == 0
    assert summary.settle_processed == 0  # settle pass still ran (nothing due)


# ----------------------------------------------------- Phase A1: ens_var threading
#
# The trained NGR pickles are full-form (sigma^2 = c + d*ens_var, d > 0). The
# live flow historically called router.predict_proba/predict_distribution
# WITHOUT ens_var, so sigma silently collapsed to sqrt(c) — live probabilities
# were overconfident vs the backtest (June audit finding 'ngr-ens-var-dropped').
# These tests pin the fix: the pooled batch variance now reaches both router
# call paths, and the ens_var=None fallback stays byte-identical to before.

FULL_FORM_PARAMS = NGRParameters(a=0.0, b=1.0, c=4.0, d=0.5)


def _clipped_sf(threshold: float, *, mu: float, sigma: float) -> float:
    return float(np.clip(stats.norm.sf(threshold, loc=mu, scale=sigma), 0.01, 0.99))


def _run_flow_and_read_prob(
    db: Path, models_dir: Path, markets: list[Market], *, ticker_suffix: str
) -> float:
    async def _fake_pull(_settings: object) -> dict[str, list[Market]]:
        return {"KXHIGHLAX": markets}

    with patch("kq.flows.paper_trade._pull_kalshi_markets", _fake_pull):
        summary = run_once(
            db_path=db,
            router_config_path=models_dir / "router_config.json",
            models_dir=models_dir,
            target_date=TARGET_DATE,
            use_nowcast=False,
        )
    assert summary.submit_recorded >= 1
    con = connect(db)
    try:
        row = con.execute(
            "SELECT model_prob_yes FROM signal WHERE ticker LIKE ?", [f"%{ticker_suffix}"]
        ).fetchone()
    finally:
        con.close()
    assert row is not None
    return float(row[0])


def test_latest_forecasts_pool_variance_of_latest_batch_only(tmp_path: Path) -> None:
    """`_latest_forecasts_for` must return the pooled cross-member variance of
    the latest as_of batch (GEFS + ECMWF union), ignoring stale batches; the
    mean keeps the historical first-row (model asc) selection."""
    db = tmp_path / "paper.duckdb"
    stale_as_of = FORECAST_AS_OF - timedelta(hours=6)
    _seed_forecast_members(
        db,
        station="KLAX",
        valid_date=TARGET_DATE,
        members_by_model={"gefs": [999.0, 100.0]},  # would explode the var if leaked
        as_of=stale_as_of,
    )
    members = {"gefs": [78.0, 80.0, 82.0], "ecmwf": [79.0, 81.0, 83.0, 85.0]}
    _seed_forecast_members(db, station="KLAX", valid_date=TARGET_DATE, members_by_model=members)

    con = connect(db)
    try:
        out = paper_trade_flow._latest_forecasts_for(con, target_date=TARGET_DATE)
    finally:
        con.close()

    fc = out["KLAX"]
    assert fc.ens_mean_f == pytest.approx(82.0)  # 'ecmwf' < 'gefs' → its mean wins the tie
    union = [v for values in members.values() for v in values]
    assert fc.ens_var_f2 == pytest.approx(float(np.var(np.asarray(union), ddof=1)))


def test_latest_forecasts_single_member_has_unknown_ens_var(tmp_path: Path) -> None:
    """A 1-member batch has UNKNOWN spread → ens_var_f2 is None, never 0.0."""
    db = tmp_path / "paper.duckdb"
    _seed_forecast_members(
        db, station="KLAX", valid_date=TARGET_DATE, members_by_model={"gefs": [80.0]}
    )
    con = connect(db)
    try:
        out = paper_trade_flow._latest_forecasts_for(con, target_date=TARGET_DATE)
    finally:
        con.close()
    fc = out["KLAX"]
    assert fc.ens_mean_f == pytest.approx(80.0)
    assert fc.ens_var_f2 is None


def test_full_form_ngr_prob_tracks_batch_spread(tmp_path: Path) -> None:
    """E2E regression for 'ngr-ens-var-dropped': with a full-form pickle
    (d > 0), a low-spread and a high-spread multi-member batch MUST price the
    same market differently. Pre-fix both collapsed to sigma = sqrt(c) and
    produced the identical probability."""
    low_members = {"gefs": [79.0, 80.0, 81.0], "ecmwf": [79.5, 80.0, 80.5]}
    high_members = {"gefs": [70.0, 80.0, 90.0], "ecmwf": [65.0, 80.0, 95.0]}

    probs: dict[str, float] = {}
    for name, members in (("low", low_members), ("high", high_members)):
        db = tmp_path / f"{name}.duckdb"
        models_dir = tmp_path / f"models_{name}"
        _seed_forecast_members(
            db, station="KLAX", valid_date=TARGET_DATE, members_by_model=members
        )
        _write_router_config_with_pickles(
            models_dir=models_dir, station="KLAX", use_ngr=True, ngr_params=FULL_FORM_PARAMS
        )
        markets = [
            _make_greater_market(
                build_weather_market_ticker("KLAX", TARGET_DATE, 74),
                threshold=74.0,
                yes_bid=0.18,
                yes_ask=0.20,
            )
        ]
        probs[name] = _run_flow_and_read_prob(db, models_dir, markets, ticker_suffix="T74")

    assert probs["low"] != probs["high"], (
        "low- and high-spread batches must price differently once ens_var is threaded "
        "(pre-fix both collapsed to sqrt(c))"
    )
    assert probs["high"] < probs["low"], "more spread → fatter sigma → less confident YES"

    # The high-spread prob must equal the full-form sigma computed from the
    # pooled (ddof=1) variance of the member union — first-principles check.
    # Greater strikes price at floor + 0.5 (whole-°F settlement, strikes.py).
    union = [v for values in high_members.values() for v in values]
    pooled_var = float(np.var(np.asarray(union), ddof=1))
    sigma = math.sqrt(FULL_FORM_PARAMS.c + FULL_FORM_PARAMS.d * pooled_var)
    assert probs["high"] == pytest.approx(_clipped_sf(74.5, mu=80.0, sigma=sigma), abs=1e-9)


def test_ens_var_none_path_keeps_sqrt_c_sigma(tmp_path: Path) -> None:
    """Backward compat: a batch with no measurable spread (single member)
    yields ens_var=None and the full-form pickle degrades to sigma = sqrt(c) —
    exactly the pre-fix pricing."""
    db = tmp_path / "paper.duckdb"
    models_dir = tmp_path / "models"
    _seed_forecast_members(
        db, station="KLAX", valid_date=TARGET_DATE, members_by_model={"gefs": [80.0]}
    )
    _write_router_config_with_pickles(
        models_dir=models_dir, station="KLAX", use_ngr=True, ngr_params=FULL_FORM_PARAMS
    )
    markets = [
        _make_greater_market(
            build_weather_market_ticker("KLAX", TARGET_DATE, 78),
            threshold=78.0,
            yes_bid=0.18,
            yes_ask=0.20,
        )
    ]
    prob = _run_flow_and_read_prob(db, models_dir, markets, ticker_suffix="T78")
    # Greater strikes price at floor + 0.5 (whole-°F settlement, strikes.py).
    expected = _clipped_sf(78.5, mu=80.0, sigma=math.sqrt(FULL_FORM_PARAMS.c))
    assert prob == pytest.approx(expected, abs=1e-9)


def test_nowcast_prior_gets_var_aware_sigma(tmp_path: Path) -> None:
    """The METAR-nowcast branch must thread ens_var into predict_distribution:
    the prior sigma (hence the updated prob) moves with the batch spread, and
    ens_var=None reproduces the legacy sqrt(c) prior exactly."""
    models_dir = tmp_path / "models"
    config_path = _write_router_config_with_pickles(
        models_dir=models_dir, station="KLAX", use_ngr=True, ngr_params=FULL_FORM_PARAMS
    )
    router = StrategyRouter.from_disk(config_path, models_dir, lead_days=1)
    # Obs below the threshold → not locked; fraction 1.0 → sigma_post == prior sigma.
    state = NowcastState(t_so_far_f=70.0, fraction_day_remaining=1.0, n_obs=1)
    forecast_arr = np.array([80.0])

    def prob_at_84(ens_var: float | None) -> float:
        prob_gt = paper_trade_flow._make_prob_gt(
            router=router,
            icao="KLAX",
            forecast_arr=forecast_arr,
            ens_var=ens_var,
            nowcast_state=state,
        )
        return prob_gt(84.0)

    p_none, p_low, p_high = prob_at_84(None), prob_at_84(1.0), prob_at_84(100.0)

    assert p_none == pytest.approx(
        _clipped_sf(84.0, mu=80.0, sigma=math.sqrt(FULL_FORM_PARAMS.c)), abs=1e-9
    ), "ens_var=None must keep the legacy constant-sigma prior"
    assert p_low < p_high, "wider batch spread must fatten the nowcast prior"
    sigma_high = math.sqrt(FULL_FORM_PARAMS.c + FULL_FORM_PARAMS.d * 100.0)
    assert p_high == pytest.approx(_clipped_sf(84.0, mu=80.0, sigma=sigma_high), abs=1e-9)
