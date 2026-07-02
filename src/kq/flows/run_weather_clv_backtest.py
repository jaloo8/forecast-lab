"""Weather CLV backtest flow — the runnable wrapper around ``weather_clv``.

Runs the rolling-origin backtest (which produces PIT-correct per-(station,
date, bracket) model + NDFD probabilities), collects the per-bracket records
the engine now exposes, scores them through
:func:`kq.backtest.weather_clv.evaluate_brackets`, and writes a JSON manifest
mirroring the NBA CLV manifest. This is the ``#63 → #64`` completion for the
weather lane: the evaluator shipped separately; this flow does the I/O.

No-data / no-router-config safe:
- empty DB → ``n_evaluated=0`` manifest, exit 0 (normal pre-prod state);
- missing ``models/router_config.json`` → falls back to ``weather_v1`` with a
  warning (so a cron entry can be active before ``kq decide-router`` has run).

Anchor caveat (see the evaluator's docstring): the benchmark is NDFD/NBM, not
a Kalshi market close — this is Brier-vs-benchmark + unconditional mean-edge,
not literal closing-line value. The outcome-conditioned
``mean_signed_edge_vs_ndfd`` was retired by the 2026-06-11 audit (root cause
#10) in favor of ``mean_edge_vs_ndfd``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from kq.backtest.engine import run_backtest
from kq.backtest.result import BacktestResult
from kq.backtest.weather_clv import WeatherClvSummary, evaluate_brackets
from kq.config import REPO_ROOT, get_settings
from kq.flows.ingest_weather import _db_path_from_settings

log = structlog.get_logger(__name__)

MODELS_DIR: Path = REPO_ROOT / "models"
MANIFEST_PATH: Path = MODELS_DIR / "backtest_weather_clv_manifest.json"


def _run_backtest_with_fallback(
    db_path: Path, strategy: str
) -> tuple[dict[str, BacktestResult], str]:
    """Run the backtest, falling back to weather_v1 if the router config is absent."""
    try:
        return run_backtest(db_path=db_path, strategy=strategy), strategy
    except FileNotFoundError:
        log.warning(
            "weather_clv.router_config_missing_fallback",
            requested=strategy,
            fallback="weather_v1",
        )
        return run_backtest(db_path=db_path, strategy="weather_v1"), "weather_v1"


def write_manifest(
    summary: WeatherClvSummary,
    *,
    strategy: str,
    out_path: Path = MANIFEST_PATH,
) -> Path:
    """Serialize the weather CLV summary (overall + per-station) as JSON."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "strategy": strategy,
        "n_evaluated": summary.n_evaluated,
        "n_skipped_no_ndfd": summary.n_skipped_no_ndfd,
        "n_skipped_no_model": summary.n_skipped_no_model,
        "brier_model": summary.brier_model,
        "brier_ndfd": summary.brier_ndfd,
        "mean_edge_vs_ndfd": summary.mean_edge_vs_ndfd,
        "win_rate_when_picked": summary.win_rate_when_picked,
        "per_station": {
            s: {
                "n": st.n,
                "brier_model": st.brier_model,
                "brier_ndfd": st.brier_ndfd,
                "mean_edge_vs_ndfd": st.mean_edge_vs_ndfd,
                "win_rate_when_picked": st.win_rate_when_picked,
            }
            for s, st in summary.per_station.items()
        },
        "honest_caveats": [
            "Anchor is NDFD/NBM (no Kalshi market close until prod) -- this is "
            "Brier-vs-benchmark + unconditional mean-edge, NOT literal "
            "closing-line value.",
            "mean_edge_vs_ndfd is mean(model - ndfd) with NO outcome in the "
            "formula -- a disagreement diagnostic, not a skill claim. Skill is "
            "the Brier pair. (The outcome-conditioned mean_signed_edge_vs_ndfd "
            "was retired by the 2026-06-11 audit, root cause #10.)",
            "win_rate_when_picked is descriptive only; it gates nothing.",
            "Built from the rolling-origin backtest's PIT-correct per-bracket "
            "evals; rows missing NDFD coverage (~pre-2024-11) are skipped.",
            "Rolling-origin step inflates apparent n; treat +/-2pp swings as "
            "within-noise (see the backtest manifest's honest_caveats).",
        ],
    }
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
    return out_path


def main(
    *,
    db_path: Path | None = None,
    strategy: str = "weather_router_v1",
    manifest_path: Path | None = None,
) -> int:
    """``python -m kq backtest-weather-clv`` entrypoint.

    Returns the count of brackets actually scored. 0 is a normal empty-DB state.
    """
    settings = get_settings()
    path = db_path or _db_path_from_settings(settings.database_url)
    results, used_strategy = _run_backtest_with_fallback(path, strategy)
    records = [rec for r in results.values() for rec in r.bracket_records]
    summary = evaluate_brackets(records)
    out_path = write_manifest(
        summary, strategy=used_strategy, out_path=manifest_path or MANIFEST_PATH
    )

    log.info(
        "weather_clv_backtest.done",
        strategy=used_strategy,
        n_evaluated=summary.n_evaluated,
        n_skipped_no_ndfd=summary.n_skipped_no_ndfd,
        n_skipped_no_model=summary.n_skipped_no_model,
        brier_model=summary.brier_model,
        brier_ndfd=summary.brier_ndfd,
        mean_edge=summary.mean_edge_vs_ndfd,
        win_rate=summary.win_rate_when_picked,
        manifest=str(out_path),
    )
    print(
        f"weather_clv_backtest: evaluated {summary.n_evaluated} brackets "
        f"(skipped {summary.n_skipped_no_ndfd} no-ndfd, "
        f"{summary.n_skipped_no_model} no-model); "
        f"mean_edge_vs_ndfd={summary.mean_edge_vs_ndfd} -> {out_path}"
    )
    return summary.n_evaluated


__all__ = ["MANIFEST_PATH", "main", "write_manifest"]
