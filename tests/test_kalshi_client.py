"""Tests for the Kalshi read-only client."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import httpx
import pytest

from kq.backtest.bracket_match import parsed_weather_markets
from kq.clients.kalshi import (
    KalshiClient,
    KalshiCredentialsError,
    Market,
    _parse_market,
    _parse_orderbook,
)
from kq.storage.duckdb_store import bootstrap
from kq.storage.repositories.kalshi import upsert_kalshi_markets


def _build_client(
    api_key_id: str,
    key_path: Path,
    *,
    client: httpx.AsyncClient,
) -> KalshiClient:
    return KalshiClient(
        api_key_id=api_key_id,
        private_key_path=key_path,
        env="demo",
        client=client,
    )


def test_parse_market_canonicalizes_prices_to_dollars() -> None:
    raw = {
        "ticker": "KXHIGHLAX-26APR23-75",
        "event_ticker": "KXHIGHLAX",
        "title": "LA high today >= 75F",
        "status": "open",
        "yes_ask": 42,  # cents
        "yes_bid": 38,
        "last_price": 40,
        "volume": 1234,
        "open_interest": 567,
        "open_time": "2026-04-23T08:00:00Z",
        "close_time": "2026-04-23T20:00:00Z",
        "expected_expiration_time": "2026-04-24T05:00:00Z",
        "rules_primary": "Settles on NWS Daily Climate Report for KLAX.",
    }
    m = _parse_market(raw)
    assert m.yes_ask == pytest.approx(0.42)
    assert m.yes_bid == pytest.approx(0.38)
    assert m.last_price == pytest.approx(0.40)
    assert m.open_time == datetime(2026, 4, 23, 8, 0, tzinfo=UTC)
    assert m.close_time == datetime(2026, 4, 23, 20, 0, tzinfo=UTC)


def test_parse_orderbook_normalizes_no_side_to_yes_ask() -> None:
    # Kalshi returns `yes` = YES-bid ladder (price=YES-side bid price),
    # and `no` = NO-bid ladder (where yes_ask = 100 - no_bid_price).
    payload = {
        "orderbook": {
            "yes": [[38, 10], [37, 20]],  # best YES bid at 38c
            "no": [[55, 30], [54, 15]],  # best YES ask = 100-55 = 45c
        }
    }
    snap = _parse_orderbook(
        payload, ticker="KXHIGHLAX-TEST", snap_time=datetime(2026, 4, 23, tzinfo=UTC)
    )
    assert snap.yes_bid == pytest.approx(0.38)
    assert snap.yes_ask == pytest.approx(0.45)
    assert snap.yes_bid_size == 10
    assert snap.yes_ask_size == 30
    # Ladders are normalized to DOLLARS (package convention), best-first.
    assert snap.yes_bids == ((0.38, 10.0), (0.37, 20.0))
    assert snap.yes_asks == ((0.45, 30.0), (0.46, 15.0))


def test_parse_orderbook_handles_empty_sides() -> None:
    snap = _parse_orderbook(
        {"orderbook": {"yes": [], "no": []}},
        ticker="X",
        snap_time=datetime(2026, 4, 23, tzinfo=UTC),
    )
    assert snap.yes_bid is None
    assert snap.yes_ask is None
    assert snap.yes_bids == ()
    assert snap.yes_asks == ()


def test_client_refuses_without_api_key(rsa_private_key_file: Path) -> None:
    with pytest.raises(KalshiCredentialsError):
        KalshiClient(api_key_id="", private_key_path=rsa_private_key_file, env="demo")


def test_client_refuses_without_key_file(tmp_path: Path) -> None:
    with pytest.raises(KalshiCredentialsError):
        KalshiClient(
            api_key_id="some-id",
            private_key_path=tmp_path / "does-not-exist.pem",
            env="demo",
        )


async def test_list_markets_end_to_end(rsa_private_key_file: Path) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["ua"] = request.headers.get("user-agent")
        captured["kalshi_key"] = request.headers.get("KALSHI-ACCESS-KEY")
        captured["kalshi_ts"] = request.headers.get("KALSHI-ACCESS-TIMESTAMP")
        captured["kalshi_sig"] = request.headers.get("KALSHI-ACCESS-SIGNATURE")
        return httpx.Response(
            200,
            json={
                "markets": [
                    {
                        "ticker": "KXHIGHLAX-X-75",
                        "event_ticker": "KXHIGHLAX",
                        "title": "LA high >= 75F",
                        "status": "open",
                        "yes_ask": 42,
                        "yes_bid": 38,
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = _build_client("my-key-id", rsa_private_key_file, client=http)
        markets = await client.list_markets(event_ticker="KXHIGHLAX")

    assert len(markets) == 1
    assert markets[0].ticker == "KXHIGHLAX-X-75"
    assert captured["kalshi_key"] == "my-key-id"
    # Auth headers are all non-empty
    assert captured["kalshi_ts"]
    assert captured["kalshi_sig"]
    # URL includes the query param
    assert "event_ticker=KXHIGHLAX" in str(captured["url"])


async def test_list_markets_filters_by_series_ticker(rsa_private_key_file: Path) -> None:
    """`series_ticker=` is forwarded as a query param — the weather-station path.

    Regression guard: stations carry Kalshi SERIES tickers; querying them by
    `event_ticker` returns nothing on prod (the bug the prod switch surfaced).
    `ingest_kalshi` / `paper_trade` rely on the series_ticker filter.
    """
    captured: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"markets": []})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = _build_client("id", rsa_private_key_file, client=http)
        await client.list_markets(series_ticker="KXHIGHLAX")

    assert "series_ticker=KXHIGHLAX" in str(captured["url"])
    assert "event_ticker=" not in str(captured["url"])


async def test_get_orderbook_end_to_end(rsa_private_key_file: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "/markets/KXHIGHLAX-TEST/orderbook" in str(request.url)
        return httpx.Response(
            200,
            json={"orderbook": {"yes": [[38, 10]], "no": [[55, 30]]}},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = _build_client("id", rsa_private_key_file, client=http)
        snap = await client.get_orderbook("KXHIGHLAX-TEST")

    assert snap.ticker == "KXHIGHLAX-TEST"
    assert snap.yes_bid == pytest.approx(0.38)
    assert snap.yes_ask == pytest.approx(0.45)


# ----------------------------- edge cases (PR #5) -----------------------------


def test_orderbook_malformed_ladder_entries_dropped() -> None:
    """Kalshi could return 3-tuples or missing-size entries during upgrades.
    The parser must drop them, not blow up."""
    payload = {
        "orderbook": {
            "yes": [
                [38, 10],
                [37],  # missing size — dropped
                [36, 20, "extra"],  # wrong arity — dropped
                "not a list",  # wrong type — dropped
                [35, "not-a-number"],  # bad size — dropped
            ],
            "no": [[55, 30]],
        }
    }
    snap = _parse_orderbook(payload, ticker="X", snap_time=datetime(2026, 4, 23, tzinfo=UTC))
    assert snap.yes_bids == ((0.38, 10.0),)
    assert snap.yes_asks == ((0.45, 30.0),)


def test_parse_market_handles_null_prices() -> None:
    raw = {
        "ticker": "X",
        "event_ticker": "KXHIGHLAX",
        "title": "t",
        "status": "open",
        "yes_ask": None,
        "yes_bid": None,
        "last_price": None,
        "volume": None,
        "open_interest": None,
    }
    m = _parse_market(raw)
    assert m.yes_ask is None
    assert m.yes_bid is None
    assert m.last_price is None
    assert m.volume is None
    assert m.open_interest is None


def test_parse_market_malformed_dates_become_none() -> None:
    raw = {
        "ticker": "X",
        "event_ticker": "E",
        "title": "t",
        "status": "open",
        "open_time": "not-an-iso-date",
        "close_time": 12345,  # wrong type entirely
        "expected_expiration_time": None,
    }
    m = _parse_market(raw)
    assert m.open_time is None
    assert m.close_time is None
    assert m.expected_expiration_time is None


# ------------------- prod wire format (2026-06-11 audit, PR-A) -------------------
#
# Recorded LIVE from api.elections.kalshi.com on 2026-06-11. The prod API
# serves dollar-string price fields (*_dollars), float-string volumes (*_fp),
# strike semantics (strike_type / floor_strike / cap_strike), and orderbooks
# under `orderbook_fp` with fractional sizes. The legacy integer-cent format
# above is what demo served; both must parse.

_FIXTURES = Path(__file__).parent / "fixtures"


def _prod_markets() -> list[dict[str, object]]:
    payload = json.loads(
        (_FIXTURES / "kalshi_prod_markets_weather.json").read_text(encoding="utf-8")
    )
    return payload["markets"]


def test_parse_prod_market_prices_from_dollar_strings() -> None:
    by_ticker = {m["ticker"]: m for m in _prod_markets()}
    raw = by_ticker["KXHIGHLAX-26JUN11-T79"]
    m = _parse_market(raw)
    # Prices come from *_dollars strings, not the absent legacy cent fields.
    assert m.yes_bid == pytest.approx(float(raw["yes_bid_dollars"]))
    assert m.yes_ask == pytest.approx(float(raw["yes_ask_dollars"]))
    assert m.last_price == pytest.approx(float(raw["last_price_dollars"]))
    assert m.yes_bid is not None and 0.0 <= m.yes_bid <= 1.0
    # Volume / OI come from *_fp float-strings (fractional trading).
    assert m.volume == pytest.approx(float(raw["volume_fp"]))
    assert m.open_interest == pytest.approx(float(raw["open_interest_fp"]))


def test_parse_prod_market_strike_fields_all_three_types() -> None:
    parsed = {m.ticker: m for m in map(_parse_market, _prod_markets())}
    # T-greater: YES iff value > floor_strike. "-T79" == "80 or above".
    greater = parsed["KXHIGHLAX-26JUN11-T79"]
    assert greater.strike_type == "greater"
    assert greater.floor_strike == pytest.approx(79.0)
    assert greater.cap_strike is None
    # T-less: YES iff value < cap_strike. "-T72" == "71 or below" — the
    # audit's inverted-semantics finding: NOT a greater contract.
    less = parsed["KXHIGHLAX-26JUN11-T72"]
    assert less.strike_type == "less"
    assert less.cap_strike == pytest.approx(72.0)
    assert less.floor_strike is None
    # B-between: YES iff floor <= value <= cap. "-B78.5" == "78 to 79".
    between = parsed["KXHIGHLAX-26JUN11-B78.5"]
    assert between.strike_type == "between"
    assert between.floor_strike == pytest.approx(78.0)
    assert between.cap_strike == pytest.approx(79.0)


def test_parse_prod_market_fixture_full_sweep() -> None:
    """Every recorded prod market parses with a usable price + strike type."""
    markets = [_parse_market(raw) for raw in _prod_markets()]
    assert len(markets) == 12
    for m in markets:
        assert m.strike_type in {"greater", "less", "between"}, m.ticker
        # Every open prod market carries dollar-string quotes -> never None.
        assert m.yes_bid is not None and m.yes_ask is not None, m.ticker
        assert 0.0 <= m.yes_bid <= 1.0 and 0.0 <= m.yes_ask <= 1.0, m.ticker


def test_parse_prod_orderbook_fp_dollar_ladders_fractional_sizes() -> None:
    payload = json.loads((_FIXTURES / "kalshi_prod_orderbook_fp.json").read_text(encoding="utf-8"))
    snap = _parse_orderbook(
        payload, ticker="KXHIGHLAX-26JUN11-T79", snap_time=datetime(2026, 6, 11, tzinfo=UTC)
    )
    # Recorded book: yes_dollars is EMPTY (real edge case), no_dollars stacked.
    assert snap.yes_bid is None and snap.yes_bid_size is None
    assert snap.yes_bids == ()
    # Best NO bid in the fixture is 0.99 -> best YES ask = 1.00 - 0.99 = 0.01.
    assert snap.yes_ask == pytest.approx(0.01)
    # Fractional size survives float-string parsing (220971.25 contracts).
    assert snap.yes_ask_size == pytest.approx(220971.25)
    # Ladder is dollars, asc by price, complement has no float dust.
    assert all(0.0 <= p <= 1.0 for p, _ in snap.yes_asks)
    assert list(snap.yes_asks) == sorted(snap.yes_asks, key=lambda r: r[0])
    assert all(round(p, 4) == p for p, _ in snap.yes_asks)


def test_parse_orderbook_prefers_fp_over_legacy_when_both_present() -> None:
    payload = {
        "orderbook_fp": {"yes_dollars": [["0.40", "5.5"]], "no_dollars": []},
        "orderbook": {"yes": [[10, 1]], "no": []},  # stale legacy block
    }
    snap = _parse_orderbook(payload, ticker="X", snap_time=datetime(2026, 6, 11, tzinfo=UTC))
    assert snap.yes_bid == pytest.approx(0.40)
    assert snap.yes_bid_size == pytest.approx(5.5)


def test_parse_market_prefers_dollars_over_legacy_when_both_present() -> None:
    raw = {
        "ticker": "X",
        "event_ticker": "E",
        "title": "t",
        "status": "active",
        "yes_bid_dollars": "0.05",
        "yes_bid": 99,  # stale legacy cents — must NOT win
    }
    m = _parse_market(raw)
    assert m.yes_bid == pytest.approx(0.05)


def test_parse_prod_orderbook_malformed_fp_entries_dropped() -> None:
    payload = {
        "orderbook_fp": {
            "yes_dollars": [
                ["0.40", "5.5"],
                ["not-a-price", "1"],  # dropped
                ["0.41"],  # wrong arity — dropped
                ["1.50", "2"],  # out of [0,1] — dropped
            ],
            "no_dollars": [],
        }
    }
    snap = _parse_orderbook(payload, ticker="X", snap_time=datetime(2026, 6, 11, tzinfo=UTC))
    assert snap.yes_bids == ((0.40, 5.5),)


def test_parsed_weather_markets_guards_on_strike_type() -> None:
    """PR-A interim guard: only 'greater' markets are eligible for the
    threshold-exceedance pricing path; 'less' would be priced exactly
    inverted and 'between' isn't supported until PR-B."""

    def mk(ticker: str, strike_type: str | None, floor: float | None) -> Market:
        return Market(
            ticker=ticker,
            event_ticker="KXHIGHLAX-26JUN11",
            title="t",
            status="active",
            category=None,
            yes_ask=0.5,
            yes_bid=0.49,
            last_price=None,
            volume=None,
            open_interest=None,
            open_time=None,
            close_time=None,
            expected_expiration_time=None,
            rules_primary=None,
            strike_type=strike_type,
            floor_strike=floor,
            cap_strike=None,
        )

    markets = [
        mk("KXHIGHLAX-26JUN11-T79", "greater", 79.0),  # kept
        mk("KXHIGHLAX-26JUN11-T72", "less", None),  # excluded: inverted semantics
        mk("KXHIGHLAX-26JUN11-T75", "greater", 76.0),  # excluded: ticker/API disagree
        mk("KXHIGHLAX-26JUN11-T77", None, None),  # kept: legacy payload, old behavior
    ]
    kept = [m.ticker for m, _ in parsed_weather_markets(markets)]
    assert kept == ["KXHIGHLAX-26JUN11-T79", "KXHIGHLAX-26JUN11-T77"]


def test_upsert_kalshi_markets_persists_strike_fields(tmp_path: Path) -> None:
    raw = _prod_markets()[0]
    m = _parse_market(raw)
    db = tmp_path / "t.duckdb"
    bootstrap(db)
    con = duckdb.connect(str(db))
    try:
        upsert_kalshi_markets(con, [m])
        row = con.execute(
            "SELECT strike_type, floor_strike, cap_strike FROM kalshi_market WHERE ticker = ?",
            [m.ticker],
        ).fetchone()
    finally:
        con.close()
    assert row is not None
    assert row[0] == m.strike_type
    assert row[1] == m.floor_strike
    assert row[2] == m.cap_strike
