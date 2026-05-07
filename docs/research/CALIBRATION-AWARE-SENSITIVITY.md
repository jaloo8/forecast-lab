# Calibration-aware router — tolerance sensitivity analysis

> Auxiliary research note. Documents the post-PR #28 sensitivity sweep on
> `CALIBRATION_AWARE_BRIER_TOLERANCE_PP`, the hysteresis margin that
> protects the active config from picking a calibration-passing strategy
> whose Brier-vs-NDFD is too far below the overall leader.
>
> **TL;DR:** 5pp default is correctly calibrated. Only KDEN's flip
> (ngr → reforecast) is robust across the realistic tolerance range
> [2pp, 15pp]. Other stations would only flip at absurd tolerances
> (50pp+) where the Brier sacrifice would be catastrophic. The
> mechanism is doing its job.

## Methodology

The sweep is analytic, not empirical. `decide_strategies_calibration_aware()`
is a pure function of the four backtest manifests + the tolerance
parameter — it doesn't need the backtest to be re-run to predict its
output. Calling the function with different tolerance values against the
on-disk manifests produces an O(seconds) sweep vs. O(hours) for a full
backtest re-run per parameter point.

The manifests used: `models/backtest_{manifest,all_raw_manifest,reforecast_manifest}.json`,
generated in PRs #25, #28, and the post-#22 audit-fix regen. Each contains
`brier_improvement_vs_ndfd_pct` + `reliability_summary.passes_bar` per
station.

## Sweep result

| tolerance_pp | KAUS | KDEN | KJFK | KLAX | KMDW | KMIA |
|---|---|---|---|---|---|---|
| 0.5 | raw | ngr | ngr | raw | raw | raw |
| 1.0 | raw | ngr | ngr | raw | raw | raw |
| 2.0 | raw | **reforecast** | ngr | raw | raw | raw |
| 3.0 | raw | reforecast | ngr | raw | raw | raw |
| **5.0 (default)** | raw | **reforecast** | ngr | raw | raw | raw |
| 8.0 | raw | reforecast | ngr | raw | raw | raw |
| 15.0 | raw | reforecast | ngr | raw | raw | raw |
| 50.0 | raw | reforecast | **reforecast** | **reforecast** | raw | raw |

## Per-station rationale

**KAUS:** No strategy clears the n-aware reliability bar. Falls through to NDFD-aware. NGR-vs-NDFD = -14.54%, RAW-vs-NDFD = -14.47%; difference is -0.07pp, well below the 1pp threshold → raw wins NDFD-aware. Stable across the entire tolerance range (calibration step is a no-op when no candidate exists).

**KDEN:** ngr passes 0/calibration; reforecast passes calibration with brier-vs-ndfd = -2.89% (vs leader ngr at -1.87%, gap = 1.02pp). At tolerance ≥ 2pp, the calibration-aware rule prefers reforecast. The 5pp default is in the middle of the robust regime.

**KJFK:** ngr leads at -1.96%; reforecast catastrophically fails the resolution side at -40.34% (gap = 38.4pp). Reforecast also passes calibration. At realistic tolerances (≤15pp), the gap is too large → fallback picks ngr. Only at 50pp+ does the rule pick reforecast — clearly the wrong call (we'd trade ~38pp of Brier for a calibration win).

**KLAX:** raw leads at +40.79%; reforecast at +5.38% (gap = 35.4pp). Same dynamics as KJFK — reforecast passes calibration but is far below the leader. Realistic tolerances pick raw via NDFD-aware fallback.

**KMDW, KMIA:** No strategy passes the calibration bar. NDFD-aware fallback picks raw at both. Tolerance is irrelevant.

## What this tells us

1. **The 5pp default is correctly tuned.** It's in the middle of the [2pp, 15pp] regime where KDEN flips and other stations stay where ndfd-aware put them. Lower (≤1pp) loses the KDEN flip; higher (≥50pp) introduces catastrophic-Brier picks.

2. **Only one station (KDEN) has a station-strategy combination where calibration and resolution disagree just enough to be worth flipping.** The other failing-calibration stations either fail across the board (KMDW, KMIA, KAUS) or have a calibration-passing alternative whose Brier cost is unacceptable (KJFK, KLAX).

3. **No tolerance setting will get us to 4/6 stations passing calibration under the current model lineup.** The post-#28 status (1/6) is a structural ceiling, not a tunable parameter. Closing the gap requires new model variants:
   - **Per-station fold-fit reforecast NGRs** (currently a single global fit) — could improve calibration where the 1-fit ensemble is misspecified
   - **Hierarchical Bayesian pooling** across stations — should help mid-range buckets at thin-data stations
   - **Conformal prediction wrappers** — distribution-free calibration guarantees on top of any base model
   - **Skew-normal at long lead** — current default is lead 1; lead 5-7 adds wing mass that quantile-binning is sensitive to

## What this does NOT tell us

The sensitivity sweep is purely about the **decision rule** ("which strategy
does the router pick?"). It does not measure:

- **Live P&L impact** of the KDEN flip — needs paper-trading data
- **Whether the calibration-aware decision generalizes out-of-sample** —
  current evaluation is on the same OOS window the decision was tuned on;
  a clean re-run on a forward window would be more honest
- **Whether `min_n=100` for the n-aware reliability is itself tuned correctly**
  — separate sensitivity question; quick win to add as a follow-up

## Next sensitivity sweeps worth running

1. **n-aware `min_n` threshold** — does dropping from 100 to 50 (or 200)
   change the candidate set materially?
2. **`MIN_BRIER_IMPROVEMENT_PCT`** — the legacy 1pp threshold for picking
   ngr over raw. Is 1pp the right number, or is 0.5pp / 2pp better?
3. **Quantile-binning vs equal-width** — do the two binning schemes
   ever disagree on `passes_bar`? If so, that's a measurement question
   we should resolve.
