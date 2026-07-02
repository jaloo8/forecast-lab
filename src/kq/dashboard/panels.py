"""Pure-function panel renderers for the Streamlit dashboard.

These functions read manifest JSONs + DuckDB rows, format them as
markdown / structured dicts, and return strings ready for
``st.markdown(...)``. Keeping them as pure functions means we can
unit-test the rendering without spinning up Streamlit.

Two domains live here:

- **Conformal-coverage panels** (``conformal_*``) -- consume the
  ``conformal_summary`` block emitted by :mod:`kq.backtest.engine`
  per station per backtest manifest (PR #32 lands the field).
- **NBA CLV panels** (``nba_clv_*``) -- consume the manifest emitted
  by :mod:`kq.flows.run_nba_clv_backtest` (PR #44 lands the flow).

The panels are intentionally small: each takes a payload, returns a
markdown string + an optional JSON-safe summary dict for telemetry.
The Streamlit integration in ``streamlit_app.py`` calls them and
renders the markdown -- a follow-up PR wires the integration once
the user is ready to upgrade the prototype.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# --------------------- conformal coverage panels ---------------------


@dataclass(frozen=True, slots=True)
class ConformalRow:
    """One per-station row of the conformal coverage table."""

    station: str
    n_test: int
    target_coverage: float
    empirical_coverage: float
    threshold: float
    pct_singleton: float
    pct_full: float
    pct_empty: float

    @property
    def coverage_status(self) -> str:
        """Glyph for the dashboard table.

        - ✅ when empirical >= target
        - ⚠️ when within 5pp of target (the standard slack at our
          test-window sample sizes)
        - ❌ when more than 5pp under target
        """
        delta = self.empirical_coverage - self.target_coverage
        if delta >= 0.0:
            return "✅"
        if delta >= -0.05:
            return "⚠️"
        return "❌"


def parse_conformal_rows(stations: dict[str, Any]) -> list[ConformalRow]:
    """Pull per-station ``conformal_summary`` blocks out of a manifest's
    ``stations`` dict and convert to ``ConformalRow``.

    Stations whose manifest entry has no ``conformal_summary`` (or an
    empty dict) are silently skipped -- they're either backtest runs
    that ran before PR #32 landed or stations with too few evaluations
    to fit a conformal calibrator.
    """
    out: list[ConformalRow] = []
    for icao, station in stations.items():
        cs = station.get("conformal_summary") or {}
        if not cs:
            continue
        out.append(
            ConformalRow(
                station=icao,
                n_test=int(cs.get("n_test", 0)),
                target_coverage=float(cs.get("target_coverage", 0.0)),
                empirical_coverage=float(cs.get("empirical_coverage", 0.0)),
                threshold=float(cs.get("threshold", 0.0)),
                pct_singleton=float(cs.get("pct_singleton", 0.0)),
                pct_full=float(cs.get("pct_full", 0.0)),
                pct_empty=float(cs.get("pct_empty", 0.0)),
            )
        )
    return sorted(out, key=lambda r: r.station)


def format_conformal_table(rows: list[ConformalRow]) -> str:
    """Render a per-station conformal-coverage table as markdown."""
    if not rows:
        return "*No conformal coverage data available.*"
    header = (
        "| Station | n_test | Target | Empirical | Status | Threshold "
        "| %singleton | %full | %empty |"
    )
    lines: list[str] = [
        header,
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r.station} | {r.n_test:,} | {r.target_coverage:.2f} | "
            f"{r.empirical_coverage:.3f} | {r.coverage_status} | "
            f"{r.threshold:.3f} | {r.pct_singleton:.2%} | "
            f"{r.pct_full:.2%} | {r.pct_empty:.2%} |"
        )
    return "\n".join(lines)


def conformal_caveats() -> str:
    """The standard caveats every conformal panel should include.

    Lifted from PR #32's PR description so reviewers and dashboard
    users see the same framing about why under-coverage isn't
    necessarily a model bug.
    """
    return (
        "**Plain English:** the model claims its 90%-confidence answer set "
        "contains the truth 90% of the time; 'Empirical' is how often it "
        "actually did. At or above the 0.90 target = honest (✅); within "
        "5 points (0.85-0.90) = keep an eye on it (⚠️); below 0.85 = the "
        "model is overconfident (❌).\n\n"
        "**Reading this table:** empirical coverage at alpha=0.1 should "
        "track the 90% target. Under-coverage at the chronological "
        "split is a non-exchangeability signal -- calibration vs test "
        "window distribution drift -- not necessarily a model bug. "
        "The threshold column is the conformal score cut-off q; "
        "predictions inside `[1 - q, q]` produce the full {0, 1} "
        "prediction set and are not traded."
    )


# --------------------- NBA CLV manifest panels ---------------------


@dataclass(frozen=True, slots=True)
class NbaClvSummary:
    """Top-level CLV manifest fields for the dashboard.

    ``mean_clv`` is the price-based Phase 5 #5 metric: (devigged
    pre-tipoff closing prob of the bought side) - (vig-inclusive entry
    price paid). The outcome-conditioned ``mean_signed_clv`` was retired
    by the 2026-06-11 audit (root cause #10); manifests carrying only
    the old key parse as ``mean_clv=None`` -> bar fails.
    """

    n_evaluated: int
    n_picked: int
    n_skipped_no_odds: int
    n_skipped_no_crosswalk: int
    n_skipped_no_pinnacle: int
    n_excluded_no_pretipoff_close: int
    brier_model: float | None
    brier_pinnacle: float | None
    mean_clv: float | None
    mean_edge_vs_close: float | None
    win_rate_when_picked: float | None
    generated_at: str

    @property
    def passes_phase_5_5_bar(self) -> bool:
        """Phase 5 readiness #5: price-based ``mean_clv >= +0.01`` (1pp).

        Returns False when the metric isn't computed (n_evaluated == 0
        or an old-schema manifest without ``mean_clv``).
        """
        if self.mean_clv is None:
            return False
        return self.mean_clv >= 0.01


def read_nba_clv_manifest(path: Path) -> NbaClvSummary | None:
    """Load the NBA CLV manifest. Returns None on missing / unreadable
    file -- dashboard panel surfaces "no data" rather than crashing."""
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return NbaClvSummary(
        n_evaluated=int(payload.get("n_evaluated", 0)),
        n_picked=int(payload.get("n_picked", 0)),
        n_skipped_no_odds=int(payload.get("n_skipped_no_odds", 0)),
        n_skipped_no_crosswalk=int(payload.get("n_skipped_no_crosswalk", 0)),
        n_skipped_no_pinnacle=int(payload.get("n_skipped_no_pinnacle", 0)),
        n_excluded_no_pretipoff_close=int(payload.get("n_excluded_no_pretipoff_close", 0)),
        brier_model=_as_float_or_none(payload.get("brier_model")),
        brier_pinnacle=_as_float_or_none(payload.get("brier_pinnacle")),
        mean_clv=_as_float_or_none(payload.get("mean_clv")),
        mean_edge_vs_close=_as_float_or_none(payload.get("mean_edge_vs_close")),
        win_rate_when_picked=_as_float_or_none(payload.get("win_rate_when_picked")),
        generated_at=str(payload.get("generated_at", "")),
    )


def _as_float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def format_nba_clv_summary(summary: NbaClvSummary | None) -> str:
    """Top-line markdown card for the NBA CLV tab."""
    if summary is None:
        return (
            "*No NBA CLV manifest found — the NBA scorecard hasn't been "
            "generated on this machine yet. Run "
            "`uv run python -m kq backtest-nba-clv` once the NBA tables "
            "(nba_game + nba_odds + nba_game_crosswalk) have data. "
            "See docs/GETTING-STARTED.md for the plain-English tour.*"
        )
    if summary.n_evaluated == 0:
        return (
            "**NBA CLV** — manifest exists but no games evaluated yet "
            "(nothing to grade so far; usually just the calendar — "
            "see below).\n\n"
            f"- Generated: `{summary.generated_at}`\n"
            f"- Skipped (no crosswalk): {summary.n_skipped_no_crosswalk}\n"
            f"- Skipped (no odds): {summary.n_skipped_no_odds}\n"
            f"- Skipped (no Pinnacle): {summary.n_skipped_no_pinnacle}\n\n"
            "Most likely cause: off-season (no games), pre-`ODDS_API_KEY` "
            "signoff (no Pinnacle quotes flowing), or the matcher hasn't "
            "run since the latest schedule + odds ingest. Run "
            "`uv run python -m kq build-nba-crosswalk` first."
        )
    pass_glyph = "✅" if summary.passes_phase_5_5_bar else "❌"
    mclv = f"{summary.mean_clv:+.4f}" if summary.mean_clv is not None else "n/a"
    medge = (
        f"{summary.mean_edge_vs_close:+.4f}" if summary.mean_edge_vs_close is not None else "n/a"
    )
    brier_model_s = f"{summary.brier_model:.4f}" if summary.brier_model is not None else "n/a"
    brier_pinnacle_s = (
        f"{summary.brier_pinnacle:.4f}" if summary.brier_pinnacle is not None else "n/a"
    )
    win_rate_s = (
        f"{summary.win_rate_when_picked:.2%}" if summary.win_rate_when_picked is not None else "n/a"
    )
    return (
        f"**NBA CLV** — {summary.n_evaluated} games evaluated "
        f"({summary.n_picked} sides picked)\n\n"
        "CLV = closing-line value: did we get a better price than the "
        "market's final (closing) price? Above zero = yes; the go-live gate "
        "is +0.01 (one cent per contract dollar).\n\n"
        f"- Generated: `{summary.generated_at}`\n"
        f"- Phase 5 #5 bar (mean_clv ≥ +0.01): {pass_glyph} current = `{mclv}` "
        f"(CLV = devigged pre-tipoff close minus entry price paid)\n"
        f"- Brier: model={brier_model_s} vs pinnacle={brier_pinnacle_s} "
        "(prediction grade — golf rules: 0 = perfect, 0.25 = coin flip; "
        "lower is better)\n"
        f"- mean_edge_vs_close: {medge} (how much we *disagree* with the "
        "closing price — a diagnostic, not skill)\n"
        f"- win_rate_when_picked: {win_rate_s} (descriptive only; "
        f"favorite-leaning models beat 0.5 without skill)\n"
        f"- Skipped: {summary.n_skipped_no_crosswalk} no-crosswalk, "
        f"{summary.n_skipped_no_odds} no-odds, "
        f"{summary.n_skipped_no_pinnacle} no-pinnacle; "
        f"excluded: {summary.n_excluded_no_pretipoff_close} with no pre-tipoff close"
    )


def format_nba_clv_skip_breakdown(summary: NbaClvSummary | None) -> str:
    """Honest skip-path breakdown so n_evaluated denominators stay
    readable. Mirrors the table in the manifest's honest_caveats."""
    if summary is None:
        return ""
    total_skipped = (
        summary.n_skipped_no_crosswalk
        + summary.n_skipped_no_odds
        + summary.n_skipped_no_pinnacle
        + summary.n_excluded_no_pretipoff_close
    )
    return (
        "| Skip path | Count | What it means |\n"
        "|---|---|---|\n"
        f"| no_crosswalk | {summary.n_skipped_no_crosswalk} | "
        "NBA game id has no Odds API match (matcher hasn't run, or off-board) |\n"
        f"| no_odds | {summary.n_skipped_no_odds} | "
        "Crosswalk exists but no Pinnacle quote in nba_odds |\n"
        f"| no_pinnacle | {summary.n_skipped_no_pinnacle} | "
        "Unusable decimal odds or out-of-band booksum (stale quote) |\n"
        f"| no_pretipoff_close | {summary.n_excluded_no_pretipoff_close} | "
        "Only in-play Pinnacle rows exist (fetched after tipoff) — excluded "
        "so outcome-embedding quotes never anchor CLV |\n"
        f"| **total skipped** | **{total_skipped}** | of "
        f"{summary.n_evaluated + total_skipped} candidate games |"
    )


__all__ = [
    "ConformalRow",
    "NbaClvSummary",
    "conformal_caveats",
    "format_conformal_table",
    "format_nba_clv_skip_breakdown",
    "format_nba_clv_summary",
    "parse_conformal_rows",
    "read_nba_clv_manifest",
]
