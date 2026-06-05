# Session audit — 2026-05-30 (Kalshi PROD switch + Phase 4 close-out + /simplify)

Continues from [`docs/SESSION-2026-05-26-AUDIT.md`](SESSION-2026-05-26-AUDIT.md)
(the #24–#28 testing-hardening arc). This session closed Phase 4's last exit
criterion, did a quality pass, and — the headline — **brought Kalshi PROD
online**, breaking the operational bottleneck every prior audit flagged.

## Headline

- **🔑 Kalshi PROD is live and weather markets are flowing.** The user created a
  prod API key on kalshi.com; we installed it, flipped `KALSHI_ENV=prod`,
  rotated the SOPS encrypted store, and **verified live auth** against
  `api.elections.kalshi.com`. `kq ingest-kalshi` now pulls **~60–72 real
  markets + orderbooks per run** (12 temperature brackets × 6 cities) into
  DuckDB. `kalshi_book_snap` health-check is now **OK** (was `0 rows / WARN`
  every prior session).
- **The switch surfaced + fixed a real bug (#97).** `ingest_kalshi` and
  `paper_trade._pull_kalshi_markets` queried each station's *series* ticker
  (`KXHIGHLAX`) as `event_ticker=`, which matches no dated event → **0 markets**.
  Invisible on demo (0 either way); on prod it would have kept the whole weather
  pipeline — and paper trading — at zero. Fixed to `series_ticker=`; renamed the
  mislabeled `Station.kalshi_event_ticker` → `kalshi_series_ticker`; added a
  direct `_pull_kalshi_markets` test (the paper-flow suite had always mocked it).
- **This starts the Phase 5 settled-trade clock.** #1/#4/#5 (≥500 settled paper
  trades, positive P&L, CLV) were "code-complete pending data"; data now flows,
  so the cron's `paper` jobs accumulate real paper trades from here. **Remaining
  work is time + uptime, not code.**

## Merged this session (#94–#98)

| PR | Area | Summary |
|---|---|---|
| #94 | feat(ops) | `scripts/alert-drill.sh` — Phase 4 exit #2: synthetic-CRIT → real ntfy push. **Phase 4 COMPLETE.** |
| #95 | test | Streamlit `AppTest` render-path smoke (no exception, 6 tabs, both #85 sections). |
| #96 | refactor | `/simplify` pass — de-dup seeders (smoke imports from test_backtest) + cron-test boilerplate helpers. |
| #97 | fix | **Kalshi `series_ticker` query fix** (the prod bug) + field rename + tests. |
| #98 | chore | Rotate `KALSHI_API_KEY_ID` → prod in the SOPS encrypted store (durability/sync). |

## Prod-switch specifics (for future reference)

- Prod key path B was used (Kalshi generated the keypair; user downloaded the
  private key). Installed to `secrets/kalshi.pem` (mode 600); demo key backed up
  at `secrets/kalshi.pem.demo-backup` (gitignored; delete when confident).
- `.env`: `KALSHI_API_KEY_ID=<prod>`, `KALSHI_ENV=prod`, path unchanged.
- Encrypted store updated via `sops --set` so `make bootstrap-secrets` won't
  revert the key ID. Committed (#98, encrypted blob — safe per §6).
- Private key never committed or pasted into chat (written to the box via a
  `Get-Clipboard | Set-Content` PowerShell one-liner; validated with
  `openssl rsa -check`).

## What needs the operator (you) — now mostly done

| Action | Status |
|---|---|
| Create Kalshi prod key + switch `KALSHI_ENV=prod` | ✅ done 2026-05-30 |
| Keep the Windows PC on + WSL keep-alive (cron uptime) | ⬜ ongoing — the clock needs weeks of it |
| Subscribe to ntfy topic `flab-a7k2p9wq4m3x` | ⬜ recommended (verified deliverable via #94 drill) |
| CPA (§1256) + NVIDIA disclosure (Phase 5 #9/#10) | ⬜ external, before any real-money activity |
| Delete `secrets/kalshi.pem.demo-backup` | optional, when confident in prod |

## Verification commands for when you're back

```bash
wsl -d Ubuntu
cd ~/forecast-lab
git log --oneline -6                    # this session's merges (#94–#98)
uv run python -m kq ingest-kalshi       # expect ~60–72 markets on prod
uv run python -m kq health-check        # kalshi_book_snap should read OK
uv run python -m kq paper-summary       # settled-trade count — the Phase 5 #1 clock
tail -50 logs/cron.log                  # confirm cron still firing
```

## Phase 5 readiness delta this session

The prod-data prerequisite for #1/#4/#5 is **met** — for the first time the
project advances on its actual gate (settled-trade accumulation) rather than on
code. No code gate flipped, but the thing blocking all of them did. The next
genuinely-valuable code work emerges only once data accrues (calibration on real
fills, CLV on real Kalshi closes).
