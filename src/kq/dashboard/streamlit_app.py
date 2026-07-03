"""Streamlit dashboard — Phase 4 deliverable.

Run with `make dashboard` or:
    uv run streamlit run src/kq/dashboard/streamlit_app.py

Seven tabs, each opening with a plain-English "what question does this page
answer?" caption so a non-expert can read it (jargon stays visible but
glossed — see docs/GETTING-STARTED.md for the glossary):

  1. **Router** — what `weather_router_v1` is dispatching per station, with
     per-strategy comparison + calibration pass/fail. Mirrors `kq router-summary`.
  2. **Backtest** — Brier metrics per station x strategy. Drill into a
     specific manifest to see the per-band + per-month diagnostics.
  3. **Reliability** — equal-width and quantile-binning reliability
     diagrams, side by side. Hosmer-Lemeshow chi-squared statistic.
  4. **Paper trades** — `paper_trade` rollup with Phase 2 exit progress
     (>= 50 settled, >= 14 distinct trade days) plus Phase 5 #1 progress
     (settled / 500). Mirrors `kq paper-summary`.
  5. **Nowcast edge** — the settlement-window study (`kq study-nowcast-edge`):
     in the final hours before settlement, does the METAR nowcast beat the
     market's price? Read-only view of the nowcast edge manifest.
  6. **NBA CLV** — closing-line value vs Pinnacle (Phase 5 #5 gate:
     mean_clv >= +0.01). Read-only view of the NBA CLV manifest.
  7. **Data health** — data freshness across weather/metar/NDFD/Kalshi +
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
import pandas as pd
import streamlit as st

from kq import __version__
from kq.config import REPO_ROOT, get_settings
from kq.dashboard.panels import (
    conformal_caveats,
    format_conformal_table,
    format_nba_clv_skip_breakdown,
    format_nba_clv_summary,
    format_nowcast_edge_summary,
    format_nowcast_edge_table,
    nowcast_edge_caveats,
    parse_conformal_rows,
    read_nba_clv_manifest,
    read_nowcast_edge_manifest,
)
from kq.flows.health_check import run_checks
from kq.flows.ingest_weather import _db_path_from_settings
from kq.flows.paper_summary import summarize as summarize_paper
from kq.flows.router_summary import summarize as summarize_router
from kq.storage.duckdb_store import connect

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

with st.expander("What am I looking at? (start here)"):
    st.markdown(
        "**The 10-second read:** this is the report card for a weather + NBA "
        "prediction model that trades with **pretend money only**. Green / OK / "
        "PASS = healthy. **Paper trades** is the scoreboard; **Data health** "
        "tells you whether the data downloads are still running.\n\n"
        "| Tab | The question it answers |\n"
        "|---|---|\n"
        "| Router | Which forecast recipe is in charge for each city? |\n"
        "| Backtest | How well would the model have predicted the past? |\n"
        "| Reliability | When the model says 70%, does it happen 70% of the time? |\n"
        "| Paper trades | Is the practice account making or losing (pretend) money? |\n"
        "| Nowcast edge | Near settlement, does our live temperature tracking beat the price? |\n"
        "| NBA CLV | Did we get better prices than the market's final price? |\n"
        "| Data health | Are the data downloads running on schedule? |\n\n"
        "Unfamiliar words (Brier, calibration, CLV, ...) are explained in the "
        "plain-English glossary in `docs/GETTING-STARTED.md`."
    )

manifests = _load_manifests()
db_path = _db_connection_path()

# ----------------------------------------------------------- tabs

(
    tab_router,
    tab_backtest,
    tab_reliability,
    tab_paper,
    tab_nowcast_edge,
    tab_nba_clv,
    tab_health,
) = st.tabs(
    [
        "Router",
        "Backtest",
        "Reliability",
        "Paper trades",
        "Nowcast edge",
        "NBA CLV",
        "Data health",
    ]
)


# ----------------------------------------------------------- Router tab


with tab_router:
    st.header("Router - which forecast recipe is in charge for each city")
    st.caption(
        "The router picks the best-tested strategy per airport city and shows "
        "whether each would be good enough for real money: it must beat the "
        "government forecast (NDFD) and stay honest about its confidence "
        "(calibrated). Mirrors `kq router-summary` for `weather_router_v1`."
    )

    router_summary = summarize_router(REPO_ROOT / "models")

    col1, col2, col3 = st.columns(3)
    col1.metric(
        "Stations",
        router_summary.n_stations,
        help="One row per airport city we forecast (e.g. LAX, JFK, MDW, MIA, DEN, AUS).",
    )
    col2.metric(
        "Brier-vs-NDFD bar (>= 2%)",
        f"{router_summary.n_passes_brier_bar} / {router_summary.n_stations}",
        help=(
            "How many cities beat NDFD (the government forecast) by at least 2% "
            "on Brier score - the prediction grade where lower is better. "
            "CLAUDE.md sect 5 Phase 5 readiness criterion #2 - needs >= 4/6 to pass."
        ),
    )
    col3.metric(
        "Calibration bar (n-aware)",
        f"{router_summary.n_passes_calibration} / {router_summary.n_stations}",
        help=(
            "How many cities are honest about their confidence: no well-sampled "
            "probability bucket (n >= 100) off by more than 10 percentage points. "
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
        st.caption(
            "`active` = the strategy the router chose for that city. "
            "`brier_vs_ndfd_*` = how much better than the government forecast, "
            "in percent (positive = better; >= 2% clears the bar). "
            "`calib_*` = PASS when the strategy is honest about its confidence."
        )
    else:
        st.warning(
            "No stations yet - the model hasn't been trained on this machine. "
            "Run `uv run kq train-weather` and then `uv run kq decide-router` "
            "(both need backfilled history - see docs/GETTING-STARTED.md)."
        )


# ----------------------------------------------------------- Backtest tab


with tab_backtest:
    st.header("Backtest - the model's report card on past data")
    st.caption(
        "Each strategy is replayed against history it never saw and graded per "
        "city. The grade is the Brier score (golf rules: 0 = perfect, 0.25 = "
        "coin flip; lower is better)."
    )

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
            "`brier_cal_*` = Brier score, the prediction grade (0 = perfect, "
            "0.25 = coin flip; lower is better; the Phase 2 exit bar is <= 0.18). "
            "`brier_vs_ndfd_*` = improvement vs NDFD, the government forecast, in "
            "percentage points (positive = we beat it; >= 2% clears the Phase 5 bar). "
            "`calib_*` = True when calibration passes: no well-sampled probability "
            "bucket (n >= 100) off by more than 10 pp."
        )
    else:
        st.warning(
            "No backtest scorecards yet - nothing has been graded on this machine. "
            "Run `uv run kq backtest --strategy weather_v1` after training "
            "(see docs/GETTING-STARTED.md)."
        )


# ----------------------------------------------------------- Reliability tab


with tab_reliability:
    st.header("Reliability - is the model honest about its confidence?")
    st.caption(
        "When the model says 70%, does it happen about 70% of the time? Each dot "
        "is a bucket of predictions: on the dashed diagonal = honest confidence, "
        "below it = overconfident, above it = underconfident. Shown for the "
        "active (`weather_router_v1`) strategy, equal-width bins."
    )

    router_manifest = manifests.get("router_v1") or {}
    stations_data = router_manifest.get("stations") or {}

    if not stations_data:
        st.warning(
            "No reliability data yet - the active-strategy backtest hasn't run "
            "on this machine. Run `uv run kq backtest --strategy weather_router_v1` "
            "after training (see docs/GETTING-STARTED.md)."
        )
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
                help=(
                    "PASS = no well-sampled probability bucket (n >= 100) is off "
                    "by more than 10 percentage points - the CLAUDE.md sect 5 #3 "
                    "calibration bar."
                ),
            )
            col2.metric(
                "Max |delta| (qualifying)",
                f"{rs.get('max_delta_pp', 'n/a')} pp",
                help=(
                    "Biggest gap between promised probability and actual frequency "
                    "across well-sampled buckets. Under 10 pp = pass."
                ),
            )
            col3.metric(
                "Failing bins",
                f"{rs.get('n_bins_failing', 0)} / {rs.get('n_bins_qualifying', 0)}",
                help=(
                    "Buckets off by more than 10 pp, out of the buckets with "
                    "enough data (n >= 100) to judge fairly. Want 0."
                ),
            )
            qbins = rs.get("quantile_bins") or {}
            if qbins:
                col4.metric(
                    "HL chi-squared (dof=8)",
                    f"{qbins.get('hl_chi_squared', 'n/a')}",
                    help=(
                        "Hosmer-Lemeshow goodness-of-fit - one combined 'is anything "
                        "off?' number for the whole diagram. Smaller = better; "
                        "larger = worse calibration."
                    ),
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
    st.caption(
        "A second honesty check: the model claims its 90%-confidence answer set "
        "contains the truth 90% of the time; 'empirical' is how often it actually "
        "did. At or above the 0.90 target = good; below 0.85 (more than 5 points "
        "short) = the model is overconfident."
    )
    conformal_rows = parse_conformal_rows(stations_data)
    if conformal_rows:
        st.markdown(format_conformal_table(conformal_rows))
        st.caption(conformal_caveats())
    else:
        st.info(
            "No conformal-coverage data yet: there are no `conformal_summary` "
            "blocks in the router_v1 manifest. Re-run "
            "`uv run kq backtest --strategy weather_router_v1` and this table "
            "will fill in."
        )


# ----------------------------------------------------------- Paper tab


with tab_paper:
    st.header("Paper trading - the scoreboard (pretend money)")
    st.caption(
        "Practice trades with pretend money, recorded and scored exactly as if "
        "they were real. This is where you check whether the system is winning. "
        "Real-money trading stays locked until these numbers clear the "
        "CLAUDE.md sect 5 gate."
    )

    paper: Any = None
    paper_err: str | None = None
    # Context-managed read-only connection: an exception mid-summarize must
    # not leak an open handle (the leaked handle held the DuckDB file lock
    # and starved the cron writers — 2026-07-01 audit), and read_only never
    # creates an empty DB on a bad path.
    try:
        with connect(db_path, read_only=True) as con:
            paper = summarize_paper(con)
    except Exception as exc:
        paper_err = str(exc)

    if paper_err is not None:
        st.error(
            f"Couldn't read the paper-trade table: {paper_err}\n\n"
            "This usually means the database hasn't been set up on this machine "
            "yet. Run `uv run kq setup` (the first-run wizard) - see "
            "docs/GETTING-STARTED.md."
        )
    elif paper is not None:
        col1, col2, col3 = st.columns(3)
        col1.metric(
            "Settled trades",
            paper.n_settled,
            delta=(
                f"Phase 2 exit >= 50: {'PASS' if paper.phase2_passes_settled_count else 'not yet'}"
            ),
            help=(
                "Practice trades whose outcome is official (the market resolved "
                "and the trade was scored). Phase 2 exit needs at least 50."
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
            help=(
                "Share of settled practice trades that made money. Context, not a "
                "gate - getting a good price matters more than raw win count."
            ),
        )

        col4, col5, col6 = st.columns(3)
        col4.metric(
            "Total P&L",
            f"${paper.total_pnl_usd:+.2f}",
            help=(
                "Pretend-money profit and loss across all settled practice "
                "trades, after simulated fees. Above $0 = winning so far."
            ),
        )
        col5.metric(
            "Bankroll",
            f"${paper.current_bankroll_usd:.2f}",
            help="Current pretend-money balance after all wins and losses.",
        )
        col6.metric(
            "ROI",
            f"{paper.roi_pct:+.2f}%",
            help=(
                "Return on investment: profit as a percentage of the starting "
                "bankroll. Positive = winning."
            ),
        )

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
                "No practice trades yet - the scoreboard starts empty. Trades "
                "appear after the data downloads (`uv run kq ingest`) and the "
                "paper trader (`uv run kq paper`) are running on a schedule and "
                "markets are open. See `docs/SCHEDULED-RUNS.md` for the cron "
                "runbook and `docs/GETTING-STARTED.md` for the plain-English tour."
            )


# ----------------------------------------------------------- Nowcast edge tab


with tab_nowcast_edge:
    st.header("Nowcast edge - do we beat the market in the final hours?")
    st.caption(
        "In the last hours before settlement, does our up-to-the-minute "
        "temperature tracking beat the market's price? By early afternoon the "
        "day's high is often nearly locked in while market prices lag - this "
        "is the project's #1 hypothesized edge, and this page is its "
        "scorecard. Mirrors `kq study-nowcast-edge` (read-only view of "
        "`models/nowcast_edge_manifest.json`)."
    )

    nowcast_edge = read_nowcast_edge_manifest(REPO_ROOT / "models" / "nowcast_edge_manifest.json")
    st.markdown(format_nowcast_edge_summary(nowcast_edge))

    if nowcast_edge is not None and nowcast_edge.n_records > 0:
        ne_overall = nowcast_edge.overall
        if ne_overall is not None:
            col1, col2, col3 = st.columns(3)
            col1.metric(
                "Market-hours graded",
                ne_overall.n,
                help=(
                    "One grade per settled market per hour bucket (the last "
                    "usable price snapshot in each hour). More is better - "
                    "small samples are mostly noise."
                ),
            )
            col2.metric(
                "Brier: model vs market",
                (f"{ne_overall.brier_model:.4f}" if ne_overall.brier_model is not None else "n/a"),
                delta=(
                    f"market {ne_overall.brier_market:.4f}"
                    if ne_overall.brier_market is not None
                    else "market n/a"
                ),
                delta_color="off",
                help=(
                    "The prediction grade (golf rules: 0 = perfect, 0.25 = coin "
                    "flip; lower is better). Model below market = our final-hours "
                    "tracking beats the price."
                ),
            )
            col3.metric(
                "After-fee capture ($/contract)",
                (
                    f"{ne_overall.mean_after_fee_capture_usd:+.4f}"
                    if ne_overall.mean_after_fee_capture_usd is not None
                    else "n/a"
                ),
                delta=f"{ne_overall.n_actionable} trades cleared the 4pp gate",
                delta_color="off",
                help=(
                    "The money view: average realized result per contract of "
                    "hypothetical trades whose edge cleared the 4-percentage-point "
                    "after-fee gate (taker fees). Positive = a real edge after fees."
                ),
            )
        st.subheader("By hours to settlement")
        st.caption(
            "Hour 0 = the final hour before the market's day officially ends. "
            "The hypothesis says the edge should grow as settlement approaches "
            "(low hour numbers)."
        )
        st.markdown(format_nowcast_edge_table(nowcast_edge))
        st.caption(nowcast_edge_caveats())


# ----------------------------------------------------------- NBA CLV tab


with tab_nba_clv:
    st.header("NBA closing-line value (CLV) vs Pinnacle")
    st.caption(
        "Did we get better prices than the market's final (closing) price? "
        "Above zero = yes - early evidence of skill, even before wins and "
        "losses pile up. A mean CLV of +0.01 (one cent per contract dollar) "
        "or higher passes the go-live gate."
    )
    st.caption(
        "Fine print: Phase 5 readiness criterion #5 (CLAUDE.md sect 5): "
        "price-based CLV vs Pinnacle >= +1pp. CLV = (devigged PRE-TIPOFF "
        "Pinnacle close of the side we bought) - (vig-inclusive entry price "
        "paid). Read-only view of `models/backtest_nba_clv_manifest.json`."
    )

    nba_clv = read_nba_clv_manifest(REPO_ROOT / "models" / "backtest_nba_clv_manifest.json")
    st.markdown(format_nba_clv_summary(nba_clv))

    if nba_clv is not None:
        col1, col2, col3 = st.columns(3)
        col1.metric(
            "Games evaluated",
            nba_clv.n_evaluated,
            help=(
                "Games with both a model prediction and a usable pre-tipoff "
                "Pinnacle price. Skipped games are itemized below."
            ),
        )
        col2.metric(
            "Mean CLV (price-based)",
            f"{nba_clv.mean_clv:+.4f}" if nba_clv.mean_clv is not None else "n/a",
            delta=f"gate >= +0.01: {'PASS' if nba_clv.passes_phase_5_5_bar else 'FAIL'}",
            help=(
                "Average price edge vs the closing line. +0.01 or higher passes "
                "the go-live gate; below zero means the market's final price was "
                "better than the one we got."
            ),
        )
        col3.metric(
            "Win rate when picked",
            (
                f"{nba_clv.win_rate_when_picked:.1%}"
                if nba_clv.win_rate_when_picked is not None
                else "n/a"
            ),
            help=(
                "Share of picked sides that won. Descriptive only — a model that "
                "leans toward favorites beats 0.5 without any skill."
            ),
        )

        skip_md = format_nba_clv_skip_breakdown(nba_clv)
        if skip_md:
            st.subheader("Skip-path breakdown")
            st.caption(
                "Why some games didn't make it into the count above - each row "
                "says what was missing."
            )
            st.markdown(skip_md)


# ----------------------------------------------------------- Data health tab


with tab_health:
    st.header("Data health - are the downloads running on schedule?")
    st.caption(
        "Every data feed should land on a schedule (weather every 6h, METAR "
        "every 10min, ...). OK = fresh. WARN = at least one missed run. "
        "CRIT = a feed has stopped - run `uv run kq doctor` for a "
        "plain-language diagnosis. Mirrors `kq health-check`."
    )

    # Same connection discipline as the Paper tab: read-only + context-managed
    # so an exception can't leak the file lock that blocks the cron writers.
    try:
        with connect(db_path, read_only=True) as con:
            status: Any = run_checks(con, models_dir=REPO_ROOT / "models")
        health_err: str | None = None
    except Exception as exc:
        status = None
        health_err = str(exc)

    if health_err is not None:
        st.error(
            f"Couldn't connect to DuckDB at {db_path}: {health_err}\n\n"
            "If this is a fresh machine, the database probably hasn't been "
            "created yet - run `uv run kq setup` (see docs/GETTING-STARTED.md)."
        )
    elif status is not None:
        sev_label = {"ok": "OK ", "warn": "WARN", "crit": "CRIT"}
        overall_gloss = {
            "ok": "Everything is fresh - the pipeline is running on schedule.",
            "warn": (
                "At least one feed missed a scheduled run. Not an emergency, "
                "but worth a look - `uv run kq doctor` explains what's stale."
            ),
            "crit": (
                "At least one feed has stopped updating (or never ran). "
                "Run `uv run kq doctor` for the plain-language fix-it list."
            ),
        }
        st.markdown(f"## Overall status: {sev_label[status.overall]}")
        st.caption(overall_gloss[status.overall])
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
        st.caption(
            "`age` = time since the newest data landed. `threshold` = how old it "
            "may get before we call it stale (set to 2x the normal schedule, so "
            "one late run doesn't cause a false alarm; ~3x past that escalates "
            "WARN to CRIT)."
        )

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
                    st.info(
                        "No scheduled ingest runs in the last 24h - the cron "
                        "loop may be stopped. See `docs/SCHEDULED-RUNS.md` to "
                        "restart it."
                    )
