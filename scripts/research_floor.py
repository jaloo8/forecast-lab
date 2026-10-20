"""Offline research registry and paper preparation checks; never executes a job."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import Any

ROLES = ("proposer", "data_reviewer", "implementer", "independent_reviewer", "risk_reviewer")
REQUIRED = {"registration", "source", "data_manifest", "accounting", "causality", "paper_contract"}
LEVELS = {
    "specification",
    "observed_source",
    "artificial_tests",
    "historical_simulation",
    "prospective_local_simulation",
    "broker_acknowledgement",
    "broker_fill",
    "reconciled_position",
}
_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_RESERVED = {"con", "prn", "aux", "nul"} | {
    f"{prefix}{i}" for prefix in ("com", "lpt") for i in range(1, 10)
}


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _constant(_: str) -> None:
    raise ValueError("nonfinite JSON constant")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(
        path.read_text(encoding="utf-8-sig"),
        object_pairs_hook=_object,
        parse_constant=_constant,
    )
    if not isinstance(value, dict):
        raise ValueError("JSON object required")
    return value


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def bundle_digest(experiment: dict[str, Any]) -> str:
    """Bind reviews to every experiment field except those reviews themselves."""
    return hashlib.sha256(
        _canonical({k: v for k, v in experiment.items() if k != "reviews"})
    ).hexdigest()


def _time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("aware ISO timestamp required")
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("aware ISO timestamp required")
    return result.astimezone(UTC)


def _money(value: Any) -> Decimal:
    if not isinstance(value, str):
        raise ValueError("money must be an exact decimal string")
    result = Decimal(value)
    if not result.is_finite() or result < 0:
        raise ValueError("money must be finite and nonnegative")
    return result


def safe_path(root: Path, value: Any) -> Path:
    """Resolve a portable evidence path without accepting secret files or links."""
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise ValueError("portable relative path required")
    parts = value.split("/")
    if PurePosixPath(value).is_absolute() or any(
        not part
        or part in (".", "..")
        or part[-1] in (" ", ".")
        or part.split(".")[0].casefold() in _RESERVED
        or any(ord(c) < 32 or c in '*?"<>|' for c in part)
        for part in parts
    ):
        raise ValueError("unsafe relative path")
    for part in parts:
        lower = part.casefold()
        if (
            lower.startswith((".env", "secrets", "id_rsa", "id_ed25519"))
            or lower.endswith((".pem", ".key"))
            or lower in (".ssh", ".git")
        ):
            raise ValueError("credential or Git internals path refused")
    base = root.resolve()
    target = base
    for part in parts:
        target = target / part
        if target.is_symlink() or target.is_junction():
            raise ValueError("linked evidence paths refused")
    if not target.resolve().is_relative_to(base):
        raise ValueError("path escaped evidence root")
    return target


def _artifact(root: Path, ref: Any) -> Path:
    if not isinstance(ref, dict) or not _SHA.fullmatch(str(ref.get("sha256", ""))):
        raise ValueError("artifact requires SHA256")
    path = safe_path(root, ref.get("path"))
    if not path.is_file():
        raise ValueError("artifact missing")
    with path.open("rb") as handle:
        actual = hashlib.file_digest(handle, "sha256").hexdigest()
    if actual != ref["sha256"]:
        raise ValueError("artifact digest changed")
    return path


def template(specs: list[str], *, now: datetime) -> dict[str, Any]:
    experiments = []
    for spec in specs:
        identity, separator, asset = spec.partition(":")
        if not separator or not _ID.fullmatch(identity) or asset not in ("stock", "options"):
            raise ValueError("experiment must be lowercase-id:stock or lowercase-id:options")
        experiments.append(
            {
                "id": identity,
                "asset_class": asset,
                "paper_mode": "local_simulation",
                "initial_cash_usd": "1000.00",
                "state_directory": f"paper-experiments/{identity}",
                "enabled": False,
                "max_trials": 1,
                "trials_consumed": 0,
                "artifacts": [],
                "reviews": {
                    role: {"status": "PENDING", "reviewer": None, "bundle_sha256": None}
                    for role in ROLES
                },
            }
        )
    if len({x["id"] for x in experiments}) != len(experiments):
        raise ValueError("duplicate experiment ID")
    return {
        "schema_version": 1,
        "registry_id": "a8-paper-preparation-v1",
        "created_at": now.isoformat(),
        "authority_host": "A8",
        "source_commit": None,
        "runtime_llm_enabled": False,
        "external_model_budget_usd": "0",
        "new_data_budget_usd": "0",
        "host_receipt": None,
        "experiments": experiments,
    }


def _reviews(experiment: dict[str, Any], root: Path, now: datetime) -> list[str]:
    errors = []
    reviews = experiment.get("reviews", {})
    if not isinstance(reviews, dict):
        return ["role reviews missing"]
    digest = bundle_digest(experiment)
    for role in ROLES:
        review = reviews.get(role)
        try:
            if not isinstance(review, dict) or review.get("status") != "PASS":
                raise ValueError("not approved")
            reviewer = review.get("reviewer")
            if not isinstance(reviewer, str) or not reviewer.strip():
                raise ValueError("reviewer identity missing")
            if review.get("bundle_sha256") != digest:
                raise ValueError("review applies to another bundle")
            if _time(review.get("reviewed_at")) > now:
                raise ValueError("future review")
            _artifact(root, review.get("artifact"))
        except (ValueError, OSError, InvalidOperation):
            errors.append(f"{role}: missing, changed or invalid review evidence")
    implementer_review = reviews.get("implementer")
    independent_review = reviews.get("independent_reviewer")
    implementer = (
        implementer_review.get("reviewer") if isinstance(implementer_review, dict) else None
    )
    independent = (
        independent_review.get("reviewer") if isinstance(independent_review, dict) else None
    )
    if implementer and implementer == independent:
        errors.append("independent reviewer must differ from implementer")
    return errors


def _contract(value: dict[str, Any], experiment: dict[str, Any]) -> None:
    if (
        value.get("experiment_id") != experiment["id"]
        or value.get("implementation_status") != "implemented"
        or value.get("paper_mode") != experiment.get("paper_mode")
        or _money(value.get("initial_cash_usd")) != Decimal(1000)
    ):
        raise ValueError("paper implementation contract does not match experiment")
    requirements = [
        "funded_cash",
        "costs",
        "next_session_causality",
        "daily_marks",
        "missing_prices_block",
        "single_writer",
        "no_margin",
    ]
    if experiment["asset_class"] == "options":
        requirements += [
            "integer_contracts",
            "verified_contract_multiplier",
            "collateral_reservation",
            "expiry_exercise_assignment",
            "unresolved_exits_block",
            "defined_risk_only",
            "no_assumed_atomic_multileg_fill",
        ]
    else:
        requirements += ["actual_unadjusted_prices", "corporate_actions", "settlement"]
        if value.get("share_precision") not in ("whole", "broker_verified_fractional"):
            raise ValueError("share precision missing")
    if experiment["paper_mode"] == "broker_paper":
        requirements += [
            "paper_host_allowlisted",
            "broker_account_reconciled",
            "durable_order_intents",
            "uncertain_submit_lookup_only",
            "deterministic_client_ids",
        ]
    if any(value.get(key) is not True for key in requirements):
        raise ValueError("paper accounting/execution prerequisites incomplete")


def _experiment(
    experiment: dict[str, Any], root: Path, now: datetime
) -> tuple[dict[str, Any], Path | None]:
    errors: list[str] = []
    identity = experiment.get("id")
    state: Path | None = None
    try:
        if not isinstance(identity, str) or not _ID.fullmatch(identity):
            raise ValueError("invalid experiment ID")
        if experiment.get("asset_class") not in ("stock", "options"):
            raise ValueError("unsupported asset class")
        if experiment.get("paper_mode") not in ("local_simulation", "broker_paper"):
            raise ValueError("unsupported paper mode")
        if _money(experiment.get("initial_cash_usd")) != Decimal(1000):
            raise ValueError("each new experiment must start with exactly $1000")
        if experiment.get("enabled") is not False:
            raise ValueError("preparation registry cannot enable a writer")
        limit, used = experiment.get("max_trials"), experiment.get("trials_consumed")
        if (
            type(limit) is not int
            or not 1 <= limit <= 10000
            or type(used) is not int
            or not 0 <= used < limit
        ):
            raise ValueError("invalid or exhausted finite trial cap")
        state = safe_path(root, experiment.get("state_directory"))
        if not state.is_relative_to(root.resolve() / "paper-experiments"):
            raise ValueError("new accounts require a separate paper-experiments directory")
        if state.exists():
            raise ValueError("new-account destination already exists; no resets allowed")
    except (ValueError, OSError, InvalidOperation) as exc:
        errors.append(str(exc))
    errors += _evidence(experiment, root)
    errors += _reviews(experiment, root, now)
    return {
        "id": identity,
        "asset_class": experiment.get("asset_class"),
        "initial_cash_usd": experiment.get("initial_cash_usd"),
        "bundle_sha256": bundle_digest(experiment),
        "status": "BLOCKED" if errors else "LOCAL_EVIDENCE_COMPLETE",
        "blockers": errors,
    }, state


def _evidence(experiment: dict[str, Any], root: Path) -> list[str]:  # noqa: PLR0912
    errors: list[str] = []
    kinds: set[str] = set()
    artifacts = experiment.get("artifacts", [])
    if not isinstance(artifacts, list):
        artifacts = []
        errors.append("artifact list required")
    registrations = [
        r.get("sha256")
        for r in artifacts
        if isinstance(r, dict) and r.get("kind") == "registration"
    ]
    if len(registrations) != 1:
        errors.append("exactly one frozen registration required")
    registration_sha = registrations[0] if len(registrations) == 1 else None
    for ref in artifacts:
        try:
            if not isinstance(ref, dict) or ref.get("evidence_level") not in LEVELS:
                raise ValueError("explicit evidence level required")
            kind = ref.get("kind")
            if not isinstance(kind, str) or kind not in REQUIRED | {
                "calendar",
                "feed_contract",
                "background",
            }:
                raise ValueError("unknown artifact kind")
            path = _artifact(root, ref)
            if kind == "paper_contract":
                contract = read_json(path)
                _contract(contract, experiment)
                if contract.get("registration_sha256") != registration_sha:
                    raise ValueError("paper contract registration differs")
            if kind in ("accounting", "causality"):
                validation = read_json(path)
                if (
                    validation.get("status") != "PASS"
                    or validation.get("experiment_id") != experiment.get("id")
                    or validation.get("registration_sha256") != registration_sha
                    or validation.get("evidence_level") != ref["evidence_level"]
                ):
                    raise ValueError("validation scope or registration differs")
            if kind == "data_manifest":
                files = read_json(path).get("files")
                if not isinstance(files, list) or not 1 <= len(files) <= 5000:
                    raise ValueError("data manifest must enumerate bounded local inputs")
                for member in files:
                    _artifact(root, member)
            kinds.add(kind)
        except (ValueError, OSError, InvalidOperation, KeyError):
            errors.append("artifact missing, changed or prerequisite contract invalid")
    errors += [f"missing artifact: {kind}" for kind in sorted(REQUIRED - kinds)]
    if "calendar" not in kinds or "feed_contract" not in kinds:
        errors.append("verified exchange calendar and independent feed contract required")
    return errors


def _host(registry: dict[str, Any], root: Path, now: datetime) -> list[str]:
    try:
        host = read_json(_artifact(root, registry.get("host_receipt")))
        age = now - _time(host.get("checked_at"))
        if not timedelta(0) <= age <= timedelta(hours=24):
            raise ValueError("A8 receipt is future-dated or older than 24 hours")
        if host.get("host") != "A8" or host.get("source_commit") != registry.get("source_commit"):
            raise ValueError("A8 identity or deployed source differs")
        for key in (
            "read_only",
            "existing_accounts_unchanged",
            "writer_identity_verified",
            "single_writer_verified",
            "independent_feed_verified",
            "unattended_completed_run_verified",
            "exchange_calendar_verified",
            "new_account_directories_empty_verified",
        ):
            if host.get(key) is not True:
                raise ValueError(f"A8 receipt does not verify {key}")
        expected = host.get("expected_latest_session")
        if (
            not isinstance(expected, str)
            or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", expected)
            or not 0 <= (now.date() - datetime.fromisoformat(expected).date()).days <= 7
            or host.get("observed_latest_session") != expected
        ):
            raise ValueError("capture session does not match independently expected session")
        verified = host.get("new_account_directories")
        required = {
            e["id"]: e["state_directory"] for e in registry["experiments"] if isinstance(e, dict)
        }
        if not isinstance(verified, dict) or verified != required:
            raise ValueError("A8 has not verified every new empty account directory")
    except (ValueError, OSError, KeyError, TypeError) as exc:
        return [f"A8 preflight: {exc}"]
    return []


def _tasks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions = {
        "proposer": "Freeze explicit tradable rules and finite trials before outcomes.",
        "data_reviewer": "Verify input hashes, observed timestamps, calendar and feed contract.",
        "implementer": "Implement the separate funded paper account; preserve old books.",
        "independent_reviewer": "Reconcile causal timing, cash, fees and all rejected cases.",
        "risk_reviewer": "Check actual $1000 tickets, lifecycle risks and account isolation.",
    }
    tasks = []
    for row in rows:
        for index, role in enumerate(ROLES):
            tasks.append(
                {
                    "experiment_id": row["id"],
                    "role": role,
                    "status": "PENDING" if row["blockers"] else "EVIDENCE_PRESENT",
                    "action": actions[role],
                    "depends_on": list(ROLES[:index]),
                    "bundle_sha256": row["bundle_sha256"],
                    "automatic_execution": False,
                }
            )
    return tasks


def check(  # noqa: PLR0912
    registry: dict[str, Any], root: Path, *, now: datetime
) -> dict[str, Any]:
    """Inspect local evidence only; complete receipts still require operator review."""
    errors: list[str] = []
    if now.tzinfo is None:
        raise ValueError("aware check clock required")
    try:
        if registry.get("schema_version") != 1 or registry.get("authority_host") != "A8":
            raise ValueError("unsupported registry or authority")
        if _time(registry.get("created_at")) > now:
            raise ValueError("future registry")
        if not _COMMIT.fullmatch(str(registry.get("source_commit", ""))):
            raise ValueError("pinned source commit missing")
        if registry.get("runtime_llm_enabled") is not False:
            raise ValueError("runtime model calls not supported")
        for key in ("external_model_budget_usd", "new_data_budget_usd"):
            if _money(registry.get(key)) != 0:
                raise ValueError("this offline workflow accepts zero external spend only")
    except (ValueError, InvalidOperation) as exc:
        errors.append(str(exc))
    experiments = registry.get("experiments", [])
    if not isinstance(experiments, list) or not 1 <= len(experiments) <= 500:
        errors.append("one to 500 explicit experiments required")
        experiments = []
    rows: list[dict[str, Any]] = []
    directories: list[str] = []
    ids: set[str] = set()
    for experiment in experiments:
        if not isinstance(experiment, dict):
            errors.append("experiment must be an object")
            continue
        row, state = _experiment(experiment, root, now)
        if row["id"] in ids:
            errors.append("duplicate experiment ID")
        ids.add(row["id"])
        if state:
            text = state.as_posix().casefold()
            if any(
                text == p or text.startswith(p + "/") or p.startswith(text + "/")
                for p in directories
            ):
                errors.append("account state directories overlap")
            directories.append(text)
        rows.append(row)
    errors += _host(registry, root, now)
    blocked = bool(errors) or any(row["blockers"] for row in rows)
    return {
        "status": "BLOCKED" if blocked else "READY_FOR_MANUAL_REVIEW",
        "checked_at": now.isoformat(),
        "execution_ready": False,
        "network_calls": 0,
        "orders_submitted": 0,
        "files_written": 0,
        "experiment_count": len(rows),
        "planned_virtual_capital_usd": str(Decimal(1000) * len(rows)),
        "registry_sha256": hashlib.sha256(_canonical(registry)).hexdigest(),
        "blockers": errors,
        "experiments": rows,
        "role_tasks": _tasks(rows),
        "limits": [
            "Hashes verify local bytes, not the truth or authenticity of supplied attestations.",
            "No host login, live feed check, broker reconciliation or order execution performed.",
            "Passing preparation is not a strategy promotion or proof of profitability.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("template", help="Emit a disabled registry template to stdout")
    create.add_argument("--experiment", action="append", required=True)
    for name in ("check", "review-digests"):
        child = sub.add_parser(name)
        child.add_argument("--registry", type=Path, required=True)
        if name == "check":
            child.add_argument("--root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "template":
            result = template(args.experiment, now=datetime.now(UTC))
        else:
            registry = read_json(args.registry)
            if args.command == "check":
                result = check(registry, args.root, now=datetime.now(UTC))
            else:
                result = {row["id"]: bundle_digest(row) for row in registry.get("experiments", [])}
        print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
        return 2 if result.get("status") == "BLOCKED" else 0
    except (ValueError, OSError, KeyError, TypeError, InvalidOperation):
        print("Research preflight refused malformed or unavailable input.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
