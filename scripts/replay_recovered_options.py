"""Offline EQUS.MINI reconstruction; protocol RECOVERED-OPTIONS-PROTOCOL-2026-10-19.

Six finite $1,000 cash accounts, not the original Yahoo replay or annual returns.
No cache catalog, acquisition, broker, external model or network fallback.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, replace
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
from scripts.run_options_pilot import select_pair

from kq.equities.opening_range import underlying_diagnostic
from kq.equities.options_replay import Observation, replay_trade
from kq.equities.options_replay import read_call_quotes as read_quotes


def verified_payload(root: Path, job: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    """Return exactly one local CSV after verifying every vendor-delivered file."""
    identifier = job["id"]
    if not re.fullmatch(r"[A-Z0-9-]+", identifier):
        raise ValueError("Invalid job ID")
    directory = root / identifier
    details = json.loads((directory / "job-details.json").read_text())
    expected = {
        "id": identifier,
        "state": "done",
        "encoding": "csv",
        "compression": None,
        "stype_out": "instrument_id",
        "pretty_px": True,
        "pretty_ts": True,
        "map_symbols": True,
        "limit": None,
    }
    if any(k not in details or details[k] != v for k, v in expected.items()):
        raise ValueError("Unexpected or incomplete job encoding/limit evidence")
    for key in ("dataset", "schema", "start", "end", "record_count"):
        if details[key] != job[key]:
            raise ValueError("Recovery receipt differs from vendor job")
    manifest = json.loads((directory / "vendor-files.json").read_text())
    receipts = {row["filename"]: row for row in job["files"]}
    if not manifest or len(receipts) != len(manifest):
        raise ValueError("Incomplete file manifest")
    csvs: list[Path] = []
    for item in manifest:
        name = item["filename"]
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or name in {".", ".."}:
            raise ValueError("Invalid delivery filename")
        receipt = receipts.get(name, {})
        if receipt.get("verified_download") is not True or any(
            receipt.get(k) != item[k] for k in ("size", "hash")
        ):
            raise ValueError("Missing verified delivery receipt")
        path = directory / "files" / name
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("Delivery path escapes recovery root")
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if path.stat().st_size != item["size"] or f"sha256:{digest}" != item["hash"]:
            raise ValueError("Vendor size/hash mismatch")
        if name.endswith(".csv"):
            csvs.append(path)
    if len(csvs) != 1:
        raise ValueError("Expected exactly one CSV payload")
    return csvs[0], details


def pick_job(jobs: list[dict[str, Any]], schema: str, start: str, end: str) -> dict[str, Any]:
    dataset = "EQUS.MINI" if schema == "ohlcv-1m" else "OPRA.PILLAR"
    matches = [
        job
        for job in jobs
        if job.get("eligible") is True
        and job["dataset"] == dataset
        and job["schema"] == schema
        and pd.Timestamp(job["start"]) == pd.Timestamp(start)
        and pd.Timestamp(job["end"]) == pd.Timestamp(end)
    ]
    if len(matches) != 1:
        raise ValueError("Expected one unambiguous frozen pilot job")
    return matches[0]


def stress_quotes(
    observations: dict[pd.Timestamp, Observation], cents: int
) -> dict[pd.Timestamp, Observation]:
    return {
        at: value
        if isinstance(value, str)
        else (
            replace(value[0], bid=value[0].bid - cents / 100, ask=value[0].ask + cents / 100),
            replace(value[1], bid=value[1].bid - cents / 100, ask=value[1].ask + cents / 100),
        )
        for at, value in observations.items()
    }


def account(
    events: list[tuple[dict[str, Any], dict[pd.Timestamp, Observation]]], cents: int
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Chronological one-spread cash ledger; missing exit halts subsequent entries."""
    cash = Decimal("1000")
    unresolved = Decimal("0")
    reserve = Decimal("0")
    realized = Decimal("0")
    closed = 0
    rows: list[dict[str, Any]] = []
    previous_exit: pd.Timestamp | None = None
    for event, observations in events:
        if previous_exit is not None and event["entry_at"] <= previous_exit:
            raise ValueError("Overlapping or unordered sampled trades")
        previous_exit = event["exit_at"]
        row = {**event, "cash_before": float(cash), "additional_cents_per_leg_side": cents}
        if unresolved:
            row.update(status="blocked_unresolved_position", reason="Prior exit remains unknown")
        elif cash < 0:
            row.update(status="blocked_cash_deficit", reason="Earlier modeled exit exhausted cash")
        else:
            result = replay_trade(
                stress_quotes(observations, cents),
                signal_at=event["signal_at"],
                entry_at=event["entry_at"],
                exit_at=event["exit_at"],
                cash_limit=float(min(cash, Decimal("100"))),
            )
            row.update(asdict(result))
            if result.entry_debit is not None:
                cash -= Decimal(str(result.entry_debit))
            if result.status == "closed":
                assert result.exit_cash is not None and result.entry_debit is not None
                cash += Decimal(str(result.exit_cash))
                realized += Decimal(str(result.exit_cash)) - Decimal(str(result.entry_debit))
                closed += 1
            elif result.status == "unresolved_exit":
                assert result.entry_debit is not None
                unresolved = Decimal(str(result.entry_debit))
                reserve = Decimal("1.30")
        row.update(
            cash_after=float(cash),
            available_cash=float(cash - reserve),
            exit_fee_reserve=float(reserve),
        )
        rows.append(row)
    summary = {
        "starting_cash": 1000,
        "ending_cash": float(cash),
        "available_cash": float(cash - reserve),
        "closed_count": closed,
        "closed_net_cash": float(realized) if closed else None,
        "unresolved_entry_debit": float(unresolved),
        "exit_fee_reserve": float(reserve),
        "terminal_return_across_sampled_dates": float(cash / 1000 - 1) if not unresolved else None,
        "daily_nav_drawdown": None,
        "annual_return": None,
        "economic_position_status": "unresolved" if unresolved else "flat",
        "cash_deficit": cash < 0,
    }
    return pd.DataFrame(rows), summary


def reconstruct(root: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError("Choose a new output; preserve previous evidence")
    recovery_path = root / "recovery.json"
    recovery = json.loads(recovery_path.read_text())
    if recovery.get("completed") is not True:
        raise ValueError("Recovery is incomplete")
    jobs = recovery["jobs"]
    bars_job = pick_job(jobs, "ohlcv-1m", "2023-03-28T00:00Z", "2026-10-17T00:00Z")
    bars_path, details = verified_payload(root, bars_job)
    if details["symbols"] != "SPY" or details["stype_in"] != "raw_symbol":
        raise ValueError("Wrong underlying job")
    bars = pd.read_csv(bars_path)
    if (
        set(bars.symbol) != {"SPY"}
        or set(bars.rtype) != {33}
        or len(bars) != details["record_count"]
    ):
        raise ValueError("Wrong underlying payload or record count")
    bars.index = pd.to_datetime(bars.ts_event, utc=True, format="ISO8601")
    regular = bars.tz_convert("America/New_York").between_time("09:30", "15:59").tz_convert("UTC")
    signals = underlying_diagnostic(regular)
    sources = [bars_job]
    events: dict[str, list[tuple[dict[str, Any], dict[pd.Timestamp, Observation]]]] = {
        "strict": [],
        "publisher_flag_sensitivity": [],
    }
    evidence: dict[str, Any] = {}
    for day in ("2026-10-08", "2026-10-14", "2026-10-15"):
        tomorrow = str((pd.Timestamp(day) + pd.Timedelta(days=1)).date())
        dj = pick_job(jobs, "definition", f"{day}T00:00Z", f"{tomorrow}T00:00Z")
        qj = pick_job(jobs, "cmbp-1", f"{day}T13:30Z", f"{day}T20:00Z")
        definitions, dd = verified_payload(root, dj)
        quotes, qd = verified_payload(root, qj)
        if (
            dd["symbols"] != "SPY.OPT"
            or dd["stype_in"] != "parent"
            or qd["stype_in"] != "raw_symbol"
        ):
            raise ValueError("Wrong option symbology")
        selected = signals.loc[signals.session.eq(day)]
        if len(selected) != 1 or selected.iloc[0].status != "underlying_only":
            raise ValueError(
                "Frozen pilot signal not reconstructed; retain failure, do not substitute"
            )
        signal = selected.iloc[0]
        close = float(regular.loc[signal.signal_at - pd.Timedelta(minutes=1), "close"])
        pair = select_pair(definitions, signal.signal_at, close, confirm_standard_spy_100=True)
        if set(pair) != set(qd["symbols"].split(",")):
            raise ValueError("Reconstructed selection differs from recovered contracts")
        event = {key: signal[key] for key in ("session", "signal_at", "entry_at", "exit_at")}
        event.update(long_symbol=pair[0], short_symbol=pair[1], signal_close=close)
        for policy, samples in events.items():
            observations = read_quotes(
                definitions,
                quotes,
                pair,
                signal.signal_at,
                (signal.entry_at, signal.exit_at),
                confirm_standard_spy_100=True,
                allow_opra_publisher_flag=policy != "strict",
            )
            samples.append((event, observations))
            evidence[f"{policy}/{day}"] = {
                str(at): obs if isinstance(obs, str) else [asdict(q) for q in obs]
                for at, obs in observations.items()
            }
        sources.extend((dj, qj))
    output.mkdir(parents=True)
    summaries: dict[str, Any] = {}
    for policy, samples in events.items():
        for cents in (0, 1, 2):
            name = f"{policy}-extra-{cents}c"
            frame, summaries[name] = account(samples, cents)
            frame.to_csv(output / f"{name}.csv", index=False)
    signals.to_csv(output / "underlying-diagnostic.csv", index=False)
    (output / "quote-evidence.json").write_text(json.dumps(evidence, indent=2, default=str))
    report = {
        "status": "retrospective_EQUS_MINI_reconstruction_not_original_Yahoo_reproduction",
        "accounts": summaries,
        "sources": sources,
        "recovery_receipt_sha256": hashlib.sha256(recovery_path.read_bytes()).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "protocol_sha256": hashlib.sha256(
            (
                Path(__file__).resolve().parents[1]
                / "docs/research/RECOVERED-OPTIONS-PROTOCOL-2026-10-19.md"
            ).read_bytes()
        ).hexdigest(),
        "limitations": [
            "Three previously viewed dates, not annual performance or unseen validation",
            "Separate-leg quotes do not prove an atomic fill; no broker eligibility verified",
            "Complete-session filter uses later data availability retrospectively",
            "No interim NAV/assignment/exercise model; unresolved exit blocks later entries",
            "Original catalog, Yahoo capture and extension stream payloads are not reconstructed",
        ],
    }
    (output / "summary.json").write_text(json.dumps(report, indent=2, allow_nan=False))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(reconstruct(args.root, args.output)["accounts"], indent=2))
