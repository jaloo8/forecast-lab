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
