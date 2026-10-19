import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest
from scripts.replay_recovered_options import account, pick_job, verified_payload

from kq.equities.option_spread import CallQuote


def event(day: str, *, missing_exit: bool = False):
    signal = pd.Timestamp(f"{day}T14:00:00Z")
    entry = signal + pd.Timedelta(minutes=1)
    exit_at = signal + pd.Timedelta(minutes=2)
    expiry = date.fromisoformat(day) + timedelta(days=1)

    def pair(at, bid, ask):
        return (
            CallQuote("SPY", expiry, 100, at, bid, ask, 1, 1),
            CallQuote("SPY", expiry, 101, at, 0.10, 0.12, 1, 1),
        )

    return (
        {"session": day, "signal_at": signal, "entry_at": entry, "exit_at": exit_at},
        {
            entry: pair(entry, 0.68, 0.70),
            exit_at: "Missing exit" if missing_exit else pair(exit_at, 0.80, 0.82),
        },
    )


def test_cash_ledger_reconciles_fees_and_two_sided_slippage():
    events = [event("2026-10-08"), event("2026-10-14")]
    rows, summary = account(events, 0)
    assert rows.entry_debit.to_list() == pytest.approx([63.30, 63.30])
    assert rows.exit_cash.to_list() == pytest.approx([64.70, 64.70])
    assert rows.cash_after.to_list() == pytest.approx([1001.40, 1002.80])
    assert summary["closed_net_cash"] == pytest.approx(2.80)
    assert summary["terminal_return_across_sampled_dates"] == pytest.approx(0.0028)
    assert summary["annual_return"] is None
    _, stressed = account(events, 1)
    assert stressed["ending_cash"] == pytest.approx(994.80)


def test_unknown_exit_retains_debit_and_blocks_later_opportunity():
    rows, summary = account([event("2026-10-08", missing_exit=True), event("2026-10-14")], 0)
    assert rows.status.to_list() == ["unresolved_exit", "blocked_unresolved_position"]
    assert summary["ending_cash"] == pytest.approx(936.70)
    assert summary["available_cash"] == pytest.approx(935.40)
    assert summary["unresolved_entry_debit"] == pytest.approx(63.30)
    assert summary["terminal_return_across_sampled_dates"] is None
    assert summary["closed_net_cash"] is None


def test_cost_stress_rechecks_affordability_instead_of_only_subtracting_profit():
    record, observations = event("2026-10-08")
    entry = record["entry_at"]
    first, second = observations[entry]
    observations[entry] = (
        CallQuote("SPY", first.expiry, first.strike, entry, 1.04, 1.05, 1, 1),
        second,
    )
    rows, _ = account([(record, observations)], 0)
    assert rows.status.iloc[0] == "closed"
    stressed, summary = account([(record, observations)], 1)
    assert stressed.status.iloc[0] == "skipped_entry"
    assert summary["ending_cash"] == 1000


def test_out_of_order_or_overlapping_events_refused():
    with pytest.raises(ValueError, match="Overlapping"):
        account([event("2026-10-14"), event("2026-10-08")], 0)


def delivery(root: Path):
    directory = root / "OPRA-TEST"
    files = directory / "files"
    files.mkdir(parents=True)
    path = files / "payload.csv"
    path.write_bytes(b"ts_recv,symbol\n")
    item = {
        "filename": path.name,
        "size": path.stat().st_size,
        "hash": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    job = {
        "id": "OPRA-TEST",
        "dataset": "OPRA.PILLAR",
        "schema": "definition",
        "start": "2026-10-08T00:00:00Z",
        "end": "2026-10-09T00:00:00Z",
        "record_count": 0,
        "files": [{**item, "verified_download": True}],
    }
    details = {
        **job,
        "state": "done",
        "encoding": "csv",
        "compression": None,
        "stype_out": "instrument_id",
        "pretty_px": True,
        "pretty_ts": True,
        "map_symbols": True,
        "limit": None,
    }
    (directory / "job-details.json").write_text(json.dumps(details))
    (directory / "vendor-files.json").write_text(json.dumps([item]))
    return job, path


def test_payload_requires_actual_vendor_hash_not_saved_verified_flag(tmp_path: Path):
    job, path = delivery(tmp_path)
    assert verified_payload(tmp_path, job)[0] == path
    path.write_bytes(b"different data")
    with pytest.raises(ValueError, match="hash mismatch"):
        verified_payload(tmp_path, job)


def test_missing_unlimited_record_evidence_and_ambiguous_jobs_refused(tmp_path: Path):
    job, _ = delivery(tmp_path)
    details_path = tmp_path / job["id"] / "job-details.json"
    details = json.loads(details_path.read_text())
    del details["limit"]
    details_path.write_text(json.dumps(details))
    with pytest.raises(ValueError, match="limit evidence"):
        verified_payload(tmp_path, job)
    job["eligible"] = True
    with pytest.raises(ValueError, match="unambiguous"):
        pick_job([job, job], "definition", job["start"], job["end"])
