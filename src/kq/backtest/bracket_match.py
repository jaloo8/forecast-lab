"""Match live Kalshi weather markets to tradeable, strike-typed contracts.

Backtest uses synthetic brackets directly. The paper executor consumes the
*live book*: every open market that parses as a weather contract AND carries
usable resolution semantics (``strike_type``/``floor_strike``/``cap_strike``
from the API — see ``kq.clients.kalshi.strikes``).

PR-B (2026-07-01) replaced the PR-A interim guard (greater-only) with the
full strike-aware path: greater, less, AND between markets are all
admitted, each paired with its authoritative :class:`Strike`. Markets whose
API strike fields disagree with the ticker text are still refused — never
guess semantics.

``find_matching_market`` / ``match_brackets`` remain for callers that think
in synthetic integer-threshold brackets (tests, diagnostics); they operate
on the greater-markets subset only, preserving their historical contract.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime

from kq.backtest.brackets import Bracket
from kq.clients.kalshi import Market
from kq.clients.kalshi._ticker_parser import (
    WeatherMarketRef,
    parse_weather_market_ticker,
)
from kq.clients.kalshi.strikes import Strike, strike_from_market


def parsed_weather_markets(
    markets: Iterable[Market],
) -> list[tuple[Market, WeatherMarketRef, Strike]]:
    """Return every market that parses as a weather contract AND yields an
    authoritative :class:`Strike` (API strike fields, cross-checked against
    the ticker; legacy ``-T`` tickers without API fields fall back to
    *greater* semantics — the pre-prod interpretation).

    Markets are dropped (never guessed at) when the ticker doesn't parse,
    the strike fields are missing/inconsistent, or ticker text disagrees
    with the API semantics.
    """
    out: list[tuple[Market, WeatherMarketRef, Strike]] = []
    for m in markets:
        ref = parse_weather_market_ticker(m.ticker)
        if ref is None:
            continue
        strike = strike_from_market(m, ref)
        if strike is None:
            continue
        out.append((m, ref, strike))
    return out


def find_matching_market(
    bracket: Bracket,
    *,
    icao: str,
    valid_date: date,
    weather_markets: Sequence[tuple[Market, WeatherMarketRef, Strike]],
) -> Market | None:
    """Find the *greater* Kalshi market for an integer-threshold bracket.

    Kept for synthetic-bracket callers. Only ``greater`` strikes are
    eligible — a bracket models P(T > threshold), which is meaningless
    against less/between contracts. Returns the most-recently-opened match
    if duplicates exist (shouldn't happen), else None.
    """
    threshold_int = round(bracket.threshold_f)
    matches = [
        market
        for market, ref, strike in weather_markets
        if strike.kind == "greater"
        and ref.icao == icao
        and ref.valid_date == valid_date
        and ref.threshold_f == threshold_int
    ]
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    # Defensive: prefer the most recently opened market when duplicates exist.
    return max(matches, key=_open_time_key)


def _open_time_key(m: Market) -> datetime:
    """Sort key tolerant of missing AND mixed naive/aware open_times.

    Comparing naive ``datetime.min`` against tz-aware values raises
    TypeError (the pre-PR-B tiebreak had that latent crash), so normalize
    everything to naive UTC; None sorts first.
    """
    t = m.open_time
    if t is None:
        return datetime.min
    if t.tzinfo is not None:
        return t.astimezone(UTC).replace(tzinfo=None)
    return t


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
