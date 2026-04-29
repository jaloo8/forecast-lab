"""CLI entrypoint: `python -m kq ...`."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from kq import __version__
from kq._logging import bind_trace_id, setup_logging
from kq.config import get_settings
from kq.execution.live import assert_live_allowed
from kq.flows.backfill_observed import main as run_backfill_observed
from kq.flows.backfill_weather import main as run_backfill_weather
from kq.flows.decide_router import main as run_decide_router
from kq.flows.ingest_all import main as run_ingest_all
from kq.flows.ingest_kalshi import main as run_ingest_kalshi
from kq.flows.ingest_metar import main as run_ingest_metar
from kq.flows.ingest_weather import main as run_ingest_weather
from kq.flows.paper_trade import main as run_paper_trade
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
