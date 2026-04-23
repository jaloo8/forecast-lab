# Kalshi Prediction Market Forecasting Tool — Feasibility & Build Plan

*A candid research report for a GPU-performance engineer building a Kalshi weather + NBA trading system with paper trading first, potentially evolving into a subscription product.*

> **Note:** Section A-Compliance of this report has been superseded in part by [`docs/COMPLIANCE-ADDENDUM.md`](../COMPLIANCE-ADDENDUM.md). Read the addendum alongside the Compliance subsection of §1e.

---

## PART 1 — REALISTIC EDGE / FEASIBILITY ANALYSIS

### 1a. Kalshi market mechanics and microstructure

**Regulatory status and settlement.** Kalshi is a CFTC-regulated Designated Contract Market (DCM). Contracts are binary: $1.00 if the event resolves YES, $0.00 if NO; prices range $0.01–$0.99 and are interpretable as probabilities. Weather markets settle on the **NWS Daily Climate Report** for specific airport stations (e.g., LAX, Central Park, Chicago Midway) using **local standard time**, which matters during DST because the "day" is 1 AM–12:59 AM local time, not midnight–midnight ([Kalshi Weather Markets Help](https://help.kalshi.com/markets/popular-markets/weather-markets)). Sports markets resolve on the final score per league rules.

**Fees (the first thing that kills retail edge).** Taker fee = `ceil(0.07 × C × (1-C) × N × 100) / 100` per contract; maker fee is ~25% of that. Fee peaks at $0.0175/contract for $0.50 contracts (3.5% taker, ~0.88% maker), and drops toward a penny at extremes. Round-trip taker cost on a 50¢ contract is $0.035 = **3.5% of notional per side, 7% round-trip at midprice** ([Market Math fee calculator](https://marketmath.io/platforms/kalshi); [Polytrage fee analysis](https://blog.polytrage.com/kalshis-fee-structure-explained/); [pm.wiki fee guide](https://pm.wiki/learn/kalshi-fees-explained); [official Kalshi fee schedule](https://kalshi.com/fee-schedule)). **Implication:** near 50¢ you need ~3.5 percentage points of edge just to break even as a taker; at 20¢/80¢ the fee is a penny, so extremes are dramatically cheaper. **A serious bot should bias toward (a) posting maker orders, and (b) trading at non-coinflip prices.**

**Order book and API.** Kalshi runs a CLOB with REST + WebSocket, authenticated via RSA-PSS signed requests with an API key ID and private key ([Kalshi API docs](https://docs.kalshi.com/api-reference/market/get-markets); [kalshi-python on PyPI](https://pypi.org/project/kalshi-python/)). Position limits are reported around **$25,000 per market** for most categories ([Market Math](https://marketmath.io/platforms/kalshi)), far above a starting retail bankroll. Kalshi pays up to ~4% APY on idle cash balances ([Monaco CPA](https://www.monacocpa.cpa/post/prediction-market-taxes-kalshi-polymarket-robinhood)).

**Liquidity realities.**
- **Weather markets** (the `KXHIGHNY`, `KXHIGHCHI`, `KXHIGHMIA`, `KXHIGHLAX`, `KXHIGHDEN`, `KXHIGHAUS` series for daily high temps) are thinner than headline political/sports markets. Spreads are often 1–3¢ on center brackets during the trading day but can widen to 5¢+ on tail buckets. Daily volumes per bracket are generally **low three figures to low four figures in contracts**; market depth inside the BBO is usually 10–200 contracts. This is a real constraint: retail size ($100–$500 per trade) is fine, but putting on $5k in a single bracket will move the market.
- **NBA markets** are Kalshi's largest category by revenue — **sports constituted ~90% of site activity and 89% of 2025 revenue** ([Wikipedia: Kalshi](https://en.wikipedia.org/wiki/Kalshi)). Moneyline markets on primetime games and playoff games are the deepest; totals and player props are thinner. NBA playoff moneylines routinely trade millions in notional per game.
- **Known market-maker presence.** Kalshi is believed to have professional MMs (Susquehanna has been publicly linked to prediction-market making, and Kalshi has institutional-grade API/co-located infrastructure). Most sports moneylines appear to be within 1–2¢ of Pinnacle's vig-free line for liquid games. Assume sharp action is present and efficiently closing obvious gaps within seconds on major markets.

**Legal landscape (as of April 2026).** Kalshi is entangled in lawsuits with Massachusetts, Nevada, Ohio, Arizona, and Washington over whether sports event contracts are gambling vs. CFTC-regulated derivatives, with mixed rulings (Massachusetts and Ohio ruled against; Tennessee ruled in Kalshi's favor; Nevada issued a restraining order) ([Wikipedia: Kalshi legal disputes](https://en.wikipedia.org/wiki/Kalshi)). Geofencing is being implemented state-by-state. **Check state availability before building automated sports trading; if you are not in a permitted state, this entire part of the project is moot.**

### 1b. Weather markets — where is the edge?

**Data sources (free vs. paid).**
- **NOAA NOMADS / AWS Open Data GEFSv12** — 31-member Global Ensemble Forecast System, 0.25° resolution, 4 runs/day, free via S3/NOMADS GRIB2 ([NOAA GEFS on AWS](https://registry.opendata.aws/noaa-gefs/); [NOAA NCEP GEFS product page](https://www.nco.ncep.noaa.gov/pmb/products/gens/)).
- **Open-Meteo Ensemble API** — free (non-commercial), returns GEFS (31 members), ICON-EPS, GFS, ECMWF IFS/AIFS (since Oct 2025 open-data), HRRR for US, JMA — pre-decoded to JSON, trivial to use ([Open-Meteo Ensemble](https://open-meteo.com/en/docs/ensemble-api); [Open-Meteo GFS/HRRR](https://open-meteo.com/en/docs/gfs-api); [Open-Meteo ECMWF](https://open-meteo.com/en/docs/ecmwf-api)).
- **HRRR** (NOAA) — 3-km rapid-refresh, US only, hourly updates, excellent for same-day nowcasting; accessible via NOMADS or AWS.
- **METAR observations** — real-time hourly airport observations (the settlement stations are all airports). These are the nowcast gold mine: by 2–3 PM local you often know the daily high within 1°F.
- **GEFS reforecast 2000–2019** (free via AWS) for historical bias correction training ([NOAA PSL GEFSv12 reforecast](https://psl.noaa.gov/forecasts/reforecast2/)).
- **Paid**: ECMWF direct (now mostly obsolete since Oct 2025 open-data), DTN/MeteoGroup, Tomorrow.io. You don't need them for v1.

**State of the art for probabilistic "high temp exceeds X" questions.** A well-calibrated 31-member GEFS ensemble with historical bias correction (e.g., **Non-Homogeneous Gaussian Regression / EMOS**) produces probabilistic forecasts that are typically within 1–2% Brier score of the best available commercial products for 1–3 day lead times on well-observed stations. For CONUS, blending GEFS + ECMWF EPS + HRRR (same-day) has measurable skill over any single model. Peer-reviewed literature on ensemble post-processing (Gneiting, Raftery, Hamill) supports that **bias-corrected ensembles are better-calibrated than raw ensembles**, and that the NWS public forecast is often already close to a human-adjusted consensus of these models.

**Is there edge on Kalshi weather markets?**
- **Yes, modestly, and primarily intraday.** The most documented retail edge is **nowcasting with METAR observations** once the observed temperature is close to the bracket boundary. If by 2 PM LAX reads 82°F and the market is still pricing "High ≥ 80°F" at $0.72, the answer is usually "almost certainly yes" — this is a real edge until the market absorbs the observation ([kalshiweatheredge.com claims ~85-90% win rate on same-day trades](https://www.kalshiweatheredge.com/)). **Treat vendor-stated win rates with skepticism** — they are marketing claims, not audited.
- **Day-ahead and 2–5 day edge is harder.** Open-source bots claiming "~8% edge threshold" with Kelly sizing exist ([suislanchez/polymarket-kalshi-weather-bot on GitHub](https://github.com/suislanchez/polymarket-kalshi-weather-bot), reportedly ~$1.8k lifetime P&L on a paper/small-real-money basis). This suggests the edge is real but small and capacity-constrained. A reasonable prior: **on center brackets, you're competing with people running the same ensemble math; on tails, you may find 2–5% edges that round-trip after fees.**
- **The Kalshi newsletter itself acknowledges** that markets "usually (but not always)" price the forecasted high in center brackets, and that traders tend to "value certainty before they should" — i.e., implicit admission that mispricing exists on tails ([Kalshi "Trading the weather"](https://news.kalshi.com/p/trading-the-weather)).
- **Known inefficiencies**: (1) tails get over-discounted; (2) during unusual conditions (wildfire haze, marine layer, cold front timing), retail consensus lags; (3) DST/local-standard-time edge-case rules are occasionally mispriced by new traders.

**Honest assessment.** A retail builder using free GEFS + ECMWF + HRRR + METAR data, correctly bias-corrected, with disciplined limit orders and fee-aware execution, can probably generate **somewhere between 2% and 10% ROI on turnover** in weather markets. At a $5k bankroll churning $50k–$100k of turnover per season, that's $1k–$10k gross, minus infrastructure, minus realized taxes, minus the fact that the edge shrinks as more people run this same playbook. **The business is capacity-constrained: position limits + liquidity cap absolute profit.** It is a worthwhile learning project and possibly worthwhile side income; it is not a path to quitting NVIDIA.

### 1c. NBA markets — where is the edge?

**Data sources.**
- **`nba_api`** (swar/nba_api) — official stats.nba.com wrapper, Python 3.10+, still actively maintained, covers play-by-play, box scores, rosters, advanced stats ([swar/nba_api](https://github.com/swar/nba_api)).
- **`nbainjuries`** — package wrapping NBA's official injury report (15-min/hourly snapshots since 2021–22) ([mxufc29/nbainjuries](https://github.com/mxufc29/nbainjuries)). This is significantly higher quality than scraping Rotoworld.
- **balldontlie.io** — free tier includes `/nba/v2/odds` returning Kalshi, Polymarket, DraftKings, FanDuel, Caesars, BetMGM, BetRivers lines in a normalized schema ([balldontlie NBA prediction markets guide](https://www.balldontlie.io/blog/nba-prediction-markets-comparison/)).
- **The Odds API (the-odds-api.com)** — paid ($10–$119/mo) but includes sharp books like Pinnacle, which Kalshi's balldontlie feed does not.
- **Pinnacle odds** (via OddsPapi, Odds API, or scraping) — the closing line benchmark.
- **Basketball-Reference** — historical game logs, travel distances, Elo priors.

**Known edges in NBA betting.** The literature and pro practitioner consensus:
1. **Closing Line Value vs. Pinnacle is the ONLY reliable long-term edge indicator** ([Pinnacle's own write-up on efficient markets](https://www.pinnacle.com/betting-resources/en/educational/efficient-market-hypothesis-in-sports-betting-why-early-bets-beat-the-market); [Trademate's CLV analysis](https://tradematesports.medium.com/closing-line-value-the-most-important-metric-in-sports-trading-58e56cdb4458)). Pinnacle's closing line is efficient to within ~2% vig in major markets.
2. **NBA moneyline/spread markets are highly efficient**; the edge is in **player props, totals with contextual factors, and live/halftime markets** ([ProbWin CLV guide](https://en.probwin.com/guides/closing-line-value-clv-ultimate-metric-measure-your-edge/)).
3. **Rest/travel/altitude/back-to-back adjustments** produce small but real edges. FiveThirtyEight's CARM-Elo documented: back-to-back = ~46 Elo (~5% win-prob penalty), long travel leg = ~16 Elo (~2%), altitude bonus for Denver/Utah ([FiveThirtyEight NBA methodology](https://fivethirtyeight.com/methodology/how-our-nba-predictions-work/); [how Elo is calculated](https://fivethirtyeight.com/features/how-we-calculate-nba-elo-ratings/)). These are already priced into Pinnacle; the edge is when a soft book (or Kalshi, during a liquidity air pocket) hasn't absorbed them yet.
4. **Injury report timing** — the 5 PM local report the day before, and the ~30-min-before-tip final status updates, create repeatable line-movement windows. Sharp bettors hammer these. Edge = whoever ingests faster with better roster-impact modeling.

**Kalshi vs. sharp books pricing efficiency.** Empirically, Kalshi NBA moneylines on primetime/playoff games hug Pinnacle closely, often within 1–2¢ (1–2% implied prob). Mispricings concentrate in: (a) early-morning after-news windows before Kalshi market-makers wake up, (b) lower-liquidity player prop and margin markets, (c) halftime/live markets with sticky bids. On less-watched games (back half of back-to-backs, midseason weeknight matchups), Kalshi can be 3–5¢ off Pinnacle.

**LLM/sentiment for NBA.** The sports-ML systematic review ([arXiv 2410.21484](https://arxiv.org/html/2410.21484v1)) finds sentiment analysis has produced *some* accuracy lift in niche sports (cricket, soccer) but is **dwarfed by structured features** (rest, injury, pace, eFG%, DRtg). An LLM-benchmark study of sports betting found LLM probability outputs are inconsistently calibrated and domain-dependent ([evaluating LLM reasoning through sports betting](https://michaeltimbs.me/blog/evaluating-llm-reasoning-through-sports-betting/)). SportQA (arXiv 2402.15862) shows GPT-4 trails domain experts by 30–65% on complex reasoning tasks. **Honest read: LLM-direct-probability for NBA is underwhelming; LLM as an extractor (parsing injury-report text, summarizing beat-writer tweets, extracting lineup changes) is useful and defensible.**

**Realistic NBA edge for a retail builder.** Beating Pinnacle in liquid NBA markets is almost impossible. Beating Kalshi *relative to Pinnacle* during short windows (news, pre-open, pre-tip) is plausible. Beating DraftKings/FanDuel via cross-book arbitrage or +EV vs. Pinnacle is an established path (this is what most "sharp" retail bettors actually do). **Expect 1–5% ROI on turnover in NBA if you execute well; zero or negative if you don't.**

### 1d. LLM-augmented trading — what actually works vs. what is hype

**Honest academic read.**
- Sentiment analysis of Reddit/Twitter via LLM has **measurable signal in equity markets for retail-driven names**, but results are inconsistent; most papers that claim large edges do not replicate (survivorship bias in what gets published, look-ahead bias in scraping historical posts that reflect hindsight).
- For **sports**: LLM sentiment adds minor lift at best; structured features dominate. The IEEE soccer-betting paper ([ieeexplore.ieee.org/abstract/document/11415979](https://ieeexplore.ieee.org/abstract/document/11415979/)) shows small improvements when LLM sentiment is added to GBM baselines — single-digit percentage gains in accuracy, not a profit-generating windfall.
- **For weather**: there is essentially no academic claim that Twitter sentiment improves temperature forecasts. The information edge is in physics-based models + observations.

**Where LLMs genuinely add value in this project:**
1. **Structured extraction** from injury reports, beat-writer tweets, press conferences — LLMs are excellent at turning "questionable with a sore hamstring, game-time decision" into `{player: X, status: Q, reason: soft_tissue, game_time_decision: true}`.
2. **Summarization** of overnight news feeds into a trader briefing.
3. **Feature engineering glue** — writing code to pull/clean/join datasets.
4. **Market rule parsing** — Kalshi market rules text is variable; LLMs are great at extracting the settlement source, cutoff time, and tiebreak language.
5. **Coding assistant** (Claude Code itself).

**Where LLMs fail:**
- **Direct probability estimation** is famously miscalibrated. Don't ask "what's the probability Lakers win?"; ask an Elo/ML model.
- **Numerical reasoning on live data** — LLMs will hallucinate box scores and stats without tool use.
- **Market timing / execution** — LLMs don't understand microstructure or order-book dynamics.

**Known pitfalls to avoid:**
- **Look-ahead bias**: any LLM trained on post-event data has "seen" the outcome. Backtesting LLM features on historical games where the model was trained after 2024 is contaminated.
- **Hallucinated data**: LLMs will confidently invent injuries, trades, stats. Always tool-call to authoritative sources.
- **Overfitting in backtests**: with ~1,200 NBA regular season + playoff games per season and weather markets producing a few hundred outcomes per year per city, your sample size is small. Any model with >~5-10 hyperparameters is probably overfit.
- **Survivorship bias in claimed success stories**: the bots with GitHub stars have cherry-picked P&L windows.

### 1e. Honest ceiling analysis

**Realistic annual return range, $3–5k bankroll, competent execution:**
- **Pessimistic (most likely)**: -5% to +5% after fees and taxes in Year 1. Most retail "edge" evaporates once real execution and variance hit.
- **Base case (decent work)**: +5% to +15% ROI on bankroll. Weather same-day + NBA cross-book arb + news-window trading.
- **Good case**: +20% to +40%. Requires meaningful sophistication (calibrated ensembles, fast execution, disciplined bankroll).
- **Optimistic (lucky + skilled)**: +50%+. Do not plan around this; if it happens, save it.

**Sample size math.** To distinguish a 3% edge from zero at p=0.05 on binary bets near 50¢, you need roughly **N ≈ (1.96/0.03)² ≈ 4,300 independent bets**. At 5–10 bets/day across weather + NBA, that's 1–2 years of data. **Don't trust any backtest or paper-trading result with N < ~500, and be skeptical until N > 1,500.** Use **Brier score** and **reliability diagrams** as your primary calibration checks, not P&L.

**Compliance / legal considerations.**

> **See [`docs/COMPLIANCE-ADDENDUM.md`](../COMPLIANCE-ADDENDUM.md) — it supersedes the blanket-blacklist framing in an earlier draft. The corrected frame is: public-data equity trading is lawful; restrictions are ticker-specific and information-specific. The items below remain relevant as a checklist of topics to confirm with counsel.**

1. **NVIDIA Insider Trading Policy** applies to all employees. Blanket prohibitions include trading NVDA derivatives, hedging NVDA, shorting NVDA, margin, pledging, and (at all times) insider trading on any company where you possess MNPI ([NVIDIA Insider Trading Policy, SEC filing](https://www.sec.gov/Archives/edgar/data/1045810/000104581025000023/nvda-2025xex191.htm)). Kalshi weather and NBA contracts are **not NVDA securities and not traditional equities**, so the core blanket prohibitions don't reach them.
2. **Outside/personal trading pre-clearance** — many tech cos require pre-clearance for derivatives/futures-like accounts. Confirm with NVIDIA HR.
3. **Tax treatment is unsettled.** Some CPAs argue Kalshi contracts are §1256 contracts (60/40 long-term/short-term, mark-to-market) because Kalshi is a CFTC DCM; others argue they are ordinary-income or short-term capital because CFTC has classified binary event contracts as "swaps," which are excluded from §1256 by IRC §1256(b)(2)(B). The IRS has not issued guidance. **Expect to file Form 6781 or Schedule D depending on advisor's view, and keep your own detailed trade log — Kalshi does not currently issue a 1099-B for event contracts.** ([Camuso CPA](https://camusocpa.com/section-1256-prediction-market-tax/); [Monaco CPA](https://www.monacocpa.cpa/post/prediction-market-taxes-kalshi-polymarket-robinhood); [KPMG](https://kpmg.com/kpmg-us/content/dam/kpmg/pdf/2025/potential-tax-implications-cftc-report.pdf); [BRC CPA](https://www.brc.cpa/2026/02/23/prediction-markets-what-do-taxpayers-need-to-know/)).
4. **State availability.** Sports markets are actively being blocked in MA, NV, OH, AZ, WA as of early 2026. Confirm your state.
5. **Subscription product implications.** Selling signals or "AI quant trading" subscriptions can trigger Commodity Trading Advisor (CTA) registration with NFA/CFTC, Investment Advisers Act issues, state securities law, and possibly state gambling-commission issues for sports picks. **This is a real legal cliff. Consult a securities/commodities lawyer before you charge anyone.**

**What would make this a real business vs. a hobby.**
- Proprietary data (not: GEFS + NBA.com; yes: real-time co-located METAR feeds, proprietary injury-classification models, internal-sentiment corpora).
- Systematic execution infrastructure (latency < 500ms end-to-end, smart order routing, maker-fee capture).
- Proven calibration over 1,500+ bets with positive CLV vs. Pinnacle.
- Clear legal structure (LLC, separate bank, potentially CTA-exempt structure).
- Capacity scaling — a subscription that sells signals, not trades, avoids position-limit caps. But now you're selling forecasts, not edge, and accuracy claims become marketing/legal risk.

---

## PART 2 — STEP-BY-STEP BUILD PLAN + CLAUDE CODE PLAYBOOK

### 2a. Recommended architecture and tech stack

**Language: Python 3.11+.** Your background is Python, all the weather/NBA/Kalshi SDKs are Python, LLM tooling is Python-native, and the performance envelope of this project is nowhere near requiring Rust or C++. For hot paths (GRIB decoding, backtest simulator), use `polars` + `numpy` and `numba` if needed.

**Core components:**
| Layer | Responsibility | Library |
|---|---|---|
| Data ingest | Pull Kalshi, NOAA, NBA feeds | `httpx`, `openmeteo-requests`, `nba_api`, `nbainjuries`, `cfgrib`/`xarray` |
| Storage | Time-series + relational | **DuckDB** for analytics, **SQLite** for ops state, **Parquet** for archival. Defer Postgres until multi-user. |
| Feature store | Point-in-time-correct features | Custom module on top of DuckDB with strict `as_of` timestamps |
| Models | Weather ensemble post-processing; NBA Elo + GBM | `scikit-learn`, `properscoring`, `lightgbm`, maybe `pytorch` later |
| Execution | Kalshi client, order router, paper-sim | **Start with `kalshi-python` SDK**, wrap thin abstraction layer so you can swap to your own client later |
| Scheduling | Cron-like orchestration | **Prefect 2/3** (beats Airflow for a solo dev); fall back to cron + systemd on the Windows box via Task Scheduler for v1 |
| Logging/obs | Structured logs + metrics | `structlog`, `loguru`, Prometheus text export + Grafana (local) |
| Dashboard | Monitoring + research UI | **Streamlit** for v1 (fastest); defer Next.js until commercial |
| API (future) | Subscription product | **FastAPI** when it's time |
| CLI | Ops and manual overrides | **Typer** |
| Tests | Unit + backtest harness | `pytest`, `hypothesis` for property tests |

**Kalshi SDK decision.** Use `kalshi-python` (official, auto-generated from OpenAPI, actively maintained) ([kalshi-python on PyPI](https://pypi.org/project/kalshi-python/)) for v1. Wrap it in your own thin `KalshiClient` interface so when you need custom behavior (maker-only orders, smart retries, WebSocket streaming) you can extend without a fork. Don't roll your own auth/RSA-PSS signing in Week 1 unless you have to.

### 2b. Data pipeline design

**Weather pipeline.**
- **Primary**: Open-Meteo Ensemble API for GEFS (31 members) + ECMWF (51 members) — JSON, no GRIB parsing, free for non-commercial, rate-limited to ~10k calls/day which is plenty ([Open-Meteo Ensemble docs](https://open-meteo.com/en/docs/ensemble-api)).
- **Secondary (when you outgrow Open-Meteo)**: direct NOAA NOMADS / AWS S3 GEFS GRIB2 via `cfgrib`+`xarray` ([NOAA GEFS on AWS](https://registry.opendata.aws/noaa-gefs/)).
- **Nowcast**: METAR observations from aviationweather.gov or synoptic data providers; poll every 5–10 min during the trading day.
- **Historical training**: GEFSv12 reforecast on AWS (2000–2019) + Open-Meteo Historical Forecast API (2021+) for bias-correction training ([Open-Meteo Historical Forecast](https://open-meteo.com/en/docs/historical-forecast-api); [Open-Meteo Previous Runs](https://open-meteo.com/en/docs/previous-runs-api)).
- **Settlement ground truth**: NWS Daily Climate Report via XMACIS / ACIS web services; this must exactly match Kalshi's resolution source.

**Schema (simplified).**

```sql
CREATE TABLE weather_forecast (
    as_of TIMESTAMP,            -- when the forecast was pulled (no look-ahead)
    run_time TIMESTAMP,         -- model cycle
    model VARCHAR,              -- 'gefs', 'ecmwf', 'hrrr', 'gfs'
    member INTEGER,             -- ensemble member index or NULL
    station VARCHAR,            -- 'KLAX', 'KJFK', etc.
    valid_date DATE,
    forecast_high_f DOUBLE,
    forecast_low_f DOUBLE,
    PRIMARY KEY (as_of, model, member, station, valid_date)
);

CREATE TABLE metar_obs (
    obs_time TIMESTAMP,
    station VARCHAR,
    temp_f DOUBLE,
    ...
);

CREATE TABLE kalshi_book_snap (
    snap_time TIMESTAMP,
    ticker VARCHAR,
    event_ticker VARCHAR,
    yes_bid DOUBLE, yes_ask DOUBLE,
    yes_bid_size DOUBLE, yes_ask_size DOUBLE,
    volume_24h DOUBLE, open_interest DOUBLE,
    ...
);
```

**Key discipline: every row has an `as_of` timestamp.** This is how you prevent look-ahead bias at backtest time.

**NBA pipeline.**
- `nba_api` for schedule, box scores, play-by-play, advanced team stats ([swar/nba_api](https://github.com/swar/nba_api)).
- `nbainjuries` for official injury reports at hourly granularity ([mxufc29/nbainjuries](https://github.com/mxufc29/nbainjuries)).
- `balldontlie` for cross-book odds (free tier) — Kalshi, Polymarket, DraftKings, FanDuel, Caesars, BetMGM, BetRivers ([balldontlie NBA odds docs](https://www.balldontlie.io/blog/nba-prediction-markets-comparison/)).
- The Odds API for Pinnacle (if budget allows — Pinnacle is the benchmark).
- Basketball-Reference scrape for historical Elo priors and travel distances.

**Kalshi pipeline.**
- REST: market discovery (`/markets`), order book (`/markets/{ticker}/orderbook`), fills, portfolio.
- WebSocket: subscribe to order book updates and fills on markets you care about; much lower latency than polling.
- Auth: RSA-PSS with API key ID + private key (store in macOS Keychain locally, `.env`-encrypted on the Windows box, never in the repo).
- Snapshot the full book every N seconds for markets in your universe; store to Parquet daily.

**Sentiment in v1: NO.** Explicit non-goal. Add it in v2 after you have calibrated baselines. The risk of garbage features polluting your model is high, and the signal-to-noise is low per §1d.

### 2c. Modeling approach for v1

**Weather v1 baseline: NGR/EMOS-bias-corrected GEFS ensemble.**
1. Pull last N days of GEFS 31-member forecasts and NWS-verified highs for the 4–6 cities Kalshi lists.
2. For each station × lead time, fit Non-homogeneous Gaussian Regression: `T_obs ~ N(a + b * ens_mean, c + d * ens_var)`.
3. At prediction time, produce a calibrated Gaussian (or empirical CDF from members) and compute `P(T > threshold)` for every Kalshi bracket.
4. Blend with ECMWF EPS (if available) and HRRR (for same-day, 0–24h).
5. As the trading day progresses, fold in METAR observations using a simple Bayesian update (observed-so-far constrains the remaining day's max).
6. Compare model probability to Kalshi bid/ask; trade only when `|edge| > threshold` after-fee, where threshold is at least 3% for taker and 1% for maker on center prices, wider at extremes.

**Do NOT start with ML on top.** Add gradient boosting (LightGBM) for residual correction only after the baseline is calibrated and backtested over 500+ events. More features → more overfitting.

**NBA v1 baseline: Pinnacle-anchored + Elo fallback.**
- Primary model: **vig-free Pinnacle implied probability** is your "truth" for major markets. Trade Kalshi when Kalshi's bid/ask is materially off Pinnacle vig-free fair, accounting for fees.
- If Pinnacle unavailable: **FiveThirtyEight-style Elo** (base 1300, K adjusted for margin of victory, home-court ~100 Elo, back-to-back -46 Elo, travel penalty, altitude bonus) ([FiveThirtyEight methodology](https://fivethirtyeight.com/methodology/how-our-nba-predictions-work/); [CARM-Elo write-up](https://fivethirtyeight.com/features/how-our-2015-16-nba-predictions-work/)). This gets you to within ~51–52% against-the-spread accuracy before injury adjustments.
- Layer on injury impact (starter out = -X% win probability per Basketball-Reference Win Shares priors).
- Kelly sizing: **fractional Kelly (0.15–0.25x)** — full Kelly is reckless, especially with model uncertainty.

**When to introduce LLMs (after v1 ships):**
- Parse injury report free-text into structured fields (reason, severity, expected return).
- Summarize beat-writer tweets / pressers into structured lineup signals.
- Parse Kalshi market rules into structured settlement spec (critical for avoiding resolution-source mistakes).
- NEVER use an LLM as the final probability estimator. Always feed its outputs as features into a calibrated model.

**Calibration testing — non-negotiable.**
- Primary metric: **Brier score** (binary probability forecast error).
- **Reliability diagram**: plot predicted vs. observed frequency in 10 buckets. If your 70% bucket wins 55% of the time, you're miscalibrated and should not trade live.
- Secondary: **log loss**, **CRPS** for continuous weather forecasts.
- Tertiary: **CLV vs. Pinnacle** for NBA.
- `properscoring` library handles Brier/CRPS.

### 2d. Backtesting and paper trading

**Realistic backtest rules:**
1. **Point-in-time data only.** Use `as_of ≤ signal_time` for every feature. No exceptions.
2. **Slippage**: assume you get the worse of (displayed ask + 1¢, midpoint) for taker; assume 70% fill probability on maker limits placed at BBO, lower as you cross inside the spread.
3. **Fees**: apply Kalshi's formula explicitly per leg. `ceil(0.07 * C * (1-C) * 100) / 100` for takers, 25% for makers.
4. **Position sizing**: fractional Kelly at 0.15x, capped at 2–5% of bankroll per trade.
5. **Market hours / settlement**: weather markets close at 3 PM ET the day of settlement (verify on each market); NBA at tipoff for moneylines, various for props.
6. **Sample size guardrail**: require N ≥ 200 before reporting a strategy; require N ≥ 500 before real money.

**Red flags in backtests:**
- Sharpe > 3 on small N.
- Monotonic equity curve with no drawdowns.
- Best on the exact backtest window but degrades when you extend it 3 months.
- More than ~3% improvement from adding any single "clever" feature — usually overfit.
- Fill rate assumptions above 80% for limit orders at BBO.
- Results that depend on one or two outlier trades.

**Paper trading rigor.** Paper-trade for **at least 200 settled bets OR 3 months, whichever is longer**, tracking: realized P&L, Brier score, CLV vs. Pinnacle (for NBA) and vs. GEFS ensemble mean (for weather), fill rate on maker orders, latency from signal to order.

### 2e. The playbook

The canonical operating playbook lives at [`CLAUDE.md`](../../CLAUDE.md) in the repo root. It is the day-to-day source of truth for phases, exit criteria, coding standards, prompting patterns, and guardrails.

### 2f. Pitfalls specific to this project

1. **Look-ahead bias in weather backtests.** The GEFS forecast "for today" that you see on Open-Meteo right now was published at a specific cycle (00/06/12/18 UTC). A Kalshi market that was tradable at 9 AM local could only use forecasts from runs issued ≤ 9 AM. The Open-Meteo Historical Forecast API aligns to first-hour forecasts — useful but not the same as what was tradable in real time. Cross-check against the **Previous Runs API** which preserves lead-time offsets ([Open-Meteo Previous Runs](https://open-meteo.com/en/docs/previous-runs-api)). **Always filter by `forecast_run_time ≤ signal_time - forecast_latency_minutes`.**
2. **Kalshi settlement edge cases.**
   - **DST**: weather markets use local standard time, so "day" is 1 AM–12:59 AM during DST ([Kalshi Weather Markets Help](https://help.kalshi.com/markets/popular-markets/weather-markets)).
   - **Missing observation**: if the airport sensor fails, Kalshi may use backup data per rules text; parse rules per market.
   - **NBA postponement/OT**: check whether market resolves on game-as-postponed, by regulation, or voids. Rules text varies.
   - **Early close/fractional trading**: some markets enable early close and fractional contracts; your executor must handle both.
3. **LLM misuse risk.** If Claude Code is allowed to "help" with predictions, it will produce plausible but miscalibrated probabilities. Constrain LLM to code + structured extraction + rule parsing. Never wire an LLM's numeric output directly into a bet-size function.
4. **Scope creep.** You mentioned three products (Kalshi bot, equities research, autonomous research agent). The 3x multiplier on scope is where solo projects die. **v1 = Kalshi weather + NBA paper trading only.** Write "NOT IN v1" on every door.
5. **When paper trading shows edge — how to size up responsibly.**
   - **Edge fades.** A 5% edge in backtest often becomes 2% live and 0% after 6 months of others finding the same trade.
   - **Tier the ramp.** After passing Phase 5 gate: month 1 live at 10% of intended bankroll, month 2 at 25%, month 3 at 50%, month 4 at 100% — only if each month's live Brier and CLV match paper within tolerance.
   - **Hard kill-switches.** Coded caps: daily loss > 3% of bankroll = halt; weekly loss > 8% = halt; 10 consecutive -CLV trades = halt and review.
   - **Review cadence.** Weekly: P&L, Brier, CLV. Monthly: full calibration re-fit. Quarterly: full strategy review with a written memo.
6. **Compliance framing.** See [`docs/COMPLIANCE-ADDENDUM.md`](../COMPLIANCE-ADDENDUM.md) for the corrected framing (public-data baseline; narrow ticker-and-information specific restrictions; no blanket blacklist).
7. **Subscription product trap.** Selling picks/signals publicly may require CTA registration (NFA) or trigger state gambling advertising rules. Don't charge anyone until a commodities attorney has cleared the structure. A "free-tier dashboard" public on GitHub is fine; a paywall is a different legal animal.

---

## RESEARCH PASS 2 PROMPT (as originally issued)

> *This prompt was run and produced [`PASS-2-EQUITIES-AGENT.md`](PASS-2-EQUITIES-AGENT.md). Preserved here for traceability.*

Conduct deep follow-up research for the same user (software engineer at NVIDIA, GPU performance, strong Python, Cursor/Claude Code, M1 Pro + always-on Windows PC) who is extending the Kalshi weather + NBA prediction-market project described in Research Pass 1. The user has now digested Pass 1 and wants two additional research areas covered with the same opinionated candor and citation rigor. Do not sugar-coat; apply the lens of a professional quant researcher, infrastructure engineer, and business operator.

**PART A — EQUITIES EXPANSION & TECH-SECTOR CROSS-INDUSTRY SIGNALS**

A1. **OpenBB / open-source Bloomberg alternatives.** Evaluate OpenBB Platform, OpenBB Terminal Pro, and alternatives (Financial Modeling Prep, Tiingo, EODHD, Alpha Vantage, Polygon.io, Finnhub, IEX Cloud successor, TwelveData, databento). For each: data coverage (equities OHLCV, fundamentals, options chains, short interest, insider transactions, 13F, news, transcripts), pricing tiers, API quality, Python SDK maturity, licensing (commercial-use OK?), latency, historical depth. Be specific about what Bloomberg has that these do not, and where free/cheap stacks genuinely substitute vs. merely approximate.

A2. **CEO / succession / key-person tracking.** What structured data sources exist for tracking CEO changes, board changes, C-suite transitions, succession planning disclosures, and key-person risk across publicly traded tech companies? Evaluate: SEC Form 8-K item 5.02 feeds (official source), BoardEx, Equilar, SmartInsider, InsiderScore, Datastream, Refinitiv Workspace, and any open-data alternatives. How do quants actually encode this as a feature (event-study returns, bias/momentum signals)? Cite research on CEO-transition alpha.

A3. **Fundamentals APIs for US equities.** Compare Financial Modeling Prep, Tiingo, SimFin, SEC EDGAR direct XBRL (free but raw), Stock Analysis API, Polygon fundamentals, Yahoo (unofficial). Focus on: point-in-time fundamentals (critical — as-reported vs. restated), normalized field coverage, restatements handling, segment data, guidance/consensus (IBES-style), ESG, insider transactions. Which of these provides clean point-in-time data that won't create look-ahead bias in backtests?

A4. **Tech-sector cross-industry signal tracking.** The user wants to systematically track signals that propagate across the tech supply chain (e.g., TSMC guidance → NVIDIA / AMD / Apple implications, hyperscaler capex → NVIDIA / AVGO / MRVL, semicap → ASML / AMAT / LRCX / KLAC). Research: (a) supply-chain mapping data sources, (b) alternative data for semi/hyperscaler, (c) existing academic research on cross-sectional momentum / lead-lag within tech, (d) conference-call transcript NLP for supply-chain mentions.

**PART B — ALWAYS-ON AUTONOMOUS RESEARCH AGENT ARCHITECTURE** — frameworks, memory, orchestration, observability, model strategy, security, reference architecture. (See Pass 2 report for full prompt body.)

**Format requirements:** two clearly separated parts; specific, opinionated, citation-rigorous; flag uncertainties; end with a Pass 3 prompt.

---

*End of Pass 1. All factual claims about fees, APIs, regulatory status, and data sources are cited above; all claims about edge sizes, ROI ranges, and sample-size thresholds are opinionated estimates grounded in the cited literature and should be independently verified before risking capital.*
