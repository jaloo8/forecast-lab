"""Artificial complete-year accounting fixtures, not historical performance evidence."""

import csv
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from scripts.audit_annual_target import calendar_returns, screen, validate_case_coverage


def fixture_rows():
    days = []
    day = date(2006, 1, 2)
    while day <= date(2025, 12, 31):
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    # Preserve each year's boundary dates while fixing the artificial row count.
    remove = len(days) - 5031
    days = [day for day in days if not (day.month == 6 and (remove := remove - 1) >= 0)]
    assert len(days) == 5031
    return [
        {
            "session_date": day.isoformat(),
            "nav": str(Decimal(10000) * Decimal("1.1") ** (day.year - 2005)),
        }
        for day in days
    ]


def test_years_use_prior_endings_and_declared_capital():
    rows = fixture_rows()
    returns = calendar_returns(rows, Decimal(10000))
    assert set(returns) == set(range(2006, 2026))
    assert all(abs(value - Decimal("0.1")) < Decimal("1e-24") for value in returns.values())
    assert calendar_returns(rows, Decimal(20000))[2006] == Decimal("-0.45")


@pytest.mark.parametrize("bad_nav", ["NaN", "Infinity", "-1", "0"])
def test_invalid_nav_is_refused(bad_nav):
    rows = fixture_rows()
    rows[100]["nav"] = bad_nav
    with pytest.raises(ValueError, match="Invalid NAV"):
        calendar_returns(rows, Decimal(10000))


def test_incomplete_or_repeated_dates_are_not_flat_years():
    rows = fixture_rows()
    with pytest.raises(ValueError, match="complete"):
        calendar_returns(rows[:-1], Decimal(10000))
    rows[1]["session_date"] = rows[0]["session_date"]
    with pytest.raises(ValueError, match="date sequence"):
        calendar_returns(rows, Decimal(10000))


def registered_cases() -> list[dict[str, str]]:
    strategies = (
        "spy_hold",
        "equal_sectors",
        "sector_momentum",
        "spy_trend",
        "sector_momentum_trend",
        "equal_sectors_invvol",
        "sector_momentum_invvol",
        "sector_momentum_trend_invvol",
    )
    return [
        {"strategy": strategy, "cost_bps": cost}
        for strategy in strategies
        for cost in ("10", "25", "50")
    ]


def test_registered_case_coverage_accepts_any_row_order() -> None:
    validate_case_coverage(list(reversed(registered_cases())))


@pytest.mark.parametrize("damage", ["duplicate", "missing", "wrong_cost"])
def test_screen_refuses_incomplete_case_coverage_before_reading_paths(
    tmp_path: Path, damage: str
) -> None:
    cases = registered_cases()
    if damage == "duplicate":
        cases[-1] = cases[0].copy()  # Still 24 rows, but one account is absent.
    elif damage == "missing":
        cases.pop()
    else:
        cases[-1]["cost_bps"] = "100"  # Still 24 unique rows, but not the registered costs.
    with (tmp_path / "metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["strategy", "cost_bps"])
        writer.writeheader()
        writer.writerows(cases)
    # No daily/ledger files exist: coverage must fail before any account is evaluated.
    with pytest.raises(ValueError, match="each registered strategy/cost case exactly once"):
        screen(tmp_path, tmp_path / "output")
