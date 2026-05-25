# Multi-sport expansion — NFL + PGA (design)

> Status: **design + foundation library shipped** on `feat/multi-sport-nfl-pga` (2026-05-24). Ingest flows / schema / paper-trade wiring are explicitly deferred follow-ups (see §7). This doc is the IC7 design record; it is NOT a commitment to v1 scope — per [`CLAUDE.md §2`](../../CLAUDE.md) weather + NBA remain the v1 verticals. NFL/PGA are an owner-requested v1.5 expansion and ship behind the same paper-first, Phase-5-gated discipline.

## 0. Why / context

The owner asked to add NFL and PGA because (a) NBA season is wrapping up, leaving the sports lane idle through summer, and (b) NFL (Sep–Feb) and golf Majors (Apr–Jul) fill the calendar. The edge thesis is unchanged from NBA: **strip the vig from a sharp book, get a fair probability, compare to the Kalshi contract price, trade the gap, measure CLV.** No model is required for the signal — the sharp book *is* the model.

## 1. What's reusable vs. new (from the NBA architecture map)

**Sport-agnostic, reused as-is:**
- `kq.models.vig_strip` — 2-way devig (proportional + power). NFL moneyline is structurally identical to NBA moneyline.
- `kq.clients.the_odds_api.TheOddsApiClient` — transport, quota tracking, response parsing tree.
- `kq.execution.paper.evaluate_market` — Kelly / fee sizing (sport-independent).
- Paper-trade settlement repository pattern, CLV aggregation math.

**New per sport:**
- Odds API sport keys + (for golf) an *outrights* fetch/parse path.
- N-way outright devig (golf): the 2-way functions don't generalize — large fields, large overround.
- Kalshi ticker parsers (`KXNFLGAME`, `KXPGATOUR`).
- (Deferred) schedule/results source, crosswalk, paper-trade flow per sport.

## 2. NFL — Pinnacle-anchored moneyline (low effort, high reuse)

- **Odds API key:** `americanfootball_nfl`, market `h2h`. **Pinnacle present via `regions=eu`** (verified live 2026-05-24: 75 games returned even in the off-season — the API carries next-season lines early). 1 credit/request.
- **Devig:** the existing 2-way `devig_proportional` / `devig_power`. No new math.
- **Kalshi series:** `KXNFLGAME`, event ticker `KXNFLGAME-<YY><MMM><DD><AWAY><HOME>` with per-team YES contracts (mirrors NBA). **Caveat (verified concern):** NFL team codes are *not* uniformly 3 letters (`SF`, `NE`, `LAC`, `WAS`). The NBA parser's hard `[A-Z]{3}` assumption breaks. The NFL parser splits the concatenated `<AWAY><HOME>` block against a **known 32-team abbreviation set** rather than by fixed width, and returns `None` if the split is ambiguous. Per-team YES suffix is **unverified against prod** (demo seeds 0 NFL markets) — round-trip test is the authority until prod confirms.
- **Settlement source (deferred):** the Odds API `/scores` endpoint returns completed-game scores for the same `sport_key` — no `nba_api` analogue needed. This is the planned NFL results source; no new dependency.
- **No Elo for v1.** The Pinnacle-anchored path needs no rating model. An NFL Elo (parameterizing `nba_elo`) is a *fallback* for when Pinnacle hasn't posted a line yet — a follow-up, not a blocker.

## 3. PGA — large-field outright (new structure)

- **Odds API keys:** Majors only — `golf_masters_tournament_winner`, `golf_pga_championship_winner`, `golf_us_open_winner`, `golf_the_open_championship_winner`. **No generic PGA Tour key** (non-Major stops need DataGolf or similar — out of scope). Market `outrights` (skip `outrights_lay`, an exchange artifact). 1 credit per region per key.
- **No Pinnacle for golf** (verified live 2026-05-24): the golf feed returns betonlineag, lowvig, betmgm, draftkings, fanduel, betrivers, betfair_ex_eu, everygame — **Pinnacle is absent.** This materially weakens the fair-value anchor vs. NBA/NFL. Decision: anchor golf to the **lowest-overround available book** among a trusted allowlist (observed: `lowvig` and `betonlineag` at booksum ≈ 1.375; `betmgm` ≈ 1.58; exchanges excluded as anchor). The anchor book is selected per-event at devig time (lowest valid booksum wins), and the chosen book is recorded with every fair-value row for auditability. **This is a known limitation — golf CLV is "vs. the sharpest retail book available," not "vs. Pinnacle."**
- **Devig — N-way, power method.** Observed booksums: 1.375 (lowvig, 94 players) to 2.48 (betfair exchange, 117 players incl. longshots). Overround of 37%+ makes method choice material; the multiplicative method systematically over-weights the long tail of no-hope players. The **power method** (solve `k` s.t. `Σ pᵢ^k = 1`, then renormalize) corrects favorite-longshot bias and stays bounded on large fields. `devig_outright(method="power")` is the default; multiplicative is available for comparison.
- **Kalshi series:** `KXPGATOUR`, event tickers like `KXPGATOUR-PGC26` (2026 PGA Championship), `KXPGATOUR-USO26`. Each player is a separate YES/NO contract resolving YES→$1 for the winner. The **per-player contract suffix is unverified** (demo seeds 0 golf markets); the parser extracts the event code and an optional player slug defensively and is flagged accordingly.
- **Name matching is the hard part (deferred).** Odds API player names (`"Scottie Scheffler"`, `"J.T. Poston"`) must crosswalk to Kalshi player tickers — fuzzier than team-abbr matching (initials, suffixes, accents). A normalized-name crosswalk is the gating follow-up before any golf paper trade.

## 4. Devig math summary

| Market | Outcomes | Typical booksum | Method | Module |
|---|---|---|---|---|
| NBA / NFL moneyline | 2 | ~1.02 (Pinnacle) | proportional (default) / power | `devig_proportional`, `devig_power` (existing) |
| Golf outright | 67–120 | 1.375–1.75 (full field) | **power** (default) / multiplicative | `devig_outright` (new) |

`devig_outright` validates booksum ∈ [0.99, 3.0] (golf overround is large; the upper band is raised from the 2-way's 1.5), solves the power exponent by bisection on `[0.05, 5.0]`, and renormalizes. Returns fair probabilities per outcome name plus the raw booksum and method for the audit trail.

## 5. Compliance / state

NFL and PGA Kalshi contracts are CFTC event contracts, same posture as NBA — sports-event contracts, contested in the ~10 states tracked by `kq state-check`. California (operator state) is green per the May 2026 snapshot. No new compliance surface beyond what NBA already carries. Real-money trading stays behind the Phase 5 gate (`CLAUDE.md §5`).

## 6. What shipped in this PR (verifiable now)

1. `vig_strip.devig_outright` — N-way power/multiplicative devig + `OutrightMarket` / `OutrightFairProbabilities`. Property-tested.
2. `the_odds_api` — `SPORT_NFL`, `GOLF_MAJOR_KEYS`, generic `fetch_h2h(sport_key)`, `fetch_outrights(sport_key)` + `parse_outrights_response` (handles null home/away, filters `outrights_lay`). Fixture-tested against a real US Open response.
3. `_ticker_parser_nfl` / `_ticker_parser_pga` — Kalshi parsers, defensively flagged unverified, round-trip tested.

## 7. Deferred follow-ups (need live prod markets / more code)

- `nfl_odds` / `pga_outright_odds` DuckDB tables + repositories (mirror `nba_odds`).
- `ingest-nfl-odds` / `ingest-pga-odds` CLI flows (no-op-on-empty, like `ingest-nba-odds`).
- NFL team crosswalk (Odds-API name → Kalshi abbr) and **golf player-name crosswalk** (the hard one).
- Odds API `/scores` ingest → NFL settlement; golf settlement on tournament resolution.
- Paper-trade flows `paper-nfl` / `paper-pga` (golf gated on the player crosswalk).
- **Verify both ticker formats against Kalshi prod** before enabling any paper flow.

These are sequenced behind: (a) Kalshi **prod** read access (demo seeds neither), and (b) for golf, the player-name crosswalk. None is blocking for the foundation library above.
