"""Append-only forward forecasts and a $100 virtual long-only paper book.

Daily bars are completed regular sessions. A session's New York open must be
strictly later than a forecast/order timestamp before an entry can occur.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

_COST = 0.001
_NOTIONAL = 10.0
_CAPITAL = 100.0
_MARKET_TZ = ZoneInfo("America/New_York")
_RESEARCH_NUMBERS = (
    "close",
    "benchmark_close",
    "momentum",
    "benchmark_momentum",
    "excess_momentum",
    "volatility_20d",
    "pe_ratio",
    "market_cap",
    "latest_eps_actual",
    "latest_eps_estimate",
    "news_count",
)


def _utc(value: Any) -> datetime:
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _day(value: Any) -> date:
    if isinstance(value, datetime):
        raise ValueError("session_date must be a date")
    if not isinstance(value, date):
        raise ValueError("session_date must be a date")
    return value


def _number(value: Any, *, positive: bool = False) -> float:
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0):
        raise ValueError("numeric input must be finite and valid")
    return result


def _inputs(  # noqa: PLR0912
    research: pd.DataFrame, bars: pd.DataFrame, as_of: datetime
) -> tuple[list[dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
    required_research = {
        "symbol",
        "horizon_sessions",
        "as_of",
        "session_date",
        "excess_momentum",
        "status",
    }
    required_bars = {"symbol", "session_date", "open", "close", "volume", "as_of"}
    if not required_research.issubset(research.columns) or not required_bars.issubset(bars.columns):
        raise ValueError("missing research or daily-bar columns")
    rows: list[dict[str, Any]] = []
    for raw in research.to_dict("records"):
        row = dict(raw)
        row["as_of"] = _utc(row["as_of"])
        row["session_date"] = _day(row["session_date"])
        if row["as_of"] > as_of or row["session_date"] > as_of.date():
            raise ValueError("future research observation")
        if not isinstance(row["symbol"], str) or not row["symbol"].isupper() or not row["symbol"]:
            raise ValueError("invalid symbol")
        if int(row["horizon_sessions"]) not in (5, 20, 126):
            raise ValueError("invalid forecast horizon")
        for column in _RESEARCH_NUMBERS:
            if column in row and not pd.isna(row[column]):
                row[column] = _number(
                    row[column], positive=column in ("close", "benchmark_close", "market_cap")
                )
        row["excess_momentum"] = _number(row["excess_momentum"])
        rows.append(row)
    daily: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in bars.to_dict("records"):
        bar = dict(raw)
        bar["as_of"] = _utc(bar["as_of"])
        day = _day(bar["session_date"])
        if bar["as_of"] > as_of or day > as_of.date():
            raise ValueError("future daily bar")
        for column in ("open", "close"):
            bar[column] = _number(bar[column], positive=True)
        bar["volume"] = _number(bar["volume"])
        if bar["volume"] < 0:
            raise ValueError("negative volume")
        symbol = bar["symbol"]
        if not isinstance(symbol, str) or not symbol.isupper() or not symbol:
            raise ValueError("invalid symbol")
        key = (symbol, day.isoformat())
        if key in daily and (daily[key]["open"], daily[key]["close"]) != (
            bar["open"],
            bar["close"],
        ):
            raise ValueError("conflicting bars in one snapshot")
        daily[key] = bar
    return rows, daily


def _schema(con: sqlite3.Connection) -> None:
    con.executescript("""
        CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS forecasts (
            symbol TEXT NOT NULL, horizon INTEGER NOT NULL, source_as_of TEXT NOT NULL,
            created_at TEXT NOT NULL,
            snapshot_hash TEXT NOT NULL, score REAL NOT NULL, payload TEXT NOT NULL,
            entry_date TEXT, exit_date TEXT, stock_return REAL, benchmark_return REAL,
            PRIMARY KEY(symbol,horizon,source_as_of)
        );
        CREATE TABLE IF NOT EXISTS snapshots (
            source_as_of TEXT PRIMARY KEY, snapshot_hash TEXT NOT NULL,
            fingerprint TEXT NOT NULL, imported_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS paper_orders (
            id INTEGER PRIMARY KEY, symbol TEXT NOT NULL, created_at TEXT NOT NULL,
            snapshot_hash TEXT NOT NULL, status TEXT NOT NULL, reserved REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS paper_trades (
            id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL UNIQUE, symbol TEXT NOT NULL,
            entry_date TEXT NOT NULL, entry_open REAL NOT NULL, shares REAL NOT NULL,
            entry_cost REAL NOT NULL, exit_date TEXT, exit_close REAL, proceeds REAL,
            net_pnl REAL, FOREIGN KEY(order_id) REFERENCES paper_orders(id)
        );
        CREATE TABLE IF NOT EXISTS bar_anchors (
            symbol TEXT NOT NULL, session_date TEXT NOT NULL, open REAL NOT NULL,
            close REAL NOT NULL, PRIMARY KEY(symbol,session_date)
        );
        CREATE TABLE IF NOT EXISTS capture_coverage (
            symbol TEXT NOT NULL, session_date TEXT NOT NULL,
            PRIMARY KEY(symbol,session_date)
        );
    """)


def _state(con: sqlite3.Connection, key: str, default: str = "") -> str:
    row = con.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
    return str(row[0]) if row else default


def _set(con: sqlite3.Connection, key: str, value: str) -> None:
    con.execute(
        "INSERT INTO state(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def _common(symbol: str, daily: dict[tuple[str, str], dict[str, Any]], after: str) -> list[str]:
    return sorted(
        day for stock, day in daily if stock == symbol and day > after and ("SPY", day) in daily
    )


def _eligible(day: str, created: str) -> bool:
    opened = datetime.combine(date.fromisoformat(day), time(9, 30), _MARKET_TZ)
    return opened.astimezone(UTC) > datetime.fromisoformat(created)


def _horizon(
    symbol: str,
    daily: dict[tuple[str, str], dict[str, Any]],
    first: str,
    length: int,
) -> list[str]:
    spy = sorted(day for ticker, day in daily if ticker == "SPY" and day >= first)
    selected = spy[:length]
    if ("SPY", first) not in daily or (symbol, first) not in daily:
        return []
    if len(selected) != length or any((symbol, day) not in daily for day in selected):
        return []
    return selected


def _anchor(con: sqlite3.Connection, symbol: str, day: str, bar: dict[str, Any]) -> None:
    con.execute(
        "INSERT OR IGNORE INTO bar_anchors VALUES(?,?,?,?)",
        (symbol, day, bar["open"], bar["close"]),
    )


def _check_coverage(
    con: sqlite3.Connection,
    daily: dict[tuple[str, str], dict[str, Any]],
) -> None:
    previous = set(con.execute("SELECT symbol,session_date FROM capture_coverage"))
    if previous:
        if previous - daily.keys():
            raise ValueError("truncated daily-bar coverage; prior sessions disappeared")
        return
    if not con.execute("SELECT 1 FROM snapshots LIMIT 1").fetchone():
        return
    for symbol, payload in con.execute("SELECT symbol,payload FROM forecasts"):
        day = str(json.loads(payload)["session_date"])
        if (symbol, day) not in daily or ("SPY", day) not in daily:
            raise ValueError("truncated daily-bar coverage for existing ledger")


def _last_session(con: sqlite3.Connection) -> str:
    stored = _state(con, "last_processed_session")
    if stored:
        return stored
    days = [
        str(json.loads(payload)["session_date"])
        for (payload,) in con.execute("SELECT payload FROM forecasts")
    ]
    return max(days, default="")


def _summary(
    con: sqlite3.Connection,
    daily: dict[tuple[str, str], dict[str, Any]],
    *,
    equity_valid: bool = True,
    record_pause: bool = True,
) -> dict[str, Any]:
    cash = float(_state(con, "cash", "100"))
    reserved = float(
        con.execute(
            "SELECT COALESCE(SUM(reserved),0) FROM paper_orders WHERE status='pending'"
        ).fetchone()[0]
    )
    open_rows = con.execute(
        "SELECT symbol,entry_date,shares,entry_open FROM paper_trades WHERE exit_date IS NULL"
    ).fetchall()
    equity = cash
    for symbol, entry_day, shares, entry_open in open_rows:
        prices = [
            (day, bar["close"])
            for (s, day), bar in daily.items()
            if s == symbol and day >= entry_day
        ]
        previous = con.execute(
            "SELECT close FROM bar_anchors WHERE symbol=? AND session_date>=? "
            "ORDER BY session_date DESC LIMIT 1",
            (symbol, entry_day),
        ).fetchone()
        mark = max(prices)[1] if prices else previous[0] if previous else entry_open
        equity += float(shares) * float(mark) * (1 - _COST)
    closed = con.execute(
        "SELECT symbol,entry_date,exit_date,net_pnl FROM paper_trades "
        "WHERE exit_date IS NOT NULL ORDER BY id"
    ).fetchall()
    grades = {
        int(h): (int(n), float(stock), float(benchmark), float(excess))
        for h, n, stock, benchmark, excess in con.execute(
            "SELECT horizon,count(*),avg(stock_return),avg(benchmark_return),"
            "avg(stock_return-benchmark_return) FROM forecasts "
            "WHERE exit_date IS NOT NULL GROUP BY horizon"
        )
    }
    latest_spy = max((day for symbol, day in daily if symbol == "SPY"), default=None)
    stale_symbols = sorted(
        {
            symbol
            for symbol, _, _, _ in open_rows
            if not latest_spy or (symbol, latest_spy) not in daily
        }
    )
    reason = _state(con, "pause_reason")
    equity_valid = equity_valid and not reason.startswith("history revision")
    if equity <= _CAPITAL - 10 and not reason and record_pause:
        reason = "marked equity fell $10 from initial capital"
        _set(con, "pause_reason", reason)
    return {
        "cash": round(cash, 6),
        "reserved_cash": round(reserved, 6),
        "equity": round(equity, 6),
        "equity_valid": equity_valid,
        "forecast_valid": not reason.startswith("history revision"),
        "pnl": round(equity - _CAPITAL, 6),
        "pending_count": int(
            con.execute("SELECT count(*) FROM paper_orders WHERE status='pending'").fetchone()[0]
        ),
        "open_count": len(open_rows),
        "closed_count": len(closed),
        "paused": bool(reason),
        "pause_reason": reason,
        "forecast_settled_count": int(
            con.execute("SELECT count(*) FROM forecasts WHERE exit_date IS NOT NULL").fetchone()[0]
        ),
        "closed_trades": [
            dict(symbol=s, entry_date=e, exit_date=x, net_pnl=round(float(p), 6))
            for s, e, x, p in closed
        ],
        "forecast_by_horizon": [
            {
                "horizon_sessions": h,
                "count": grades[h][0] if h in grades else 0,
                "mean_stock_return": round(grades[h][1], 6) if h in grades else None,
                "mean_benchmark_return": round(grades[h][2], 6) if h in grades else None,
                "mean_excess_return": round(grades[h][3], 6) if h in grades else None,
            }
            for h in (5, 20, 126)
        ],
        "stale_symbols": stale_symbols,
    }


def update_ledger(  # noqa: PLR0912, PLR0915
    path: Path,
    research: pd.DataFrame,
    bars: pd.DataFrame,
    *,
    snapshot_hash: str,
    as_of: datetime,
) -> dict[str, Any]:
    """Record forecasts and update prospective virtual fills from completed daily bars.

    Returns JSON-serializable cash/reservation/equity/P&L, position counts,
    pause reason, settled-forecast count and closed trade summaries.
    Active books reject multi-session catch-up, which cannot preserve fill order.
    """
    now = _utc(as_of)
    if not snapshot_hash or not isinstance(snapshot_hash, str):
        raise ValueError("snapshot hash required")
    rows, daily = _inputs(research, bars, now)
    source_times = {row["as_of"].isoformat() for row in rows}
    if len(source_times) > 1:
        raise ValueError("mixed research capture times")
    if source_times:
        source_as_of = next(iter(source_times))
    elif daily:
        source_as_of = max(bar["as_of"] for bar in daily.values()).isoformat()
    else:
        raise ValueError("empty snapshot")
    fingerprint = hashlib.sha256(
        json.dumps(
            [rows, [(symbol, day, bar) for (symbol, day), bar in sorted(daily.items())]],
            default=str,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as con:
        _schema(con)
        con.execute("BEGIN IMMEDIATE")
        last = _state(con, "last_as_of")
        if last and now.isoformat() < last:
            raise ValueError("older snapshot cannot mutate ledger")
        prior = con.execute(
            "SELECT snapshot_hash,fingerprint FROM snapshots WHERE source_as_of=?",
            (source_as_of,),
        ).fetchone()
        if prior:
            if prior != (snapshot_hash, fingerprint):
                raise ValueError("conflicting immutable snapshot replay")
            cached = _state(con, "last_summary")
            if cached:
                return dict(json.loads(cached))
            latest_source = _state(con, "last_source_as_of")
            return _summary(con, daily if source_as_of == latest_source else {}, record_pause=False)
        latest_source = _state(con, "last_source_as_of")
        if latest_source and source_as_of < latest_source:
            raise ValueError("older source snapshot cannot mutate ledger")
        if last == now.isoformat() and _state(con, "last_hash") != snapshot_hash:
            raise ValueError("conflicting snapshot replay")
        _check_coverage(con, daily)
        previous_session = _last_session(con)
        new_sessions = sorted(
            day for symbol, day in daily if symbol == "SPY" and day > previous_session
        )
        active = (
            con.execute("SELECT 1 FROM paper_orders WHERE status='pending' LIMIT 1").fetchone()
            or con.execute("SELECT 1 FROM paper_trades WHERE exit_date IS NULL LIMIT 1").fetchone()
        )
        if active and len(new_sessions) > 1:
            raise ValueError("active paper book cannot catch up multiple sessions; review required")

        for symbol, day, old_open, old_close in con.execute(
            "SELECT symbol,session_date,open,close FROM bar_anchors"
        ):
            bar = daily.get((symbol, day))
            if bar and (bar["open"], bar["close"]) != (old_open, old_close):
                _set(
                    con, "pause_reason", f"history revision for {symbol} {day}; comparison invalid"
                )
                _set(con, "last_as_of", now.isoformat())
                _set(con, "last_hash", snapshot_hash)
                _set(con, "last_source_as_of", source_as_of)
                con.execute(
                    "INSERT INTO snapshots VALUES(?,?,?,?)",
                    (source_as_of, snapshot_hash, fingerprint, now.isoformat()),
                )
                result = _summary(con, {}, equity_valid=False)
                _set(con, "last_summary", json.dumps(result))
                con.commit()
                return result

        con.executemany("INSERT OR IGNORE INTO capture_coverage VALUES(?,?)", daily.keys())

        con.execute(
            "INSERT INTO snapshots VALUES(?,?,?,?)",
            (source_as_of, snapshot_hash, fingerprint, now.isoformat()),
        )
        for row in rows:
            payload = json.dumps(
                {
                    k: v.isoformat()
                    if isinstance(v, (date, datetime))
                    else None
                    if pd.isna(v)
                    else v
                    for k, v in row.items()
                },
                sort_keys=True,
            )
            con.execute(
                "INSERT INTO forecasts(symbol,horizon,source_as_of,created_at,"
                "snapshot_hash,score,payload) VALUES(?,?,?,?,?,?,?)",
                (
                    row["symbol"],
                    int(row["horizon_sessions"]),
                    source_as_of,
                    now.isoformat(),
                    snapshot_hash,
                    row["excess_momentum"],
                    payload,
                ),
            )

        if not _state(con, "pause_reason"):
            for order_id, symbol, created in con.execute(
                "SELECT id,symbol,created_at FROM paper_orders WHERE status='pending' ORDER BY id"
            ).fetchall():
                sessions = [day for day in _common(symbol, daily, "") if _eligible(day, created)]
                if not sessions:
                    continue
                day = sessions[0]
                open_price = float(daily[(symbol, day)]["open"])
                shares = _NOTIONAL / (open_price * (1 + _COST))
                cash = float(_state(con, "cash", "100"))
                if cash < _NOTIONAL:
                    continue
                _set(con, "cash", str(cash - _NOTIONAL))
                con.execute(
                    "UPDATE paper_orders SET status='filled',reserved=0 WHERE id=?", (order_id,)
                )
                con.execute(
                    "INSERT INTO paper_trades(order_id,symbol,entry_date,entry_open,"
                    "shares,entry_cost) "
                    "VALUES(?,?,?,?,?,?)",
                    (order_id, symbol, day, open_price, shares, _NOTIONAL),
                )
                _anchor(con, symbol, day, daily[(symbol, day)])
                _anchor(con, "SPY", day, daily[("SPY", day)])

        for trade_id, symbol, entry_day, shares in con.execute(
            "SELECT id,symbol,entry_date,shares FROM paper_trades WHERE exit_date IS NULL"
        ).fetchall():
            sessions = [day for day in _common(symbol, daily, "") if day >= entry_day]
            for day in sessions:
                _anchor(con, symbol, day, daily[(symbol, day)])
                _anchor(con, "SPY", day, daily[("SPY", day)])
            complete = _horizon(symbol, daily, entry_day, 20)
            if complete and not _state(con, "pause_reason").startswith("history revision"):
                day = complete[-1]
                close = float(daily[(symbol, day)]["close"])
                proceeds = float(shares) * close * (1 - _COST)
                con.execute(
                    "UPDATE paper_trades SET exit_date=?,exit_close=?,proceeds=?,net_pnl=? "
                    "WHERE id=?",
                    (day, close, proceeds, proceeds - _NOTIONAL, trade_id),
                )
                _set(con, "cash", str(float(_state(con, "cash")) + proceeds))

        for symbol, horizon, source, created, entry_day in con.execute(
            "SELECT symbol,horizon,source_as_of,created_at,entry_date FROM forecasts "
            "WHERE exit_date IS NULL"
        ).fetchall():
            first_day = entry_day
            if first_day is None:
                eligible = [day for day in _common(symbol, daily, "") if _eligible(day, created)]
                if not eligible:
                    continue
                first_day = eligible[0]
                con.execute(
                    "UPDATE forecasts SET entry_date=? WHERE symbol=? AND horizon=? "
                    "AND source_as_of=?",
                    (first_day, symbol, horizon, source),
                )
            for day in _common(symbol, daily, ""):
                if day < first_day:
                    continue
                _anchor(con, symbol, day, daily[(symbol, day)])
                _anchor(con, "SPY", day, daily[("SPY", day)])
            sessions = _horizon(symbol, daily, first_day, horizon)
            if not sessions:
                continue
            first, last_day = sessions[0], sessions[horizon - 1]
            stock_ret = daily[(symbol, last_day)]["close"] / daily[(symbol, first)]["open"] - 1
            spy_ret = daily[("SPY", last_day)]["close"] / daily[("SPY", first)]["open"] - 1
            con.execute(
                "UPDATE forecasts SET entry_date=?,exit_date=?,stock_return=?,benchmark_return=? "
                "WHERE symbol=? AND horizon=? AND source_as_of=?",
                (first, last_day, stock_ret, spy_ret, symbol, horizon, source),
            )

        result = _summary(con, daily)
        if not result["paused"]:
            active = result["pending_count"] + result["open_count"]
            available = result["cash"] - result["reserved_cash"]
            candidates = sorted(
                (
                    r
                    for r in rows
                    if r["horizon_sessions"] == 20
                    and r["as_of"].isoformat() == source_as_of
                    and r["symbol"] != "SPY"
                    and r["excess_momentum"] > 0
                    and r["status"] == "ranked"
                ),
                key=lambda r: (-r["excess_momentum"], r["symbol"]),
            )
            for row in candidates:
                if active >= 5 or available < _NOTIONAL:
                    break
                symbol = row["symbol"]
                if (
                    con.execute(
                        "SELECT 1 FROM paper_orders WHERE symbol=? AND status='pending'", (symbol,)
                    ).fetchone()
                    or con.execute(
                        "SELECT 1 FROM paper_trades WHERE symbol=? AND exit_date IS NULL", (symbol,)
                    ).fetchone()
                ):
                    continue
                con.execute(
                    "INSERT INTO paper_orders(symbol,created_at,snapshot_hash,status,reserved) "
                    "VALUES(?,?,?,?,?)",
                    (symbol, now.isoformat(), snapshot_hash, "pending", _NOTIONAL),
                )
                active += 1
                available -= _NOTIONAL
            result = _summary(con, daily)
        _set(con, "last_as_of", now.isoformat())
        _set(con, "last_hash", snapshot_hash)
        _set(con, "last_source_as_of", source_as_of)
        latest_day = max((day for symbol, day in daily if symbol == "SPY"), default="")
        _set(con, "last_processed_session", max(previous_session, latest_day))
        _set(con, "last_summary", json.dumps(result))
        con.commit()
        return result
