# Getting started — Kalshi setup

**Looking for the stock research lab?** Start with the [project overview](../README.md) and [Stock Paper Lab runbook](STOCK-PAPER-LAB.md). Stocks are now the active research focus; this guide covers the separate Kalshi application. Its installer does not configure stock captures, the A8 ledger or a stock trading account.

This guide assumes **zero** programming knowledge. If you can install a
game, you can install this. Every gray box below shows **real output**
captured from a real machine — what you see should match it closely.

## What is this thing, in one paragraph?

The Kalshi application forecasts high temperatures (and who
wins NBA games), then compares its predictions with the prices on
**Kalshi** — a website where people bet on real-world events. When the
app's prediction disagrees with the market's price, it makes a
**practice trade with pretend money** and keeps score. If, after hundreds
of practice trades, the app is genuinely better than the market, only then
would real money ever be considered (and that's locked behind multiple
safety switches).

## Install (one command)

First, get the project onto your computer. If someone sent you a folder,
skip to the next step. Otherwise, in a terminal:

```
git clone https://github.com/jaloo8/forecast-lab.git
cd forecast-lab
```

Then run the installer:

| Your computer | Do this |
|---|---|
| **Windows** | Double-click `install.bat` (or run it in a terminal) |
| **Mac / Linux / WSL** | Run `./install.sh` in a terminal |

The installer downloads the tools and walks you through 4 quick steps.
This is what it looks like (real output):

```
Welcome to forecast-lab! Setting you up (about 2 minutes).

Step 1 of 4 - Your database (where all downloaded data lives)
  OK - created: data\forecast_lab.duckdb

Step 2 of 4 - Your settings file (.env)
  OK - created from template: .env

Step 3 of 4 - Kalshi account (optional)
  Kalshi is the prediction-market website this project watches.
  Connecting an account lets the app see live market prices and
  practice-trade with pretend money. Skipping is completely fine -
  everything else works without it.

  How would you like to continue?
    1. I have the project's secret vault key (a small file that
       unlocks the credentials already stored inside this project).
    2. I'll paste my own Kalshi API details.
    3. Skip for now - free mode. (You can rerun `kq setup` later.)
  Type 1, 2, or 3 [3]:

Step 4 of 4 - Checking everything works
  OK - database ready (data\forecast_lab.duckdb)
  OK - settings file ready (.env)
  OK - free mode (no Kalshi account connected)
```

That's it. You're installed.

### About Step 3 (the only step a computer can't do for you)

The app's Kalshi credentials are like a house key: they must **never** be
stored inside the project itself, because the project lives on GitHub and
anything on GitHub can leak. So one small "vault key" file has to be
copied to each new computer **once** — by you, not by git. If you're the
project owner moving to a new machine, copy your `age` key file over (a
USB stick or password manager works), pick option 1, and the wizard
unlocks everything else automatically. Full details: [SECRETS.md](SECRETS.md).

If you don't have any keys: pick option 3. Free mode still does all the
science — it just can't see live Kalshi prices.

## Launch it (like a game)

```
uv run kq dashboard
```

Your web browser opens with the app: current markets, the model's
predictions, practice-trade results, and a data-health panel.
Press `Ctrl+C` in the terminal window to close it.

## Everyday commands

You only ever need three:

| Command | What it does | When |
|---|---|---|
| `uv run kq ingest` | Downloads the latest weather + market data | Daily (or let the scheduler do it) |
| `uv run kq dashboard` | Opens the app in your browser | Whenever you're curious |
| `uv run kq doctor` | Health checkup: "is anything broken or lying to me?" | When something looks off |

Real output from a data download (shortened):

```
$ uv run kq ingest-weather
{"station": "KDEN", "rows": 574, "event": "openmeteo.fetched", ...}
{"station": "KAUS", "rows": 574, "event": "openmeteo.fetched", ...}
{"inserted": 3444, "db": "data\\forecast_lab.duckdb", "event": "weather.ingest_done", ...}
inserted 3444 forecast rows
```

Translation: it fetched 7-day forecasts (dozens of slightly-different
"ensemble members" per city — that spread is how the model measures its
own uncertainty) and saved 3,444 rows into your database.

To see everything the app can do:

```
uv run kq --help
```

## Words you'll run into (plain-English glossary)

| Word | What it actually means |
|---|---|
| **Bracket / market** | One yes-or-no question, like "Will LA's high be 74–75° tomorrow?" You can buy YES or NO. |
| **Ensemble** | The same weather forecast run ~30 times with tiny variations. If all 30 agree, be confident; if they disagree, don't be. |
| **Brier score** | A grade for predictions: 0 is perfect, lower is better. Like golf. |
| **Calibration** | When you say "70% chance," does it actually happen about 70% of the time? If yes, you're calibrated. |
| **Edge** | How much better your predicted probability is than the market's price. No edge → no trade. |
| **Paper trading** | Practice trading with pretend money. Every trade is recorded and scored as if real. |
| **Kelly sizing** | A math rule for how much to bet: more when your edge is big, less when it's small, never everything. |
| **Settlement** | The moment the question's answer becomes official and the trade is scored (e.g., the weather station reports the day's high). |
| **CLV** | "Closing line value" — did you get a better price than the market's final price? A skill check that works even before results land. |
| **NGR** | The statistical recipe that turns raw weather forecasts into calibrated probabilities (fixes each city's known biases). |

## Fixing common hiccups

| You see | It means | Do this |
|---|---|---|
| `router config not found ... run 'kq decide-router' first` | The model hasn't been trained on this machine yet | Run `uv run kq train-weather` then `uv run kq decide-router` (needs historical data — see [SETUP.md](SETUP.md) backfill section) |
| `paper run skipped submit pass: no_kalshi_creds` | No Kalshi account is connected — practice trading is off | Fine in free mode. To connect: `uv run kq setup`, option 1 or 2 |
| `0 markets` from Kalshi commands | Your account points at the empty practice server (`demo`) | In `.env`, `KALSHI_ENV=prod` uses the real site (read-only + paper trading is still pretend money) |
| Red panels in the dashboard's Data health tab | Data downloads have stopped landing | Run `uv run kq doctor` and read its plain-language report |

## Where things live

```
forecast-lab/
├── install.bat / install.sh   <- the installer you already ran
├── .env                       <- YOUR settings (never leaves this computer)
├── data/                      <- your database (grows as data downloads)
├── models/                    <- trained model files + scorecards
├── docs/                      <- everything else, including this file
└── src/kq/                    <- the code
```

## Want more?

- [README.md](../README.md) — the project's front page
- [SETUP.md](SETUP.md) — full setup detail, including the always-on PC
- [SECRETS.md](SECRETS.md) — how credentials move between machines safely
- [ROADMAP.md](../ROADMAP.md) — what's done and what's next
