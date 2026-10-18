"""NFL paper-trading flow (submit + settle).

Mirrors :mod:`kq.flows.paper_nba_trade` — every discipline that lane earned
through the 2026-06-11/07-01 audits is inherited wholesale — minus the Elo
machinery: NFL v1 is pure Pinnacle-anchored (no fallback model; the design
doc's "No Elo for v1" — Pinnacle quotes NFL lines months ahead, so the
anchor never goes missing the way NBA's does).

Submit pass (per game where Kalshi has an open market and we have data):

1. Pull every open ``KXNFLGAME`` market via its SERIES ticker (cursor-paged
   by the client — an unfiltered first page of ``/markets`` on prod never
   contains the series you want; audit #5 class).
2. Group per-side tickers by (game_date, home, away) — Kalshi lists a
   YES-home AND a YES-away market for every game (66 live markets = 33
   events verified 2026-07-02). Skip games already kicked off
   (pre-kickoff guard below), then evaluate every side against the latest
   Pinnacle h2h quote (via the crosswalk) with
   :func:`kq.execution.paper_nfl.evaluate_nfl_signal`.
3. Record AT MOST ONE side per game — the larger post-fee edge wins, ties
   break to the lexicographically smaller ticker (audit #6: both sides
   express one opinion; trading both doubles Kelly exposure).
   Idempotent: re-runs with unchanged inputs don't double-insert.
4. Games with no usable Pinnacle anchor produce NO signal and are counted
   (``submit_skipped_no_anchor``) — a no-model lane never trades blind.

Settle pass: :func:`settle_due_nfl_paper_trades` walks every unsettled
NFL-ticker trade against ``nfl_game`` — YES/NO on a winner, ``TIE`` at
$0.50/side on a tied game (real in the NFL), ``VOID`` past the postponement
window.

Pre-kickoff guard: kickoff time comes from ``nfl_game.commence_time``
(the /scores ingest carries it for upcoming games), falling back to
``nfl_odds.commence_time`` via the crosswalk, then to a conservative
date-level guard. Games whose completed result already landed are refused
outright.

**Entry-window timing (W2) is an operator cron choice, not code.** The
strategy panel's recommendation (STRATEGY-PANEL-2026-06-11, Seat 2 P2-A):
paper-trade window W2 = T-60min after official inactives (inactives land
at T-90). Because signals are idempotent per market, the FIRST submit tick
that clears the edge gate books the trade — so schedule the first tick of
each game window ~60 min before its kickoff slot rather than running
submit all day. Recommended crontab (times in ET; shift for the host TZ):

    # Sunday early slate (1:00pm ET kickoffs) — first tick at T-60
    0 12 * * 0        kq paper-nfl
    # Sunday late-afternoon slate (4:05/4:25pm ET)
    15 15 * * 0       kq paper-nfl
    # Sunday/Monday/Thursday night games (8:15-8:20pm ET)
    15 19 * * 0,1,4   kq paper-nfl
    # Daily settlement sweep (runs the settle pass only; cheap + safe)
    30 8 * * *        kq paper-nfl --settle-only

Skip conditions (structured warnings, never errors — cron stays exit-0):

* Kalshi credentials missing -> ``skipped_reason='no_kalshi_creds'``;
  settlement still runs.
* No open NFL markets (off-season) -> empty submit, settlement runs.
* No crosswalk row for a matchup -> skip that game (build-nfl-crosswalk
  hasn't caught up).
* No usable Pinnacle quote -> NO signal (counted, loud).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Final

import structlog

from kq.clients.kalshi import KalshiClient, KalshiCredentialsError, Market
from kq.clients.kalshi._ticker_parser_nfl import NflMarketRef, parse_nfl_market_ticker
from kq.config import get_settings
from kq.execution.fees import fee_per_contract
from kq.execution.paper import (
    DEFAULT_KELLY_FRACTION,
    DEFAULT_MAX_STAKE_USD,
    DEFAULT_MIN_EDGE_PCT,
    PaperTradeIntent,
)
from kq.execution.paper_nfl import (
    NflQuotePair,
    NflSignalDecision,
    NflSignalInputs,
    evaluate_nfl_signal,
)
from kq.flows.ingest_weather import _db_path_from_settings
from kq.models.nba_crosswalk import odds_api_to_us_eastern_date
from kq.storage.duckdb_store import connect
from kq.storage.repositories.paper_trades import (
    insert_paper_trade_with_signal,
    settle_due_nfl_paper_trades,
    vertical_free_capital_usd,
)

log = structlog.get_logger(__name__)

DEFAULT_STARTING_BANKROLL_USD = 1_000.0

# Kalshi's NFL game-winner series. Queried as `series_ticker=` with cursor
# pagination — never via status-open page-1 + client-side filtering (the
# 2026-06-11 audit #5 class). Verified live 2026-07-02.
NFL_SERIES_TICKER: Final = "KXNFLGAME"


@dataclass(frozen=True, slots=True)
class PaperNflRunSummary:
    """What :func:`run_once_nfl` did. Used for logging + tests."""

    submit_evaluated: int
    """How many open Kalshi NFL markets reached the evaluator (unparsable
    tickers and games blocked by the pre-kickoff guard don't count)."""

    submit_recorded: int
    """How many new paper-trade rows the submit pass wrote (idempotent;
    re-runs with same inputs report 0)."""

    settle_processed: int
    """How many NFL trades the settlement pass moved from unsettled to
    settled (YES/NO/TIE/VOID)."""

    bankroll_snapshot_usd: float
    """FREE capital at the start of this run: starting + settled P&L -
    open-position cost. Sizing input, not equity — see
    vertical_free_capital_usd."""

    submit_skipped_no_anchor: int = 0
    """Games skipped because no usable Pinnacle anchor existed (no
    crosswalk row, no quote, or an unusable quote). NFL v1 has no fallback
    model, so these games produce NO signal — counted, never silent."""

    skipped_reason: str | None = None
    """When submit was skipped wholesale (missing creds); settle still runs."""


def run_once_nfl(
    *,
    db_path: Path | None = None,
    starting_bankroll_usd: float = DEFAULT_STARTING_BANKROLL_USD,
    min_edge_pct: float = DEFAULT_MIN_EDGE_PCT,
    kelly_fraction: float = DEFAULT_KELLY_FRACTION,
    max_stake_usd: float = DEFAULT_MAX_STAKE_USD,
    settle_only: bool = False,
    now_utc: datetime | None = None,
) -> PaperNflRunSummary:
    """Run one full NFL paper-trading cycle (submit + settle).

    ``settle_only=True`` skips the submit pass entirely — the daily
    settlement sweep uses this. Never raises on missing credentials or
    empty markets; skip reasons land in the summary so cron is always
    exit-0 unless the code itself faults.
    """
    settings = get_settings()
    db = db_path or _db_path_from_settings(settings.database_url)
    now = now_utc or datetime.now(tz=UTC)

    con = connect(db)
    try:
        # FREE capital, not equity: starting + realized P&L - open-position
        # cost. Deducting open exposure is the aggregate cap (audit
        # 2026-08-07); vertical-scoped per #128 so another lane's drawdown
        # never zeroes this lane's stake.
        bankroll = vertical_free_capital_usd(
            con, vertical="nfl", starting_usd=starting_bankroll_usd
        )
        n_eval = 0
        n_recorded = 0
        n_no_anchor = 0
        skipped: str | None = None

        if not settle_only:
            try:
                n_eval, n_recorded, n_no_anchor = _submit_pass_nfl(
                    con,
                    bankroll_usd=bankroll,
                    min_edge_pct=min_edge_pct,
                    kelly_fraction=kelly_fraction,
                    max_stake_usd=max_stake_usd,
                    now_utc=now,
                )
            except KalshiCredentialsError as exc:
                log.warning("paper_nfl.submit.skipped_no_creds", detail=str(exc))
                skipped = "no_kalshi_creds"

        n_settled = settle_due_nfl_paper_trades(con, now=now)
    finally:
        con.close()

    summary = PaperNflRunSummary(
        submit_evaluated=n_eval,
        submit_recorded=n_recorded,
        settle_processed=n_settled,
        bankroll_snapshot_usd=bankroll,
        submit_skipped_no_anchor=n_no_anchor,
        skipped_reason=skipped,
    )
    log.info(
        "paper_nfl.run_once.done",
        evaluated=summary.submit_evaluated,
        recorded=summary.submit_recorded,
        settled=summary.settle_processed,
        bankroll=summary.bankroll_snapshot_usd,
        skipped_no_anchor=summary.submit_skipped_no_anchor,
        skipped=summary.skipped_reason,
    )
    return summary


def _submit_pass_nfl(
    con: object,  # duckdb.DuckDBPyConnection
    *,
    bankroll_usd: float,
    min_edge_pct: float,
    kelly_fraction: float,
    max_stake_usd: float,
    now_utc: datetime,
) -> tuple[int, int, int]:
    """Returns ``(n_evaluated, n_recorded, n_skipped_no_anchor)``.

    Kalshi lists TWO markets per game (YES-home and YES-away). We evaluate
    every side but record AT MOST ONE trade per (game_date, home, away) —
    the side with the larger post-fee edge; ties break to the
    lexicographically smaller ticker so re-runs are deterministic (the
    NBA lane's audit-#6 discipline, inherited unchanged).
    """
    nfl_markets = asyncio.run(_pull_kalshi_nfl_markets())
    if not nfl_markets:
        log.warning("paper_nfl.submit.no_open_markets")
        return 0, 0, 0

    by_game: dict[tuple[date, str, str], list[tuple[Market, NflMarketRef]]] = {}
    for market in nfl_markets:
        ref = parse_nfl_market_ticker(market.ticker)
        if ref is None:
            log.warning("paper_nfl.submit.ticker_unparsable", ticker=market.ticker)
            continue
        key = (ref.game_date, ref.home_team_abbr, ref.away_team_abbr)
        by_game.setdefault(key, []).append((market, ref))

    n_eval = 0
    n_recorded = 0
    n_no_anchor = 0
    # Running free capital WITHIN the pass — see the weather flow's twin
    # comment. A full Sunday slate must not size every game against the
    # same untouched run-start figure.
    available = bankroll_usd
    for _game_key, sides in sorted(by_game.items()):
        game_ref = sides[0][1]
        if available <= 0:
            log.info(
                "paper_nfl.submit.capital_exhausted",
                game_date=game_ref.game_date.isoformat(),
                available_usd=round(available, 2),
            )
            continue
        kickoff_skip = _pre_kickoff_skip_reason(con, game_ref, now_utc=now_utc)
        if kickoff_skip is not None:
            log.info(
                "paper_nfl.submit.skipped_pre_kickoff_guard",
                game_date=game_ref.game_date.isoformat(),
                home=game_ref.home_team_abbr,
                away=game_ref.away_team_abbr,
                skip_reason=kickoff_skip,
            )
            continue

        pinnacle_home, pinnacle_away = _fetch_latest_pinnacle_quote(con, game_ref)
        if pinnacle_home is None or pinnacle_away is None:
            n_no_anchor += 1
            log.warning(
                "paper_nfl.submit.skipped_no_anchor",
                game_date=game_ref.game_date.isoformat(),
                home=game_ref.home_team_abbr,
                away=game_ref.away_team_abbr,
                detail="no Pinnacle quote via crosswalk; NFL v1 has no fallback model",
            )
            continue

        n_side_eval, candidates, anchor_unusable = _evaluate_game_sides_nfl(
            sides,
            pinnacle_home=pinnacle_home,
            pinnacle_away=pinnacle_away,
            bankroll_usd=available,
            min_edge_pct=min_edge_pct,
            kelly_fraction=kelly_fraction,
            max_stake_usd=max_stake_usd,
            now_utc=now_utc,
        )
        n_eval += n_side_eval
        if anchor_unusable:
            n_no_anchor += 1
            continue
        if not candidates:
            continue
        candidates.sort(key=lambda c: (-_post_fee_edge(c[0]), c[0].ticker))
        intent, decision, ref = candidates[0]
        for other_intent, _d, _r in candidates[1:]:
            log.info(
                "paper_nfl.submit.skipped_other_side",
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
                f"NFL {ref.away_team_abbr}@{ref.home_team_abbr} on {ref.game_date.isoformat()}; "
                f"YES={ref.yes_team_abbr}; pinnacle_fair_home={decision.model_prob_home:.3f}"
            ),
        )
        if was_new:
            n_recorded += 1
            available -= intent.limit_price * intent.qty + intent.fee_usd
            log.info(
                "paper_nfl.submit.recorded",
                ticker=intent.ticker,
                side=intent.side,
                qty=intent.qty,
                limit_price=intent.limit_price,
                edge_bps=intent.edge_bps,
                available_usd=round(available, 2),
            )
    return n_eval, n_recorded, n_no_anchor


def _evaluate_game_sides_nfl(
    sides: list[tuple[Market, NflMarketRef]],
    *,
    pinnacle_home: float,
    pinnacle_away: float,
    bankroll_usd: float,
    min_edge_pct: float,
    kelly_fraction: float,
    max_stake_usd: float,
    now_utc: datetime,
) -> tuple[int, list[tuple[PaperTradeIntent, NflSignalDecision, NflMarketRef]], bool]:
    """Evaluate both Kalshi sides of one game against one Pinnacle anchor.

    Returns ``(n_evaluated, candidates, anchor_unusable)``.
    ``anchor_unusable`` is True when the quote existed but the devig
    refused it (bad odds / out-of-band booksum) — the caller then counts
    the game as no-anchor and records NOTHING (no fallback model exists).
    """
    n_eval = 0
    candidates: list[tuple[PaperTradeIntent, NflSignalDecision, NflMarketRef]] = []
    anchor_unusable = False
    for market, ref in sides:
        n_eval += 1
        decision = evaluate_nfl_signal(
            NflSignalInputs(
                home_team_abbr=ref.home_team_abbr,
                away_team_abbr=ref.away_team_abbr,
                pinnacle_home_decimal_odds=pinnacle_home,
                pinnacle_away_decimal_odds=pinnacle_away,
                kalshi_quote=NflQuotePair(
                    ticker=market.ticker,
                    yes_bid=_as_optional_float(market.yes_bid),
                    yes_ask=_as_optional_float(market.yes_ask),
                    yes_bid_size=_as_optional_float(market.yes_bid_size),
                    yes_ask_size=_as_optional_float(market.yes_ask_size),
                ),
                bankroll_usd=bankroll_usd,
                as_of=now_utc,
                yes_is_home=ref.yes_is_home,
            ),
            min_edge_pct=min_edge_pct,
            kelly_fraction=kelly_fraction,
            max_stake_usd=max_stake_usd,
        )
        if decision.source == "none":
            anchor_unusable = True
            log.warning(
                "paper_nfl.submit.skipped_unusable_anchor",
                ticker=market.ticker,
                skip_reason=decision.skip_reason,
            )
            continue
        if decision.intent is None:
            log.info(
                "paper_nfl.submit.skipped_no_edge",
                ticker=market.ticker,
                model_prob_home=decision.model_prob_home,
                skip_reason=decision.skip_reason,
            )
            continue
        candidates.append((decision.intent, decision, ref))
    return n_eval, candidates, anchor_unusable


def _post_fee_edge(intent: PaperTradeIntent) -> float:
    """Post-fee edge in probability points — the same quantity
    ``evaluate_market`` gates on, recomputed for cross-side comparison."""
    return intent.edge_bps / 10_000.0 - fee_per_contract(intent.limit_price, side="taker")


def _pre_kickoff_skip_reason(
    con: object,
    ref: NflMarketRef,
    *,
    now_utc: datetime,
) -> str | None:
    """Return a skip reason when the game already kicked off (or finished);
    ``None`` when it's still safe to submit.

    Kickoff time preference order: ``nfl_game.commence_time`` (the /scores
    ingest carries it for upcoming games), then ``nfl_odds.commence_time``
    via the crosswalk, then a conservative date-level guard (refuse any
    game whose US/Eastern date has passed; same-day games without a known
    kickoff are allowed through — the finished-game check still blocks
    anything whose completed result already landed).
    """
    finished = con.execute(  # type: ignore[attr-defined]
        """
        SELECT 1
        FROM nfl_game
        WHERE game_date = ?
          AND home_team_abbr = ?
          AND away_team_abbr = ?
          AND completed
        LIMIT 1
        """,
        [ref.game_date, ref.home_team_abbr, ref.away_team_abbr],
    ).fetchone()
    if finished is not None:
        return "game_finished"

    row = con.execute(  # type: ignore[attr-defined]
        """
        SELECT MAX(commence_time)
        FROM nfl_game
        WHERE game_date = ?
          AND home_team_abbr = ?
          AND away_team_abbr = ?
        """,
        [ref.game_date, ref.home_team_abbr, ref.away_team_abbr],
    ).fetchone()
    commence = row[0] if row is not None else None
    if not isinstance(commence, datetime):
        row = con.execute(  # type: ignore[attr-defined]
            """
            SELECT MAX(o.commence_time)
            FROM nfl_game_crosswalk c
            JOIN nfl_odds o
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
        return "kickoff_passed" if now_utc >= commence_utc else None

    if ref.game_date < odds_api_to_us_eastern_date(now_utc):
        return "game_date_past"
    return None


def _fetch_latest_pinnacle_quote(
    con: object,
    ref: NflMarketRef,
) -> tuple[float | None, float | None]:
    """Return ``(home_decimal_odds, away_decimal_odds)`` from the most
    recent Pinnacle h2h snapshot for the game referenced by ``ref``.

    ``(None, None)`` when no crosswalk row exists (build-nfl-crosswalk
    hasn't caught up) or no Pinnacle quote landed yet. Unlike NBA this is
    NOT a soft fallback state — the caller refuses to signal.
    """
    row = con.execute(  # type: ignore[attr-defined]
        """
        SELECT o.home_decimal_odds, o.away_decimal_odds
        FROM nfl_game_crosswalk c
        JOIN nfl_odds o
          ON o.odds_api_game_id = c.odds_api_game_id
        WHERE c.game_date = ?
          AND c.home_team_abbr = ?
          AND c.away_team_abbr = ?
          AND o.bookmaker_key = 'pinnacle'
          AND o.market_key = 'h2h'
        ORDER BY o.fetched_at DESC
        LIMIT 1
        """,
        [ref.game_date, ref.home_team_abbr, ref.away_team_abbr],
    ).fetchone()
    if row is None:
        return None, None
    home = float(row[0]) if row[0] is not None else None
    away = float(row[1]) if row[1] is not None else None
    return home, away


async def _pull_kalshi_nfl_markets() -> list[Market]:
    """Fetch every open ``KXNFLGAME`` market via its series ticker.

    ``series_ticker=`` is load-bearing on prod (audit #5 class); the
    client cursor-paginates. The prefix filter is defense-in-depth
    against the series ever carrying non-game tickers.
    """
    settings = get_settings()
    async with KalshiClient.from_settings(settings) as client:
        series_markets = await client.list_markets(series_ticker=NFL_SERIES_TICKER, status="open")
    nfl = [m for m in series_markets if m.ticker.startswith(f"{NFL_SERIES_TICKER}-")]
    log.info(
        "paper_nfl.kalshi.fetch_done",
        n_series_markets=len(series_markets),
        n_nfl=len(nfl),
    )
    return nfl


def _as_optional_float(value: object) -> float | None:
    """Tolerate Decimal / int / float / None from upstream Kalshi types."""
    if value is None:
        return None
    return float(value)  # type: ignore[arg-type]


def main(*, db_path: Path | None = None, settle_only: bool = False) -> int:
    """``python -m kq paper-nfl`` entrypoint.

    Returns the count of NFL paper-trade rows recorded this pass (0+).
    Settlement runs unconditionally; check the structured logs for the
    settle count separately.
    """
    summary = run_once_nfl(db_path=db_path, settle_only=settle_only)
    print(
        f"paper_nfl run_once: evaluated={summary.submit_evaluated}, "
        f"recorded={summary.submit_recorded}, settled={summary.settle_processed}, "
        f"bankroll=${summary.bankroll_snapshot_usd:.2f}"
        + (
            f", no_anchor_skips={summary.submit_skipped_no_anchor}"
            if summary.submit_skipped_no_anchor
            else ""
        )
        + (f", skipped={summary.skipped_reason}" if summary.skipped_reason else "")
    )
    return summary.submit_recorded


__all__ = [
    "DEFAULT_STARTING_BANKROLL_USD",
    "NFL_SERIES_TICKER",
    "PaperNflRunSummary",
    "main",
    "run_once_nfl",
]
