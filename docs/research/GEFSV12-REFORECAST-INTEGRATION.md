# GEFSv12 Reforecast — Integration Scoping

> **Status:** scoping research. Drives Phase 2 extension item #6 per the [Pass 1 extension memo](PASS-1-EXTENSION-EMOS-EXECUTION.md). Three-phase ship plan documented at the bottom; this doc unblocks phase 1 (PR #19).
>
> **Author:** spike + scoping, 2026-04-30.

---

## 60-second summary

NOAA's GEFSv12 retrospective ("reforecast") archive at `s3://noaa-gefs-retrospective` is a **20-year, 5-member, 1-cycle/day** reforecast set frozen at GEFSv12. It's the canonical training source for postprocessing models (Hagedorn-Hamill-Whitaker 2008 reports roughly *doubled* CRPSS over short-window NGR for 2 m temperature). For our 6 stations + Tmax, byte-range subsetting via the `.idx` companion files reduces the raw data volume from the memo's 25 GB estimate to **~1 GB** — far more tractable than originally projected.

Three phases:

1. **Phase 1 (this PR, ~200 LoC, no new deps):** scoping doc, S3 URL builder, listing helpers, `kq plan-gefsv12-pull` dry-run that estimates data volume per (year, member, var) without actually downloading.
2. **Phase 2 (~300 LoC, +`cfgrib`/`xarray`/`eccodes`):** real byte-range fetch + GRIB2 parse + per-station extract + DuckDB schema. Adds the system dep `eccodes` — needs explicit user signoff per CLAUDE.md §9.
3. **Phase 3 (~150 LoC):** rewire NGR training to consume reforecast data; re-run backtest verdict; close KMDW gap (or surface that even reforecast training can't).

This document covers phase 1 + everything you'd need to know before approving phases 2/3.

---

## Archive shape (verified 2026-04-30)

```
s3://noaa-gefs-retrospective/
  GEFSv12/
    reforecast/
      {YEAR}/                      2000..2019 (20 years, frozen)
        {YYYYMMDDHH}/              one cycle per day, typically 00 UTC
          c00/                     control member
          p01/, p02/, p03/, p04/   4 perturbation members → 5 total
            Days:1-10/             short-range forecast hours
            Days:10-16/            long-range forecast hours
              {var}_{level}_{cycle}_{member}.grib2
              {var}_{level}_{cycle}_{member}.grib2.idx
```

**Key facts:**

- **Members:** `c00` (control) + `p01-p04` (4 perturbations) = 5 total. NOT 31 like operational GEFS — this is a deliberate design choice for the long reforecast set. Hagedorn-Hamill-Whitaker 2008's CRPSS doubling result holds even with 5-member reforecast.
- **Cycles:** 00 UTC daily, ~7,300 cycles total over 20 years.
- **Variable for Tmax:** `tmax_2m` ✓ (matches our needs exactly). Other relevant variables that ship with the archive: `tmin_2m`, `tmp_2m`, `dpt_2m` (dewpoint), `pres_msl`, `cape_sfc`, `pbl_hgt`, etc.
- **File size:** ~59 MB per (cycle, member, variable, days-range). Full-resolution global grid covering 1-10 day forecast at ~0.25° resolution.
- **Index files:** `.idx` companion is ~6.7 KB and lists byte offsets per record (per forecast hour). Enables HTTP byte-range subset extraction without downloading the full file.

## Data volume estimate

**Without byte-range subsetting (the memo's framing):**

```
20 years * 365 days/year * 5 members * 1 var (tmax_2m) * 1 days-range * 59 MB
= ~2.1 TB
```

That's the "pull whole files" upper bound. Not feasible.

**With byte-range subsetting (the right approach):**

For each station, we want the grid point nearest the station coordinates. At GEFSv12's 0.25° resolution, that's a single grid cell (~25 km box). One forecast-hour record per station per file is ~few KB. The `.idx` file tells us byte offsets so we can `Range:` request just those bytes.

```
20 years * 365 days * 5 members * 1 var * 6 stations * ~3 KB/station-record
= ~660 MB raw
```

If we want **~40 km neighborhood** per station per the memo (for spatial averaging or context features) at 0.25° → ~9 grid cells per station, ~25 KB/station-record:

```
~5.5 GB
```

Either way, **far less than the 25 GB estimate in the memo** because byte-range subsetting was implicit there but not stated.

For phase 1 we plan against the **single-grid-point case (~660 MB)** as the v1 target. Multi-cell neighborhood is a phase-3 extension.

## Why this matters for KMDW

Per the [post-#15 audit + post-#18 verdict](../../ROADMAP.md), KMDW is the deepest residual gap on the board (Brier-vs-NDFD = -51% under both NGR and RAW). The memo identifies reforecast-trained NGR as the single most likely lever:

> "Hagedorn, Hamill, and Whitaker (2008, *Mon. Wea. Rev.* 136, 2608)... show reforecast-trained NGR roughly *doubles* CRPSS over short-window NGR. They also show that reforecast training adds a meaningful CRPSS bump over a 30-day rolling-window NGR specifically at lead times where the rolling window is too short to learn site-specific structure — the exact regime where your KLAX/KMDW/KMIA models are dying."

KMDW is uniformly bad across every month (per #12 diagnostic) — the "uniform" character points at site-specific structure NGR with our current ~14-month training window can't learn. Reforecast gives us 20 years × 5 members = 100x more matched (forecast, observed) pairs.

## Dependency story

**Phase 1 (this PR):** no new deps. Pure URL building + S3 listing via existing `httpx`. The `.idx` listing is a tiny ASCII parse; no GRIB2 awareness needed.

**Phase 2 (deferred):** needs **`cfgrib` (Python) + `xarray` (Python) + `eccodes` (system C library)**. Per CLAUDE.md §9:

> "Install new dependencies (every addition requires approval and pinning)."

The `eccodes` system dep is the bigger ask: macOS `brew install eccodes` (one-liner), Linux `apt-get install libeccodes-dev` (one-liner). Already a known dep for the deferred NBM `qmd` upgrade in [`NDFD-BENCHMARK-SOURCE.md`](NDFD-BENCHMARK-SOURCE.md) — installing it once unblocks both items #6 (this) and the qmd upgrade.

Recommendation: phase 2 should bundle the `eccodes` install with the NBM `qmd` upgrade so the user only needs to approve one system-dep addition. Combined PR scope: ~600 LoC.

## Storage decision

**Option A: Reuse the existing `weather_forecast` table.** Add rows with `model='gefsv12_reforecast'` and `member` filling 0..4 (mirror the existing GEFS member convention). Pros: minimal schema change. Cons: the table fills up fast (20 years × 5 members × 6 stations = ~220k rows just for tmax).

**Option B: New `gefsv12_reforecast` table.** Dedicated columns for reforecast metadata (`reforecast_cycle`, `forecast_hour_offset`, `member_index`). Pros: clean separation, room for richer metadata. Cons: another table to maintain.

**Recommended for phase 2: Option A.** The `weather_forecast` schema already has `model` + `member` fields that distinguish GEFS members; reforecast is just another `model` value. This keeps the training join straightforward — `build_training_set` already filters by `model` and aggregates members.

## Per-station extraction approach

For each (cycle, member, days-range) GRIB2 file we want **the grid point nearest each of our 6 stations** for forecast hours covering the relevant lead times. With byte-range subsetting:

```python
# Pseudocode for phase 2:
async with httpx.AsyncClient() as client:
    idx_text = await fetch_idx(client, idx_url)
    record_offsets = parse_idx(idx_text)  # {forecast_hour: (start, end)}
    for hour in TARGET_HOURS:                # e.g., 24, 48, 72 (lead 1-3 days)
        start, end = record_offsets[hour]
        record_bytes = await fetch_byte_range(client, grib2_url, start, end)
        ds = open_grib2_record_in_memory(record_bytes)  # cfgrib
        for station in STATIONS:
            tmax_at_station = ds.tmax_2m.sel(
                latitude=station.lat, longitude=station.lon, method="nearest"
            )
            yield (station, valid_date, member, tmax_at_station)
```

For the v1 target lead time (1 day → forecast hour 24), one HTTP request per (cycle, member) gives us all 6 stations. With concurrency, the full 20-year pull is ~hours of wall time.

## Phase 1 deliverables (this PR)

1. **This research doc** documenting the archive shape, dependency story, storage decision, and per-station extraction approach.
2. **`src/kq/clients/gefs_reforecast.py`** — pure functions:
   - `s3_url_for(year, cycle, member, days_range, var)` — URL builder, no I/O.
   - `iter_reforecast_keys(start_year, end_year, members, vars, days_ranges)` — yields S3 keys without listing.
   - `parse_idx_text(text)` → `dict[forecast_hour, tuple[int, int]]` — byte-range parser for `.idx` files. Pure function.
   - `estimate_pull_volume(start_year, end_year, members, vars, n_stations)` → bytes — back-of-envelope from the per-station-record size assumption.
3. **`kq plan-gefsv12-pull`** CLI subcommand — dry run. Prints expected count of files, bytes, and HTTP requests for a given config. **No actual data pull.**
4. **Tests** for the URL builder, key iterator, idx parser, and volume estimator.
5. **ROADMAP** entry: row #6 status `⏸ deferred` → `🟡 in flight (phase 1 of 3)`.

## Phase 2 (deferred — needs user signoff for new deps)

- Add `cfgrib`, `xarray` to `pyproject.toml`. Document `eccodes` install in `docs/SETUP.md`.
- Implement actual byte-range fetching + GRIB2 parsing.
- DuckDB schema additions (Option A: extend `weather_forecast`).
- `kq pull-gefsv12-reforecasts --start --end --vars` CLI to drive the pull.
- Tests covering the parser + ingest flow.

## Phase 3 (deferred — depends on phase 2)

- Modify `kq train-weather` to optionally consume reforecast data alongside (or instead of) the rolling Open-Meteo training window.
- Re-run backtest with reforecast-trained NGR. Expected impact (per memo): KMDW vs-NDFD goes from -51% to plausibly **+5% to +20%** based on Hagedorn-Hamill-Whitaker doubling-CRPSS result. Other stations should also improve.
- Update Phase 5 readiness criteria #2 with the post-reforecast verdict.

---

## Path B execution + verdict (2026-05-01)

After PR #22's null-or-slight-negative verdict at 1-year c00 sample size, user approved Path B (more reforecast data). This section documents what we ran, what we discovered, and what it means.

### Operational pull

- **Scope:** `c00,p01,p02,p03,p04` × 2015-2019, lead-day-1 records (`Days:1-10/tmax_2m_*.grib2`, hours 24-48).
- **Volume:** 9,130 files indexed; 431,952 station-records fetched; **53,994 rows inserted** into `weather_forecast` (model=`gefsv12_reforecast`, members 0..4, idempotent on PK).
- **Wall time:** ~2 hours, single-process, max-concurrent=5. CPU-bound on cfgrib parsing — bumping HTTP concurrency wouldn't help (single async event loop). The `print(...processed N/M files)` progress markers stay buffered until process exit; structlog `gefsv12.records_fetched` and `gefsv12.pull_done` events fire only at end.
- **Per-member coverage:** c00=1,826, p01=1,772, p02=1,771, p03=1,804, p04=1,826 per station — ~1.5% per-file failure rate (worker swallows per-file errors and returns `[]`). Acceptable for a downstream NGR fit.

### Discovery: observed-truth coverage was the actual bottleneck

The first reforecast×observed JOIN yielded **396 dates per station** — the same as the 1-year c00 baseline. Investigation: `weather_observed` only covered 2018-12-01+. We had reforecast data for 2015-2019, but no truth pairs to fit against pre-2018-12-01.

**Fix:** ran `kq backfill-observed --start 2015-01-01 --end 2018-11-30` (NWS ACIS, 8,580 rows in 10 sec). The JOIN then yielded **1,825 dates per station** as intended. The `weather_observed` table now covers 2015-01-01 → present.

**Lesson for future feature backfills:** when adding a new forecast source, audit observed-truth coverage at the same time. The PR #21 ingest landed before the truth table caught up; the verdict was misleading because of it.

### Verdict at full sample size

Re-ran `kq backtest --strategy weather_reforecast_v1` after the truth backfill. Per-station NGR fit on 1,825 cycles × 5-member ensemble mean (vs. the prior 365 cycles × 1-member trace).

| Station | 1y c00 (vs NDFD) | Path B full (vs NDFD) | Δ vs c00 | Skew-NGR (active) | Δ vs skew-NGR |
|---|---|---|---|---|---|
| KAUS | -12.9% | -14.1% | -1.2pp | -14.5% | +0.4pp (tied) |
| KDEN | -1.2% | -2.9% | -1.7pp | -1.9% | -1.0pp (tied) |
| KJFK | -42.4% | -40.3% | +2.1pp | -2.0% | **-38.3pp** |
| KLAX | +4.1% | +5.4% | +1.3pp | +40.8% | **-35.4pp** |
| KMDW | -66.3% | -60.4% | +5.9pp | -51.1% | -9.3pp |
| KMIA | -2.6% | **+8.2%** | **+10.9pp** ✓ | +8.9% | -0.7pp (tied) |

**Headline:** KMIA is the only station to flip from below-bar to above-bar attributable to Path B (-2.6% → +8.2% vs NDFD). Other stations move by ±1-6pp — within noise except for KMDW's modest +5.9pp gain that still leaves it far from passing.

**Path B vs skew-NGR (the active model):** reforecast-NGR is **tied or worse at every station**. KJFK and KLAX collapse by ~36pp because the cross-model-family bias structure doesn't transfer. **The router would never pick reforecast-NGR over skew-NGR**, so this is a shipped-but-shelved capability.

### Hypotheses revisited

The two hypotheses from the PR #22 writeup, refined:

1. **Cross-model-family mismatch dominates.** Confirmed at full sample size. Even with 5x more training data and a true 5-member ensemble mean as the predictor, training on GEFSv12 reforecast and evaluating on GFS-via-Open-Meteo operational forecasts produces NGR fits that don't transfer cleanly. KJFK and KLAX's ~36pp collapses are the cleanest evidence.

2. **Insufficient training data was a compounding effect, not the dominant one.** Path B closed the sample-size axis (1,825 vs 365 dates, 5-member vs 1-member predictor) and most stations moved by < 6pp. KMDW's +5.9pp gain and KMIA's +10.9pp flip are real but consistent with a "more data helps a little" picture, not a doubling-CRPSS picture.

### What's left

**Not pursued; documented for future reference:**

- **Path A (model-family alignment)** — switching operational ingest to a GEFS-based product. This requires verifying Open-Meteo's GEFS endpoints, redoing 5+ years of operational ingest, and re-validating the entire pipeline. Significant work for a marginal improvement on KMDW. **Recommendation: pursue only if KMDW becomes a higher priority** (e.g., post-Phase-5 if other gaps close and KMDW is the priority outlier).

- **Treat KMDW as a known structural gap** — Chicago Midway's lake-effect microclimate is below the 0.25° GEFS reforecast resolution and below the 2.5km NBM operational resolution. No NGR/EMOS-style postprocessing will close that gap; only either (a) higher-resolution operational forecasts (HRRR-based, which we're not ingesting yet) or (b) a non-postprocessing approach (LightGBM with extended MOS predictors per item #10, post-Phase-5) is a plausible lever.

### Bar status (post-Path-B, 2026-05-01)

**Unchanged: 2 of 6 cleanly clear** (KLAX, KMIA via active model `weather_router_v1`). Path B's KMIA flip is consistent with the active model's existing pass rather than additive to it.

The recommended trading config remains `weather_router_v1` (skew-NGR + NDFD-aware per-station decisions). Reforecast-NGR is shipped, exercised at full sample size, and parked as a non-driver. The Phase 5 readiness criterion #2 (≥ 5% Brier improvement vs raw-ensemble baseline) is met by the active model at KLAX and KMIA; KAUS and KDEN are within noise of the bar; KJFK and KMDW are not.

## Open questions for phases 2-3

1. **Concurrency limits.** Open Data is unauthenticated but rate-limited (likely ~100 RPS sustained per IP). Need to throttle the pull. Default plan: 10 concurrent requests, ~30 minutes wall time for full archive.
2. **Storage location.** The ~660 MB extracted dataset fits in the DuckDB file. We should NOT commit this to git (gitignored already for `data/*.duckdb`). The user's M1 Pro has plenty of space; Windows backup discipline per `docs/SCHEDULED-RUNS.md` already covers DuckDB rotations.
3. **Train/eval split with reforecast.** Reforecasts span 2000-2019; our backtest evaluation window is 2024-11 → 2025-06 (NDFD-covered). No overlap → reforecast can be pure training data with no leak risk. The rolling-origin discipline still applies on top (only training rows from before each fold's test window).
4. **Variable selection.** Phase 1 plans for `tmax_2m` only. Phase 2 candidates per Pass 1 memo: `tmp_2m` (mean temp), `dpt_2m` (dewpoint), `pbl_hgt` (boundary layer height) — used as MOS-style predictors in item #10 (LightGBM quantile regression, post-Phase-5 only). For now, `tmax_2m` alone keeps the schema simple.

---

## References

- [NOAA GEFS Retrospective (Hamill et al. 2022, *MWR*)](https://journals.ametsoc.org/view/journals/mwre/150/3/MWR-D-21-0245.1.xml) — operational dataset description.
- [Hagedorn, Hamill, Whitaker 2008, *MWR*](https://journals.ametsoc.org/view/journals/mwre/136/7/2007mwr2410.1.xml) — CRPSS-doubling result.
- [Pass 1 Extension memo §1](PASS-1-EXTENSION-EMOS-EXECUTION.md) — original ship-list framing.
- [NDFD-BENCHMARK-SOURCE.md](NDFD-BENCHMARK-SOURCE.md) — companion `eccodes`/`cfgrib` dep discussion (NBM qmd upgrade).
- AWS Open Data: `s3://noaa-gefs-retrospective` (no auth, no egress fees).
