"""Exploratory fixed-grid comparisons; never writes to forward paper accounts."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from kq.equities.strategy_lab.engine_accounting import Prices
from kq.equities.strategy_lab.features import score_candidates
from kq.equities.strategy_lab.registry import SelectionSpec, selection_specs


def _summary(
    spec: SelectionSpec, hold: int, cost: int, cohorts: list[dict[str, Any]]
) -> dict[str, Any]:
    finished = [row for row in cohorts if row["status"] == "complete"]
    unavailable = sum(row["status"] == "unavailable" for row in cohorts)
    returns = [row["net_return"] for row in finished]
    excess = [row["excess_vs_spy"] for row in finished]
    measured = bool(returns) and not unavailable
    status = "complete" if measured else "no_outcomes"
    if unavailable:
        status = "incomplete"
    elif measured and not any(row["selected_symbols"] for row in finished):
        status = "no_selections"
    return {
        "selection_id": spec.selection_id,
        "family": spec.family,
        "lookback": spec.lookback,
        "size": spec.size,
        "hold_sessions": hold,
        "cost_bps": cost,
        "protocol_id": f"{spec.selection_id}_h{hold}_c{cost}",
        "cohort_count": len(finished),
        "unavailable_count": unavailable,
        "pending_count": sum(row["status"] == "pending" for row in cohorts),
        "mean_exposure": float(np.mean([row["exposure"] for row in finished]))
        if finished
        else None,
        "mean_net_return": float(np.mean(returns)) if measured else None,
        "median_net_return": float(np.median(returns)) if measured else None,
        "mean_excess_vs_spy": float(np.mean(excess))
        if measured and all(value is not None for value in excess)
        else None,
        "worst_cohort_return": min(returns) if measured else None,
        "status": status,
    }


def _scores(
    bars: pd.DataFrame, prices: Prices, specs: tuple[SelectionSpec, ...]
) -> dict[tuple[int, str, int], pd.DataFrame]:
    cache = {}
    pairs = {(spec.family, spec.lookback) for spec in specs} | {("low_volatility", 60)}
    for index in range(60, len(prices.dates), 5):
        window = bars[bars.session_date.between(prices.dates[index - 60], prices.dates[index])]
        for family, lookback in sorted(pairs):
            cache[index, family, lookback] = score_candidates(
                window, prices.dates[index], family, lookback
            )
    return cache


def _check_benchmark(row: dict[str, Any], scores: pd.DataFrame) -> None:
    if scores.reason.eq("unavailable_benchmark").any():
        row.update(
            status="unavailable",
            reason="unavailable_benchmark",
            gross_return=None,
            entry_cost=None,
            exit_cost=None,
            net_return=None,
            invested_exposure=None,
            missing_symbols=["SPY"],
        )


def _controls(
    prices: Prices, cache: dict[tuple[int, str, int], pd.DataFrame]
) -> tuple[list[dict[str, Any]], dict[tuple[int, int, int], dict[str, Any]]]:
    rows = []
    spy = {}
    for hold in (5, 20):
        for index in range(60, len(prices.dates), hold):
            scores = cache[index, "low_volatility", 60]
            universe = scores.loc[scores.eligible, "symbol"].tolist()
            for cost in (10, 25, 50):
                for name, symbols in [
                    ("cash", []),
                    ("spy", ["SPY"]),
                    ("eligible_universe", universe),
                ]:
                    row = prices.cohort(symbols, len(symbols), index, hold, cost, details=False)
                    if name == "eligible_universe":
                        _check_benchmark(row, scores)
                    row["control"] = name
                    rows.append(row)
                    if name == "spy":
                        spy[index, hold, cost] = row
    return rows, spy


def compare(bars: pd.DataFrame, specs: tuple[SelectionSpec, ...] | None = None) -> dict[str, Any]:
    """Return JSON-compatible summary, cohort audit and control rows.

    Input schema: symbol, session_date, open/high/low/close/volume and simulated
    session-close as_of. Actual source retrieval times belong in source metadata.
    Each cohort includes decision/entry/exit dates, allocations, price gain and
    both costs. Exposure denotes allocated slots including their entry costs;
    invested_exposure is share notional alone. Pending cohorts are explicit and
    mature missing outcomes withhold the entire variant's return aggregates.
    """
    specs = selection_specs() if specs is None else specs
    if len({spec.selection_id for spec in specs}) != len(specs):
        raise ValueError("Duplicate selection configurations")
    frame = bars.copy()
    frame["session_date"] = pd.to_datetime(frame.session_date).dt.date
    if frame.duplicated(["symbol", "session_date"]).any():
        raise ValueError("Duplicate or revised symbol/session rows")
    prices = Prices(frame)
    cache = _scores(frame, prices, specs)
    controls, spy = _controls(prices, cache)
    exclusions = [
        {
            "decision_date": prices.dates[index].isoformat(),
            "family": family,
            "lookback": lookback,
            "symbols_by_reason": {
                str(reason): sorted(group.symbol.tolist())
                for reason, group in scored.loc[~scored.eligible].groupby("reason")
            },
        }
        for (index, family, lookback), scored in cache.items()
    ]
    cohorts = []
    results = []
    for spec in specs:
        for hold in (5, 20):
            for cost in (10, 25, 50):
                attempts = []
                for index in range(60, len(prices.dates), hold):
                    scored = cache[index, spec.family, spec.lookback]
                    eligible = scored[scored.eligible].sort_values(
                        ["score", "symbol"], ascending=[False, True]
                    )
                    selected = eligible.head(spec.size)
                    row = prices.cohort(selected.symbol.tolist(), spec.size, index, hold, cost)
                    _check_benchmark(row, scored)
                    row.update(
                        selection_id=spec.selection_id,
                        eligible_count=len(eligible),
                        excluded_count=len(scored) - len(eligible),
                        exclusion_reasons=scored.loc[~scored.eligible, "reason"]
                        .value_counts()
                        .to_dict(),
                        selections=[
                            {
                                "symbol": item.symbol,
                                "score": float(item.score),
                                "as_of": pd.Timestamp(item.as_of).isoformat(),
                            }
                            for item in selected.itertuples()
                        ],
                    )
                    reference = spy[index, hold, cost]["net_return"]
                    row["excess_vs_spy"] = (
                        row["net_return"] - reference
                        if row["net_return"] is not None and reference is not None
                        else None
                    )
                    attempts.append(row)
                cohorts.extend(attempts)
                results.append(_summary(spec, hold, cost, attempts))
    return {
        "results": results,
        "cohorts": cohorts,
        "controls": controls,
        "exclusions": exclusions,
        "limitations": [
            "Exploratory: this historical period has already been inspected.",
            "Survivor bias: delisted stocks missing; complete histories condition on availability.",
            "Short history, correlated experiments and omitted dividends limit inference.",
            "Fractional shares and next-open fills are hypothetical; costs are assumptions.",
            "All-in equal slots reserve entry costs; unused slots stay cash with zero interest.",
            "as_of is simulated; actual retrieval times remain source metadata.",
            "Eligible-universe controls use 60-session history and common price/liquidity gates.",
            "Pending cohorts are explicit; any missing mature outcome withholds aggregate returns.",
        ],
    }
