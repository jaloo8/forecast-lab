-- forecast-lab DuckDB schema.
-- Every feature-bearing table carries `as_of` to prevent look-ahead bias.
-- All timestamps stored in UTC; convert at display layer.

CREATE TABLE IF NOT EXISTS weather_forecast (
    as_of            TIMESTAMP NOT NULL,  -- when the forecast row was pulled
    run_time         TIMESTAMP NOT NULL,  -- model cycle
    model            VARCHAR   NOT NULL,  -- 'gefs' | 'ecmwf' | 'hrrr' | 'gfs'
    member           INTEGER,             -- ensemble member index or NULL for deterministic
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
    rules_text      TEXT
);

CREATE TABLE IF NOT EXISTS kalshi_book_snap (
    snap_time       TIMESTAMP NOT NULL,
    ticker          VARCHAR   NOT NULL,
    yes_bid         DOUBLE,
    yes_ask         DOUBLE,
    yes_bid_size    INTEGER,
    yes_ask_size    INTEGER,
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
    pnl_usd        DOUBLE
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
