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
