"""Aggregate ingest: runs weather, METAR, and Kalshi (if creds) in sequence.

Designed for cron. Each sub-flow is wrapped in its own try/except so a single
upstream outage does not block the rest. Exits:
    0 — at least one sub-flow succeeded
    1 — every sub-flow failed

Intended cadences are documented in `docs/SCHEDULED-RUNS.md`. This entrypoint
runs every sub-flow once per invocation; use cron (or later Prefect 3) to
pace it.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import structlog

from kq.clients.kalshi import KalshiCredentialsError
from kq.flows.ingest_kalshi import ingest_once as ingest_kalshi_once
from kq.flows.ingest_metar import ingest_once as ingest_metar_once
from kq.flows.ingest_ndfd import ingest_once as ingest_ndfd_once
from kq.flows.ingest_weather import ingest_once as ingest_weather_once

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class FlowResult:
    name: str
    ok: bool
    rows: int
    detail: str = ""


async def _run_weather() -> FlowResult:
    try:
        n = await ingest_weather_once()
    except Exception as exc:
        log.exception("ingest.weather_failed")
        return FlowResult("weather", ok=False, rows=0, detail=repr(exc))
    return FlowResult("weather", ok=True, rows=n)


async def _run_metar() -> FlowResult:
    try:
        n = await ingest_metar_once()
    except Exception as exc:
        log.exception("ingest.metar_failed")
        return FlowResult("metar", ok=False, rows=0, detail=repr(exc))
    return FlowResult("metar", ok=True, rows=n)


async def _run_ndfd() -> FlowResult:
    try:
        n = await ingest_ndfd_once()
    except Exception as exc:
        log.exception("ingest.ndfd_failed")
        return FlowResult("ndfd", ok=False, rows=0, detail=repr(exc))
    return FlowResult("ndfd", ok=True, rows=n)


async def _run_kalshi() -> FlowResult:
    try:
        n_markets, n_books = await ingest_kalshi_once()
    except KalshiCredentialsError as exc:
        log.warning("ingest.kalshi_skipped", detail=str(exc))
        return FlowResult("kalshi", ok=False, rows=0, detail="credentials missing")
    except Exception as exc:
        log.exception("ingest.kalshi_failed")
        return FlowResult("kalshi", ok=False, rows=0, detail=repr(exc))
    return FlowResult("kalshi", ok=True, rows=n_markets + n_books)


async def ingest_all() -> list[FlowResult]:
    """Run every sub-flow once, collecting results. Never raises."""
    results = [
        await _run_weather(),
        await _run_metar(),
        await _run_ndfd(),
        await _run_kalshi(),
    ]
    log.info(
        "ingest.summary",
        ok=[r.name for r in results if r.ok],
        failed=[r.name for r in results if not r.ok],
    )
    return results


def main() -> int:
    """`python -m kq ingest` / cron entrypoint. Returns shell exit code."""
    results = asyncio.run(ingest_all())
    for r in results:
        marker = "OK " if r.ok else "ERR"
        tail = f" ({r.detail})" if r.detail else ""
        print(f"  {marker} {r.name}: {r.rows} rows{tail}")
    return 0 if any(r.ok for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
