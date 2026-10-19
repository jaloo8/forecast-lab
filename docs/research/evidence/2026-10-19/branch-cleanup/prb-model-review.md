# PR-B generated-model evidence review

Completed semantic reading of six changed model files: all11before/after JSON images,805distinct objects/arrays and24field schemas. Every novel value and metadata field was read; identical subtrees were reused by SHA-256 and JSON pointer. All11images reconstruct losslessly and match original Git blob SHA-256. Raw diff sections are recorded at lines1360–8595 in the other-22 branch diff.

Base `21b655b0f33217a2c138fd6e5bf6be8d45f82389`; tip `8849097a32c87d79931b5da1734e90e25c1db649`; tip is an ancestor of current main `e1e1f4bc43e19ca862e1425ff637e7fa0d124db1`.

- **This branch intentionally replaces invalid historical evidence, not a standalone model success.** The three regenerated backtest manifests explicitly say each (station, valid_date, bracket) is counted at most once, non-overlapping test windows, true lead-1 inputs. Per-station evaluations change 28616 to3822. Training samples/date ranges and stations also change, so the before/after numerical difference cannot be attributed to one strategy improvement on identical inputs.

- **Regenerated selected-router benchmark comparisons fail for all six stations.** Recorded improvement versus NDFD is KAUS-45.44%,KDEN-24.73%,KLAX-19.74%,KMDW-50.17%,KMIA-38.95%,KNYC-43.47%. The router selects five NGR strategies and raw forKMIA. Synthetic-market profits do not reverse the forecast benchmark failure.

- **New York identity and training evidence are deliberately revised.** KJFK is replaced by KNYC. Training changes from2024-04-01..2025-03-31,365 samples,292folds to2024-11-01..2026-06-30,607samples,39folds,step14. New schema adds cv_step_size/n_semantics and calibration summaries. A calibration PASS with only1–2qualifying median bins does not establish every bucket is calibrated.

- **Deleted reforecast evidence is superseded and must remain accessible in history.** Before-only reforecast manifest includes KJFK final bank balance-0.01 and122.65% drawdown,KLAX-0.24 and100.05%,KMIA103.37% drawdown. The branch-tip session audit says this void reforecast manifest was deleted pending genuine GEFSv12 inputs. The deleted file is preserved by Git ancestry and audit source hashes; there is no generated replacement to merge.

- **Generated profitability figures have explicit and material simulation limits.** All backtests preserve caveats: naive synthetic market without a historical Kalshi price archive, assumed displayed fills, liquidity/queue omissions, deterministic NBM Tmax with fitted Gaussian rather than true probabilistic qmd, and incomplete NDFD archive overlap. Large ROI figures are not executable or future returns. Even the old calibrated KLAX manifest ends at-0.04 with100.43% drawdown.

Recommendation: **DELETE the redundant branch pointer after backup; no additional merge.** Preserve main history, including the deliberately removed invalid reforecast artifact. These figures demonstrate an evidence correction, not annual profit or a deployable strategy.

Receipts: `prb-model-review.json`, `prb-model-head-coverage.json`, `prb-model-tail-coverage.json`, `prb-subtree-mapping.json`, `prb-schema-key.jsonl`, and `prb-value-tuples.jsonl`. No model/backtest/operational code was executed.
