"""Artificial receipts test preparation checks, never a server or trading path."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from scripts.research_floor import ROLES, bundle_digest, check, main, read_json, safe_path, template

NOW = datetime(2026, 10, 20, 20, tzinfo=UTC)


def write(root: Path, name: str, value: Any) -> dict[str, str]:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return {"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def reviews(root: Path, experiment: dict[str, Any]) -> None:
    digest = bundle_digest(experiment)
    for role in ROLES:
        experiment["reviews"][role] = {
            "status": "PASS",
            "reviewer": f"fixture-{role}",
            "bundle_sha256": digest,
            "reviewed_at": NOW.isoformat(),
            "artifact": write(root, f"{experiment['id']}/{role}.json", {"fixture": role}),
        }


def complete(root: Path, asset: str = "stock") -> dict[str, Any]:
    registry = template([f"sample:{asset}"], now=NOW)
    registry["source_commit"] = "a" * 40
    experiment = registry["experiments"][0]
    registration = write(root, "sample/registration.json", {"fixture": "frozen"})
    artifacts = [
        {**registration, "kind": "registration", "evidence_level": "specification"},
        {
            **write(root, "sample/source.py", "artificial source fixture"),
            "kind": "source",
            "evidence_level": "specification",
        },
    ]
    data = write(root, "sample/input.json", {"fixture": "artificial prices"})
    artifacts.append(
        {
            **write(root, "sample/data.json", {"files": [data]}),
            "kind": "data_manifest",
            "evidence_level": "artificial_tests",
        }
    )
    for kind in ("accounting", "causality"):
        artifacts.append(
            {
                **write(
                    root,
                    f"sample/{kind}.json",
                    {
                        "experiment_id": "sample",
                        "status": "PASS",
                        "registration_sha256": registration["sha256"],
                        "evidence_level": "artificial_tests",
                    },
                ),
                "kind": kind,
                "evidence_level": "artificial_tests",
            }
        )
    contract: dict[str, Any] = {
        "experiment_id": "sample",
        "implementation_status": "implemented",
        "paper_mode": "local_simulation",
        "initial_cash_usd": "1000.00",
        "registration_sha256": registration["sha256"],
        "share_precision": "whole",
    }
    for flag in (
        "funded_cash",
        "costs",
        "next_session_causality",
        "daily_marks",
        "missing_prices_block",
        "single_writer",
        "no_margin",
        "actual_unadjusted_prices",
        "corporate_actions",
        "settlement",
        "integer_contracts",
        "verified_contract_multiplier",
        "collateral_reservation",
        "expiry_exercise_assignment",
        "unresolved_exits_block",
        "defined_risk_only",
        "no_assumed_atomic_multileg_fill",
    ):
        contract[flag] = True
    artifacts.append(
        {
            **write(root, "sample/contract.json", contract),
            "kind": "paper_contract",
            "evidence_level": "specification",
        }
    )
    for kind in ("calendar", "feed_contract"):
        artifacts.append(
            {
                **write(root, f"sample/{kind}.json", {"fixture": kind}),
                "kind": kind,
                "evidence_level": "specification",
            }
        )
    experiment["artifacts"] = artifacts
    reviews(root, experiment)
    host: dict[str, Any] = {
        "host": "A8",
        "source_commit": registry["source_commit"],
        "checked_at": NOW.isoformat(),
        "expected_latest_session": "2026-10-19",
        "observed_latest_session": "2026-10-19",
        "new_account_directories": {"sample": experiment["state_directory"]},
    }
    for flag in (
        "read_only",
        "existing_accounts_unchanged",
        "writer_identity_verified",
        "single_writer_verified",
        "independent_feed_verified",
        "unattended_completed_run_verified",
        "exchange_calendar_verified",
        "new_account_directories_empty_verified",
    ):
        host[flag] = True
    registry["host_receipt"] = write(root, "host.json", host)
    return registry


def test_complete_evidence_never_authorizes_execution_or_writes(tmp_path: Path) -> None:
    registry = complete(tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    result = check(registry, tmp_path, now=NOW)
    assert result["status"] == "READY_FOR_MANUAL_REVIEW"
    assert result["execution_ready"] is False
    assert result["orders_submitted"] == result["network_calls"] == result["files_written"] == 0
    assert not (tmp_path / "paper-experiments").exists()
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


def test_template_is_explicitly_blocked_and_capital_is_per_account(tmp_path: Path) -> None:
    result = check(template(["trend:stock", "spread:options"], now=NOW), tmp_path, now=NOW)
    assert result["status"] == "BLOCKED"
    assert result["planned_virtual_capital_usd"] == "2000"
    assert len(result["experiments"]) == 2
    assert all(row["blockers"] for row in result["experiments"])


@pytest.mark.parametrize("value", [None, [], "PASS", 7])
def test_malformed_role_is_blocked(tmp_path: Path, value: Any) -> None:
    registry = complete(tmp_path)
    registry["experiments"][0]["reviews"]["implementer"] = value
    assert check(registry, tmp_path, now=NOW)["status"] == "BLOCKED"


@pytest.mark.parametrize("age", [timedelta(hours=25), timedelta(seconds=-1)])
def test_stale_or_future_host_attestation_is_blocked(tmp_path: Path, age: timedelta) -> None:
    registry = complete(tmp_path)
    host = read_json(tmp_path / "host.json")
    host["checked_at"] = (NOW - age).isoformat()
    registry["host_receipt"] = write(tmp_path, "host.json", host)
    assert check(registry, tmp_path, now=NOW)["status"] == "BLOCKED"


def test_fresh_receipt_cannot_mask_old_market_capture(tmp_path: Path) -> None:
    registry = complete(tmp_path)
    host = read_json(tmp_path / "host.json")
    host["expected_latest_session"] = host["observed_latest_session"] = "2020-01-02"
    registry["host_receipt"] = write(tmp_path, "host.json", host)
    assert check(registry, tmp_path, now=NOW)["status"] == "BLOCKED"


@pytest.mark.parametrize("which", ["source.py", "input.json"])
def test_changed_source_or_manifest_member_is_blocked(tmp_path: Path, which: str) -> None:
    registry = complete(tmp_path)
    (tmp_path / "sample" / which).write_text("changed", encoding="utf-8")
    assert check(registry, tmp_path, now=NOW)["status"] == "BLOCKED"


def test_updating_hash_alone_does_not_reapprove_changed_policy(tmp_path: Path) -> None:
    registry = complete(tmp_path)
    experiment = registry["experiments"][0]
    experiment["max_trials"] += 1
    result = check(registry, tmp_path, now=NOW)
    assert result["status"] == "BLOCKED"
    assert any("review evidence" in x for x in result["experiments"][0]["blockers"])


@pytest.mark.parametrize(
    "field,value",
    [
        ("initial_cash_usd", "100"),
        ("initial_cash_usd", "NaN"),
        ("initial_cash_usd", 1000),
        ("enabled", True),
        ("trials_consumed", 1),
        ("paper_mode", "live"),
        ("state_directory", "data/equities/parallel-books"),
    ],
)
def test_experiment_refuses_unsafe_or_changed_scope(tmp_path: Path, field: str, value: Any) -> None:
    registry = complete(tmp_path)
    registry["experiments"][0][field] = value
    assert check(registry, tmp_path, now=NOW)["status"] == "BLOCKED"


def test_existing_account_and_duplicate_account_are_blocked(tmp_path: Path) -> None:
    registry = complete(tmp_path)
    (tmp_path / registry["experiments"][0]["state_directory"]).mkdir(parents=True)
    registry["experiments"].append(dict(registry["experiments"][0]))
    result = check(registry, tmp_path, now=NOW)
    assert result["status"] == "BLOCKED"
    assert "duplicate experiment ID" in result["blockers"]
    assert "account state directories overlap" in result["blockers"]


@pytest.mark.parametrize("flag", ["integer_contracts", "collateral_reservation", "daily_marks"])
def test_options_incomplete_accounting_is_blocked(tmp_path: Path, flag: str) -> None:
    registry = complete(tmp_path, "options")
    experiment = registry["experiments"][0]
    contract = read_json(tmp_path / "sample/contract.json")
    contract[flag] = False
    ref = write(tmp_path, "sample/contract.json", contract)
    next(r for r in experiment["artifacts"] if r["kind"] == "paper_contract").update(ref)
    reviews(tmp_path, experiment)
    assert check(registry, tmp_path, now=NOW)["status"] == "BLOCKED"


def test_broker_mode_needs_separate_execution_evidence(tmp_path: Path) -> None:
    registry = complete(tmp_path)
    experiment = registry["experiments"][0]
    experiment["paper_mode"] = "broker_paper"
    contract = read_json(tmp_path / "sample/contract.json")
    contract["paper_mode"] = "broker_paper"
    ref = write(tmp_path, "sample/contract.json", contract)
    next(r for r in experiment["artifacts"] if r["kind"] == "paper_contract").update(ref)
    reviews(tmp_path, experiment)
    assert check(registry, tmp_path, now=NOW)["status"] == "BLOCKED"


@pytest.mark.parametrize(
    "path",
    [
        "../outside",
        "/abs",
        "C:/abs",
        "x\\y",
        "x//y",
        "x/CON",
        "x/file.",
        ".env",
        "secrets.enc.yaml",
    ],
)
def test_unsafe_evidence_path_rejected_before_reading(tmp_path: Path, path: str) -> None:
    with pytest.raises(ValueError):
        safe_path(tmp_path, path)


def test_duplicate_and_nonfinite_json_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    for text in ('{"id":1,"id":2}', '{"cost":NaN}'):
        path.write_text(text, encoding="utf-8")
        with pytest.raises(ValueError):
            read_json(path)


def test_cli_template_and_rejection(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["template", "--experiment", "trend:stock"]) == 0
    registry = json.loads(capsys.readouterr().out)
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(registry), encoding="utf-8")
    assert main(["check", "--registry", str(path), "--root", str(tmp_path)]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "BLOCKED"
