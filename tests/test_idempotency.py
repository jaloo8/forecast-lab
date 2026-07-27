"""Idempotency regression guards for the ingest repositories.

The cron soak re-runs every ingest constantly (weather every 6 h, METAR every
15 min, NDFD every 6 h, ...), so each repository write MUST be idempotent:
re-inserting the SAME rows must NOT grow the table, and re-inserting with a
changed value at the same PK must REPLACE in place. Every repo uses
``INSERT OR REPLACE`` today; these tests pin that invariant so a future change
to a plain ``INSERT`` -- which would silently duplicate data on every cron tick
and corrupt the model's training set -- fails CI.

Covers every ingest/upsert path that the cron soak re-runs:

- **Weather lane** — forecasts / METAR / observed (highest-frequency writers).
- **NDFD/NBM benchmark** — ``ndfd_forecast`` (every 6 h).
- **NBA lane** — ``nba_game`` (PK ``game_id``, with a NULL→score replace
  transition) + ``nba_odds`` (PK includes ``fetched_at`` — a deliberate
  line-movement time-series, so a *new* fetch appends but a re-run with the
  same ``fetched_at`` is a no-op).
- **Kalshi lane** — ``kalshi_market`` (PK ``ticker``) + ``kalshi_book_snap``
  (PK ``(snap_time, ticker)``).
- **NFL player lane (Fantasy F1a)** — ``nfl_player_game`` (PK
  ``(player_id, season, week, season_type)``, stat corrections replace in
  place) + ``nfl_player_projection`` (``as_of`` in the PK — an append-only
  point-in-time ledger like the odds tables: same ``as_of`` is a no-op, a
  new ``as_of`` appends).
- **Social event lane (Phase S1)** — ``social_post`` (PK ``(source,
  source_post_id)``): re-fetch is a no-op, upstream EDITS replace
  title/text in place, and the first-sighting stamps (``as_of`` +
  ``created_at``) NEVER move — publishers bump pubDate on edits, which
  would otherwise fake freshness in the latency ledger. NULLs from a
  degraded re-parse never wipe stored values (weather_observed posture).

Each lane gets a run-twice-stable guard and, where the PK admits in-place
updates, a replace-in-place guard. The matrix (docs/TESTING.md) tracks the
mapping from module to test type.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb

from kq.clients.acis import DailyClimateObservation
from kq.clients.kalshi import Market, OrderBookSnapshot
from kq.clients.metar import MetarObservation
from kq.clients.nba_schedule import NbaGameRow
from kq.clients.ndfd import NbmDeterministicForecast
from kq.clients.nfl_players import PlayerGameRow
from kq.clients.openmeteo import EnsembleForecast
from kq.storage.duckdb_store import bootstrap
from kq.storage.repositories.forecasts import insert_forecasts
from kq.storage.repositories.kalshi import insert_kalshi_books, upsert_kalshi_markets
from kq.storage.repositories.metar import insert_metar
from kq.storage.repositories.nba import upsert_nba_games
from kq.storage.repositories.nba_odds import OddsRow, upsert_odds_rows
from kq.storage.repositories.ndfd import insert_ndfd_forecasts
from kq.storage.repositories.nfl_players import (
    ProjectionRow,
    insert_projections,
    upsert_player_games,
)
from kq.storage.repositories.observed import insert_observed
from kq.storage.repositories.social import SocialPostRow, upsert_social_posts


def _con(tmp_path: Path) -> duckdb.DuckDBPyConnection:
    db = tmp_path / "idem.duckdb"
    bootstrap(db)
    return duckdb.connect(str(db))


def _count(con: duckdb.DuckDBPyConnection, table: str) -> int:
    return int(con.execute(f"SELECT count(*) FROM {table}").fetchone()[0])


def _forecasts() -> list[EnsembleForecast]:
    aso = datetime(2025, 1, 1, 0, 0, tzinfo=UTC)
    return [
        EnsembleForecast(
            as_of=aso,
            run_time=aso,
            model="gfs_seamless",
            member=m,
            station="KLAX",
            valid_date=date(2025, 1, 2),
            forecast_high_f=75.0 + m,
            forecast_low_f=55.0,
        )
        for m in range(3)
    ]


def test_insert_forecasts_idempotent(tmp_path: Path) -> None:
    con = _con(tmp_path)
    rows = _forecasts()
    insert_forecasts(con, rows)
    assert _count(con, "weather_forecast") == 3
    insert_forecasts(con, rows)  # same rows again
    assert _count(con, "weather_forecast") == 3


def test_forecasts_replace_updates_in_place(tmp_path: Path) -> None:
    con = _con(tmp_path)
    insert_forecasts(con, _forecasts())
    aso = datetime(2025, 1, 1, 0, 0, tzinfo=UTC)
    updated = [
        EnsembleForecast(
            as_of=aso,
            run_time=aso,
            model="gfs_seamless",
            member=0,
            station="KLAX",
            valid_date=date(2025, 1, 2),
            forecast_high_f=99.0,  # changed, same PK
            forecast_low_f=55.0,
        )
    ]
    insert_forecasts(con, updated)
    assert _count(con, "weather_forecast") == 3  # replaced, not appended
    val = con.execute(
        "SELECT forecast_high_f FROM weather_forecast WHERE member = 0 AND station = 'KLAX'"
    ).fetchone()[0]
    assert val == 99.0


def test_insert_metar_idempotent(tmp_path: Path) -> None:
    con = _con(tmp_path)
    t = datetime(2025, 1, 1, 12, 0, tzinfo=UTC)
    rows = [
        MetarObservation(
            obs_time=t, station=s, temp_f=70.0, dewpoint_f=50.0, wind_kt=5.0, pressure_mb=1013.0
        )
        for s in ("KLAX", "KJFK")
    ]
    insert_metar(con, rows)
    assert _count(con, "metar_obs") == 2
    insert_metar(con, rows)
    assert _count(con, "metar_obs") == 2


def test_insert_observed_idempotent(tmp_path: Path) -> None:
    con = _con(tmp_path)
    rows = [
        DailyClimateObservation(
            station="KLAX",
            valid_date=date(2025, 1, 2),
            high_f=78.0,
            low_f=54.0,
            source="acis",
            fetched_at=datetime(2025, 1, 3, 0, 0, tzinfo=UTC),
        )
    ]
    insert_observed(con, rows)
    assert _count(con, "weather_observed") == 1
    insert_observed(con, rows)
    assert _count(con, "weather_observed") == 1


# --------------------------------------------------------------- NDFD lane


def _ndfd() -> list[NbmDeterministicForecast]:
    aso = datetime(2025, 1, 1, 0, 0, tzinfo=UTC)
    return [
        NbmDeterministicForecast(
            as_of=aso,
            station=s,
            valid_date=date(2025, 1, 2),
            lead_days=1,
            forecast_max_f=72.0,
            source="nbm_deterministic_openmeteo",
        )
        for s in ("KLAX", "KJFK")
    ]


def test_insert_ndfd_idempotent(tmp_path: Path) -> None:
    con = _con(tmp_path)
    insert_ndfd_forecasts(con, _ndfd())
    assert _count(con, "ndfd_forecast") == 2
    insert_ndfd_forecasts(con, _ndfd())
    assert _count(con, "ndfd_forecast") == 2


def test_ndfd_replace_updates_in_place(tmp_path: Path) -> None:
    con = _con(tmp_path)
    insert_ndfd_forecasts(con, _ndfd())
    aso = datetime(2025, 1, 1, 0, 0, tzinfo=UTC)
    updated = [
        NbmDeterministicForecast(
            as_of=aso,
            station="KLAX",
            valid_date=date(2025, 1, 2),
            lead_days=1,
            forecast_max_f=88.0,  # changed, same PK
            source="nbm_deterministic_openmeteo",
        )
    ]
    insert_ndfd_forecasts(con, updated)
    assert _count(con, "ndfd_forecast") == 2  # replaced, not appended
    row = con.execute("SELECT forecast_max_f FROM ndfd_forecast WHERE station = 'KLAX'").fetchone()
    assert row is not None
    assert row[0] == 88.0


# --------------------------------------------------------------- NBA lane


def _nba_game(*, home_score: int | None, home_won: bool | None) -> NbaGameRow:
    return NbaGameRow(
        game_id="0022400123",
        season="2024-25",
        season_type="Regular Season",
        game_date=date(2025, 1, 2),
        home_team_id=1610612747,
        home_team_abbr="LAL",
        away_team_id=1610612744,
        away_team_abbr="GSW",
        home_score=home_score,
        away_score=110 if home_score is not None else None,
        home_won=home_won,
    )


def test_upsert_nba_games_idempotent(tmp_path: Path) -> None:
    con = _con(tmp_path)
    row = _nba_game(home_score=None, home_won=None)
    upsert_nba_games(con, [row])
    assert _count(con, "nba_game") == 1
    upsert_nba_games(con, [row])  # same game_id, re-pulled pre-tipoff
    assert _count(con, "nba_game") == 1


def test_nba_game_score_transition_replaces_in_place(tmp_path: Path) -> None:
    con = _con(tmp_path)
    upsert_nba_games(con, [_nba_game(home_score=None, home_won=None)])
    # Game finishes: scores transition NULL -> populated on the same game_id.
    upsert_nba_games(con, [_nba_game(home_score=118, home_won=True)])
    assert _count(con, "nba_game") == 1  # replaced, not a second row
    row = con.execute(
        "SELECT home_score, home_won FROM nba_game WHERE game_id = '0022400123'"
    ).fetchone()
    assert row is not None
    assert row[0] == 118
    assert row[1] is True


def _odds_row(*, fetched_at: datetime) -> OddsRow:
    return OddsRow(
        odds_api_game_id="abc123",
        bookmaker_key="pinnacle",
        market_key="h2h",
        home_team="Los Angeles Lakers",
        away_team="Golden State Warriors",
        commence_time=datetime(2025, 1, 2, 3, 0),
        home_decimal_odds=1.83,
        away_decimal_odds=2.05,
        book_last_update=datetime(2025, 1, 2, 2, 30),
        fetched_at=fetched_at,
    )


def test_upsert_odds_same_fetch_is_noop(tmp_path: Path) -> None:
    con = _con(tmp_path)
    row = _odds_row(fetched_at=datetime(2025, 1, 2, 2, 35))
    upsert_odds_rows(con, [row])
    assert _count(con, "nba_odds") == 1
    upsert_odds_rows(con, [row])  # identical PK incl. fetched_at -> no-op
    assert _count(con, "nba_odds") == 1


def test_upsert_odds_new_fetch_appends_timeseries(tmp_path: Path) -> None:
    con = _con(tmp_path)
    upsert_odds_rows(con, [_odds_row(fetched_at=datetime(2025, 1, 2, 2, 35))])
    # A later poll of the same game/book/market is a NEW row by design
    # (fetched_at is part of the PK -- this is the line-movement series).
    upsert_odds_rows(con, [_odds_row(fetched_at=datetime(2025, 1, 2, 3, 35))])
    assert _count(con, "nba_odds") == 2


# --------------------------------------------------------------- Kalshi lane


def _market(*, rules: str) -> Market:
    t = datetime(2025, 1, 1, 0, 0, tzinfo=UTC)
    return Market(
        ticker="HIGHLAX-25JAN02-T75",
        event_ticker="HIGHLAX-25JAN02",
        title="Will LAX high exceed 75F?",
        status="active",
        category="Climate",
        yes_ask=0.55,
        yes_bid=0.52,
        last_price=0.54,
        volume=100.0,
        open_interest=50.0,
        open_time=t,
        close_time=t,
        expected_expiration_time=t,
        rules_primary=rules,
    )


def test_upsert_kalshi_markets_idempotent_and_replace(tmp_path: Path) -> None:
    con = _con(tmp_path)
    upsert_kalshi_markets(con, [_market(rules="settles on KLAX METAR")])
    assert _count(con, "kalshi_market") == 1
    upsert_kalshi_markets(con, [_market(rules="settles on KLAX METAR (clarified)")])
    assert _count(con, "kalshi_market") == 1  # PK=ticker -> replaced in place
    row = con.execute(
        "SELECT rules_text FROM kalshi_market WHERE ticker = 'HIGHLAX-25JAN02-T75'"
    ).fetchone()
    assert row is not None
    assert row[0] == "settles on KLAX METAR (clarified)"


def _strike_market(
    *,
    strike_type: str | None,
    floor_strike: float | None,
    cap_strike: float | None,
    open_time: datetime | None,
    close_time: datetime | None,
    rules: str = "settles on KLAX climate report",
) -> Market:
    return Market(
        ticker="KXHIGHLAX-25JAN02-B76.5",
        event_ticker="KXHIGHLAX-25JAN02",
        title="LAX high 76-77F?",
        status="active",
        category="Climate",
        yes_ask=0.55,
        yes_bid=0.52,
        last_price=0.54,
        volume=100.0,
        open_interest=50.0,
        open_time=open_time,
        close_time=close_time,
        expected_expiration_time=close_time,
        rules_primary=rules,
        strike_type=strike_type,
        floor_strike=floor_strike,
        cap_strike=cap_strike,
    )


def test_upsert_kalshi_markets_degraded_payload_cannot_null_strikes(tmp_path: Path) -> None:
    """Settlement reads kalshi_market as point-in-time truth: one degraded
    payload (strike fields / open+close times missing) must NOT wipe the
    stored values — the old blind INSERT OR REPLACE did exactly that.
    Ordinary non-guarded fields (rules_text) still update."""
    con = _con(tmp_path)
    t_open = datetime(2025, 1, 1, 0, 0, tzinfo=UTC)
    t_close = datetime(2025, 1, 2, 23, 0, tzinfo=UTC)
    upsert_kalshi_markets(
        con,
        [
            _strike_market(
                strike_type="between",
                floor_strike=76.0,
                cap_strike=77.0,
                open_time=t_open,
                close_time=t_close,
            )
        ],
    )
    upsert_kalshi_markets(
        con,
        [
            _strike_market(
                strike_type=None,
                floor_strike=None,
                cap_strike=None,
                open_time=None,
                close_time=None,
                rules="clarified rules",
            )
        ],
    )
    assert _count(con, "kalshi_market") == 1
    row = con.execute(
        """
        SELECT strike_type, floor_strike, cap_strike, opens_at, closes_at, rules_text
        FROM kalshi_market WHERE ticker = 'KXHIGHLAX-25JAN02-B76.5'
        """
    ).fetchone()
    assert row is not None
    assert row[0] == "between"
    assert row[1] == 76.0
    assert row[2] == 77.0
    assert row[3] == t_open.replace(tzinfo=None)
    assert row[4] == t_close.replace(tzinfo=None)
    assert row[5] == "clarified rules"


def test_upsert_kalshi_markets_real_values_still_update_guarded_fields(tmp_path: Path) -> None:
    """The guard blocks NULLs only: a payload carrying real strike/time
    values updates the stored ones (venue corrections must flow through)."""
    con = _con(tmp_path)
    t_open = datetime(2025, 1, 1, 0, 0, tzinfo=UTC)
    t_close = datetime(2025, 1, 2, 23, 0, tzinfo=UTC)
    upsert_kalshi_markets(
        con,
        [
            _strike_market(
                strike_type="between",
                floor_strike=76.0,
                cap_strike=77.0,
                open_time=t_open,
                close_time=t_close,
            )
        ],
    )
    upsert_kalshi_markets(
        con,
        [
            _strike_market(
                strike_type="between",
                floor_strike=75.0,
                cap_strike=76.0,
                open_time=t_open,
                close_time=t_close + timedelta(hours=1),
            )
        ],
    )
    row = con.execute(
        """
        SELECT floor_strike, cap_strike, closes_at
        FROM kalshi_market WHERE ticker = 'KXHIGHLAX-25JAN02-B76.5'
        """
    ).fetchone()
    assert row is not None
    assert row[0] == 75.0
    assert row[1] == 76.0
    assert row[2] == (t_close + timedelta(hours=1)).replace(tzinfo=None)


def _book_snap(*, snap_time: datetime) -> OrderBookSnapshot:
    return OrderBookSnapshot(
        snap_time=snap_time,
        ticker="HIGHLAX-25JAN02-T75",
        yes_bid=0.52,
        yes_ask=0.55,
        yes_bid_size=10,
        yes_ask_size=12,
        yes_bids=((52, 10),),
        yes_asks=((55, 12),),
    )


def test_insert_kalshi_books_idempotent(tmp_path: Path) -> None:
    con = _con(tmp_path)
    t = datetime(2025, 1, 2, 18, 0, tzinfo=UTC)
    insert_kalshi_books(con, [_book_snap(snap_time=t)])
    assert _count(con, "kalshi_book_snap") == 1
    insert_kalshi_books(con, [_book_snap(snap_time=t)])  # same (snap_time, ticker)
    assert _count(con, "kalshi_book_snap") == 1


def test_insert_kalshi_books_new_snap_appends(tmp_path: Path) -> None:
    con = _con(tmp_path)
    insert_kalshi_books(con, [_book_snap(snap_time=datetime(2025, 1, 2, 18, 0, tzinfo=UTC))])
    insert_kalshi_books(con, [_book_snap(snap_time=datetime(2025, 1, 2, 18, 0, 30, tzinfo=UTC))])
    assert _count(con, "kalshi_book_snap") == 2  # distinct snap_time -> new row


# --------------------------------------------------- NFL player lane (F1a)


def _player_game(*, fantasy_std: float = 14.14) -> PlayerGameRow:
    return PlayerGameRow(
        player_id="00-0033873",
        player_name="Patrick Mahomes",
        season=2024,
        week=1,
        season_type="REG",
        team="KC",
        opponent="BAL",
        position="QB",
        snaps=54.0,
        snap_pct=1.0,
        targets=1,
        receptions=1,
        carries=2,
        passing_yards=291.0,
        passing_tds=1,
        rushing_yards=3.0,
        rushing_tds=0,
        receiving_yards=2.0,
        receiving_tds=0,
        fumbles_lost=0.0,
        interceptions=1.0,
        red_zone_touches=None,
        fantasy_points_std=fantasy_std,
        fantasy_points_ppr=fantasy_std + 1.0,
    )


def test_upsert_player_games_idempotent(tmp_path: Path) -> None:
    con = _con(tmp_path)
    as_of = datetime(2025, 1, 10, 11, 0, tzinfo=UTC)
    upsert_player_games(con, [_player_game()], as_of=as_of)
    assert _count(con, "nfl_player_game") == 1
    upsert_player_games(con, [_player_game()], as_of=as_of)  # same rows again
    assert _count(con, "nfl_player_game") == 1


def test_player_game_correction_replaces_in_place(tmp_path: Path) -> None:
    con = _con(tmp_path)
    upsert_player_games(con, [_player_game(fantasy_std=14.14)])
    upsert_player_games(con, [_player_game(fantasy_std=14.64)])  # stat correction, same PK
    assert _count(con, "nfl_player_game") == 1
    row = con.execute(
        "SELECT fantasy_points_std FROM nfl_player_game WHERE player_id = '00-0033873'"
    ).fetchone()
    assert row is not None
    assert row[0] == 14.64


def _projection_row(*, as_of: datetime) -> ProjectionRow:
    return ProjectionRow(
        player_id="00-0033873",
        player_name="Patrick Mahomes",
        season=2025,
        week=1,
        scoring_format="std",
        projected_points=18.2,
        floor_points=9.1,
        ceiling_points=28.4,
        as_of=as_of,
        model_version="fantasy_nfl_v0",
    )


def test_insert_projections_same_as_of_is_noop(tmp_path: Path) -> None:
    con = _con(tmp_path)
    row = _projection_row(as_of=datetime(2025, 9, 2, 11, 0, tzinfo=UTC))
    insert_projections(con, [row])
    assert _count(con, "nfl_player_projection") == 1
    insert_projections(con, [row])  # identical PK incl. as_of -> no-op
    assert _count(con, "nfl_player_projection") == 1


def test_insert_projections_new_as_of_appends_ledger(tmp_path: Path) -> None:
    con = _con(tmp_path)
    insert_projections(con, [_projection_row(as_of=datetime(2025, 9, 2, 11, 0, tzinfo=UTC))])
    # A re-projection closer to kickoff is a NEW ledger row by design.
    insert_projections(con, [_projection_row(as_of=datetime(2025, 9, 7, 13, 0, tzinfo=UTC))])
    assert _count(con, "nfl_player_projection") == 2


# --- social event lane (Phase S1) -------------------------------------------


def _social_post(
    *,
    title: str = "[Schefter] Colts placed WR Alec Pierce on the PUP list",
    text: str | None = "submitted by /u/MattyT7",
    author: str | None = "/u/MattyT7",
    created_at: datetime | None = None,
    matched: bool = True,
) -> SocialPostRow:
    return SocialPostRow(
        source="reddit",
        source_post_id="t3_1v8dm3p",
        subreddit_or_feed="r/nfl",
        author=author,
        title=title,
        text=text,
        url="https://www.reddit.com/r/nfl/comments/1v8dm3p/",
        is_official=False,
        created_at=created_at or datetime(2026, 7, 27, 21, 19, 22, tzinfo=UTC),
        matched_entity_type="nfl_player" if matched else None,
        matched_entity_id="00-0037247" if matched else None,
    )


def test_social_posts_reinsert_is_stable(tmp_path: Path) -> None:
    con = _con(tmp_path)
    first = datetime(2026, 7, 27, 22, 0, tzinfo=UTC)
    upsert_social_posts(con, [_social_post()], as_of=first)
    assert _count(con, "social_post") == 1
    upsert_social_posts(con, [_social_post()], as_of=first + timedelta(minutes=15))
    assert _count(con, "social_post") == 1


def test_social_post_edit_replaces_text_but_stamps_never_move(tmp_path: Path) -> None:
    """An upstream edit updates title/text; the first-sighting `as_of` and
    `created_at` are FROZEN even when the publisher bumps the source clock
    (pubDate-on-edit would otherwise fake freshness), and `fetched_at`
    advances to the latest touch."""
    con = _con(tmp_path)
    first = datetime(2026, 7, 27, 22, 0, tzinfo=UTC)
    original_created = datetime(2026, 7, 27, 21, 19, 22, tzinfo=UTC)
    upsert_social_posts(con, [_social_post(created_at=original_created)], as_of=first)

    later = first + timedelta(hours=2)
    edited = _social_post(
        title="[Schefter] Colts placed WR Alec Pierce on the PUP list (updated)",
        text="edited body",
        created_at=original_created + timedelta(hours=1),  # publisher bumped pubDate
    )
    upsert_social_posts(con, [edited], as_of=later)

    assert _count(con, "social_post") == 1
    row = con.execute(
        "SELECT title, text, created_at, as_of, fetched_at FROM social_post"
    ).fetchone()
    assert row is not None
    title, text, created_at, as_of, fetched_at = row
    assert title.endswith("(updated)")
    assert text == "edited body"
    assert created_at == original_created.replace(tzinfo=None)  # frozen
    assert as_of == first.replace(tzinfo=None)  # frozen
    assert fetched_at == later.replace(tzinfo=None)  # advances


def test_social_post_nulls_never_wipe_stored_values(tmp_path: Path) -> None:
    con = _con(tmp_path)
    upsert_social_posts(con, [_social_post()])
    degraded = _social_post(text=None, author=None, matched=False)
    upsert_social_posts(con, [degraded])
    row = con.execute(
        "SELECT text, author, matched_entity_type, matched_entity_id FROM social_post"
    ).fetchone()
    assert row is not None
    assert row[0] == "submitted by /u/MattyT7"
    assert row[1] == "/u/MattyT7"
    assert (row[2], row[3]) == ("nfl_player", "00-0037247")
