"""Write-once challenger decisions and isolated matched-SPY forward outcomes.

``evaluate`` DataFrame schema: lane, symbol, as_of (aware UTC), status,
entry_date, exit_date, gross_return, net_return, spy_net_return,
excess_vs_spy, decision_hash, future_source_hash. Null results mean pending
or invalid, never zero returns. These cohorts are not funded-account P&L.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from kq.equities.challenger import screen
from kq.equities.research import _timestamp, daily_bars

PROTOCOL = {
    "name": "earnings_momentum_forward_v1",
    "universe": "captured_catalogue_intersect_unfiltered_earnings_calendar",
    "common": "21_exact_spy_sessions_close_ge_5_median20_dollar_volume_ge_20m_positive20_excess",
    "challenger": "verified_report_last7_after_next_utc_midnight_positive_estimate_beat_ge_5pct",
    "selection": "top3_excess_desc_ticker_ascending",
    "ablation": "same_universe_common_rules_without_earnings_gate",
    "entry": "next_regular_ny_open_strictly_after_decision",
    "exit": "20th_held_session_close_matched_spy",
    "friction_each_side_bps": 10,
}
METHOD_HASH = hashlib.sha256(json.dumps(PROTOCOL, sort_keys=True).encode()).hexdigest()
FRICTION = 0.999 / 1.001
NY = ZoneInfo("America/New_York")
EVAL_COLUMNS = [
    "lane", "symbol", "as_of", "status", "entry_date", "exit_date",
    "gross_return", "net_return", "spy_net_return", "excess_vs_spy",
    "decision_hash", "future_source_hash",
]


def _hash(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for record in frame.to_dict(orient="records"):
        clean: dict[str, Any] = {}
        for key, value in record.items():
            if value is None or (not isinstance(value, str) and bool(pd.isna(value))):
                clean[key] = None
            elif isinstance(value, (datetime, pd.Timestamp)):
                clean[key] = value.isoformat()
            elif hasattr(value, "item"):
                clean[key] = value.item()
            else:
                clean[key] = value
        records.append(clean)
    return records


def _anchors(
    snapshot: dict[str, Any], names: set[str], *, latest_only: bool = False
) -> dict[str, list[dict[str, Any]]]:
    bars = daily_bars(snapshot)
    result: dict[str, list[dict[str, Any]]] = {}
    for symbol in sorted(names):
        rows = bars.loc[bars.symbol == symbol].sort_values("session_date")
        if latest_only:
            rows = rows.tail(21)
        result[symbol] = [
            {"session_date": row.session_date.isoformat(), "open": float(row.open),
             "close": float(row.close), "volume": float(row.volume)}
            for row in rows.itertuples(index=False)
        ]
    return result


def write_decision(snapshot: dict[str, Any], path: Path) -> dict[str, Any]:
    """Write a non-backdated, exclusive JSON decision after screening inputs."""
    frame = screen(snapshot)
    created = datetime.now(UTC)
    captured = _timestamp(snapshot.get("captured_at"), "captured_at")
    if created < captured:
        raise ValueError("decision creation cannot predate capture")
    if path.suffix != ".json":
        raise ValueError("decision output must be JSON")
    selected = {
        lane: frame.loc[frame[f"{lane}_selected"], "symbol"].tolist()
        for lane in ("challenger", "momentum")
    }
    anchors = _anchors(
        snapshot, {"SPY", *selected["challenger"], *selected["momentum"]}, latest_only=True
    )
    artifact = {
        "created_at": created.isoformat(), "input_captured_at": captured.isoformat(),
        "input_hash": _hash(snapshot), "method_hash": METHOD_HASH,
        "protocol": dict(PROTOCOL), "selected": selected, "anchors": anchors,
        "screen": _records(frame),
    }
    payload = json.dumps(artifact, indent=2, allow_nan=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(payload)
    return artifact


def _selected(decision: dict[str, Any]) -> list[tuple[str, str]]:
    selected = decision.get("selected")
    if not isinstance(selected, dict) or set(selected) != {"challenger", "momentum"}:
        raise ValueError("decision selected lanes missing")
    pairs: list[tuple[str, str]] = []
    for lane in ("challenger", "momentum"):
        names = selected[lane]
        if (not isinstance(names, list) or len(names) > 3 or len(set(names)) != len(names)
            or any(not isinstance(s, str) or not s or s != s.upper() or s == "SPY"
                   for s in names)):
            raise ValueError("invalid decision selection")
        pairs.extend((lane, symbol) for symbol in names)
    return pairs


def evaluate(  # noqa: PLR0912, PLR0915
    decision: dict[str, Any], future_snapshot: dict[str, Any],
    previous_snapshot: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Evaluate 20 subsequent sessions; a prior capture detects later revisions.

    Without an exchange-holiday calendar, any missing weekday in the observed
    SPY grid yields ``unverified_calendar`` rather than a return estimate.
    """
    created = _timestamp(decision.get("created_at"), "created_at")
    input_time = _timestamp(decision.get("input_captured_at"), "input_captured_at")
    observed = _timestamp(future_snapshot.get("captured_at"), "captured_at")
    if input_time > created or created > datetime.now(UTC) or observed > datetime.now(UTC):
        raise ValueError("invalid forward observation chronology")
    future_hash = _hash(future_snapshot)
    if observed < created and (observed != input_time or
                               future_hash != decision.get("input_hash")):
        raise ValueError("older observation must match decision input exactly")
    if future_snapshot.get("benchmark") != "SPY":
        raise ValueError("future benchmark must be SPY")
    if future_snapshot.get("adjustment_type") != "split":
        raise ValueError("future adjustment_type must be split")
    if decision.get("method_hash") != METHOD_HASH:
        raise ValueError("unsupported decision method")
    if decision.get("protocol") != PROTOCOL:
        raise ValueError("unsupported decision protocol")
    pairs = _selected(decision)
    bars = daily_bars(future_snapshot)
    spy = bars.loc[bars.symbol == "SPY"].set_index("session_date").sort_index()
    if spy.empty:
        raise ValueError("future SPY bars missing")
    held = [day for day in spy.index if datetime.combine(day, time(9, 30), NY).astimezone(UTC)
            > created]
    target = held[:20]
    decision_hash = _hash(decision)
    expected_anchors = decision.get("anchors")
    expected_symbols = {"SPY", *(symbol for _, symbol in pairs)}
    anchor_fields = {"session_date", "open", "close", "volume"}
    if (not isinstance(expected_anchors, dict) or set(expected_anchors) != expected_symbols
        or any(not isinstance(original, list) or len(original) != 21
               or any(not isinstance(bar, dict) or set(bar) != anchor_fields
                      for bar in original)
               for original in expected_anchors.values())):
        raise ValueError("decision anchors missing")
    actual_anchors = _anchors(future_snapshot, set(expected_anchors))
    failures = {symbol for symbol, original in expected_anchors.items()
                if any(bar not in actual_anchors[symbol] for bar in original)}
    revisions: set[str] = set()
    if previous_snapshot is not None:
        prior_time = _timestamp(previous_snapshot.get("captured_at"), "captured_at")
        if prior_time > observed or previous_snapshot.get("benchmark") != "SPY":
            raise ValueError("invalid previous observation chronology")
        previous = _anchors(previous_snapshot, set(expected_anchors))
        revisions = {symbol for symbol, original in previous.items()
                     if any(bar not in actual_anchors[symbol] for bar in original)}
    local = created.astimezone(NY)
    first_possible = local.date() + (timedelta(days=1) if local.time() >= time(9, 30)
                                     else timedelta())
    last_check = observed.date() - timedelta(days=1)
    if len(target) == 20:
        last_check = min(last_check, target[-1])
    calendar_gap = not set(pd.bdate_range(first_possible, last_check).date).issubset(
        set(held)
    )
    rows: list[dict[str, Any]] = []
    for lane, symbol in pairs:
        stock = bars.loc[bars.symbol == symbol].set_index("session_date").sort_index()
        missing_stock_session = bool(target) and not set(target).issubset(set(stock.index))
        row: dict[str, Any] = {
            "lane": lane, "symbol": symbol, "as_of": max(observed, created),
            "status": "pending",
            "entry_date": target[0].isoformat() if target else None,
            "exit_date": target[-1].isoformat() if len(target) == 20 else None,
            "gross_return": None, "net_return": None, "spy_net_return": None,
            "excess_vs_spy": None, "decision_hash": decision_hash,
            "future_source_hash": future_hash,
        }
        if "SPY" in failures or symbol in failures:
            row["status"] = "invalid_anchor"
        elif "SPY" in revisions or symbol in revisions:
            row["status"] = "invalid_revision"
        elif missing_stock_session:
            row["status"] = "invalid_missing_session"
        elif calendar_gap:
            row["status"] = "unverified_calendar"
        elif len(target) == 20:
            gross = float(stock.at[target[-1], "close"] / stock.at[target[0], "open"] - 1)
            net = (1 + gross) * FRICTION - 1
            spy_net = (float(spy.at[target[-1], "close"] /
                             spy.at[target[0], "open"]) * FRICTION - 1)
            row.update(status="mature", gross_return=gross, net_return=net,
                       spy_net_return=spy_net, excess_vs_spy=net - spy_net)
        rows.append(row)
    result = pd.DataFrame(rows, columns=EVAL_COLUMNS)
    result["as_of"] = pd.to_datetime(result["as_of"], utc=True)
    return result
