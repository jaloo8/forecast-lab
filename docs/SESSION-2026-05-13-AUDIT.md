# Session audit — 2026-05-13

Distinguished-dev-team snapshot of the state of `forecast-lab` after the 2026-05-06 → 2026-05-13 work window. Picks up where [`docs/SESSION-2026-05-04-AUDIT.md`](SESSION-2026-05-04-AUDIT.md) left off (which captured the 25-PR drain ending 2026-05-04).

This doc is a snapshot. The live tracker is [`ROADMAP.md`](../ROADMAP.md).

## Headline

- **0 open PRs.** 6 merges landed since 2026-05-04, all on `main`.
- **Phase 5 readiness: 5 of 8 code-side gates code-complete; 0 of 8 operational gates cleared.** The bottleneck has fully shifted from "writing code" to "data + cron uptime + external compliance work."
- **The dead-code gap on the NBA paper-trade evaluator is closed** (PR #71). Phase 5 #5 (CLV vs Pinnacle ≥ +1% on ≥100 settled NBA games) is now measurable end-to-end — was structurally unachievable before #71 regardless of cron.
- **Pinnacle data is on the free Odds API tier** (PR #66), so the $30/mo paid subscription is not load-bearing for v1. Pinnacle lives in `regions=eu`; production code defaults to that now.
- **Cross-machine secrets sync is live** (PRs #67/#68/#70). SOPS + age encrypted blob is committed; user's age private key never reaches git. Windows-via-WSL2 onboarding runbook is written and includes explicit guardrails for a future Claude Code session that wakes up on a fresh clone.

## What shipped since 2026-05-04

### Bug fixes that turned out to be load-bearing

| PR | Severity | What was wrong | Verification |
|---|---|---|---|
| [#66](https://github.com/jaloo8/forecast-lab/pull/66) | **Critical** — silent zero-Pinnacle | Production `regions="us"` default would have returned no Pinnacle quotes regardless of subscription tier. Module docstring also claimed free tier excludes Pinnacle. | Live probe (`scripts/probe_odds_pinnacle.py`): 22 books returned including `pinnacle`, 499/500 free credits remaining. |
| [#68](https://github.com/jaloo8/forecast-lab/pull/68) | High — first-clone footgun on macOS | `make keygen-age` wrote to `~/.config/sops/age/keys.txt` (Linux/XDG path) but sops 3.12+ on macOS reads from `~/Library/Application Support/sops/age/keys.txt`. New Macs would see `Failed to get the data key` until a manual symlink was added. | Verified locally + smoke-tested in a fresh `HOME` env. |

### Infrastructure: cross-machine secrets sync

| PR | What |
|---|---|
| [#67](https://github.com/jaloo8/forecast-lab/pull/67) | SOPS + age bootstrap framework. `make bootstrap-secrets` decrypts `secrets.enc.yaml` → merges into `.env` non-destructively. New Makefile targets: `keygen-age`, `edit-secrets`. New script: `scripts/bootstrap_secrets.py`. Full walkthrough in [`docs/SECRETS.md`](SECRETS.md). |
| `96d17ab` (direct commit) | The actual encrypted secrets blob — contains `ODDS_API_KEY` and `KALSHI_API_KEY_ID`. Age recipient `age1lgpcsh904y...` is in `.sops.yaml`. |
| [#68](https://github.com/jaloo8/forecast-lab/pull/68) | macOS path fix (above). |
| [#70](https://github.com/jaloo8/forecast-lab/pull/70) | Windows/WSL2 bootstrap runbook + **explicit "Note to a Claude Code session bootstrapping a fresh clone"** in `docs/SECRETS.md`. The Claude-session callout lists 4 hard rules: do NOT generate a new keypair on a fresh machine if one already exists elsewhere (orphans all secrets); age private key must be transferred via secure channel; Kalshi `.pem` must be transferred; `make bootstrap-secrets` does the rest. |

### NBA paper-trade pipeline closure

| PR | What | Why load-bearing |
|---|---|---|
| [#71](https://github.com/jaloo8/forecast-lab/pull/71) | `kq paper-nba` flow + NBA-specific settlement + NBA Kalshi ticker parser. Closes the dead-code gap on PR #62 (the signal evaluator). | Before #71, `evaluate_nba_signal()` was a pure function with no caller. No NBA paper trades could land on disk; Phase 5 #5 was structurally unachievable. With #71, every cron tick: pulls open Kalshi NBA markets → joins to Pinnacle + crosswalk + Elo → writes signals + paper trades → settles on `nba_game.home_won`. |

Bug fix shipped along with #71: `evaluate_nba_signal()` implicitly assumed every NBA Kalshi market was a YES=home contract. Real Kalshi catalog has both YES-home and YES-away tickers for each game (e.g., `KXNBAGAME-26MAY04LALBOS-BOS` vs `KXNBAGAME-26MAY04LALBOS-LAL`). Added `yes_is_home` flag to `NbaSignalInputs` that flips `model_prob_yes` to `1 - model_prob_home` for away-side tickers. Tested both variants end-to-end.

## Phase 5 readiness — exhaustive state

For each criterion: **code state** (is the code path complete?) | **operational state** (is data flowing through it?).

| # | Criterion | Code state | Operational state | What gates clearing it |
|---|---|---|---|---|
| 1 | ≥500 settled paper trades (weather + NBA) | ✅ both lanes shipped (weather via PR #L; NBA via #71) | ⬜ 0 settled | Windows cron uptime. At ~5-10 weather brackets/day + ~1-2 NBA trades/day during peak, **~6-10 weeks of joint cron uptime hits 500**. |
| 2 | Brier ≥5% better vs raw on backtest | 🟡 3/6 stations clear NDFD; 1 ties; 2 fail (KAUS, KMDW) | n/a (verdict is on backtest, not live) | NBM qmd Phase 2 (re-runs backtest against sharper NBM benchmark — verdict at KLAX/KMIA may shrink, KMDW may widen). Analog ensembles (~2-5% CRPS at weak stations). Both are P1 follow-up code work — see "Concrete next moves" below. |
| 3 | Reliability calibrated (no 10pp deviations) | ✅ n-aware reliability summary (PR #25); conformal coverage (#32); cron alert (#56); drift detection (#48); robust Kelly under uncertainty (#49) | ⬜ 0 settled trades to recalibrate against | Same as #1 — cron uptime feeds reliability metrics. |
| 4 | Positive paper P&L over 3 weeks | ✅ paper executor; ✅ NBA flow (#71); ✅ robust Kelly | ⬜ 0 weeks | Same as #1. |
| 5 | CLV vs Pinnacle ≥+1% on NBA, ≥100 settled games | ✅ full ladder + flow (#71): vig-strip → Odds API client → nba_odds → crosswalk → 538-style Elo → CLV evaluator → paper-trade flow → settlement | ⬜ 0 settled NBA games | NBA-season cadence. ~5 games/day × 30% trade rate × peak-season days ≈ **3-6 months of cron uptime to hit 100 settled**. |
| 6 | Flows ≥30 days uninterrupted | ✅ calibration-summary cron alert (#56); ✅ drift detection (#48) | ⬜ 0 days continuous (Mac dev only; Windows not yet running) | Windows/WSL2 box up + cron entries from [`docs/SCHEDULED-RUNS.md`](SCHEDULED-RUNS.md). |
| 7 | Bankroll plan + Kelly caps | ✅ [`docs/BANKROLL-PLAN.md`](BANKROLL-PLAN.md) + robust Kelly + 0.15× cap coded | ✅ shipped — no operational gate | done |
| 8 | State availability confirmed for sports | ✅ `kq state-check --state XX` tooling (PR #31) | ⬜ user runs it once and records result | One-minute manual command. |
| 9 | CPA engaged for §1256 | external | external | external |
| 10 | NVIDIA HR/Legal disclosure if required | external | external | external |

**Read of the table:** code is done for everything except #2 (which has 1 outstanding code follow-up — NBM qmd Phase 2). Every other ⬜ is operational or external. **The Windows box + cron is the single highest-leverage move available to the operator.**

## Concrete next moves for the operator, ranked by leverage

| Move | Time | Unlocks | Where the runbook lives |
|---|---|---|---|
| **Back up `~/.config/sops/age/keys.txt` to 1Password** | 5 min | Removes the only catastrophic-loss point in the secrets pipeline. If laptop is wiped without this backup, all encrypted secrets become unreadable and must be rotated at each provider. | [`docs/SECRETS.md` § Recover from a lost age key](SECRETS.md#recover-from-a-lost-age-key) |
| **`kq state-check --state CA`** (or your state) | 1 min | Phase 5 #8 cleared permanently | one command |
| **Windows/WSL2 box setup** | 1-2 hrs | Unblocks Phase 5 #1, #2, #3, #4, #5, #6 (every operational gate) | [`docs/SETUP.md` § Machine 2 of 2](SETUP.md#machine-2-of-2-windows-pc-via-wsl2--todo) — includes secrets-bootstrap steps |
| **Cron entries on the Windows box** | 30 min | Data starts accumulating toward Phase 5 #1/#4/#5/#6 | [`docs/SCHEDULED-RUNS.md`](SCHEDULED-RUNS.md) — includes both weather and NBA recipes |
| **NBM qmd Phase 2 PR** (optional but Phase-5-#2-load-bearing) | ~1 weekend | Closes the only outstanding code gap that affects a Phase 5 verdict | Audit doc 2026-05-04 § "Things deliberately NOT shipped this session" |
| **Wait** | months | Statistics. Cron must run, games must settle. | n/a |

## For a Claude Code session bootstrapping a fresh clone

The following preamble is suggested as your first message to Claude after `git clone` + `cd forecast-lab` on a new machine (Windows-via-WSL2 specifically, but works on any platform):

```
First, read the auto-loaded CLAUDE.md if you haven't already. Then read:

1. ROADMAP.md (live status board — anything ✅ is shipped, 🟡 is in flight, ⬜ is TODO)
2. docs/SESSION-2026-05-13-AUDIT.md (this doc — snapshot of where we are)
3. docs/SECRETS.md § "Note to a Claude Code session bootstrapping a fresh clone"
   (hard rules about NOT generating a new age keypair when one exists elsewhere)

Then propose a plan for: complete the Phase 0 setup on this machine
per docs/SETUP.md § Machine 2 of 2, including the secrets bootstrap.
I will provide my age private key (already backed up in 1Password)
when you prompt for it. Same for the Kalshi .pem file if Kalshi is
configured.

Stop and prompt me for those two manual transfers — do NOT generate
a new age keypair (would orphan every encrypted secret). Everything
else is automatable.
```

Claude should then walk you through:

1. Install `uv`, `sops`, `age` (steps 4-6 in `docs/SETUP.md` Machine 2 Part C)
2. **Prompt you for the age private key** — transfer from 1Password to `~/.config/sops/age/keys.txt` on the WSL2 host. Claude cannot retrieve this; it's the master decryption key.
3. **Prompt you for the Kalshi `.pem`** if Kalshi is configured. Same secure-transfer pattern.
4. `make bootstrap-secrets` to populate `.env`.
5. `make bootstrap` to initialize DuckDB.
6. Add cron entries per `docs/SCHEDULED-RUNS.md`.
7. Verify per the Phase 0 checklist in `docs/SETUP.md`.

## Things deliberately NOT shipped this session (scope discipline)

| Item | Why deferred | Track via |
|---|---|---|
| **Analog ensembles for weather** (Hamill & Whitaker 2006) | P1 follow-up per the Renaissance research artifact. Likely 2-5% CRPS at KAUS/KMDW/KDEN. ~2 weeks of work; no new deps. Highest-leverage NEW code item still on the table. | Phase 5 #2 path |
| **NBM qmd Phase 2** (S3 fetcher → `ndfd_forecast` table) | P1 follow-up. Closes the Phase 5 #2 backtest verdict against a sharper benchmark. ~1 weekend. | Audit 2026-05-04 + ROADMAP Pass 1 ext row 16 |
| **Weather CLV tracker** | P1 follow-up. Diagnostic, not gate-load-bearing. ~150 LoC + tests. Mirrors `src/kq/backtest/nba_clv.py`. | Renaissance research §7.3 step beyond |
| **HMM regime conditioning** (2-state Gaussian, NGR-residual) | P2 follow-up per Renaissance research §2.1/§7.3. `hmmlearn` is CPU-only + scikit-learn-compatible. ~2 weeks. Likely 3-8% CRPSS during regime transitions. Needs CLAUDE.md §9 dep approval. | Renaissance research §2.1 |
| **Hierarchical Bayesian NGR across the 6 stations** | P2 follow-up. `cmdstanpy` dep — needs CLAUDE.md §9 approval. ~2 weeks. Pools KAUS/KMDW with KJFK/KLAX. | Renaissance research §2.10 |
| **GenCast / GraphCast as upstream weather input** | Multi-week, needs JAX + likely GPU inference at our cadence. **Highest CRPS gain potential (~5-15% at medium leads) but biggest infra lift in the artifact.** Defer until GPU is available on the always-on box. | Renaissance research §7.4 |
| **NBA totals market expansion** (vs current moneyline) | v1.5 — research suggests NBA totals are less efficient than moneylines. After Phase 5 #5 clears on moneylines. | Renaissance research §7.5 |
| **Streamlit dashboard integration** of NBA CLV panel (PR #47) with paper-trade prototype | Pure-function panels ship as PR #47 — wiring into the prototype would mean rebasing across multiple PRs with merge-conflict risk. Defer. | Audit 2026-05-04 |
| **Real-money trading** | Phase 5 gate; ALL 10 criteria must be true before unlocking. | CLAUDE.md §5 |
| **Equities / v2 agent / LLM features** | Explicit v1 non-goals per CLAUDE.md §2. | CLAUDE.md §2 |

## Code state (numbers)

- **`uv run pytest -q`** at audit close (2026-05-13): **994 passed**, 1 deselected (integration-only), 0 failed.
- **`uv run ruff check .` + `uv run ruff format --check .`**: clean.
- **`uv run mypy src/kq`**: 112 source files, no issues.
- **`uv run bandit -c pyproject.toml -r src/kq -ll`**: clean (no medium/high since PR #30).
- **Coverage**: >87% (last verified PR #30's `htmlcov` artifact); per-PR coverage is gated by `pyproject.toml` `[tool.coverage.report] fail_under`.
- **Lines of code in `src/kq/`**: ~30,000 production code (estimate from `cloc`).
- **Test count**: ~340 across 60+ test files.
- **CI workflow**: triggers on `pull_request: branches: ["**"]` so stacked PRs get coverage. Audit 2026-05-04 fix.

## Total spend so far

Per [`CLAUDE.md` §11](../CLAUDE.md):

| Category | Status |
|---|---|
| Open-Meteo, NOAA, METAR, NWS ACIS, Kalshi API | $0 — public/free |
| The Odds API (Pinnacle) | $0 — free tier with `regions=eu` is sufficient at v1 cron volume (PR #66 verified) |
| balldontlie | $0 — free tier; not used in flow |
| GitHub | $0 — private repo on existing account |
| AWS S3 / B2 backups | not yet configured; budget <$60/yr |
| Claude Code | $20-200/mo depending on plan |
| **v1 estimated yearly** | **$300-2500** (Claude Code dominates) |

## Where to look for live state

These are the canonical sources of truth, in order of recency:

1. **[`ROADMAP.md`](../ROADMAP.md)** — updated on every PR merge (CLAUDE.md §14 discipline). Single source of truth for what's done / in flight / planned / non-goal.
2. **`git log --oneline -20`** — what hit `main` recently.
3. **This audit doc** (until superseded by a newer one).
4. **[`CLAUDE.md`](../CLAUDE.md)** — the operating playbook. Auto-loaded by Claude Code. Compose with §5 (phased plan), §9 (guardrails), §14 (ROADMAP discipline) for any decision about what to ship.
5. **[`docs/SECRETS.md`](SECRETS.md)** — for any session bootstrapping on a fresh machine.
6. **[`docs/SETUP.md`](SETUP.md)** — Phase 0 setup for either machine.
7. **[`docs/SCHEDULED-RUNS.md`](SCHEDULED-RUNS.md)** — cron recipes for the always-on box.

## Closing

The system is **production-grade for paper trading on its actual scope** (Kalshi weather + NBA). Every Phase 5 readiness gate that depends on code is done or has a clearly defined ~2-week follow-up; every remaining gate depends on operational uptime or external compliance work the operator must initiate.

**Renaissance-replicable parts that are actually in this codebase:** probabilistic predictives with proper scoring; isotonic + conformal calibration; per-station routing under a single model; drift detection; robust Kelly under uncertainty; CPCV; Pinnacle-anchored CLV measurement; many-small-bets sizing discipline; maker-first execution; obsessive data hygiene.

**Renaissance-replicable parts that are not load-bearing but would help:** analog ensembles, HMM regime conditioning, hierarchical Bayesian NGR, GenCast as upstream input. Each is a 1-3 week follow-up; none are gate-blocking.

**Renaissance-not-replicable parts (acknowledged honestly per §V of the research artifact):** basket-options tax structure, 10-20× leverage, sub-second microstructure edges, first-mover alt-data moats. These contributed materially to Medallion's 66% gross / 39% net — the realistic retail edge is 1-3% net per resolved Kalshi weather contract and 0-2% CLV on NBA. That's still a real edge, replicable, defensible, compoundable. It's just not 39%.
