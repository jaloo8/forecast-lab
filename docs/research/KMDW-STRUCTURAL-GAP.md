# KMDW (Chicago Midway) structural gap memo

**TL;DR:** Five postprocessing techniques + GEFSv12 reforecast retraining
have all failed to close KMDW's Brier-vs-NDFD gap to within the
Phase 5 #2 bar. The remaining gap is **structural**, not
recalibratable. Forward options are (a) accept a 5-of-6 success bar
in place of all-6, (b) add a Lake Michigan / convective-environment
predictor that NDFD has and we don't, or (c) defer KMDW for v1 and
trade the other five stations only. **Recommendation: (c) for v1
ship; revisit (b) post-Phase-5.**

## What we tried

| Technique | KMDW Brier-vs-NDFD | Δ vs prior | Verdict |
|---|---|---|---|
| Pure-NGR baseline | -67.1 % | (start) | Fails |
| + Isotonic recal (PR #14) | -52.1 % | +14 pp | Still fails |
| + Skew-normal NGR (PR #15) | ~ -52 % | unchanged | Wing-Δ unchanged at our scale |
| + Climatology blend at lead 1 (PR #16) | -76 % to -52 % | Net-negative | Default-off; reverts |
| + Maker/taker policy (PR #17) | -52 % (Brier unchanged; PnL impact only) | 0 pp Brier | Orthogonal to skill |
| + GEFSv12 reforecast NGR (PR #19/#21/#22 + Path B) | ~ -52 % | ±1-6 pp | Cross-model-family mismatch dominates |
| + Calibration-aware router (PR #28) | -52 % at KMDW | unchanged | Router can't pick a winning leg if no leg wins |
| + Conformal coverage (PR #32) | n/a (different metric) | KMDW empirical-coverage 87 % at α=0.1 | Diagnostic, not skill upgrade |

The pattern: every postprocessing technique is **calibration**
machinery (isotonic, skew, climatology blend, conformal). KMDW's
gap is **resolution** -- our model and NDFD disagree on which days
will be hot vs cold, not just on the magnitude of the probability.
Calibration machinery can't move resolution.

## Why KMDW specifically

KMDW (Chicago Midway, 41.79°N / -87.75°E) sits in a uniquely
hard-to-forecast micrometeorology bucket relative to the other 5
stations:

- **Lake-effect Tmax**: prevailing southwest summer flow advects warm
  continental air; prevailing northeast late-fall flow advects cold
  Lake Michigan air (lake is still ~50°F when continental air is
  10°F). The 50-mile north-south swing in lake-shore boundary-layer
  depth determines Tmax. Our GEFS-via-Open-Meteo ingest has zero
  visibility into the lake's surface temperature; NDFD does
  (NWS-internal lake-surface-temperature analyses ingested via
  RTMA).
- **Convective complexes**: Midwest summer thunderstorms cap Tmax by
  triggering at noon and shutting down further surface heating.
  Convective outflow boundaries from morning storms 100+ miles
  away modify Tmax 6 h later in ways our 0.25° GFS doesn't see.
- **Polar-vortex intrusions**: Dec-Feb, 30-50°F day-over-day Tmax
  swings on cold-air-mass arrivals. Our continuous-Gaussian-tail NGR
  systematically misses these even with skew-normal -- the swings
  are 3-4σ events from steady-state, not a tail-shape problem.

KAUS (Austin) has a milder version of the same problem (Gulf
moisture vs. dry-line position). KDEN, KJFK, KLAX, KMIA all have
much narrower micrometeorology that GFS gridded data captures
adequately at 0.25°.

## Forward options

### (a) Lower the bar from "all 6 stations" to "5 of 6"

**Pros:** Phase 5 #2 + #3 flip green immediately on the existing
five-station envelope (KJFK, KLAX, KMIA, KDEN, KAUS where
calibration-aware router is making positive progress). No new code.

**Cons:** Sets a precedent where "structural gap" = "drop the
station." If we ship and KAUS develops a similar gap, we're at 4 of
6. Plus, the original CLAUDE.md §5 #2 wording is "Brier ≥ 5 % better
than raw on backtest" *across stations* -- if we mean "across the
ones we trade," we should re-word the criterion explicitly so future-us
isn't reading the original text and assuming all 6.

### (b) Add a lake-shore / convective-environment feature

**Pros:** The right fix. Adds a real predictor (Lake Michigan SST,
or a CAPE-based convective-cap proxy from the GFS sounding) that
addresses the structural gap. Could also lift KAUS via the same
Gulf-moisture mechanism.

**Cons:** Multi-PR effort. Requires an additional ingest path
(RTMA lake SST or GFS upper-air sounding), feature engineering, and
re-fit of every model that consumes weather features. Realistic
1-2 month timeline; not load-bearing for v1 ship. Revisit
post-Phase-5.

### (c) Trade the other 5 stations for v1; defer KMDW

**Pros:** Operationally simplest. The router already has the
infrastructure to pick a "no-trade" leg per station -- we just
configure KMDW to "no-trade" for v1, document this is intentional,
and move on. The four-of-five bar still meets the Phase 5 #2
"≥ 4 of 6 stations" reformulation that the active ROADMAP language
already uses.

**Cons:** Slightly cosmetic; if a Kalshi user looks at our system
they'll see KMDW trades blank while the other five fire. Flag this
in the dashboard's data-freshness panel so the silence isn't
mistaken for a bug.

## Recommendation

**Adopt option (c) for v1.** Configure the router to "no-trade" KMDW
explicitly (not silently). Document in the bankroll plan that v1
trades 5 of 6 weather stations. Keep the GEFSv12 reforecast path
warm + the lake-SST / CAPE feature work in v2 backlog -- when we
revisit, the option (b) work picks up where it leaves off.

**Phase 5 #2 + #3 reformulation:** the active ROADMAP wording is
already "≥ 4 of 6 stations" (the original "all 6" was unrealistic
in the v1 deployability filter). This memo justifies the
reformulation explicitly so future audits don't keep re-debating.

## Where this is referenced

- [`ROADMAP.md`](../../ROADMAP.md) Phase 5 #2 + #3 readiness rows.
- [`docs/BANKROLL-PLAN.md`](../BANKROLL-PLAN.md) -- v1 trades 5 of 6
  weather stations (no-KMDW configured router).
- [`docs/research/PASS-1-EXTENSION-EMOS-EXECUTION.md`](PASS-1-EXTENSION-EMOS-EXECUTION.md)
  item #6 (GEFSv12) -- still warm for the v2 lake-SST / CAPE re-attempt.
