import numpy as np
import pandas as pd
import pytest
from scripts.run_sector_study import metrics, run_study


def test_compounding_drawdown_and_annual_thresholds():
    daily = pd.DataFrame(
        {
            "session_date": pd.to_datetime(["2006-01-03", "2006-12-29", "2007-12-31"]),
            "nav": [9000.0, 15000.0, 7500.0],
        }
    )
    result = metrics(daily)
    assert result["cagr"] == pytest.approx(np.sqrt(0.75) - 1)
    assert result["mean_annual"] == 0
    assert result["max_drawdown"] == -0.5
    assert result["annual"] == {2006: 0.5, 2007: -0.5}
    assert result["years_ge_10pct"] == result["years_ge_20pct"] == 1
    assert result["positive_years"] == 1


def test_initial_capital_is_drawdown_anchor():
    daily = pd.DataFrame(
        {"session_date": pd.to_datetime(["2006-01-03", "2006-12-29"]), "nav": [9000.0, 9500.0]}
    )
    result = metrics(daily)
    assert result["max_drawdown"] == pytest.approx(-0.1)
    assert result["worst_year"] == pytest.approx(-0.05)


def test_monthly_rolling_year_uses_12_periods_not_average():
    dates = pd.date_range("2006-01-31", periods=24, freq="ME")
    daily = pd.DataFrame({"session_date": dates, "nav": 10000 * 1.01 ** np.arange(1, 25)})
    result = metrics(daily)
    assert result["rolling12_min"] == pytest.approx(1.01**12 - 1)
    assert result["rolling12_max"] == pytest.approx(1.01**12 - 1)


def test_existing_output_is_never_overwritten(tmp_path):
    with pytest.raises(FileExistsError):
        run_study(tmp_path / "missing.zip", tmp_path)
