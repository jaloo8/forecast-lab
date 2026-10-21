"""Independent Decimal reconstruction; does not import the index analysis module."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import date
from decimal import Decimal, getcontext
from functools import cache
from pathlib import Path
from typing import Any

getcontext().prec = 45
D = Decimal
YEARDAYS = D("365.2425")
Point = tuple[date, Decimal]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_implementation(manifest: dict[str, Any], root: Path) -> None:
    expected = {"src/kq/equities/option_benchmarks.py", "scripts/run_option_benchmarks.py"}
    entries = {name.replace("\\", "/"): value for name, value in manifest["implementation"].items()}
    assert len(entries) == len(manifest["implementation"]) and set(entries) == expected
    for name, fingerprint in entries.items():
        assert digest(root / name) == fingerprint


def verify_horizons(reported: list[dict[str, Any]], registered: list[int]) -> None:
    assert len(reported) == len(registered)
    assert {x["horizon_observations"] for x in reported} == set(registered)


def read(path: Path, name: str, date_name: str = "DATE") -> list[Point]:
    result = []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            text = row[date_name]
            if "/" in text:
                m, d, y = (int(v) for v in text.split("/"))
                day = date(y, m, d)
            else:
                day = date.fromisoformat(text)
            value = D(row[name])
            assert value.is_finite() and value > 0
            assert not result or result[-1][0] < day
            result.append((day, value))
    return result


@cache
def cost(days: int, drag: str) -> Decimal:
    return (-D(drag) * D(days) / YEARDAYS).exp()


def select(rows: list[Point], name: str) -> list[Point]:
    limited = [p for p in rows if p[0].year <= 2025]
    if name == "dense_complete_years":
        breaks = [
            i for i in range(1, len(limited)) if (limited[i][0] - limited[i - 1][0]).days > 31
        ]
        limited = limited[max(breaks, default=0) :]
        year = limited[0][0].year + 1
    else:
        assert name == "common_2014_2025"
        year = 2014
    counts = Counter(p[0].year for p in limited)
    assert year <= 2025 and all(counts[y] >= 240 for y in range(year, 2026))
    baseline = max(p[0] for p in limited if p[0].year == year - 1)
    return [p for p in limited if p[0] >= baseline]


def match(actual: Any, expected: Decimal | int | str | None) -> None:
    if isinstance(expected, Decimal):
        delta = abs(D(str(actual)) - expected)
        assert delta <= D("0.000000002") * max(D(1), abs(expected)), (actual, str(expected))
    else:
        assert actual == expected, (actual, expected)


def verify_metrics(reported: dict[str, Any], rows: list[Point], drag: str) -> int:
    initial, initial_level = rows[0]
    values = [D(1000) * v / initial_level * cost((d - initial).days, drag) for d, v in rows]
    days = (rows[-1][0] - initial).days
    peak = values[0]
    loss = D(0)
    ends = {}
    for (day, _), value in zip(rows, values, strict=True):
        peak = max(peak, value)
        loss = min(loss, value / peak - 1)
        ends[day.year] = value
    annual = {str(y): ends[y] / ends[y - 1] - 1 for y in ends if y - 1 in ends}
    scalar = {
        "start": str(initial),
        "end": str(rows[-1][0]),
        "observations": len(rows),
        "calendar_days": days,
        "terminal_normalized_value": values[-1],
        "cagr": ((values[-1] / 1000).ln() * YEARDAYS / days).exp() - 1,
        "observed_close_drawdown": loss,
        "worst_year": min(annual.values()) if annual else None,
        "negative_years": sum(v < 0 for v in annual.values()),
        "years_ge10pct": sum(v >= D("0.1") for v in annual.values()),
        "years_ge25pct": sum(v >= D("0.25") for v in annual.values()),
    }
    for key, expected in scalar.items():
        match(reported[key], expected)
    assert set(annual) == set(reported["calendar_returns"])
    for year, value in annual.items():
        match(reported["calendar_returns"][year], value)
    expected_gaps = []
    for i in range(1, len(rows)):
        a, b = rows[i - 1][0], rows[i][0]
        if (b - a).days > 7:
            expected_gaps.append({"from": str(a), "to": str(b), "calendar_days": (b - a).days})
    assert reported["gaps_over_seven_days"] == expected_gaps
    return len(rows)


def quantile(ordered: list[Decimal], fraction: str) -> Decimal:
    index = D(len(ordered) - 1) * D(fraction)
    i = int(index)
    if i == len(ordered) - 1:
        return ordered[i]
    return ordered[i] * (1 - index + i) + ordered[i + 1] * (index - i)


def verify_fresh(
    reported: dict[str, Any], rows: list[Point], drag: str, saved: list[dict[str, Any]]
) -> int:
    horizon = reported["horizon_observations"]
    seen = set()
    values = []
    for i in range(1, len(rows)):
        day, value = rows[i]
        month = (day.year, day.month)
        if month in seen:
            continue
        seen.add(month)
        if i + horizon >= len(rows):
            continue
        end, end_value = rows[i + horizon]
        change = end_value / value * cost((end - day).days, drag) - 1
        record = saved[len(values)]
        assert record["start"] == str(day) and record["end"] == str(end)
        match(record["return"], change)
        assert record["calendar_days"] == (end - day).days
        values.append(change)
    assert len(values) == reported["count"] == len(saved)
    if not values:
        return 0
    ordered = sorted(values)
    expected = {
        "mean": sum(values) / len(values),
        "median": quantile(ordered, "0.5"),
        "p05": quantile(ordered, "0.05"),
        "p95": quantile(ordered, "0.95"),
        "minimum": min(values),
        "maximum": max(values),
        "loss_fraction": D(sum(v < 0 for v in values)) / len(values),
        "double_fraction": D(sum(v >= 1 for v in values)) / len(values),
        "hundredfold_fraction": D(sum(v >= 99 for v in values)) / len(values),
        "half_loss_fraction": D(sum(v <= D("-0.5") for v in values)) / len(values),
    }
    for key, value in expected.items():
        match(reported[key], value)
    return len(values)


def check(protocol: Path, sources: Path, benchmark: Path, output: Path) -> dict[str, Any]:
    registration = json.loads(protocol.read_text(encoding="utf-8"))
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    verify_implementation(manifest, Path(__file__).resolve().parents[1])
    assert digest(protocol) == summary["registration_sha256"] == manifest["registration_sha256"]
    assert digest(sources / "inventory.json") == registration["source_manifest_sha256"]
    assert digest(benchmark) == registration["benchmark"]["sha256"]
    for filename, expected in manifest["outputs"].items():
        assert digest(output / filename) == expected
    inventory = json.loads((sources / "inventory.json").read_text(encoding="utf-8"))
    inputs = {}
    for item in inventory["sources"]:
        if item["status"] == 200:
            path = sources / (item["ticker"] + "_History.csv")
            assert digest(path) == item["sha256"]
            inputs[item["ticker"]] = read(path, item["ticker"])
    spy = dict(read(benchmark, "Adj Close", "Date"))
    trials: dict[tuple[str, str, str, int], list[dict[str, Any]]] = {}
    with (output / "fresh-starts.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            key = (row["ticker"], row["window"], str(row["annual_drag"]), row["horizon"])
            trials.setdefault(key, []).append(row)
    expected_cases = {
        (t, w, str(d))
        for t in registration["tickers"]
        for w in registration["windows"]
        for d in registration["annual_cost_drags"]
    }
    actual_cases = {(r["ticker"], r["window"], str(r["annual_drag"])) for r in summary["results"]}
    assert expected_cases == actual_cases and len(summary["results"]) == 150
    count = fresh_count = refusals = 0
    for result in summary["results"]:
        ticker, name, drag = result["ticker"], result["window"], str(result["annual_drag"])
        try:
            rows = select(inputs[ticker], name)
        except (AssertionError, ValueError):
            assert result["status"] == "refused"
            assert not any(key[:3] == (ticker, name, drag) for key in trials)
            refusals += 1
            continue
        assert result["status"] == "completed"
        count += verify_metrics(result, rows, drag)
        matching = [(d, v) for d, v in rows if d in spy]
        count += verify_metrics(result["matched_index"], matching, drag)
        count += verify_metrics(result["matched_spy"], [(d, spy[d]) for d, _ in matching], "0")
        verify_horizons(result["fresh_starts"], registration["short_horizons_sessions"])
        for fresh in result["fresh_starts"]:
            key = (ticker, name, drag, fresh["horizon_observations"])
            fresh_count += verify_fresh(fresh, rows, drag, trials.pop(key, []))
    assert not trials
    return {
        "status": "PASS",
        "scenarios": len(summary["results"]),
        "completed": len(summary["results"]) - refusals,
        "refusals_reconciled": refusals,
        "decimal_level_calculations": count,
        "fresh_starts_reconciled": fresh_count,
        "registration_sha256": digest(protocol),
        "summary_sha256": digest(output / "summary.json"),
        "checker_sha256": digest(Path(__file__)),
        "scope": (
            "Independent Decimal arithmetic from original CSVs; "
            "not independent vendor index replication"
        ),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    receipt = check(arguments.protocol, arguments.sources, arguments.benchmark, arguments.output)
    (arguments.output / "independent-accounting.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt))
