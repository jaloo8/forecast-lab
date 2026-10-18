"""Locked, point-in-time historical stock study checks."""

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from kq.equities.historical_study import main, run_study

SYMBOLS = ("AAPL", "MSFT", "AMZN", "JPM", "XOM", "COST", "SPY")


def test_explicit_universe_reuses_rules_without_changing_fixed_default() -> None:
    source = _source()
    source["universe"] = ["AAPL", "MSFT"]
    source["bars"] = [row for row in source["bars"] if row["symbol"] in {"AAPL", "MSFT", "SPY"}]
    with pytest.raises(ValueError):
        run_study(source)
    broad = run_study(source, stocks=("AAPL", "MSFT"))
    assert broad["protocol"]["stocks"] == ["AAPL", "MSFT"]
    assert broad["protocol"]["friction_each_side_bps"] == 10
    assert broad["cohorts"][0]["net_return"] == pytest.approx(120 / 112 * 0.999 / 1.001 - 1)
    with pytest.raises(ValueError):
        run_study(source, stocks=("AAPL", "AAPL"))


def _source(*, rising: bool = True, start: date = date(2010, 1, 4), count: int = 160) -> dict:
    days = []
    day = start
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    results = []
    for symbol in SYMBOLS:
        bars = []
        for i, session in enumerate(days):
            price = 100.0 + 2.0 * i if rising and symbol == "AAPL" else 100.0
            bars.append(
                {
                    "begins_at": datetime.combine(session, datetime.min.time(), UTC).isoformat(),
                    "open_price": str(price),
                    "high_price": str(price),
                    "low_price": str(price),
                    "close_price": str(price),
                    "volume": 1000,
                    "session": "reg",
                }
            )
        results.append({"symbol": symbol, "interval": "day", "bounds": "regular", "bars": bars})
    return {
        "captured_at": "2011-01-01T00:00:00Z",
        "benchmark": "SPY",
        "universe": list(SYMBOLS[:-1]),
        "adjustment_type": "split",
        "bars": results,
    }


def test_next_open_costs_and_nonoverlapping_cohorts() -> None:
    result = run_study(_source())
    rows = [row for row in result["cohorts"] if row["horizon_sessions"] == 5]
    first = rows[0]
    assert first["selected"] == ["AAPL"]
    assert first["signal_date"] == "2010-01-11"
    assert first["entry_date"] == "2010-01-12"
    assert first["exit_date"] == "2010-01-18"
    gross = 120 / 112 - 1
    expected_net = 120 / 112 * 0.999 / 1.001 - 1
    assert first["gross_return"] == pytest.approx(gross)
    assert first["net_return"] == pytest.approx(expected_net)
    assert first["spy_market_net_return"] == pytest.approx(0.999 / 1.001 - 1)
    assert rows[1]["entry_date"] > first["exit_date"]
    assert first["signal_as_of"].endswith("21:00:00+00:00")
    assert all(row["signal_as_of"].endswith(("20:00:00+00:00", "21:00:00+00:00")) for row in rows)


def test_cash_cohort_is_not_reported_as_spy_investment() -> None:
    result = run_study(_source(rising=False))
    group = next(item for item in result["groups"] if item["horizon_sessions"] == 5)
    assert group["invested_count"] == 0
    assert group["positive_fraction_invested"] is None
    assert group["mean_net_return"] == 0.0
    assert group["mean_excess_vs_matched_spy"] == 0.0
    assert group["mean_spy_market_net_return"] < 0
    row = next(item for item in result["cohorts"] if item["horizon_sessions"] == 5)
    assert row["selected"] == []
    assert row["net_return"] == row["matched_spy_net_return"] == 0.0
    assert row["spy_market_net_return"] < 0


def test_equal_positive_scores_choose_three_tickers_deterministically() -> None:
    source = _source()
    rising = source["bars"][0]["bars"]
    for series in source["bars"][:6]:
        series["bars"] = [dict(bar) for bar in rising]
    first = next(row for row in run_study(source)["cohorts"] if row["horizon_sessions"] == 5)
    assert first["selected"] == ["AAPL", "AMZN", "COST"]


def test_capture_must_follow_completed_bar() -> None:
    source = _source()
    source["captured_at"] = source["bars"][0]["bars"][-1]["begins_at"]
    with pytest.raises(ValueError, match="capture"):
        run_study(source)


@pytest.mark.parametrize(
    "defect", ["missing", "duplicate", "synthetic", "nan", "bad_ohlc", "boolean"]
)
def test_bad_price_history_fails_closed(defect: str) -> None:
    source = _source()
    bars = source["bars"][0]["bars"]
    if defect == "missing":
        bars.pop(8)
    elif defect == "duplicate":
        bars.insert(8, dict(bars[8]))
    elif defect == "synthetic":
        bars[8]["session"] = "synthetic"
    elif defect == "nan":
        bars[8]["close_price"] = "nan"
    elif defect == "boolean":
        for key in ("open_price", "high_price", "low_price", "close_price"):
            bars[8][key] = True
    else:
        bars[8]["high_price"] = "1"
    with pytest.raises(ValueError):
        run_study(source)


def test_block_exit_never_crosses_boundary_and_warmup_may_precede_it() -> None:
    source = _source(start=date(2018, 11, 1), count=150)
    source["captured_at"] = "2019-12-01T00:00:00Z"
    result = run_study(source)
    early = [r for r in result["cohorts"] if r["block"] == "2010-2018"]
    late = [r for r in result["cohorts"] if r["block"] == "2019-2022"]
    assert early and late
    assert all(r["exit_date"] <= "2018-12-31" for r in early)
    assert all(r["entry_date"] >= "2019-01-01" for r in late)


def test_cli_writes_study_only_and_preserves_paper_ledger(tmp_path: Path) -> None:
    source = _source()
    input_path = tmp_path / "history.json"
    input_path.write_text(json.dumps(source), encoding="utf-8")
    paper = tmp_path / "paper.sqlite"
    paper.write_bytes(b"untouched ledger sentinel")
    output = tmp_path / "study.json"
    assert main(["--input", str(input_path), "--output", str(output)]) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    canonical = json.dumps(source, sort_keys=True, separators=(",", ":"), allow_nan=False)
    assert payload["source_hash"] == hashlib.sha256(canonical.encode()).hexdigest()
    assert payload["cohorts"]
    assert paper.read_bytes() == b"untouched ledger sentinel"
