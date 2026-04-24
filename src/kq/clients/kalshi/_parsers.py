"""Parsers: Kalshi wire JSON -> typed domain objects.

Split from the client so test surface is explicit and mockable without
standing up HTTP plumbing.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from kq.clients.kalshi._types import Market, OrderBookSnapshot


def _parse_market(raw: dict[str, Any]) -> Market:
    return Market(
        ticker=str(raw.get("ticker", "")),
        event_ticker=str(raw.get("event_ticker", "")),
        title=str(raw.get("title", "")),
        status=str(raw.get("status", "")),
        category=_opt_str(raw.get("category")),
        yes_ask=_cents_to_dollars(raw.get("yes_ask")),
        yes_bid=_cents_to_dollars(raw.get("yes_bid")),
        last_price=_cents_to_dollars(raw.get("last_price")),
        volume=_opt_float(raw.get("volume")),
        open_interest=_opt_float(raw.get("open_interest")),
        open_time=_opt_dt(raw.get("open_time")),
        close_time=_opt_dt(raw.get("close_time")),
        expected_expiration_time=_opt_dt(raw.get("expected_expiration_time")),
        rules_primary=_opt_str(raw.get("rules_primary")),
    )


def _parse_orderbook(
    payload: dict[str, Any], *, ticker: str, snap_time: datetime
) -> OrderBookSnapshot:
    book = payload.get("orderbook") or {}
    yes_bids_raw = book.get("yes") or []
    yes_asks_raw = book.get("no") or []
    # Kalshi: `yes` = YES-bid ladder; `no` = NO-bid ladder.
    # YES-ask price = 100 - NO-bid price.
    yes_bids = tuple(sorted(_clean_ladder(yes_bids_raw), key=lambda r: -r[0]))
    yes_asks = tuple(
        sorted(
            ((100 - p, s) for p, s in _clean_ladder(yes_asks_raw)),
            key=lambda r: r[0],
        )
    )
    best_bid = yes_bids[0][0] / 100.0 if yes_bids else None
    best_ask = yes_asks[0][0] / 100.0 if yes_asks else None
    best_bid_size = yes_bids[0][1] if yes_bids else None
    best_ask_size = yes_asks[0][1] if yes_asks else None
    return OrderBookSnapshot(
        snap_time=snap_time,
        ticker=ticker,
        yes_bid=best_bid,
        yes_ask=best_ask,
        yes_bid_size=best_bid_size,
        yes_ask_size=best_ask_size,
        yes_bids=yes_bids,
        yes_asks=yes_asks,
    )


def _clean_ladder(raw: Any) -> list[tuple[int, int]]:
    """Filter a ladder to well-formed (price_cents, size) tuples."""
    out: list[tuple[int, int]] = []
    if not isinstance(raw, list):
        return out
    for entry in raw:
        if not isinstance(entry, list | tuple) or len(entry) != 2:
            continue
        price, size = entry
        try:
            out.append((int(price), int(size)))
        except (TypeError, ValueError):
            continue
    return out


def _cents_to_dollars(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value) / 100.0
    except (TypeError, ValueError):
        return None


def _opt_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _opt_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _opt_dt(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
