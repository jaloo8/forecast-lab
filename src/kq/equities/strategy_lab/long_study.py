"""Pure fixed-arm long-history research with reset budgets and explicit gaps."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from kq.equities.strategy_lab.engine_accounting import Prices

ARMS = ("M", "R", "V", "MR", "MV", "RV", "MRV")
HOLDS = (21, 63, 105)
EPOCHS = {
    "2006-2012": (2006, 2012),
    "2013-2019": (2013, 2019),
    "2020-2025": (2020, 2025),
    "2026": (2026, 2026),
}


def _features(frame: pd.DataFrame, prices: Prices, index: int) -> pd.DataFrame:
    """Return symbol, eligible, reason, as_of, M/R/V and percentile arm columns."""
    dates = prices.dates[index - 60 : index + 1]
    close = prices.closes.reindex(dates)
    window = frame[frame.session_date.isin(dates)]
    volume = window.pivot(index="session_date", columns="symbol", values="volume")
    volume = volume.reindex(index=dates, columns=close.columns)
    enough = close.notna().all()
    liquid = (close * volume).iloc[-20:].median().ge(20_000_000)
    affordable = close.iloc[-1].ge(5)
    score = pd.DataFrame(
        {
            "M": np.log(close.iloc[-6] / close.iloc[0])
            - np.log(close["SPY"].iloc[-6] / close["SPY"].iloc[0]),
            "R": -np.log(close.iloc[-1] / close.iloc[-6]),
            "V": -np.log(close / close.shift(1)).iloc[-20:].std(ddof=1),
        }
    ).drop(index="SPY")
    score["reason"] = np.select(
        [
            ~enough.reindex(score.index),
            ~affordable.reindex(score.index),
            ~liquid.reindex(score.index),
        ],
        ["insufficient_history", "price_below_5", "dollar_volume_below_20m"],
        default="eligible",
    )
    score["eligible"] = score.reason.eq("eligible")
    latest = window[window.session_date.eq(dates[-1])].set_index("symbol")
    score["as_of"] = pd.to_datetime(latest.as_of, utc=True).reindex(score.index)
    for arm in "MRV":
        score[f"rank_{arm}"] = score[arm].where(score.eligible).rank(method="average", pct=True)
    for arm in ARMS:
        score[f"score_{arm}"] = score[[f"rank_{component}" for component in arm]].mean(axis=1)
    return score.rename_axis("symbol").reset_index()


def _selection(row: Any, arm: str) -> dict[str, Any]:
    return {
        "symbol": row.symbol,
        "score": float(getattr(row, f"score_{arm}")),
        "as_of": pd.Timestamp(row.as_of).isoformat(),
        "components": {key: float(getattr(row, key)) for key in "MRV"},
        "ranks": {key: float(getattr(row, f"rank_{key}")) for key in "MRV"},
    }


def _decision(scored: pd.DataFrame, day: str) -> dict[str, Any]:
    eligible = scored[scored.eligible]
    return {
        "decision_date": day,
        "eligible_count": len(eligible),
        "candidate_count": len(scored),
        "insufficient_universe": len(eligible) < 5,
        "excluded_by_reason": {
            str(reason): sorted(group.symbol.tolist())
            for reason, group in scored[~scored.eligible].groupby("reason")
        },
        "scores": [
            dict(
                _selection(row, "MRV"),
                arm_scores={arm: float(getattr(row, f"score_{arm}")) for arm in ARMS},
            )
            for row in eligible.sort_values("symbol").itertuples()
        ],
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    complete = [row for row in rows if row["status"] == "complete"]
    unavailable = sum(row["status"] == "unavailable" for row in rows)
    measurable = bool(complete) and not unavailable
    returns = [row["net_return"] for row in complete]
    excess = [row["excess_vs_spy"] for row in complete]
    return {
        "cohort_count": len(complete),
        "unavailable_count": unavailable,
        "pending_count": sum(row["status"] == "pending" for row in rows),
        "cash_only_count": sum(not row["selected_symbols"] for row in complete),
        "mean_net_return": float(np.mean(returns)) if measurable else None,
        "median_net_return": float(np.median(returns)) if measurable else None,
        "mean_excess_vs_spy": float(np.mean(excess)) if measurable else None,
        "worst_cohort_return": min(returns) if measurable else None,
        "status": "incomplete" if unavailable else "complete" if complete else "no_outcomes",
    }


def _attempt(
    prices: Prices, scored: pd.DataFrame, arm: str, size: int, index: int, hold: int, cost: int
) -> dict[str, Any]:
    eligible = scored[scored.eligible].sort_values(
        [f"score_{arm}", "symbol"], ascending=[False, True]
    )
    selected = eligible.head(size if len(eligible) >= 5 else 0)
    row = prices.cohort(selected.symbol.tolist(), 10, index, hold, cost)
    benchmark = prices.cohort(["SPY"], 1, index, hold, cost, details=False)
    exposure = len(selected) / 10
    reference = benchmark["net_return"]
    matched = reference * exposure if reference is not None else None
    row.update(
        arm=arm,
        size=size,
        protocol_id=f"{arm}_n{size}_h{hold}_c{cost}",
        eligible_count=len(eligible),
        insufficient_universe=len(eligible) < 5,
        idle_cash_dollars=100 - 10 * len(selected),
        budget_dollars=100,
        selections=[_selection(item, arm) for item in selected.itertuples()],
        matched_spy_return=matched,
        excess_vs_spy=row["net_return"] - matched
        if row["net_return"] is not None and matched is not None
        else None,
    )
    return row


def compare_long(bars: pd.DataFrame) -> dict[str, Any]:
    """Compare 189 frozen variants; return JSON-compatible audits and summaries.

    Input: symbol, session_date, positive regular open/high/low/close/volume,
    simulated UTC session-close as_of. Only actual bars: absent history remains
    absent. Actual retrieval and adjustment metadata belong in the source manifest.
    All returns use a normalized $100 reset budget, not sequential account equity.
    Any missing mature outcome withholds that variant's aggregate return metrics.
    """
    frame = bars.copy()
    frame["session_date"] = pd.to_datetime(frame.session_date).dt.date
    if frame.duplicated(["symbol", "session_date"]).any():
        raise ValueError("Duplicate or revised symbol/session rows")
    prices = Prices(frame)
    if prices.valid.eq(False).any().any():
        raise ValueError("Invalid genuine bar or future simulated as_of")
    indices = sorted({index for hold in HOLDS for index in range(60, len(prices.dates), hold)})
    cache = {index: _features(frame, prices, index) for index in indices}
    decisions = [_decision(cache[index], prices.dates[index].isoformat()) for index in indices]
    cohorts = []
    results = []
    for arm in ARMS:
        for size in (1, 3, 5):
            for hold in HOLDS:
                for cost in (10, 25, 50):
                    attempts = [
                        _attempt(prices, cache[index], arm, size, index, hold, cost)
                        for index in range(60, len(prices.dates), hold)
                    ]
                    cohorts.extend(attempts)
                    epochs = {}
                    for name, (start, end) in EPOCHS.items():
                        within = [
                            row
                            for row in attempts
                            if row["exit_date"] is not None
                            and start <= int(row["decision_date"][:4]) <= end
                            and start <= int(row["exit_date"][:4]) <= end
                        ]
                        epochs[name] = _summary(within)
                    results.append(
                        dict(
                            _summary(attempts),
                            arm=arm,
                            size=size,
                            hold_sessions=hold,
                            cost_bps=cost,
                            protocol_id=f"{arm}_n{size}_h{hold}_c{cost}",
                            epochs=epochs,
                        )
                    )
    coverage = {
        str(symbol): {
            "observations": len(group),
            "first_session": min(group.session_date).isoformat(),
            "last_session": max(group.session_date).isoformat(),
        }
        for symbol, group in frame.groupby("symbol")
    }
    return {
        "results": results,
        "cohorts": cohorts,
        "decisions": decisions,
        "coverage": coverage,
        "limitations": [
            "Exploratory current-survivor sample; omitted dividends and delisting outcomes.",
            "Historical as_of is simulated; actual retrieval times remain in source metadata.",
            "Split-adjusted price/liquidity eligibility is a historical proxy.",
            "Calendar uses observed SPY sessions; shared missing exchange sessions are undetected.",
            "Reset $100 cohorts, $10 all-in per name and zero-interest idle cash; no account CAGR.",
            "No sequential loss pauses or account drawdown; fractional fills are hypothetical.",
            "Correlated fixed comparisons, no untouched holdout or validated winner.",
            "Missing mature outcomes withhold aggregate returns; pending cohorts remain explicit.",
            "Epoch metrics exclude cross-boundary outcomes, which remain in overall metrics.",
        ],
    }
