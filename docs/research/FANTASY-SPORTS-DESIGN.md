# Fantasy Sports Expansion — Design (2026-07-27)

Owner-requested scope adjustment: build out the sports section in parallel with
the running weather lane — **NBA + NFL**, and extend both into **fantasy
sports**: who to start, bench, draft, and the chance of winning a matchup.

## The owner's hypothesis, refined

> "When we pull all these sources and compile which teams will most likely
> win, it should also apply to fantasy."

**Half right, and the right half is the expensive half.** What transfers
directly (already built for team-win modeling):

| Shared source | Team-win use | Fantasy use |
|---|---|---|
| Schedules (nba_api / NFL lane) | who plays whom, rest | weekly slate, bye weeks |
| Injuries feed | availability adjustment | start/sit triggers, waiver spikes |
| **Vegas lines (The Odds API, already ingested)** | fair win prob | **the single best public predictor of fantasy scoring environment** — implied team totals + spreads → expected plays, game script, garbage time |
| Elo / team strength | win prob | opponent-quality matchup adjustment |
| The whole ops substrate | cron, DuckDB, reports, dashboard | identical |

What does **not** transfer: team win probability says nothing about *which
player* scores the points. Fantasy needs a **player-level projection layer**
that does not exist yet:

- **Volume**: minutes (NBA) / snaps, targets, carries (NFL) — the dominant
  fantasy signal
- **Efficiency**: per-touch production, regressed properly
- **Matchup**: opponent defense vs position, pace
- **Cascades**: injury to a starter re-routes volume to specific backups
- **Game script**: big favorite → run-heavy 4th quarter; big dog → pass volume
  (this is where the odds ingest becomes a fantasy feature, not just a price)

So the architecture is: **existing team lane feeds a new player-projection
lane**; fantasy outputs sit on top of both.

## Phased plan (ordered by the calendar, not by elegance)

**The clock that matters: NFL fantasy drafts happen late August – early
September.** Draft tooling delivered September 10th is worthless. NBA drafts
are mid-October. Therefore NFL player lane first, NBA second, despite NBA
having the richer existing client.

### Phase F1 — NFL player data + projections (target: mid-August)
- Ingest weekly + historical player stats: rosters, snap counts, targets,
  carries, red-zone usage, depth charts. Source: the nflverse ecosystem
  (`nfl_data_py`) — free, maintained, the de-facto standard. **New dependency
  → needs §9 sign-off.**
- `player_game` + `player_projection` tables (every row `as_of`-stamped, same
  look-ahead discipline as weather).
- Projection model v0: volume share × efficiency, adjusted by implied team
  total (from our own odds ingest), opponent positional defense, and injury
  status. scikit-learn only (§2 ML policy holds).
- **Weekly self-scoring**: every projection is scored against actual fantasy
  points after games settle — same reality-contact discipline as the weather
  Brier ledger. We know within weeks whether the projections are calibrated.

### Phase F2 — Draft kit (hard deadline: ~Aug 25)
- Season-long projections per player → positional scarcity → **VORP-based
  draft board + auction values**, exportable as a sortable sheet + dashboard
  tab. Tuned to the league's scoring settings.

### Phase F3 — Weekly automation (in-season)
- Tuesday waiver report: usage spikes (snap/target deltas), drop candidates.
- Thursday/Sunday start-sit: ranked lineup per roster with projection
  distributions, not just point estimates.
- **Matchup win probability**: Monte Carlo over both rosters' projection
  distributions → "you win this week with p=0.63". Delivered through the
  existing 8-hourly report + a dashboard tab.

### Phase F4 — NBA fantasy (target: early October)
- Same pattern; `nba_api` already carries player box scores (no new
  dependency). Category leagues need per-category projections (pts/reb/ast/
  stl/blk/TO/FG%/FT%/3PM) — modest extension of the same volume×efficiency
  frame.

### Phase F5 — League integration (after F2)
- Pull the actual league: rosters, scoring, opponents. Platform APIs differ
  (Sleeper: open+free; ESPN: unofficial but workable; Yahoo: OAuth). Until
  wired, F2/F3 outputs work standalone with manually-entered rosters.

## What this is NOT (scope guards)
- **No DFS** (DraftKings/FanDuel daily lineups) — gambling-adjacent, separate
  compliance surface, not requested.
- **No real-money anything** — unchanged; fantasy outputs are analysis.
- **No in-game trading** — separate path per the stoppage-window design
  discussion; websocket recorder remains post-Phase-5.
- Kalshi NBA/NFL *team* paper trading continues unchanged alongside; fantasy
  reuses its data, doesn't replace it.

## Locked decisions (owner, 2026-07-27)

- **`nfl_data_py` dependency: APPROVED** (§9 sign-off) — pinned, used only in
  the NFL player lane. NBA player stats come from the existing `nba_api` dep.
- **Platforms: ESPN + Yahoo** (some leagues may not exist yet) → F5 targets
  ESPN first (league ID + cookie auth), Yahoo second (OAuth). Standalone
  manual-roster mode is a first-class citizen, not a fallback.
- **Scoring: BOTH Standard and PPR are first-class outputs** — scoring is a
  config knob from day one; every projection/draft artifact renders under
  both formats (half-PPR falls out for free).
- **League type: redraft is the priority**; keeper/dynasty valuation (age
  curves, rookie premiums) goes on the roadmap for later.

## Honest uncertainties
- Public player projections are a crowded field (ESPN, Yahoo, FantasyPros do
  this free). Our edge candidates: (1) odds-driven game-script integration
  done properly, (2) calibrated *distributions* rather than point estimates
  (nobody gives you "72% chance Player X beats Player Y this week"), (3) the
  self-scoring ledger — we will *know* our skill, which the free sites never
  publish. If after a season the ledger says we add nothing over FantasyPros
  consensus, we say so and pivot to consensus + our matchup layer.
- NFL projections from public data lag Vegas player props; player-prop ingest
  (The Odds API carries them) is the natural v2 accuracy lever.
