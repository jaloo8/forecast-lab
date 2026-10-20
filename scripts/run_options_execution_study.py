"""Offline finite options execution study; no network, acquisition or broker path."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scripts.replay_recovered_options import pick_job, verified_payload
from scripts.run_options_pilot import select_pair

from kq.equities.opening_range import underlying_diagnostic
from kq.equities.options_replay import _latest, _quote

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "docs/research/OPTIONS-EXECUTION-PROTOCOL-2026-10-20.md"
DAYS = ("2026-10-08", "2026-10-14", "2026-10-15")
STRUCTURES = ("debit_spread", "long_call")
DELAYS = (0, 1, 5)
CENTS = (1, 2, 3)
ZERO = Decimal("0")
Record = dict[str, Any]


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def dump(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, allow_nan=False, default=str) + "\n", encoding="utf-8"
    )


def timestamp(value: Any) -> pd.Timestamp:
    result = pd.Timestamp(value)
    if pd.isna(result) or result.tzinfo is None:
        raise ValueError("Explicit aware timestamp required")
    return result.tz_convert("UTC")


def latest_books(
    path: Path,
    symbols: tuple[str, str],
    times: tuple[pd.Timestamp, ...],
    *,
    chunksize: int = 100_000,
) -> tuple[dict[str, dict[str, Any]], int]:
    """As-of search per sorted chunk; retain last source row for receive-time ties."""
    columns = [
        "ts_recv",
        "ts_event",
        "instrument_id",
        "symbol",
        "rtype",
        "publisher_id",
        "action",
        "flags",
        "bid_px_00",
        "ask_px_00",
        "bid_sz_00",
        "ask_sz_00",
    ]
    result: dict[str, dict[str, Any]] = {str(at): {} for at in times}
    needles = np.array([at.value for at in times], dtype=np.int64)
    count = 0
    for chunk in pd.read_csv(path, usecols=columns, dtype=str, chunksize=chunksize):
        count += len(chunk)
        if not chunk.symbol.isin(symbols).all():
            raise ValueError("Unexpected symbol in delivered quote file")
        frame = chunk.loc[chunk.action.isin(["A", "M", "C", "R"])].copy()
        frame["received"] = pd.to_datetime(
            frame.ts_recv, utc=True, format="ISO8601", errors="raise"
        )
        if frame.received.isna().any():
            raise ValueError("Missing receive timestamp")
        for symbol in symbols:
            ordered = frame.loc[frame.symbol.eq(symbol)].sort_values("received", kind="stable")
            if ordered.empty:
                continue
            # pandas may choose a lower-resolution datetime dtype: explicitly use nanoseconds.
            positions = (
                np.searchsorted(
                    ordered.received.astype("int64").to_numpy()
                    * (pd.Timedelta(1, unit=ordered.received.dtype.unit).value),
                    needles,
                    side="right",
                )
                - 1
            )
            for at, position in zip(times, positions, strict=True):
                if position < 0:
                    continue
                row = ordered.iloc[int(position)]
                old = result[str(at)].get(symbol)
                if old is None or row.received >= timestamp(old["ts_recv"]):
                    result[str(at)][symbol] = {key: row[key] for key in columns}
    return result, count


def validated(event: Record, at: pd.Timestamp, structure: str) -> list[Record]:
    """Use the prior strict schema checks; validate each actually held leg."""
    signal = timestamp(event["signal_at"])
    symbols = [event["long_symbol"]]
    if structure == "debit_spread":
        symbols.append(event["short_symbol"])
    elif structure != "long_call":
        raise ValueError("Unregistered structure")
    snapshot = event["snapshots"].get(str(at), {})
    result = []
    for symbol in symbols:
        if symbol not in snapshot or symbol not in event["definitions"]:
            raise ValueError("Missing latest quote or definition")
        definition = pd.Series(event["definitions"][symbol], dtype=object)
        quote = pd.Series(snapshot[symbol], dtype=object)
        for record in (definition, quote):
            for field in ("ts_recv", "ts_event"):
                record[field] = timestamp(record[field])
        if (
            definition.ts_recv > signal
            or definition.ts_recv.tz_convert("America/New_York").date()
            != signal.tz_convert("America/New_York").date()
        ):
            raise ValueError("Definition not known on signal date")
        checked = _quote(definition, quote, symbol, True, signal, at, False)
        checked.validate(at)
        if not pd.Timedelta(0) <= at - timestamp(checked.as_of) <= pd.Timedelta(seconds=5):
            raise ValueError("Stale/future quote at nanosecond precision")
        if checked.expiry != at.tz_convert("America/New_York").date() + timedelta(days=1):
            raise ValueError("Not next-calendar-day expiration")
        result.append(
            {
                "symbol": symbol,
                "as_of": str(quote.ts_recv),
                "bid": str(quote.bid_px_00),
                "ask": str(quote.ask_px_00),
                "strike": str(definition.strike_price),
            }
        )
    if len(result) == 2 and (
        abs(timestamp(result[0]["as_of"]) - timestamp(result[1]["as_of"])) > pd.Timedelta(seconds=1)
        or Decimal(result[1]["strike"]) - Decimal(result[0]["strike"]) != 1
    ):
        raise ValueError("Unsynchronized or wrong-width legs")
    return result


def cashflow(quotes: list[Record], cents: int, *, entering: bool) -> Decimal:
    """Signed one-contract cash after fees; Decimal avoids float money drift."""
    slip = Decimal(cents) / 100
    bids = [Decimal(q["bid"]) - slip for q in quotes]
    asks = [Decimal(q["ask"]) + slip for q in quotes]
    if min(bids) <= 0:
        raise ValueError("Nonpositive stressed bid")
    fee = Decimal("0.65") * len(quotes)
    if entering:
        debit = asks[0] - (bids[1] if len(quotes) == 2 else ZERO)
        if debit <= 0 or (len(quotes) == 2 and debit >= 1):
            raise ValueError("Invalid executable debit")
        return -(100 * debit + fee)
    return 100 * (bids[0] - (asks[1] if len(quotes) == 2 else ZERO)) - fee


def simulate(  # noqa: PLR0912, PLR0915 -- keep cash transitions and marks in one audited sequence.
    events: list[Record], structure: str, delay: int, cents: int
) -> Record:
    """Run one preregistered account; all detailed output remains private."""
    if structure not in STRUCTURES or delay not in DELAYS or cents not in CENTS:
        raise ValueError("Unregistered scenario")
    cash, realized, outstanding, reserve = Decimal("1000"), ZERO, ZERO, ZERO
    trades, marks = [], []
    total_fees = ZERO
    previous_exit = None
    leg_count = 2 if structure == "debit_spread" else 1
    fee = Decimal("0.65") * leg_count

    def mark(at: pd.Timestamp, kind: str, nav: Decimal | None, reason: str | None = None) -> None:
        marks.append(
            {
                "at": str(at),
                "kind": kind,
                "cash": str(cash),
                "nav": None if nav is None else str(nav),
                "reserve": str(reserve),
                "reason": reason,
            }
        )

    for event in events:
        signal = timestamp(event["signal_at"])
        entry = timestamp(event["entry_at"]) + pd.Timedelta(seconds=delay)
        exit_at = timestamp(event["exit_at"]) + pd.Timedelta(seconds=delay)
        if not signal < entry < exit_at or (previous_exit is not None and entry <= previous_exit):
            raise ValueError("Noncausal or overlapping event schedule")
        previous_exit = exit_at
        start = timestamp(event["session"] + "T13:30:00Z")
        mark(
            start,
            "session_start",
            None if outstanding else cash,
            "Prior unresolved position" if outstanding else None,
        )
        trade = {
            "session": event["session"],
            "signal_at": str(signal),
            "entry_at": str(entry),
            "exit_at": str(exit_at),
            "cash_before": str(cash),
            "entry_debit": None,
            "exit_cash": None,
            "net_cash": None,
        }
        if outstanding:
            trade.update(status="blocked_unresolved_position", reason="Prior exit remains unknown")
        else:
            try:
                quotes = validated(event, entry, structure)
                if any(timestamp(q["as_of"]) <= signal for q in quotes):
                    raise ValueError("Entry quote not strictly after signal")
                debit = -cashflow(quotes, cents, entering=True)
                if debit + fee > min(Decimal("100"), cash):
                    raise ValueError("Debit and exit reserve exceed research cash limit")
            except ValueError as exc:
                trade.update(status="skipped_entry", reason=str(exc))
            else:
                mark(entry, "before_entry", cash)
                cash -= debit
                reserve, outstanding = fee, debit
                total_fees += fee
                trade["entry_debit"] = str(debit)
                # Whole-minute marks plus event marks, with no future quote interpolation.
                grid = list(pd.date_range(entry.ceil("min"), exit_at, freq="min"))
                times = sorted({entry, exit_at, *grid})
                for at in times:
                    kind = (
                        "after_entry"
                        if at == entry
                        else ("before_exit" if at == exit_at else "minute")
                    )
                    try:
                        liquidation = cashflow(
                            validated(event, at, structure), cents, entering=False
                        )
                        mark(at, kind, cash + liquidation)
                    except ValueError as exc:
                        mark(at, kind, None, str(exc))
                try:
                    proceeds = cashflow(validated(event, exit_at, structure), cents, entering=False)
                    if cash + proceeds < 0:
                        raise ValueError("Exit would require cash borrowing")
                except ValueError as exc:
                    trade.update(status="unresolved_exit", reason=str(exc))
                else:
                    cash += proceeds
                    realized += proceeds - debit
                    reserve, outstanding = ZERO, ZERO
                    total_fees += fee
                    trade.update(
                        status="closed",
                        reason=None,
                        exit_cash=str(proceeds),
                        net_cash=str(proceeds - debit),
                    )
                    mark(exit_at, "after_exit", cash)
        trade.update(
            cash_after=str(cash), available_cash=str(cash - reserve), exit_fee_reserve=str(reserve)
        )
        trades.append(trade)
    peak = Decimal("1000")
    observed_dd = ZERO
    for row in marks:
        if row["nav"] is not None:
            nav = Decimal(row["nav"])
            peak = max(peak, nav)
            observed_dd = max(observed_dd, 1 - nav / peak)
    unknown = sum(row["nav"] is None for row in marks)
    counts = {
        status: sum(t["status"] == status for t in trades)
        for status in ("closed", "skipped_entry", "unresolved_exit", "blocked_unresolved_position")
    }
    summary = {
        "structure": structure,
        "delay_seconds": delay,
        "slippage_cents_per_leg_side": cents,
        "starting_cash": "1000",
        "ending_cash": str(cash),
        "available_cash": str(cash - reserve),
        "closed_net_cash": str(realized),
        "paid_commissions": str(total_fees),
        "unresolved_entry_debit": str(outstanding),
        "exit_fee_reserve": str(reserve),
        "terminal_sample_return": str(cash / 1000 - 1) if not outstanding else None,
        "economic_position_status": "unresolved" if outstanding else "flat",
        "sampled_mark_max_drawdown": str(observed_dd) if not unknown else None,
        "observed_mark_drawdown_lower_bound": str(observed_dd),
        "mark_count": len(marks),
        "unknown_mark_count": unknown,
        **counts,
        "annual_return": None,
    }
    return {"summary": summary, "trades": trades, "marks": marks}


def prepare(recovered: Path) -> tuple[list[Record], list[Record]]:
    """Verify local sources and extract only necessary as-of snapshots."""
    recovery_path = recovered / "recovery.json"
    receipt = json.loads(recovery_path.read_text(encoding="utf-8"))
    if receipt.get("completed") is not True:
        raise ValueError("Recovery incomplete")
    jobs = receipt["jobs"]
    bars_job = pick_job(jobs, "ohlcv-1m", "2023-03-28T00:00Z", "2026-10-17T00:00Z")
    bars_path, details = verified_payload(recovered, bars_job)
    bars = pd.read_csv(bars_path)
    if (
        details["symbols"] != "SPY"
        or details["stype_in"] != "raw_symbol"
        or set(bars.symbol) != {"SPY"}
        or set(bars.rtype) != {33}
        or len(bars) != details["record_count"]
    ):
        raise ValueError("Wrong underlying data")
    bars.index = pd.to_datetime(bars.ts_event, utc=True, format="ISO8601")
    regular = bars.tz_convert("America/New_York").between_time("09:30", "15:59").tz_convert("UTC")
    signals = underlying_diagnostic(regular)
    sources = [
        {"role": "underlying", "sha256": sha(bars_path), "records": len(bars)},
        {"role": "recovery_receipt", "sha256": sha(recovery_path)},
    ]
    events = []
    for day in DAYS:
        tomorrow = str((pd.Timestamp(day) + pd.Timedelta(days=1)).date())
        dj = pick_job(jobs, "definition", f"{day}T00:00Z", f"{tomorrow}T00:00Z")
        qj = pick_job(jobs, "cmbp-1", f"{day}T13:30Z", f"{day}T20:00Z")
        definition_path, dd = verified_payload(recovered, dj)
        quotes_path, qd = verified_payload(recovered, qj)
        if (
            dd["symbols"] != "SPY.OPT"
            or dd["stype_in"] != "parent"
            or qd["stype_in"] != "raw_symbol"
        ):
            raise ValueError("Wrong option symbology")
        selected = signals.loc[signals.session.eq(day)]
        if len(selected) != 1 or selected.iloc[0].status != "underlying_only":
            raise ValueError("Frozen pilot signal absent; no substitution")
        signal = selected.iloc[0]
        close = float(regular.loc[signal.signal_at - pd.Timedelta(minutes=1), "close"])
        pair = select_pair(definition_path, signal.signal_at, close, confirm_standard_spy_100=True)
        if set(pair) != set(qd["symbols"].split(",")):
            raise ValueError("Selected contracts differ from delivery")
        event = {key: str(signal[key]) for key in ("session", "signal_at", "entry_at", "exit_at")}
        event.update(long_symbol=pair[0], short_symbol=pair[1], signal_close=close)
        times = set(
            pd.date_range(signal.entry_at, signal.exit_at + pd.Timedelta(seconds=5), freq="min")
        )
        for delay in DELAYS:
            times.update(
                (
                    signal.entry_at + pd.Timedelta(seconds=delay),
                    signal.exit_at + pd.Timedelta(seconds=delay),
                )
            )
        definitions = _latest(
            definition_path, pair, (signal.signal_at,), 100_000, definitions=True
        )[signal.signal_at]
        event["definitions"] = {
            symbol: {k: str(v) for k, v in row.items()} for symbol, row in definitions.items()
        }
        event["snapshots"], count = latest_books(quotes_path, pair, tuple(sorted(times)))
        if count != qd["record_count"]:
            raise ValueError("Quote record count mismatch")
        for role, path, count_value in (
            ("definition", definition_path, dd["record_count"]),
            ("cmbp-1", quotes_path, count),
        ):
            sources.append(
                {"role": role, "session": day, "sha256": sha(path), "records": count_value}
            )
        events.append(event)
    return events, sources


def reviewed_hashes() -> dict[str, str]:
    paths = (
        PROTOCOL,
        Path(__file__),
        ROOT / "scripts/check_options_execution_study.py",
        ROOT / "tests/test_options_execution_study.py",
        ROOT / "scripts/replay_recovered_options.py",
        ROOT / "scripts/run_options_pilot.py",
        ROOT / "src/kq/equities/opening_range.py",
        ROOT / "src/kq/equities/options_replay.py",
        ROOT / "src/kq/equities/option_spread.py",
    )
    return {path.relative_to(ROOT).as_posix(): sha(path) for path in paths}


def run(recovered: Path, output: Path, review: Path) -> Record:
    if output.exists():
        raise FileExistsError("Preserve prior evidence; choose a new output directory")
    approval = json.loads(review.read_text(encoding="utf-8"))
    hashes = reviewed_hashes()
    if approval.get("status") != "approved_for_offline_run" or approval.get("files") != hashes:
        raise ValueError("Missing or stale independent review of this exact implementation")
    output.mkdir(parents=True)
    (output / "review-receipt.json").write_bytes(review.read_bytes())
    started = {
        "started_utc": str(pd.Timestamp.now(tz="UTC")),
        "protocol_sha256": sha(PROTOCOL),
        "runner_sha256": sha(Path(__file__)),
        "new_data_spend_usd": "0",
        "status": "started_before_quote_processing",
        "accounts_registered": 18,
        "review_receipt_sha256": sha(output / "review-receipt.json"),
        "reviewed_files": hashes,
    }
    dump(output / "started.json", started)
    phase = "prepare"
    try:
        events, sources = prepare(recovered)
        dump(output / "private-evidence.json", {"events": events, "sources": sources})
        summaries = {}
        phase = "simulate"
        for structure, delay, cents in itertools.product(STRUCTURES, DELAYS, CENTS):
            key = f"{structure}_delay{delay}_c{cents}"
            result = simulate(events, structure, delay, cents)
            dump(output / f"{key}.json", result)
            summaries[key] = result["summary"]
        phase = "post_run_hash_check"
        if reviewed_hashes() != hashes or sha(output / "review-receipt.json") != sha(review):
            raise ValueError("Reviewed implementation or receipt changed during run")
    except Exception as exc:
        # Type and phase are enough for the public failure marker; raw exceptions
        # can contain private delivery paths. Preserve all already written artifacts.
        dump(
            output / "run-error.json",
            {
                "status": "failed_incomplete_not_performance",
                "phase": phase,
                "exception_type": type(exc).__name__,
                "started_receipt_sha256": sha(output / "started.json"),
            },
        )
        raise
    summary = {
        **started,
        "status": "completed_conditional_retrospective_three_session_simulation",
        "sources": sources,
        "accounts": summaries,
        "dates": DAYS,
        "independent_accounting_review": "pending",
        "scope": "18 accounts / 54 session decisions; no annualization or broker eligibility claim",
    }
    dump(output / "summary.json", summary)
    dump(
        output / "manifest.json",
        {
            "files": {
                path.name: {"sha256": sha(path), "bytes": path.stat().st_size}
                for path in sorted(output.iterdir())
                if path.is_file()
            }
        },
    )
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recovered", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.recovered, args.output, args.review)
    print(json.dumps({"completed_accounts": len(result["accounts"]), "new_data_spend_usd": "0"}))
