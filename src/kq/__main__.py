"""CLI entrypoint: `python -m kq ...`."""

from __future__ import annotations

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
from kq.flows.decide_router import main as run_decide_router
from kq.flows.health_check import main as run_health_check
from kq.flows.ingest_all import main as run_ingest_all
from kq.flows.ingest_kalshi import main as run_ingest_kalshi
from kq.flows.ingest_metar import main as run_ingest_metar
from kq.flows.ingest_nba_schedule import main as run_ingest_nba_schedule
from kq.flows.ingest_ndfd import main as run_ingest_ndfd
from kq.flows.ingest_weather import main as run_ingest_weather
from kq.flows.paper_summary import main as run_paper_summary
from kq.flows.paper_trade import main as run_paper_trade
from kq.flows.plan_gefsv12_pull import main as run_plan_gefsv12_pull
from kq.flows.pull_gefsv12_reforecasts import main as run_pull_gefsv12_reforecasts
from kq.flows.run_backtest import main as run_backtest_flow
from kq.flows.train_weather import main as run_train_weather

app = typer.Typer(
    name="kq",
    help="forecast-lab CLI. See CLAUDE.md for the phased milestone plan.",
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
        bool,
        typer.Option(
            "--log-json/--log-pretty",
            help="Force JSON or pretty console output. Default auto-detects: "
            "JSON in non-TTY (cron/CI/pipes), pretty in interactive shells.",
        ),
    ] = False,
) -> None:
    """Configure logging once before any subcommand runs.

    Honors precedence: CLI flag > LOG_LEVEL env var > 'info' default. Binds
    a fresh trace_id to the contextvar so every log line for this run can be
    correlated with `trace_id=<value>`.
    """
    settings = get_settings()
    effective_level = log_level or settings.log_level or "info"
    setup_logging(
        level=effective_level,
        log_file=log_file,
        json_output=True if log_json else None,
    )
    bind_trace_id()


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo(__version__)


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
) -> None:
    """Backfill historical deterministic weather forecasts between dates."""
    run_backfill_weather(start=start, end=end)


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
    """Run every ingest once (weather + METAR + Kalshi). Use for cron."""
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
) -> None:
    """Read backtest manifest, write models/router_config.json with per-station strategy."""
    run_decide_router(threshold_pct=threshold_pct)


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

    Exits 0 if both Phase 5 gates pass (>=50 settled trades AND >=14 active
    days), 1 if either is still accumulating, 2 on a fundamental error
    (DB unreachable, etc.). The exit-1 case is informational, not failure —
    cron should `&&` to surface progress without alerting.
    """
    import datetime as _dt  # noqa: PLC0415 — local import keeps top-level lean

    start_d = _dt.date.fromisoformat(start) if start else None
    end_d = _dt.date.fromisoformat(end) if end else None
    raise typer.Exit(
        code=run_paper_summary(
            start_date=start_d,
            end_date=end_d,
            starting_bankroll_usd=starting_bankroll_usd,
            json_output=json_output,
        )
    )


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
