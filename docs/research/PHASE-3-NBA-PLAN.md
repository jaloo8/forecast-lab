# Phase 3 — NBA Implementation Plan

> **Status:** scoping doc only. Phase 3 starts after Phase 2 ships (14 days continuous paper trading + ≥ 50 settled paper trades on the Windows box; see `CLAUDE.md` §5 + `docs/SCHEDULED-RUNS.md`). Do **not** start Phase 3 work until that gate clears — it's a discipline guardrail, not a technical one.
>
> **Status of underlying research:** the broader feasibility analysis is already in [`PASS-1-FEASIBILITY.md`](PASS-1-FEASIBILITY.md) §1c; this doc is the scoping plan to translate that research into an actual ship list.

## Why this doc exists now

The forecast-lab repo currently houses Phase 2 (weather) end-to-end. Phase 3 (NBA) is on the medium-term roadmap. When the gate clears, the order of operations and dependency story should be a 2-page reference, not a research dive — that's what this doc captures.

## Architecture (matching Phase 2's pattern)

```
[ nba_api swar/nba_api ]      ─┐
[ nbainjuries (mxufc29) ]      │
[ balldontlie /odds        ]   ├─► ingest ─► DuckDB ─► features ─► models ─► signals ─► execution
[ The Odds API (Pinnacle) ]    │            (existing                 (NBA Elo +
[ Kalshi NBA markets       ]   ┘             schema +                  Pinnacle
                                              new tables)               vig-strip)
```

Storage: extend the existing DuckDB file with new NBA tables; **no new database**. Schema additions:

- `nba_game` — schedule + final results
- `nba_team_state` — daily Elo ratings, rest/travel/altitude features per team
- `nba_injury_snapshot` — periodic injury report snapshots
- `pinnacle_odds_snap` — pre-game + in-game odds snapshots (Pinnacle is the fair-value anchor)
- `kalshi_nba_market` — symmetric with `kalshi_market` (mirrors weather schema)
- `kalshi_nba_book_snap` — symmetric with `kalshi_book_snap`
- `signal_nba` — model-prob vs. market for each NBA contract (mirrors `signal`)
- `paper_trade_nba` — symmetric with `paper_trade`
- `settlement_nba` — symmetric with `settlement`

A clean schema fork is preferable to overloading the weather tables — different feature sets, different settle logic.

## Ship sequence

5 PRs, each ≤ 400 lines per CLAUDE.md §8. Open follow-up issues rather than expanding scope.

### PR 1 — `nba_api` schedule + results client (~250 lines)

- `src/kq/clients/nba_schedule.py` — wraps `nba_api.stats.endpoints.scoreboardv2` and `leaguegamefinder` for historical results.
- New deps: `nba_api>=1.10` (already in `pyproject.toml` mypy ignores; need the actual install).
- `src/kq/storage/repositories/nba.py` — `insert_nba_games`, `fetch_nba_games`.
- Schema migration: `nba_game` table with PK `(game_id)`, fields `(date, home_team, away_team, home_score, away_score, home_won, season, game_type)`.
- `src/kq/flows/ingest_nba_schedule.py` + CLI `kq ingest-nba-schedule`.
- Backfill via `kq backfill-nba-schedule --start 2018-10 --end 2024-06` for 6+ seasons of history (Elo training set).

**Exit:** ≥ 6 seasons of historical games loaded. Ingest cron schedules a daily refresh during the season.

### PR 2 — Injury polling (~150 lines)

- `src/kq/clients/nba_injuries.py` — wraps `nbainjuries`. **Polls cadence per CLAUDE.md §5: hourly on game days, 15-min in final 3 hours pre-tipoff.**
- `nba_injury_snapshot` PK `(snapshot_at, team, player)`.
- `src/kq/flows/ingest_nba_injuries.py` + CLI.

**Exit:** flow runs cleanly across multiple game days; no rate-limit issues.

### PR 3 — Pinnacle odds + balldontlie fallback (~250 lines)

- `src/kq/clients/odds_api.py` — wraps The Odds API (paid GOAT tier, $30/mo per [`PASS-1-FEASIBILITY.md`](PASS-1-FEASIBILITY.md) §11).
- `src/kq/clients/balldontlie_odds.py` — free fallback for Pinnacle moneylines when paid tier unavailable.
- `pinnacle_odds_snap` PK `(captured_at, game_id, market_type)`. Stores both raw American odds and computed vig-stripped fair probability.
- Vig-strip math in `src/kq/models/nba_pinnacle_fair.py`: power-method or Shin's method over the (home, away) pair. Pinnacle is THE fair-value anchor for NBA per Pass 1 §1c — its mid-vig probability is the model.

**Exit:** snapshots accumulate cleanly across a week of games; vig-strip output sanity-checks against Pinnacle's own implied prob.

### PR 4 — Elo model + features (~300 lines)

- `src/kq/models/nba_elo.py` — FiveThirtyEight-style Elo (CARM-Elo derivative, no special-sauce):
  - K-factor: 20.0 (regular season) / 12.0 (playoffs).
  - Margin multiplier: `MoV * 2.2 / (rating_diff * 0.001 + 2.2)` per 538.
  - Home advantage: 100 Elo (≈ 65% home win rate baseline).
  - Rest adjustment: B2B = -46, 1 day rest = -8, 2 days = -3, 3+ days = 0 (538-derived per [PASS-1-FEASIBILITY.md](PASS-1-FEASIBILITY.md) §1c, citing Probwin CLV guide).
  - Altitude bonus for DEN, UTA: +20 Elo at home.
- Pre-fit on backfilled schedule (~6 seasons, regular + playoffs).
- Per-fold backtest harness extension — extends `src/kq/backtest/engine.py` to support `strategy="nba_elo_v1"` with the **same rolling-origin discipline** as weather_v1.
- Output `models/backtest_nba_manifest.json` with same schema as the weather manifests.

**Exit:** Elo backtest hit rate within 1.5% of FiveThirtyEight's published historical accuracy (~67-68% straight-up regular season, ~70% playoff per their methodology page).

### PR 5 — NBA paper executor + dashboard surface (~250 lines)

- Extend `src/kq/execution/paper.py` to dispatch by market category. NBA brackets are simpler than weather (binary YES/NO moneyline, no temperature thresholds) — most of the work is feature plumbing.
- Add per-game pre-tipoff submit pass + post-game settle pass to the cron schedule (paper-trading surface, NOT live).
- Streamlit dashboard (Phase 4 work) gets an NBA tab.

**Exit:** paper-traded NBA signals show ≥ 0% CLV vs. Pinnacle on N ≥ 100 settled games per [CLAUDE.md §5](../../CLAUDE.md) Phase 3 exit criteria. Bar is "+1% average CLV" for Phase 5 readiness.

## Dependencies

| Package | Version | Status | Notes |
|---|---|---|---|
| `nba_api` | ≥ 1.10 | Listed in `pyproject.toml` mypy ignores | Install actual dep on PR 1. |
| `nbainjuries` | latest | Not installed | Pure-python; no system deps. |
| `requests` (Odds API) | already installed | OK | Use `httpx.AsyncClient` to match existing client style. |
| Pinnacle direct API | not used | n/a | The Odds API is the documented path; Pinnacle does not publish a public API. |

No new system-level deps (no eccodes-style asks). Per CLAUDE.md §9 each addition still requires explicit signoff in the PR.

## Cost impact

- **The Odds API GOAT tier:** $30/mo = $360/yr. Per `CLAUDE.md` §11 already budgeted.
- **balldontlie free fallback:** $0; rate-limited but workable in development.
- Other components: free.

## Compliance

NBA on Kalshi has the same compliance posture as weather per [`docs/COMPLIANCE-ADDENDUM.md`](../COMPLIANCE-ADDENDUM.md):

- Kalshi NBA moneylines = CFTC event contracts, **not securities**. Trading them is contractually permitted in the user's outside-activities policy.
- **State availability** is the actual blocker per CLAUDE.md §5 readiness #8: MA / NV / OH / AZ / WA currently blocked or contested for sports event contracts. The user's state of residence determines whether real-money NBA trading is even available; verify before Phase 5 transition.

## Out of scope (don't add to v1)

Per [`CLAUDE.md`](../../CLAUDE.md) §2, none of the following ship in v1 even if they're tempting after the basic Elo lands:

- Player props / totals (research suggests these have edge but liquidity is thin and the model surface is much larger).
- In-game / live markets (the v1 cadence is daily; live needs sub-minute reactivity).
- Sentiment / Twitter / Reddit signals (explicit non-goal).
- LLM-derived features (Pass 1 §1d already disqualified).
- Multi-game parlays (latent dependence makes Kelly sizing wrong).

## Decision deferred to start of Phase 3

When the gate clears and we kick off Phase 3, revisit these:

1. **The Odds API tier.** $30/mo paid vs. balldontlie free. Free works for backtest seed data; paid is needed for live operational ingest if the daily cadence requires more than a few hundred requests/day.
2. **Storage rotation.** NBA games × snapshots × multiple bookmakers per game can grow the `pinnacle_odds_snap` table to millions of rows. Decide rotation policy at PR 3.
3. **Backtest reuse vs. fork.** Whether to extend `src/kq/backtest/engine.py` with strategy dispatch or fork into a new `src/kq/backtest/nba_engine.py`. Lean toward the fork — different prediction units (binary moneyline vs. bracket grid), different edges, different risk profile.

## References

- [Pass 1 §1c — NBA market analysis](PASS-1-FEASIBILITY.md#1c-nba-markets-where-is-the-edge)
- [CLAUDE.md §5 Phase 3 — NBA addition](../../CLAUDE.md#phase-3--nba-addition-days-1930)
- [FiveThirtyEight NBA methodology (Elo)](https://fivethirtyeight.com/methodology/how-our-nba-predictions-work/)
- [The Odds API pricing](https://the-odds-api.com/) (verify against current schedule before PR 3)
- [nba_api swar/nba_api](https://github.com/swar/nba_api)
- [nbainjuries mxufc29/nbainjuries](https://github.com/mxufc29/nbainjuries)
