"""CLI entrypoint: `python -m kq ...`."""

from __future__ import annotations

from typing import Annotated

import typer

from kq import __version__
from kq.execution.live import assert_live_allowed
from kq.flows.backfill_observed import main as run_backfill_observed
from kq.flows.backfill_weather import main as run_backfill_weather
from kq.flows.ingest_all import main as run_ingest_all
from kq.flows.ingest_kalshi import main as run_ingest_kalshi
from kq.flows.ingest_metar import main as run_ingest_metar
from kq.flows.ingest_weather import main as run_ingest_weather
from kq.flows.train_weather import main as run_train_weather

app = typer.Typer(
    name="kq",
    help="forecast-lab CLI. See CLAUDE.md for the phased milestone plan.",
    no_args_is_help=True,
)


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
def backtest(strategy: str = typer.Option(..., help="Strategy name, e.g. weather_v1")) -> None:
    """Run a backtest for `strategy`. Implemented in Phase 2."""
    _ = strategy
    raise typer.Exit(code=_not_yet("backtest", phase=2))


@app.command()
def paper() -> None:
    """Start the paper trader. Implemented in Phase 2."""
    raise typer.Exit(code=_not_yet("paper", phase=2))


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
