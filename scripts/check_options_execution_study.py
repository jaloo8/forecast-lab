"""Independent saved-snapshot arithmetic audit; no simulator imports or network."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import re
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def time(value: str) -> pd.Timestamp:
    at = pd.Timestamp(value)
    assert at.tzinfo is not None and not pd.isna(at), "Missing aware time"
    return at.tz_convert("UTC")


def legs(event: dict[str, Any], at: pd.Timestamp, n: int) -> list[dict[str, Any]] | None:
    """Independently check causal, standard-contract and strict quote conditions."""
    out = []
    signal = time(event["signal_at"])
    for symbol in [event["long_symbol"], event["short_symbol"]][:n]:
        definition = event["definitions"].get(symbol)
        row = event["snapshots"].get(str(at), {}).get(symbol)
        if definition is None or row is None:
            return None
        recv, occurred = time(row["ts_recv"]), time(row["ts_event"])
        known, def_event = time(definition["ts_recv"]), time(definition["ts_event"])
        occ = re.fullmatch(r"SPY   (\d{6})C(\d{8})", symbol)
        if occ is None:
            return None
        expiry = time(definition["expiration"])
        bid, ask = Decimal(row["bid_px_00"]), Decimal(row["ask_px_00"])
        if (
            not pd.Timedelta(0) <= at - recv <= pd.Timedelta(seconds=5)
            or occurred > at
            or known > signal
            or def_event > signal
            or known.tz_convert("America/New_York").date()
            != signal.tz_convert("America/New_York").date()
            or definition["instrument_class"] != "C"
            or definition["underlying"] != "SPY"
            or definition["security_update_action"] not in ("A", "M")
            or int(definition["contract_multiplier"]) not in (100, 2147483647)
            or definition["instrument_id"] != row["instrument_id"]
            or expiry.strftime("%y%m%d") != occ[1]
            or Decimal(definition["strike_price"]) != Decimal(occ[2]) / 1000
            or expiry.date() != at.tz_convert("America/New_York").date() + timedelta(days=1)
            or int(row["rtype"]) != 177
            or int(row["publisher_id"]) != 30
            or row["action"] not in ("A", "M", "C")
            or int(row["flags"]) & ~(128 | 64 | 32)
            or not bid.is_finite()
            or not ask.is_finite()
            or not 0 < bid <= ask
            or min(int(row["bid_sz_00"]), int(row["ask_sz_00"])) < 1
        ):
            return None
        out.append(row)
    if n == 2 and (
        abs(time(out[0]["ts_recv"]) - time(out[1]["ts_recv"])) > pd.Timedelta(seconds=1)
        or Decimal(event["definitions"][event["short_symbol"]]["strike_price"])
        - Decimal(event["definitions"][event["long_symbol"]]["strike_price"])
        != 1
    ):
        return None
    return out


def amounts(event: dict[str, Any], at: pd.Timestamp, n: int, cents: int) -> tuple[Any, Any]:
    rows = legs(event, at, n)
    if rows is None:
        return None, None
    slip = Decimal(cents) / 100
    bid = [Decimal(row["bid_px_00"]) - slip for row in rows]
    ask = [Decimal(row["ask_px_00"]) + slip for row in rows]
    if min(bid) <= 0:
        return None, None
    purchase = 100 * (ask[0] - (bid[1] if n == 2 else 0)) + Decimal("0.65") * n
    liquidation = 100 * (bid[0] - (ask[1] if n == 2 else 0)) - Decimal("0.65") * n
    return purchase, liquidation


def audit_account(  # noqa: PLR0912, PLR0915 -- independent sequential cash reconciliation.
    events: list[dict[str, Any]], account: dict[str, Any], structure: str, delay: int, cents: int
) -> dict[str, int]:
    """Reconcile every saved trade/mark, including independently derived refusals."""
    n = 2 if structure == "debit_spread" else 1
    fee = Decimal("0.65") * n
    cash, realized, paid, outstanding, reserve = map(Decimal, ("1000", "0", "0", "0", "0"))
    expected_marks: list[tuple[str, str, Decimal, Decimal, Any]] = []
    counts = dict.fromkeys(
        ("closed", "skipped_entry", "unresolved_exit", "blocked_unresolved_position"), 0
    )

    def mark(at: pd.Timestamp, kind: str, nav: Any) -> None:
        expected_marks.append((str(at), kind, cash, reserve, nav))

    assert len(account["trades"]) == len(events) == 3, "Wrong session count"
    for event, trade in zip(events, account["trades"], strict=True):
        entry = time(event["entry_at"]) + pd.Timedelta(seconds=delay)
        exit_at = time(event["exit_at"]) + pd.Timedelta(seconds=delay)
        assert time(event["signal_at"]) < entry < exit_at
        assert trade["session"] == event["session"]
        assert trade["signal_at"] == event["signal_at"]
        assert time(trade["entry_at"]) == entry and time(trade["exit_at"]) == exit_at
        assert Decimal(trade["cash_before"]) == cash, "Trade opening cash"
        mark(time(event["session"] + "T13:30:00Z"), "session_start", None if outstanding else cash)
        debit = proceeds = net = None
        if outstanding:
            status = "blocked_unresolved_position"
        else:
            proposed, _ = amounts(event, entry, n, cents)
            rows = legs(event, entry, n)
            accepted = (
                proposed is not None
                and rows is not None
                and all(time(row["ts_recv"]) > time(event["signal_at"]) for row in rows)
                and proposed > fee
                and (n == 1 or proposed - fee < 100)
                and proposed + fee <= min(100, cash)
            )
            if not accepted:
                status = "skipped_entry"
            else:
                debit = proposed
                mark(entry, "before_entry", cash)
                cash -= debit
                outstanding, reserve = debit, fee
                paid += fee
                grid = set(pd.date_range(entry.ceil("min"), exit_at, freq="min"))
                for at in sorted({entry, exit_at, *grid}):
                    _, sale = amounts(event, at, n, cents)
                    kind = (
                        "after_entry"
                        if at == entry
                        else ("before_exit" if at == exit_at else "minute")
                    )
                    mark(at, kind, None if sale is None else cash + sale)
                _, sale = amounts(event, exit_at, n, cents)
                if sale is None or cash + sale < 0:
                    status = "unresolved_exit"
                else:
                    status = "closed"
                    proceeds, net = sale, sale - debit
                    cash += proceeds
                    realized += net
                    paid += fee
                    outstanding, reserve = Decimal(0), Decimal(0)
                    mark(exit_at, "after_exit", cash)
        assert trade["status"] == status, "Incorrect trade classification"
        counts[status] += 1
        for field, expected in (("entry_debit", debit), ("exit_cash", proceeds), ("net_cash", net)):
            assert (None if trade[field] is None else Decimal(trade[field])) == expected, field
        for field, expected in (
            ("cash_after", cash),
            ("available_cash", cash - reserve),
            ("exit_fee_reserve", reserve),
        ):
            assert Decimal(trade[field]) == expected, field
    assert len(account["marks"]) == len(expected_marks), "Missing/extra NAV marks"
    peak, drawdown = Decimal(1000), Decimal(0)
    unknown = 0
    for actual, (at, kind, expected_cash, expected_reserve, nav) in zip(
        account["marks"], expected_marks, strict=True
    ):
        assert actual["at"] == at and actual["kind"] == kind, "Mark schedule"
        assert Decimal(actual["cash"]) == expected_cash, "Mark cash"
        assert Decimal(actual["reserve"]) == expected_reserve, "Mark reserve"
        assert (None if actual["nav"] is None else Decimal(actual["nav"])) == nav, "Mark NAV"
        if nav is None:
            unknown += 1
        else:
            peak = max(peak, nav)
            drawdown = max(drawdown, 1 - nav / peak)
    expected_summary = {
        "structure": structure,
        "delay_seconds": delay,
        "slippage_cents_per_leg_side": cents,
        "starting_cash": "1000",
        "ending_cash": str(cash),
        "available_cash": str(cash - reserve),
        "closed_net_cash": str(realized),
        "paid_commissions": str(paid),
        "unresolved_entry_debit": str(outstanding),
        "exit_fee_reserve": str(reserve),
        "terminal_sample_return": str(cash / 1000 - 1) if not outstanding else None,
        "economic_position_status": "unresolved" if outstanding else "flat",
        "sampled_mark_max_drawdown": str(drawdown) if not unknown else None,
        "observed_mark_drawdown_lower_bound": str(drawdown),
        "mark_count": len(expected_marks),
        "unknown_mark_count": unknown,
        "annual_return": None,
        **counts,
    }
    assert account["summary"] == expected_summary, "Account summary mismatch"
    return {"session_decisions": 3, "marks": len(expected_marks), "unknown_marks": unknown}


def audit(directory: Path) -> dict[str, Any]:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    for name, record in manifest["files"].items():
        assert Path(name).name == name, "Unsafe file path"
        path = directory / name
        assert path.stat().st_size == record["bytes"] and digest(path) == record["sha256"]
    evidence = json.loads((directory / "private-evidence.json").read_text(encoding="utf-8"))
    events = evidence["events"]
    assert [e["session"] for e in events] == ["2026-10-08", "2026-10-14", "2026-10-15"]
    report = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    review = json.loads((directory / "review-receipt.json").read_text(encoding="utf-8"))
    assert review["status"] == "approved_for_offline_run"
    assert review["files"] == report["reviewed_files"]
    assert report["review_receipt_sha256"] == digest(directory / "review-receipt.json")
    keys = {
        f"{s}_delay{d}_c{c}"
        for s, d, c in itertools.product(("debit_spread", "long_call"), (0, 1, 5), (1, 2, 3))
    }
    assert set(report["accounts"]) == keys, "Scenario coverage"
    details = {}
    for structure, delay, cents in itertools.product(
        ("debit_spread", "long_call"), (0, 1, 5), (1, 2, 3)
    ):
        key = f"{structure}_delay{delay}_c{cents}"
        account = json.loads((directory / f"{key}.json").read_text(encoding="utf-8"))
        details[key] = audit_account(events, account, structure, delay, cents)
        assert report["accounts"][key] == account["summary"], "Public/private summary mismatch"
    for cents, expected in ((1, "983.20"), (2, "971.20"), (3, "959.20")):
        original = report["accounts"][f"debit_spread_delay0_c{cents}"]
        assert original["closed"] == 3 and original["unresolved_exit"] == 0
        assert Decimal(original["ending_cash"]) == Decimal(expected), "Prior baseline changed"
    return {
        "status": "pass",
        "checker_sha256": digest(Path(__file__)),
        "manifest_sha256": digest(directory / "manifest.json"),
        "accounts_checked": len(details),
        "session_decisions_checked": sum(d["session_decisions"] for d in details.values()),
        "nav_marks_checked": sum(d["marks"] for d in details.values()),
        "unknown_nav_marks": sum(d["unknown_marks"] for d in details.values()),
        "prior_zero_delay_spread_accounts_matched": 3,
        "scope": [
            "All 18 account keys, 54 decisions, costs, cash, reserves, NAV and sampled drawdown",
            "Independent definition/quote causality, strict flags, funding and refusal arithmetic",
            "Saved source snapshots and output digests; no simulator import",
        ],
        "limits": [
            "Does not independently reconstruct opening-range signals or chain selection",
            "Does not independently rescan raw deliveries to prove latest-record extraction",
            "No execution, assignment, exercise, broker eligibility or annual-return proof",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if args.receipt.exists():
        raise FileExistsError("Preserve prior receipt")
    receipt = audit(args.run)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))
