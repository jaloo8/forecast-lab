"""Match generated brackets to live Kalshi weather markets.

Backtest uses synthetic brackets directly. Paper executor needs to find the
real Kalshi market that corresponds to each generated bracket so it can pull
the orderbook + simulate a fill.

Matching rules:
    1. Parse every Kalshi market ticker we have via `parse_weather_market_ticker`
    2. For a given (station, valid_date, threshold), find the market whose
       parsed (icao, valid_date, threshold_f) match exactly
    3. If multiple match (shouldn't happen but defensive), pick the most
       recently-opened one
    4. If none match, return None

The match is INTEGER-EXACT on threshold. If `Bracket.threshold_f = 75.0` we
match `KXHIGHLAX-...-T75`, not `T74` or `T76`. Bracket spacing is 2F by
default so this is safe; widen the tolerance only if Kalshi publishes
between-degree thresholds.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date

from kq.backtest.brackets import Bracket
from kq.clients.kalshi import Market
from kq.clients.kalshi._ticker_parser import (
    WeatherMarketRef,
    parse_weather_market_ticker,
)


def parsed_weather_markets(
    markets: Iterable[Market],
) -> list[tuple[Market, WeatherMarketRef]]:
    """Return only the markets that parse as weather contracts AND are safe
    to price with the current threshold-exceedance model.

    PR-A interim guard (2026-06-11 audit): prod low-tail ``-T<n>`` tickers are
    ``strike_type='less'`` (YES iff value < cap) and ``-B<x>.5`` between-markets
    don't parse at all — the legacy ticker-text path would price a *less*
    contract as a *greater* one, i.e. exactly inverted. Until the strike-aware
    matcher lands (PR-B), only ``strike_type == 'greater'`` markets whose
    ``floor_strike`` agrees with the ticker threshold are eligible. Markets
    with ``strike_type=None`` (legacy/demo payloads) keep the old behavior.
    """
    parsed: list[tuple[Market, WeatherMarketRef]] = []
    for m in markets:
        ref = parse_weather_market_ticker(m.ticker)
        if ref is None:
            continue
        if m.strike_type is not None:
            if m.strike_type != "greater":
                continue  # less/between: wrong semantics for P(T > thr) pricing
            if m.floor_strike is not None and float(ref.threshold_f) != m.floor_strike:
                continue  # ticker text disagrees with API strike — refuse to guess
        parsed.append((m, ref))
    return parsed


def find_matching_market(
    bracket: Bracket,
    *,
    icao: str,
    valid_date: date,
    weather_markets: Sequence[tuple[Market, WeatherMarketRef]],
) -> Market | None:
    """Find the Kalshi market for the given bracket on (icao, valid_date).

    Returns the most-recently-opened match if multiple candidates exist
    (shouldn't happen — Kalshi gives one market per (station, date, threshold)
    — but defensive). Returns None when no match.
    """
    threshold_int = round(bracket.threshold_f)
    matches = [
        market
        for market, ref in weather_markets
        if ref.icao == icao and ref.valid_date == valid_date and ref.threshold_f == threshold_int
    ]
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    # Defensive: prefer the most recently opened market when duplicates exist.
    return max(matches, key=lambda m: m.open_time or _SENTINEL_DT)


def match_brackets(
    brackets: Iterable[Bracket],
    *,
    icao: str,
    valid_date: date,
    kalshi_markets: Iterable[Market],
) -> dict[Bracket, Market | None]:
    """Convenience: parse markets once, then match every bracket in one pass."""
    parsed = parsed_weather_markets(kalshi_markets)
    return {
        bracket: find_matching_market(
            bracket, icao=icao, valid_date=valid_date, weather_markets=parsed
        )
        for bracket in brackets
    }


# Datetime sentinel for the rare duplicate-tickers case; older datetimes lose
# the max() comparison so unset open_times never beat actual values.
from datetime import datetime  # noqa: E402

_SENTINEL_DT = datetime.min
