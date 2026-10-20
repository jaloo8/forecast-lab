"""Artificial fixtures: no market-data loading or claimed historical performance."""

import copy
import json
from decimal import Decimal

import pandas as pd
import pytest
from scripts import run_options_execution_study as runner
from scripts.check_options_execution_study import audit_account
from scripts.run_options_execution_study import latest_books, simulate


def event(day="2026-10-08"):
    tomorrow = pd.Timestamp(day) + pd.Timedelta(days=1)
    expiry = tomorrow.strftime("%y%m%d")
    symbols = [f"SPY   {expiry}C00775000", f"SPY   {expiry}C00776000"]
    signal = pd.Timestamp(day + "T13:59:00Z")
    entry = signal + pd.Timedelta(minutes=1)
    exit_at = entry + pd.Timedelta(minutes=2)
    definitions = {}
    for i, symbol in enumerate(symbols):
        definitions[symbol] = {
            "raw_symbol": symbol,
            "ts_recv": day + "T13:00:00Z",
            "ts_event": day + "T13:00:00Z",
            "instrument_id": str(i + 1),
            "expiration": str(tomorrow.tz_localize("UTC")),
            "strike_price": str(775 + i),
            "instrument_class": "C",
            "underlying": "SPY",
            "security_update_action": "A",
            "contract_multiplier": "2147483647",
        }
    times = set(pd.date_range(entry, exit_at, freq="min"))
    for delay in (0, 1, 5):
        times.update((entry + pd.Timedelta(seconds=delay), exit_at + pd.Timedelta(seconds=delay)))
    snapshots = {}
    for at in times:
        snapshots[str(at)] = {
            symbol: {
                "ts_recv": str(at - pd.Timedelta(milliseconds=100)),
                "ts_event": str(at - pd.Timedelta(milliseconds=110)),
                "symbol": symbol,
                "instrument_id": str(i + 1),
                "rtype": "177",
                "publisher_id": "30",
                "action": "M",
                "flags": "128",
                "bid_px_00": "0.50" if i == 0 else "0.20",
                "ask_px_00": "0.52" if i == 0 else "0.22",
                "bid_sz_00": "1",
                "ask_sz_00": "1",
            }
            for i, symbol in enumerate(symbols)
        }
    return {
        "session": day,
        "signal_at": str(signal),
        "entry_at": str(entry),
        "exit_at": str(exit_at),
        "long_symbol": symbols[0],
        "short_symbol": symbols[1],
        "definitions": definitions,
        "snapshots": snapshots,
    }


def three_events():
    return [event(day) for day in ("2026-10-08", "2026-10-14", "2026-10-15")]


@pytest.mark.parametrize(
    "structure,expected", [("debit_spread", "968.20"), ("long_call", "984.10")]
)
@pytest.mark.parametrize("delay", [0, 1, 5])
def test_cash_and_independent_reconciliation(structure, expected, delay):
    events = three_events()
    account = simulate(events, structure, delay, 1)
    assert Decimal(account["summary"]["ending_cash"]) == Decimal(expected)
    assert account["summary"]["closed"] == 3
    assert audit_account(events, account, structure, delay, 1)["session_decisions"] == 3


def test_long_call_does_not_require_unused_short_quote():
    one = event()
    for snapshot in one["snapshots"].values():
        snapshot[one["short_symbol"]]["flags"] = "8"
    assert simulate([one], "debit_spread", 0, 1)["summary"]["skipped_entry"] == 1
    assert simulate([one], "long_call", 0, 1)["summary"]["closed"] == 1


def test_commissions_and_reserve_make_otherwise_affordable_call_a_skip():
    one = event()
    for snapshot in one["snapshots"].values():
        snapshot[one["long_symbol"]].update(bid_px_00="0.98", ask_px_00="0.98")
    # $99 stressed premium + $0.65 entry + $0.65 reserved exit = $100.30.
    summary = simulate([one], "long_call", 0, 1)["summary"]
    assert summary["skipped_entry"] == 1 and Decimal(summary["ending_cash"]) == 1000


def test_missing_exit_preserves_position_and_blocks_future_entries():
    events = three_events()
    del events[0]["snapshots"][events[0]["exit_at"]]
    account = simulate(events, "debit_spread", 0, 1)
    summary = account["summary"]
    assert summary["unresolved_exit"] == 1 and summary["blocked_unresolved_position"] == 2
    assert summary["terminal_sample_return"] is None
    assert summary["sampled_mark_max_drawdown"] is None
    assert Decimal(summary["unresolved_entry_debit"]) == Decimal("35.30")
    assert Decimal(summary["exit_fee_reserve"]) == Decimal("1.30")
    audit_account(events, account, "debit_spread", 0, 1)


def test_missing_interim_nav_does_not_invent_a_mark_or_erase_known_terminal_cash():
    events = three_events()
    missing = str(pd.Timestamp(events[0]["entry_at"]) + pd.Timedelta(minutes=1))
    del events[0]["snapshots"][missing]
    account = simulate(events, "long_call", 0, 1)
    assert account["summary"]["unknown_mark_count"] == 1
    assert account["summary"]["sampled_mark_max_drawdown"] is None
    assert account["summary"]["terminal_sample_return"] is not None
    audit_account(events, account, "long_call", 0, 1)


@pytest.mark.parametrize("change", ["future_event", "stale_ns", "unsynchronized_ns", "pre_signal"])
def test_bad_entry_times_refused_at_nanosecond_precision(change):
    one = event()
    at = pd.Timestamp(one["entry_at"])
    snapshot = one["snapshots"][str(at)]
    row = snapshot[one["long_symbol"]]
    if change == "future_event":
        row["ts_event"] = str(at + pd.Timedelta(nanoseconds=1))
    elif change == "stale_ns":
        row["ts_recv"] = str(at - pd.Timedelta(seconds=5, nanoseconds=1))
    elif change == "unsynchronized_ns":
        row["ts_recv"] = str(at - pd.Timedelta(seconds=1, milliseconds=100, nanoseconds=1))
    else:
        row["ts_recv"] = one["signal_at"]
    assert simulate([one], "debit_spread", 0, 1)["summary"]["skipped_entry"] == 1


def test_delay_uses_its_own_snapshot():
    one = event()
    row = one["snapshots"][str(pd.Timestamp(one["entry_at"]) + pd.Timedelta(seconds=1))]
    row[one["long_symbol"]]["ask_px_00"] = "0.54"
    zero = simulate([one], "long_call", 0, 1)
    delayed = simulate([one], "long_call", 1, 1)
    assert Decimal(zero["summary"]["ending_cash"]) - Decimal(delayed["summary"]["ending_cash"]) == 2


@pytest.mark.parametrize("corruption", ["cash", "nav", "status", "drawdown", "missing_mark"])
def test_checker_rejects_semantic_corruption_without_manifest_shortcut(corruption):
    events = three_events()
    account = simulate(events, "debit_spread", 0, 1)
    if corruption == "cash":
        account["trades"][0]["cash_after"] = "1000"
    elif corruption == "nav":
        account["marks"][2]["nav"] = "1000"
    elif corruption == "status":
        account["trades"][0]["status"] = "skipped_entry"
    elif corruption == "drawdown":
        account["summary"]["sampled_mark_max_drawdown"] = "0"
    else:
        account["marks"].pop(2)
    with pytest.raises(AssertionError):
        audit_account(events, account, "debit_spread", 0, 1)


def test_chunked_asof_retains_invalid_latest_and_last_source_row_tie(tmp_path):
    one = event()
    at = pd.Timestamp(one["entry_at"])
    row = one["snapshots"][str(at)][one["long_symbol"]]
    old, reset, tied, future = [copy.deepcopy(row) for _ in range(4)]
    old["ts_recv"] = str(at - pd.Timedelta(seconds=1))
    reset.update(action="R", ts_recv=str(at - pd.Timedelta(milliseconds=50)))
    tied.update(action="M", flags="8", ts_recv=reset["ts_recv"])
    future["ts_recv"] = str(at + pd.Timedelta(nanoseconds=1))
    path = tmp_path / "quotes.csv"
    pd.DataFrame([old, reset, tied, future]).to_csv(path, index=False)
    samples, count = latest_books(
        path, (one["long_symbol"], one["short_symbol"]), (at,), chunksize=2
    )
    assert count == 4
    assert samples[str(at)][one["long_symbol"]]["flags"] == "8"
    assert samples[str(at)][one["long_symbol"]]["ts_recv"] == tied["ts_recv"]


def test_no_unregistered_scenario():
    with pytest.raises(ValueError, match="Unregistered"):
        simulate([event()], "debit_spread", 10, 1)


def test_exit_cannot_create_borrowing():
    events = three_events()
    events[0]["snapshots"][events[0]["exit_at"]][events[0]["short_symbol"]].update(
        bid_px_00="19.99", ask_px_00="20.00"
    )
    account = simulate(events, "debit_spread", 0, 1)
    assert account["summary"]["unresolved_exit"] == 1
    assert account["summary"]["blocked_unresolved_position"] == 2
    assert Decimal(account["summary"]["ending_cash"]) > 0
    assert "borrowing" in account["trades"][0]["reason"]
    audit_account(events, account, "debit_spread", 0, 1)


def test_strict_after_signal_even_when_quote_otherwise_fresh():
    one = event()
    at = pd.Timestamp(one["entry_at"])
    one["signal_at"] = str(at - pd.Timedelta(seconds=1))
    for row in one["snapshots"][str(at)].values():
        row["ts_recv"] = one["signal_at"]
        row["ts_event"] = one["signal_at"]
    assert simulate([one], "debit_spread", 0, 1)["summary"]["skipped_entry"] == 1


def test_stale_review_stops_before_prepare(tmp_path, monkeypatch):
    review = tmp_path / "review.json"
    review.write_text(json.dumps({"status": "approved_for_offline_run", "files": {}}))
    monkeypatch.setattr(runner, "prepare", lambda _: pytest.fail("Must not read data"))
    with pytest.raises(ValueError, match="stale"):
        runner.run(tmp_path, tmp_path / "output", review)
    assert not (tmp_path / "output").exists()


def test_failure_retains_explicit_error_receipt_without_exception_details(tmp_path, monkeypatch):
    review = tmp_path / "review.json"
    review.write_text(
        json.dumps({"status": "approved_for_offline_run", "files": runner.reviewed_hashes()})
    )

    def fail(_):
        raise ValueError("private delivery details not for public receipt")

    monkeypatch.setattr(runner, "prepare", fail)
    with pytest.raises(ValueError):
        runner.run(tmp_path, tmp_path / "output", review)
    raw = (tmp_path / "output/run-error.json").read_text()
    receipt = json.loads(raw)
    assert receipt["phase"] == "prepare" and receipt["exception_type"] == "ValueError"
    assert "private delivery" not in raw


def test_changed_implementation_during_run_is_not_completed(tmp_path, monkeypatch):
    original = runner.reviewed_hashes()
    review = tmp_path / "review.json"
    review.write_text(json.dumps({"status": "approved_for_offline_run", "files": original}))
    calls = iter((original, {**original, "new/unreviewed": "bad"}))
    monkeypatch.setattr(runner, "reviewed_hashes", lambda: next(calls))
    monkeypatch.setattr(runner, "prepare", lambda _: (three_events(), []))
    with pytest.raises(ValueError, match="changed"):
        runner.run(tmp_path, tmp_path / "output", review)
    receipt = json.loads((tmp_path / "output/run-error.json").read_text())
    assert receipt["phase"] == "post_run_hash_check"
    assert not (tmp_path / "output/summary.json").exists()
