"""Parse Kalshi PGA (golf) tournament-winner ticker strings to typed metadata.

Format (event layer web-verified 2026-05-24; the per-player contract suffix
is UNVERIFIED — demo seeds 0 golf markets and we have no prod sample yet):

    KXPGATOUR-<EVENTCODE>[-<PLAYER_SLUG>]

where ``<EVENTCODE>`` is a short tournament code followed by a 2-digit year,
e.g.:

    KXPGATOUR-PGC26    ->  2026 PGA Championship (event-level market)
    KXPGATOUR-USO26    ->  2026 US Open
    KXPGATOUR-PGC26-SCHEFFLER  ->  (GUESS) the "Scottie Scheffler wins" leg

Golf is a large-field outright market: each player is a separate YES/NO
contract that resolves YES -> $1 for the tournament winner. The event-level
parse (tournament + year) is reliable; the **per-player slug is a guess** —
Kalshi may key players by surname, full name, or an internal id. The parser
therefore returns the player segment *verbatim* (no assumption about its
internal structure) and never raises.

⚠️ Heavily unverified. Confirm against a live ``GET /markets?event_ticker=
KXPGATOUR-...`` before wiring any golf paper-trade flow. The round-trip test
in ``tests/test_kalshi_ticker_parser_pga.py`` pins current behavior only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

KXPGATOUR_PREFIX: Final = "KXPGATOUR"

# Best-effort tournament-code -> human name map for the four Majors The Odds
# API also covers. Unknown codes still parse (tournament_name=None) — the code
# itself is preserved verbatim. These specific codes are inferred, not confirmed.
_TOURNAMENT_CODES: Final[dict[str, str]] = {
    "MAS": "Masters Tournament",
    "PGC": "PGA Championship",
    "USO": "US Open",
    "THE": "The Open Championship",
}

# <EVENTCODE> = leading letters (tournament) + trailing 2-digit year.
# Optional trailing "-<PLAYER>" segment captured verbatim.
PGA_TICKER_RE: Final = re.compile(
    r"^KXPGATOUR-"
    r"(?P<tcode>[A-Z]{2,5})(?P<yy>\d{2})"
    r"(?:-(?P<player>[A-Z0-9]+))?$"
)


@dataclass(frozen=True, slots=True)
class PgaMarketRef:
    """Parsed identifier for a Kalshi PGA tournament-winner market.

    ``player_slug`` is ``None`` for the event-level ticker and the verbatim
    trailing segment for a per-player contract (its internal structure is
    unverified — treat it as an opaque key for now). ``tournament_name`` is
    a best-effort lookup; ``None`` for codes outside the four Majors.
    """

    event_code: str  # full code as written, e.g. "PGC26"
    tournament_code: str  # leading letters, e.g. "PGC"
    year: int  # 4-digit, e.g. 2026
    player_slug: str | None
    raw_ticker: str

    @property
    def tournament_name(self) -> str | None:
        """Human-readable Major name, or None for an unrecognized code."""
        return _TOURNAMENT_CODES.get(self.tournament_code)

    @property
    def is_player_contract(self) -> bool:
        """True when this ticker names a specific player's win contract."""
        return self.player_slug is not None


def parse_pga_market_ticker(ticker: str) -> PgaMarketRef | None:
    """Return a ``PgaMarketRef`` if ``ticker`` matches, else None. Never raises."""
    match = PGA_TICKER_RE.match(ticker.strip())
    if match is None:
        return None
    tcode = match.group("tcode")
    try:
        year = 2000 + int(match.group("yy"))
    except ValueError:
        return None
    return PgaMarketRef(
        event_code=f"{tcode}{match.group('yy')}",
        tournament_code=tcode,
        year=year,
        player_slug=match.group("player"),
        raw_ticker=ticker.strip(),
    )


def build_pga_market_ticker(
    *,
    tournament_code: str,
    year: int,
    player_slug: str | None = None,
) -> str:
    """Construct a Kalshi PGA ticker. Inverse of :func:`parse_pga_market_ticker`.

    Raises ``ValueError`` on a malformed tournament code or player slug.
    ``player_slug=None`` builds the event-level ticker.
    """
    if not (
        2 <= len(tournament_code) <= 5 and tournament_code.isalpha() and tournament_code.isupper()
    ):
        raise ValueError(f"bad tournament_code {tournament_code!r}: need 2-5 uppercase letters")
    yy = f"{year % 100:02d}"
    base = f"{KXPGATOUR_PREFIX}-{tournament_code}{yy}"
    if player_slug is None:
        return base
    if not (player_slug.isalnum() and player_slug.isupper()):
        raise ValueError(f"player_slug must be uppercase alphanumeric, got {player_slug!r}")
    return f"{base}-{player_slug}"


__all__ = [
    "KXPGATOUR_PREFIX",
    "PGA_TICKER_RE",
    "PgaMarketRef",
    "build_pga_market_ticker",
    "parse_pga_market_ticker",
]
