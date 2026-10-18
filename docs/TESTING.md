# TESTING.md — How we know this works

This doc is the source of truth for "what we test and why." Walk it before every merge. When a new module lands, add a row here in the same PR.

## Philosophy

Three layers, from fastest to slowest:

1. **Unit + property tests** — under `tests/`, run on every `uv run pytest`. Must be green in CI. Cover parsers, math, validation. Use `hypothesis` where input space matters.
2. **Mocked integration tests** — use `httpx.MockTransport` + generated RSA keys to exercise real client code without hitting the network. Also in `tests/` and `pytest`.
3. **Live smoke checks** — one command per flow that hits the real API. Run by hand before a merge that changes a client. Never in CI.

Separately: **edge cases are first-class**. If a malformed payload / rate limit / clock skew could break a production run, there's a test for it. We add edge tests proactively in the same PR as the feature — not "later."

## Running the suite

```bash
uv run ruff check .              # lint
uv run ruff format --check .     # formatting
uv run mypy src/kq               # types (strict)
uv run pytest                    # tests (~1,180)
uv run pytest --cov=src/kq       # with coverage
```

Every one of these must exit 0 before merge. CI enforces all of them (its pytest step runs with `--cov` and the 80% coverage gate).

### Platform coverage

CI runs the suite on **`ubuntu-latest` and `windows-latest`**. Windows is not a
courtesy target — it is becoming the production host (see
[`DEPLOY-WINDOWS.md`](DEPLOY-WINDOWS.md)), and a Linux-only matrix cannot see a
Windows-only break at all: the first run of the suite on a native-Windows host
turned up 23 failures that CI had never had the chance to flag.

Two known platform differences show up in the suite:

- **The shell-script tests need `bash`.** `tests/test_cron_scripts.py` drives
  the ops scripts through `bash` in a subprocess. A module-level
  `pytest.mark.skipif` on `shutil.which("bash")` makes the whole file **skip**
  when bash is not on PATH — the normal case on a native-Windows host. On Linux
  (WSL2 + CI) bash is always present and nothing skips. Before that guard
  existed, a Windows run produced 23 errors from this file alone
  (`FileNotFoundError: [WinError 2]`), which is what a missing interpreter looks
  like when `subprocess` is asked for it. Skips there are expected; errors are a
  regression.
- **GRIB2 paths are Mac/WSL2-only.** `eccodeslib` has no Windows wheels
  (`sys_platform != 'win32'` in `pyproject.toml`). The affected modules import
  lazily and their tests patch `xarray.open_dataset`, so the suite stays green
  on Windows without ever loading eccodes — but the live GRIB2 ingest commands
  cannot run there.

## Per-module testing matrix

Legend: ✅ = covered, ⚠️ = partial/gap, ⬜ = not yet built, 🟡 = live only (no unit surface).

### `kq.clients._http`

| What | Status | Tests |
|---|---|---|
| Happy-path GET returns JSON | ✅ | `test_http_helper.py::test_happy_path_returns_json` |
| Retry on 5xx then succeed | ✅ | `test_retries_then_succeeds` |
| Non-retryable 4xx raises immediately | ✅ | `test_non_retryable_raises_immediately` |
| Exhausts retries → HttpError | ✅ | `test_exhausts_retries_and_raises` |
| Default UA header set | ✅ | `test_user_agent_default_present` |
| **Transport errors (ConnectError, TimeoutException)** | ✅ | `test_http_helper.py::test_transport_error_retries` *(PR #5)* |
| **`max_retries=0` means no retries** | ✅ | `test_zero_retries_still_raises` *(PR #5)* |
| **Custom headers merged correctly** | ✅ | `test_headers_forwarded` *(PR #5)* |

### `kq.clients.kalshi`

| What | Status | Tests |
|---|---|---|
| RSA-PSS signature verifies with public key | ✅ | `test_kalshi_auth.py::test_signature_verifies_with_public_key` |
| Tampered message rejected | ✅ | `test_signature_rejects_tampered_message` |
| `auth_headers` timestamp in ms | ✅ | `test_auth_headers_default_timestamp_is_millis` |
| PEM load rejects non-RSA | ✅ | `test_load_private_key_rejects_non_rsa` |
| Market parser: cents → dollars | ✅ | `test_kalshi_client.py::test_parse_market_canonicalizes_prices_to_dollars` |
| OrderBook: NO → YES-ask normalization | ✅ | `test_parse_orderbook_normalizes_no_side_to_yes_ask` |
| OrderBook: empty sides | ✅ | `test_parse_orderbook_handles_empty_sides` |
| Missing creds → `KalshiCredentialsError` | ✅ | `test_client_refuses_without_api_key`, `test_client_refuses_without_key_file` |
| End-to-end list_markets with auth headers | ✅ | `test_list_markets_end_to_end` |
| End-to-end get_orderbook | ✅ | `test_get_orderbook_end_to_end` |
| **Ladder entries with wrong shape (length ≠ 2)** | ✅ | `test_kalshi_client.py::test_orderbook_malformed_ladder_entries_dropped` *(PR #5)* |
| **Market with null prices** | ✅ | `test_parse_market_handles_null_prices` *(PR #5)* |
| **Market with malformed date strings** | ✅ | `test_parse_market_malformed_dates_become_none` *(PR #5)* |
| Strike built from API fields, all three kinds (recorded prod fixture) | ✅ | `test_strikes.py::test_strike_from_recorded_prod_fixture_all_three_kinds` *(PR-B)* |
| Ticker-vs-API strike disagreement refused | ✅ | `test_strikes.py::test_strike_refuses_ticker_api_disagreement` *(PR-B)* |
| `less` market prices below-mass, not inverted | ✅ | `test_strikes.py::test_less_market_prices_below_mass_not_inverted` *(PR-B)* |
| Ladder probabilities tile to Σp=1 | ✅ | `test_strikes.py::test_full_ladder_probabilities_tile_to_one` *(PR-B)* |
| Settlement and pricing boundaries agree | ✅ | `test_strikes.py::test_settlement_and_pricing_boundaries_agree` *(PR-B)* |
| Live prod read (sanity) | ✅ | `make ingest-kalshi` — verified 60-72 markets/orderbooks on prod (2026-05-30) |

### `kq.clients.openmeteo`

| What | Status | Tests |
|---|---|---|
| Parses fixture payload, row per member | ✅ | `test_openmeteo_client.py::test_parse_payload_produces_rows_per_member` |
| Values align to source members | ✅ | `test_parse_payload_values_align` |
| Control-run promoted to member 0 | ✅ | covered in `_values_align` |
| Empty payload returns no rows | ✅ | `test_parse_empty_payload_returns_nothing` |
| `run_time` rounds to 6h cycle | ✅ | `test_coerce_run_time_rounds_to_cycle` |
| Unsupported model → ValueError | ✅ | `test_unsupported_model_raises` |
| Unknown station → ValueError | ✅ | `test_unknown_station_raises` |
| End-to-end MockTransport | ✅ | `test_fetch_ensemble_end_to_end_with_mock` |
| **Max has member 5, min doesn't (asymmetric members)** | ✅ | `test_openmeteo_client.py::test_asymmetric_members_still_produce_rows` *(PR #5)* |
| **Non-numeric values in member series** | ✅ | `test_non_numeric_member_values_are_none` *(PR #5)* |
| **Missing `daily` key entirely** | ✅ | `test_missing_daily_key_returns_empty` *(PR #5)* |
| Live fetch against real API | ✅ | `make ingest-weather` — verified 3,444 rows on Mac |

#### Historical deterministic backfill (Phase 2 PR A)

| What | Status | Tests |
|---|---|---|
| Parses Historical Forecast API payload | ✅ | `test_historical_forecast.py::test_parse_historical_produces_one_row_per_day` |
| Values align to source daily series | ✅ | `test_parse_historical_values_align` |
| Sentinel `model='gfs_hist'`, `member=0` tagging | ✅ | covered in `_produces_one_row_per_day` |
| Empty `daily` returns no rows | ✅ | `test_parse_historical_empty_daily_returns_empty` |
| Missing max series → None values, still produces row | ✅ | `test_parse_historical_missing_series_falls_back_to_none` |
| End-to-end MockTransport hits historical host + passes dates | ✅ | `test_fetch_historical_end_to_end_with_mock` |
| Reversed date range → ValueError | ✅ | `test_fetch_historical_rejects_reversed_date_range` |
| Unknown station → ValueError | ✅ | `test_fetch_historical_unknown_station_raises` |
| Historical and ensemble rows coexist in PK | ✅ | `test_backfill_weather.py::test_historical_rows_coexist_with_ensemble_in_pk` |
| Flow rejects reversed date range | ✅ | `test_backfill_rejects_reversed_date_range` |
| Live fetch | ✅ | `make backfill-weather START=2025-06-01 END=2025-06-30` — 180 rows verified |

### `kq.clients.acis` (NWS daily-climate truth, Phase 2 PR B)

| What | Status | Tests |
|---|---|---|
| Parses ACIS `data` array happy path | ✅ | `test_acis_client.py::test_parse_payload_happy_path` |
| String coercion: `"76"` → 76.0; missing `"M"` → None | ✅ | `test_parse_acis_value_handles_sentinels` |
| Malformed entries skipped | ✅ | `test_parse_payload_skips_malformed_entries` |
| Non-dict / missing `data` key returns empty | ✅ | `test_parse_payload_on_non_dict_returns_empty`, `test_parse_payload_missing_data_key` |
| End-to-end MockTransport with request-param check | ✅ | `test_fetch_daily_end_to_end_with_mock` |
| Unknown station → ValueError | ✅ | `test_fetch_daily_unknown_station_raises` |
| Reversed date range → ValueError | ✅ | `test_fetch_daily_reversed_range_raises` |
| `insert_observed` round-trip + idempotent | ✅ | `test_backfill_observed.py::test_insert_observed_round_trip` |
| Preserves missing-high sentinel in DuckDB | ✅ | `test_insert_observed_preserves_missing_highs` |
| Empty iterable returns 0 | ✅ | `test_insert_observed_empty_returns_zero` |
| Flow rejects reversed dates | ✅ | `test_backfill_rejects_reversed_date_range` |
| Live fetch | ✅ | `make backfill-observed START=2025-06-01 END=2025-06-10` — 60 rows verified |

### `kq.clients.metar`

| What | Status | Tests |
|---|---|---|
| Celsius → Fahrenheit math | ✅ | `test_metar_client.py::test_c_to_f_known_values`, `test_c_to_f_preserves_precision` |
| slp / altim fallback | ✅ | `test_parse_one_falls_back_from_slp_to_altim` |
| Bad shape rejected | ✅ | `test_parse_one_rejects_bad_shape` |
| Skips bad rows in list | ✅ | `test_parse_payload_skips_bad_rows` |
| Non-list payload returns empty | ✅ | `test_parse_payload_rejects_non_list` |
| Empty stations tuple short-circuits | ✅ | `test_fetch_latest_empty_tuple_short_circuits` |
| End-to-end MockTransport | ✅ | `test_fetch_latest_end_to_end_with_mock` |
| **Numeric field delivered as string** (`"temp": "15.6"`) | ✅ | `test_metar_client.py::test_string_numeric_fields_coerce` *(PR #5)* |
| **Station requested but not in response** | ✅ | `test_missing_station_silently_dropped` *(PR #5)* |
| Live fetch | ✅ | `make ingest-metar` — verified 6 stations on Mac |

### `kq.utils.kalshi_dates` (Phase 1 PR D)

| What | Status | Tests |
|---|---|---|
| settlement_day rejects naive datetime | ✅ | `test_kalshi_dates.py::test_settlement_day_requires_aware_datetime` |
| Accepts any tz-aware input | ✅ | `test_settlement_day_accepts_any_aware_zone` |
| Bounds span exactly 24h | ✅ | `test_settlement_day_bounds_span_24h` |
| Noon UTC maps to same local day (LAX) | ✅ | `test_noon_utc_maps_to_same_day_lax` |
| UTC midnight = previous day on west coast | ✅ | `test_utc_midnight_is_previous_day_at_west_coast` |
| **DST: Kalshi day rolls at 01:00 local-clock** | ✅ | `test_kalshi_day_rolls_at_1am_local_clock_during_dst` |
| LST midnight boundary | ✅ | `test_lst_boundary_exact_lst_midnight` |
| **Spring-forward (2025-03-09) unaffected** | ✅ | `test_dst_spring_forward_unaffected` |
| **Fall-back (2025-11-02) unaffected** | ✅ | `test_dst_fall_back_unaffected` |
| Cross-station same UTC instant | ✅ | `test_different_stations_at_same_utc_instant` |
| bounds round-trip (25 samples/day) | ✅ | `test_bounds_round_trip` |
| bounds end is exclusive | ✅ | `test_bounds_end_exclusive` |
| instant_in_settlement_day true/false | ✅ | `test_instant_in_settlement_day_true_and_false` |
| instant_in_settlement_day rejects naive | ✅ | `test_instant_in_settlement_day_requires_aware` |

### `kq.execution.fees`

| What | Status | Tests |
|---|---|---|
| 50¢ peak fee = $0.02 | ✅ | `test_fees.py::test_fee_at_50_cents_is_175_bps` |
| Extremes (10¢/90¢) = $0.01 | ✅ | `test_fee_at_extremes_is_cheap` |
| Maker < Taker across prices | ✅ | `test_maker_is_cheaper_than_taker` |
| Price out of range (0, 1) rejected | ✅ | `test_rejects_out_of_range_prices` |
| Total fee non-negative, finite (Hypothesis) | ✅ | `test_total_fee_nonneg` |
| Zero qty → zero fee | ✅ | `test_zero_qty_zero_fee` |
| **Rounding at transition prices (0.49/0.50/0.51)** | ✅ | `test_fees.py::test_fee_at_transition_prices_rounds_up` *(PR #5)* |
| **Negative qty raises** | ✅ | `test_total_fee_rejects_negative_qty` *(PR #5)* |

### `kq.execution.kelly`

| What | Status | Tests |
|---|---|---|
| No edge → zero stake | ✅ | `test_kelly.py::test_no_edge_means_zero_stake` |
| Edge produces expected stake | ✅ | `test_edge_produces_positive_stake` |
| Hard cap enforced | ✅ | `test_hard_cap_enforced` |
| Zero bankroll → zero stake | ✅ | `test_zero_bankroll_zero_stake` |
| Stake bounds (Hypothesis) | ✅ | `test_stake_nonneg_and_bounded` |
| Bad probabilities rejected | ✅ | `test_rejects_bad_probabilities` |
| **Fraction out of (0,1] rejected** | ✅ | `test_kelly.py::test_invalid_fraction_rejected` *(PR #5)* |
| **max_stake_usd ≤ 0 rejected** | ✅ | `test_invalid_max_stake_rejected` *(PR #5)* |

### `kq.execution.live`

| What | Status | Tests |
|---|---|---|
| No ack → refused | ✅ | `test_live_gate.py::test_ack_false_refused` |
| Env not set → refused | ✅ | `test_ack_true_but_env_false_refused` |
| LiveExecutor always raises on construction | ✅ | `test_live_executor_always_raises_on_construction` |

### `kq.features.weather` (Phase 2 PR C)

| What | Status | Tests |
|---|---|---|
| FEATURE_COLUMNS schema stability | ✅ | `test_weather_features.py::test_features_schema_is_stable` |
| mean/std/min/max/quantile/range aggregations | ✅ | `test_features_aggregate_correctly` |
| Single-member row → std = 0, range = 0 | ✅ | `test_deterministic_single_member_std_is_zero` |
| Filters by station / date / model | ✅ | `test_filters_by_station_date_model` |
| Null-valued members not counted | ✅ | `test_members_with_null_highs_not_counted` |
| Training-set join computes residuals + lead_days | ✅ | `test_training_set_joins_and_computes_residual` |
| Unobserved rows dropped | ✅ | `test_training_set_drops_unobserved_rows` |
| Empty DB returns empty frame with full schema | ✅ | `test_training_set_empty_when_no_data` |
| ACIS 'M' (null observed) rows excluded | ✅ | `test_observations_with_null_high_excluded` |
| Returns polars DataFrame | ✅ | `test_training_set_returns_polars_dataframe` |
| Live verify: 348 features / 60 training rows | ✅ | manual run against populated DB |

### `kq.models.calibration`

| What | Status | Tests |
|---|---|---|
| Perfect calibration Brier = 0 | ✅ | `test_calibration.py::test_brier_perfect_is_zero` |
| Always-wrong Brier = 1 | ✅ | `test_brier_always_wrong_is_one` |
| Coin-flip Brier ≈ 0.25 | ✅ | `test_brier_coin_flip_model_is_quarter` |
| Reliability bins count matches | ✅ | `test_reliability_bins_count_matches` |
| Shape mismatch raises | ✅ | `test_brier_shape_mismatch_raises` |

### `kq.storage.duckdb_store` + `.repositories.*`

| What | Status | Tests |
|---|---|---|
| `bootstrap` is idempotent | ✅ | `test_storage.py::test_bootstrap_is_idempotent` *(PR #5)* |
| `insert_forecasts` PK collision = replace | ✅ | `test_ingest_weather.py::test_insert_forecasts_is_idempotent` |
| `insert_metar` PK collision = replace | ✅ | `test_ingest_metar.py::test_ingest_round_trip_idempotent` |
| `insert_*` with empty iterable returns 0 | ✅ | `test_storage.py::test_inserts_with_empty_iterable` *(PR #5)* |
| Connect creates parent directory | ✅ | `test_storage.py::test_connect_creates_parent_dir` *(PR #5)* |

### `kq.flows.*`

| What | Status | Tests |
|---|---|---|
| Aggregate: all succeed | ✅ | `test_ingest_all.py::test_all_succeed` |
| Aggregate: Kalshi creds missing → warning, not failure | ✅ | `test_kalshi_credentials_missing_is_warning_not_failure` |
| Aggregate: partial failure collects all results | ✅ | `test_partial_failure_returns_all_results` |
| Aggregate: all-fail invariant | ✅ | `test_all_fail_sets_nonzero_exit` |
| **DB path rejects non-duckdb URL** | ✅ | `test_ingest_weather.py::test_db_path_rejects_other_urls` |

### `kq.__main__` (CLI)

| What | Status | Tests |
|---|---|---|
| `version` prints something | ✅ | `test_cli.py::test_version_command` |
| `--help` references CLAUDE.md | ✅ | `test_help_includes_phase_reference` |
| `kq setup` wizard flow | ✅ | `test_setup_wizard.py` |
| `kq dashboard` launcher / `kq` console script (`uv run kq ...`) | ⚠️ | thin `subprocess`/entry-point wrappers; no dedicated tests yet |

## Live-verification checklist (before any merge that touches a client)

Run these on the Mac; all should exit 0 and produce reasonable log output:

```bash
make ingest-weather                                # expect 3,000+ rows
make ingest-metar                                  # expect 6 rows
make ingest-kalshi                                 # prod: expect ~60-72 markets/orderbooks (12 brackets x 6 cities)
make ingest                                        # aggregate: expect 4/4 OK (weather, metar, ndfd, kalshi)
make backfill-weather START=2025-06-01 END=2025-06-30   # expect 180 rows (6 stations x 30 days)
make backfill-observed START=2025-06-01 END=2025-06-30  # expect 180 rows of NWS truth
```

If any of these start producing weird counts, silently skipping stations, or raising unexpected errors, **fix before merge** — the unit suite won't catch data-quality regressions.

## Module × test-type matrix (2026-05-25 arc + standing coverage map)

Test types: **U** unit · **P** property (hypothesis) · **G** golden-file · **I** integration (MockTransport / fixtures, no network) · **S** smoke/e2e · **ID** idempotency. ✅ have · ⬜ gap (tracked task in parens).

| Module | U | P | G | I | S | ID |
|---|---|---|---|---|---|---|
| `models.vig_strip` (2-way + `devig_outright`) | ✅ | ✅ | – | – | – | – |
| `models.analog_ensemble` | ✅ | ⬜ | – | – | – | – |
| `backtest.weather_clv` (evaluator) | ✅ | – | – | – | – | – |
| `flows.run_weather_clv_backtest` | ✅ | – | ⬜ | – | ✅ no-data | – |
| `the_odds_api` (h2h + outrights) | ✅ | – | – | ✅ | – | – |
| `kalshi._ticker_parser_nfl` / `_pga` | ✅ | – | – | – | – | – |
| `kalshi.strikes` (greater/less/between pricing + settlement) | ✅ | ✅ | – | ✅ recorded prod fixture | – | – |
| `kalshi.auth` (RSA-PSS signing) | ✅ | – | – | ✅ MockTransport | – | – |
| `clients.openmeteo` / `metar` / `acis` / `ndfd` | ✅ | – | – | ✅ MockTransport | – | ✅ weather lane + ndfd |
| `clients.nfl_players` (weekly legacy+new-scheme fetch, snaps/rosters/ids, snap merge) | ✅ | – | – | ✅ recorded nflverse fixtures (2024 legacy + 2025 new-scheme w1 slices) | – | – |
| `storage.repositories.nfl_players` (`nfl_player_game` guarded upsert + projection ledger) | ✅ | – | – | – | – | ✅ replace-in-place + append-only `as_of` |
| `flows.ingest_nfl_players` (fetch→merge→upsert, self-bootstrap, degraded-snaps recovery) | ✅ | – | – | ✅ fixture-driven e2e into tmp DuckDB | – | – |
| `models.fantasy_nfl` (volume×efficiency, opp/script adj, walk-forward quantiles) | ✅ exact-arithmetic + look-ahead pin | – | – | – | – | – |
| `flows.project_fantasy_nfl` + `score_fantasy_projections` | ✅ | – | – | ✅ seeded-DB e2e (JAC→JAX + devig pin, manifest content) | – | ✅ ledger append / latest-as_of grading |
| `clients.social` (Reddit Atom + RSS parsing, allowlist TOML, UA/spacing/429 posture) | ✅ | – | – | ✅ recorded 2026-07-27 live slices (Reddit Atom + 4 RSS shape variants incl. named-`EST`/`GMT`/`-0400` dates, UUID/scoped/permalink guids) | – | – |
| `models.social_entities` (conservative matching: collision refusal, priority, word boundaries) | ✅ real-fixture titles | – | – | – | – | – |
| `storage.repositories.social` + `flows.ingest_social` | ✅ | – | – | ✅ fixture-driven e2e incl. 429 + garbage-source skips, rotation | – | ✅ frozen first-sighting stamps + NULL-never-wipes |
| `storage.repositories.*` (insert/upsert) | ✅ | – | – | – | – | ✅ all lanes (forecasts/metar/observed/ndfd/nba/nba_odds/kalshi/nfl_players) |
| `backtest.engine` (rolling-origin) | ✅ | – | ✅ | – | – | – |
| `execution.*` (fees/kelly/maker_taker/robust_kelly/live-gate/paper) | ✅ | ✅ | – | – | – | – |
| `flows.*` (CLI) | ✅ | – | – | partial | ✅ pipeline contract (#24) | – |
| `scripts/*.sh` (cron ops: backup/health/notify/rotate) | – | – | – | ✅ (#27) | – | – |

`scripts/*.sh` coverage is **bash-gated**: those tests skip wholesale on a host
without `bash` on PATH (see [Platform coverage](#platform-coverage)), so a
native-Windows run proves nothing about the ops scripts. CI's Linux leg is where
that row is actually enforced.

**Idempotency invariant (verified 2026-05-25, `tests/test_idempotency.py`):** every repo write uses `INSERT OR REPLACE` / `OR IGNORE`, so a cron re-run never duplicates rows or grows the table — re-insert at the same PK replaces in place. **All ingest/upsert lanes are now pinned** (#25): weather (forecasts / metar / observed), NDFD/NBM benchmark, NBA (`nba_game` with a NULL→score replace transition + `nba_odds` line-movement time-series where a *new* `fetched_at` appends by design), Kalshi (`kalshi_market` PK=ticker + `kalshi_book_snap` PK=(snap_time, ticker)), and the Phase S1 social lane (`social_post` PK=(source, source_post_id): upstream edits replace title/text in place while the first-sighting `as_of`/`created_at` stamps NEVER move — a pubDate bumped on edit must not fake freshness in the latency ledger — and NULLs from a degraded re-parse never wipe stored values).

**Pipeline contract smoke (verified 2026-05-25, `tests/test_smoke_pipeline.py`):** the per-flow tests each exercise one flow against a *hand-written* fixture manifest, so none of them catches producer/consumer drift — a rename in `BacktestResult.to_summary_dict` would pass every unit test yet blank out the dashboard + router + health calibration view. The smoke runs the real `run_backtest` engine over a seeded fixture DB, emits the manifest the way `kq.flows.run_backtest` does, then feeds that *same* manifest through every consumer (`dashboard.panels.parse_conformal_rows`, `router_summary.summarize`, `health_check.run_checks`) and asserts each parses it coherently. Network-free, deterministic, CI-safe.

**Money-path coverage audit (2026-05-25, #28):** ran `pytest --cov` over `src/kq/execution` + `src/kq/backtest`. The critical sizing/fee/settlement code is **already at 99–100%** — `fees`, `kelly`, `maker_taker`, `robust_kelly`, `paper_nba`, `synthetic_market`, `result`, `brackets` all 100%; `paper` 99%; overall 96%. The audit found **one genuine safety gap and closed it**: `test_live_gate.py` covered both *refusal* paths but nothing asserted the gate *opens* under the exact §5/§9 conditions (`ack=True` **and** `KQ_LIVE=true`) — added `test_ack_true_and_env_true_allowed`. Also pinned two money-math edge guards that feed the drawdown circuit-breakers (`equity_curve` length-mismatch raise; `max_drawdown([])` → `(0,0)`). Remaining uncovered lines are a test-only helper (`paper.py:fresh_trade_id`), a defensive-dead guard (`metrics.py:53`, unreachable once the empty-equity check at line 47 fires), the gated `LiveExecutor` internals (intentionally never exercised pre-Phase-5), and backtest-engine orchestration edge branches.

**Mutation testing (2026-05-25, #28, dev dep `mutmut` — user-approved per §9):** scoped to the pure-function money path (`fees`, `kelly`, `maker_taker`, `robust_kelly`) with `tests_dir` pinned to their dedicated fast tests so each mutant's run stays sub-second. Config in `[tool.mutmut]`; run with `uv run mutmut run` then `uv run mutmut results`. First pass: 159 mutants, **122 killed (77%)**, 37 survived. Triaging the survivors surfaced **real test gaps** — the open-interval `(0,1)` guards on `kelly_fraction_yes` weren't tested at their boundaries, and (most important) the **§5 hard-cap defaults `fraction=0.15` / `max_stake_usd=200` weren't pinned** (a default could be changed silently), plus `total_fee` was never asserted for a *nonzero* qty (a `round(x,4)`→`round(x)` regression would zero sub-dollar fees). Added boundary + default-pinning + `q_passthrough`-propagation + nonzero-qty tests → **131 killed (82%)**. The residual 28 survivors are all explained: **true equivalents** (`"taker"`→`"XXtakerXX"` still hits the taker branch; `bankroll<=0`→`<0` yields 0 stake either way; `>`/`>=` swaps at exact-equality points; `*100`→`*101` only flips a ceil at a razor-thin non-price), **unkillable cosmetic** (mutmut wraps strings as `XX…XX`, so the original stays a substring — error-message mutations can't be killed via `pytest.raises(match=)`), and **a mutmut blind spot** (default-argument/signature-line mutations map to no test under per-line coverage selection because defaults execute at *import*; verified manually that the new default-pinning tests DO fail under the applied mutation, so they're caught by the full CI suite). Chasing 100% would mean testing-to-the-mutant (asserting exact message text, magic boundary prices) — an anti-pattern. The `mutants/` working dir is gitignored.

**Cron-ops scripts (2026-05-25, #27, `tests/test_cron_scripts.py`):** the four scripts the WSL2 cron host runs unattended (`backup-duckdb.sh` + `notify-failure.sh` + `cron-health.sh` from #78, `rotate-logs.sh` from #80) were committed but had **zero test coverage** — a future edit to the operational safety net could break silently. This pins their behavior with hermetic, network-free subprocess tests: backup writes a timestamped copy + `.wal` sidecar and prunes to `KEEP` (and errors on a missing DB); `notify-failure` no-ops cleanly when `NTFY_TOPIC` is unset (tested via a temp copy so the real `.env`/topic is never touched — no actual push); `rotate-logs` no-ops on a missing log dir and runs clean under logrotate (skipped if absent); `cron-health` appends the health JSON to `health.log` and fires the alert **only** on CRIT (exit ≥ 2), driven by a fake `uv` shim + a marker-dropping fake `notify-failure` so no uv/DB/ntfy is needed.

**Network-free guarantee (2026-05-25, #26, `tests/conftest.py::_no_network` + `tests/test_network_guard.py`):** an audit confirmed every *active* external client already has a hermetic test — httpx clients (`openmeteo`, `metar`, `acis`, `ndfd`, `nbm_qmd`, `ecmwf_opendata`, `the_odds_api`, `nba_odds`, `kalshi`, `_http`) via `httpx.MockTransport`; `nba_api` clients (`nba_schedule`, `nba_injuries`) via `MagicMock`/`patch`. (`clients/nba.py` is a `NotImplementedError` stub superseded by those, so nothing to test.) Rather than add redundant tests, #26 makes the invariant **enforceable**: an autouse fixture blocks real non-loopback socket egress (`socket.connect` / `connect_ex` / `create_connection`; loopback is exempt — it can't reach an external endpoint, and Windows asyncio's event loop needs a real 127.0.0.1 connect) for every non-`integration` test, so a future test that forgets to mock fails loudly instead of flaking on the network. The whole suite runs green under it (proof the existing client tests are truly hermetic); `test_network_guard.py` proves the guard itself fires. `@pytest.mark.integration` tests opt out.

**Open testing-hardening tasks:** none — the #24–#28 hardening arc is complete (asserted smoke suite #24 ✅, full idempotency coverage #25 ✅, network-free guarantee #26 ✅, cron-ops-script tests #27 ✅, money-path coverage audit + mutation testing #28 ✅).

## Coverage goals

- **Unit + mocked integration:** every parser, every sizing/calibration function, every storage repository, every flow error path — targeted.
- **Line coverage:** 80% is enforced as a hard CI gate (`fail_under = 80` in pyproject.toml); meaningful coverage beyond that beats chasing line count.
- **Live coverage:** manual per the checklist above. Never automated.

## What tests we are deliberately not writing

- **Live API tests in CI.** External APIs rate-limit; flaky CI is worse than no live tests. Live checks are manual.
- **Pixel/visual-regression UI tests.** We don't snapshot the rendered dashboard pixels. Instead `tests/test_dashboard_apptest.py` uses Streamlit's official `AppTest` harness to run the app script through the real Streamlit runtime in-process and assert structure: no uncaught exception in any tab, all six tabs present in order, and the #85 sections (Conformal coverage + NBA CLV) render. This catches the render-time failures a bare import can't (bad `st.tabs` unpacking, None-handling slips, Streamlit API misuse) without a browser, a server, or flaky pixel diffs. Visual eyeballing stays manual (`make dashboard`).
- **Backtest correctness against real historical data** — this is the backtest engine's own job (Phase 2 PR 11), not something we duplicate in tests.
- **Kalshi order-placement tests.** Write endpoints are deferred to Phase 5 gate. If any `POST` handler exists before the gate, that's a bug and `test_live_gate.py` should catch it.

## When to update this doc

- Any new module → add a row.
- Any edge-case bug discovered in production → add a test AND a row.
- Any test removal → explain why in the commit message, then delete the row.
- Every PR should leave `docs/TESTING.md` and the actual test suite in sync.

## Reality-contact testing (post-2026-06-11 audit)

The audit's core lesson: **a hermetic suite can only validate the code against
the author's assumptions** — 1,101 green tests coexisted with a system that
could not place a single prod trade, because the tests, the code, and the
fixtures all encoded the same wrong beliefs about the venue. Three standing
countermeasures:

1. **Recorded-reality fixtures.** Wire-format tests use payloads captured
   LIVE from the venue (`tests/fixtures/kalshi_prod_*.json`), never
   hand-written ones. The test author cannot bias what the venue returned.
   When the venue changes formats, re-capture — do not edit by hand.
2. **`kq doctor` (live probes).** Deliberately non-hermetic diagnostics that
   check parser-vs-venue agreement, settlement-source text, and DB truth
   freshness against reality. Run after every deploy; weekly via
   `scripts/reality-probe.sh` with ntfy alerting on CRIT. Its evaluation
   logic is unit-tested with recorded payloads (`tests/test_doctor.py`);
   its live path is intentionally untested — it IS the test.
3. **Loud known-breakage.** When reality and the pipeline are known to
   disagree (e.g. the NY/Central-Park station mismatch until PR-C), the
   doctor reports CRIT on every run rather than special-casing it quiet.
   Visible beats silent; the alert fatigue is the point.

Planned additions as the fix series lands: null-model must-fail CI tests for
every gate metric (PR-E), `as_of`-vs-wall-clock ingest tripwires and a
residual-std plausibility alarm (PR-F).

## Options acquisition checks (October 18)

| Component | Verification |
| --- | --- |
| Databento metadata | Network-blocked MockTransport tests: free GET allowlist, header auth, redirect/error sanitization, bounded symbols/time and invalid costs |
| Estimate CLI | Network-blocked receipt test; no billable endpoint, no key output, existing receipt and malformed plan refusal before transport |
| Options cache values/storage | Canonical identity, schema/source version isolation and fresh credit evidence; file/import/restore integration tests follow with the ledger |
| Options ledger | Offline acquisition/resume, replay and restore smoke; no submit/download method |
