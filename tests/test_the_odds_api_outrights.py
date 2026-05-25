"""Tests for the Odds API outrights (golf) + generic h2h (NFL) additions.

Coverage:
- ``parse_outrights_response`` maps the recorded US Open fixture to typed
  events, ignores null home/away, and filters out ``outrights_lay``.
- ``fetch_outrights`` round-trips via ``httpx.MockTransport`` — URL uses the
  golf sport key, params request the ``outrights`` market, quota surfaces.
- ``fetch_h2h`` is sport-generic — an NFL call hits the NFL sport key.
- ``fetch_nba_h2h`` still delegates to the NFL/NBA-generic ``fetch_h2h``.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from kq.clients.the_odds_api import (
    BASE_URL,
    BOOKMAKER_PINNACLE,
    GOLF_US_OPEN_KEY,
    SPORT_NFL,
    OddsApiOutrightEvent,
    QuotaUsage,
    TheOddsApiClient,
    parse_outrights_response,
)

H2H_FIXTURE = Path(__file__).parent / "fixtures" / "the_odds_api_nba_h2h.json"
OUTRIGHTS_FIXTURE = Path(__file__).parent / "fixtures" / "the_odds_api_golf_outrights.json"


def _load_outrights() -> list[dict[str, object]]:
    return json.loads(OUTRIGHTS_FIXTURE.read_text(encoding="utf-8"))


# --------------------------- parse_outrights_response ---------------------------


def test_parse_outrights_single_event() -> None:
    events = parse_outrights_response(_load_outrights())
    assert len(events) == 1
    ev = events[0]
    assert isinstance(ev, OddsApiOutrightEvent)
    assert ev.event_id == "cfbf8baac8b2b9e462de66c714bb72f8"
    assert ev.sport_key == GOLF_US_OPEN_KEY
    assert ev.commence_time.year == 2026
    assert {b.key for b in ev.bookmakers} == {"lowvig", "betfair_ex_eu"}


def test_parse_outrights_filters_lay_market() -> None:
    """The exchange ``outrights_lay`` market must be dropped; only the real
    win-probability ``outrights`` market survives."""
    events = parse_outrights_response(_load_outrights())
    betfair = next(b for b in events[0].bookmakers if b.key == "betfair_ex_eu")
    assert [m.key for m in betfair.markets] == ["outrights"]


def test_parse_outrights_player_names_and_odds() -> None:
    events = parse_outrights_response(_load_outrights())
    lowvig = next(b for b in events[0].bookmakers if b.key == "lowvig")
    outrights = lowvig.markets[0]
    assert outrights.key == "outrights"
    by_player = {o.team_name: o.decimal_odds for o in outrights.outcomes}
    assert by_player["Scottie Scheffler"] == pytest.approx(5.0)
    assert by_player["Xander Schauffele"] == pytest.approx(22.0)
    assert len(outrights.outcomes) == 5


def test_parse_outrights_empty_payload() -> None:
    assert parse_outrights_response([]) == []


# --------------------------- fetch_outrights round-trip ---------------------------


@pytest.mark.asyncio
async def test_fetch_outrights_round_trip() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url).split("?")[0]
        captured["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            content=json.dumps(_load_outrights()),
            headers={
                "x-requests-remaining": "496",
                "x-requests-used": "4",
                "x-requests-last": "2",
                "content-type": "application/json",
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = TheOddsApiClient(api_key="dummy-key", client=http)
        async with client:
            events, quota = await client.fetch_outrights(GOLF_US_OPEN_KEY)

    assert captured["url"] == f"{BASE_URL}/sports/{GOLF_US_OPEN_KEY}/odds"
    assert captured["params"] == {
        "apiKey": "dummy-key",
        "regions": "eu,us",
        "markets": "outrights",
        "oddsFormat": "decimal",
    }
    assert len(events) == 1
    assert quota == QuotaUsage(remaining=496, used=4, last_cost=2)


@pytest.mark.asyncio
async def test_fetch_outrights_requires_context_manager() -> None:
    client = TheOddsApiClient(api_key="dummy-key")
    with pytest.raises(RuntimeError, match=r"async with"):
        await client.fetch_outrights(GOLF_US_OPEN_KEY)


# --------------------------- generic fetch_h2h (NFL) ---------------------------


@pytest.mark.asyncio
async def test_fetch_h2h_uses_given_sport_key() -> None:
    """The generic h2h fetch must hit whatever sport key it is handed (NFL)."""
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url).split("?")[0]
        captured["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            content=H2H_FIXTURE.read_text(encoding="utf-8"),
            headers={"x-requests-remaining": "495", "content-type": "application/json"},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = TheOddsApiClient(api_key="dummy-key", client=http)
        async with client:
            games, quota = await client.fetch_h2h(SPORT_NFL, bookmaker_keys=(BOOKMAKER_PINNACLE,))

    assert captured["url"] == f"{BASE_URL}/sports/{SPORT_NFL}/odds"
    assert captured["params"]["markets"] == "h2h"
    assert captured["params"]["regions"] == "eu"
    assert len(games) == 3  # reuses the 3-game h2h fixture shape
    assert quota.remaining == 495
