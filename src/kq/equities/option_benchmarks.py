"""Analysis of published hypothetical option-index levels, never broker execution."""

from __future__ import annotations

import csv
import math
from collections import Counter
from dataclasses import dataclass
from datetime import date
from itertools import pairwise
from pathlib import Path
from statistics import mean
from typing import Any


@dataclass(frozen=True)
class Level:
    day: date
    value: float


def load_levels(path: Path, column: str, *, date_column: str = "DATE") -> list[Level]:
    """Validate the whole supplied series; do not silently sort or fill bad data."""
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    result: list[Level] = []
    for row in rows:
        text = row[date_column]
        if "/" in text:
            month, day, year = map(int, text.split("/"))
            at = date(year, month, day)
        else:
            at = date.fromisoformat(text)
        value = float(row[column])
        if not math.isfinite(value) or value <= 0:
            raise ValueError("Finite positive index levels required")
        if result and at <= result[-1].day:
            raise ValueError("Dates must be unique and increasing")
        result.append(Level(at, value))
    if len(result) < 2:
        raise ValueError("Insufficient data")
    return result


def window(levels: list[Level], name: str) -> list[Level]:
    data = [x for x in levels if x.day <= date(2025, 12, 31)]
    if not data:
        raise ValueError("No data before cutoff")
    if name == "dense_complete_years":
        start = 0
        for i in range(1, len(data)):
            if (data[i].day - data[i - 1].day).days > 31:
                start = i
        data = data[start:]
        first_year = data[0].day.year + 1
    elif name == "common_2014_2025":
        first_year = 2014
    else:
        raise ValueError("Unregistered window")
    baseline = [x for x in data if x.day.year == first_year - 1]
    if not baseline or first_year > 2025:
        raise ValueError("Missing prior-year baseline")
    following = [x for x in data if first_year <= x.day.year <= 2025]
    counts = Counter(x.day.year for x in following)
    if any(counts[y] < 240 for y in range(first_year, 2026)):
        raise ValueError("At least 240 observations required in every full year")
    return [baseline[-1], *following]


def normalized(levels: list[Level], drag: float) -> list[float]:
    if not math.isfinite(drag) or drag < 0:
        raise ValueError("Invalid annual drag")
    first = levels[0]
    return [
        1000 * x.value / first.value * math.exp(-drag * (x.day - first.day).days / 365.2425)
        for x in levels
    ]


def observed_drawdown(values: list[float]) -> float:
    peak = values[0]
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        worst = min(worst, value / peak - 1)
    return worst


def gaps(levels: list[Level]) -> list[dict[str, Any]]:
    return [
        {"from": a.day.isoformat(), "to": b.day.isoformat(), "calendar_days": (b.day - a.day).days}
        for a, b in pairwise(levels)
        if (b.day - a.day).days > 7
    ]


def metrics(levels: list[Level], drag: float) -> dict[str, Any]:
    values = normalized(levels, drag)
    days = (levels[-1].day - levels[0].day).days
    if days <= 0:
        raise ValueError("Positive elapsed time required")
    year_ends: dict[int, float] = {}
    for item, value in zip(levels, values, strict=True):
        year_ends[item.day.year] = value
    annual = {
        str(y): value / year_ends[y - 1] - 1 for y, value in year_ends.items() if y - 1 in year_ends
    }
    return {
        "start": levels[0].day.isoformat(),
        "end": levels[-1].day.isoformat(),
        "observations": len(values),
        "calendar_days": days,
        "terminal_normalized_value": values[-1],
        "cagr": (values[-1] / 1000) ** (365.2425 / days) - 1,
        "observed_close_drawdown": observed_drawdown(values),
        "calendar_returns": annual,
        "worst_year": min(annual.values()) if annual else None,
        "negative_years": sum(x < 0 for x in annual.values()),
        "years_ge10pct": sum(x >= 0.1 for x in annual.values()),
        "years_ge25pct": sum(x >= 0.25 for x in annual.values()),
        "gaps_over_seven_days": gaps(levels),
        "drawdown_scope": (
            "Observed published closes only; gaps and intraday losses may understate loss"
        ),
    }


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    point = (len(ordered) - 1) * probability
    lower = int(point)
    upper = math.ceil(point)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (point - lower)


def fresh_starts(levels: list[Level], drag: float, horizon: int) -> dict[str, Any]:
    if horizon <= 0:
        raise ValueError("Positive horizon required")
    seen: set[tuple[int, int]] = set()
    trials: list[dict[str, Any]] = []
    # The prior December baseline is not a fresh start inside the requested full years.
    for i, item in enumerate(levels[1:], start=1):
        month = (item.day.year, item.day.month)
        if month in seen:
            continue
        seen.add(month)
        if i + horizon >= len(levels):
            continue
        end = levels[i + horizon]
        change = end.value / item.value * math.exp(-drag * (end.day - item.day).days / 365.2425) - 1
        trials.append(
            {
                "start": str(item.day),
                "end": str(end.day),
                "return": change,
                "calendar_days": (end.day - item.day).days,
            }
        )
    returns = [x["return"] for x in trials]
    if not returns:
        return {"horizon_observations": horizon, "count": 0, "trials": []}
    return {
        "horizon_observations": horizon,
        "count": len(returns),
        "mean": mean(returns),
        "median": percentile(returns, 0.5),
        "p05": percentile(returns, 0.05),
        "p95": percentile(returns, 0.95),
        "minimum": min(returns),
        "maximum": max(returns),
        "loss_fraction": sum(x < 0 for x in returns) / len(returns),
        "double_fraction": sum(x >= 1 for x in returns) / len(returns),
        "hundredfold_fraction": sum(x >= 99 for x in returns) / len(returns),
        "half_loss_fraction": sum(x <= -0.5 for x in returns) / len(returns),
        "trials": trials,
    }


def analyze(levels: list[Level], benchmark: list[Level], name: str, drag: float) -> dict[str, Any]:
    selected = window(levels, name)
    result = metrics(selected, drag)
    by_day = {x.day: x for x in benchmark}
    matching = [x for x in selected if x.day in by_day]
    if len(matching) < 2:
        raise ValueError("Insufficient matched benchmark dates")
    result["matched_index"] = metrics(matching, drag)
    result["matched_spy"] = metrics([by_day[x.day] for x in matching], 0)
    result["fresh_starts"] = [fresh_starts(selected, drag, h) for h in (5, 21, 63)]
    return result
