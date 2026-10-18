from pathlib import Path

import pandas as pd
import pytest
from scripts.run_free_factor_screen import load_monthly, summarize


def test_loader_reads_first_monthly_table_not_annual_or_equal_weight(tmp_path: Path) -> None:
    path = tmp_path / "sample.csv"
    path.write_text("notes\n,first,second\n200601,1,2\n200602,3,4\n\n,first,second\n200601,50,60\n")
    result = load_monthly(path)
    assert result.loc["2006-01", "first"] == 0.01
    assert result.loc["2006-02", "second"] == 0.04
    assert len(result) == 2


@pytest.mark.parametrize("bad", ["-99.99", "-999", "NaN", "inf"])
def test_loader_rejects_missing_or_nonfinite(tmp_path: Path, bad: str) -> None:
    path = tmp_path / "sample.csv"
    path.write_text(f",x\n200601,{bad}\n")
    with pytest.raises(ValueError):
        load_monthly(path)


@pytest.mark.parametrize("dates", [["200601", "200601"], ["200601", "200603"]])
def test_loader_rejects_duplicate_or_missing_month(tmp_path: Path, dates: list[str]) -> None:
    path = tmp_path / "sample.csv"
    path.write_text(",x\n" + "\n".join(f"{date},1" for date in dates))
    with pytest.raises(ValueError):
        load_monthly(path)


def test_compounding_initial_loss_and_drag() -> None:
    index = pd.period_range("2006-01", "2006-12", freq="M")
    returns = pd.Series([-0.5, 0.5] + [0.0] * 10, index=index)
    metrics, annual = summarize(returns, pd.Series(0.0, index=index), 0.02)
    assert metrics["cagr"] == pytest.approx(-0.265)
    assert metrics["max_month_end_drawdown"] <= -0.5
    assert metrics["positive_years"] == 0
    assert annual.loc[2006] == pytest.approx(-0.265)


def test_partial_year_cannot_be_reported_as_annual() -> None:
    returns = pd.Series(0.01, index=pd.period_range("2006-02", "2006-12", freq="M"))
    with pytest.raises(ValueError):
        summarize(returns, returns, 0.0)
