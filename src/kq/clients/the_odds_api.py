"""The Odds API v4 read-only client (NBA moneylines).

Fetches NBA head-to-head moneyline odds from `the-odds-api.com`, our
Pinnacle-via-paid-aggregator path. Pinnacle is the lowest-vig book in
the business and the closest thing public bettors get to a "fair" line;
their data lives behind The Odds API's GOAT plan ($30/mo, ~5 k req/mo)
since Pinnacle doesn't operate a public retail US sportsbook themselves.

The free tier (500 req/mo) does NOT include Pinnacle. The pipeline is
designed so the client and parsers can be tested + exercised locally
without an API key (recorded-JSON fixtures); the live call simply errors
out at construction if the key is missing. Wire-up to a scheduled flow
is deferred to PR 4 -- this PR is the HTTP + types layer only.

Quota-discipline note: every successful call logs the
``x-requests-remaining`` and ``x-requests-used`` headers The Odds API
returns. Operators monitoring the cron should alert when remaining
< 10 % of the monthly bucket.

References:
- https://the-odds-api.com/liveapi/guides/v4/
- CLAUDE.md §5 Phase 3 (Pinnacle as the NBA fair-value anchor)
- CLAUDE.md §11 (cost tracking; this is the largest paid line item).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Any, Final, Self

import httpx
import structlog

from kq.clients._http import default_client

log = structlog.get_logger(__name__)

# Public v4 base URL. Path layout: ``/sports/{sport_key}/odds``.
BASE_URL: Final = "https://api.the-odds-api.com/v4"

# Sport key for NBA head-to-head moneylines. The Odds API uses
# ``basketball_nba`` for the regular season + playoffs (no separate
# preseason key in the public catalog as of 2026-04).
SPORT_NBA: Final = "basketball_nba"

# Bookmaker keys we care about. Pinnacle is the canonical fair-value
# anchor; the other US books are listed for resilience -- if Pinnacle
# isn't quoted on a given matchup we can fall back to the lowest-vig
# alternative observed (typically BetMGM or DraftKings).
BOOKMAKER_PINNACLE: Final = "pinnacle"
BOOKMAKER_FALLBACKS: Final[tuple[str, ...]] = (
    BOOKMAKER_PINNACLE,
    "betmgm",
    "draftkings",
    "fanduel",
)

# Markets key. Head-to-head (moneyline) is the v1 NBA target.
MARKET_H2H: Final = "h2h"


# --------------------------- typed payload ---------------------------


@dataclass(frozen=True, slots=True)
class OddsApiOutcome:
    """One side of a market: a team name + decimal odds."""

    team_name: str
    decimal_odds: float


@dataclass(frozen=True, slots=True)
class OddsApiMarket:
    """A single market quote (e.g. ``h2h``) with its outcomes."""

    key: str  # "h2h" | "spreads" | "totals"
    last_update: datetime
    outcomes: tuple[OddsApiOutcome, ...]


@dataclass(frozen=True, slots=True)
class OddsApiBookmaker:
    """One bookmaker's quotes on a single game."""

    key: str  # "pinnacle" | "betmgm" | ...
    title: str
    last_update: datetime
    markets: tuple[OddsApiMarket, ...]


@dataclass(frozen=True, slots=True)
class OddsApiGame:
    """One game with all bookmakers' quotes attached.

    The Odds API returns games as a top-level list, each with an
    embedded ``bookmakers`` array. We preserve that shape so the
    parser is one-to-one with the wire format.
    """

    game_id: str
    sport_key: str
    commence_time: datetime
    home_team: str
    away_team: str
    bookmakers: tuple[OddsApiBookmaker, ...]


@dataclass(frozen=True, slots=True)
class QuotaUsage:
    """The Odds API quota counters from response headers.

    All three headers are documented at
    https://the-odds-api.com/liveapi/guides/v4/#response-headers .
    """

    remaining: int | None
    used: int | None
    last_cost: int | None
    """Cost of the most recent request (varies with markets/regions)."""


# --------------------------- client ---------------------------


class TheOddsApiClient:
    """Async client for The Odds API v4 NBA moneylines.

    Construction requires a non-empty API key. Use as an async context
    manager (``async with``) so the underlying ``httpx.AsyncClient``
    gets cleaned up on exit.
    """

    def __init__(
        self,
        api_key: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ValueError(
                "api_key required; set ODDS_API_KEY in .env -- The Odds API "
                "rejects requests without a key (no anonymous tier)"
            )
        self._api_key = api_key
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self) -> Self:
        if self._client is None:
            self._client = default_client()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def fetch_nba_h2h(
        self,
        *,
        bookmaker_keys: tuple[str, ...] = (BOOKMAKER_PINNACLE,),
        regions: str = "us",
    ) -> tuple[list[OddsApiGame], QuotaUsage]:
        """Fetch NBA head-to-head moneylines for the requested bookmakers.

        Returns ``(games, quota)``. ``games`` is the list of upcoming
        NBA games with bookmaker quotes attached; ``quota`` carries the
        post-call quota counters from the response headers.

        ``regions`` is the v4 regions string (``us`` for US books,
        ``us2`` for the secondary US set, ``uk`` for UK books, etc.).
        Pinnacle lives in ``us`` per the v4 docs as of 2026-04.

        Raises :class:`httpx.HTTPStatusError` on non-2xx responses --
        the caller decides whether to retry. Quota-exhausted (429) is
        the failure mode the cron operator most cares about.
        """
        if self._client is None:
            raise RuntimeError("use `async with TheOddsApiClient(...)` first")
        params = {
            "apiKey": self._api_key,
            "regions": regions,
            "markets": MARKET_H2H,
            "bookmakers": ",".join(bookmaker_keys),
            "oddsFormat": "decimal",
        }
        url = f"{BASE_URL}/sports/{SPORT_NBA}/odds"
        resp = await self._client.get(url, params=params)
        resp.raise_for_status()
        quota = parse_quota_headers(dict(resp.headers))
        log.info(
            "odds_api.fetch",
            sport=SPORT_NBA,
            bookmakers=bookmaker_keys,
            n_games=len(resp.json()),
            remaining=quota.remaining,
            used=quota.used,
            last_cost=quota.last_cost,
        )
        games = parse_odds_response(resp.json())
        return games, quota


# --------------------------- parsing ---------------------------


def parse_quota_headers(headers: dict[str, str]) -> QuotaUsage:
    """Pull quota counters from response headers; missing fields -> None.

    HTTP header names are case-insensitive per RFC 7230. ``httpx.Headers``
    normalizes to lowercase but a plain ``dict[str, str]`` passed by a
    caller may carry canonical-case keys; we look up case-insensitively.
    """
    lowered = {k.lower(): v for k, v in headers.items()}

    def _as_int(key: str) -> int | None:
        value = lowered.get(key)
        if value is None:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    return QuotaUsage(
        remaining=_as_int("x-requests-remaining"),
        used=_as_int("x-requests-used"),
        last_cost=_as_int("x-requests-last"),
    )


def parse_odds_response(payload: list[dict[str, Any]]) -> list[OddsApiGame]:
    """Parse the v4 ``/sports/{key}/odds`` JSON list into typed games.

    Defensive against partial bookmaker payloads -- a game with no
    Pinnacle quote (yet) still parses, just with an empty
    ``bookmakers`` tuple. Caller decides whether to skip such games.
    """
    out: list[OddsApiGame] = []
    for raw_game in payload:
        out.append(_parse_game(raw_game))
    return out


def _parse_game(raw: dict[str, Any]) -> OddsApiGame:
    return OddsApiGame(
        game_id=str(raw["id"]),
        sport_key=str(raw["sport_key"]),
        commence_time=_parse_iso(raw["commence_time"]),
        home_team=str(raw["home_team"]),
        away_team=str(raw["away_team"]),
        bookmakers=tuple(_parse_bookmaker(b) for b in raw.get("bookmakers", [])),
    )


def _parse_bookmaker(raw: dict[str, Any]) -> OddsApiBookmaker:
    return OddsApiBookmaker(
        key=str(raw["key"]),
        title=str(raw["title"]),
        last_update=_parse_iso(raw["last_update"]),
        markets=tuple(_parse_market(m) for m in raw.get("markets", [])),
    )


def _parse_market(raw: dict[str, Any]) -> OddsApiMarket:
    return OddsApiMarket(
        key=str(raw["key"]),
        last_update=_parse_iso(raw["last_update"]),
        outcomes=tuple(
            OddsApiOutcome(
                team_name=str(o["name"]),
                decimal_odds=float(o["price"]),
            )
            for o in raw.get("outcomes", [])
        ),
    )


def _parse_iso(value: str) -> datetime:
    """Parse The Odds API's ISO-8601 with ``Z`` suffix.

    ``datetime.fromisoformat`` handles the ``Z`` suffix natively only
    in Python 3.11+; we run 3.12, so a direct call is safe.
    """
    return datetime.fromisoformat(value)
