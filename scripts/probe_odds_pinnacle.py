"""One-shot probe: does The Odds API free tier return Pinnacle when we ask the EU region?

Reads ODDS_API_KEY from .env via the project config. Prints whether Pinnacle is in
the response and how much of the 500/mo free-tier quota remains. Safe to run any
time -- exactly one credit per invocation.
"""

from __future__ import annotations

import sys

import httpx

from kq.config import get_settings


def main() -> int:
    key = get_settings().odds_api_key.strip()
    if not key:
        print("ODDS_API_KEY is empty. Add it to .env then re-run.")
        return 1
    print(f"Key loaded ({len(key)} chars).")

    try:
        r = httpx.get(
            "https://api.the-odds-api.com/v4/sports/upcoming/odds",
            params={"apiKey": key, "regions": "eu", "markets": "h2h"},
            timeout=10.0,
        )
    except httpx.HTTPError as exc:
        print(f"Request failed: {exc}")
        return 1

    remaining = r.headers.get("x-requests-remaining", "?")
    print(f"HTTP {r.status_code}, free-tier quota remaining: {remaining}/500")
    if r.status_code != 200:
        print(r.text[:300])
        return 1

    games = r.json()
    books = sorted({b["key"] for g in games for b in g.get("bookmakers", [])})
    print(f"{len(games)} upcoming games, {len(books)} unique books in EU region")
    print(f"books seen: {books}")
    if "pinnacle" in books:
        print("VERDICT: Pinnacle returned on free tier - no $30/mo subscription needed.")
    else:
        print("VERDICT: Pinnacle NOT on free tier - GOAT plan is the path.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
