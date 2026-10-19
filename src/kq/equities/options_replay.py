"""Offline causal CMBP observations for the unchanged one-spread kernel."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

import pandas as pd

from kq.equities.option_spread import CallQuote, spread_cashflow

QuotePair = tuple[CallQuote, CallQuote]
Observation = QuotePair | str


@dataclass(frozen=True)
class ReplayResult:
    status: Literal["skipped_entry", "unresolved_exit", "closed"]
    reason: str | None = None
    entry_debit: float | None = None
    exit_cash: float | None = None
    net_cash: float | None = None


def _time(value: pd.Timestamp) -> pd.Timestamp:
    value = pd.Timestamp(value)
    if pd.isna(value) or value.tzinfo is None:
        raise ValueError("Explicit timezone-aware timestamp required")
    return value.tz_convert("UTC")


def _latest(
    path: Path,
    symbols: tuple[str, str],
    times: tuple[pd.Timestamp, ...],
    chunksize: int,
    *,
    definitions: bool = False,
) -> dict[pd.Timestamp, dict[str, pd.Series]]:
    symbol = "raw_symbol" if definitions else "symbol"
    fields = (
        "expiration strike_price instrument_class underlying security_update_action "
        "contract_multiplier"
        if definitions
        else "action flags bid_px_00 ask_px_00 bid_sz_00 ask_sz_00"
    )
    columns = ["ts_recv", "ts_event", "instrument_id", symbol, *fields.split()]
    result: dict[pd.Timestamp, dict[str, pd.Series]] = {t: {} for t in times}
    for frame in pd.read_csv(path, usecols=columns, dtype=str, chunksize=chunksize):
        chunk = frame.loc[frame[symbol].isin(symbols)].copy()
        if not definitions:
            chunk = chunk.loc[chunk.action.isin(["A", "M", "C", "R"])].copy()
        for field in ("ts_recv", "ts_event"):
            chunk[field] = pd.to_datetime(chunk[field], utc=True, format="ISO8601", errors="raise")
            if chunk[field].isna().any():
                raise ValueError("Missing evidence timestamp")
        for at in times:
            eligible = chunk.ts_recv <= at
            if definitions:
                eligible &= (
                    chunk.ts_recv.dt.tz_convert("America/New_York").dt.date
                    == at.tz_convert("America/New_York").date()
                )
            latest = (
                chunk.loc[eligible].sort_values("ts_recv", kind="stable").groupby(symbol).tail(1)
            )
            for _, row in latest.iterrows():
                old = result[at].get(row[symbol])
                if old is None or row.ts_recv >= old.ts_recv:
                    result[at][row[symbol]] = row
    return result


def _quote(
    definition: pd.Series,
    row: pd.Series,
    symbol: str,
    confirmed: bool,
    signal_at: pd.Timestamp,
    at: pd.Timestamp,
) -> CallQuote:
    if definition.ts_event > signal_at or row.ts_event > at:
        raise ValueError("Latest evidence has a future event timestamp")
    occ = re.fullmatch(r"SPY   (\d{6})C(\d{8})", symbol)
    if (
        occ is None
        or definition.instrument_class != "C"
        or definition.underlying != "SPY"
        or definition.security_update_action not in {"A", "M"}
    ):
        raise ValueError("Invalid standard SPY call definition")
    expiry = pd.Timestamp(definition.expiration).date()
    strike = float(definition.strike_price)
    if (
        expiry != datetime.strptime(occ[1], "%y%m%d").date()
        or strike != int(occ[2]) / 1000
        or int(row.instrument_id) != int(definition.instrument_id)
    ):
        raise ValueError("Mismatched definition expiry/strike/instrument_id")
    multiplier = int(definition.contract_multiplier)
    if multiplier != 100 and not (multiplier == 2147483647 and confirmed is True):
        raise ValueError("Undefined/nonstandard multiplier: confirm standard SPY 100 mapping")
    if int(row["flags"]) & ~(128 | 64 | 32) or row.action == "R":
        raise ValueError("Latest book has data-quality flags or book clear")
    bid, ask = float(row.bid_px_00), float(row.ask_px_00)
    bid_size, ask_size = int(row.bid_sz_00), int(row.ask_sz_00)
    return CallQuote("SPY", expiry, strike, row.ts_recv, bid, ask, bid_size, ask_size)


def _pair(observation: Observation, at: pd.Timestamp) -> QuotePair:
    if isinstance(observation, str):
        raise ValueError(observation)
    for quote in observation:
        if not pd.Timedelta(0) <= at - _time(quote.as_of) <= pd.Timedelta(seconds=5):
            raise ValueError("Stale or future quote (nanosecond age)")
        quote.validate(at)
    if abs(observation[0].as_of - observation[1].as_of) > pd.Timedelta(seconds=1):
        raise ValueError("Unsynchronized legs (nanosecond age)")
    return observation


def read_call_quotes(
    definitions_path: Path,
    quotes_path: Path,
    symbols: tuple[str, str],
    signal_at: pd.Timestamp,
    decision_times: tuple[pd.Timestamp, ...],
    *,
    confirm_standard_spy_100: bool = False,
    chunksize: int = 100_000,
) -> dict[pd.Timestamp, Observation]:
    """Chunked latest A/M/C/R by receive time; invalid latest records never fall back.

    Symbols are ordered long/short OCC calls. Definitions must be known by the signal
    on its New York date. Both event and receive timestamps must be causal.
    Expiration is an encoded calendar date. Sentinel multipliers need confirmation.
    Return each UTC decision's quote pair or descriptive refusal; no I/O fallback.
    """
    signal_at = _time(signal_at)
    times = tuple(_time(t) for t in decision_times)
    if len(symbols) != 2 or len(set(symbols)) != 2 or chunksize < 1:
        raise ValueError("Two distinct ordered symbols and positive chunksize required")
    try:
        definitions = _latest(definitions_path, symbols, (signal_at,), chunksize, definitions=True)[
            signal_at
        ]
        quotes = _latest(quotes_path, symbols, times, chunksize)
    except (ValueError, OSError) as exc:
        return {t: f"Unreadable evidence: {exc}" for t in times}
    result: dict[pd.Timestamp, Observation] = {}
    for at in times:
        try:
            pair = tuple(
                _quote(definitions[s], quotes[at][s], s, confirm_standard_spy_100, signal_at, at)
                for s in symbols
            )
            result[at] = _pair((pair[0], pair[1]), at)
        except (ValueError, KeyError) as exc:
            result[at] = f"Quote/definition refused: {exc}"
    return result


def replay_trade(
    observations: Mapping[pd.Timestamp, Observation],
    *,
    signal_at: pd.Timestamp,
    entry_at: pd.Timestamp,
    exit_at: pd.Timestamp,
    cash_limit: float = 100,
) -> ReplayResult:
    """One spread; retain entry debit on unresolved exits, never invent exit/net cash."""
    signal_at, entry_at, exit_at = map(_time, (signal_at, entry_at, exit_at))
    try:
        if not signal_at < entry_at < exit_at:
            raise ValueError("Require signal < entry < exit")
        entry = _pair(observations.get(entry_at, "Missing entry"), entry_at)
        debit = -spread_cashflow(
            *entry, entry_at, entering=True, signal_at=signal_at, cash_limit=cash_limit
        )
    except ValueError as exc:
        return ReplayResult("skipped_entry", str(exc))
    try:
        closing = _pair(observations.get(exit_at, "Missing exit"), exit_at)
        if any(
            (a.symbol, a.expiry, a.strike, a.multiplier)
            != (b.symbol, b.expiry, b.strike, b.multiplier)
            for a, b in zip(entry, closing, strict=True)
        ):
            raise ValueError("Exit changed contract identity")
        cash = spread_cashflow(*closing, exit_at, entering=False)
    except ValueError as exc:
        return ReplayResult("unresolved_exit", str(exc), debit)
    return ReplayResult("closed", entry_debit=debit, exit_cash=cash, net_cash=cash - debit)
