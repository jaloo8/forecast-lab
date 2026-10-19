"""Reproduce registered evidence and screen complete calendar years; never place orders."""

import argparse
import csv
import hashlib
import json
import subprocess
import zipfile
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import TypedDict

from scripts.run_directional_study import PROVENANCE, PROVENANCE_SHA256, member_path

REGISTERED_STRATEGIES = (
    "spy_hold",
    "equal_sectors",
    "sector_momentum",
    "spy_trend",
    "sector_momentum_trend",
    "equal_sectors_invvol",
    "sector_momentum_invvol",
    "sector_momentum_trend_invvol",
)
REGISTERED_COSTS = ("10", "25", "50")


class AccountSummary(TypedDict):
    strategy: str
    cost_bps: int
    cagr: float
    worst_year_return: float
    max_close_drawdown: float
    years_ge_10pct: int
    years_between_10_20pct: int
    years_above_20pct: int
    losing_years: int
    passes_every_year: bool
    max_ledger_identity_error: float


def validate_case_coverage(cases: list[dict[str, str]]) -> None:
    """Require every preregistered strategy/cost account exactly once."""
    expected = {(strategy, cost) for strategy in REGISTERED_STRATEGIES for cost in REGISTERED_COSTS}
    actual = [(case["strategy"], case["cost_bps"]) for case in cases]
    if len(actual) != len(expected) or set(actual) != expected:
        raise ValueError("Expected each registered strategy/cost case exactly once")


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def prepare(source: Path, output: Path) -> None:
    """Preserve original bytes in a data-only wrapper with the loader's expected prefix."""
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    root = Path(__file__).resolve().parents[1]
    files = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")
    inventory = []
    for name in filter(None, files):
        path = root / name
        raw = path.read_bytes()
        inventory.append(
            {
                "path": name,
                "bytes": len(raw),
                "lines": len(raw.splitlines()),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "review_status": "excluded_encrypted" if name == "secrets.enc.yaml" else "pending",
            }
        )
    write_json(
        output / "inventory.json", {"files": inventory, "note": "Inventory is not semantic review."}
    )
    provenance_path = source / PROVENANCE.removeprefix("Tester/")
    raw = provenance_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != PROVENANCE_SHA256:
        raise ValueError("Frozen provenance differs; do not regenerate it")
    provenance = json.loads(raw)
    members = {PROVENANCE: raw}
    for pointer_name, meta in provenance["data"].items():
        pointer = member_path(pointer_name)
        pointer_bytes = (source / pointer).read_bytes()
        if hashlib.sha256(pointer_bytes).hexdigest() != meta["pointer_sha256"]:
            raise ValueError(f"Pointer hash differs: {pointer}")
        snapshot = member_path(meta["snapshot"])
        if json.loads(pointer_bytes)["snapshot"] != snapshot:
            raise ValueError("Pointer and provenance disagree")
        manifest_name = snapshot + "/manifest.json"
        manifest_bytes = (source / manifest_name).read_bytes()
        if hashlib.sha256(manifest_bytes).hexdigest() != meta["manifest_sha256"]:
            raise ValueError("Manifest hash differs")
        members["Tester/" + pointer] = pointer_bytes
        members["Tester/" + manifest_name] = manifest_bytes
        for info in json.loads(manifest_bytes)["files"].values():
            name = snapshot + "/" + member_path(info["file"])
            payload = (source / name).read_bytes()
            if hashlib.sha256(payload).hexdigest() != info["sha256"]:
                raise ValueError(f"Data hash differs: {name}")
            members["Tester/" + name] = payload
    archive = output / "frozen-data-wrapper.zip"
    with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED) as zipped:
        for name, payload in sorted(members.items()):
            zipped.writestr(name, payload)
    write_json(
        output / "assembly.json",
        {
            "created_utc": datetime.now(UTC).isoformat(),
            "source": str(source.resolve()),
            "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "kind": "new data-only wrapper; not original transfer archive",
            "members": {name: hashlib.sha256(raw).hexdigest() for name, raw in members.items()},
        },
    )
    print(
        json.dumps(
            {
                "files_inventoried": len(inventory),
                "lines": sum(x["lines"] for x in inventory),
                "verified_data_members": len(members),
            }
        )
    )


def calendar_returns(rows: list[dict[str, str]], capital: Decimal) -> dict[int, Decimal]:
    """Refuse incomplete windows and compute each year's wealth ratio independently."""
    if not capital.is_finite() or capital <= 0:
        raise ValueError("Invalid capital")
    years: dict[int, list[tuple[date, Decimal]]] = {}
    previous = None
    for row in rows:
        day = date.fromisoformat(row["session_date"][:10])
        nav = Decimal(row["nav"])
        if not nav.is_finite() or nav <= 0 or (previous is not None and day <= previous):
            raise ValueError("Invalid NAV or date sequence")
        years.setdefault(day.year, []).append((day, nav))
        previous = day
    if set(years) != set(range(2006, 2026)) or len(rows) != 5031:
        raise ValueError("Not the registered complete 2006-2025 window")
    returns = {}
    for year, observations in sorted(years.items()):
        if (
            observations[0][0].month != 1
            or observations[0][0].day > 7
            or observations[-1][0] < date(year, 12, 28)
        ):
            raise ValueError("Partial calendar year")
        ending = observations[-1][1]
        returns[year] = ending / capital - 1
        capital = ending
    return returns


def screen(run: Path, output: Path) -> None:
    """Check all 24 frozen paths, yearly returns and ledger costs without retuning."""
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    with (run / "metrics.csv").open(newline="", encoding="utf-8") as handle:
        expected = list(csv.DictReader(handle))
    validate_case_coverage(expected)
    summary: list[AccountSummary] = []
    annual: list[dict[str, str | int | float]] = []
    largest_return_difference = Decimal(0)
    for case in expected:
        stem = f"{case['strategy']}_c{case['cost_bps']}"
        with (run / f"{stem}_daily.csv").open(newline="", encoding="utf-8") as handle:
            daily = list(csv.DictReader(handle))
        with (run / f"{stem}_ledger.csv").open(newline="", encoding="utf-8") as handle:
            ledger = list(csv.DictReader(handle))
        returns = calendar_returns(daily, Decimal(10000))
        for row in daily:
            if Decimal(row["cash"]) < Decimal("-0.0000001"):
                raise ValueError("Negative cash")
        worst_accounting_error = Decimal(0)
        for row in ledger:
            before, after, cost = (Decimal(row[k]) for k in ("pre_nav", "post_nav", "cost"))
            error = abs(before - after - cost)
            worst_accounting_error = max(worst_accounting_error, error)
            if error > Decimal("0.000001") or abs(
                cost - Decimal(row["turnover"]) * Decimal(case["cost_bps"]) / 10000
            ) > Decimal("0.000001"):
                raise ValueError("Ledger cash/cost identity failed")
            if any(
                Decimal(value) < Decimal("-0.0000001")
                for key, value in row.items()
                if key.startswith("units_")
            ):
                raise ValueError("Negative units")
        first = Decimal(10000)
        ending = Decimal(daily[-1]["nav"])
        cagr = float((ending / first) ** (Decimal(1) / 20) - 1)
        if abs(cagr - float(case["cagr"])) > 1e-10:
            raise ValueError("CAGR mismatch")
        largest_return_difference = max(
            largest_return_difference, abs(min(returns.values()) - Decimal(case["worst_year"]))
        )
        if largest_return_difference > Decimal("0.0000000001"):
            raise ValueError("Worst-year mismatch")
        summary.append(
            {
                "strategy": case["strategy"],
                "cost_bps": int(case["cost_bps"]),
                "cagr": cagr,
                "worst_year_return": float(min(returns.values())),
                "max_close_drawdown": float(case["max_drawdown"]),
                "years_ge_10pct": sum(x >= Decimal("0.10") for x in returns.values()),
                "years_between_10_20pct": sum(
                    Decimal("0.10") <= x <= Decimal("0.20") for x in returns.values()
                ),
                "years_above_20pct": sum(x > Decimal("0.20") for x in returns.values()),
                "losing_years": sum(x < 0 for x in returns.values()),
                "passes_every_year": all(x >= Decimal("0.10") for x in returns.values()),
                "max_ledger_identity_error": float(worst_accounting_error),
            }
        )
        annual.extend(
            {
                "strategy": case["strategy"],
                "cost_bps": int(case["cost_bps"]),
                "year": y,
                "return": float(v),
            }
            for y, v in returns.items()
        )
    write_json(
        output / "screen.json",
        {
            "created_utc": datetime.now(UTC).isoformat(),
            "cases": summary,
            "annual": annual,
            "passes": sum(row["passes_every_year"] for row in summary),
            "observations_checked": sum(5031 for _ in summary),
            "independent_decimal_years": len(annual),
            "max_worst_year_error": float(largest_return_difference),
            "limitations": (
                "Previously examined adjusted history; no independent exchange-calendar proof; "
                "simulated $10000 fractional account; no taxes; closing drawdowns only."
            ),
        },
    )
    print(
        json.dumps(
            {
                "cases": len(summary),
                "passes": sum(row["passes_every_year"] for row in summary),
                "calendar_returns": len(annual),
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    assembly = sub.add_parser("prepare")
    assembly.add_argument("--source", type=Path, required=True)
    assembly.add_argument("--output", type=Path, required=True)
    audit = sub.add_parser("screen")
    audit.add_argument("--run", type=Path, required=True)
    audit.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.source, args.output)
    else:
        screen(args.run, args.output)
