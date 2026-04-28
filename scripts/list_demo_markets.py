"""Diagnostic: list every open market on Kalshi demo, grouped by event_ticker.

Useful when `make ingest-kalshi` returns 0 markets and you want to know what
tickers actually exist on demo. Read-only; no writes; no creds beyond what's
already in .env.

Run with:
    uv run python scripts/list_demo_markets.py
"""

from __future__ import annotations

import asyncio

from kq.clients.kalshi import KalshiClient


async def main() -> None:
    async with KalshiClient.from_settings() as c:
        markets = await c.list_markets(status="open", limit=200)

    events: dict[str, list[str]] = {}
    for m in markets:
        events.setdefault(m.event_ticker, []).append(m.ticker)

    print(f"Demo has {len(markets)} open markets across {len(events)} events")
    print()
    for et, tickers in sorted(events.items()):
        print(f"  {et}: {len(tickers)} markets")
        # Show one sample ticker so we can see what they look like
        if tickers:
            print(f"    e.g. {tickers[0]}")


if __name__ == "__main__":
    asyncio.run(main())
