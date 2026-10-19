import argparse
import json

import pandas as pd
import pytest
from scripts.prepare_options_extension import quote_windows
from scripts.report_options_extension import block_interval, run, stressed, summarize

from kq.equities.options_replay import ReplayResult


def test_windows_include_boundary_and_coalesce_without_duplicate_coverage():
    at = pd.Timestamp("2024-06-10T14:00:00Z")
    assert quote_windows(at, at + pd.Timedelta(minutes=10)) == [
        (at - pd.Timedelta(minutes=10), at + pd.Timedelta(minutes=20))
    ]
    assert len(quote_windows(at, at + pd.Timedelta(hours=1))) == 2


def test_stress_rechecks_affordability_and_keeps_missing_exit_unknown():
    expensive = ReplayResult("closed", entry_debit=97, exit_cash=103, net_cash=6)
    assert stressed(expensive, 0.01).status == "skipped_entry"
    missing = ReplayResult("unresolved_exit", entry_debit=40)
    got = stressed(missing, 0.02)
    assert got.entry_debit == 44 and got.net_cash is None
    closed = ReplayResult("closed", entry_debit=40, exit_cash=50, net_cash=10)
    assert stressed(closed, 0.01).net_cash == pytest.approx(6)


def test_summary_includes_initial_drawdown_and_unresolved_cash():
    df = pd.DataFrame(
        [
            dict(status="closed", net_cash=-10, entry_debit=50),
            dict(status="closed", net_cash=5, entry_debit=50),
            dict(status="unresolved_exit", net_cash=None, entry_debit=60),
        ]
    )
    result = summarize(df)
    assert result["closed_net_usd"] == -5
    assert result["closed_max_drawdown_usd"] == 10
    assert result["unresolved_debit_usd"] == 60
    assert result["closed_win_rate"] == 0.5


def test_no_eligible_contracts_report_is_explicit_not_zero_profit(tmp_path):
    census = tmp_path / "census.csv"
    pd.DataFrame(
        [
            dict(
                session="2024-01-02",
                status="underlying_only",
                year=2024,
                volatility="low",
                trend="above_60d",
                pilot_options_cached=False,
                next_day_weekend=False,
            )
        ]
    ).to_csv(census, index=False)
    selections = tmp_path / "selections.json"
    selections.write_text(json.dumps([dict(session="2024-01-02", status="no_eligible_chain")]))
    output = tmp_path / "report"
    run(
        argparse.Namespace(
            root=tmp_path / "cache", selections=selections, census=census, output=output
        )
    )
    report = json.loads((output / "report.json").read_text())
    assert report["0"]["overall"]["closed_net_usd"] is None
    assert report["0"]["overall"]["statuses"] == {"no_eligible_chain": 1}


def test_block_interval_does_not_claim_precision_from_three_trades():
    small = pd.DataFrame(dict(status=["closed"] * 3, net_cash=[-16.6, -18.6, 18.4]))
    assert block_interval(small) is None
