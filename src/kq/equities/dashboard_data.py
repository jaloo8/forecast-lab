"""Read-only, point-in-time view of the local stock paper experiment."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

import pandas as pd

from kq.backtest.metrics import hit_rate


def _legacy_summary(
    state: dict[str, str],
    orders: pd.DataFrame,
    trades: pd.DataFrame,
    forecasts: pd.DataFrame,
) -> dict[str, Any]:
    pending = orders[orders["status"] == "pending"]
    opened = trades[trades["exit_date"].isna()]
    closed = trades[trades["exit_date"].notna()]
    reserved = float(pending["reserved"].sum())
    no_executions = trades.empty and len(pending) == len(orders)
    cash: float | None
    if "cash" in state:
        cash = float(state["cash"])
        if not math.isfinite(cash) or cash < 0:
            raise ValueError("malformed ledger state: cash")
    elif no_executions:
        cash = 100.0
    else:
        cash = None
    reason = state.get("pause_reason", "")
    valid = cash is not None and opened.empty and not reason.startswith("history revision")
    settled = forecasts[forecasts["exit_date"].notna()]
    grades: list[dict[str, Any]] = []
    for horizon in (5, 20, 126):
        group = settled[settled["horizon"] == horizon]
        stock = group["stock_return"].astype(float)
        benchmark = group["benchmark_return"].astype(float)
        grades.append(
            {
                "horizon_sessions": horizon,
                "count": len(group),
                "mean_stock_return": float(stock.mean()) if len(group) else None,
                "mean_benchmark_return": float(benchmark.mean()) if len(group) else None,
                "mean_excess_return": float((stock - benchmark).mean()) if len(group) else None,
            }
        )
    return {
        "cash": cash,
        "reserved_cash": reserved,
        "equity": cash if valid else None,
        "pnl": cash - 100.0 if valid and cash is not None else None,
        "equity_valid": valid,
        "forecast_valid": not reason.startswith("history revision"),
        "pending_count": len(pending),
        "open_count": len(opened),
        "closed_count": len(closed),
        "paused": bool(reason),
        "pause_reason": reason,
        "forecast_settled_count": int(forecasts["exit_date"].notna().sum()),
        "closed_trades": closed[["symbol", "entry_date", "exit_date", "net_pnl"]].to_dict(
            "records"
        ),
        "stale_symbols": sorted(opened["symbol"].unique().tolist()),
        "forecast_by_horizon": grades,
    }


def _matched_source(data_dir: Path, digest: str) -> tuple[dict[str, Any] | None, str]:
    matched: dict[str, Any] | None = None
    ignored = 0
    for path in sorted(data_dir.glob("snapshot*.json")):
        try:
            candidate = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(candidate, dict):
                raise ValueError("source capture must be an object")
            canonical = json.dumps(
                candidate, sort_keys=True, separators=(",", ":"), allow_nan=False
            )
            if hashlib.sha256(canonical.encode()).hexdigest() == digest:
                matched = candidate
            else:
                ignored += 1
        except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
            ignored += 1
    warning = (
        "" if matched is not None else "No local source capture matches committed snapshot hash."
    )
    if ignored:
        warning += f" Ignored {ignored} other or unreadable capture(s)."
    return matched, warning.strip()


def load_dashboard(data_dir: Path) -> dict[str, Any]:
    """Load one SQLite read transaction; never create or update the ledger."""
    ledger = data_dir / "paper.sqlite"
    if not ledger.is_file():
        raise FileNotFoundError(f"Stock paper ledger missing: {ledger}")
    uri = ledger.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as con:
        con.execute("PRAGMA query_only=ON")
        con.execute("BEGIN")
        try:
            state = dict(con.execute("SELECT key,value FROM state"))
            digest = state.get("last_hash")
            if not digest or len(digest) != 64:
                raise ValueError("malformed ledger state: last_hash")
            row = con.execute(
                "SELECT source_as_of,snapshot_hash,imported_at FROM snapshots "
                "WHERE snapshot_hash=? ORDER BY imported_at DESC LIMIT 1",
                (digest,),
            ).fetchone()
            if row is None:
                raise ValueError("malformed ledger state: latest committed snapshot missing")
            latest = dict(zip(("source_as_of", "snapshot_hash", "imported_at"), row, strict=True))
            if state.get("last_source_as_of") != latest["source_as_of"]:
                raise ValueError("malformed ledger state: last_source_as_of")
            orders = pd.read_sql_query("SELECT * FROM paper_orders ORDER BY id", con)
            trades = pd.read_sql_query("SELECT * FROM paper_trades ORDER BY id", con)
            forecasts = pd.read_sql_query(
                "SELECT * FROM forecasts ORDER BY created_at,symbol,horizon", con
            )
            raw_summary = state.get("last_summary")
            if raw_summary is not None:
                try:
                    summary = json.loads(raw_summary)
                except (ValueError, TypeError) as exc:
                    raise ValueError("malformed ledger state: last_summary") from exc
                if not isinstance(summary, dict) or not {
                    "cash",
                    "reserved_cash",
                    "pnl",
                    "pending_count",
                    "open_count",
                    "closed_count",
                    "forecast_by_horizon",
                }.issubset(summary):
                    raise ValueError("malformed ledger state: last_summary")
                legacy_warning = ""
            else:
                summary = _legacy_summary(state, orders, trades, forecasts)
                legacy_warning = "Reconstructed legacy summary from immutable paper records."
        finally:
            con.execute("ROLLBACK")
    source, source_warning = _matched_source(data_dir, digest)
    warning = " ".join(part for part in (source_warning, legacy_warning) if part)
    closed_pnl = trades.loc[trades["exit_date"].notna(), "net_pnl"].astype(float).tolist()
    return {
        "summary": summary,
        "state": state,
        "orders": orders,
        "trades": trades,
        "forecasts": forecasts,
        "latest_snapshot": latest,
        "source": source,
        "source_warning": warning,
        "win_rate": hit_rate(closed_pnl) if closed_pnl else None,
    }
