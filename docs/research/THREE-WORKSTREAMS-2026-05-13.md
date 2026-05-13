# Three workstreams: Analog Ensembles, NBA Meta-Labeling, NBM qmd Phase 2

**Status:** design spec — implementation **deferred**. None of the code in this doc is in the repo yet. See "How to use this doc" below.

**Audience:** future Claude Code session or human implementer working on any of:

- **P1 — Analog Ensembles** for weather post-processing. Hamill & Whitaker (2006) framework with the Delle Monache et al. (2013) weighted-Euclidean metric, station-specific feature sets, CMA-ES weight learning, OOD detection via $d_k$ percentile, KDEN Chinook regime stratification. Builds on top of the existing NGR + isotonic + climatology stack — does not replace it.
- **P2 — NBA totals meta-labeling** (de Prado §3.6 adaptation). Glicko-2 pace + pace×efficiency primary model, LightGBM meta-classifier, Kelly sizing with meta-adjusted effective probability and explicit flip logic, season-block purged k-fold CV.
- **P3 — NBM qmd S3 inventory format** (Phase 2 spec for the NBM qmd Phase 1 work shipped in PR #53). S3 bucket structure, `.idx` inventory format, byte-range partial GETs for ~75× egress savings, PCHIP+Gaussian-tail quantile→CDF reconstruction.

**Provenance:** authored by the forecast-lab research team, 2026-05-13, as a follow-up to the Renaissance Technologies research artifact discussed earlier the same week. Stored verbatim from the original source document.

**Honest expected gains (paper's own §1.6 / §2.9 / §3.5):**

| Workstream | Realistic gain | Concerning if |
|---|---|---|
| **P1 AnEn** on top of NGR+isotonic | 2–5% CRPS at typical leads; 5–10% on regime-transition days; **0–2% at KMIA** | claimed >10% sustained at non-regime days |
| **P2 Meta-labeling** on NBA totals | 51% primary → ~52.5% selective hit rate; sustained CLV 0.5–1.5% | >+2.5% CLV sustained (overfit suspect) |
| **P3 NBM qmd Phase 2** | ~$0.80/mo egress at byte-range partial GETs; ~5–8% CRPS gain over raw GEFS at 1–3 day leads — **this is the benchmark to beat, not the model** | naive full-file ingest would blow the $50/mo budget |

**Phase 5 readiness implications:**

| Workstream | Which gate it moves | How |
|---|---|---|
| P1 AnEn | #2 (Brier ≥5% better) | Pushes KAUS/KMDW/KDEN closer to the ≥4-of-6-stations bar |
| P2 Meta-labeling | n/a directly; new market vertical | NBA totals are a separate Kalshi product from moneylines; would expand our trade-rate but doesn't move the current #5 metric |
| P3 NBM qmd Phase 2 | #2 (Brier ≥5% better) | Replaces our deterministic-Gaussian-wrap NDFD baseline with NBM's own quantile distribution — **changes the verdict** at KLAX/KMIA (likely shrinks) and KMDW (likely widens) |

## How to use this doc

Each of **Part 1**, **Part 2**, **Part 3** below is implementation-ready as a dedicated PR. The 12-week integrated roadmap at the bottom is the suggested sequence; you do not have to follow it strictly but the dependencies are real (e.g., the NBM benchmark in P3 week 1 is what tells you which station/lead cells P1's AnEn needs to beat).

**Before starting any implementation:**

1. Per CLAUDE.md §9, any new dependency requires explicit user sign-off. The new deps this work would introduce:
   - **P1**: `cma` (pycma; pure Python, no compile)
   - **P3 Phase 2 enhancement**: `boto3`, possibly `pyarrow` for GRIB metadata; `cfgrib` + `eccodes` already deferred per `pyproject.toml` notes
   - **P2**: `lightgbm` already in stack; no new deps
2. Each PR should ship < ~600 lines + tests, per CLAUDE.md §8 small-PR discipline.
3. Each PR must update `ROADMAP.md` per CLAUDE.md §14 ROADMAP discipline.

**This doc supersedes:** no prior doc; it's the first canonical design spec for these three workstreams.

**This doc is superseded by:** any individual implementation PR's docstring + tests, once landed. Mark superseded sections inline.

**Honest framing:** the paper distills 80% Renaissance-replicable best practice and 20% novel application of meta-labeling to fixed-settlement binary markets. The single most original contribution is the §2.4 Kelly derivation under meta-labeling with explicit flip logic. The single most operationally critical claim is §3.6 — that the partial-GET path is the difference between fitting in the $50/mo budget and not.

---

# PART 1 — Analog Ensemble Implementation for forecast-lab

## 1.1 The Analog Metric: Per-Station Feature Sets and Weight Initialization

The Delle Monache et al. (2013) metric, parametrized for predictor $i \in \{1,\dots,N_v\}$, lead time $t$, and candidate day $t'$:

$$
\Vert F_t,A_{t'} \Vert \;=\; \sum_{i=1}^{N_v} \frac{w_i}{\sigma_{f_i}} \sqrt{\sum_{j=-\tilde{t}}^{\tilde{t}} \bigl(F_{i,t+j} - A_{i,t'+j}\bigr)^2}
$$

where $w_i$ is the predictor weight, $\sigma_{f_i}$ is the standard deviation of predictor $i$ over the training archive (per lead time), and $\tilde t$ is the half-width of the time-tendency window. We use $\tilde t = 1$ for daily-max-temperature (12-hour analog window on each side), matching the original paper's empirical finding that the metric is insensitive above $\tilde t \geq 1$.

The GEFSv12 reforecast (2000–2019, 5 perturbed members, ~0.25° native resolution after de-staggering, FV3 dynamical core) provides ~176 upper-air and ~43 surface fields per cycle. We do **not** need 176 features. Curse of dimensionality bites hard above $d \sim 10$ — both because k-d trees degrade and because effective sample size in feature-space neighborhoods shrinks geometrically.

**Recommended per-station feature sets** (each 6–9 base features plus 2 doy features; GEFSv12 ensemble-mean evaluated at the nearest land grid point or bilinearly interpolated to station; tendency features are paired with the value feature via the $\tilde t$ window):

### KLAX — marine layer, subsidence, Santa Ana

| Feature | Weight init | Rationale |
|---|---|---|
| T2m | 0.30 | Direct target proxy |
| 850 hPa T | 0.15 | Subsidence inversion strength |
| 925 hPa T − T2m | 0.15 | Inversion lapse rate (engineered) |
| 700 hPa RH | 0.10 | Marine layer presence |
| MSLP gradient (KLAX–KEDW) | 0.15 | Santa Ana proxy (offshore pressure gradient) |
| 10m u-wind | 0.10 | Onshore/offshore wind sign |
| DSWRF | 0.05 | Marine stratus persistence |

The 925−T2m engineered inversion feature is the single highest-information feature for KLAX max-T forecast errors — NGR consistently busts on inversion-break days.

### KJFK — nor'easters, sea breeze

| Feature | Weight init |
|---|---|
| T2m | 0.30 |
| 850 hPa T | 0.15 |
| 500 hPa Z | 0.10 |
| MSLP | 0.10 |
| 10m u, v wind | 0.10 + 0.10 |
| 700 hPa RH | 0.05 |
| 1000-500 hPa thickness | 0.10 |

500 hPa Z carries the trough/ridge regime signal; thickness captures airmass type. Sea-breeze days are subtle — flag with low MSLP gradient + onshore 10m wind, but don't make it the dominant feature.

### KMDW — continental cold-air outbreaks, lake-effect

| Feature | Weight init |
|---|---|
| T2m | 0.25 |
| 850 hPa T | 0.20 |
| 1000-850 hPa thickness | 0.15 |
| 500 hPa Z | 0.10 |
| 10m wind speed | 0.10 |
| 10m v-wind | 0.10 |
| TCDC | 0.10 |

KMDW max-T is driven by 850 T advection more than at any of the other stations. Cold-air outbreak days have characteristic 850 T anomalies of −15 to −25 K; weighting 850 T at 0.20 is deliberate.

### KMIA — trade-wind regime, sea breeze, tropical

| Feature | Weight init |
|---|---|
| T2m | 0.25 |
| 850 hPa T | 0.10 |
| 10m wind speed | 0.15 |
| 10m wind direction (sin, cos) | 0.10 + 0.10 |
| 700 hPa RH | 0.15 |
| PWAT | 0.10 |
| MSLP | 0.05 |

KMIA has the weakest synoptic forcing of the six in summer. Wind direction (encoded as sin/cos of the bearing) is more diagnostic than wind speed because it picks up Bermuda High orientation. Expect the smallest AnEn gain here.

### KDEN — downslope warming, Chinook, upslope snow

| Feature | Weight init |
|---|---|
| T2m | 0.20 |
| 700 hPa T | 0.20 |
| 700 hPa u-wind | 0.20 |
| 500 hPa Z | 0.10 |
| 700-500 hPa thickness | 0.10 |
| MSLP | 0.10 |
| DSWRF | 0.10 |

KDEN is the hard station. 700 hPa T and 700 hPa u-wind together discriminate Chinook (westerly downslope) vs. upslope (easterly) regimes — these two features carry more than half the predictive power. 850 hPa is underground at Denver's elevation; **do not use it**.

### KAUS — dryline, gulf moisture, blue norther

| Feature | Weight init |
|---|---|
| T2m | 0.25 |
| 850 hPa T | 0.15 |
| 850 hPa dewpoint (TD) | 0.15 |
| 10m v-wind | 0.15 |
| MSLP gradient (E–W) | 0.10 |
| 500 hPa Z | 0.10 |
| LCL height | 0.10 |

850 TD captures the gulf moisture surge; v-wind sign captures the post-front cold airmass; the E–W MSLP gradient encodes dryline position. Norther passages create T errors of 10–20 K in raw GEFS — AnEn should add meaningful skill here.

### Weight learning via CMA-ES on CRPS

Hand weights above are **initializations**, not the final answer. Learn $\{w_i\}$ per station and per lead time on a 2014–2017 holdout by minimizing mean CRPS:

$$
\text{CRPS}(F, y) \;=\; \int_{-\infty}^{\infty} \bigl(F(x) - \mathbb{1}\{x \geq y\}\bigr)^2 dx
$$

For an empirical CDF from $k$ analog members, CRPS has the closed form (Gneiting & Raftery 2007 eq. 20):

$$
\text{CRPS}_{\text{emp}}(\{a_1,\dots,a_k\}, y) \;=\; \frac{1}{k}\sum_{i=1}^k |a_i - y| - \frac{1}{2k^2}\sum_{i=1}^k\sum_{j=1}^k |a_i - a_j|
$$

Use `cma` (the `pycma` package, pure Python, no compile) for CMA-ES over the simplex-constrained weight vector (project to $\sum w_i = 1$, $w_i \geq 0$ after each step, or parametrize as $w_i = \exp(\theta_i) / \sum_j \exp(\theta_j)$). CMA-ES handles the ~10-dimensional non-smooth objective better than Nelder-Mead, which gets stuck in local minima with this many predictors. Budget ~500 evaluations per (station × lead). On CPU this is ~2 hours per station for all lead times; do it once per quarter as a calibration job.

## 1.2 Number of Analogs $k$

Hamill & Whitaker (2006) used $k \in [75, 100]$ with a 25-year archive and gridded forecasts; Delle Monache et al. (2013) used $k \in [20, 30]$ with operational deterministic forecasts.

GEFSv12 reforecast gives you 2000–2019 = **7305 candidate days × 5 perturbed members**. After applying a ±45-day seasonal window (see §1.3), the effective pool per query is ~20 × 90 × 5 = **9000 candidates** per lead time. That's enough to support $k$ on the larger end.

**Recommended $k = 50$**, with formal leave-one-year-out CV. Procedure:

```
for each station, lead_time:
  for k in [20, 30, 50, 75, 100, 150]:
    crps_year = []
    for held_year in 2000..2019:
      train_pool = all days NOT in held_year
      for each forecast day in held_year:
        find k nearest analogs in train_pool
        compute CRPS(empirical_cdf, observed_max_T)
        crps_year.append(...)
    record mean CRPS(k)
  pick k* = argmin mean CRPS
```

Empirically you will find $k^* \in [40, 75]$ at most stations; $k = 50$ is a defensible default that you should override only at stations where CV strongly prefers something else. Increase to $k = 75$ at KMIA (weak signal, more averaging helps); decrease to $k = 30$ at KDEN (regime-specific analogs degrade fast as you add more).

## 1.3 Temporal Window and Circular DOY Encoding

Discrete ±15 (Hamill) vs. ±45 day (Delle Monache) windows trade bias against variance. For daily-max-T at our stations with a 20-year archive:

- **±15 days** = 30 × 20 = 600 candidate days. Too few once you require analogs to be also synoptically close; you'll often exhaust the pool and your $k$ nearest will be junk.
- **±45 days** = 90 × 20 = 1800 candidate days. Better, but seasonal contamination is real at continental stations (Feb candidates for Apr forecasts: 850 T climatology is shifted).

**Recommendation: Replace the hard window with a Gaussian DOY kernel weight added to the metric.** Define

$$
d_{\text{doy}}(t, t') \;=\; \min\bigl(|d - d'|,\, 365 - |d - d'|\bigr)
$$

where $d, d'$ are day-of-year. Add to the metric:

$$
\Vert F_t, A_{t'}\Vert_{\text{full}} \;=\; \Vert F_t, A_{t'}\Vert + \lambda_{\text{doy}} \cdot \frac{d_{\text{doy}}(t,t')^2}{\sigma_{\text{doy}}^2}
$$

with $\sigma_{\text{doy}} = 30$ days and $\lambda_{\text{doy}} \approx 0.5$ (also tuned via CMA-ES jointly with the predictor weights). This is mathematically equivalent to adding two features — $\sin(2\pi d/365.25)$ and $\cos(2\pi d/365.25)$ — to the metric with appropriate weights, which is the cleaner implementation:

```python
features += [np.sin(2*np.pi*doy/365.25), np.cos(2*np.pi*doy/365.25)]
```

with the corresponding weights $w_{\sin} = w_{\cos} = w_{\text{doy}}$ also CMA-ES-tuned. This sidesteps the boundary discontinuity entirely and keeps the metric Euclidean (so cKDTree still applies).

## 1.4 Search Infrastructure

Candidate space: 7305 days × 5 members = 36,525 records per station per lead time. After applying the doy weighting (which is a soft penalty rather than a hard filter), all candidates are searched. Vector dimension $d \approx 9$ after engineered features.

| Option | Build cost | Query cost (k=50, d=9, n=36K) | Verdict |
|---|---|---|---|
| `scipy.spatial.cKDTree` | O(n log n), ~50 ms | ~1–2 ms per query | **Recommended** |
| `sklearn.neighbors.BallTree` | similar | ~2–4 ms | Slower than cKDTree at d≤15 |
| `faiss.IndexFlatL2` | trivial | ~5 ms (CPU SIMD, brute-force) | Overkill for 36K points |
| Numpy broadcast brute force | 0 | ~10 ms | Cleanest code, fine for prod |

At $d = 9$ cKDTree is solidly inside its regime (degradation kicks in around $d > 15$). The break-even with brute force is around $n = 10^4$; you have $n \approx 3.6 \times 10^4$ per (station, lead), so cKDTree wins by ~5×. Build the tree once per (station, lead) at startup; persist via `pickle` and reload on container start.

Cache the standardization vector $(\mu_i, \sigma_i)$ per feature alongside the tree — these are computed from the archive and must be applied identically at query time.

## 1.5 Blending AnEn into NGR + Isotonic + Climatology

You have three components after fitting:

- $F_{\text{NGR}}(x)$: skew-normal predictive CDF (3-parameter), already isotonic-recalibrated via PAV
- $F_{\text{AnEn}}(x)$: empirical CDF from $k$ analog observations
- $F_{\text{clim}}(x)$: climatology CDF for this station/doy

Your existing stack already blends NGR with climatology at lead-time-dependent weight $\alpha(\tau)$. We add AnEn as a third component.

### Three blending strategies

**(a) BMA / EM-trained log-score weights.** Fit $\pi_1, \pi_2, \pi_3$ on a holdout by EM on the log score. **Reject.** With 3 components and a holdout of ~1500 days per station, EM collapses to a near-degenerate solution maybe 25% of the time — the skew-normal component tends to absorb everything because it's smooth and dense, leaving AnEn with $\pi \approx 0.05$. This is a known pathology in moderate-sample BMA (Raftery et al. 2005 noted >5000-sample requirement for stable 3-way mixtures).

**(b) CRPS-optimal convex combination.** Define

$$
F_{\text{blend}}(x) \;=\; w_1 F_{\text{NGR}}(x) + w_2 F_{\text{AnEn}}(x) + w_3 F_{\text{clim}}(x)
$$

with $\sum w_j = 1$, $w_j \geq 0$, fit per station and per lead time on a holdout by minimizing mean CRPS. CRPS is convex in the weights (linear-CDF combinations of proper-scoring-rule-optimal components yield a convex problem in the weights). Use `scipy.optimize.minimize` with SLSQP and simplex constraints. **This is the primary recommendation.** It's a 2-DOF problem per (station, lead) (the third weight is determined), is robust, and beats (a) by 1–3% in CRPS in our experience because it directly optimizes the production loss.

**(c) Station-conditional meta-blender.** Train a LightGBM regressor that, given current synoptic features (the same features used for AnEn metric, plus the analog distance $d_k$), outputs the blending weights. **Phase 2.** Worth doing once you have (b) running, because the gain over (b) is regime-conditional: it should help on Chinook days, Santa Ana days, and norther days, where the optimal weights legitimately differ from the marginal optimum. Use multi-output regression with softmax-projected output (or fit each weight separately and renormalize). Expect another 1–2% CRPS gain on top of (b), concentrated in regime-transition days.

## 1.6 Honest Expected CRPS Improvement

Reference points: Delle Monache et al. (2013) §4 reported AnEn CRPS reductions of ~30% vs. raw NWP for 2m T at 24–48 h, but the comparison was vs. raw ensemble, not vs. NGR+isotonic. Yang et al. (CW3E, 2024) on Sierra Nevada T2m using PRISM+GEFS shows AnEn reducing CRPS by ~1.1°C across all leads, again vs. raw not post-processed.

**Vs. your already-strong NGR+isotonic+climatology baseline, the realistic AnEn marginal gain is:**

| Lead | Median day | Regime-transition day |
|---|---|---|
| 24 h | 2–4% | 5–10% |
| 72 h | 3–5% | 5–12% |
| 120 h | 2–4% | 4–8% |
| 168 h | 1–3% | 3–6% |

Concentrated CRPS gains happen on days where the parametric skew-normal cannot represent the predictive distribution — bimodal (sea-breeze in vs. out at KMIA), heavy-tailed (Santa Ana at KLAX), or strongly truncated (dryline at KAUS). The empirical AnEn CDF handles these natively.

**At KMIA the realistic gain is 0–2%.** Synoptic forcing is too weak; do not over-promise.

## 1.7 Implementation Scaffold

```python
"""
forecast_lab/analog_ensemble.py
Implementation-ready AnEn module. CPU only, scikit-learn + scipy + cma.
"""
from __future__ import annotations
import numpy as np
import pickle, pathlib, dataclasses
from scipy.spatial import cKDTree
from scipy.stats import skewnorm
from scipy.optimize import minimize
import cma

STATION_FEATURES = {
    "KLAX": ["t2m","t850","inv_925_t2m","rh700","mslp_gradEW",
             "u10","dswrf","sin_doy","cos_doy"],
    "KJFK": ["t2m","t850","z500","mslp","u10","v10","rh700",
             "thick_1000_500","sin_doy","cos_doy"],
    "KMDW": ["t2m","t850","thick_1000_850","z500","wspd10","v10",
             "tcdc","sin_doy","cos_doy"],
    "KMIA": ["t2m","t850","wspd10","wdir_sin","wdir_cos","rh700",
             "pwat","mslp","sin_doy","cos_doy"],
    "KDEN": ["t2m","t700","u700","z500","thick_700_500","mslp",
             "dswrf","sin_doy","cos_doy"],
    "KAUS": ["t2m","t850","td850","v10","mslp_gradEW","z500",
             "lcl","sin_doy","cos_doy"],
}

INIT_WEIGHTS = {
    "KLAX": np.array([0.30, 0.15, 0.15, 0.10, 0.15, 0.10, 0.05, 0.05, 0.05]),
    "KJFK": np.array([0.30, 0.15, 0.10, 0.10, 0.10, 0.10, 0.05, 0.10, 0.05, 0.05]),
    "KMDW": np.array([0.25, 0.20, 0.15, 0.10, 0.10, 0.10, 0.10, 0.05, 0.05]),
    "KMIA": np.array([0.25, 0.10, 0.15, 0.10, 0.10, 0.15, 0.10, 0.05, 0.05, 0.05]),
    "KDEN": np.array([0.20, 0.20, 0.20, 0.10, 0.10, 0.10, 0.10, 0.05, 0.05]),
    "KAUS": np.array([0.25, 0.15, 0.15, 0.15, 0.10, 0.10, 0.10, 0.05, 0.05]),
}

@dataclasses.dataclass
class AnalogFitState:
    tree: cKDTree
    train_obs: np.ndarray              # shape (n_train,) observed max-T
    feature_mu: np.ndarray             # shape (d,)
    feature_sigma: np.ndarray          # shape (d,)
    weights: np.ndarray                # shape (d,) learned via CMA-ES
    k: int

def empirical_crps(members: np.ndarray, y: float) -> float:
    """Closed-form CRPS for ensemble forecast.
       Gneiting & Raftery 2007 eq. 20."""
    k = len(members)
    term1 = np.mean(np.abs(members - y))
    diffs = np.abs(members[:, None] - members[None, :])
    term2 = 0.5 * diffs.mean()
    return term1 - term2

class AnalogEnsemble:
    """One instance per (station, lead_time)."""
    def __init__(self, station: str, lead_h: int, k: int = 50):
        self.station = station
        self.lead_h = lead_h
        self.k = k
        self.feat_names = STATION_FEATURES[station]
        self.state: AnalogFitState | None = None

    # ---------------- fit ----------------
    def fit(self, X_train: np.ndarray, y_train: np.ndarray,
            X_holdout: np.ndarray, y_holdout: np.ndarray,
            optimize_weights: bool = True, cma_budget: int = 500):
        """
        X_train:    (n_train, d) AnEn predictor matrix (raw units)
        y_train:    (n_train,)   observed daily max-T
        X_holdout:  (n_holdout, d)
        y_holdout:  (n_holdout,)
        """
        mu = X_train.mean(axis=0)
        sigma = X_train.std(axis=0) + 1e-9
        Xz = (X_train - mu) / sigma
        w0 = INIT_WEIGHTS[self.station]
        assert len(w0) == X_train.shape[1], "weight vector / feature count mismatch"
        if optimize_weights:
            w_star = self._cma_es_weights(Xz, y_train,
                                          (X_holdout - mu) / sigma, y_holdout,
                                          w0, budget=cma_budget)
        else:
            w_star = w0
        # Build tree on weighted, standardized features (weighted-Euclidean)
        Xw = Xz * np.sqrt(w_star)
        tree = cKDTree(Xw)
        self.state = AnalogFitState(
            tree=tree, train_obs=y_train.copy(),
            feature_mu=mu, feature_sigma=sigma, weights=w_star, k=self.k,
        )
        return self

    def _cma_es_weights(self, Xz, y_train, Xz_h, y_h, w0, budget):
        def loss(theta):
            w = np.exp(theta); w = w / w.sum()         # simplex parametrization
            Xw   = Xz   * np.sqrt(w)
            Xw_h = Xz_h * np.sqrt(w)
            tree = cKDTree(Xw)
            crps_sum = 0.0
            for i, x in enumerate(Xw_h):
                _, idx = tree.query(x, k=self.k)
                members = y_train[idx]
                crps_sum += empirical_crps(members, y_h[i])
            return crps_sum / len(y_h)
        es = cma.CMAEvolutionStrategy(np.log(w0 + 1e-3), 0.5,
                                       {"maxfevals": budget, "verbose": -9})
        es.optimize(loss)
        w = np.exp(es.result.xbest)
        return w / w.sum()

    # -------------- predict --------------
    def predict_members(self, x_query: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Return (k analog observations, k distances)."""
        assert self.state is not None, "fit first"
        s = self.state
        xz = (x_query - s.feature_mu) / s.feature_sigma
        xw = xz * np.sqrt(s.weights)
        dists, idx = s.tree.query(xw, k=s.k)
        return s.train_obs[idx], dists

    def predict_cdf(self, x_query: np.ndarray, eval_grid: np.ndarray) -> np.ndarray:
        """Empirical CDF evaluated on eval_grid."""
        members, _ = self.predict_members(x_query)
        return np.searchsorted(np.sort(members), eval_grid, side="right") / len(members)


class BlendedCDF:
    """CRPS-optimal convex blend of NGR + AnEn + Climatology (Strategy b)."""
    def __init__(self):
        self.w = np.array([1/3, 1/3, 1/3])

    def fit(self, ngr_cdfs, anen_cdfs, clim_cdfs, y_obs, grid):
        """
        cdfs: list of length n_holdout, each item np.ndarray shape (len(grid),).
        y_obs: (n_holdout,) observations.
        """
        def crps_from_cdf(cdf, y):
            indicator = (grid >= y).astype(float)
            return np.trapz((cdf - indicator) ** 2, grid)
        def objective(w):
            w = np.clip(w, 0, None); w = w / w.sum()
            total = 0.0
            for i in range(len(y_obs)):
                blend = w[0]*ngr_cdfs[i] + w[1]*anen_cdfs[i] + w[2]*clim_cdfs[i]
                total += crps_from_cdf(blend, y_obs[i])
            return total / len(y_obs)
        cons = [{"type":"eq", "fun": lambda w: w.sum() - 1.0}]
        bnds = [(0, 1)] * 3
        res = minimize(objective, self.w, method="SLSQP",
                       constraints=cons, bounds=bnds,
                       options={"ftol": 1e-7, "maxiter": 200})
        self.w = res.x
        return self

    def predict(self, ngr_cdf, anen_cdf, clim_cdf):
        return self.w[0]*ngr_cdf + self.w[1]*anen_cdf + self.w[2]*clim_cdf


# ---------------- integration with existing router ----------------

class PerStationForecaster:
    """Routes through NGR -> AnEn -> blend, replacing/augmenting your existing call site."""
    def __init__(self, station, lead_h):
        self.station = station
        self.lead_h = lead_h
        self.ngr = None             # your existing NGR+isotonic estimator
        self.anen = AnalogEnsemble(station, lead_h)
        self.clim = None            # your existing climatology estimator
        self.blender = BlendedCDF()

    def predict(self, gefs_features_today: np.ndarray, eval_grid: np.ndarray):
        # 1. parametric skew-normal CDF from NGR (already isotonic-recalibrated)
        sn_params = self.ngr.predict_params(gefs_features_today)  # (loc, scale, a)
        ngr_cdf = skewnorm.cdf(eval_grid, a=sn_params[2],
                                          loc=sn_params[0], scale=sn_params[1])
        # 2. analog ensemble empirical CDF
        anen_cdf = self.anen.predict_cdf(gefs_features_today, eval_grid)
        # 3. climatology CDF
        clim_cdf = self.clim.predict_cdf(eval_grid)
        # 4. blend
        return self.blender.predict(ngr_cdf, anen_cdf, clim_cdf)
```

The router integration assumes your existing per-station strategy already returns a CDF on a price-aligned eval grid for each Kalshi temperature contract. The `PerStationForecaster.predict` returns the same shape; existing maker-order-first execution and 0.15× Kelly sizing stay identical.

## 1.8 Failure Modes and Production Diagnostics

### OOD detection via $d_k$ percentile

For every query, the $k$-th nearest distance $d_k$ is a free OOD signal. Maintain the empirical distribution of $d_k$ from a rolling 365-day window per (station, lead). Define

$$
\text{OOD}_t \;=\; \mathbb{1}\bigl\{ d_k(t) > Q_{0.95}(d_k \mid \text{rolling 365d}) \bigr\}
$$

When `OOD_t = 1`:

1. Up-weight the climatology component in the blend by 50% (renormalize).
2. Halve the Kelly fraction for that contract that day.
3. Log to the diagnostics dashboard.

```python
def ood_flag(d_k_today, d_k_history, q=0.95):
    return d_k_today > np.quantile(d_k_history, q)
```

### KDEN conditioning on Chinook flag

KDEN errors bimodal-ize on Chinook vs. upslope days. Engineer a regime flag pre-search:

```python
def kden_regime(u700, mslp_grad_EW):
    # Chinook: westerly 700 hPa flow + Plains-side high pressure
    if u700 > 8.0 and mslp_grad_EW > 1.5:  # hPa per 5° longitude
        return "chinook"
    elif u700 < -3.0:
        return "upslope"
    return "neutral"
```

Maintain three separate cKDTrees at KDEN, one per regime. Route queries by the regime flag computed from the current GEFS forecast. This is messy but adds another 2–4% CRPS at KDEN beyond the un-stratified model, and prevents the catastrophic 8–15 K busts that the unconditional model produces on Chinook break days.

### Production monitoring

Daily report per (station, lead):

| Metric | Definition | Alert threshold |
|---|---|---|
| Mean CRPS (30d rolling) | Mean over 30d window | >10% above prior 365d mean |
| PIT histogram p-value | Chi-square uniformity test | p < 0.01 |
| $d_k$ p99 | 99th pct of $d_k$ in 30d | >2× 365d p99 |
| Blend weight $w_2$ (AnEn) | Effective weight on holdout refit | drift > 0.15 from prior refit |
| OOD rate | Fraction of days with OOD flag | >10% in any 30d window |
| Chinook fraction (KDEN only) | Chinook days / total | for context only |

The PIT histogram is the single most diagnostic plot. AnEn integrated correctly should keep PIT roughly uniform; under-dispersion (U-shape) means AnEn is too tight (k too small, or weights overfit), over-dispersion (hump) means too loose (k too large, or seasonal contamination from weak doy weight).

```python
def pit_value(cdf_fn, y_obs):
    return cdf_fn(y_obs)

def pit_uniformity_chisq(pit_values, n_bins=10):
    from scipy.stats import chisquare
    counts, _ = np.histogram(pit_values, bins=n_bins, range=(0,1))
    expected = np.full(n_bins, len(pit_values)/n_bins)
    return chisquare(counts, expected).pvalue
```

---

# PART 2 — Meta-Labeling for NBA Totals on Kalshi

## 2.1 Primary Model: Glicko-2 Pace + Efficiency

Kalshi NBA totals settle binary at game end based on actual total points vs. line. No path, no time-out, no triple-barrier. The de Prado Ch. 3 machinery does not transfer directly. The correct adaptation is **meta-labeling** (de Prado §3.6): a primary model produces a directional signal; a secondary model decides whether to take the bet and how big.

### Primary model construction

Two coupled components per team:

**(i) Glicko-2 pace rating.** Pace = possessions per 48 min, league average ~99 in 2024-25. Treat team pace as a latent rating $\rho_T$ with rating volatility, updated game-by-game in the Glicko-2 framework. The output for game $(A \text{ vs } B)$:

$$
\hat{P}_{AB} \;=\; \frac{\rho_A + \rho_B}{2} + \beta_{\text{home}} \cdot \mathbb{1}\{A \text{ home}\} + \delta_{\text{league}}(t)
$$

with $\delta_{\text{league}}(t)$ a slowly-varying season-to-date league pace adjustment (e.g., a 30-game rolling mean of league pace anomaly — captures rule changes, ref crew effects, fatigue trends).

**(ii) Offensive/defensive efficiency.** Each team has $O_T$ (points per 100 possessions, on offense) and $D_T$ (points allowed per 100 possessions, on defense), with home/away splits, regressed to league mean with shrinkage proportional to $1 / \sqrt{n_{\text{games}}}$. Predicted total:

$$
\widehat{T}_{AB} \;=\; \hat{P}_{AB} \cdot \frac{(O_A^{\text{off}} + D_B^{\text{def}}) + (O_B^{\text{off}} + D_A^{\text{def}})}{2 \cdot 100}
$$

Add a residual variance term $\sigma^2_{\text{total}} \approx (12 \text{ pts})^2$ estimated from training residuals, treat as Gaussian, output:

$$
P(\text{total} > L \mid \text{features}) \;=\; 1 - \Phi\!\left(\frac{L - \widehat T_{AB}}{\sigma_{\text{total}}}\right)
$$

This is your **primary probability** $p$.

## 2.2 Secondary (Meta) Model

A LightGBM binary classifier that ingests:

- The primary $p$
- Additional context features (see §2.5)
- Engineered confidence feature $c = 2|p - 0.5|$

Outputs $q = P(\text{primary signal is correct} \mid \text{features})$.

The pattern is exactly de Prado §3.6: the primary model decides direction; the meta-model decides whether the primary is trustworthy on this specific game.

## 2.3 Labeling Scheme

Position direction is forced by the primary:

- If $p > 0.5$, intended position is **YES** (over).
- If $p < 0.5$, intended position is **NO** (under).

Label:

$$
\ell \;=\; \mathbb{1}\bigl\{(p > 0.5 \wedge \text{total} > L) \vee (p < 0.5 \wedge \text{total} < L)\bigr\}
$$

Confidence signal as feature: $c = 2|p - 0.5| \in [0, 1]$.

The meta-model is trained on $\ell$ with $p$ (or $c$) plus context features. **Never** train the meta-model on the same data used to fit the primary — train primary on seasons $S_1 \dots S_{k-1}$, meta-model on out-of-sample primary predictions for season $S_k$, with the canonical purged-by-season CV described in §2.6.

## 2.4 Position Sizing: Kelly Derivation under Meta-Labeling

This needs to be derived carefully. The user specified: given primary edge $p$ and meta-model probability $q$, the effective edge is $q \cdot p + (1-q)(1-p)$. Here is the derivation.

### Setup

The primary model picks a side (the side it believes is more likely):

$$
s = \begin{cases} \text{YES} & p > 0.5 \\ \text{NO} & p < 0.5 \end{cases}
$$

Conditional on a primary-picked direction $s$, define:

- $p^* = \max(p, 1-p)$ = the primary's stated probability that side $s$ wins
- $q$ = meta-model's probability that the primary is **correct on this specific instance**

The meta-model is a meta-judgment about the *truthfulness* of the primary signal — it is **not** an alternative probability over the underlying event.

### Effective probability that side $s$ wins

There are two possibilities:

1. **Primary is correct** (probability $q$): then the underlying probability of side $s$ winning is $p^*$, drawn from a population where the primary's signal is reliable.
2. **Primary is wrong** (probability $1-q$): then the underlying conditional distribution puts probability $1-p^*$ on side $s$ winning.

Therefore the effective win probability for the position the primary recommends is:

$$
\boxed{\,P_{\text{eff}}(s \text{ wins}) \;=\; q \cdot p^* + (1-q)\cdot (1-p^*)\,}
$$

This is exactly the user's stated formula (with $p = p^*$ after the primary picks its side). Note three regimes:

1. **$q > 0.5$:** Meta-model says primary is more often right than wrong. $P_{\text{eff}} > 0.5$ iff $p^* > 0.5$, which holds by construction (primary picked the higher-probability side). Take position $s$.
2. **$q \approx 0.5$:** Meta-model is uninformative. $P_{\text{eff}} \to 0.5$. Skip the bet.
3. **$q < 0.5$:** Meta-model believes the primary is **systematically wrong** on this kind of game. $P_{\text{eff}} < 0.5$, meaning the opposite side has higher effective probability. Flip the position to $\bar s$ with effective probability $1 - P_{\text{eff}} = q(1-p^*) + (1-q) p^*$.

### Kelly fraction

Kalshi YES contracts trade at price $b \in (0,1)$ and pay $1 - b$ on win, $-b$ on loss (per contract held). Equivalently the payout ratio is $(1-b)/b$ to 1. The Kelly criterion for a bet with win probability $\pi$ and payout ratio $\beta$ is:

$$
f^* \;=\; \frac{\pi \beta - (1-\pi)}{\beta}
$$

With $\beta = (1-b)/b$ this simplifies to:

$$
f^* \;=\; \pi - \frac{(1-\pi)b}{1-b} \;=\; \frac{\pi - b}{1 - b}
$$

Substituting the meta-adjusted effective probability:

- If $P_{\text{eff}} > 0.5$ (take primary side $s$ at Kalshi price $b_s$):

$$
f^*_{\text{primary-side}} \;=\; \frac{(q \, p^* + (1-q)(1-p^*)) - b_s}{1 - b_s}
$$

- If $P_{\text{eff}} < 0.5$ (flip to $\bar s$ at price $b_{\bar s} = 1 - b_s$ approximately, ignoring spread):

$$
f^*_{\text{flip}} \;=\; \frac{(q\,(1-p^*) + (1-q)\,p^*) - b_{\bar s}}{1 - b_{\bar s}}
$$

Apply 0.15× fractional Kelly:

$$
f_{\text{deployed}} \;=\; 0.15 \cdot \max(0, f^*)
$$

### Practical gates

Don't flip on low-confidence meta-model output — calibration error in the meta-model can produce false-confident flips that destroy P&L. Gate flipping behind: (i) meta-model out-of-fold Brier score below a threshold, (ii) $|q - 0.5| > 0.15$. The skip band is $q \in [0.42, 0.58]$ in our default tuning.

```python
def kelly_meta(p_primary, q_meta, kalshi_price_yes, frac=0.15,
               skip_band=(0.42, 0.58), flip_min_conf=0.15):
    # Primary picks side
    if p_primary >= 0.5:
        side_primary, p_star, b = "YES", p_primary, kalshi_price_yes
    else:
        side_primary, p_star, b = "NO", 1 - p_primary, 1 - kalshi_price_yes

    # Effective probability that primary side wins
    P_eff_primary = q_meta * p_star + (1 - q_meta) * (1 - p_star)

    # Skip band
    if skip_band[0] <= q_meta <= skip_band[1]:
        return 0.0, side_primary, "skip"

    if P_eff_primary >= 0.5:
        edge = P_eff_primary - b
        side = side_primary
    else:
        # Flip
        if abs(q_meta - 0.5) < flip_min_conf:
            return 0.0, side_primary, "low_conf_no_flip"
        side = "NO" if side_primary == "YES" else "YES"
        b_flip = 1 - b
        P_eff_flip = 1 - P_eff_primary
        edge = P_eff_flip - b_flip

    if edge <= 0:
        return 0.0, side, "no_edge"
    return frac * edge / (1 - b if side == side_primary else 1 - (1 - b)), side, "active"
```

## 2.5 Feature Engineering for NBA Totals

| Feature | Source | Use in primary | Use in meta |
|---|---|---|---|
| Team pace rating (Glicko-2) | derived | ✓ | ✓ |
| Off / Def efficiency (home/away splits) | derived | ✓ | ✓ |
| Last 5 / 10 / 20 game pace | rolling | ✓ | ✓ |
| Rest days (team A, team B) | schedule | — | ✓ |
| Back-to-back flag | schedule | — | ✓ |
| 3-in-4-nights flag | schedule | — | ✓ |
| Travel distance from previous venue | great-circle | — | ✓ |
| Days into season | calendar | ✓ | ✓ |
| League-avg pace 30d rolling | derived | ✓ | — |
| Injury minutes affected | ESPN/BR injury | — | ✓ |
| Ref crew pace tendency | NBA officials data | ✓ | ✓ |
| Vegas opening total | sportsbook | ✓ (yes) | ✓ |
| Pinnacle opening total | Pinnacle | ✓ (yes) | ✓ |
| Pinnacle closing total | Pinnacle | **NEVER as input** | **NEVER as input** |

### The Vegas line as feature: lookahead trap

The **opening line** is fair game — it exists before you'd place a bet. The **closing line** is not — it incorporates information (sharp action, late injury news) that you would not have at bet placement. Closing line is your **target / CLV benchmark only**.

A subtler trap: even the opening line is a function of the bookmaker's model, which has been trained on outcomes you may also have in your training set (no real-world leakage there). But if you collect "opening line" from a data vendor that retroactively backfills with closing line on missing rows, you have a covert leak. Audit your line data: histogram open-vs-close differences; if your "opening line" matches closing-line statistics, the vendor is lying.

Treat your closing-line ingestion as a one-way pipe: written only to a separate `clv_facts` table that the training pipeline cannot read.

## 2.6 Cross-Validation: Purged k-Fold by Season

CPCV is the right framework but the right block is **the season**, not the individual game.

- Inside a season, team ratings are co-dependent — each game's label updates the priors used in the next game's features. Standard CV would leak season-specific dynamics across folds.
- Embargo within season: 0 days (no need — the rating-update mechanism is the only carrier of leakage, and you'll either include all of a season or none of it).
- Embargo across seasons: 0 days (off-season ~4 months provides natural separation).

Recommended scheme: **5-fold purged by season** with all available seasons (typically 2015-16 through current). Each fold holds out one season; the meta-model is fit on the four others, evaluated on the held-out one. Rotate.

```python
def season_cv_splits(season_index_per_game, n_folds=5):
    seasons = np.unique(season_index_per_game)
    fold_assignment = {s: i % n_folds for i, s in enumerate(seasons)}
    splits = []
    for fold in range(n_folds):
        test_seasons = [s for s in seasons if fold_assignment[s] == fold]
        train_mask = ~np.isin(season_index_per_game, test_seasons)
        test_mask  =  np.isin(season_index_per_game, test_seasons)
        splits.append((np.where(train_mask)[0], np.where(test_mask)[0]))
    return splits
```

There is one subtle issue: if your Glicko-2 rating system has cross-season carryover (which it should — team identity persists), then a model fit on 2018-21 and evaluated on 2022 *is* using 2022-relevant team-rating information as a feature. This is correct and not a leak — the feature is "rating at game time", computed only from games before game time. Make sure your data pipeline materializes ratings causally (sort by game time, update sequentially) and not retrospectively.

## 2.7 CLV Measurement Infrastructure

CLV (closing line value) is the only honest near-term proof that your model has edge before P&L results stabilize over hundreds of bets.

Build *before* placing any real bets:

1. **Pinnacle line ingestion** at open and close for every NBA game (Pinnacle is the consensus sharp book; their close is the best proxy for true probability). Use Pinnacle's REST API (paid) or an aggregator like the-odds-api ($30/mo within budget).
2. **Bet placement timestamp** persisted with millisecond precision.
3. **Implied probability** computed from both your placed Kalshi price and the closing Pinnacle line (de-vigged via power method or proportional method — use proportional for simplicity).
4. Per-bet **signed CLV**:

$$
\text{CLV}_{\text{bet}} \;=\; \text{sign}(\text{position}) \cdot \bigl( p^{\text{impl,close}}_{\text{Pinnacle}} - p^{\text{impl,placed}}_{\text{Kalshi}}\bigr)
$$

5. Aggregate diagnostics:

   - **Mean CLV** (target: 0.5–1.5%)
   - **Hit rate above closing line** (target >55%)
   - **Sharpe of CLV per bet** (target >1.0 over 200+ bets)

**Honest framing:** A model with sustained +1% CLV over 200+ bets at 0.15× Kelly with proper bankroll management is at the boundary of professional-quality. +2% sustained is rare and indicates either a temporary inefficiency or proprietary information. **+3% sustained on public-data-only is almost certainly overfit** — audit aggressively. Public data + Vegas-line-as-feature gives you only the diffuse "I trained on more recent regimes" edge; that's worth maybe a few tenths of a percent CLV honestly.

## 2.8 NBA Pseudocode

```python
"""
forecast_lab/nba.py
NBA totals primary + meta-label pipeline, CPU-only.
"""
import numpy as np, pandas as pd
import lightgbm as lgb
from dataclasses import dataclass
from scipy.stats import norm

# --------------- Glicko-2 pace ---------------

@dataclass
class GlickoState:
    rating: float = 99.0        # initial league avg pace
    rd: float = 35.0            # rating deviation
    sigma: float = 0.06         # volatility

class NBAGlickoModel:
    """Glicko-2 ratings for team pace (regression variant)."""
    Q = np.log(10)/400
    TAU = 0.5
    def __init__(self):
        self.teams: dict[str, GlickoState] = {}
    def get(self, team): return self.teams.setdefault(team, GlickoState())
    def update(self, team_a, team_b, observed_pace):
        # Regression variant: rate against a latent quantity (Glickman 2012)
        sa, sb = self.get(team_a), self.get(team_b)
        mu_pred = (sa.rating + sb.rating) / 2
        resid = observed_pace - mu_pred
        for s in (sa, sb):
            g = 1 / np.sqrt(1 + 3 * (self.Q * s.rd / np.pi) ** 2)
            s.rating += 0.5 * g * resid
            s.rd = np.sqrt(max(35.0 ** 2,
                               s.rd ** 2 + s.sigma ** 2 - 0.5 * g ** 2 * s.rd ** 2))
    def predict_pace(self, team_a, team_b, home=None, league_anomaly=0.0):
        sa, sb = self.get(team_a), self.get(team_b)
        beta_home = 1.5 if home == team_a else (-1.5 if home == team_b else 0.0)
        return (sa.rating + sb.rating) / 2 + beta_home + league_anomaly

# --------------- Pace x Efficiency ---------------

class PaceEfficiencyModel:
    def __init__(self, glicko: NBAGlickoModel, sigma_total: float = 12.0):
        self.g = glicko
        self.sigma_total = sigma_total
        self.eff = {}  # team -> dict of O/D home/away + n_games
    def update(self, team_a, team_b, pts_a, pts_b, pace, home):
        self.g.update(team_a, team_b, pace)
        for t, pts, opp_pts, is_home in [
            (team_a, pts_a, pts_b, home == team_a),
            (team_b, pts_b, pts_a, home == team_b),
        ]:
            e = self.eff.setdefault(t, dict(O_home=113.0, O_away=113.0,
                                              D_home=113.0, D_away=113.0,
                                              n_games=0))
            ortg = pts / pace * 100
            drtg = opp_pts / pace * 100
            tau = 1 / (e["n_games"] + 20)  # shrinkage
            if is_home:
                e["O_home"] = (1-tau)*e["O_home"] + tau*ortg
                e["D_home"] = (1-tau)*e["D_home"] + tau*drtg
            else:
                e["O_away"] = (1-tau)*e["O_away"] + tau*ortg
                e["D_away"] = (1-tau)*e["D_away"] + tau*drtg
            e["n_games"] += 1
    def predict_prob_over(self, team_a, team_b, line, home, league_anomaly):
        pace = self.g.predict_pace(team_a, team_b, home=home,
                                    league_anomaly=league_anomaly)
        ea = self.eff.get(team_a, dict(O_home=113, O_away=113, D_home=113, D_away=113))
        eb = self.eff.get(team_b, dict(O_home=113, O_away=113, D_home=113, D_away=113))
        oa = ea["O_home"] if home == team_a else ea["O_away"]
        ob = eb["O_home"] if home == team_b else eb["O_away"]
        da = ea["D_home"] if home == team_a else ea["D_away"]
        db = eb["D_home"] if home == team_b else eb["D_away"]
        pred_total = pace * ((oa + db) + (ob + da)) / (2 * 100)
        return 1 - norm.cdf((line - pred_total) / self.sigma_total), pred_total

# --------------- Meta-label classifier ---------------

class MetaLabelClassifier:
    def __init__(self):
        self.model = lgb.LGBMClassifier(
            n_estimators=400, learning_rate=0.03, num_leaves=31,
            max_depth=-1, min_data_in_leaf=50, feature_fraction=0.8,
            bagging_fraction=0.8, bagging_freq=5,
            reg_alpha=0.1, reg_lambda=0.5, n_jobs=-1, verbose=-1,
        )
    def fit(self, X_context, p_primary, y_outcome_total, lines):
        intended_side = (p_primary > 0.5).astype(int)
        won = ((intended_side == 1) & (y_outcome_total > lines)) | \
              ((intended_side == 0) & (y_outcome_total < lines))
        label = won.astype(int)
        feat = np.column_stack([p_primary, np.abs(p_primary - 0.5)*2, X_context])
        self.model.fit(feat, label)
        return self
    def predict_q(self, X_context, p_primary):
        feat = np.column_stack([p_primary, np.abs(p_primary - 0.5)*2, X_context])
        return self.model.predict_proba(feat)[:, 1]

# --------------- Kelly Sizer w/ flip logic (see §2.4 derivation) ---------------

class KellySizer:
    def __init__(self, fraction=0.15, skip_band=(0.42, 0.58),
                 flip_min_conf=0.15):
        self.fraction = fraction
        self.skip_lo, self.skip_hi = skip_band
        self.flip_min_conf = flip_min_conf
    def size(self, p_primary, q_meta, kalshi_yes_price):
        if p_primary >= 0.5:
            side_primary, p_star, b = "YES", p_primary, kalshi_yes_price
        else:
            side_primary, p_star, b = "NO", 1 - p_primary, 1 - kalshi_yes_price
        if self.skip_lo <= q_meta <= self.skip_hi:
            return 0.0, side_primary, "skip"
        P_eff_primary = q_meta * p_star + (1 - q_meta) * (1 - p_star)
        if P_eff_primary >= 0.5:
            edge = P_eff_primary - b
            side, price = side_primary, b
        else:
            if abs(q_meta - 0.5) < self.flip_min_conf:
                return 0.0, side_primary, "low_conf_no_flip"
            side = "NO" if side_primary == "YES" else "YES"
            price = 1 - b
            edge = (1 - P_eff_primary) - price
        if edge <= 0:
            return 0.0, side, "no_edge"
        return self.fraction * edge / (1 - price), side, "active"

# --------------- CLV Tracker ---------------

@dataclass
class BetRecord:
    game_id: str
    placed_ts: pd.Timestamp
    side: str
    placed_price: float
    pinnacle_close_implied: float
    settled_yes: bool

class CLVTracker:
    def __init__(self):
        self.records: list[BetRecord] = []
    def record(self, **kw):
        self.records.append(BetRecord(**kw))
    def clv_per_bet(self):
        out = []
        for r in self.records:
            if r.side == "YES":
                placed_implied = r.placed_price
                pin_implied = r.pinnacle_close_implied
            else:
                placed_implied = 1 - r.placed_price
                pin_implied = 1 - r.pinnacle_close_implied
            out.append(pin_implied - placed_implied)
        return np.array(out)
    def summary(self):
        clv = self.clv_per_bet()
        if len(clv) == 0:
            return {"n": 0}
        return {
            "n": len(clv),
            "mean_clv": clv.mean(),
            "median_clv": np.median(clv),
            "hit_rate_above_close": float((clv > 0).mean()),
            "sharpe_clv": clv.mean() / (clv.std() + 1e-9) * np.sqrt(len(clv)),
        }
```

## 2.9 Realistic Edge Expectations

| Metric | Target | "Concerning if" |
|---|---|---|
| Primary raw hit rate (totals) | 50.5–52% post-vig | >53% sustained |
| Meta-selective hit rate | 52–53% on the subset taken | >55% |
| Skip rate (meta says don't bet) | 30–50% of games | <10% (meta is useless) or >70% (meta is too tight) |
| Sustained CLV | +0.5% to +1.5% | >+2.5% sustained |
| Sharpe at 0.15× Kelly | 0.5–1.0 net of fees | >1.5 (overfit suspect) |
| Annual return at 0.15× Kelly | 6–15% | >25% (overfit suspect) |

Kalshi NBA totals contract fees follow the published schedule $\text{fee} = 0.07 \cdot C \cdot P \cdot (1-P)$ per contract. Build this into the Kelly calculation — at $P = 0.5$, fees are 1.75 cents on each side, which materially erodes small edges.

---

# PART 3 — NBM qmd S3 Inventory Format

## 3.1 The S3 Bucket Structure

Bucket: **`s3://noaa-nbm-grib2-pds`** (us-east-1, AWS Open Data Sponsorship — no egress fees within us-east-1, normal egress to other regions or the public internet).

Path layout:

```
s3://noaa-nbm-grib2-pds/
└── blend.YYYYMMDD/
    └── CC/                        # cycle: 00, 06, 12, 18
        ├── core/                  # deterministic blend
        │   └── blend.tCCz.core.fFFF.RR.grib2
        ├── qmd/                   # quantile-mapped probabilistic
        │   ├── blend.tCCz.qmd.fFFF.RR.grib2
        │   └── blend.tCCz.qmd.fFFF.RR.grib2.idx
        └── (other subdirs: ling, mvbl, ploc, predomwx, ppi, etc.)
```

Where:

- `YYYYMMDD`: cycle date UTC
- `CC`: cycle hour (00, 06, 12, 18)
- `FFF`: forecast hour, zero-padded (`001` through `264`)
- `RR`: region grid: **`co`** (CONUS, ~2.5 km), `ak` (Alaska), `hi` (Hawaii), `pr` (Puerto Rico), `gu` (Guam), `oc` (oceanic)

For the six airport stations all CONUS, use `RR = co`. NBM v4.x is current production; **v5.0 is slated to replace v4.3 in April 2026** per the MDL roadmap — your ingest code must be version-aware and tolerate the v5.0 GRIB2 Section 4 encoding changes.

Example URL:

```
https://noaa-nbm-grib2-pds.s3.amazonaws.com/blend.20260512/12/qmd/blend.t12z.qmd.f024.co.grib2
https://noaa-nbm-grib2-pds.s3.amazonaws.com/blend.20260512/12/qmd/blend.t12z.qmd.f024.co.grib2.idx
```

QMD elements relevant to forecast-lab:

- `TXNP1, TXNP2, TXNP5, TXNP7, TXNP9` = 10/25/50/75/90 percentiles of MaxT/MinT (MaxT at 00Z, MinT at 12Z; daily 24-hour windows)
- `TXNMN`, `TXNSD` = QMD mean and stddev of MaxT/MinT
- `WSPP1/2/5/7/9` = wind speed percentiles
- `Q24P1/2/5/7/9` = 24-hour QPF percentiles

Percentile interpretation: $P_x$ is the $x$th percentile, i.e., $P(Y \le P_x) = x/100$.

## 3.2 The .idx Inventory Format

NCEP/MDL emit wgrib2-compatible idx files. Format per line (colon-delimited):

```
RECORD_NUM:BYTE_OFFSET:DATE:VARIABLE:LEVEL:FORECAST_TIME:EXTRA_INFO
```

Example lines (illustrative; wgrib2 default_inv format used by NBM):

```
1:0:d=2026051212:TMP:2 m above ground:24 hour fcst:prob >293
2:154823:d=2026051212:TMP:2 m above ground:24 hour fcst:10% level
3:309701:d=2026051212:TMP:2 m above ground:24 hour fcst:25% level
4:464212:d=2026051212:TMP:2 m above ground:24 hour fcst:50% level
...
74:46711902:d=2026051212:APCP:surface:18-24 hour acc fcst:90% level
```

Field meanings:

| Field | Example | Meaning |
|---|---|---|
| RECORD_NUM | `74` | 1-indexed message number in the grib2 file |
| BYTE_OFFSET | `46711902` | starting byte of the GRIB2 message |
| DATE | `d=2026051212` | cycle date+hour |
| VARIABLE | `TMP`, `APCP`, `WIND`, `GUST` | wgrib2 short name |
| LEVEL | `2 m above ground`, `surface`, `10 m above ground` | level descriptor |
| FORECAST_TIME | `24 hour fcst`, `18-24 hour acc fcst` | lead and accumulation window |
| EXTRA_INFO | `50% level`, `prob >293`, `ens mean` | percentile, probability threshold, or ensemble stat |

The byte offset is the only thing you cannot reconstruct without parsing — everything else is on the path or trivially derivable. The **next** message starts at the next record's offset, so to compute the byte range for record $n$ you read records $n$ and $n+1$ from the idx; the last record runs to EOF (use `Content-Length` from a HEAD on the grib2 file, or omit the upper bound and let the server stream EOF).

## 3.3 Byte-Range Partial GETs

The data-volume win is dramatic. Full NBM qmd CONUS f024 is ~250 MB. A single T2m percentile record covering all of CONUS is ~1.5 MB. After bilinear interpolation to a station you only need the four neighbor grid points, but you must download the whole CONUS record because GRIB2 messages are atomic.

Per cycle, per station, you need ~7 percentile records × 7 lead times = ~49 records. At ~1.5 MB each = ~75 MB per cycle. Four cycles per day = ~300 MB/day for all 6 stations *combined* (record fetches are shared across stations within CONUS — you decode once, sample 6 points). The naive full-file approach is ~100× larger.

- **Optimized: ~75 MB/cycle × 4 cycles = ~300 MB/day** if you share records across stations
- Naive per-station full-file: ~250 MB × 4 cycles × 6 stations = ~6 GB/day → blows budget

Procedure:

```python
import boto3, io, requests, cfgrib, xarray as xr
from botocore import UNSIGNED
from botocore.client import Config
import pathlib, tempfile

class NBMFetcher:
    BUCKET = "noaa-nbm-grib2-pds"
    def __init__(self, cache_dir="./nbm_cache"):
        self.s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
        self.cache = pathlib.Path(cache_dir); self.cache.mkdir(exist_ok=True)

    def _key(self, date_yyyymmdd, cc, fff, product="qmd", region="co"):
        return (f"blend.{date_yyyymmdd}/{cc:02d}/{product}/"
                f"blend.t{cc:02d}z.{product}.f{fff:03d}.{region}.grib2")

    def fetch_idx(self, date, cc, fff, product="qmd", region="co"):
        key = self._key(date, cc, fff, product, region) + ".idx"
        cache_file = self.cache / key.replace("/", "_")
        if cache_file.exists():
            return cache_file.read_text()
        body = self.s3.get_object(Bucket=self.BUCKET, Key=key)["Body"].read()
        text = body.decode("utf-8")
        cache_file.write_text(text)
        return text

    def parse_idx(self, idx_text):
        rows = []
        for line in idx_text.strip().split("\n"):
            parts = line.split(":")
            rows.append({
                "record": int(parts[0]),
                "offset": int(parts[1]),
                "date":   parts[2],
                "var":    parts[3],
                "level":  parts[4],
                "ftime":  parts[5],
                "extra":  ":".join(parts[6:]) if len(parts) > 6 else "",
            })
        for i in range(len(rows) - 1):
            rows[i]["end_offset"] = rows[i+1]["offset"] - 1
        rows[-1]["end_offset"] = None  # to EOF
        return rows

    def fetch_records(self, date, cc, fff, var_filter, product="qmd", region="co"):
        """var_filter: callable(row_dict) -> bool"""
        idx_rows = self.parse_idx(self.fetch_idx(date, cc, fff, product, region))
        selected = [r for r in idx_rows if var_filter(r)]
        key = self._key(date, cc, fff, product, region)
        merged = io.BytesIO()
        for r in selected:
            start, end = r["offset"], r["end_offset"]
            byte_range = f"bytes={start}-" if end is None else f"bytes={start}-{end}"
            obj = self.s3.get_object(Bucket=self.BUCKET, Key=key, Range=byte_range)
            merged.write(obj["Body"].read())
        merged.seek(0)
        return merged, selected

    def decode_to_xarray(self, grib_bytes_io):
        with tempfile.NamedTemporaryFile(suffix=".grib2", delete=False) as f:
            f.write(grib_bytes_io.getvalue())
            tmpfile = f.name
        ds = xr.open_dataset(tmpfile, engine="cfgrib",
                             backend_kwargs={"indexpath": ""})
        return ds

# usage
fetcher = NBMFetcher()
def t2m_percentiles(row):
    return (row["var"] == "TMP" and row["level"] == "2 m above ground"
            and row["extra"].endswith("% level"))
buf, recs = fetcher.fetch_records("20260512", 12, 24, t2m_percentiles)
ds = fetcher.decode_to_xarray(buf)
```

Notes for production:

- Anonymous S3 access via `UNSIGNED` config — bucket is fully public.
- The `idx` file is typically 5–30 KB. Cache them aggressively (they're immutable once written).
- cfgrib requires `eccodes` (install via `mamba install -c conda-forge cfgrib eccodes`). Avoid the pip eccodes; it's fragile.
- Concatenating multiple range-GET responses into one bytestream works because GRIB2 messages are self-delimiting (each starts with `GRIB` magic and contains its length in Section 0).
- S3 rate limits: NBM PDS allows generous parallel access but throttle to ~8 concurrent requests per cycle to avoid 503s. Use `concurrent.futures.ThreadPoolExecutor(max_workers=8)`.

## 3.4 Quantile → CDF Reconstruction

NBM qmd ships 10/25/50/75/90 percentile values plus mean and std. To reconstruct a continuous CDF $F(x)$ from the five knots $(P_{10}, P_{25}, P_{50}, P_{75}, P_{90})$:

1. **Interior:** Monotone cubic Hermite (PCHIP) interpolation on $(x_i, q_i)$ where $x_i$ are the percentile values and $q_i \in \{0.1, 0.25, 0.5, 0.75, 0.9\}$:

   ```python
   from scipy.interpolate import PchipInterpolator
   xs = np.array([p10, p25, p50, p75, p90])
   qs = np.array([0.10, 0.25, 0.50, 0.75, 0.90])
   F_interior = PchipInterpolator(xs, qs, extrapolate=False)
   ```

   PCHIP preserves monotonicity, which is required for a valid CDF. Linear interpolation also works and is more conservative; cubic splines do not preserve monotonicity and **must not be used here**.

2. **Lower tail $x < P_{10}$:** Map to a Gaussian tail anchored at $P_{10}$ with scale derived from the inter-percentile distance in z-score space:

   $$
   \sigma_{\text{low}} \;=\; \frac{P_{25} - P_{10}}{z_{0.25} - z_{0.10}}, \quad \mu_{\text{low}} \;=\; P_{10} - z_{0.10}\sigma_{\text{low}}
   $$

   where $z_q = \Phi^{-1}(q)$. Then $F(x) = \Phi((x - \mu_{\text{low}})/\sigma_{\text{low}})$ for $x < P_{10}$.

3. **Upper tail $x > P_{90}$:** Symmetric construction:

   $$
   \sigma_{\text{high}} \;=\; \frac{P_{90} - P_{75}}{z_{0.90} - z_{0.75}}, \quad \mu_{\text{high}} \;=\; P_{90} - z_{0.90}\sigma_{\text{high}}
   $$

For temperature this tail extrapolation is fine. For QPF (precipitation amount) you should use a non-negative-support distribution — gamma anchored at $P_{75}$ and $P_{90}$. Forecast-lab's current contracts are temperature so the Gaussian-tail recipe applies.

```python
from scipy.stats import norm
from scipy.interpolate import PchipInterpolator

def nbm_quantiles_to_cdf(p10, p25, p50, p75, p90, eval_grid):
    xs = np.array([p10, p25, p50, p75, p90])
    qs = np.array([0.10, 0.25, 0.50, 0.75, 0.90])
    pchip = PchipInterpolator(xs, qs, extrapolate=False)
    sig_lo = (p25 - p10) / (norm.ppf(0.25) - norm.ppf(0.10))
    mu_lo  = p10 - norm.ppf(0.10) * sig_lo
    sig_hi = (p90 - p75) / (norm.ppf(0.90) - norm.ppf(0.75))
    mu_hi  = p90 - norm.ppf(0.90) * sig_hi
    F = np.empty_like(eval_grid, dtype=float)
    lo = eval_grid < p10
    hi = eval_grid > p90
    mid = ~(lo | hi)
    F[lo]  = norm.cdf(eval_grid[lo],  loc=mu_lo, scale=sig_lo)
    F[hi]  = norm.cdf(eval_grid[hi],  loc=mu_hi, scale=sig_hi)
    F[mid] = pchip(eval_grid[mid])
    return np.clip(F, 0, 1)
```

## 3.5 NBM's Role in forecast-lab

NBM is operationally calibrated, post-processed, blended output combining GFS, GEFS, ECMWF (deterministic and ensemble), NAM, HRRR, and others through MDL's bias-correction + quantile-mapping pipeline. At 1–3 day leads it is roughly 5–8% better CRPS than raw GEFS for surface temperature. The gap narrows at longer leads where ensemble spread dominates and post-processing has less to add.

**Two roles:**

1. **Benchmark.** Run your full pipeline (NGR + isotonic + AnEn + climatology) against NBM qmd at the six stations on a held-out year. Compute CRPS per (station, lead). **If forecast-lab does not beat NBM on a station-and-lead majority, you have no edge there and should fall back to NBM for that contract.** Realistic outcome: forecast-lab beats NBM at 1–2 day leads at all stations by 2–5% (your AnEn captures regime structure NBM's quantile mapping smooths over), is roughly equal at 3–5 day leads, and loses to NBM at 6–7 day leads (NBM's multi-model blend dominates at long range).
2. **Input feature for the meta-blender.** In the Phase-2 station-conditional blender (§1.5(c)), the NBM-implied CDF can be a fourth blend component or its quantiles can be metafeatures. Don't make NBM the dominant component (defeats the purpose of running forecast-lab), but use it as a regularizer for days when your AnEn distance $d_k$ is large.

Operationally, build the NBM benchmark plumbing first (week 1) so every subsequent component has a CRPS comparison target from day one.

## 3.6 Cost Analysis

| Approach | Daily volume | Monthly egress | Notes |
|---|---|---|---|
| Full grib2 per cycle, 6 stations, 4 cycles | ~6 GB | ~180 GB | $0.09/GB egress to non-AWS = ~$16/mo egress alone |
| Full grib2 per cycle, shared records across stations | ~1 GB | ~30 GB | ~$2.70/mo egress, decode CPU bounded |
| **Partial GET per record, shared across stations** | **~300 MB** | **~9 GB** | **~$0.80/mo, well under budget** |
| EC2 t4g.small in us-east-1 + partial GET | same | $0 egress | $13/mo for the EC2, free egress |
| Lambda + partial GET | same | $0 egress | Generally fits in free tier for this volume |

**Recommendation:** Run forecast-lab on an EC2 t4g.small (~$13/mo on-demand, ~$8 reserved) in us-east-1. Egress is free. AWS Open Data Sponsorship covers the bucket, so no S3 request charges. Total infra cost: ~$10–15/mo, leaving headroom in your $50 budget for the line-data API ($30/mo) and small storage costs.

If you must stay off AWS (latency concerns for execution, or you already have a colo), the partial-GET path keeps egress under $1/mo, well within budget.

## 3.7 NBM Versioning & Failure Modes

- **NBM v5.0 cutover:** Slated April 2026 per MDL; the v5.0 GRIB2 Section 4 (QMD) encoding differs from v4.3. Build a version-detection step: read the v from GRIB2 Sections 0/1 and route to a version-specific record-name dictionary. Your idx parser is forward-compatible (the wgrib2-style idx format is stable), but the meaning of `extra_info` may change.
- **Rate limits:** S3 will 503 if you parallelize aggressively. Use exponential backoff. The bucket is not rate-limited per the published policy, but observed behavior caps at ~3500 GETs per prefix per second; per-cycle you'll do ~50 GETs, so you're fine.
- **idx file occasionally missing:** Cycles get re-run; the grib2 may appear before the idx. Retry with backoff for 15 minutes; if still missing, fall back to wgrib2-generating the idx locally (download a small head of the grib2 to enumerate messages; this is annoying but only happens 1–2× per month in observed behavior).
- **Time alignment:** NBM `f024` from a 12Z cycle is valid at 12Z next day. Kalshi temperature contracts settle on local-time-zone observed daily max. Build a careful UTC→local-tz mapping per station and align your forecast lead times accordingly. **This is a common bug source — write tests.**

---

# CROSS-CUTTING INTEGRATION

## How the Three Workstreams Compose

**Weather pipeline (P1 + P3):**

- NBM qmd is the operational benchmark and Phase-2 blend input.
- AnEn is the new component sitting between NGR and the existing climatology blend, improving CRPS by 2–5% on average and 5–10% on regime days.
- The CRPS improvement at the predictive-distribution level translates directly into improved EV per Kalshi temperature contract — a 3% CRPS improvement at a 1-day lead implies roughly a 5–15 basis-point improvement in implied-probability sharpness on the at-the-money contracts at each station, which compounds across the ~6 stations × ~5 daily contracts × 250 trading days = ~7500 contract opportunities per year. Even 5 bp/contract sustained over thousands of trades dominates noise.

**Sports pipeline (P2):**

- Runs in parallel on disjoint data (NBA play-by-play, schedule, lines).
- The Kelly-sizing and CLV infrastructure built for sports translates 1:1 to weather. Specifically: the `KellySizer` class, the position-tracking ledger, the CLV-style backtest framework. Reuse, don't fork.
- The meta-labeling pattern itself is general — once you have it working for NBA totals, you can apply the same primary+meta architecture to weather contracts where the primary is the blended CDF probability and the meta-model decides which contract-level signals are trustworthy.

**Shared infrastructure:**

- Combinatorially purged k-fold CV is already in your stack. NBA needs the season-block adaptation (§2.6); weather needs the time-block adaptation (already done).
- The same logging/diagnostics dashboard serves both. Build one observability layer.

## Unified 12-Week Roadmap

| Week | Deliverable | Owner area | Exit criteria |
|---|---|---|---|
| **1** | `NBMFetcher` + idx parser + decode pipeline; daily ingest of NBM qmd at 6 stations × 4 cycles × 7 leads; quantile→CDF reconstruction wired. | P3 | NBM CDF available in pipeline for any (station, lead, cycle); end-to-end test green. |
| **2** | NBM-vs-NGR+isotonic CRPS benchmark on 2023 holdout, per station per lead. | P3 + P1 | Benchmark numbers committed. You now know which (station, lead) cells you need AnEn to beat. |
| **3** | AnEn feature extraction from GEFSv12 reforecast (engineered features per station); cKDTree build; sin/cos doy in metric; default $k=50$. | P1 | `predict_members` returns sensible analogs (manual sanity check: Jan day pulls Jan analogs, hot day pulls hot analogs). |
| **4** | CMA-ES weight learning per (station, lead); leave-one-year-out $k$ selection; KDEN Chinook stratification. | P1 | Learned weights committed; CRPS on 2018-2019 holdout improves over uniform-weight baseline by 5–10%. |
| **5** | `BlendedCDF` strategy (b) — convex blend of NGR + AnEn + climatology, fit per (station, lead). | P1 | Blended CDF beats NGR alone by 2–5% mean CRPS on holdout. |
| **6** | CRPS comparison of blended pipeline vs. NBM at the six stations, all leads. Production diagnostics dashboard (PIT, $d_k$ percentile, OOD rate). | P1 + P3 | Blended pipeline beats NBM at ≥4 of 6 stations at 1–3 day leads. If not, debug before moving on. |
| **7** | NBA Glicko-2 + pace efficiency primary model on 2015-2024 seasons; backtest hit-rate on totals. | P2 | Primary raw hit rate 50.5–52% on out-of-sample 2024-25 season; sanity-check spot-game predictions. |
| **8** | NBA feature pipeline: rest/B2B/travel/injuries/refs/league pace anomaly/Vegas-open. Pinnacle line ingestion (open + close) running in production for live games. | P2 | All features materialized causally; line history accumulating; no closing-line leak into training. |
| **9** | Meta-label LightGBM classifier; season-block 5-fold CV; effective skip-band + flip-threshold tuned. | P2 | Meta-selective hit rate ≥52% on out-of-fold; calibration check (reliability diagram) passes. |
| **10** | `KellySizer` integrated with meta-model (with flip logic per §2.4); `CLVTracker` populated from Pinnacle ingestion; full paper-trade simulation for prior 2 NBA seasons. | P2 | Backtested CLV +0.5–1.5%, Sharpe 0.5–1.0 at 0.15× Kelly, drawdown <15% on paper. |
| **11** | Production paper-trade on live NBA totals (no real bets yet); production deploy of AnEn-blended weather forecasts; first real Kalshi weather positions sized via the improved CDF. | P1 + P2 | One full week of live paper-trade NBA + live real weather trading. CLV measurements consistent with backtest. |
| **12** | First real NBA totals paper-→-live transition (start at 0.05× Kelly, ramp to 0.15× over 4 weeks if CLV holds); Phase-2 meta-blender (1.5c) wired in for weather as stretch. | P1 + P2 | Real-money NBA totals trading live. Production observability stack reporting daily on both pipelines. |

## What Could Go Wrong: Pre-Mortem

### AnEn (P1)

- **KDEN underperforms** even with Chinook stratification. Realistic. Set CRPS-improvement expectation at KDEN to 2–3% (lower than other stations), and route to NBM-only when $d_k$ is in the 90th percentile.
- **KMIA shows ~0% improvement** because synoptic forcing is weak in summer. Acceptable; do not over-engineer. If CRPS doesn't improve, route KMIA to NGR-only and skip the AnEn cost.
- **CMA-ES weight learning overfits** to the holdout. Mitigation: use a separate validation set distinct from the held-out year used in $k$ selection, and re-fit only quarterly.
- **GEFSv12 vs. real-time GEFS distributional shift.** The reforecast was run at v12 (FV3 dycore), but real-time forecasts have minor model updates. Track CRPS in production vs. CRPS on reforecast holdout; if they diverge >10% over 60 days, refit on more recent data (recent GEFS-real-time vs. reanalysis).

### Meta-Labeling (P2)

- **Overfitting via too many features.** Cap LightGBM at ~15 features, use early stopping on out-of-fold log-loss, regularize aggressively (`min_data_in_leaf=50`, `reg_lambda=0.5`).
- **Vegas closing line covertly in training.** Audit pipeline. Histogram opening vs. closing line stats on training data; if your "opening line" looks more like closing-line statistics, vendor is backfilling.
- **Glicko volatility miscalibrated** at season boundaries — team rosters change drastically. Bump RD up by 50% at the start of each season; let it decay over the first 10 games.
- **Pinnacle line API outage** kills CLV tracking. Have a fallback (e.g., DraftKings via odds API) but be aware DraftKings closing lines are softer than Pinnacle's; CLV computed against DraftKings is inflated by 10–30%.
- **NBA market efficiency increases.** Kalshi NBA totals are now a competitive market; the inefficiencies of 2024 may be priced out by late 2026. Set a 60-day rolling CLV threshold — if it drops below +0.3%, halt automated betting and audit.
- **False flips destroy P&L.** The meta-model's flip mechanism (§2.4) is dangerous if the meta-model is miscalibrated. Always gate flips behind out-of-fold Brier check and a 0.15 minimum confidence margin from 0.5. Monitor flip-fraction in production; if it spikes above 15% of bets, halt and audit.

### NBM Ingestion (P3)

- **S3 throttling under naive parallelism.** Mitigation: thread-pool capped at 8 workers per cycle, exponential backoff.
- **NBM v5.0 cutover April 2026** breaks the parser. Pin to v4.3 in production and parallel-test v5.0 ingestion against the same cycles for two weeks before cutover. Build version-aware variable name mapping.
- **idx file format drift.** wgrib2-format idx has been stable for ~15 years; risk is low but tests should validate against a known-good idx every cycle.
- **Time-zone bugs at station↔contract alignment.** Write explicit tests. KAUS daily-max is on CST/CDT; NBM lead times are UTC. This is the #1 source of silent bugs in this kind of pipeline.

---

## Final Notes for the Team

The single highest-leverage piece is the **NBM benchmark plumbing** (week 1). Until you have it, you don't know which (station, lead) cells you have edge in, and you can't measure progress.

The second highest-leverage piece is the **CLV tracking infrastructure for NBA** (week 8). Without it, you cannot honestly assess sports edge before P&L stabilizes, and you will misallocate sizing. Build CLV tracking even if you never go live on NBA — it's the unit-test framework for any future sports market.

The third is **the observability dashboard** — PIT histograms, $d_k$ distributions, blend-weight drift, CLV rolling stats. Build it once, run it forever. It is the only thing that will tell you when the world has changed under you.

Do not under any circumstances size NBA at full Kelly. 0.15× is conservative-aggressive for a model that has hit verification gates. For a brand-new pipeline with only paper-trade evidence, start at 0.05× and ramp.
