"""Keep historical experiments separate from prospective account performance."""

import json
from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_historical_panel_labels_bias_and_does_not_claim_account_returns(tmp_path: Path) -> None:
    result = {
        "label": "Exploratory study",
        "captured_at": "2026-09-28T00:00:00Z",
        "source_hash": "a" * 64,
        "cohorts": [],
        "groups": [
            {
                "block": "2023-2026",
                "horizon_sessions": 20,
                "cohort_count": 30,
                "invested_count": 28,
                "mean_net_return": 0.01,
                "mean_excess_vs_matched_spy": -0.002,
                "mean_spy_market_net_return": 0.012,
                "positive_fraction_invested": 0.6,
                "worst_cohort": {"net_return": -0.2},
            }
        ],
    }
    (tmp_path / "historical-study.json").write_text(json.dumps(result), encoding="utf-8")
    app = AppTest.from_string(
        "from pathlib import Path\nfrom kq.equities.study_panel import render_study\n"
        f"render_study(Path({str(tmp_path)!r}))"
    ).run()
    assert not app.exception
    assert not app.error
    assert any("survivors" in warning.value for warning in app.warning)
    assert not app.metric
    assert app.dataframe[0].value.iloc[0]["Ahead of matched SPY (pp)"] == -0.2
    assert app.dataframe[0].value.iloc[0]["Worst period (%)"] == -20


def test_missing_study_is_an_honest_empty_state(tmp_path: Path) -> None:
    app = AppTest.from_string(
        "from pathlib import Path\nfrom kq.equities.study_panel import render_study\n"
        f"render_study(Path({str(tmp_path)!r}))"
    ).run()
    assert not app.exception
    assert app.info
