# Selected reading: validation, uncertainty and portfolio mathematics

Read on October 20, 2026. This log records selected original textbook sections
and author-prepared teaching material actually inspected. It is not a claim to
have read these entire books, reproduced their examples or run another strategy.
No source code changed, no model calls were made and no book PDFs were added to
the repository.

## 1. Forecasting: Principles and Practice, third edition

**Authors:** Rob J. Hyndman and George Athanasopoulos.
**Primary publisher source:** [Chapter 5, The forecaster's toolbox](https://otexts.com/fpp3/toolbox.html).
The older `tscv.html` and `prediction-intervals.html` URLs now redirect there.

**Read scope:** section 5.10's rolling-origin and multi-step validation discussion
and worked example; section 5.5's normal intervals, one-/multi-step uncertainty,
benchmark formulas and residual-bootstrap explanation. Also inspected the
section 5.9 passages explaining Winkler scores and CRPS.

**Useful principles:** A forecast at a test origin uses earlier observations
only; evaluation should match the intended horizon. In-sample residual error
can understate forecasting error. Prediction intervals describe uncertainty,
and their assumptions matter. The illustrated residual bootstrap assumes
uncorrelated errors with constant variance.

**Project application:** fit transformations and parameters inside each
chronological training window; score one- and five-session forecasts separately.
Compare interval coverage and sharpness with a simple benchmark before using
probabilities for sizing.

**Limit:** good prediction-error scores do not establish a profitable policy.
A nominal prediction interval is not a guaranteed loss bound. We have not
established that this book's simple residual-bootstrap assumptions hold for our
strategy returns.

## 2. An Introduction to Statistical Learning: original author resources

**Book authors:** Gareth James, Daniela Witten, Trevor Hastie and Robert
Tibshirani; Jonathan Taylor joins the Python edition.
**Primary provenance:** the [official Python resources page](https://www.statlearning.com/resources-python)
explicitly identifies the linked slides as prepared by the authors.

The official full-book download returned HTTP 403, and the direct PDF open did
not succeed. Therefore the reading below is **author slides, not a claim to have
read the corresponding book chapters**. No access restriction was bypassed.

### Cross-validation and feature selection

**Read:** [Chapter 5 slides](https://web.stanford.edu/~hastie/ISLR2/Slides/Ch5_Resampling_Methods.pdf),
printed slides 2, 4–11 and 17–21, especially the feature-selection example
(PDF pages 25–32, counting from one).

**Useful principle:** selecting predictors using all outcomes and then
cross-validating only the final model leaks information. Validation must include
the selection step.

**Project application:** a future news model must rebuild outcome-dependent
vocabularies, feature rankings, normalizers and model selection using training
data only. Choosing the best headline rules after seeing the evaluation period
is also research selection; retain that history.

**Limit:** these slides illustrate random folds. Our time-series adaptation
must retain chronology; it is not justified to randomly shuffle trading dates.
No feature-selection experiment was performed here.

### Multiple testing

**Read:** [Chapter 13 slides](https://web.stanford.edu/~hastie/ISLR2/Slides/Ch13_Multiple_Testing.pdf),
printed slides 17–23 and 28–30: family-wise error, Bonferroni, Holm, false
discovery rate and Benjamini–Hochberg.

**Useful distinction:** family-wise error concerns any false rejection;
false-discovery rate concerns the expected false share among rejections.
Bonferroni compares each valid p-value with `alpha / m`; Holm applies sequential
thresholds to ordered p-values.

**Project application:** register the complete hypothesis family before
testing, preserve failures and report the chosen error-control method.
Thousands of variants cannot be treated as one preselected test.

**Limit:** adjustment cannot repair invalid underlying p-values, hindsight
selection or missing trials. Dependence and overlapping return windows require
an appropriate statistical design before these procedures are applied.

**Reading correction:** printed slide 28 says `Pr(V > 1)` while describing
“any” false rejection; slide 17 correctly gives `Pr(V >= 1)`. We use the latter.
No significance result has been computed or asserted in this log.

## 3. Convex Optimization

**Authors:** Stephen Boyd and Lieven Vandenberghe.
**Primary source:** [author-hosted book PDF](https://web.stanford.edu/~boyd/cvxbook/bv_cvxbook.pdf),
available with publisher permission stated on the
[authors' book page](https://web.stanford.edu/~boyd/cvxbook/).

**Read scope:** section 4.4.1, the Markowitz portfolio example and transaction-cost
extension, printed pages 155–156 (PDF pages 169–170).

**Useful mathematics:** for portfolio weights `w`, modeled variance is
`w.T @ covariance @ w`; expected return is `mean.T @ w`. The example uses
budget and nonnegative-position constraints, and shows how purchases, sales
and proportional transaction fees enter the funding constraint.

**Project application:** separate objective, feasible weights and execution
accounting. Any future allocator must fund costs from actual cash, verify
constraint residuals and preserve infeasibility/solver failures.

**Limit:** the example assumes supplied means and covariances. Solving that
optimization accurately does not validate estimated inputs or future returns.
A constraint on **expected** return does not establish a minimum realized return
in every year. Continuous weights also do not by themselves establish
integer-share feasibility for a $1,000 account.

## What this changes next

Our proposed implementation priority is one shared evaluation contract: exact
data availability, all learning inside chronological training windows, a finite
registered hypothesis family, forecast-quality measurements separated from
costed account performance, and explicit feasibility checks. This is our
application of the reading, not a newly completed experiment or a change to the
frozen research registrations.

For the news pilot specifically, complete effective-dated entity linkage and
prospective observation quality before testing financial predictions. Preserve
the existing distinction between `published_at`, `first_seen_at` and
`retrieved_at`; a textbook validation method cannot recover missing historical
availability.
