"""Artificial mathematical and missing-data checks, never historical profit evidence."""

import math
from datetime import date, timedelta
from pathlib import Path

import pytest
from scripts.check_option_benchmarks import verify_horizons, verify_implementation

from kq.equities.option_benchmarks import (
    Level,
    analyze,
    fresh_starts,
    gaps,
    load_levels,
    metrics,
    normalized,
    observed_drawdown,
    percentile,
    window,
)


def weekdays(start: date, end: date) -> list[Level]:
    rows = []
    at = start
    while at <= end:
        if at.weekday() < 5:
            rows.append(Level(at, 100.0))
        at += timedelta(days=1)
    return rows


def test_drawdown_counts_intermediate_loss_even_when_endpoint_recovers() -> None:
    assert observed_drawdown([1000, 1200, 600, 1500]) == -0.5


def test_calendar_cost_drag_spans_weekends_and_leap_year() -> None:
    rows = [Level(date(2023, 12, 29), 100), Level(date(2024, 12, 31), 100)]
    result = metrics(rows, 0.02)
    assert result["terminal_normalized_value"] == pytest.approx(
        1000 * math.exp(-0.02 * 368 / 365.2425)
    )
    assert result["cagr"] == pytest.approx(math.exp(-0.02) - 1)


def test_annual_returns_include_start_year_loss() -> None:
    rows = [
        Level(date(2023, 12, 29), 100),
        Level(date(2024, 12, 31), 80),
        Level(date(2025, 12, 31), 120),
    ]
    result = metrics(rows, 0)
    assert result["calendar_returns"] == pytest.approx({"2024": -0.2, "2025": 0.5})
    assert result["negative_years"] == 1


def test_sparse_early_history_is_not_treated_as_daily_history() -> None:
    rows = [Level(date(1991, 3, 4), 1), *weekdays(date(2023, 1, 2), date(2025, 12, 31))]
    selected = window(rows, "dense_complete_years")
    assert selected[0].day == date(2023, 12, 29)
    assert selected[1].day == date(2024, 1, 1)


def test_incomplete_year_refused_without_filling() -> None:
    rows = weekdays(date(2023, 1, 2), date(2025, 12, 31))
    # Distributed missing days keep every gap below the dense-segment reset threshold.
    remove = {x.day for i, x in enumerate(rows) if x.day.year == 2024 and i % 5 == 0}
    rows = [x for x in rows if x.day not in remove]
    with pytest.raises(ValueError, match="240"):
        window(rows, "dense_complete_years")


def test_fresh_starts_skip_baseline_and_use_observations_not_calendar_days() -> None:
    rows = weekdays(date(2024, 12, 31), date(2025, 4, 30))
    result = fresh_starts(rows, 0, 5)
    assert result["trials"][0]["start"] == "2025-01-01"
    assert result["trials"][0]["end"] == "2025-01-08"
    assert result["count"] == 4
    assert result["double_fraction"] == 0


def test_fresh_start_tail_is_not_shortened_to_fit() -> None:
    rows = weekdays(date(2024, 12, 31), date(2025, 1, 7))
    assert fresh_starts(rows, 0, 5)["count"] == 0


def test_thresholds_are_account_multiples_not_percentage_numbers() -> None:
    rows = [Level(date(2024, 12, 31), 1), Level(date(2025, 1, 2), 1), Level(date(2025, 1, 3), 100)]
    result = fresh_starts(rows, 0, 1)
    assert result["double_fraction"] == 1
    assert result["hundredfold_fraction"] == 1
    assert result["half_loss_fraction"] == 0


def test_linear_percentile_definition() -> None:
    assert percentile([0, 10], 0.05) == pytest.approx(0.5)


@pytest.mark.parametrize("value", ["nan", "inf", "0", "-1"])
def test_invalid_index_values_rejected(tmp_path: Path, value: str) -> None:
    path = tmp_path / "data.csv"
    path.write_text(f"DATE,A\n01/02/2025,1\n01/03/2025,{value}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="positive"):
        load_levels(path, "A")


def test_duplicate_dates_rejected(tmp_path: Path) -> None:
    path = tmp_path / "data.csv"
    path.write_text("DATE,A\n01/02/2025,1\n01/02/2025,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unique"):
        load_levels(path, "A")


def test_gaps_are_reported_without_synthetic_marks() -> None:
    rows = [Level(date(2025, 1, 2), 100), Level(date(2025, 1, 13), 100)]
    assert gaps(rows)[0]["calendar_days"] == 11
    assert len(normalized(rows, 0)) == 2


def test_benchmark_is_exact_intersection_and_rebased() -> None:
    rows = weekdays(date(2023, 1, 2), date(2025, 12, 31))
    spy = [Level(x.day, 200) for x in rows if x.day.year == 2025]
    result = analyze(rows, spy, "dense_complete_years", 0)
    assert result["matched_spy"]["start"] == "2025-01-01"
    assert result["matched_spy"]["terminal_normalized_value"] == 1000
    assert result["matched_spy"]["observations"] == len(spy)


def test_checker_rejects_omitted_or_duplicate_horizon() -> None:
    with pytest.raises(AssertionError):
        verify_horizons([{"horizon_observations": 5}], [5, 21, 63])
    with pytest.raises(AssertionError):
        verify_horizons([{"horizon_observations": h} for h in [5, 5, 63]], [5, 21, 63])


def test_checker_rejects_unbound_implementation(tmp_path: Path) -> None:
    with pytest.raises(AssertionError):
        verify_implementation({"implementation": {}}, tmp_path)


def test_checker_rejects_changed_implementation(tmp_path: Path) -> None:
    for name in ["src/kq/equities/option_benchmarks.py", "scripts/run_option_benchmarks.py"]:
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("changed", encoding="utf-8")
    with pytest.raises(AssertionError):
        verify_implementation(
            {
                "implementation": {
                    "src/kq/equities/option_benchmarks.py": "incorrect",
                    "scripts/run_option_benchmarks.py": "incorrect",
                }
            },
            tmp_path,
        )
