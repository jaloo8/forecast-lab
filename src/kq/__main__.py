"""CLI entrypoint: `python -m kq ...`."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer

from kq import __version__
from kq._logging import bind_trace_id, setup_logging
from kq.clients.gefs_reforecast import DEFAULT_MEMBERS as GEFSV12_DEFAULT_MEMBERS
from kq.config import get_settings
from kq.execution.live import assert_live_allowed
from kq.flows.backfill_nba_schedule import main as run_backfill_nba_schedule
from kq.flows.backfill_ndfd import main as run_backfill_ndfd
from kq.flows.backfill_observed import main as run_backfill_observed
from kq.flows.backfill_weather import main as run_backfill_weather
from kq.flows.build_nba_crosswalk import main as run_build_nba_crosswalk
from kq.flows.decide_router import main as run_decide_router
from kq.flows.doctor import main as run_doctor
from kq.flows.health_check import main as run_health_check
from kq.flows.ingest_all import main as run_ingest_all
from kq.flows.ingest_ecmwf_opendata import main as run_ingest_ecmwf_opendata
from kq.flows.ingest_kalshi import main as run_ingest_kalshi
from kq.flows.ingest_metar import main as run_ingest_metar
from kq.flows.ingest_nba_injuries import main as run_ingest_nba_injuries
from kq.flows.ingest_nba_odds import main as run_ingest_nba_odds
from kq.flows.ingest_nba_schedule import main as run_ingest_nba_schedule
from kq.flows.ingest_ndfd import main as run_ingest_ndfd
from kq.flows.ingest_observed import main as run_ingest_observed
from kq.flows.ingest_weather import main as run_ingest_weather
from kq.flows.paper_nba_trade import main as run_paper_nba_trade
from kq.flows.paper_summary import main as run_paper_summary
from kq.flows.paper_trade import main as run_paper_trade
from kq.flows.plan_gefsv12_pull import main as run_plan_gefsv12_pull
from kq.flows.pull_gefsv12_reforecasts import main as run_pull_gefsv12_reforecasts
from kq.flows.router_summary import main as run_router_summary
from kq.flows.run_backtest import main as run_backtest_flow
from kq.flows.run_nba_clv_backtest import main as run_nba_clv_backtest
from kq.flows.run_weather_clv_backtest import main as run_weather_clv_backtest
from kq.flows.setup_wizard import main as run_setup_wizard
from kq.flows.state_check import main as run_state_check
from kq.flows.study_nowcast_edge import DEFAULT_WINDOW_HOURS as NOWCAST_STUDY_WINDOW_HOURS
from kq.flows.study_nowcast_edge import main as run_study_nowcast_edge
from kq.flows.train_weather import main as run_train_weather

app = typer.Typer(
    name="kq",
    help="forecast-lab: forecasts daily high temperatures and NBA games, "
    "compares them with prediction-market prices, and practice-trades the "
    "differences with pretend money. New here? Start with: kq setup "
    "(then kq dashboard to see the app). Developer docs: CLAUDE.md.",
    no_args_is_help=True,
)


@app.callback()
def _root(
    log_level: Annotated[
        str | None,
        typer.Option(
            "--log-level",
            "-v",
            help="Log level (debug/info/warning/error). "
            "Defaults to LOG_LEVEL env var, then 'info'. "
            "Use `-v debug` to see HTTP requests, retries, etc.",
        ),
    ] = None,
    log_file: Annotated[
        Path | None,
        typer.Option(
            "--log-file",
            help="Write a copy of every log line here (rotates daily, keeps 14 days). "
            "Useful for cron — paired with stdout redirection it's redundant; "
            "the file handler is the single source of truth.",
        ),
    ] = None,
    log_json: Annotated[
        bool | None,
        typer.Option(
            "--log-json/--log-pretty",
            help="Force JSON (--log-json) or pretty console (--log-pretty) output. "
            "When neither flag is given, auto-detects: JSON in non-TTY "
            "(cron/CI/pipes), pretty in interactive shells.",
        ),
    ] = None,
) -> None:
    """Configure logging once before any subcommand runs.

    Honors precedence: CLI flag > LOG_LEVEL env var > 'info' default. Binds
    a fresh trace_id to the contextvar so every log line for this run can be
    correlated with `trace_id=<value>`.

    ``--log-json/--log-pretty`` is a real tri-state: unset auto-detects,
    ``--log-json`` forces JSON, ``--log-pretty`` forces pretty even in a
    non-TTY (the pre-audit bool collapsed --log-pretty into "auto").
    """
    settings = get_settings()
    effective_level = log_level or settings.log_level or "info"
    setup_logging(
        level=effective_level,
        log_file=log_file,
        json_output=log_json,
    )
    bind_trace_id()


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo(__version__)


@app.command()
def setup(
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            "-y",
            help="Answer every question with its safe default (no prompts). "
            "Used by the install scripts; ends up in free mode.",
        ),
    ] = False,
) -> None:
    """First-time setup, in plain English. Safe to rerun any time.

    Creates your database and settings file, optionally connects your
    Kalshi account, and checks that everything works. New computer?
    Run install.bat (Windows) or ./install.sh (Mac/Linux) — it calls
    this for you.
    """
    raise typer.Exit(code=run_setup_wizard(yes=yes))


@app.command()
def dashboard() -> None:
    """Open the app: starts the dashboard in your web browser.

    Shows current markets, model predictions, practice-trade results,
    and data health. Press Ctrl+C in this window to close it.
    """
    import subprocess  # noqa: PLC0415 -- only needed here  # nosec B404

    from kq.config import REPO_ROOT  # noqa: PLC0415

    app_path = REPO_ROOT / "src" / "kq" / "dashboard" / "streamlit_app.py"
    raise typer.Exit(
        code=subprocess.run(  # nosec B603 -- fixed argv, our own file
            [sys.executable, "-m", "streamlit", "run", str(app_path)],
            check=False,
        ).returncode
    )


@app.command("ingest-weather")
def ingest_weather() -> None:
    """Pull one round of Open-Meteo ensemble forecasts into DuckDB."""
    run_ingest_weather()


@app.command("ingest-metar")
def ingest_metar() -> None:
    """Pull the latest METAR observations for every station into DuckDB."""
    run_ingest_metar()


@app.command("ingest-ndfd")
def ingest_ndfd() -> None:
    """Pull the latest NDFD/NBM-deterministic Tmax benchmark for every station."""
    run_ingest_ndfd()


@app.command("ingest-observed")
def ingest_observed(
    lookback_days: Annotated[
        int,
        typer.Option(
            "--lookback-days",
            help="Trailing window to refresh (default 3 — idempotent upserts "
            "pick up late corrections to the climate reports). Use a wider "
            "window for recovery.",
        ),
    ] = 3,
) -> None:
    """Pull observed daily highs/lows (NWS ACIS settlement truth) for all stations.

    The daily settle pass reads `weather_observed`; without this scheduled
    ingest weather settlement can never fire (2026-06-11 audit #7).
    Idempotent on (station, valid_date).
    """
    run_ingest_observed(lookback_days=lookback_days)


@app.command("ingest-kalshi")
def ingest_kalshi(
    event_ticker: Annotated[
        list[str] | None,
        typer.Option(
            "--event-ticker",
            "-e",
            help="Override default station list. Repeatable. e.g. -e KXNBAGAME-26APR30BOSPHI",
        ),
    ] = None,
) -> None:
    """Snapshot Kalshi market orderbooks. Defaults to weather; -e overrides."""
    run_ingest_kalshi(event_tickers=event_ticker or None)


@app.command("backfill-weather")
def backfill_weather(
    start: str = typer.Option(..., help="YYYY-MM-DD"),
    end: str = typer.Option(..., help="YYYY-MM-DD"),
    model_id: Annotated[
        list[str] | None,
        typer.Option(
            "--model-id",
            help=(
                "Previous Runs model id (repeatable), e.g. gfs_seamless, "
                "ecmwf_ifs025. Default: all verified model lanes."
            ),
        ),
    ] = None,
) -> None:
    """Backfill true lead-1 weather forecast lanes between dates."""
    run_backfill_weather(start=start, end=end, model_ids=model_id or None)


@app.command("backfill-observed")
def backfill_observed(
    start: str = typer.Option(..., help="YYYY-MM-DD"),
    end: str = typer.Option(..., help="YYYY-MM-DD"),
) -> None:
    """Backfill observed daily high/low (NWS ACIS truth) between dates."""
    run_backfill_observed(start=start, end=end)


@app.command("backfill-ndfd")
def backfill_ndfd(
    start: str = typer.Option(..., help="YYYY-MM-DD"),
    end: str = typer.Option(..., help="YYYY-MM-DD"),
) -> None:
    """Backfill historical NDFD/NBM Tmax (Open-Meteo archive) between dates."""
    run_backfill_ndfd(start=start, end=end)


@app.command("ingest-ecmwf-opendata")
def ingest_ecmwf_opendata() -> None:
    """Pull the latest ECMWF Open Data IFS HRES cycle and upsert lead-1 daily Tmax.

    Pulls one ``fc.grib2`` per cycle (~130 MB) and extracts the
    ``mx2t24`` field at steps up to 48h (day-aligned per cycle) -- WMO-standard "max 2m temperature
    in last 24h", which IS tomorrow's calendar-day max under a 00z
    init. Tagged ``model='ecmwf_opendata'`` so the existing backtest
    engine A/Bs it against the Open-Meteo `model='ecmwf'` lane.

    Falls back to the prior cycle on a 404 (cycle not yet published).
    """
    raise typer.Exit(code=0 if run_ingest_ecmwf_opendata() >= 0 else 1)


@app.command("ingest-nba-schedule")
def ingest_nba_schedule(
    lookback_days: Annotated[
        int,
        typer.Option(
            "--lookback-days",
            help="How many days back from today to refresh. Default 1 catches "
            "late-finishing games from yesterday. Use a wider window for recovery.",
        ),
    ] = 1,
) -> None:
    """Pull NBA games (yesterday + today) into DuckDB. Idempotent on game_id.

    Phase 3 starter scaffold; CLAUDE.md §5 Phase 3 gates this behind Phase 2
    paper-trading exit. Safe to run any time — just doesn't have downstream
    consumers yet.
    """
    raise typer.Exit(code=0 if run_ingest_nba_schedule(lookback_days=lookback_days) >= 0 else 1)


@app.command("ingest-nba-injuries")
def ingest_nba_injuries(
    csv: Annotated[
        Path | None,
        typer.Option(
            "--csv",
            help="CSV file with columns: player_id, player_name, team_abbr, "
            "status, reason, as_of. Required to ingest; skipped with a warning "
            "when omitted (cron-safe before live source decision).",
        ),
    ] = None,
) -> None:
    """Ingest NBA injury statuses from a CSV file.

    v1: CSV-only. Live scraping deferred until CLAUDE.md §9 signs off
    on a dep choice (see kq.clients.nba_injuries for the menu).
    """
    raise typer.Exit(code=0 if run_ingest_nba_injuries(csv_path=csv) >= 0 else 1)


@app.command("build-nba-crosswalk")
def build_nba_crosswalk(
    lookback_days: Annotated[
        int,
        typer.Option(
            "--lookback-days",
            help="Window of game_dates to refresh. Default 7 covers a tipoff "
            "week without re-touching stale rows.",
        ),
    ] = 7,
) -> None:
    """Match Odds API games to nba_api games via (home, away, date).

    Reads ``nba_odds`` (latest snapshot per game) + ``nba_game`` rows
    in the lookback window and runs ``kq.models.nba_crosswalk.match_games``.
    Idempotent on PK (odds_api_game_id).
    """
    raise typer.Exit(code=0 if run_build_nba_crosswalk(lookback_days=lookback_days) >= 0 else 1)


@app.command("ingest-nba-odds")
def ingest_nba_odds() -> None:
    """Pull current NBA moneyline odds (Pinnacle h2h) into DuckDB.

    No-ops with a warning when ``ODDS_API_KEY`` is empty -- the cron
    entry can be active before the GOAT-plan signoff. Idempotent
    per (game_id, bookmaker, market, fetched_at).
    """
    raise typer.Exit(code=0 if run_ingest_nba_odds() >= 0 else 1)


@app.command("backfill-nba-schedule")
def backfill_nba_schedule(
    start: str = typer.Option(..., help="YYYY-MM-DD"),
    end: str = typer.Option(..., help="YYYY-MM-DD"),
) -> None:
    """Backfill historical NBA games via leaguegamefinder. Idempotent.

    Per Phase 3 PR 1 plan: backfill ≥ 6 seasons of completed games before
    Elo training. Single API call per range; OK to invoke for multi-season
    pulls (NBA's endpoint handles it).
    """
    run_backfill_nba_schedule(start=start, end=end)


@app.command("train-weather")
def train_weather(
    lead_days: Annotated[
        int,
        typer.Option("--lead-days", help="Forecast lead in days. v1 default: 1."),
    ] = 1,
) -> None:
    """Fit per-station NGR weather models from the joined training set."""
    run_train_weather(lead_days=lead_days)


@app.command()
def ingest() -> None:
    """Run every ingest once (weather + METAR + NDFD + Kalshi + observed truth).

    Use for cron."""
    raise typer.Exit(code=run_ingest_all())


@app.command()
def backtest(
    strategy: Annotated[
        str,
        typer.Option(
            "--strategy",
            help="weather_v1 (pure NGR) | weather_router_v1 (per-station NGR/raw)",
        ),
    ] = "weather_v1",
) -> None:
    """Replay forecasts vs observed truth, simulate trades vs naive market, emit P&L."""
    run_backtest_flow(strategy=strategy)


@app.command("backtest-nba-clv")
def backtest_nba_clv() -> None:
    """Replay finished NBA games through Elo + Pinnacle vig-strip, emit CLV manifest.

    Reads ``nba_game`` (settled games), ``nba_odds`` (entry + closing
    Pinnacle quotes fetched STRICTLY BEFORE tipoff), and
    ``nba_game_crosswalk`` (Odds API ↔ NBA game id bridge); computes
    price-based CLV per game — (devigged pre-tipoff closing prob of the
    bought side) minus (vig-inclusive entry price) — and writes
    ``models/backtest_nba_clv_manifest.json`` with the Phase 5 #5
    ``mean_clv`` metric. Games with only in-play quotes are excluded
    and counted (``n_excluded_no_pretipoff_close``).

    Safe to run with empty inputs (off-season, pre-GOAT signoff): the
    manifest reports n_evaluated=0 and the skip-path counters.
    """
    n = run_nba_clv_backtest()
    raise typer.Exit(code=0 if n >= 0 else 1)


@app.command("backtest-weather-clv")
def backtest_weather_clv(
    strategy: Annotated[
        str,
        typer.Option(
            "--strategy",
            help="weather_router_v1 (active config, default) | weather_v1 | "
            "weather_all_raw_v1. Falls back to weather_v1 if router_config.json is absent.",
        ),
    ] = "weather_router_v1",
) -> None:
    """Score the weather model's edge vs the NDFD benchmark, emit a CLV manifest.

    Runs the rolling-origin backtest (PIT-correct per-bracket model + NDFD
    probabilities), scores each settled (station, date, bracket) through the
    weather CLV evaluator, and writes ``models/backtest_weather_clv_manifest.json``
    with per-station Brier-vs-NDFD and the unconditional ``mean_edge_vs_ndfd``
    (no outcome conditioning). The weather twin of ``backtest-nba-clv``.
    Safe on an empty DB (reports n_evaluated=0).
    """
    n = run_weather_clv_backtest(strategy=strategy)
    raise typer.Exit(code=0 if n >= 0 else 1)


@app.command("study-nowcast-edge")
def study_nowcast_edge(
    window_hours: Annotated[
        int,
        typer.Option(
            "--window-hours",
            help="How many final hours before settlement to study (default 8).",
        ),
    ] = NOWCAST_STUDY_WINDOW_HOURS,
) -> None:
    """Measures whether we actually beat the market in the final hours before
    settlement -- the project's #1 hypothesized edge.

    Replays every settled weather market's orderbook history: at each of the
    final hours it rebuilds what our up-to-the-minute temperature model
    (the METAR nowcast) would have said, using only data available at that
    moment, and compares it with the market's price and the eventual
    outcome. Writes ``models/nowcast_edge_manifest.json`` (shown on the
    dashboard's "Nowcast edge" tab). Safe on an empty database -- reports
    n=0 with a friendly note and exits 0. Read-only; never trades.
    """
    n = run_study_nowcast_edge(window_hours=window_hours)
    raise typer.Exit(code=0 if n >= 0 else 1)


@app.command("plan-gefsv12-pull")
def plan_gefsv12_pull(
    start_year: Annotated[
        int,
        typer.Option("--start-year", help="Archive start year (>= 2000)."),
    ] = 2000,
    end_year: Annotated[
        int,
        typer.Option("--end-year", help="Archive end year (<= 2019, frozen)."),
    ] = 2019,
    n_stations: Annotated[
        int,
        typer.Option("--n-stations", help="Number of stations to extract per file."),
    ] = 6,
    records_per_file: Annotated[
        int,
        typer.Option("--records-per-file", help="Forecast-hour records per file."),
    ] = 1,
) -> None:
    """Dry-run estimate of the planned GEFSv12 reforecast pull (Phase 1 of #6).

    Reads NO data — just sizes up the work for the future
    `kq pull-gefsv12-reforecasts` (Phase 2; needs eccodes/cfgrib signoff).
    See docs/research/GEFSV12-REFORECAST-INTEGRATION.md.
    """
    run_plan_gefsv12_pull(
        start_year=start_year,
        end_year=end_year,
        n_stations=n_stations,
        n_target_records_per_file=records_per_file,
    )


@app.command("pull-gefsv12-reforecasts")
def pull_gefsv12_reforecasts(
    start_year: Annotated[int, typer.Option("--start-year")] = 2000,
    end_year: Annotated[int, typer.Option("--end-year")] = 2019,
    members: Annotated[
        str,
        typer.Option(
            "--members",
            help=(
                "Comma-separated members. Smoke test: 'c00'. Full ensemble: 'c00,p01,p02,p03,p04'."
            ),
        ),
    ] = ",".join(GEFSV12_DEFAULT_MEMBERS),
    max_days: Annotated[
        int | None,
        typer.Option("--max-days", help="Truncate per member (smoke testing)."),
    ] = None,
    max_concurrent: Annotated[
        int, typer.Option("--max-concurrent", help="HTTP concurrency cap.")
    ] = 5,
) -> None:
    """Phase 2 of #6: pull GEFSv12 reforecast Tmax for lead-day-1 into DuckDB.

    Idempotent on the weather_forecast PK. Use --max-days for smoke tests.
    """
    run_pull_gefsv12_reforecasts(
        start_year=start_year,
        end_year=end_year,
        members=tuple(m.strip() for m in members.split(",") if m.strip()),
        max_days=max_days,
        max_concurrent=max_concurrent,
    )


@app.command("decide-router")
def decide_router(
    threshold_pct: Annotated[
        float,
        typer.Option(
            "--threshold-pct",
            help="Min Brier-improvement %% to choose NGR over raw (default 1.0)",
        ),
    ] = 1.0,
    mode: Annotated[
        str,
        typer.Option(
            "--mode",
            help=(
                "Decision mode: auto (default — strongest available), "
                "calibration_aware (n-aware reliability + Brier-vs-NDFD; "
                "needs all 4 manifests), ndfd_aware (NGR vs RAW on Brier-vs-NDFD), "
                "or legacy (NGR vs naive market)."
            ),
        ),
    ] = "auto",
    brier_tolerance_pp: Annotated[
        float,
        typer.Option(
            "--brier-tolerance-pp",
            help=(
                "calibration_aware only: refuse to pick a calibration-passing strategy "
                "if its Brier-vs-NDFD is more than this far below the overall best (default 5.0)."
            ),
        ),
    ] = 5.0,
) -> None:
    """Read backtest manifests, write models/router_config.json with per-station strategy.

    `mode=auto` (default) picks the strongest available mode — calibration_aware
    when all 4 manifests are present, else ndfd_aware, else legacy. Pass an
    explicit `--mode` to lock the choice (useful for A/B comparisons).
    """
    run_decide_router(
        threshold_pct=threshold_pct,
        mode=mode,  # type: ignore[arg-type]  # typer can't narrow Literal from str
        brier_tolerance_pp=brier_tolerance_pp,
    )


@app.command()
def paper(
    settle_only: Annotated[
        bool,
        typer.Option(
            "--settle-only",
            help="Skip the submit pass; only resolve already-booked trades.",
        ),
    ] = False,
    starting_bankroll_usd: Annotated[
        float,
        typer.Option(
            "--starting-bankroll-usd",
            help="Snapshot bankroll for Kelly sizing (does not affect settle pass).",
        ),
    ] = 1_000.0,
    target_date: Annotated[
        str | None,
        typer.Option(
            "--target-date",
            help="ISO date for the forecast horizon (default: tomorrow UTC).",
        ),
    ] = None,
    no_nowcast: Annotated[
        bool,
        typer.Option(
            "--no-nowcast",
            help="Disable the intraday METAR Bayesian update (default: enabled).",
        ),
    ] = False,
) -> None:
    """Run one paper-trading cycle (submit + settle). Safe to invoke from cron."""
    raise typer.Exit(
        code=run_paper_trade(
            settle_only=settle_only,
            starting_bankroll_usd=starting_bankroll_usd,
            target_date_iso=target_date,
            use_nowcast=not no_nowcast,
        )
    )


@app.command("paper-nba")
def paper_nba(
    settle_only: Annotated[
        bool,
        typer.Option(
            "--settle-only",
            help="Skip the submit pass; only settle already-booked NBA trades.",
        ),
    ] = False,
) -> None:
    """Run one NBA paper-trading cycle (submit + settle).

    Pulls open Kalshi NBA-game-winner markets, joins to the latest
    Pinnacle quote and current Elo state, and writes signals + paper
    trades for any model edge above ``KQ_KELLY_FRACTION``. Settles
    trades whose underlying NBA game has resolved.

    No-ops gracefully if Kalshi credentials are missing or no NBA
    markets are open. Safe to invoke from cron.
    """
    raise typer.Exit(code=0 if run_paper_nba_trade(settle_only=settle_only) >= 0 else 1)


@app.command("paper-summary")
def paper_summary(
    start: Annotated[
        str | None,
        typer.Option("--start", help="Filter range start (YYYY-MM-DD, inclusive)."),
    ] = None,
    end: Annotated[
        str | None,
        typer.Option("--end", help="Filter range end (YYYY-MM-DD, inclusive)."),
    ] = None,
    starting_bankroll_usd: Annotated[
        float,
        typer.Option(
            "--starting-bankroll-usd",
            help="Bankroll snapshot for ROI calc; does not modify any data.",
        ),
    ] = 1_000.0,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit JSON instead of the human-readable table."),
    ] = False,
) -> None:
    """Roll-up paper-trade activity. Read-only. Used for the Phase 2 exit
    daily check and for cron alerting (see docs/SCHEDULED-RUNS.md).

    Exits 0 if both Phase 2 exit criteria pass (>=50 settled trades AND
    >=14 distinct trade days), 1 if either is still accumulating, 2 on a
    fundamental error (DB unreachable, etc.). Phase 5 gate #1 progress
    (settled / 500) is reported separately in the output. The exit-1 case
    is informational, not failure — cron should `&&` to surface progress
    without alerting.
    """
    import datetime as _dt  # noqa: PLC0415 — local import keeps top-level lean

    try:
        start_d = _dt.date.fromisoformat(start) if start else None
        end_d = _dt.date.fromisoformat(end) if end else None
    except ValueError as exc:
        # Exit 2 (fundamental error), not 1: cron treats exit 1 as the
        # documented "still accumulating, don't alert" code, so a malformed
        # date must not masquerade as it.
        typer.echo(
            f"paper-summary: invalid --start/--end value ({exc}); expected YYYY-MM-DD",
            err=True,
        )
        raise typer.Exit(code=2) from exc
    raise typer.Exit(
        code=run_paper_summary(
            start_date=start_d,
            end_date=end_d,
            starting_bankroll_usd=starting_bankroll_usd,
            json_output=json_output,
        )
    )


@app.command("router-summary")
def router_summary(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit JSON instead of the human-readable view."),
    ] = False,
) -> None:
    """Live trading config snapshot. Read-only.

    Reads `models/router_config.json` + the four backtest manifests and
    shows per-station: which strategy is active, why, and how every
    strategy compares on Brier-vs-NDFD + n-aware calibration. Use to
    sanity-check what a paper-trading run would dispatch today.

    Exits 0 if the active config currently clears Phase 5 #2's "≥ 4/6
    stations clear ≥ 2-3% Brier vs NDFD" bar; 1 otherwise (informational);
    2 on a manifest-parse error.
    """
    raise typer.Exit(code=run_router_summary(json_output=json_output))


@app.command("doctor")
def doctor(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit JSON instead of the human-readable report."),
    ] = False,
) -> None:
    """Reality-contact diagnostics: live venue probes + DB truth checks.

    Deliberately NON-hermetic (real network calls to Kalshi's public
    market endpoints). The antidote to the 2026-06-11 audit failure
    class: green tests + broken reality. Run after every deploy and
    weekly via scripts/reality-probe.sh. Exit: 0 OK / 1 WARN / 2 CRIT.
    """
    raise typer.Exit(code=run_doctor(json_output=json_output))


@app.command("health-check")
def health_check(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit JSON instead of the human-readable summary."),
    ] = False,
) -> None:
    """System health snapshot for cron alerting. Read-only.

    Checks pipeline freshness across weather/metar/NDFD/Kalshi tables and
    the backtest_manifest + router_config file mtimes. Returns:

      0 — all OK
      1 — at least one WARN (single missed cron tick or similar)
      2 — at least one CRIT (table-empty / file-missing / DB unreachable)

    Pair with `&&` / `||` in cron to drive alerting:

        kq health-check && echo 'OK' >> heartbeat.log || ntfy_alert
    """
    raise typer.Exit(code=run_health_check(json_output=json_output))


@app.command("state-check")
def state_check(
    state: Annotated[
        str | None,
        typer.Option("--state", help="2-letter US state code; overrides OPERATOR_STATE env."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit JSON instead of the human-readable summary."),
    ] = False,
) -> None:
    """Check whether Kalshi sports contracts are available in the operator's state.

    Per CLAUDE.md §5 readiness #8 + the May 2026 research snapshot, sports
    contracts are blocked or contested in MA / NV / AZ / MD / MT / OH / MI /
    IL / CT / NY (~10 states). Weather contracts are uncontested in all 50
    states. Court cases are moving fast; re-run after major rulings.

    Reads operator state from `--state` flag or `OPERATOR_STATE` in `.env`.
    Exits 0 if green for sports, 1 if contested (paper-only), 2 if blocked
    or operator state unset.
    """
    raise typer.Exit(code=run_state_check(state=state, json_output=json_output))


@app.command()
def live(
    i_understand_the_risks: bool = typer.Option(
        False,
        "--i-understand-the-risks",
        help="Required acknowledgment. Gated behind CLAUDE.md §5.",
    ),
) -> None:
    """Start the live trader. Refuses unless Phase 5 gate is cleared AND env var set."""
    assert_live_allowed(ack=i_understand_the_risks)
    raise typer.Exit(code=_not_yet("live", phase=5))


def _not_yet(cmd: str, phase: int) -> int:
    typer.echo(f"[not-implemented] `kq {cmd}` lands in Phase {phase}. See CLAUDE.md §5.", err=True)
    return 2


if __name__ == "__main__":
    app()
