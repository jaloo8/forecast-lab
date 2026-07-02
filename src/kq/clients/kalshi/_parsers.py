"""Parsers: Kalshi wire JSON -> typed domain objects.

Split from the client so test surface is explicit and mockable without
standing up HTTP plumbing.

Two wire formats are supported (2026-06-11 audit, PR-A):

* **Prod (current)** — prices as dollar-strings (``yes_bid_dollars:
  "0.0500"``), volumes as ``*_fp`` float-strings, orderbooks under
  ``orderbook_fp`` with ``yes_dollars``/``no_dollars`` ladders of
  ``[price_dollars_str, size_str]`` and fractional sizes. Verified against
  ``api.elections.kalshi.com`` live; recorded fixtures in
  ``tests/fixtures/kalshi_prod_*.json``.
* **Legacy / demo** — prices as integer cents (``yes_bid: 5``), orderbooks
  under ``orderbook`` with ``yes``/``no`` integer-cent ladders.

Prod-style fields are preferred when present; legacy fields are the
fallback. Everything is normalized to the package convention: prices in
dollars (0..1), sizes as floats.
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
        yes_ask=_price_dollars(raw, "yes_ask"),
        yes_bid=_price_dollars(raw, "yes_bid"),
        yes_ask_size=_fp_or_legacy_float(raw, "yes_ask_size"),
        yes_bid_size=_fp_or_legacy_float(raw, "yes_bid_size"),
        last_price=_price_dollars(raw, "last_price"),
        volume=_fp_or_legacy_float(raw, "volume"),
        open_interest=_fp_or_legacy_float(raw, "open_interest"),
        open_time=_opt_dt(raw.get("open_time")),
        close_time=_opt_dt(raw.get("close_time")),
        expected_expiration_time=_opt_dt(raw.get("expected_expiration_time")),
        rules_primary=_opt_str(raw.get("rules_primary")),
        strike_type=_opt_str(raw.get("strike_type")),
        floor_strike=_opt_float(raw.get("floor_strike")),
        cap_strike=_opt_float(raw.get("cap_strike")),
    )


def _parse_orderbook(
    payload: dict[str, Any], *, ticker: str, snap_time: datetime
) -> OrderBookSnapshot:
    fp = payload.get("orderbook_fp")
    if isinstance(fp, dict):
        # Prod format: dollar-string ladders, fractional sizes.
        yes_bids_raw = _clean_ladder_dollars(fp.get("yes_dollars") or [])
        no_bids_raw = _clean_ladder_dollars(fp.get("no_dollars") or [])
    else:
        # Legacy format: integer-cent ladders.
        book = payload.get("orderbook") or {}
        yes_bids_raw = [
            (p / 100.0, float(s)) for p, s in _clean_ladder_cents(book.get("yes") or [])
        ]
        no_bids_raw = [(p / 100.0, float(s)) for p, s in _clean_ladder_cents(book.get("no") or [])]

    # Kalshi: yes ladder = YES-bid; no ladder = NO-bid. YES-ask = 1.0 - NO-bid.
    # round() kills float dust from the complement (1.0 - 0.99 = 0.010000...09);
    # 4 decimals is below Kalshi's 1-cent (linear_cent) tick so it is lossless.
    yes_bids = tuple(sorted(yes_bids_raw, key=lambda r: -r[0]))
    yes_asks = tuple(sorted(((round(1.0 - p, 4), s) for p, s in no_bids_raw), key=lambda r: r[0]))
    best_bid = yes_bids[0][0] if yes_bids else None
    best_ask = yes_asks[0][0] if yes_asks else None
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


def _clean_ladder_dollars(raw: Any) -> list[tuple[float, float]]:
    """Filter a prod ``*_dollars`` ladder to well-formed (price_dollars, size) tuples.

    Drops out-of-range prices AND non-positive sizes: a size-0.00 level is
    not a quotable level, and keeping it would surface a phantom top-of-book
    (best bid/ask with nothing behind it).
    """
    out: list[tuple[float, float]] = []
    if not isinstance(raw, list):
        return out
    for entry in raw:
        if not isinstance(entry, list | tuple) or len(entry) != 2:
            continue
        price, size = entry
        try:
            p, s = float(price), float(size)
        except (TypeError, ValueError):
            continue
        if not 0.0 <= p <= 1.0:
            continue
        if not s > 0.0:  # rejects NaN, zero (phantom level), and negative sizes
            continue
        out.append((p, s))
    return out


def _clean_ladder_cents(raw: Any) -> list[tuple[int, int]]:
    """Filter a legacy integer-cent ladder to well-formed (price_cents, size) tuples.

    Mirrors :func:`_clean_ladder_dollars`: prices outside 0..100 cents and
    non-positive sizes are dropped — the legacy path previously admitted both.
    """
    out: list[tuple[int, int]] = []
    if not isinstance(raw, list):
        return out
    for entry in raw:
        if not isinstance(entry, list | tuple) or len(entry) != 2:
            continue
        price, size = entry
        try:
            p, s = int(price), int(size)
        except (TypeError, ValueError):
            continue
        if not 0 <= p <= 100:
            continue
        if s <= 0:
            continue
        out.append((p, s))
    return out


def _price_dollars(raw: dict[str, Any], base: str) -> float | None:
    """Prefer the prod ``{base}_dollars`` string field; fall back to legacy
    integer-cent ``{base}``."""
    dollars = raw.get(f"{base}_dollars")
    if dollars is not None:
        try:
            return float(dollars)
        except (TypeError, ValueError):
            pass
    return _cents_to_dollars(raw.get(base))


def _fp_or_legacy_float(raw: dict[str, Any], base: str) -> float | None:
    """Prefer the prod ``{base}_fp`` float-string field; fall back to legacy
    numeric ``{base}``."""
    fp = raw.get(f"{base}_fp")
    if fp is not None:
        try:
            return float(fp)
        except (TypeError, ValueError):
            pass
    return _opt_float(raw.get(base))


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
