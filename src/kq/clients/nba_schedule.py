"""NBA schedule + game-result client.

Wraps `nba_api.stats.endpoints` to fetch:
  * **Daily scoreboard** — `scoreboardv2.ScoreboardV2(game_date=...)` returns
    completed games (with scores) and scheduled games (without).
  * **Historical games for backfill** — `leaguegamefinder.LeagueGameFinder`
    returns one row per (game, team) for a date range. We aggregate to
    one row per game.

NBA Phase 3 PR 1 per the
[Phase 3 plan doc](../../../docs/research/PHASE-3-NBA-PLAN.md). The
client is **read-only** and stateless; no caching, no DB writes.

Threading model: `nba_api` is sync (uses `requests`), so we keep the
client sync. Callers that need async should wrap in `asyncio.to_thread`.

Rate limiting: `nba_api` defaults to a 30s timeout per request. NBA's
public stats endpoint has unauthenticated rate limits (informally
~30 req/min); the daily scoreboard is one request per day so we're far
below that for normal use. Backfill loops should sleep briefly between
requests; the helper `iter_dates_range` provides the iteration scaffold
and callers add their own sleep cadence.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import structlog

log = structlog.get_logger(__name__)

# `nba_api` defaults are noisy under our INFO log level; quiet to WARNING.
logging.getLogger("nba_api").setLevel(logging.WARNING)

# ScoreboardV2's GAME_STATUS_ID: 1 = scheduled, 2 = in progress, 3 = final.
_GAME_STATUS_FINAL: int = 3

# Fixed EST offset for deriving the US/Eastern calendar date — same
# no-DST convention as ``kq.models.nba_crosswalk.odds_api_to_us_eastern_date``
# (duplicated to keep clients/ free of models/ imports).
_US_EASTERN_OFFSET_HOURS: int = -5

# Season type strings as the API returns them — pinned here so callers can
# switch on a known set without inspecting each parsed row.
SEASON_TYPE_REGULAR: str = "Regular Season"
SEASON_TYPE_PLAYOFFS: str = "Playoffs"
SEASON_TYPE_PRESEASON: str = "Preseason"
SEASON_TYPE_ALL_STAR: str = "All Star"


@dataclass(frozen=True, slots=True)
class NbaGameRow:
    """One game's flat representation. Maps 1:1 to the `nba_game` schema.

    ``home_score`` / ``away_score`` / ``home_won`` are ``None`` until the
    source reports the game as FINAL — never derived from a live mid-game
    score. A non-None ``home_won`` is what settlement (irreversible) and
    PR-D's finished-game guard key on, so populating it early would settle
    trades on a partial score.
    """

    game_id: str
    season: str  # e.g., "2024-25"
    season_type: str
    game_date: date
    home_team_id: int
    home_team_abbr: str
    away_team_id: int
    away_team_abbr: str
    home_score: int | None  # None until the game is FINAL
    away_score: int | None
    home_won: bool | None


class NbaScheduleClient:
    """Sync client. Construct once and call methods as needed.

    The two public methods (`fetch_games_for_date`, `fetch_games_for_range`)
    return lists of `NbaGameRow`. Both methods catch upstream errors and
    return an empty list with a structured warning — better to surface
    "no data" than to crash a daily ingest.
    """

    def __init__(self, *, request_timeout_s: float = 30.0) -> None:
        self._timeout = request_timeout_s

    def fetch_games_for_date(self, target_date: date) -> list[NbaGameRow]:
        """Pull every game scheduled for `target_date` (US/Eastern day).

        Returns an empty list when:
          * The date has no games (e.g., NBA off-season day).
          * Upstream returns an error (logged at WARNING).
        """
        try:
            # Lazy import to keep `nba_api` out of the client module's import
            # cost when the caller only constructs the client (e.g., for tests).
            from nba_api.stats.endpoints import scoreboardv2  # noqa: PLC0415

            board = scoreboardv2.ScoreboardV2(
                game_date=target_date.isoformat(),
                timeout=self._timeout,
            )
            game_header = board.game_header.get_dict()
            line_score = board.line_score.get_dict()
        except Exception as exc:
            log.warning(
                "nba_schedule.scoreboard_failed", date=target_date.isoformat(), error=str(exc)
            )
            return []

        return _parse_scoreboard(game_header, line_score)

    def fetch_games_for_range(
        self,
        *,
        start: date,
        end: date,
    ) -> list[NbaGameRow]:
        """Pull every completed game in [start, end] (inclusive).

        Used for backfill. ``end`` defaults to "today" semantics in callers;
        we accept it explicitly for testability.
        """
        if end < start:
            raise ValueError(f"end {end} precedes start {start}")
        try:
            from nba_api.stats.endpoints import leaguegamefinder  # noqa: PLC0415

            finder = leaguegamefinder.LeagueGameFinder(
                date_from_nullable=start.strftime("%m/%d/%Y"),
                date_to_nullable=end.strftime("%m/%d/%Y"),
                league_id_nullable="00",  # NBA proper (vs WNBA="10", G League="20")
                timeout=self._timeout,
            )
            payload = finder.league_game_finder_results.get_dict()
        except Exception as exc:
            log.warning(
                "nba_schedule.leaguegamefinder_failed",
                start=start.isoformat(),
                end=end.isoformat(),
                error=str(exc),
            )
            return []

        return _parse_leaguegamefinder(payload)


def iter_dates_range(start: date, end: date) -> Iterator[date]:
    """Inclusive day-by-day iteration. Provided so callers can write their
    own sleep/throttle loop without re-implementing date arithmetic."""
    if end < start:
        raise ValueError(f"end {end} precedes start {start}")
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def _us_eastern_today(now_utc: datetime | None = None) -> date:
    """Current US/Eastern calendar date under the fixed-EST convention."""
    now = now_utc or datetime.now(tz=UTC)
    return (now.astimezone(UTC) + timedelta(hours=_US_EASTERN_OFFSET_HOURS)).date()


def _scoreboard_reported_final(header: dict[str, Any]) -> bool | None:
    """Tri-state finality from ScoreboardV2's status fields.

    Real scoreboard payloads carry ``GAME_STATUS_ID`` (1 scheduled /
    2 in progress / 3 final) and ``GAME_STATUS_TEXT`` ("Final",
    "Q3 5:32", "7:00 pm ET"). Returns True/False when either field is
    present, ``None`` when the payload carries no status signal at all
    (drift / minimal fixtures) so the caller can apply the conservative
    date-based rule instead.
    """
    status_id = _coerce_int(header.get("GAME_STATUS_ID"))
    if status_id is not None:
        return status_id == _GAME_STATUS_FINAL
    status_text = header.get("GAME_STATUS_TEXT")
    if status_text is not None and str(status_text).strip():
        return str(status_text).strip().lower().startswith("final")
    return None


def _conservatively_final(
    *,
    home_score: int | None,
    away_score: int | None,
    game_date: date,
    today_et: date,
) -> bool:
    """Fallback finality when the source payload has no status field:
    require BOTH scores present AND the game's US/Eastern date strictly
    before the current US/Eastern date. Same-day scores are treated as
    live (better to settle a day late than settle a mid-game score)."""
    return home_score is not None and away_score is not None and game_date < today_et


def _parse_scoreboard(
    game_header: dict[str, Any],
    line_score: dict[str, Any],
    *,
    today_et: date | None = None,
) -> list[NbaGameRow]:
    """Parse `ScoreboardV2`'s response. The API returns two parallel tables:

      * `game_header`: one row per game with `GAME_ID`, `HOME_TEAM_ID`,
        `VISITOR_TEAM_ID`, `GAME_STATUS_ID`/`GAME_STATUS_TEXT`, season metadata.
      * `line_score`: TWO rows per game (one per team) with `PTS`, `TEAM_ABBREVIATION`.

    We join on `GAME_ID` + `TEAM_ID` to get scores per home/away. Scores and
    ``home_won`` are only populated for FINAL games: the scoreboard reports a
    live ``PTS`` while a game is in progress, and a non-None ``home_won``
    irreversibly settles paper trades downstream. Finality comes from
    ``GAME_STATUS_ID``/``GAME_STATUS_TEXT`` when present (always is on real
    payloads), else the conservative both-scores-and-day-elapsed rule.
    """
    game_rows = _zip_dict(game_header)
    line_rows = _zip_dict(line_score)
    today = today_et or _us_eastern_today()

    # Build (game_id -> {team_id: row}) for the line score.
    line_by_game: dict[str, dict[int, dict[str, Any]]] = {}
    for line in line_rows:
        game_id = str(line.get("GAME_ID", ""))
        team_id = line.get("TEAM_ID")
        if not game_id or team_id is None:
            continue
        line_by_game.setdefault(game_id, {})[int(team_id)] = line

    out: list[NbaGameRow] = []
    for header in game_rows:
        row = _build_row_from_scoreboard(header, line_by_game, today_et=today)
        if row is not None:
            out.append(row)
    return out


def _build_row_from_scoreboard(
    header: dict[str, Any],
    line_by_game: dict[str, dict[int, dict[str, Any]]],
    *,
    today_et: date,
) -> NbaGameRow | None:
    game_id = str(header.get("GAME_ID", ""))
    if not game_id:
        return None
    home_team_id = _coerce_int(header.get("HOME_TEAM_ID"))
    away_team_id = _coerce_int(header.get("VISITOR_TEAM_ID"))
    if home_team_id is None or away_team_id is None:
        return None

    line = line_by_game.get(game_id, {})
    home_line = line.get(home_team_id, {})
    away_line = line.get(away_team_id, {})

    home_score = _coerce_int(home_line.get("PTS"))
    away_score = _coerce_int(away_line.get("PTS"))
    game_date = _parse_game_date(header.get("GAME_DATE_EST", ""))

    final = _scoreboard_reported_final(header)
    if final is None:
        final = _conservatively_final(
            home_score=home_score, away_score=away_score, game_date=game_date, today_et=today_et
        )
    if not final:
        # In-progress / scheduled: a live PTS must never look like a result.
        home_score = None
        away_score = None
    home_won = (
        (home_score > away_score) if (home_score is not None and away_score is not None) else None
    )

    return NbaGameRow(
        game_id=game_id,
        season=str(header.get("SEASON") or _derive_season_from_game_id(game_id)),
        season_type=_derive_season_type_from_game_id(game_id),
        game_date=game_date,
        home_team_id=home_team_id,
        home_team_abbr=str(home_line.get("TEAM_ABBREVIATION") or ""),
        away_team_id=away_team_id,
        away_team_abbr=str(away_line.get("TEAM_ABBREVIATION") or ""),
        home_score=home_score,
        away_score=away_score,
        home_won=home_won,
    )


def _parse_leaguegamefinder(
    payload: dict[str, Any],
    *,
    today_et: date | None = None,
) -> list[NbaGameRow]:
    """LeagueGameFinder returns one row per (game, team), so games appear
    twice. We aggregate to one row per `GAME_ID`. Each game-team row has
    `MATCHUP` like "BOS @ LAL" (away) or "LAL vs. BOS" (home), which is how
    we identify which side is home. Finality comes from the row's `WL`
    field ('W'/'L' once the game is final, None while live) when the
    payload carries it, else the conservative day-elapsed rule."""
    rows = _zip_dict(payload)
    today = today_et or _us_eastern_today()
    by_game: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        game_id = str(r.get("GAME_ID", ""))
        if game_id:
            by_game.setdefault(game_id, []).append(r)

    out: list[NbaGameRow] = []
    for game_id, sides in by_game.items():
        game = _build_row_from_lgf_sides(game_id, sides, today_et=today)
        if game is not None:
            out.append(game)
    return out


def _lgf_reported_final(home: dict[str, Any], away: dict[str, Any]) -> bool | None:
    """Tri-state finality from LeagueGameFinder's `WL` column: 'W'/'L' once
    final, None/empty while live. Returns ``None`` only when neither side
    carries the column at all (payload drift / minimal fixtures)."""
    if "WL" not in home and "WL" not in away:
        return None
    wl = str(home.get("WL") or away.get("WL") or "").strip().upper()
    return wl in {"W", "L"}


def _build_row_from_lgf_sides(
    game_id: str,
    sides: list[dict[str, Any]],
    *,
    today_et: date,
) -> NbaGameRow | None:
    if len(sides) != 2:
        # Most often the API returned a partial view; skip rather than guess.
        return None
    # Find which side is home via MATCHUP "vs." (home) or "@" (away).
    home, away = None, None
    for s in sides:
        matchup = str(s.get("MATCHUP", ""))
        if " vs. " in matchup:
            home = s
        elif " @ " in matchup:
            away = s
    if home is None or away is None:
        return None

    home_team_id = _coerce_int(home.get("TEAM_ID"))
    away_team_id = _coerce_int(away.get("TEAM_ID"))
    if home_team_id is None or away_team_id is None:
        # Malformed/partial API response — skip rather than KeyError.
        return None

    home_score = _coerce_int(home.get("PTS"))
    away_score = _coerce_int(away.get("PTS"))
    game_date = _parse_game_date(str(home.get("GAME_DATE", "")))

    final = _lgf_reported_final(home, away)
    if final is None:
        final = _conservatively_final(
            home_score=home_score, away_score=away_score, game_date=game_date, today_et=today_et
        )
    if not final:
        home_score = None
        away_score = None
    home_won = (
        (home_score > away_score) if (home_score is not None and away_score is not None) else None
    )
    return NbaGameRow(
        game_id=game_id,
        season=str(home.get("SEASON_ID") or _derive_season_from_game_id(game_id)),
        season_type=_derive_season_type_from_game_id(game_id),
        game_date=game_date,
        home_team_id=home_team_id,
        home_team_abbr=str(home.get("TEAM_ABBREVIATION") or ""),
        away_team_id=away_team_id,
        away_team_abbr=str(away.get("TEAM_ABBREVIATION") or ""),
        home_score=home_score,
        away_score=away_score,
        home_won=home_won,
    )


def _zip_dict(table: dict[str, Any]) -> list[dict[str, Any]]:
    """`nba_api`'s `.get_dict()` returns ``{"headers": [...], "data": [[...], ...]}``.
    Convert to a list of dicts keyed by header."""
    headers = table.get("headers") or []
    data = table.get("data") or []
    return [dict(zip(headers, row, strict=False)) for row in data]


def _coerce_int(value: Any) -> int | None:
    """Best-effort int coercion; returns None on missing/empty/non-numeric."""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_game_date(raw: str) -> date:
    """`GAME_DATE_EST` (scoreboard) and `GAME_DATE` (LGF) are both
    ISO-8601 dates / datetimes. Returns `date(1900,1,1)` for empty input
    so a downstream PK conflict surfaces rather than a None corruption."""
    if not raw:
        return date(1900, 1, 1)
    # Both APIs include time info; drop it.
    head = raw.split("T", 1)[0]
    try:
        return datetime.strptime(head, "%Y-%m-%d").date()
    except ValueError:
        # LGF sometimes returns "MM/DD/YYYY"; try that fallback.
        try:
            return datetime.strptime(head, "%m/%d/%Y").date()
        except ValueError:
            log.warning("nba_schedule.unparseable_date", raw=raw)
            return date(1900, 1, 1)


def _derive_season_from_game_id(game_id: str) -> str:
    """NBA game ids encode the season in positions 3-4 ("0022400123" -> "24" -> "2024-25").

    The format: 1 char season-type + 1 char unused + 2 chars season-year-suffix +
    5 chars sequence. We extract the year suffix and reconstruct "YYYY-YY"."""
    if len(game_id) < 5:
        return ""
    year_suffix = game_id[3:5]
    try:
        yr = int(year_suffix)
    except ValueError:
        return ""
    # Two-digit year disambiguation: NBA seasons tracked since 1946; we'll
    # treat 00..50 as 2000s, 51..99 as 1900s. Realistic for foreseeable use.
    full_start = 2000 + yr if yr <= 50 else 1900 + yr
    return f"{full_start}-{(full_start + 1) % 100:02d}"


def _derive_season_type_from_game_id(game_id: str) -> str:
    """Char[0] is the league marker ("0" = NBA proper); chars[1:3] encode
    the season type:
       "01" -> Preseason
       "02" -> Regular Season
       "03" -> All Star
       "04" -> Playoffs
       "05" -> Play-In Tournament (newer; falls through to "Other" since
              the schema doesn't track it as a separate type yet)

    Returns "Other" for unknown prefixes (e.g. WNBA "10..", G League "20..").
    """
    if not game_id or len(game_id) < 3:
        return "Other"
    code = game_id[1:3]
    return {
        "01": SEASON_TYPE_PRESEASON,
        "02": SEASON_TYPE_REGULAR,
        "03": SEASON_TYPE_ALL_STAR,
        "04": SEASON_TYPE_PLAYOFFS,
    }.get(code, "Other")


__all__ = [
    "SEASON_TYPE_ALL_STAR",
    "SEASON_TYPE_PLAYOFFS",
    "SEASON_TYPE_PRESEASON",
    "SEASON_TYPE_REGULAR",
    "NbaGameRow",
    "NbaScheduleClient",
    "iter_dates_range",
]
