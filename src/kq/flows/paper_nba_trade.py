"""NBA paper-trading flow (submit + settle).

This is the orchestrator that connects the pieces shipped in earlier PRs into
a single ``run_once_nba()`` cycle. Mirrors :mod:`kq.flows.paper_trade` for
weather, but with NBA-specific data joins.

Submit pass (per game where Kalshi has an open market and we have data):

1. Fold the ``nba_game`` completed-game history (regular season + playoffs
   only — preseason/exhibition results are excluded, 2026-07-01 audit) into
   a fresh Elo state (538-style, with between-seasons regression to the
   mean and home-court / B2B / travel / altitude adjustments from
   :mod:`kq.models.nba_elo`).
2. Pull every open ``KXNBAGAME`` market via its SERIES ticker (cursor-paged
   by the client — 2026-06-11 audit #5: the unfiltered first page of
   ``/markets`` on prod never contains NBA games).
3. Group per-side tickers by (game_date, home, away) — Kalshi lists a
   YES-home AND a YES-away market for every game. Skip games that already
   tipped off (pre-tipoff guard), then evaluate every side with the latest
   Pinnacle h2h quote (via the crosswalk) and a schedule-derived
   :class:`GameContext`, via :func:`kq.execution.paper_nba.evaluate_nba_signal`.
4. Record AT MOST ONE side per game — the one with the larger post-fee edge
   (2026-06-11 audit #6: trading both sides doubled Kelly exposure and
   double-counted settles). Persist via
   :func:`insert_paper_trade_with_signal` (same path the weather flow uses).
   Idempotent: re-runs with unchanged inputs don't double-insert.

Settle pass: :func:`settle_due_nba_paper_trades` walks every unsettled
NBA-ticker trade, looks up ``nba_game.home_won``, and writes the result.

Skip conditions (logged as structured warnings, not errors):

* Kalshi credentials missing -> ``skipped_reason='no_kalshi_creds'`` and exit
  the submit pass; settlement still runs.
* No open NBA markets on Kalshi -> empty submit, settlement runs.
* No crosswalk row for a given Kalshi ticker -> skip that game (still need
  ``build-nba-crosswalk`` to have caught up to the matchup).
* No Pinnacle quote -> evaluator falls back to Elo automatically; the signal
  is tagged ``nba_elo_fallback_v1`` instead of ``nba_pinnacle_anchored_v1``.
* Elo fallback with a thin state (either team under
  ``MIN_SETTLED_GAMES_FOR_RATING`` settled games) or a ticker naming an
  unknown team -> NO signal for that game; counted in the run summary as
  ``submit_skipped_insufficient_data`` (2026-07-01 audit, Tier 1: a fresh
  DB traded confidently off the home-court prior alone).

Why no nowcasting / brackets / forecasts here:

* NBA games are binary outcomes; no need for bracket generation.
* Elo updates discretely after each finished game, not continuously like
  METAR — no nowcast layer.
* Pinnacle's vig-stripped fair IS the intraday update — we just refresh
  ``nba_odds`` separately via ``kq ingest-nba-odds``.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Final

import structlog

from kq.clients.kalshi import KalshiClient, KalshiCredentialsError, Market
from kq.clients.kalshi._ticker_parser_nba import NbaMarketRef, parse_nba_market_ticker
from kq.clients.nba_schedule import SEASON_TYPE_PLAYOFFS, SEASON_TYPE_REGULAR
from kq.config import get_settings
from kq.execution.fees import fee_per_contract
from kq.execution.paper import (
    DEFAULT_KELLY_FRACTION,
    DEFAULT_MAX_STAKE_USD,
    DEFAULT_MIN_EDGE_PCT,
    PaperTradeIntent,
)
from kq.execution.paper_nba import (
    NbaQuotePair,
    NbaSignalDecision,
    NbaSignalInputs,
    evaluate_nba_signal,
)
from kq.flows.ingest_weather import _db_path_from_settings
from kq.models.nba_crosswalk import odds_api_to_us_eastern_date
from kq.models.nba_elo import (
    KNOWN_TEAM_ABBRS,
    MIN_SETTLED_GAMES_FOR_RATING,
    GameContext,
    NbaEloRatings,
    season_start_year,
    update_after_game,
)
from kq.storage.duckdb_store import connect
from kq.storage.repositories.paper_trades import (
    insert_paper_trade_with_signal,
    settle_due_nba_paper_trades,
    settled_pnl_total,
)

log = structlog.get_logger(__name__)


DEFAULT_STARTING_BANKROLL_USD = 1_000.0

# Kalshi's NBA game-winner series. Queried as `series_ticker=` (mirrors the
# weather stations' PR #97 fix) — never via status-open page-1 + client-side
# filtering, which sees 0 NBA markets on prod (2026-06-11 audit #5).
NBA_SERIES_TICKER: Final = "KXNBAGAME"


@dataclass(frozen=True, slots=True)
class PaperNbaRunSummary:
    """What :func:`run_once_nba` did. Used for logging + tests."""

    submit_evaluated: int
    """How many open Kalshi NBA markets reached the evaluator (unparsable
    tickers and games blocked by the pre-tipoff guard don't count)."""

    submit_recorded: int
    """How many new paper-trade rows the submit pass wrote (idempotent;
    re-runs with same inputs report 0)."""

    settle_processed: int
    """How many NBA trades the settlement pass moved from unsettled to settled."""

    bankroll_snapshot_usd: float
    """Bankroll at the start of this run (starting + cumulative settled P&L)."""

    submit_skipped_insufficient_data: int = 0
    """Games the data-sufficiency guard refused to signal on: a team
    abbreviation that isn't a known NBA team, or an Elo fallback consulted
    while either team has fewer than ``MIN_SETTLED_GAMES_FOR_RATING``
    settled games in the state (2026-07-01 audit, Tier 1: a fresh DB
    produced confident bogus Elo signals from the home-court prior alone)."""

    skipped_reason: str | None = None
    """When submit was skipped wholesale (missing creds, etc.); settle still runs."""


def run_once_nba(
    *,
    db_path: Path | None = None,
    starting_bankroll_usd: float = DEFAULT_STARTING_BANKROLL_USD,
    min_edge_pct: float = DEFAULT_MIN_EDGE_PCT,
    kelly_fraction: float = DEFAULT_KELLY_FRACTION,
    max_stake_usd: float = DEFAULT_MAX_STAKE_USD,
    settle_only: bool = False,
    now_utc: datetime | None = None,
) -> PaperNbaRunSummary:
    """Run one full NBA paper-trading cycle (submit + settle).

    ``settle_only=True`` skips the submit pass entirely. Useful for cron
    splits where settlement runs daily but submit runs only during game
    windows.

    Never raises on missing credentials or empty markets -- reports skip
    reasons via the summary so a cron run is always exit-0 unless the
    code itself faults.
    """
    settings = get_settings()
    db = db_path or _db_path_from_settings(settings.database_url)
    now = now_utc or datetime.now(tz=UTC)

    con = connect(db)
    try:
        # Per-vertical bankroll: another lane's drawdown must never zero this
        # lane's stake (see settled_pnl_total).
        bankroll = starting_bankroll_usd + settled_pnl_total(con, vertical="nba")
        n_eval = 0
        n_recorded = 0
        n_data_guard = 0
        skipped: str | None = None

        if not settle_only:
            try:
                n_eval, n_recorded, n_data_guard = _submit_pass_nba(
                    con,
                    bankroll_usd=bankroll,
                    min_edge_pct=min_edge_pct,
                    kelly_fraction=kelly_fraction,
                    max_stake_usd=max_stake_usd,
                    now_utc=now,
                )
            except KalshiCredentialsError as exc:
                log.warning("paper_nba.submit.skipped_no_creds", detail=str(exc))
                skipped = "no_kalshi_creds"

        n_settled = settle_due_nba_paper_trades(con, now=now)
    finally:
        con.close()

    summary = PaperNbaRunSummary(
        submit_evaluated=n_eval,
        submit_recorded=n_recorded,
        settle_processed=n_settled,
        bankroll_snapshot_usd=bankroll,
        submit_skipped_insufficient_data=n_data_guard,
        skipped_reason=skipped,
    )
    log.info(
        "paper_nba.run_once.done",
        evaluated=summary.submit_evaluated,
        recorded=summary.submit_recorded,
        settled=summary.settle_processed,
        bankroll=summary.bankroll_snapshot_usd,
        skipped_insufficient_data=summary.submit_skipped_insufficient_data,
        skipped=summary.skipped_reason,
    )
    return summary


def _submit_pass_nba(
    con: object,  # duckdb.DuckDBPyConnection
    *,
    bankroll_usd: float,
    min_edge_pct: float,
    kelly_fraction: float,
    max_stake_usd: float,
    now_utc: datetime,
) -> tuple[int, int, int]:
    """Returns ``(n_evaluated, n_recorded, n_skipped_data_guard)``.

    Kalshi lists TWO markets per game (YES-home and YES-away). We evaluate
    every side but record AT MOST ONE trade per (game_date, home, away) —
    both sides express the same opinion, so trading both doubles Kelly
    exposure and double-counts settles (2026-06-11 audit #6). The side with
    the larger post-fee edge wins; ties break to the lexicographically
    smaller ticker so re-runs are deterministic.

    Data-sufficiency guard (2026-07-01 audit, Tier 1): a game whose ticker
    names a team outside the 30 known NBA abbreviations is never evaluated,
    and a game whose evaluation fell back to Elo while either team has
    fewer than ``MIN_SETTLED_GAMES_FOR_RATING`` settled games produces NO
    signal — a thin Elo state mostly restates the home-court prior, which
    on a fresh DB cleared the edge gate with zero information behind it.
    Pinnacle-anchored signals are unaffected (they don't consult Elo).
    """
    elo = _compute_elo_state(con)
    nba_markets = asyncio.run(_pull_kalshi_nba_markets())
    if not nba_markets:
        log.warning("paper_nba.submit.no_open_markets")
        return 0, 0, 0

    by_game: dict[tuple[date, str, str], list[tuple[Market, NbaMarketRef]]] = {}
    for market in nba_markets:
        ref = parse_nba_market_ticker(market.ticker)
        if ref is None:
            log.warning("paper_nba.submit.ticker_unparsable", ticker=market.ticker)
            continue
        key = (ref.game_date, ref.home_team_abbr, ref.away_team_abbr)
        by_game.setdefault(key, []).append((market, ref))

    n_eval = 0
    n_recorded = 0
    n_data_guard = 0
    for _game_key, sides in sorted(by_game.items()):
        game_ref = sides[0][1]
        unknown = [
            t
            for t in (game_ref.home_team_abbr, game_ref.away_team_abbr)
            if t not in KNOWN_TEAM_ABBRS
        ]
        if unknown:
            n_data_guard += 1
            log.warning(
                "paper_nba.submit.skipped_unknown_team",
                game_date=game_ref.game_date.isoformat(),
                home=game_ref.home_team_abbr,
                away=game_ref.away_team_abbr,
                unknown_teams=unknown,
            )
            continue
        tipoff_skip = _pre_tipoff_skip_reason(con, game_ref, now_utc=now_utc)
        if tipoff_skip is not None:
            log.info(
                "paper_nba.submit.skipped_pre_tipoff_guard",
                game_date=game_ref.game_date.isoformat(),
                home=game_ref.home_team_abbr,
                away=game_ref.away_team_abbr,
                skip_reason=tipoff_skip,
            )
            continue

        n_side_eval, candidates, elo_guard_tripped = _evaluate_game_sides(
            con,
            sides,
            elo=elo,
            bankroll_usd=bankroll_usd,
            min_edge_pct=min_edge_pct,
            kelly_fraction=kelly_fraction,
            max_stake_usd=max_stake_usd,
            now_utc=now_utc,
        )
        n_eval += n_side_eval
        if elo_guard_tripped:
            n_data_guard += 1
            continue
        if not candidates:
            continue
        candidates.sort(key=lambda c: (-_post_fee_edge(c[0]), c[0].ticker))
        intent, decision, ref = candidates[0]
        for other_intent, _d, _r in candidates[1:]:
            log.info(
                "paper_nba.submit.skipped_other_side",
                ticker=other_intent.ticker,
                chosen_ticker=intent.ticker,
                edge_bps=other_intent.edge_bps,
                chosen_edge_bps=intent.edge_bps,
            )
        _, was_new = insert_paper_trade_with_signal(
            con,  # type: ignore[arg-type]
            intent,
            submitted_at=now_utc,
            source_urls=["https://api.the-odds-api.com/v4/", "https://kalshi.com/"],
            reasoning=(
                f"NBA {ref.away_team_abbr}@{ref.home_team_abbr} on {ref.game_date.isoformat()}; "
                f"YES={ref.yes_team_abbr}; model_prob_home={decision.model_prob_home:.3f} "
                f"({decision.source})"
            ),
        )
        if was_new:
            n_recorded += 1
            log.info(
                "paper_nba.submit.recorded",
                ticker=intent.ticker,
                side=intent.side,
                qty=intent.qty,
                limit_price=intent.limit_price,
                edge_bps=intent.edge_bps,
                source=decision.source,
            )
    return n_eval, n_recorded, n_data_guard


def _evaluate_game_sides(
    con: object,
    sides: list[tuple[Market, NbaMarketRef]],
    *,
    elo: NbaEloRatings,
    bankroll_usd: float,
    min_edge_pct: float,
    kelly_fraction: float,
    max_stake_usd: float,
    now_utc: datetime,
) -> tuple[int, list[tuple[PaperTradeIntent, NbaSignalDecision, NbaMarketRef]], bool]:
    """Evaluate both Kalshi sides of one game.

    Returns ``(n_evaluated, candidates, elo_guard_tripped)``.
    ``elo_guard_tripped`` is True when the evaluator fell back to Elo
    (``decision.source == 'elo'``) while either team has fewer than
    ``MIN_SETTLED_GAMES_FOR_RATING`` settled games in ``elo`` — the
    caller must then record NO signal for the game (2026-07-01 audit,
    Tier 1). Keying off the decision's actual source (rather than
    re-deriving "would Pinnacle apply?") also covers the corner where a
    Pinnacle quote exists but is unusable (bad odds / out-of-band
    booksum) and the evaluator silently falls back.
    """
    game_ref = sides[0][1]
    ctx = _build_game_context(con, game_ref)
    pinnacle_home, pinnacle_away = _fetch_latest_pinnacle_quote(con, game_ref)

    n_eval = 0
    candidates: list[tuple[PaperTradeIntent, NbaSignalDecision, NbaMarketRef]] = []
    elo_guard_tripped = False
    for market, ref in sides:
        n_eval += 1
        inputs = NbaSignalInputs(
            home_team_abbr=ref.home_team_abbr,
            away_team_abbr=ref.away_team_abbr,
            elo=elo,
            pinnacle_home_decimal_odds=pinnacle_home,
            pinnacle_away_decimal_odds=pinnacle_away,
            kalshi_quote=NbaQuotePair(
                ticker=market.ticker,
                yes_bid=_as_optional_float(market.yes_bid),
                yes_ask=_as_optional_float(market.yes_ask),
                yes_bid_size=_as_optional_float(market.yes_bid_size),
                yes_ask_size=_as_optional_float(market.yes_ask_size),
            ),
            bankroll_usd=bankroll_usd,
            as_of=now_utc,
            elo_context=ctx,
            yes_is_home=ref.yes_is_home,
        )
        decision = evaluate_nba_signal(
            inputs,
            min_edge_pct=min_edge_pct,
            kelly_fraction=kelly_fraction,
            max_stake_usd=max_stake_usd,
        )
        if decision.source == "elo":
            thin = {
                team: elo.games_recorded(team)
                for team in (ref.home_team_abbr, ref.away_team_abbr)
                if not elo.has_min_history(team)
            }
            if thin:
                elo_guard_tripped = True
                log.warning(
                    "paper_nba.submit.skipped_insufficient_elo_history",
                    ticker=market.ticker,
                    settled_games=thin,
                    min_settled_games=MIN_SETTLED_GAMES_FOR_RATING,
                )
                continue
        if decision.intent is None:
            log.info(
                "paper_nba.submit.skipped_no_edge",
                ticker=market.ticker,
                source=decision.source,
                model_prob_home=decision.model_prob_home,
                skip_reason=decision.skip_reason,
            )
            continue
        candidates.append((decision.intent, decision, ref))
    return n_eval, candidates, elo_guard_tripped


def _post_fee_edge(intent: PaperTradeIntent) -> float:
    """Post-fee edge in probability points — the same quantity
    ``evaluate_market`` gates on, recomputed for cross-side comparison."""
    return intent.edge_bps / 10_000.0 - fee_per_contract(intent.limit_price, side="taker")


def _pre_tipoff_skip_reason(
    con: object,
    ref: NbaMarketRef,
    *,
    now_utc: datetime,
) -> str | None:
    """Return a skip reason when the game already started (or finished);
    ``None`` when it's still safe to submit.

    Tipoff time lives in ``nba_odds.commence_time`` (joined via the
    crosswalk) — ``nba_game`` stores only the US/Eastern game DATE, no start
    time. When no odds row exists yet, fall back to a conservative
    date-level guard: refuse any game whose US/Eastern date has passed.
    Same-day games without a known tipoff are allowed through; the
    finished-game check still blocks anything whose result already landed.
    """
    finished = con.execute(  # type: ignore[attr-defined]
        """
        SELECT 1
        FROM nba_game
        WHERE game_date = ?
          AND home_team_abbr = ?
          AND away_team_abbr = ?
          AND home_won IS NOT NULL
        LIMIT 1
        """,
        [ref.game_date, ref.home_team_abbr, ref.away_team_abbr],
    ).fetchone()
    if finished is not None:
        return "game_finished"

    row = con.execute(  # type: ignore[attr-defined]
        """
        SELECT MAX(o.commence_time)
        FROM nba_game_crosswalk c
        JOIN nba_odds o
          ON o.odds_api_game_id = c.odds_api_game_id
        WHERE c.game_date = ?
          AND c.home_team_abbr = ?
          AND c.away_team_abbr = ?
        """,
        [ref.game_date, ref.home_team_abbr, ref.away_team_abbr],
    ).fetchone()
    commence = row[0] if row is not None else None
    if isinstance(commence, datetime):
        # Stored naive UTC (repo convention); reattach UTC to compare.
        commence_utc = commence if commence.tzinfo is not None else commence.replace(tzinfo=UTC)
        return "tipoff_passed" if now_utc >= commence_utc else None

    if ref.game_date < odds_api_to_us_eastern_date(now_utc):
        return "game_date_past"
    return None


def _build_game_context(con: object, ref: NbaMarketRef) -> GameContext:
    """Derive per-game Elo adjustments from the stored schedule.

    Back-to-back: the team appears in a COMPLETED ``nba_game`` row dated the
    previous US/Eastern day (completed, so a postponed listing doesn't count
    as a played game). Travel miles stay at the neutral 0.0 default —
    arena-to-arena distances aren't ingested in v1 (and
    ``TRAVEL_PENALTY_PER_MILE`` is pinned to 0 anyway). Altitude needs no
    context: ``predict_win_prob`` keys the bonus off the home team abbr.
    """
    prev_day = ref.game_date - timedelta(days=1)

    def _played_prev_day(team_abbr: str) -> bool:
        row = con.execute(  # type: ignore[attr-defined]
            """
            SELECT 1
            FROM nba_game
            WHERE game_date = ?
              AND (home_team_abbr = ? OR away_team_abbr = ?)
              AND home_won IS NOT NULL
            LIMIT 1
            """,
            [prev_day, team_abbr, team_abbr],
        ).fetchone()
        return row is not None

    return GameContext(
        home_back_to_back=_played_prev_day(ref.home_team_abbr),
        away_back_to_back=_played_prev_day(ref.away_team_abbr),
    )


def _compute_elo_state(con: object) -> NbaEloRatings:
    """Fold every completed game in ``nba_game`` chronologically into a fresh
    Elo state. Linear in the number of games (~thousands), so cheap on CPU.

    Applies the 538-style regression to the mean at every season boundary —
    without it a multi-season backfill carries June's ratings straight into
    October (the 2026-06-11 audit found ``regress_to_baseline`` was dead code).

    Only regular-season and playoff games are replayed. ``season_type`` is
    stored on every row (the schedule client derives it from the game id:
    "Regular Season" / "Playoffs" / "Preseason" / "All Star" / "Other") but
    was never filtered, so preseason and exhibition results polluted the
    ratings (2026-07-01 audit, Tier 2). Play-in games currently land as
    "Other" and are excluded until the schema tracks them as their own type.

    Rows whose team abbreviations aren't known NBA teams (payload drift,
    partial line scores yielding "") are skipped, not rated.
    """
    elo = NbaEloRatings()
    rows = con.execute(  # type: ignore[attr-defined]
        """
        SELECT game_date, home_team_abbr, away_team_abbr, home_score, away_score
        FROM nba_game
        WHERE home_won IS NOT NULL
          AND home_score IS NOT NULL
          AND away_score IS NOT NULL
          AND season_type IN (?, ?)
        ORDER BY game_date ASC, game_id ASC
        """,
        [SEASON_TYPE_REGULAR, SEASON_TYPE_PLAYOFFS],
    ).fetchall()
    prev_season: int | None = None
    n_unknown_team_rows = 0
    for game_date, home, away, home_score, away_score in rows:
        home_abbr = str(home)
        away_abbr = str(away)
        if home_abbr not in KNOWN_TEAM_ABBRS or away_abbr not in KNOWN_TEAM_ABBRS:
            n_unknown_team_rows += 1
            continue
        season = season_start_year(game_date)
        if prev_season is not None and season != prev_season:
            elo.regress_to_baseline()
        prev_season = season
        update_after_game(
            elo,
            home_team_abbr=home_abbr,
            away_team_abbr=away_abbr,
            home_score=int(home_score),
            away_score=int(away_score),
            ctx=None,
        )
    if n_unknown_team_rows:
        log.warning(
            "paper_nba.elo_state.unknown_team_rows_skipped",
            n_rows=n_unknown_team_rows,
        )
    log.info(
        "paper_nba.elo_state.computed",
        n_games=len(rows) - n_unknown_team_rows,
        n_teams=len(elo.ratings),
    )
    return elo


def _fetch_latest_pinnacle_quote(
    con: object,
    ref: NbaMarketRef,
) -> tuple[float | None, float | None]:
    """Return ``(home_decimal_odds, away_decimal_odds)`` from the most recent
    Pinnacle h2h snapshot for the game referenced by ``ref``.

    Returns ``(None, None)`` if:
    - no crosswalk row exists for this matchup (build-nba-crosswalk hasn't
      caught up), or
    - no Pinnacle quote exists in ``nba_odds`` yet.

    The evaluator handles both as a fallback to Elo, so this is a
    feature-not-a-bug.
    """
    row = con.execute(  # type: ignore[attr-defined]
        """
        SELECT no.home_decimal_odds, no.away_decimal_odds
        FROM nba_game_crosswalk c
        JOIN nba_odds no
          ON no.odds_api_game_id = c.odds_api_game_id
        WHERE c.game_date = ?
          AND c.home_team_abbr = ?
          AND c.away_team_abbr = ?
          AND no.bookmaker_key = 'pinnacle'
          AND no.market_key = 'h2h'
        ORDER BY no.fetched_at DESC
        LIMIT 1
        """,
        [ref.game_date, ref.home_team_abbr, ref.away_team_abbr],
    ).fetchone()
    if row is None:
        return None, None
    home = float(row[0]) if row[0] is not None else None
    away = float(row[1]) if row[1] is not None else None
    return home, away


async def _pull_kalshi_nba_markets() -> list[Market]:
    """Fetch every open ``KXNBAGAME`` market via its series ticker.

    ``series_ticker=`` is load-bearing on prod: the unfiltered ``/markets``
    listing pages through thousands of markets across all of Kalshi and its
    first page contains zero NBA games (2026-06-11 audit #5 — the same bug
    PR #97 fixed for the weather series). Cursor pagination in the client
    covers slates beyond one page. The prefix filter is defense-in-depth
    against the series ever carrying non-game tickers.
    """
    settings = get_settings()
    async with KalshiClient.from_settings(settings) as client:
        series_markets = await client.list_markets(series_ticker=NBA_SERIES_TICKER, status="open")
    nba = [m for m in series_markets if m.ticker.startswith(f"{NBA_SERIES_TICKER}-")]
    log.info(
        "paper_nba.kalshi.fetch_done",
        n_series_markets=len(series_markets),
        n_nba=len(nba),
    )
    return nba


def _as_optional_float(value: object) -> float | None:
    """Tolerate Decimal / int / float / None from upstream Kalshi types."""
    if value is None:
        return None
    return float(value)  # type: ignore[arg-type]


def main(*, db_path: Path | None = None, settle_only: bool = False) -> int:
    """``python -m kq paper-nba`` entrypoint.

    Returns the count of NBA paper-trade rows recorded this pass (0+).
    Settlement runs unconditionally; check the structured logs for the
    settle count separately.
    """
    summary = run_once_nba(db_path=db_path, settle_only=settle_only)
    print(
        f"paper_nba run_once: evaluated={summary.submit_evaluated}, "
        f"recorded={summary.submit_recorded}, settled={summary.settle_processed}, "
        f"bankroll=${summary.bankroll_snapshot_usd:.2f}"
        + (
            f", data_guard_skips={summary.submit_skipped_insufficient_data}"
            if summary.submit_skipped_insufficient_data
            else ""
        )
        + (f", skipped={summary.skipped_reason}" if summary.skipped_reason else "")
    )
    return summary.submit_recorded


__all__ = [
    "DEFAULT_STARTING_BANKROLL_USD",
    "NBA_SERIES_TICKER",
    "PaperNbaRunSummary",
    "main",
    "run_once_nba",
]
