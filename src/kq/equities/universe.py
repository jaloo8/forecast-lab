"""Offline dated Nasdaq Trader listings; no price or broker eligibility claims.

``load_universe`` preserves each listing's flags, classification and UTC provenance.
Current membership must not be backdated into a historical universe.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

_FILES = {
    "nasdaqlisted.txt": (
        "Symbol|Security Name|Market Category|Test Issue|Financial Status|"
        "Round Lot Size|ETF|NextShares",
        "Symbol",
        7,
    ),
    "otherlisted.txt": (
        "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol",
        "ACT Symbol",
        6,
    ),
}
_BASE = "https://www.nasdaqtrader.com/dynamic/SymDir/"
_CREATION = re.compile(r"File Creation Time: (\d{8}\d{2}:\d{2})")
_NON_STOCK = (
    ("warrant", r"\bwarrants?\b"),
    ("unit", r"\bunits?\b"),
    ("preferred", r"\bpreferred (?:stock|shares?)\b|\bpreference shares?\b"),
    ("debt", r"\b(?:senior|convertible) notes?\b|\bnotes? due\b|\bdebentures?\b"),
)
_STOCK = re.compile(
    r"\bcommon stock\b|\bordinary shares?\b|"
    r"\bamerican depositary (?:shares?|receipts?)\b|\bads\b|\badr\b",
    re.I,
)


def _capture_time(raw: Any) -> datetime:
    value = datetime.fromisoformat(raw)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("manifest captured_at must be timezone-aware")
    value = value.astimezone(UTC)
    if value > datetime.now(UTC):
        raise ValueError("manifest capture is in the future")
    return value


def _classify(row: dict[str, str], source: str) -> tuple[str, str, str]:  # noqa: PLR0911
    name = row["Security Name"]
    if row["Test Issue"] == "Y":
        return "test", "excluded", "test_issue"
    if row["ETF"] == "Y":
        return "etf", "excluded", "etf_flag"
    if source == "nasdaqlisted.txt" and row["Financial Status"] != "N":
        return "unclassified", "review", f"financial_status_{row['Financial Status']}"
    if source == "otherlisted.txt" and row["Exchange"] in {"F", "M"}:
        return "unclassified", "review", f"unsupported_exchange_{row['Exchange']}"
    for reason, pattern in _NON_STOCK:
        if re.search(pattern, name, re.I):
            return "other_security", "excluded", reason
    if re.search(r"\bamerican depositary (?:shares?|receipts?)\b|\bads\b|\badr\b", name, re.I):
        return "stock_candidate", "candidate", "name_common_ordinary_or_adr"
    if re.search(r"\brights?\b", name, re.I):
        return "other_security", "excluded", "right"
    if _STOCK.search(name):
        return "stock_candidate", "candidate", "name_common_ordinary_or_adr"
    if re.search(r"\b(?:closed.end|exchange.traded|mutual|index) funds?\b|\betf\b", name, re.I):
        return "other_security", "excluded", "fund"
    return "unclassified", "review", "broad_candidate_name_unspecified"


def _parse_source(  # noqa: PLR0912
    path: Path, entry: dict[str, Any], captured: datetime
) -> list[dict[str, Any]]:
    filename = entry["file"]
    header, symbol_field, tail_pipes = _FILES[filename]
    if entry["url"] != _BASE + filename:
        raise ValueError(f"unexpected source URL for {filename}")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != entry["sha256"]:
        raise ValueError(f"source hash changed: {filename}")
    lines = raw.decode("utf-8-sig").splitlines()
    if len(lines) != entry["lines"] or len(lines) < 3 or lines[0] != header:
        raise ValueError(f"source header or line count invalid: {filename}")
    match = _CREATION.fullmatch(lines[-1].split("|")[0])
    if not match or lines[-1] != match.group(0) + "|" * tail_pipes:
        raise ValueError(f"source trailer invalid: {filename}")
    if lines[-1] != entry["trailer"]:
        raise ValueError(f"manifest trailer mismatch: {filename}")
    created = match.group(1)
    datetime.strptime(created, "%m%d%Y%H:%M")
    if datetime.strptime(created[:8], "%m%d%Y").date() > captured.date():
        raise ValueError(f"source creation after capture: {filename}")
    columns = header.split("|")
    result = []
    for line in lines[1:-1]:
        fields = line.split("|")
        if len(fields) != len(columns):
            raise ValueError(f"malformed directory row: {filename}")
        row = dict(zip(columns, fields, strict=True))
        symbol = row[symbol_field]
        if (
            not symbol
            or not re.fullmatch(r"[A-Z0-9.^$-]{1,14}", symbol)
            or not row["Security Name"].strip()
        ):
            raise ValueError(f"invalid symbol or name: {filename}")
        if row["Test Issue"] not in {"Y", "N"} or row["ETF"] not in {"Y", "N"}:
            raise ValueError(f"invalid issue flag: {symbol}")
        if not row["Round Lot Size"].isdigit() or int(row["Round Lot Size"]) <= 0:
            raise ValueError(f"invalid round lot: {symbol}")
        if filename == "nasdaqlisted.txt":
            if (
                row["Market Category"] not in {"Q", "G", "S"}
                or row["Financial Status"] not in {"N", "D", "E", "Q", "G", "H", "J", "K"}
                or row["NextShares"] not in {"Y", "N"}
            ):
                raise ValueError(f"invalid Nasdaq flags: {symbol}")
            exchange, market = "NASDAQ", row["Market Category"]
        else:
            if row["Exchange"] not in {"A", "N", "P", "Z", "V", "F", "M"}:
                raise ValueError(f"invalid exchange: {symbol}")
            exchange, market = row["Exchange"], ""
        category, status, reason = _classify(row, filename)
        result.append(
            {
                "symbol": symbol,
                "name": row["Security Name"].strip(),
                "exchange": exchange,
                "market_category": market,
                "category": category,
                "status": status,
                "reason": reason,
                "etf_flag": row["ETF"],
                "test_issue": row["Test Issue"],
                "financial_status": row.get("Financial Status", ""),
                "as_of": captured,
                "source_file": filename,
                "source_url": entry["url"],
                "source_sha256": digest,
                "file_created_at": created,
            }
        )
    return result


def load_universe(manifest_path: Path) -> pd.DataFrame:
    """Validate an archived two-file capture and preserve every listed security."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not isinstance(manifest.get("sources"), list):
        raise ValueError("malformed universe manifest")
    captured = _capture_time(manifest["captured_at"])
    sources = manifest["sources"]
    if len(sources) != 2 or {item["file"] for item in sources} != set(_FILES):
        raise ValueError("manifest must identify both directory files once")
    rows = []
    for entry in sources:
        rows.extend(_parse_source(manifest_path.parent / entry["file"], entry, captured))
    frame = pd.DataFrame.from_records(rows)
    if not frame["symbol"].is_unique:
        raise ValueError("duplicate symbol across directories")
    frame["as_of"] = pd.to_datetime(frame["as_of"], utc=True)
    return frame.sort_values("symbol").reset_index(drop=True)


def summarize_universe(frame: pd.DataFrame) -> dict[str, Any]:
    """Report catalogue counts without implying available prices or history."""
    return {
        "as_of": frame["as_of"].iloc[0].isoformat(),
        "total_listings": len(frame),
        "stock_candidates": int((frame["category"] == "stock_candidate").sum()),
        "broad_candidates": int((frame["reason"] == "broad_candidate_name_unspecified").sum()),
        "by_category": {str(k): int(v) for k, v in frame["category"].value_counts().items()},
        "by_status": {str(k): int(v) for k, v in frame["status"].value_counts().items()},
        "price_coverage": "unpriced",
        "historical_coverage": "not_provided",
        "scope": "Current Nasdaq Trader US listings only; not a historical universe.",
        "limitations": (
            "No delisted securities, OTC/global universe, historical membership, "
            "price, news or broker eligibility coverage. Names are classification hints."
        ),
    }


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="", dir=path.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
        handle.write(content)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    """Write a full CSV and JSON coverage summary from an offline manifest."""
    parser = argparse.ArgumentParser(description="Offline dated US listing catalogue")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.csv.suffix != ".csv" or args.summary.suffix != ".json":
            raise ValueError("universe outputs must be CSV and JSON files")
        protected = {args.manifest.resolve()} | {
            (args.manifest.parent / name).resolve() for name in _FILES
        }
        if (
            args.csv.resolve() in protected
            or args.summary.resolve() in protected
            or args.csv.resolve() == args.summary.resolve()
        ):
            raise ValueError("input and output paths must differ")
        frame = load_universe(args.manifest)
        _write(args.csv, frame.to_csv(index=False))
        _write(args.summary, json.dumps(summarize_universe(frame), indent=2) + "\n")
    except (OSError, ValueError, TypeError, KeyError, UnicodeError) as exc:
        print(f"Universe import failed: {exc}", file=sys.stderr)
        return 2
    print(f"Universe: {len(frame)} captured listings; {args.csv}; {args.summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
