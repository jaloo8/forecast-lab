"""CLI entrypoint: `python -m kq ...`."""

from __future__ import annotations

import typer

from kq import __version__
from kq.execution.live import assert_live_allowed
from kq.flows.ingest_weather import main as run_ingest_weather

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


@app.command()
def ingest() -> None:
    """Run every scheduled ingest once (weather + NBA + Kalshi). Phase 1 partial."""
    raise typer.Exit(code=_not_yet("ingest (full)", phase=1))


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
