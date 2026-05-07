"""Tests for the Odds API v4 client + parser.

Coverage:
- Parser maps the recorded JSON fixture to typed dataclasses correctly.
- Quota-header parser handles present, missing, and malformed values.
- Client construction enforces a non-empty key.
- End-to-end ``fetch_nba_h2h`` round-trip via ``httpx.MockTransport``
  verifies query-param composition + header propagation.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from kq.clients.the_odds_api import (
    BASE_URL,
    BOOKMAKER_PINNACLE,
    SPORT_NBA,
    OddsApiBookmaker,
    OddsApiGame,
    OddsApiMarket,
    OddsApiOutcome,
    QuotaUsage,
    TheOddsApiClient,
    _parse_iso,
    parse_odds_response,
    parse_quota_headers,
)

FIXTURE = Path(__file__).parent / "fixtures" / "the_odds_api_nba_h2h.json"


def _load_fixture() -> list[dict[str, object]]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


# --------------------------- parse_odds_response ---------------------------


def test_parse_three_games_from_fixture() -> None:
    payload = _load_fixture()
    games = parse_odds_response(payload)
    assert len(games) == 3
    assert all(isinstance(g, OddsApiGame) for g in games)
    assert {g.game_id for g in games} == {
        "abcd1234abcd1234abcd1234abcd1234",
        "efgh5678efgh5678efgh5678efgh5678",
        "ijkl9012ijkl9012ijkl9012ijkl9012",
    }


def test_parse_first_game_lakers_celtics_pinnacle_quote() -> None:
    games = parse_odds_response(_load_fixture())
    g = next(g for g in games if g.home_team == "Los Angeles Lakers")
    assert g.away_team == "Boston Celtics"
    assert g.commence_time == datetime(2026, 5, 4, 23, 0, tzinfo=UTC)
    pinnacle = next(b for b in g.bookmakers if b.key == BOOKMAKER_PINNACLE)
    assert pinnacle.title == "Pinnacle"
    h2h = next(m for m in pinnacle.markets if m.key == "h2h")
    assert h2h.last_update == datetime(2026, 5, 4, 20, 30, tzinfo=UTC)
    assert {o.team_name for o in h2h.outcomes} == {
        "Los Angeles Lakers",
        "Boston Celtics",
    }
    lakers = next(o for o in h2h.outcomes if o.team_name == "Los Angeles Lakers")
    assert lakers.decimal_odds == pytest.approx(2.45)


def test_parse_handles_game_with_empty_bookmakers() -> None:
    """Heat-Pacers in the fixture has no bookmaker quotes yet -- parser
    must still produce a game record with an empty bookmakers tuple."""
    games = parse_odds_response(_load_fixture())
    g = next(g for g in games if g.home_team == "Miami Heat")
    assert g.bookmakers == ()


def test_parse_preserves_multiple_bookmakers_per_game() -> None:
    """Lakers-Celtics has both Pinnacle + DraftKings quotes."""
    games = parse_odds_response(_load_fixture())
    g = next(g for g in games if g.home_team == "Los Angeles Lakers")
    keys = {b.key for b in g.bookmakers}
    assert keys == {"pinnacle", "draftkings"}


def test_parse_pickem_quote_returns_correct_decimal() -> None:
    """Pinnacle's 1.91/1.91 Nuggets-Thunder pickem -- both sides parse to 1.91."""
    games = parse_odds_response(_load_fixture())
    g = next(g for g in games if g.home_team == "Denver Nuggets")
    pinnacle = g.bookmakers[0]
    h2h = pinnacle.markets[0]
    assert all(o.decimal_odds == pytest.approx(1.91) for o in h2h.outcomes)


def test_parse_empty_payload() -> None:
    assert parse_odds_response([]) == []


# --------------------------- parse_quota_headers ---------------------------


def test_quota_headers_parsed_from_lowercase_keys() -> None:
    headers = {
        "x-requests-remaining": "4823",
        "x-requests-used": "177",
        "x-requests-last": "1",
    }
    quota = parse_quota_headers(headers)
    assert quota == QuotaUsage(remaining=4823, used=177, last_cost=1)


def test_quota_headers_parsed_from_canonical_case() -> None:
    """httpx.Headers normalizes to lowercase but defensive against the
    canonical X- prefix some gateways emit verbatim."""
    headers = {
        "X-Requests-Remaining": "100",
        "X-Requests-Used": "0",
        "X-Requests-Last": "1",
    }
    quota = parse_quota_headers(headers)
    assert quota == QuotaUsage(remaining=100, used=0, last_cost=1)


def test_quota_headers_missing_fields_are_none() -> None:
    quota = parse_quota_headers({})
    assert quota == QuotaUsage(remaining=None, used=None, last_cost=None)


def test_quota_headers_malformed_value_is_none() -> None:
    """A non-numeric header value should surface as None, not crash."""
    quota = parse_quota_headers({"x-requests-remaining": "n/a"})
    assert quota.remaining is None


# --------------------------- client construction ---------------------------


def test_client_rejects_empty_api_key() -> None:
    with pytest.raises(ValueError, match="api_key required"):
        TheOddsApiClient(api_key="")


@pytest.mark.asyncio
async def test_client_requires_async_context_manager() -> None:
    """Calling fetch without entering the context raises a clear error."""
    client = TheOddsApiClient(api_key="dummy-key")
    with pytest.raises(RuntimeError, match=r"async with"):
        await client.fetch_nba_h2h()


# --------------------------- end-to-end via MockTransport ---------------------------


@pytest.mark.asyncio
async def test_fetch_nba_h2h_round_trip_with_mock_transport() -> None:
    """Pin the request URL + params, return the recorded fixture, verify
    the typed games come out + quota headers are surfaced."""
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url).split("?")[0]
        captured["params"] = dict(request.url.params)
        body = json.dumps(_load_fixture())
        return httpx.Response(
            200,
            content=body,
            headers={
                "x-requests-remaining": "4999",
                "x-requests-used": "1",
                "x-requests-last": "1",
                "content-type": "application/json",
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = TheOddsApiClient(api_key="dummy-key", client=http)
        async with client:
            games, quota = await client.fetch_nba_h2h(bookmaker_keys=(BOOKMAKER_PINNACLE,))

    assert captured["url"] == f"{BASE_URL}/sports/{SPORT_NBA}/odds"
    assert captured["params"] == {
        "apiKey": "dummy-key",
        "regions": "us",
        "markets": "h2h",
        "bookmakers": "pinnacle",
        "oddsFormat": "decimal",
    }
    assert len(games) == 3
    assert quota == QuotaUsage(remaining=4999, used=1, last_cost=1)


@pytest.mark.asyncio
async def test_fetch_nba_h2h_propagates_http_error() -> None:
    """A 401 (bad key) surfaces as ``HTTPStatusError``, not a parse error."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, content=b'{"message":"invalid api key"}')

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = TheOddsApiClient(api_key="bad-key", client=http)
        async with client:
            with pytest.raises(httpx.HTTPStatusError):
                await client.fetch_nba_h2h()


@pytest.mark.asyncio
async def test_fetch_nba_h2h_supports_multiple_bookmakers() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["bookmakers"] = request.url.params.get("bookmakers")
        return httpx.Response(200, content=b"[]", headers={})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = TheOddsApiClient(api_key="dummy-key", client=http)
        async with client:
            await client.fetch_nba_h2h(bookmaker_keys=("pinnacle", "betmgm", "draftkings"))
    assert captured["bookmakers"] == "pinnacle,betmgm,draftkings"


# --------------------------- type sanity ---------------------------


def test_outcome_is_frozen() -> None:
    out = OddsApiOutcome(team_name="X", decimal_odds=2.0)
    with pytest.raises(AttributeError):
        out.team_name = "mutated"  # type: ignore[misc]


def test_market_is_frozen() -> None:
    market = OddsApiMarket(
        key="h2h",
        last_update=datetime(2026, 5, 4, tzinfo=UTC),
        outcomes=(),
    )
    with pytest.raises(AttributeError):
        market.key = "mutated"  # type: ignore[misc]


def test_bookmaker_is_frozen() -> None:
    book = OddsApiBookmaker(
        key="pinnacle",
        title="Pinnacle",
        last_update=datetime(2026, 5, 4, tzinfo=UTC),
        markets=(),
    )
    with pytest.raises(AttributeError):
        book.key = "mutated"  # type: ignore[misc]


def test_game_is_frozen() -> None:
    game = OddsApiGame(
        game_id="g1",
        sport_key="basketball_nba",
        commence_time=datetime(2026, 5, 4, tzinfo=UTC),
        home_team="X",
        away_team="Y",
        bookmakers=(),
    )
    with pytest.raises(AttributeError):
        game.game_id = "mutated"  # type: ignore[misc]


def test_iso_parse_handles_z_suffix() -> None:
    """commence_time uses ``Z`` suffix in the live wire format -- we
    rely on Python 3.11+ ``fromisoformat`` to handle it. Confirm with a
    minimal direct round-trip."""
    parsed = _parse_iso("2026-05-04T23:00:00Z")
    assert parsed == datetime(2026, 5, 4, 23, 0, tzinfo=UTC)
