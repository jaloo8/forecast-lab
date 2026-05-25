# Kalshi demo → prod switch (read-only market data)

> One-step-when-you're-ready runbook. Switching to prod gives **real market
> data + orderbooks** so paper trades can actually be discovered and settled.
> It does **NOT** enable real-money trading — the Kalshi client exposes no
> order-placement methods, and live execution stays behind the
> `CLAUDE.md §5` Phase 5 gate (`KQ_LIVE=true` + `--live --i-understand-the-risks`).
> Same compliance posture as demo (see `docs/COMPLIANCE-ADDENDUM.md`).

## Why you need this

The Windows/WSL2 box is set up and a demo cron soak is running, but the Kalshi
**demo** environment is a sandbox: it seeds **0 weather markets and 0 NBA/NFL/PGA
markets**. So on demo, every Kalshi-dependent pass (`ingest-kalshi`, `paper`,
`paper-nba`) finds nothing to trade and the Phase 5 settled-trade gates (#1, #4,
#5) cannot accumulate. **Prod read-only is the unlock.** Everything else
(weather/METAR/NDFD ingest, Pinnacle odds) already works and is accumulating.

## Steps (all inside WSL2 Ubuntu, `cd ~/forecast-lab`)

### 1. Create a Kalshi prod API key

On <https://kalshi.com> (real account, logged in):
- Account → **API Keys** → **Create API Key**.
- Kalshi gives you an **API Key ID** (UUID-ish string).
- You provide the **public half** of an RSA keypair. Generate the pair locally:
  ```bash
  openssl genrsa -out /tmp/kalshi_prod.pem 2048
  openssl rsa -in /tmp/kalshi_prod.pem -pubout -out /tmp/kalshi_prod_pub.pem
  ```
  Upload `/tmp/kalshi_prod_pub.pem` to the Kalshi dashboard; keep the private
  `kalshi_prod.pem`. **Kalshi shows the key ID once — copy it now.**

> Note: prod and demo are **separate** keys. The `.pem` currently in
> `secrets/kalshi.pem` is the demo key; do not overwrite it until you've
> confirmed prod works (keep a backup).

### 2. Install the prod private key

```bash
cp /tmp/kalshi_prod.pem ~/forecast-lab/secrets/kalshi.pem
chmod 600 ~/forecast-lab/secrets/kalshi.pem
rm /tmp/kalshi_prod.pem /tmp/kalshi_prod_pub.pem   # clean up the temp copies
```

### 3. Update the API key ID in the encrypted store

```bash
sops secrets.enc.yaml          # opens decrypted; set KALSHI_API_KEY_ID: <prod UUID>
make bootstrap-secrets         # merges it into .env
```
(Editing the encrypted blob keeps both machines in sync once you `git push` it.)

### 4. Flip the environment

Edit `.env`:
```dotenv
KALSHI_ENV=prod
```
The base URL flips `demo-api.kalshi.co` → `api.elections.kalshi.com`
automatically (`src/kq/clients/kalshi/client.py`).

### 5. Verify

```bash
# auth + real markets (expect non-zero during weather season / game days):
uv run python -m kq ingest-kalshi
# weather contracts are seasonal (Nov-Mar strongest); NBA during the season.
```
You should see non-zero `markets:` counts in the structlog output. If you see
`401`, the key ID / `.pem` / env are mismatched (prod key against demo env or
vice-versa).

### 6. Tighten the health-check (optional, recommended)

Once prod is live, `kalshi_book_snap` being empty is a real problem (not a
demo artifact). In `src/kq/flows/health_check.py`, set the kalshi check's
`severity_when_missing="crit"` so the heartbeat escalates. (Code change →
feature branch → PR, per `CLAUDE.md §9`.)

## After the switch

- The existing cron soak immediately starts discovering real markets; paper
  trades begin accumulating toward Phase 5 #1/#4/#5.
- Consider raising the NBA-odds cron cadence back toward the documented hourly
  windows (`docs/SCHEDULED-RUNS.md`) during the season — watch the Odds API
  500/mo free quota (logged as `remaining=` on every `ingest-nba-odds`).
- Re-run `kq state-check --state <your state>` if you've moved; sports-contract
  availability is litigated and changes.
