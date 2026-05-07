# CLAUDE.md — forecast-lab Operating Playbook

> This file is loaded automatically by Claude Code in this repo. Treat it as standing instructions. When in doubt, read `docs/research/PASS-1-FEASIBILITY.md`, `docs/research/PASS-2-EQUITIES-AGENT.md`, and `docs/COMPLIANCE-ADDENDUM.md`. The addendum supersedes Pass 2 where they conflict.

## 1. Project Vision

Build a production-grade, calibrated, paper-trading-first system that forecasts Kalshi event contracts in two verticals:

1. **Weather markets** — daily high temperature at specific US airports (LAX, JFK, MDW, MIA, DEN, AUS).
2. **NBA markets** — playoff and regular-season game moneylines, with selective props later.

Edge sources (in priority):

- Bias-corrected ensemble weather forecasts (GEFS + ECMWF + HRRR + METAR nowcast).
- Pinnacle-anchored fair-value arbitrage on Kalshi NBA markets.
- Disciplined Kelly sizing, maker-order-first execution, strict calibration testing.

Long-term possible path: subscription product delivering signals (not trades). All product/legal decisions deferred until after v1 ships and the Phase 5 gate is cleared.

## 2. Non-Goals (v1)

These are explicit — do not add them to the v1 scope regardless of how interesting they sound.

- NO real-money trading until §5 gate is passed.
- NO sentiment/LLM-as-probability features.
- NO Twitter/Reddit ingestion.
- NO equities, crypto, political, or macro markets.
- NO multi-user dashboard, auth, payments, marketing site.
- NO Polymarket, Crypto.com, or Robinhood execution (price-compare only).
- NO exotic orders (iceberg, IOC optimization) — plain limit/market only.
- NO ML beyond scikit-learn + LightGBM until baseline NGR/EMOS is calibrated over 500+ events.
- NO autonomous agent running live; paper scaffolding is acceptable.

"Cool idea" ≠ v1 feature. Everything else is a v2 ticket.

## 3. Architecture (v1)

```
[ NOAA / Open-Meteo GEFS+ECMWF+HRRR ] ─┐
[ METAR aviationweather.gov          ] ─┼─► ingest ─► DuckDB ─► features ─► models ─► signals ─► execution ─► Kalshi
[ nba_api / nbainjuries              ] ─┤                                                          (paper | live)
[ Pinnacle / balldontlie / Odds API  ] ─┘                                                                │
                                                                                                        ▼
                                                                            Streamlit dashboard + cron on always-on Windows PC
```

## 4. Repo Structure

Source under `src/kq/`. Tests under `tests/`. Research notebooks under `notebooks/` (NOT imported by production code). Scheduled jobs under `src/kq/flows/` or `scripts/` depending on complexity. Dashboard under `src/kq/dashboard/`.

All timestamps in UTC in storage; convert at display layer. Every data-producing function returns a typed `pd.DataFrame` or `pl.DataFrame` with a documented schema. **Every feature row carries an `as_of` column — no exceptions.** This is how we avoid look-ahead bias.

## 5. Phased Milestone Plan

### Phase 0 — Setup (Days 1–2)

Full walkthrough + verification checklist: [`docs/SETUP.md`](docs/SETUP.md).

- Initialize repo; `pyproject.toml` with `uv`; `ruff`, `mypy --strict`, `pytest` configured.
- `.env.example` with all required API keys; settings via `pydantic-settings`.
- Bootstrap DuckDB schema (`scripts/bootstrap_db.py`).
- GitHub Actions CI running `ruff check`, `mypy src/kq`, `pytest`.
- Install on M1 Pro (native) and the Windows PC (via WSL2); both machines run `uv run python -m kq version`.

**Exit criteria:** `uv run pytest -q` green, `uv run ruff check .` clean, `uv run mypy src/kq` clean, DuckDB initialized on both machines.

**Status (2026-04-23):** Mac ✅ done. Windows/WSL2 ⬜ TODO — see `docs/SETUP.md`.

### Phase 1 — Kalshi API client + weather data ingest (Days 3–7)
- Wrap `kalshi-python` SDK in `src/kq/clients/kalshi.py` with typed methods: `list_weather_markets()`, `get_orderbook(ticker)`, `get_fills()`, `get_positions()`.
- Open-Meteo client `src/kq/clients/openmeteo.py` — GEFS (31 members) + ECMWF (51 members) for 6 cities.
- METAR client `src/kq/clients/metar.py`.
- Scheduled ingest: weather forecasts every 6h; METAR every 10 min during trading hours; Kalshi weather orderbook snapshots every 30s during trading hours.

**Exit criteria:** 7 consecutive days of uninterrupted ingest on Windows box; Kalshi book snapshots + GEFS forecasts + METAR join cleanly on `(valid_date, station)`.

### Phase 2 — Weather model v0 + paper trading (Days 8–18)
- Pull 2 years of GEFS historical forecasts + NWS verified highs.
- Fit NGR/EMOS bias correction per station × lead time.
- Implement `P(high > threshold)` for each Kalshi bracket.
- Paper-trade executor `src/kq/execution/paper.py` (cannot reach live endpoint).
- Backtest harness with point-in-time features, fee model, fill-prob model, P&L + Brier + reliability diagrams.
- Intraday METAR update logic (Bayesian update on remaining-day max).

**Exit criteria:**
- Backtest Brier ≤ 0.18 on bias-corrected model (raw GEFS is ~0.20–0.22 on center brackets).
- Reliability diagram in 10 buckets — no bucket off by > 10 pp.
- Paper trading live on Windows box for 14 consecutive days, ≥ 50 settled paper trades with logged CLV proxy.

### Phase 3 — NBA addition (Days 19–30)
- `nba_api` for schedule + team stats.
- `nbainjuries` polling — hourly on game days, 15-min in final 3 hours.
- Pinnacle odds ingest (via The Odds API paid tier, or balldontlie free fallback).
- Vig-free fair model from Pinnacle; FiveThirtyEight-style Elo fallback with rest/travel/altitude adjustments.
- Extend paper trader and backtest to NBA.

**Exit criteria:**
- Elo model within 1.5% of FiveThirtyEight historical accuracy on same games.
- Paper-traded NBA signals show positive CLV vs. Pinnacle on N ≥ 100 settled games.

### Phase 4 — Dashboard + monitoring (Days 31–37)
- Streamlit dashboard: (1) current open markets with model prob vs. market, (2) signal log, (3) P&L / Brier / reliability, (4) data freshness.
- Alerting on stale data, failed flows (ntfy or Pushover).

**Exit criteria:** dashboard reachable from phone; alerts fire on synthetic failure tests.

### Phase 5 — Real-money decision gate (Day 38+)

**ALL must be true to enable `--live`:**

1. ≥ 500 settled paper trades across weather + NBA.
2. Brier score better than raw-ensemble baseline by ≥ 5%.
3. Reliability diagram calibrated (no 10 pp deviations in any bucket).
4. Positive paper P&L after simulated fees, net of at least 3 full weeks.
5. CLV vs. Pinnacle ≥ +1% average on NBA.
6. Code: all flows have run ≥ 30 days without unrecoverable failure.
7. Bankroll plan written (initial stake ≤ 2% of risk capital; 0.15× Kelly caps coded as hard limits).
8. Confirmed state availability for sports markets (MA/NV/OH/AZ/WA currently blocked or contested).
9. CPA engaged; decision on §1256 vs. capital treatment recorded.
10. NVIDIA HR/Legal disclosure completed if required by outside-activities policy.

Only after all 10 → enable `live` executor behind `--live --i-understand-the-risks` CLI flag AND `KQ_LIVE=true` env var. Start at 10% of intended bankroll.

## 6. Coding Standards

- Python 3.12, full type hints, `mypy --strict`.
- `ruff` for lint + format; `pre-commit` enforced locally.
- All I/O wrapped in `async` where natural (`httpx.AsyncClient`).
- `structlog` JSON logging with `trace_id` propagation.
- No globals. Config via `pydantic-settings`. Secrets via `.env` (gitignored) + macOS Keychain / Windows DPAPI at runtime.
- Every data-producing function returns a `pd.DataFrame` or `pl.DataFrame` with documented schema.
- Every model produces calibrated probabilities in `[0.01, 0.99]`; exposes `.predict_proba` and `.brier_score`.
- All timestamps stored in UTC.
- **Every feature row has an `as_of` column. No exceptions.**
- Default to no comments. Only comment non-obvious *why*.

## 7. Testing

- `pytest` unit tests for every client, feature, and model.
- Property tests (`hypothesis`) for fee model, Kelly sizing, calibration functions.
- Golden-file tests for backtest outputs (small fixture dataset in `tests/fixtures/`).
- Integration tests against Kalshi demo environment where possible.
- CI runs on every PR; no merge without green.

## 8. Prompting Patterns (for Claude Code sessions)

When asking Claude Code to do work in this repo:

1. **Anchor to the phase.** "We are in Phase 2. Implement `src/kq/models/weather_ensemble.py` per the NGR approach in CLAUDE.md §5."
2. **Specify exit criteria.** "Done when `pytest tests/test_weather_ensemble.py` passes and the backtest produces Brier < 0.19."
3. **Require plan first.** "Before writing code, produce a 5–10 step plan and list the files you will touch. Wait for my approval."
4. **Explicit non-goals.** "Do NOT add dependencies. Do NOT add ML on top of NGR in this PR. Do NOT add live-trading code paths."
5. **Ask for calibration proof.** "After implementing, run the backtest and paste Brier + reliability diagram into the PR description."
6. **Small PRs.** Each PR touches ≤ 10 files and ≤ 400 lines. Open follow-up issues rather than expanding scope.
7. **Pair programming, not autopilot.** Every diff reviewed before merge to `main`.
8. **Provide context files.** When starting a task, paste the relevant schema, the function signature you want, and 1–2 existing files to match style.

## 9. Guardrails — What Claude Code MUST NOT Do Without Explicit Human Confirmation

- Place any real-money order. The live executor must require both (a) `KQ_LIVE=true` env var AND (b) `--live --i-understand-the-risks` CLI flag. If either is missing, refuse.
- Commit API keys, `.env` files, or `*.pem` / `*.key` files.
- Push to `main`. Always open PRs to a feature branch.
- Delete historical data or DuckDB files.
- Modify the fee model, position-sizing caps, or gate criteria in §5 without explicit human sign-off.
- Install new dependencies (every addition requires approval and pinning).
- Make network calls to endpoints not listed in `src/kq/clients/` allowlist.
- Publish anything to PyPI, GitHub release, or public URL.
- Reintroduce broad NVIDIA-adjacent ticker blacklists into docs or code (see `docs/COMPLIANCE-ADDENDUM.md`).

## 10. Always-On Windows PC

Full setup + crontab recipes: [`docs/SCHEDULED-RUNS.md`](docs/SCHEDULED-RUNS.md).

- Install Python via `uv` + `pyenv-win` (or uv-managed Python).
- Run scheduled flows via WSL2 cron for v1; Prefect 3 Windows Service later if cron becomes unmanageable.
- Wake-on-LAN enabled; M1 Pro is dev only.
- Remote access via Tailscale (no exposed ports).
- Backups: nightly rsync of `data/` and `.duckdb` file to external drive + encrypted rclone to Backblaze B2.
- Health check: cron heartbeat → Uptime Kuma → ntfy/Pushover alert on failure.
- Windows Update: active hours 3–5 AM ET so NBA trading hours (7 PM–1 AM ET) are never touched.

## 11. Cost Tracking

| Service | Tier | Est. cost |
|---|---|---|
| Open-Meteo | Free (non-commercial) | $0 |
| NOAA / METAR | Public | $0 |
| `nba_api` / `nbainjuries` | Free | $0 |
| balldontlie | Free tier | $0 |
| The Odds API (Pinnacle) | Free tier (500 req/mo, `regions=eu`) sufficient at v1 cron volume | $0; ~$30-90/yr only if quota exceeded |
| Kalshi API | Free | $0 |
| Claude Code | Subscription or API | ~$20–200/mo |
| AWS S3 / B2 backups | <$5/mo | ~$60/yr |
| **v1 total** | | **~$300–$2,500/yr** |

Log every LLM spend in `costs/llm.csv` with `date, model, input_tokens, output_tokens, usd, task`. Review weekly.

## 12. Common Commands

```bash
make ingest              # one-shot ingest
make backtest STRATEGY=weather_v1
make paper               # start paper trader
make dashboard           # start Streamlit
make live --i-understand-the-risks   # Phase 5+ only

uv run pytest
uv run ruff check .
uv run mypy src/kq
```

## 13. Compliance Quick Reference

Full context: [`docs/COMPLIANCE-ADDENDUM.md`](docs/COMPLIANCE-ADDENDUM.md).

- **Kalshi weather + NBA:** zero compliance surface. CFTC event contracts, not securities.
- **Equity research using public data:** lawful. Default posture.
- **NVDA specifically:** don't trade on internal knowledge. Use ESPP + 10b5-1 plans.
- **Any other ticker:** if you specifically know a non-public material fact about it from work, don't trade that name until the info is public.
- **Evidence trail:** every real-money signal logged with `source_urls[], retrieved_at, generated_at, model_or_method, reasoning`.
- **Selling signals commercially:** post-v1 business question; requires counsel, LLC, possibly restricted universe.

**Not legal advice.** Review NVIDIA Insider Trading Policy, engage a CPA for §1256 treatment, and consult a personal securities attorney before material real-money activity or commercialization.

## 14. Documentation discipline — keep ROADMAP current

[`ROADMAP.md`](ROADMAP.md) is the live status board. Every PR that lands on `main` should update it in the same commit:

- **Shipped a feature** → mark its row ✅ + commit hash
- **Discovered a new gap or backlog item** → add a row with ⬜ or 🟡
- **Decided something is a non-goal / deferred** → add to the "deferred" or "non-goals" section with one-line rationale
- **A Phase 5 readiness criterion changed** → re-check the §5 readiness table

This is socially enforced (no CI gate) but it's the single most important doc discipline for future-you (or future Claude sessions) — when this rots, the project loses its memory. If you ever find ROADMAP.md out of sync with what's on `main`, that's a bug — fix it in a one-line PR.
