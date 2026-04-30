# NDFD Benchmark — Data Source Decision

> **Status:** decision record. Drives [Phase 2 extension item #1](../../ROADMAP.md#phase-2-extension--ship-list-from-pass-1-extension-research) (NDFD benchmark + CLV tracking) per the [Pass 1 extension memo](PASS-1-EXTENSION-EMOS-EXECUTION.md).
>
> **Author:** spike + decision, 2026-04-29.

---

## 60-second summary

The Pass 1 extension memo asks for "NWS NDFD probabilistic Tmax forecast at issue T-1h before market close" as the external Brier benchmark. After a focused source spike, the production data path that ships fastest without new system dependencies is:

1. **Source:** NBM (National Blend of Models, NDFD's modern operational backbone) deterministic Tmax via Open-Meteo's `ncep_nbm_conus` model. Pulled at the moment we'd lock in a trade for the day-ahead market (T-1h before LST midnight close).
2. **Probabilistic conversion:** wrap the deterministic Tmax with a per-station residual sigma fit from training-window history; compute `P(Tmax > threshold) = 1 - Φ((threshold - NBM_mean) / σ_residual)`. This sigma is re-fit per CV fold to keep the comparison apples-to-apples with our NGR.
3. **Archive depth:** Open-Meteo's NBM history reaches back to ~2024-11-01 (~18 months as of 2026-04-29) — sufficient for a first-pass per-station verdict, and the same window over which our existing NGR backtest has the highest density of feature rows.
4. **Upgrade path (deferred):** true NBM probabilistic quantiles via `s3://noaa-nbm-grib2-pds` `qmd` GRIB2 files + `cfgrib`/`eccodes`. Adds a system dep; documented below as a separate ship item.

Net: this PR **strictly upgrades** our benchmark vs. the synthetic-naive-market currently in `backtest/synthetic_market.py` — the comparison is now NWS-derived rather than self-referential. The Gaussian wrapper is a known compromise, called out honestly in the manifest output and ROADMAP.

---

## Problem statement

Our current backtest compares the model against a "naive synthetic market" that wraps the **same forecast we are trading on** in a Gaussian sigma derived from the **same NGR fit** we are evaluating. That makes the Brier improvement comparison structurally pessimistic at coastal stations (because the synthetic market re-uses our model's inputs) and optimistic at the wings (because it doesn't capture market-maker informed pricing).

Phase 5 readiness criterion #2 needs a benchmark that is:

- External (not derived from our model)
- Calibrated (a published, operationally-vetted forecast)
- Available at every (station, valid_date) we backtest
- Available at the moment we'd lock in a trade

The Pass 1 extension memo is explicit: "the cleanest external benchmark is the NWS NDFD probabilistic Tmax forecast at issue T-1h before market close (free, public, well-calibrated). If we cannot beat NDFD by ≥ 2-3% Brier consistently across our 6 stations, no execution upgrade saves us."

---

## Sources evaluated

| Source | Probabilistic? | Archive depth | New deps | Notes |
|---|---|---|---|---|
| **NBM `qmd` via `s3://noaa-nbm-grib2-pds`** | ✅ Yes (P1, P5, P10, P25, P50, P75, P90, P95, P99) | ✅ Back to **2020-05-18** (verified) | ❌ `cfgrib` + `eccodes` C lib | Canonical answer; full-fidelity probabilistic. Per-cycle file is ~280 MB but `.idx` + HTTP range requests reduce this to ~few hundred KB per station per cycle. |
| **NWS API (`api.weather.gov/gridpoints`)** | ❌ No (deterministic Tmax only — verified by probing `OKX/42,40` for KJFK; only `temperature`, `maxTemperature`, `probabilityOfPrecipitation`, `probabilityOfThunder` returned) | Real-time only | ✅ None | Useless for probabilistic Tmax. |
| **Open-Meteo `ncep_nbm_conus`** | ❌ No (deterministic only) | ⚠️ ~2024-11-01 onward (verified) — pre-Nov-2024 returns null | ✅ None (existing client extension) | The pragmatic v1 path. Still NWS-derived (NBM is the underlying model), just stripped of probabilistic quantiles. |
| **NDFD GRIB2 via `tgftp.nws.noaa.gov`** | ⚠️ Some probabilistic elements but no probabilistic Tmax in standard NDFD products | Real-time only (no archive) | ❌ `cfgrib` + `eccodes` | Inferior to NBM `qmd` in every dimension — older, narrower archive, same GRIB2 dep. |
| **NDFD SOAP Web Service** | ⚠️ Has experimental `Maximum Temperature` probability element | No archive | ⚠️ Adds SOAP/XML parsing | Deprecated; rate-limited; wrong direction. |
| **NCEP LAMP/MOS bulletins** | ✅ Yes (probabilistic Tmax in plain ASCII) | Limited archive (~30 days) | ✅ None (text parser) | Wrong product class — LAMP is short-range MOS, not the operational probabilistic Tmax the memo asks for. Range too short for our 1-7-day brackets. |

### Verification commands

```bash
# NBM grib2 archive (back to 2020-05-18 confirmed)
curl -sS "https://noaa-nbm-grib2-pds.s3.amazonaws.com/?list-type=2&max-keys=20&delimiter=/"

# NBM qmd file structure (288 MB per cycle, hourly issues)
curl -sS "https://noaa-nbm-grib2-pds.s3.amazonaws.com/?list-type=2&prefix=blend.20260428/12/qmd/&max-keys=10"

# NWS API — probabilistic temperature: NOT AVAILABLE
curl -sS "https://api.weather.gov/gridpoints/OKX/42,40" -H "User-Agent: forecast-lab/0.0.1"
# (only `maxTemperature` deterministic + `probabilityOfPrecipitation`; no probabilistic Tmax)

# Open-Meteo NBM — historical archive depth probe
for d in 2024-11-01 2025-01-01 2025-04-01 2025-12-01; do
  curl -sS "https://historical-forecast-api.open-meteo.com/v1/forecast?latitude=40.6413&longitude=-73.7781&start_date=${d}&end_date=${d}&daily=temperature_2m_max&models=ncep_nbm_conus&temperature_unit=fahrenheit&timezone=America%2FNew_York"
done
# 2024-11-01: 77.7  | 2025-01-01: 51.2  | 2025-04-01: 56.3  | 2025-12-01: present
# 2024-06-01: null  | 2023-06-01: null  (depth wall ~2024-11)
```

---

## Decision

**Ship Open-Meteo NBM (deterministic) + per-fold fitted-sigma in PR 1 + PR 2 of this work item.** Defer NBM `qmd` (probabilistic) via S3 GRIB2 to a follow-up item once we know whether the deterministic-NBM benchmark is cleared.

### Rationale

1. **Ships fastest.** Mirrors the existing Open-Meteo client pattern; one new model id (`ncep_nbm_conus`) on a familiar API. No new system dependencies.
2. **Strictly upgrades the current benchmark.** Today's "synthetic naive market" wraps our own forecast in our own sigma. The new benchmark wraps an externally-blended NWS forecast in an externally-fit-residual sigma. The mean is independent of our model. That's a meaningful step up.
3. **Sufficient signal for the Phase 5 readiness question.** "Do we have edge over NWS-derived guidance?" is answerable with deterministic-NBM-with-fit-sigma. If the answer is "no" by a wide margin, true probabilistic NBM wouldn't save us. If the answer is "yes" or "borderline," that's when probabilistic NBM earns the eccodes dep.
4. **Archive depth is workable.** ~18 months of NBM history maps cleanly onto our existing backtest window where we have the densest joint feature coverage (METAR + Open-Meteo ensembles + NWS observed truth all most reliable from late 2024 onward).
5. **Upgrade path is well-understood.** When we later add `cfgrib` for `qmd` quantiles, the existing `ndfd_forecast` table extends naturally (probabilistic columns added via PR-time `ALTER TABLE`; new rows tagged `source='nbm_qmd_s3'`).

### What we lose by punting on `qmd`

- **Skewness in the predictive distribution.** NBM `qmd` quantiles capture upper-tail heaviness (Allen et al. 2023 reports 8-15% upper-tail Brier improvement from skew-aware predictive distributions). Wrapping deterministic-NBM in a Gaussian discards that information.
- **Bias-corrected sigma.** NBM's published quantiles are calibrated; our fit-from-residuals sigma is a Gaussian approximation that will under-cover tails at marine stations (KMIA, KLAX) and over-cover at continental stations (KDEN winter chinook events).
- **Honest framing for Phase 5 gate criterion #2.** The "≥ 2-3% Brier improvement vs NDFD" target was specified against the published probabilistic forecast, not a Gaussian wrap. If we beat the Gaussian wrap by 3% but fail vs. true `qmd`, that's a false positive. Mitigation: name this in the ROADMAP and the manifest output, and re-test against `qmd` before crossing the Phase 5 gate.

---

## Schema design (PR 1)

New DuckDB table, designed for the eventual probabilistic upgrade without migration:

```sql
CREATE TABLE IF NOT EXISTS ndfd_forecast (
    as_of           TIMESTAMP NOT NULL,   -- when we pulled this row
    station         VARCHAR   NOT NULL,
    valid_date      DATE      NOT NULL,
    lead_days       INTEGER   NOT NULL,   -- floor((valid_date_lst_midnight - as_of) / 1d)
    source          VARCHAR   NOT NULL,   -- 'nbm_deterministic_openmeteo' (v1) | 'nbm_qmd_s3' (v2)
    forecast_max_f  DOUBLE,               -- deterministic Tmax (always populated)
    -- Probabilistic columns — NULL for source='nbm_deterministic_openmeteo'.
    -- Reserved for the qmd upgrade so we don't migrate later.
    p10_max_f       DOUBLE,
    p25_max_f       DOUBLE,
    p50_max_f       DOUBLE,
    p75_max_f       DOUBLE,
    p90_max_f       DOUBLE,
    PRIMARY KEY (as_of, source, station, valid_date)
);
```

Notes:
- `as_of` is the snapshot timestamp; `(as_of, source, station, valid_date)` makes per-snapshot rows unique even if the same valid_date is fetched at multiple times (e.g., once at T-1h and once at T-6h).
- `source` is part of the PK so deterministic-only rows and qmd rows can coexist without conflict when the upgrade lands.
- `lead_days` is denormalized for fast filtering during backtest joins (avoid recomputing it from `as_of` + `valid_date` per row).

---

## Probabilistic conversion (PR 2 + audit fix)

For a deterministic-NBM forecast `μ_NBM`, threshold `T`, and per-fold residual stats `(bias, σ)`:

```
P(Tmax > T) = 1 - Φ((T - (μ_NBM - bias)) / σ)
```

The bias term is **load-bearing**, not cosmetic. Verified empirically on 162 station-days/station of joint NDFD+observed truth:

| Station | bias (°F) | σ (°F) | bias / σ |
|---|---|---|---|
| KLAX | -3.59 | 2.19 | -1.64 |
| KMIA | -1.80 | 1.29 | -1.40 |
| KJFK | -1.68 | 1.83 | -0.92 |
| KDEN | -1.95 | 2.68 | -0.73 |
| KAUS | -1.16 | 2.13 | -0.55 |
| KMDW | -0.87 | 1.93 | -0.45 |

All stations show NBM under-forecasting (negative bias). Skipping the bias term applies a Gaussian centered on `μ_NBM` instead of the calibrated `μ_NBM - bias`, handicapping NDFD by up to 1.6σ at marine sites. This was caught in the post-PR-#12 audit (2026-04-29) and is the standard EMOS bias correction — not a novel adjustment.

Sigma fit logic (per CV fold, per station):

```python
# residuals on training portion only
residuals = nbm_train_forecasts - nbm_train_observed
bias = float(np.mean(residuals))
sigma = max(np.std(residuals, ddof=1), 1.0)  # 1 °F floor so we never collapse the distribution
return bias, sigma
```

Per-fold fit keeps the comparison fair: NBM benchmark sees the same `as_of <= signal_time` constraint our NGR does. No look-ahead.

The `1.0` floor mirrors how the existing engine clamps `market_sigma_f = max(ngr.fit_metadata.get("raw_residual_std", 3.5), 1.0)` ([engine.py:231](../../src/kq/backtest/engine.py)).

---

## Open questions (flagged, not blocking PR 1)

1. **Lead-day mapping for ingest.** Live ingest pulls "right now"; `lead_days` is computed from `as_of`. For backfill we use Open-Meteo's historical-forecast API, which returns "what NBM would have forecast for date `D` based on the most relevant cycle" — they don't surface the precise issue cycle. We treat the backfilled row as `lead_days=1` (the operational case for our day-ahead trades) and document that as a known approximation in the manifest.

2. **Per-station vs. per-station-per-month sigma.** The fitted sigma for KJFK winter is materially different from KJFK summer. Per-station-per-month gives more honest tail probabilities but needs ≥30 events/month/station to be stable. With ~18 months of history that's borderline. PR 2 ships per-station only; per-station-per-month is a follow-up if the verdict is borderline.

3. **Threshold semantics.** Kalshi `KXHIGHLAX-26APR30-T75` resolves YES if "Tmax > 75°F" (strict inequality) per [`bracket_match.py`](../../src/kq/backtest/bracket_match.py). The Gaussian wrap respects strict inequality natively (continuous CDF). At integer thresholds with deterministic forecasts ending in `.5`, the resulting probabilities are clean. No special-casing needed.

4. **Open-Meteo rate limits.** The historical-forecast API tier limit is 10k calls/day on the free tier. 6 stations × 18 months × 1 call/(station,day) = ~3,300 backfill calls — comfortable. Live ingest is 6 calls/cycle × 1-2 cycles/day = ~12 calls/day. Well within budget.

---

## Upgrade path: NBM `qmd` (deferred)

When we want to harvest the skew/tail benefits, the work is:

1. Add `cfgrib` to `pyproject.toml` (and document `eccodes` system install in `docs/SETUP.md`).
2. Add `kq.clients.nbm_grib` — async S3 byte-range fetcher using the `.idx` companion files. Reads only the `TMAX:24 hour Maximum:percentile=N` records for the 6 station coordinates.
3. Insert rows with `source='nbm_qmd_s3'` and the probabilistic columns populated.
4. Update `backtest/engine.py` to prefer `qmd` rows where available and fall back to `nbm_deterministic_openmeteo` otherwise — letting the comparison gradually upgrade in place.

Estimated cost: ~250 LoC + the dep + an hour of system-setup docs. Worth the spend if our deterministic-NBM verdict is borderline (clear win or clear loss likely doesn't change with the upgrade).

---

## References

- [Pass 1 Extension memo §1, §C, §D](PASS-1-EXTENSION-EMOS-EXECUTION.md) — original ask + Brier-improvement target
- [NOAA NBM AWS Open Data](https://registry.opendata.aws/noaa-nbm/) — bucket structure, retention
- [Open-Meteo Historical Forecast API](https://open-meteo.com/en/docs/historical-forecast-api) — JSON access, model coverage
- [Allen et al. 2023, *MWR*, "Accounting for Skew when Postprocessing MOGREPS-UK Temperature Forecast Fields"](https://empslocal.ex.ac.uk/people/staff/fk206/papers/MWR_21.pdf) — why probabilistic Tmax matters at the wings
