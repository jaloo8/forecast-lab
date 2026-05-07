"""Tests for the pure-function dashboard panel renderers.

No Streamlit required — every panel returns a markdown string we can
assert against directly.
"""

from __future__ import annotations

import json
from pathlib import Path

from kq.dashboard.panels import (
    ConformalRow,
    NbaClvSummary,
    conformal_caveats,
    format_conformal_table,
    format_nba_clv_skip_breakdown,
    format_nba_clv_summary,
    parse_conformal_rows,
    read_nba_clv_manifest,
)

# --------------------------- conformal panels ---------------------------


def test_parse_conformal_rows_extracts_blocks_and_skips_missing() -> None:
    """Stations missing a `conformal_summary` block are silently
    skipped — the dashboard surfaces "no data" rather than crashing."""
    stations = {
        "KAUS": {
            "conformal_summary": {
                "alpha": 0.1,
                "target_coverage": 0.9,
                "empirical_coverage": 0.857,
                "threshold": 0.364,
                "n_test": 14308,
                "pct_singleton": 0.962,
                "pct_full": 0.0,
                "pct_empty": 0.038,
            },
        },
        "KMDW": {},  # No conformal_summary at all -> skip
        "KJFK": {
            "conformal_summary": {
                "alpha": 0.1,
                "target_coverage": 0.9,
                "empirical_coverage": 0.898,
                "threshold": 0.500,
                "n_test": 14308,
                "pct_singleton": 0.992,
                "pct_full": 0.009,
                "pct_empty": 0.0,
            },
        },
    }
    rows = parse_conformal_rows(stations)
    assert {r.station for r in rows} == {"KAUS", "KJFK"}
    # Sorted alphabetically.
    assert [r.station for r in rows] == ["KAUS", "KJFK"]


def test_conformal_row_status_above_target() -> None:
    """Empirical >= target -> ✅."""
    row = ConformalRow(
        station="KMIA",
        n_test=100,
        target_coverage=0.9,
        empirical_coverage=0.911,
        threshold=0.394,
        pct_singleton=0.97,
        pct_full=0.0,
        pct_empty=0.034,
    )
    assert row.coverage_status == "✅"


def test_conformal_row_status_within_5pp() -> None:
    """Empirical between (target - 5pp) and target -> ⚠."""
    row = ConformalRow(
        station="KAUS",
        n_test=100,
        target_coverage=0.9,
        empirical_coverage=0.857,
        threshold=0.364,
        pct_singleton=0.96,
        pct_full=0.0,
        pct_empty=0.04,
    )
    assert row.coverage_status == "⚠️"


def test_conformal_row_status_below_5pp() -> None:
    """Empirical more than 5pp below target -> ❌."""
    row = ConformalRow(
        station="KMDW",
        n_test=100,
        target_coverage=0.9,
        empirical_coverage=0.78,
        threshold=0.40,
        pct_singleton=0.95,
        pct_full=0.0,
        pct_empty=0.05,
    )
    assert row.coverage_status == "❌"


def test_format_conformal_table_renders_header_plus_rows() -> None:
    rows = [
        ConformalRow(
            station="KAUS",
            n_test=14308,
            target_coverage=0.9,
            empirical_coverage=0.857,
            threshold=0.364,
            pct_singleton=0.962,
            pct_full=0.0,
            pct_empty=0.038,
        )
    ]
    md = format_conformal_table(rows)
    assert "Station" in md
    assert "KAUS" in md
    assert "14,308" in md
    assert "0.857" in md


def test_format_conformal_table_empty() -> None:
    md = format_conformal_table([])
    assert "No conformal coverage" in md


def test_conformal_caveats_mentions_non_exchangeability() -> None:
    """Pin the framing -- the user-facing explanation must call out
    that under-coverage is a drift signal, not a model bug."""
    text = conformal_caveats()
    assert "non-exchangeability" in text
    assert "drift" in text


# --------------------------- NBA CLV panels ---------------------------


def _write_manifest(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_read_nba_clv_manifest_returns_none_when_missing(tmp_path: Path) -> None:
    assert read_nba_clv_manifest(tmp_path / "absent.json") is None


def test_read_nba_clv_manifest_returns_none_on_unparseable(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{ not valid json", encoding="utf-8")
    assert read_nba_clv_manifest(bad) is None


def test_read_nba_clv_manifest_parses_full_payload(tmp_path: Path) -> None:
    out = tmp_path / "manifest.json"
    _write_manifest(
        out,
        {
            "n_evaluated": 100,
            "n_skipped_no_odds": 5,
            "n_skipped_no_crosswalk": 2,
            "n_skipped_no_pinnacle": 3,
            "brier_model": 0.21,
            "brier_pinnacle": 0.225,
            "mean_clv_vs_pinnacle": 0.005,
            "mean_signed_clv": 0.012,
            "win_rate_when_picked": 0.55,
            "generated_at": "2026-05-04T22:00:00+00:00",
        },
    )
    summary = read_nba_clv_manifest(out)
    assert summary is not None
    assert summary.n_evaluated == 100
    assert summary.brier_model == 0.21
    assert summary.mean_signed_clv == 0.012
    assert summary.passes_phase_5_5_bar is True


def test_read_nba_clv_manifest_handles_empty_payload(tmp_path: Path) -> None:
    """An empty / fresh-bootstrap manifest (n_evaluated=0, all metrics
    None) should parse cleanly and surface defaults."""
    out = tmp_path / "manifest.json"
    _write_manifest(
        out,
        {
            "n_evaluated": 0,
            "n_skipped_no_odds": 0,
            "n_skipped_no_crosswalk": 0,
            "n_skipped_no_pinnacle": 0,
            "brier_model": None,
            "brier_pinnacle": None,
            "mean_clv_vs_pinnacle": None,
            "mean_signed_clv": None,
            "win_rate_when_picked": None,
            "generated_at": "2026-05-04T22:00:00+00:00",
        },
    )
    summary = read_nba_clv_manifest(out)
    assert summary is not None
    assert summary.n_evaluated == 0
    assert summary.passes_phase_5_5_bar is False  # None metric -> bar fails


def test_passes_phase_5_5_bar_at_exactly_threshold() -> None:
    summary = NbaClvSummary(
        n_evaluated=100,
        n_skipped_no_odds=0,
        n_skipped_no_crosswalk=0,
        n_skipped_no_pinnacle=0,
        brier_model=0.20,
        brier_pinnacle=0.22,
        mean_clv_vs_pinnacle=0.01,
        mean_signed_clv=0.01,  # exactly at the +0.01 bar
        win_rate_when_picked=0.55,
        generated_at="2026-05-04T22:00:00+00:00",
    )
    assert summary.passes_phase_5_5_bar is True


def test_passes_phase_5_5_bar_just_below() -> None:
    summary = NbaClvSummary(
        n_evaluated=100,
        n_skipped_no_odds=0,
        n_skipped_no_crosswalk=0,
        n_skipped_no_pinnacle=0,
        brier_model=0.20,
        brier_pinnacle=0.22,
        mean_clv_vs_pinnacle=0.005,
        mean_signed_clv=0.0099,  # one bp below the bar
        win_rate_when_picked=0.55,
        generated_at="2026-05-04T22:00:00+00:00",
    )
    assert summary.passes_phase_5_5_bar is False


def test_format_nba_clv_summary_no_manifest() -> None:
    md = format_nba_clv_summary(None)
    assert "No NBA CLV manifest" in md
    assert "backtest-nba-clv" in md  # CLI hint included


def test_format_nba_clv_summary_empty_evaluations(tmp_path: Path) -> None:
    out = tmp_path / "m.json"
    _write_manifest(
        out,
        {
            "n_evaluated": 0,
            "n_skipped_no_odds": 0,
            "n_skipped_no_crosswalk": 0,
            "n_skipped_no_pinnacle": 0,
            "brier_model": None,
            "brier_pinnacle": None,
            "mean_clv_vs_pinnacle": None,
            "mean_signed_clv": None,
            "win_rate_when_picked": None,
            "generated_at": "2026-05-04T22:00:00+00:00",
        },
    )
    summary = read_nba_clv_manifest(out)
    md = format_nba_clv_summary(summary)
    assert "no games evaluated yet" in md
    assert "build-nba-crosswalk" in md  # CLI hint to fix the no-data state


def test_format_nba_clv_summary_with_evaluations(tmp_path: Path) -> None:
    out = tmp_path / "m.json"
    _write_manifest(
        out,
        {
            "n_evaluated": 100,
            "n_skipped_no_odds": 5,
            "n_skipped_no_crosswalk": 2,
            "n_skipped_no_pinnacle": 3,
            "brier_model": 0.21,
            "brier_pinnacle": 0.225,
            "mean_clv_vs_pinnacle": 0.005,
            "mean_signed_clv": 0.012,
            "win_rate_when_picked": 0.55,
            "generated_at": "2026-05-04T22:00:00+00:00",
        },
    )
    summary = read_nba_clv_manifest(out)
    md = format_nba_clv_summary(summary)
    assert "100 games evaluated" in md
    assert "✅" in md  # passes_phase_5_5_bar = True with msc = 0.012
    assert "+0.0120" in md or "+0.012" in md  # mean_signed_clv displayed


def test_format_nba_clv_skip_breakdown_renders_table() -> None:
    summary = NbaClvSummary(
        n_evaluated=100,
        n_skipped_no_odds=5,
        n_skipped_no_crosswalk=2,
        n_skipped_no_pinnacle=3,
        brier_model=0.20,
        brier_pinnacle=0.22,
        mean_clv_vs_pinnacle=0.005,
        mean_signed_clv=0.012,
        win_rate_when_picked=0.55,
        generated_at="2026-05-04T22:00:00+00:00",
    )
    md = format_nba_clv_skip_breakdown(summary)
    assert "no_crosswalk" in md
    assert "no_odds" in md
    assert "no_pinnacle" in md
    assert "**total skipped** | **10**" in md  # 5+2+3
    assert "of 110 candidate games" in md  # 100 + 10


def test_format_nba_clv_skip_breakdown_no_manifest() -> None:
    """No manifest -> empty string (the summary panel already explains
    the no-data state; no need to duplicate)."""
    assert format_nba_clv_skip_breakdown(None) == ""
