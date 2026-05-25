# NBM qmd Phase 2 — investigation findings (2026-05-25): deferred, not "a quick wiring PR"

> **TL;DR:** ROADMAP item #16 framed NBM qmd Phase 2 as a near-term follow-up that "wires qmd quantiles into `ndfd_forecast`." A pre-build investigation (2026-05-25) found that Phase-1's assumptions are wrong on three counts and, more importantly, that the daily-**MaxT** quantiles we'd need **are not in the public f048 `qmd.co` file at all**. Phase 2 is therefore a research-plus-engineering project, deferred. This doc records what was found so the next session doesn't re-discover it.

## What was checked (live, against `s3://noaa-nbm-grib2-pds`)

The bucket is reachable, anonymous, layout intact, and **retains history back past 2025-01-15** (covers our 2024-11→2025-05 backtest window) — so the data-access side is fine. The problems are with the file contents + size:

### 1. The file is ~767 MB, not "30–50 MB"
`blend.t00z.qmd.f048.co.grib2` downloaded at **767 MB**. The Phase-1 docstring (`src/kq/clients/nbm_qmd.py`) claims "~30-50 MB at 2.5km" and on that basis **explicitly skipped `.idx` byte-range subsetting**. At 767 MB:
- forward ingest at 4 cycles/day = ~3 GB/day of whole-file pulls;
- a historical backfill of the ~180-day window = **~115–140 GB**.
Both are impractical. Phase 2 **must** implement `.idx` byte-range subsetting (pull only the handful of Tmax-quantile messages, a few MB).

### 2. Phase-1's `extract_station_quantiles` matches zero variables
It filters `filter_by_keys={'shortName': 'mx2t'}`. The real file has **no `mx2t`/`tmax`** field — `cfgrib` returns an empty dataset (`StopIteration` on `next(iter(ds.data_vars))`). Temperature is `TMP` (instantaneous 2 m), not a max element.

### 3. (The real blocker) No daily-MaxT element in the f048 qmd.co file
The `.idx` shows the only temperature entries are:
```
TMP:2 m above ground:48 hour fcst:<N>% level     # the quantiles (0,5,10,…,95,100)
TMP:2 m above ground:48 hour fcst:prob <X / >X   # threshold exceedance probs
```
i.e. **instantaneous 2 m temperature at the f048 valid time** (≈ 00Z two days out — midnight UTC), by percentile. There is **no `MaxT`/`TMAX`/period-max descriptor anywhere** in the file (`grep -i max` on the `.idx` → nothing; the only level/fcst descriptor for temperature is `2 m above ground:48 hour fcst`).

Our weather model predicts the **daily maximum** temperature (LST-day Tmax). Comparing it against instantaneous midnight-UTC temperature quantiles would be methodologically wrong. NBM *does* produce a daily-MaxT ("MaxT") element, but it is **not in this f048 qmd.co file** — it would be at a different forecast step (the one whose period covers the local daytime max, ~f036–f042 for a 00z init over CONUS afternoons) and/or a different element/param, which needs NBM-product research to locate and confirm it exists in the public qmd bucket in usable form.

## What Phase 2 actually requires (revised scope)
1. **Research:** identify the NBM daily-MaxT quantile element — which step file holds it, its GRIB param/level/period descriptor, and how its max-window aligns to our LST-day Tmax (`kq.clients.kalshi` LST settlement-day logic). Uncertain whether it's in the public `qmd` bucket at all vs. only `core`/deterministic.
2. **`.idx` byte-range subsetting** (mandatory given 767 MB): parse the `.idx`, select the 5 (or more) MaxT-quantile messages, HTTP `Range`-GET only those byte spans, parse with cfgrib.
3. Fix/replace `extract_station_quantiles` with the correct `filter_by_keys` once the element is known.
4. `qmd_exceedance(quantiles, threshold)` — monotone interpolation of `P(Tmax > t)` from the labelled quantiles (replaces the deterministic Gaussian-wrap).
5. Ingest flow → `ndfd_forecast(source='nbm_qmd_s3')` with the `p10..p90` columns (schema already has them).
6. Benchmark/engine: consume `source='nbm_qmd_s3'` for Brier-vs-NDFD when present; fall back to deterministic.
7. Backfill (now feasible *with* byte-range) + re-run the Phase 5 #2 verdict.

Realistically a multi-day effort gated on step 1's research outcome. **Recommendation:** keep the deterministic NBM benchmark (current default) as the Phase 5 #2 benchmark for now; treat NBM qmd as a v2 research ticket. Prefer higher-confidence Phase-5-#2 levers first (e.g., analog ensembles).

## Concrete next-session starting points
- `.idx` URL pattern: `<grib_url>.idx`; columns `msg:byteoffset:d=YYYYMMDDHH:PARAM:level:fcst:percentile/prob`.
- Probe other steps for a MaxT element: `curl -s '<base>/blend.YYYYMMDD/00/qmd/blend.t00z.qmd.fNNN.co.grib2.idx' | grep -iE 'max|TMP'` across fNNN ∈ {f024,f036,f042,f048}.
- Byte-range fetch: `Range: bytes=<start>-<end-1>` where end = next message's offset (or EOF for the last).
