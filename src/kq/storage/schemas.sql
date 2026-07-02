-- forecast-lab DuckDB schema.
-- Every feature-bearing table carries `as_of` to prevent look-ahead bias.
-- All timestamps stored in UTC; convert at display layer.

CREATE TABLE IF NOT EXISTS weather_forecast (
    as_of            TIMESTAMP NOT NULL,  -- when the forecast row was pulled
    run_time         TIMESTAMP NOT NULL,  -- model cycle
    model            VARCHAR   NOT NULL,  -- 'gefs' | 'ecmwf' | 'hrrr' | 'gfs'
    -- Ensemble member index; -1 = deterministic run (sentinel). `member` is
    -- part of the PK, and PK columns are implicitly NOT NULL, so the old
    -- "NULL for deterministic" doc was unimplementable — the first
    -- HRRR/GFS-deterministic ingest would crash the batch (2026-07-01
    -- audit, Tier 2). Sentinel keeps the PK (and INSERT OR REPLACE
    -- idempotency) intact; writers must map None -> -1.
    member           INTEGER   NOT NULL DEFAULT -1,
    station          VARCHAR   NOT NULL,  -- 'KLAX', 'KJFK', ...
    valid_date       DATE      NOT NULL,
    forecast_high_f  DOUBLE,
    forecast_low_f   DOUBLE,
    PRIMARY KEY (as_of, model, member, station, valid_date)
);

CREATE TABLE IF NOT EXISTS metar_obs (
    obs_time      TIMESTAMP NOT NULL,
    station       VARCHAR   NOT NULL,
    temp_f        DOUBLE,
    dewpoint_f    DOUBLE,
    wind_kt       DOUBLE,
    pressure_mb   DOUBLE,
    PRIMARY KEY (obs_time, station)
);

-- NWS Daily Climate Report "truth" — what Kalshi weather markets settle on.
-- Pulled from ACIS (NOAA Regional Climate Centers).
CREATE TABLE IF NOT EXISTS weather_observed (
    station     VARCHAR   NOT NULL,
    valid_date  DATE      NOT NULL,
    high_f      DOUBLE,
    low_f       DOUBLE,
    source      VARCHAR   NOT NULL DEFAULT 'nws_acis',
    fetched_at  TIMESTAMP NOT NULL,
    PRIMARY KEY (station, valid_date)
);

CREATE TABLE IF NOT EXISTS kalshi_market (
    ticker          VARCHAR PRIMARY KEY,
    event_ticker    VARCHAR,
    category        VARCHAR,     -- 'WEATHER' | 'NBA' | ...
    settlement_src  VARCHAR,     -- 'NWS daily climate report LAX' | ...
    opens_at        TIMESTAMP,
    closes_at       TIMESTAMP,
    rules_text      TEXT,
    strike_type     VARCHAR,     -- 'greater' | 'less' | 'between' (prod resolution semantics)
    floor_strike    DOUBLE,
    cap_strike      DOUBLE
);

CREATE TABLE IF NOT EXISTS kalshi_book_snap (
    snap_time       TIMESTAMP NOT NULL,
    ticker          VARCHAR   NOT NULL,
    yes_bid         DOUBLE,
    yes_ask         DOUBLE,
    yes_bid_size    DOUBLE,   -- fractional trading on prod (orderbook_fp)
    yes_ask_size    DOUBLE,
    volume_24h      DOUBLE,
    open_interest   DOUBLE,
    PRIMARY KEY (snap_time, ticker)
);

CREATE TABLE IF NOT EXISTS signal (
    signal_id        VARCHAR   PRIMARY KEY,
    as_of            TIMESTAMP NOT NULL,
    ticker           VARCHAR   NOT NULL,
    model_prob_yes   DOUBLE    NOT NULL,
    market_prob_yes  DOUBLE,
    edge_bps         DOUBLE,
    model_name       VARCHAR   NOT NULL,
    source_urls      VARCHAR[],        -- public-data evidence trail
    reasoning        TEXT
);

CREATE TABLE IF NOT EXISTS paper_trade (
    trade_id       VARCHAR   PRIMARY KEY,
    signal_id      VARCHAR   NOT NULL REFERENCES signal(signal_id),
    submitted_at   TIMESTAMP NOT NULL,
    ticker         VARCHAR   NOT NULL,
    side           VARCHAR   NOT NULL,   -- 'BUY_YES' | 'SELL_YES' | 'BUY_NO' | 'SELL_NO'
    limit_price    DOUBLE    NOT NULL,
    qty            INTEGER   NOT NULL,
    fee_usd        DOUBLE    NOT NULL,
    filled_at      TIMESTAMP,
    fill_price     DOUBLE,
    settled_at     TIMESTAMP,
    settlement     VARCHAR,              -- 'YES' | 'NO' | 'VOID'
    pnl_usd        DOUBLE,
    strike_type    VARCHAR,              -- 'greater' | 'less' | 'between' (PR-B; captured at submit)
    floor_strike   DOUBLE,
    cap_strike     DOUBLE
);

CREATE TABLE IF NOT EXISTS settlement (
    ticker       VARCHAR   PRIMARY KEY,
    settled_at   TIMESTAMP NOT NULL,
    outcome      VARCHAR   NOT NULL,  -- 'YES' | 'NO' | 'VOID'
    observed     DOUBLE              -- the underlying (e.g., NWS high_f)
);

-- External NWS-derived Tmax benchmark (NDFD/NBM). Used for Brier-vs-NDFD
-- comparison and CLV-vs-NDFD tracking — see docs/research/NDFD-BENCHMARK-SOURCE.md.
-- v1 ships deterministic-only (forecast_max_f) via Open-Meteo's NBM endpoint;
-- the probabilistic columns (p10..p90) are reserved for the qmd/cfgrib upgrade.
-- `source` is part of the PK so deterministic and qmd rows can coexist.
CREATE TABLE IF NOT EXISTS ndfd_forecast (
    as_of           TIMESTAMP NOT NULL,  -- when we pulled (live) or anchored (historical)
    station         VARCHAR   NOT NULL,
    valid_date      DATE      NOT NULL,
    lead_days       INTEGER   NOT NULL,  -- valid_date - as_of.date(), in days
    source          VARCHAR   NOT NULL,  -- 'nbm_deterministic_openmeteo' (v1) | 'nbm_qmd_s3' (v2)
    forecast_max_f  DOUBLE,
    p10_max_f       DOUBLE,
    p25_max_f       DOUBLE,
    p50_max_f       DOUBLE,
    p75_max_f       DOUBLE,
    p90_max_f       DOUBLE,
    PRIMARY KEY (as_of, source, station, valid_date)
);

-- ----------------------------------------------------------------------------
-- Phase 3 (NBA) — schedule + completed-game results.
--
-- Sourced from `nba_api.stats.endpoints.scoreboardv2` (live) and
-- `leaguegamefinder` (backfill). One row per (game_id, team_id) at the team
-- grain initially? No — one row per game_id with home/away on the same row.
-- Game IDs in the NBA system are stable strings ("0022400123", etc.) so
-- they're a clean PK. Score and `home_won` are NULL until the game finishes
-- (allows pre-tipoff snapshots without requiring a separate "schedule" table).
--
-- Per `docs/research/PHASE-3-NBA-PLAN.md`. NBA Phase 3 work is gated behind
-- Phase 2 ship per CLAUDE.md §5; this schema lands as the starter scaffold
-- so the data layer is ready when Phase 3 kicks off.
CREATE TABLE IF NOT EXISTS nba_game (
    game_id        VARCHAR PRIMARY KEY,    -- "0022400123" — NBA's canonical id
    season         VARCHAR NOT NULL,       -- "2024-25" (fall-year format)
    season_type    VARCHAR NOT NULL,       -- "Regular Season" | "Playoffs" | "Preseason" | "All Star"
    game_date      DATE    NOT NULL,       -- localized US/Eastern game date
    home_team_id   INTEGER NOT NULL,       -- NBA's stable team id (e.g., 1610612747 = LAL)
    home_team_abbr VARCHAR NOT NULL,       -- "LAL", "BOS", ...
    away_team_id   INTEGER NOT NULL,
    away_team_abbr VARCHAR NOT NULL,
    home_score     INTEGER,                -- NULL until the game finishes
    away_score     INTEGER,
    home_won       BOOLEAN,                -- NULL until the game finishes
    fetched_at     TIMESTAMP NOT NULL      -- naive UTC at insert
);

-- NBA player injury status snapshots.
--
-- One row per (player_id, as_of) so we get a time-series of how a
-- player's status moved (Probable -> Questionable -> OUT). Game-day
-- predictions consume the most recent (max as_of) row per player as
-- of T-30min before tipoff.
--
-- Status codes follow the NBA injury-report convention:
--   * 'OUT'         — not playing
--   * 'DOUBTFUL'    — ~25% chance of playing
--   * 'QUESTIONABLE'— ~50% chance of playing
--   * 'PROBABLE'    — ~75% chance of playing (rare in modern reports)
--   * 'AVAILABLE'   — cleared to play (return-from-injury notes)
--
-- v1 ingest: CSV import via `kq ingest-nba-injuries --csv FILE`. The
-- parser layer is designed so a future automated source (nba_api
-- endpoint, official injury-report PDF parse, or the nbainjuries pip
-- package once the dep is signed off per CLAUDE.md §9) drops in
-- cleanly.
CREATE TABLE IF NOT EXISTS nba_injury (
    player_id      VARCHAR   NOT NULL,
    player_name    VARCHAR   NOT NULL,
    team_abbr      VARCHAR   NOT NULL,
    status         VARCHAR   NOT NULL,
    reason         VARCHAR,
    as_of          TIMESTAMP NOT NULL,
    fetched_at     TIMESTAMP NOT NULL,
    PRIMARY KEY (player_id, as_of)
);

-- NBA moneyline odds snapshots from The Odds API v4.
--
-- One row per (odds_api_game_id, bookmaker_key, fetched_at) — every
-- fetch creates a fresh row even for the same game and book, so we get
-- a time-series of how the line moved. The PK is composite to enforce
-- this; queries that want "latest" pick MAX(fetched_at) per
-- (game, book) group.
--
-- The odds_api_game_id is The Odds API's UUID-style identifier — it
-- does NOT match nba_game.game_id (NBA's "0022400123" format). Joining
-- the two tables requires a separate (home_team, away_team, game_date)
-- match because The Odds API doesn't surface NBA's canonical IDs.
-- Phase 3 PR 5 will add that cross-walk; v1 keeps the tables loosely
-- coupled to avoid premature normalization.
CREATE TABLE IF NOT EXISTS nba_odds (
    odds_api_game_id    VARCHAR   NOT NULL,  -- The Odds API's UUID
    bookmaker_key       VARCHAR   NOT NULL,  -- 'pinnacle' | 'betmgm' | ...
    market_key          VARCHAR   NOT NULL,  -- 'h2h' (v1 scope; spreads/totals later)
    home_team           VARCHAR   NOT NULL,  -- "Los Angeles Lakers"
    away_team           VARCHAR   NOT NULL,
    commence_time       TIMESTAMP NOT NULL,  -- naive UTC; game tipoff
    home_decimal_odds   DOUBLE,              -- NULL when the side wasn't quoted
    away_decimal_odds   DOUBLE,
    book_last_update    TIMESTAMP NOT NULL,  -- when the BOOK updated its quote (naive UTC)
    fetched_at          TIMESTAMP NOT NULL,  -- when WE pulled the row (naive UTC)
    PRIMARY KEY (odds_api_game_id, bookmaker_key, market_key, fetched_at)
);

-- nba_game <-> nba_odds bridge built by the deterministic 3-tuple
-- matcher in `kq.models.nba_crosswalk`. One row per matched pair.
-- Both the (odds_api_game_id) and (nba_game_id) columns are foreign-key
-- shaped (we don't enforce FK constraints — DuckDB allows out-of-order
-- inserts and we want the matcher to land before the odds ingest does
-- without blocking on referential integrity).
--
-- Rebuild semantics: the matcher is deterministic over (odds_games,
-- nba_rows), so re-running the flow with the same inputs is a no-op.
-- INSERT OR REPLACE on the PK keeps re-runs idempotent; mismatched
-- columns (team abbreviations, game date) update on conflict so a
-- corrected nba_game row eventually heals the bridge.
CREATE TABLE IF NOT EXISTS nba_game_crosswalk (
    odds_api_game_id    VARCHAR PRIMARY KEY, -- one Odds API game points to at most one NBA game
    nba_game_id         VARCHAR NOT NULL,    -- "0022400123" — NBA's canonical id
    home_team_abbr      VARCHAR NOT NULL,    -- "LAL", "BOS", ... (denormalized for query convenience)
    away_team_abbr      VARCHAR NOT NULL,
    game_date           DATE    NOT NULL,    -- US/Eastern game-date (matches nba_game.game_date)
    matched_at          TIMESTAMP NOT NULL   -- naive UTC when the matcher upserted this row
);
