"""Chronological delayed recognition of already committed paper instructions."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta
from typing import Any

from kq.equities import ledger


def _weekdays(first: date, last: date) -> list[str]:
    return [
        day.isoformat()
        for n in range((last - first).days + 1)
        if (day := first + timedelta(days=n)).weekday() < 5
    ]


def _require_bar(daily: dict[tuple[str, str], dict[str, Any]], symbol: str, day: str) -> None:
    bar = daily.get((symbol, day))
    if not bar:
        raise ValueError(f"missing recovery session for {symbol} {day}; holidays remain unresolved")
    if float(bar["volume"]) <= 0 or any(
        bool(bar.get(flag, False)) for flag in ("interpolated", "synthetic")
    ):
        raise ValueError(f"recovery requires genuine daily bars for {symbol} {day}")


def validate_recovery(
    con: sqlite3.Connection,
    daily: dict[tuple[str, str], dict[str, Any]],
    prior_session: str,
    current_session: str,
    observed_at: datetime,
) -> None:
    """Check complete weekday and held-stock coverage before any book mutation."""
    end = date.fromisoformat(current_session)
    if end >= observed_at.date():
        raise ValueError("recovery requires a completed session before the current UTC date")
    for symbol, day in daily:
        if day > current_session:
            raise ValueError(f"recovery bar for {symbol} {day} is after the benchmark session")
        if day > prior_session and date.fromisoformat(day).weekday() >= 5:
            raise ValueError(f"invalid weekend recovery session for {symbol} {day}")
    for day in _weekdays(date.fromisoformat(prior_session) + timedelta(days=1), end):
        _require_bar(daily, "SPY", day)
    for symbol, entry_day in con.execute(
        "SELECT symbol,entry_date FROM paper_trades WHERE exit_date IS NULL"
    ):
        for day in _weekdays(date.fromisoformat(entry_day), end):
            _require_bar(daily, "SPY", day)
            _require_bar(daily, symbol, day)
    for symbol, created in con.execute(
        "SELECT symbol,created_at FROM paper_orders WHERE status='pending'"
    ):
        for day in _weekdays(datetime.fromisoformat(created).date(), end):
            if ledger._eligible(day, created):
                _require_bar(daily, "SPY", day)
                _require_bar(daily, symbol, day)


def recover_positions(
    con: sqlite3.Connection,
    daily: dict[tuple[str, str], dict[str, Any]],
    sessions: list[str],
    observed_at: datetime,
    snapshot_hash: str,
    holding_sessions: int,
    prior_session: str,
) -> None:
    """Use the existing fill/exit rules, daily risk checks, and one actual observation."""
    previous = json.loads(ledger._state(con, "delayed_recovery", "{}"))
    old_summary = json.loads(ledger._state(con, "last_summary", "{}"))
    peak = max(100.0, previous.get("peak_equity", 100.0), old_summary.get("equity", 100.0))
    minimum = min(previous.get("minimum_equity", 100.0), old_summary.get("equity", 100.0))
    run_minimum = run_peak = float(old_summary.get("equity", 100.0))
    drawdown = float(previous.get("max_drawdown_recovered", 0.0))
    events: list[dict[str, Any]] = []
    for day in sessions:
        before = {
            int(trade_id): exit_day
            for trade_id, exit_day in con.execute("SELECT id,exit_date FROM paper_trades")
        }
        was_paused = bool(ledger._state(con, "pause_reason"))
        available = {key: value for key, value in daily.items() if key[1] <= day}
        ledger._advance_positions(con, available, holding_sessions)
        for trade_id, order_id, symbol, entry_day, exit_day in con.execute(
            "SELECT id,order_id,symbol,entry_date,exit_date FROM paper_trades ORDER BY id"
        ):
            if trade_id not in before:
                events.append(
                    dict(
                        kind="delayed_fill",
                        session=entry_day,
                        order_id=order_id,
                        trade_id=trade_id,
                        symbol=symbol,
                    )
                )
            if exit_day is not None and before.get(trade_id) is None:
                events.append(
                    dict(
                        kind="delayed_exit",
                        session=exit_day,
                        order_id=order_id,
                        trade_id=trade_id,
                        symbol=symbol,
                    )
                )
        summary = ledger._summary(con, available)
        peak = max(peak, summary["equity"])
        minimum = min(minimum, summary["equity"])
        run_peak = max(run_peak, summary["equity"])
        run_minimum = min(run_minimum, summary["equity"])
        drawdown = max(drawdown, 1 - summary["equity"] / peak)
        events.append(dict(kind="delayed_mark", session=day, equity=summary["equity"]))
        if summary["paused"] and not was_paused:
            events.append(dict(kind="loss_pause", session=day, equity=summary["equity"]))
    con.execute("""CREATE TABLE IF NOT EXISTS recovery_runs (
        snapshot_hash TEXT PRIMARY KEY, observed_at TEXT NOT NULL,
        prior_session TEXT NOT NULL, current_session TEXT NOT NULL,
        sessions TEXT NOT NULL, events TEXT NOT NULL
    )""")
    con.execute(
        "INSERT INTO recovery_runs VALUES(?,?,?,?,?,?)",
        (
            snapshot_hash,
            observed_at.isoformat(),
            prior_session,
            sessions[-1],
            json.dumps(sessions),
            json.dumps(events, sort_keys=True),
        ),
    )
    evidence = dict(
        prior_session=previous.get("prior_session", prior_session),
        through_session=sessions[-1],
        recognized_at=observed_at.isoformat(),
        missed_sessions_count=previous.get("missed_sessions_count", 0) + len(sessions),
        run_count=previous.get("run_count", 0) + 1,
        peak_equity=peak,
        minimum_equity=minimum,
        last_run_peak_equity=run_peak,
        last_run_minimum_equity=run_minimum,
        max_drawdown_recovered=drawdown,
        fill_count=previous.get("fill_count", 0) + sum(e["kind"] == "delayed_fill" for e in events),
        exit_count=previous.get("exit_count", 0) + sum(e["kind"] == "delayed_exit" for e in events),
    )
    ledger._set(con, "delayed_recovery", json.dumps(evidence, sort_keys=True))
