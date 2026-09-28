"""Offline Nasdaq Trader directory integrity and classification contracts."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from kq.equities.universe import load_universe, main, summarize_universe

NASDAQ = (
    "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares"
)
OTHER = "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol"
CREATED = "0925202621:31"


def _fixture(tmp_path: Path) -> Path:
    sources = []
    for filename, header, rows, trailer in (
        (
            "nasdaqlisted.txt",
            NASDAQ,
            [
                "AAPL|Apple Inc. - Common Stock|Q|N|N|100|N|N",
                "ADR|Foreign Co - American Depositary Shares|G|N|N|100|N|N",
                "ETF|Example ETF|G|N|N|100|Y|N",
                "TST|Test Common Stock|S|Y|N|100|N|N",
                "WRNT|Example Warrant|G|N|N|100|N|N",
                "BAD|Example Common Stock|G|N|D|100|N|N",
            ],
            f"File Creation Time: {CREATED}|||||||",
        ),
        (
            "otherlisted.txt",
            OTHER,
            [
                "A|Agilent Technologies, Inc. Common Stock|N|A|N|100|N|A",
                "XYZ|Unspecified Holdings Inc.|P|XYZ|N|100|N|XYZ",
                "FUND|Example Preferred Stock|N|FUND|N|100|N|FUND",
                "ODD|Mystery Security|F|ODD|N|100|N|ODD",
            ],
            f"File Creation Time: {CREATED}||||||",
        ),
    ):
        content = "\n".join([header, *rows, trailer]) + "\n"
        (tmp_path / filename).write_bytes(content.encode())
        sources.append(
            {
                "file": filename,
                "url": f"https://www.nasdaqtrader.com/dynamic/SymDir/{filename}",
                "sha256": hashlib.sha256(content.encode()).hexdigest(),
                "lines": len(rows) + 2,
                "trailer": trailer,
            }
        )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "captured_at": datetime(2026, 9, 28, 4, 35, tzinfo=UTC).isoformat(),
                "sources": sources,
            }
        ),
        encoding="utf-8",
    )
    return manifest


def test_complete_rows_classification_and_provenance(tmp_path: Path) -> None:
    frame = load_universe(_fixture(tmp_path))
    assert len(frame) == 10
    assert frame["as_of"].dt.tz is not None
    rows = frame.set_index("symbol")
    assert rows.loc["AAPL", "category"] == "stock_candidate"
    assert rows.loc["AAPL", "status"] == "candidate"
    assert rows.loc["ADR", "category"] == "stock_candidate"
    assert rows.loc["A", "category"] == "stock_candidate"
    assert rows.loc["XYZ", "category"] == "unclassified"
    assert rows.loc["XYZ", "reason"] == "broad_candidate_name_unspecified"
    assert rows.loc["ODD", "status"] == "review"
    assert rows.loc["ETF", "reason"] == "etf_flag"
    assert rows.loc["TST", "reason"] == "test_issue"
    assert rows.loc["WRNT", "reason"] == "warrant"
    assert rows.loc["FUND", "reason"] == "preferred"
    assert rows.loc["BAD", "reason"] == "financial_status_D"
    assert rows.loc["AAPL", "source_file"] == "nasdaqlisted.txt"
    assert rows.loc["AAPL", "file_created_at"] == CREATED
    assert (
        rows.loc["AAPL", "source_sha256"]
        == json.loads((tmp_path / "manifest.json").read_text())["sources"][0]["sha256"]
    )
    summary = summarize_universe(frame)
    assert summary["total_listings"] == 10
    assert summary["stock_candidates"] == 3
    assert summary["broad_candidates"] == 1
    assert summary["price_coverage"] == "unpriced"
    assert summary["historical_coverage"] == "not_provided"


@pytest.mark.parametrize("damage", ["hash", "truncated", "header", "flag", "duplicate", "future"])
def test_malformed_or_revised_capture_rejected(tmp_path: Path, damage: str) -> None:
    manifest = _fixture(tmp_path)
    info = json.loads(manifest.read_text())
    nasdaq = tmp_path / "nasdaqlisted.txt"
    if damage == "hash":
        nasdaq.write_text(nasdaq.read_text().replace("Apple", "Changed"))
    elif damage == "truncated":
        nasdaq.write_text("\n".join(nasdaq.read_text().splitlines()[:-1]) + "\n")
    elif damage == "header":
        nasdaq.write_text(nasdaq.read_text().replace("Market Category", "Wrong Header"))
    elif damage == "flag":
        nasdaq.write_text(nasdaq.read_text().replace("|Q|N|N|100|N|N", "|Q|X|N|100|N|N"))
    elif damage == "duplicate":
        nasdaq.write_text(nasdaq.read_text().replace("ADR|Foreign", "AAPL|Foreign"))
    else:
        info["captured_at"] = (datetime.now(UTC) + timedelta(days=1)).isoformat()
        manifest.write_text(json.dumps(info))
    if damage in {"header", "flag", "duplicate"}:
        content = nasdaq.read_bytes()
        info["sources"][0]["sha256"] = hashlib.sha256(content).hexdigest()
        manifest.write_text(json.dumps(info))
    with pytest.raises(ValueError):
        load_universe(manifest)


def test_cli_outputs_all_rows_and_declares_coverage_limits(tmp_path: Path) -> None:
    manifest = _fixture(tmp_path)
    csv_path = tmp_path / "all.csv"
    summary_path = tmp_path / "summary.json"
    args = ["--manifest", str(manifest), "--csv", str(csv_path), "--summary", str(summary_path)]
    assert main(args) == 0
    assert len(csv_path.read_text(encoding="utf-8").splitlines()) == 11
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["total_listings"] == 10
    assert "current" in summary["scope"].lower()
    assert "delisted" in summary["limitations"].lower()


def test_actual_captured_sample_contract() -> None:
    path = Path("data/equities/universe-2026-09-28/manifest.json")
    if not path.exists():
        pytest.skip("archived local capture unavailable")
    frame = load_universe(path)
    assert len(frame) == 5636 + 7652
    rows = frame.set_index("symbol")
    for symbol in ("NTRS", "WASH", "PFBC", "WDH"):
        assert rows.loc[symbol, "category"] == "stock_candidate"
        assert rows.loc[symbol, "status"] == "candidate"
    assert rows.loc["OPENW", "reason"] == "warrant"


@pytest.mark.parametrize("source", ["nasdaqlisted.txt", "otherlisted.txt"])
def test_cli_cannot_overwrite_archived_directory_file(tmp_path: Path, source: str) -> None:
    manifest = _fixture(tmp_path)
    protected = tmp_path / source
    original = protected.read_bytes()
    args = [
        "--manifest", str(manifest), "--csv", str(protected),
        "--summary", str(tmp_path / "summary.json"),
    ]
    assert main(args) == 2
    assert protected.read_bytes() == original
    assert not (tmp_path / "summary.json").exists()
