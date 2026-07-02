"""Streamlit dashboard — Phase 4 deliverable.

Run with `make dashboard` or:
    uv run streamlit run src/kq/dashboard/streamlit_app.py

Five tabs:
  1. **Router** — what `weather_router_v1` is dispatching per station, with
     per-strategy comparison + calibration pass/fail. Mirrors `kq router-summary`.
  2. **Backtest** — Brier metrics per station x strategy. Drill into a
     specific manifest to see the per-band + per-month diagnostics.
  3. **Reliability** — equal-width and quantile-binning reliability
     diagrams, side by side. Hosmer-Lemeshow chi-squared statistic.
  4. **Paper trading** — `paper_trade` rollup with Phase 2 exit progress
     (>= 50 settled, >= 14 distinct trade days) plus Phase 5 #1 progress
     (settled / 500). Mirrors `kq paper-summary`.
  5. **Data health** — data freshness across weather/metar/NDFD/Kalshi +
     manifest mtimes. Mirrors `kq health-check`.

The dashboard is **read-only** — it loads JSON manifests from `models/`
and aggregates the DuckDB file. It does not place orders, mutate
manifests, or call external APIs.

Phase 4 exit criterion (per CLAUDE.md §5): dashboard reachable from
phone; alerts fire on synthetic failure tests. We're meeting #1 here;
#2 is the cron + ntfy/Pushover wiring documented in
``docs/SCHEDULED-RUNS.md``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import altair as alt
import duckdb
import pandas as pd
import streamlit as st

from kq import __version__
from kq.config import REPO_ROOT, get_settings
from kq.dashboard.panels import (
    conformal_caveats,
    format_conformal_table,
    format_nba_clv_skip_breakdown,
    format_nba_clv_summary,
    parse_conformal_rows,
    read_nba_clv_manifest,
)
from kq.flows.health_check import run_checks
from kq.flows.ingest_weather import _db_path_from_settings
from kq.flows.paper_summary import summarize as summarize_paper
from kq.flows.router_summary import summarize as summarize_router

st.set_page_config(page_title="forecast-lab", layout="wide")

# ----------------------------------------------------------- helpers


@st.cache_data(ttl=60)
def _load_manifests() -> dict[str, Any]:
    """Read the four backtest manifests + router config + training manifest.
    Cached for 60s so a single dashboard refresh doesn't pound the FS."""
    models = REPO_ROOT / "models"
    out: dict[str, Any] = {}
    for short, fname in (
        ("v1", "backtest_manifest.json"),
        ("router_v1", "backtest_router_manifest.json"),
        ("all_raw_v1", "backtest_all_raw_manifest.json"),
        ("reforecast_v1", "backtest_reforecast_manifest.json"),
        ("training", "manifest.json"),
        ("router_config", "router_config.json"),
    ):
        path = models / fname
        if path.exists():
            try:
                out[short] = json.loads(path.read_text())
            except json.JSONDecodeError:
                out[short] = None
        else:
            out[short] = None
    return out


@st.cache_data(ttl=60)
def _db_connection_path() -> Path:
    """Get the configured DuckDB path. Cached so we don't re-parse settings."""
    return _db_path_from_settings(get_settings().database_url)


def _format_pct(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:+6.2f}%"


def _format_pass(v: bool | None) -> str:
    if v is None:
        return "—"
    return "PASS" if v else "FAIL"


# ----------------------------------------------------------- header

st.title("forecast-lab")
st.caption(
    f"v{__version__} - paper trading only - "
    "live trading is gated behind CLAUDE.md sect 5 + sect 9. "
    f"Loaded {datetime.now(tz=UTC).isoformat(timespec='seconds')}"
)

manifests = _load_manifests()
db_path = _db_connection_path()

# ----------------------------------------------------------- tabs

(
    tab_router,
    tab_backtest,
    tab_reliability,
    tab_paper,
    tab_nba_clv,
    tab_health,
) = st.tabs(
    [
        "Router",
        "Backtest",
        "Reliability",
        "Paper trades",
        "NBA CLV",
        "Data health",
    ]
)


# ----------------------------------------------------------- Router tab


with tab_router:
    st.header("Live trading config - what `weather_router_v1` would dispatch today")

    router_summary = summarize_router(REPO_ROOT / "models")

    col1, col2, col3 = st.columns(3)
    col1.metric("Stations", router_summary.n_stations)
    col2.metric(
        "Brier-vs-NDFD bar (>= 2%)",
        f"{router_summary.n_passes_brier_bar} / {router_summary.n_stations}",
        help="CLAUDE.md sect 5 Phase 5 readiness criterion #2 - needs >= 4/6 to pass.",
    )
    col3.metric(
        "Calibration bar (n-aware)",
        f"{router_summary.n_passes_calibration} / {router_summary.n_stations}",
        help=(
            "CLAUDE.md sect 5 Phase 5 readiness criterion #3 - n-aware reliability "
            "(min_n=100, tolerance=10pp). Mechanism in PR #25."
        ),
    )

    if router_summary.router_config_generated_at:
        st.caption(
            f"Router config generated: {router_summary.router_config_generated_at} "
            f"(mode={router_summary.router_mode})"
        )

    # Per-station table
    router_rows: list[dict[str, Any]] = []
    for v in router_summary.stations:
        rrow: dict[str, Any] = {"station": v.station, "active": v.active_strategy.upper()}
        for short in ("v1", "router_v1", "all_raw_v1", "reforecast_v1"):
            rrow[f"brier_vs_ndfd_{short}"] = _format_pct(v.brier_vs_ndfd_pct_by_strategy.get(short))
            rrow[f"calib_{short}"] = _format_pass(v.calibration_passes_by_strategy.get(short))
        rrow["reason"] = v.decision_reason[:120] + ("..." if len(v.decision_reason) > 120 else "")
        router_rows.append(rrow)

    if router_rows:
        df = pd.DataFrame(router_rows)
        st.dataframe(df, hide_index=True, use_container_width=True)
    else:
        st.warning("No stations in router_config or any manifest.")


# ----------------------------------------------------------- Backtest tab


with tab_backtest:
    st.header("Backtest verdicts per station x strategy")

    bt_rows: list[dict[str, Any]] = []
    stations: set[str] = set()
    for short in ("v1", "router_v1", "all_raw_v1", "reforecast_v1"):
        m = manifests.get(short) or {}
        stations.update((m.get("stations") or {}).keys())

    for st_id in sorted(stations):
        bt_row: dict[str, Any] = {"station": st_id}
        for short in ("v1", "router_v1", "all_raw_v1", "reforecast_v1"):
            m = manifests.get(short) or {}
            entry = (m.get("stations") or {}).get(st_id) or {}
            bt_row[f"brier_cal_{short}"] = (
                round(entry["brier_calibrated"], 4) if "brier_calibrated" in entry else None
            )
            bt_row[f"brier_vs_ndfd_{short}"] = entry.get("brier_improvement_vs_ndfd_pct")
            rs = entry.get("reliability_summary") or {}
            bt_row[f"calib_{short}"] = rs.get("passes_bar")
        bt_rows.append(bt_row)

    if bt_rows:
        df = pd.DataFrame(bt_rows)
        st.dataframe(df, hide_index=True, use_container_width=True)
        st.caption(
            "`brier_cal_*` = absolute Brier score (lower = better). "
            "`brier_vs_ndfd_*` = pp improvement vs NDFD (positive = better). "
            "`calib_*` = passes_bar from the n-aware reliability summary."
        )
    else:
        st.warning("No backtest manifests found in `models/`. Run `kq backtest` first.")


# ----------------------------------------------------------- Reliability tab


with tab_reliability:
    st.header("Reliability diagrams")
    st.caption(
        "Equal-width per-station reliability on the active (`weather_router_v1`) "
        "strategy. Diagonal = perfect calibration."
    )

    router_manifest = manifests.get("router_v1") or {}
    stations_data = router_manifest.get("stations") or {}

    if not stations_data:
        st.warning("No router_v1 manifest found.")
    else:
        station_choice = st.selectbox("Station", sorted(stations_data.keys()))
        station_entry = stations_data[station_choice]

        bins = station_entry.get("reliability") or []
        if bins:
            df_bins = pd.DataFrame(bins)
            df_bins = df_bins[df_bins["n"] > 0]
            if df_bins.empty:
                st.info("No populated bins.")
            else:
                base = (
                    alt.Chart(df_bins)
                    .mark_circle(size=60)
                    .encode(
                        x=alt.X(
                            "mean_predicted:Q",
                            title="Predicted prob",
                            scale=alt.Scale(domain=[0, 1]),
                        ),
                        y=alt.Y(
                            "mean_observed:Q", title="Observed freq", scale=alt.Scale(domain=[0, 1])
                        ),
                        size=alt.Size("n:Q", title="Bucket size"),
                        tooltip=["lower", "upper", "n", "mean_predicted", "mean_observed"],
                    )
                )
                diagonal = (
                    alt.Chart(pd.DataFrame({"x": [0, 1], "y": [0, 1]}))
                    .mark_line(strokeDash=[4, 4], color="gray")
                    .encode(x="x", y="y")
                )
                st.altair_chart(
                    (diagonal + base).properties(
                        width=600,
                        height=400,
                        title=f"{station_choice} (equal-width binning)",
                    ),
                    use_container_width=True,
                )

        rs = station_entry.get("reliability_summary") or {}
        if rs:
            col1, col2, col3, col4 = st.columns(4)
            col1.metric(
                "Passes bar (equal-width)",
                "PASS" if rs.get("passes_bar") else "FAIL",
            )
            col2.metric(
                "Max |delta| (qualifying)",
                f"{rs.get('max_delta_pp', 'n/a')} pp",
            )
            col3.metric(
                "Failing bins",
                f"{rs.get('n_bins_failing', 0)} / {rs.get('n_bins_qualifying', 0)}",
            )
            qbins = rs.get("quantile_bins") or {}
            if qbins:
                col4.metric(
                    "HL chi-squared (dof=8)",
                    f"{qbins.get('hl_chi_squared', 'n/a')}",
                    help="Hosmer-Lemeshow goodness-of-fit. Larger = worse calibration.",
                )

            if qbins:
                st.subheader("Quantile-binned (Hosmer-Lemeshow) summary")
                col_a, col_b, col_c = st.columns(3)
                col_a.metric(
                    "Passes bar (quantile)",
                    "PASS" if qbins.get("passes_bar") else "FAIL",
                )
                col_b.metric(
                    "Max |delta| (quantile)",
                    f"{qbins.get('max_delta_pp', 'n/a')} pp",
                )
                col_c.metric(
                    "Failing bins (quantile)",
                    f"{qbins.get('n_bins_failing', 0)} / {qbins.get('n_bins_qualifying', 0)}",
                )

    st.divider()
    st.subheader("Conformal coverage (alpha=0.1)")
    conformal_rows = parse_conformal_rows(stations_data)
    if conformal_rows:
        st.markdown(format_conformal_table(conformal_rows))
        st.caption(conformal_caveats())
    else:
        st.info(
            "No `conformal_summary` blocks in the router_v1 manifest yet. "
            "Re-run `kq backtest --strategy weather_router_v1` once the "
            "conformal field lands."
        )


# ----------------------------------------------------------- Paper tab


with tab_paper:
    st.header("Paper trading status")

    paper: Any = None
    paper_err: str | None = None
    try:
        con = duckdb.connect(str(db_path), read_only=True)
        paper = summarize_paper(con)
        con.close()
    except Exception as exc:
        paper_err = str(exc)

    if paper_err is not None:
        st.error(f"Couldn't read paper-trade table: {paper_err}")
    elif paper is not None:
        col1, col2, col3 = st.columns(3)
        col1.metric(
            "Settled trades",
            paper.n_settled,
            delta=(
                f"Phase 2 exit >= 50: {'PASS' if paper.phase2_passes_settled_count else 'not yet'}"
            ),
        )
        col2.metric(
            "Distinct trade days (UTC)",
            paper.n_distinct_trade_days,
            delta=(
                f"Phase 2 exit >= 14: {'PASS' if paper.phase2_passes_distinct_days else 'not yet'}"
            ),
            help="Distinct UTC dates with at least one fill — not a consecutive streak.",
        )
        col3.metric(
            "Phase 5 #1 progress",
            f"{paper.n_settled} / {paper.phase5_settled_target}",
            delta=f"{paper.phase5_settled_progress_pct:.1f}% of the 500-trade gate",
            help="Phase 5 gate #1 (CLAUDE.md sect 5): >= 500 settled paper trades.",
        )
        st.metric(
            "Win rate (settled)",
            f"{paper.win_rate * 100:.1f}%" if paper.n_settled > 0 else "n/a",
        )

        col4, col5, col6 = st.columns(3)
        col4.metric("Total P&L", f"${paper.total_pnl_usd:+.2f}")
        col5.metric("Bankroll", f"${paper.current_bankroll_usd:.2f}")
        col6.metric("ROI", f"{paper.roi_pct:+.2f}%")

        if paper.per_station:
            st.subheader("Per-station breakdown")
            df_ps = pd.DataFrame(
                [
                    {
                        "station": p.station,
                        "settled": p.n_settled,
                        "won": p.n_won,
                        "win_rate": f"{p.win_rate * 100:.1f}%" if p.n_settled > 0 else "n/a",
                        "pnl_usd": f"${p.total_pnl_usd:+.2f}",
                    }
                    for p in paper.per_station
                ]
            )
            st.dataframe(df_ps, hide_index=True, use_container_width=True)
        elif paper.n_filled == 0:
            st.info(
                "No paper trades yet. Get `kq paper` running on cron - see "
                "`docs/SCHEDULED-RUNS.md` for the Windows runbook."
            )


# ----------------------------------------------------------- NBA CLV tab


with tab_nba_clv:
    st.header("NBA closing-line value vs Pinnacle")
    st.caption(
        "Phase 5 readiness criterion #5 (CLAUDE.md sect 5): price-based CLV "
        "vs Pinnacle >= +1pp. CLV = (devigged PRE-TIPOFF Pinnacle close of "
        "the side we bought) - (vig-inclusive entry price paid). Read-only "
        "view of `models/backtest_nba_clv_manifest.json`."
    )

    nba_clv = read_nba_clv_manifest(REPO_ROOT / "models" / "backtest_nba_clv_manifest.json")
    st.markdown(format_nba_clv_summary(nba_clv))

    if nba_clv is not None:
        col1, col2, col3 = st.columns(3)
        col1.metric("Games evaluated", nba_clv.n_evaluated)
        col2.metric(
            "Mean CLV (price-based)",
            f"{nba_clv.mean_clv:+.4f}" if nba_clv.mean_clv is not None else "n/a",
            delta=f"gate >= +0.01: {'PASS' if nba_clv.passes_phase_5_5_bar else 'FAIL'}",
        )
        col3.metric(
            "Win rate when picked",
            (
                f"{nba_clv.win_rate_when_picked:.1%}"
                if nba_clv.win_rate_when_picked is not None
                else "n/a"
            ),
            help="Descriptive only — favorite-leaning models beat 0.5 without skill.",
        )

        skip_md = format_nba_clv_skip_breakdown(nba_clv)
        if skip_md:
            st.subheader("Skip-path breakdown")
            st.markdown(skip_md)


# ----------------------------------------------------------- Data health tab


with tab_health:
    st.header("Pipeline data freshness")

    try:
        con = duckdb.connect(str(db_path), read_only=True)
        status: Any = run_checks(con, models_dir=REPO_ROOT / "models")
        con.close()
        health_err: str | None = None
    except Exception as exc:
        status = None
        health_err = str(exc)

    if health_err is not None:
        st.error(f"Couldn't connect to DuckDB at {db_path}: {health_err}")
    elif status is not None:
        sev_label = {"ok": "OK ", "warn": "WARN", "crit": "CRIT"}
        st.markdown(f"## Overall status: {sev_label[status.overall]}")
        st.caption(f"Checked at {status.checked_at_utc}")

        df_health = pd.DataFrame(
            [
                {
                    "check": c.name,
                    "severity": sev_label[c.severity],
                    "detail": c.detail,
                    "age": (f"{c.age_seconds / 3600:.2f}h" if c.age_seconds is not None else "n/a"),
                    "threshold": (
                        f"{c.threshold_seconds / 3600:.0f}h"
                        if c.threshold_seconds is not None
                        else "n/a"
                    ),
                }
                for c in status.checks
            ]
        )
        st.dataframe(df_health, hide_index=True, use_container_width=True)

        # Hourly ingest count chart from cron logs (best-effort).
        # Path is configurable via Settings.cron_log_dir (default
        # `data/cron-logs/` under the repo root) so this works under
        # Windows + WSL2 as well as Linux/macOS without /tmp guarantees.
        cron_dir = get_settings().cron_log_dir
        if cron_dir.exists():
            ingest_logs = sorted(cron_dir.glob("ingest-*.log"))
            if ingest_logs:
                st.subheader("Background ingest cron (last 24h)")
                cutoff = datetime.now(tz=UTC) - timedelta(hours=24)
                recent = []
                for f in ingest_logs:
                    stem = f.stem.removeprefix("ingest-")
                    try:
                        ts = datetime.strptime(stem, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
                    except ValueError:
                        continue
                    if ts >= cutoff:
                        recent.append({"time": ts, "log": f.name})
                if recent:
                    st.dataframe(pd.DataFrame(recent), hide_index=True, use_container_width=True)
                else:
                    st.info("No cron-loop runs in the last 24h.")
