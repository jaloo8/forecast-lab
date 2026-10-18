"""Offline broad-universe scan contracts using source-shaped batch captures."""

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from kq.equities.broad_scan import main, scan_captures


def _manifest(tmp_path: Path) -> Path:
    files = []
    for name, header, rows, pipes in (
        (
            "nasdaqlisted.txt",
            "Symbol|Security Name|Market Category|Test Issue|Financial Status|"
            "Round Lot Size|ETF|NextShares",
            [f"{s}|{s} Common Stock|Q|N|N|100|N|N" for s in "ABCDEF"],
            7,
        ),
        (
            "otherlisted.txt",
            "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|"
            "Test Issue|NASDAQ Symbol",
            ["G|G Common Stock|N|G|N|100|N|G"],
            6,
        ),
    ):
        trailer = "File Creation Time: 0925202621:31" + "|" * pipes
        content = "\n".join([header, *rows, trailer]) + "\n"
        (tmp_path / name).write_bytes(content.encode())
        files.append(
            {
                "file": name,
                "url": f"https://www.nasdaqtrader.com/dynamic/SymDir/{name}",
                "sha256": hashlib.sha256(content.encode()).hexdigest(),
                "lines": len(rows) + 2,
                "trailer": trailer,
            }
        )
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "captured_at": "2026-09-28T04:35:42Z",
                "sources": files,
            }
        ),
        encoding="utf-8",
    )
    return path


def _bars(symbol: str, dates: pd.DatetimeIndex, *, missing: int = -1) -> dict[str, object]:
    return {
        "symbol": symbol,
        "interval": "day",
        "bounds": "regular",
        "bars": [
            {
                "begins_at": date.strftime("%Y-%m-%dT00:00:00Z"),
                "open_price": str(100 + index * (0.2 if symbol == "A" else 0.1)),
                "close_price": str(100 + index * (0.2 if symbol == "A" else 0.1)),
                "high_price": str(101 + index * (0.2 if symbol == "A" else 0.1)),
                "low_price": str(99 + index * (0.2 if symbol == "A" else 0.1)),
                "volume": 1000,
                "session": "reg",
            }
            for index, date in enumerate(dates)
            if index != missing
        ],
    }


def _capture(
    history: Path,
    filename: str,
    symbols: list[str],
    results: list[dict[str, object]],
    *,
    not_found: list[str] | None = None,
) -> Path:
    history.mkdir(exist_ok=True)
    data: dict[str, object] = {"results": results}
    if not_found is not None:
        data["not_found"] = not_found
    payload = {
        "captured_at": "2026-09-28T04:40:52Z",
        "request": {
            "symbols": symbols,
            "interval": "day",
            "bounds": "regular",
            "adjustment_type": "split",
            "start_time": "2026-03-01T00:00:00Z",
            "end_time": "2026-09-28T00:00:00Z",
        },
        "data": data,
    }
    path = history / filename
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _setup(tmp_path: Path) -> tuple[Path, Path, pd.DatetimeIndex]:
    manifest = _manifest(tmp_path)
    history = tmp_path / "history"
    dates = pd.bdate_range("2026-03-30", periods=130)
    _capture(history, "benchmark.json", ["SPY"], [_bars("SPY", dates)])
    return manifest, history, dates


def test_partial_collection_has_every_candidate_and_existing_ranker(tmp_path: Path) -> None:
    manifest, history, dates = _setup(tmp_path)
    a = _bars("A", dates)
    for bar in a["bars"][:3]:
        bar["interpolated"] = True
    _capture(
        history,
        "batch-0000.json",
        ["A", "B", "C", "D", "E", "F"],
        [
            a,
            _bars("E", dates[:80]),
            _bars("F", dates, missing=20),
        ],
        not_found=["D"],
    )
    rankings, coverage = scan_captures(manifest, history)
    assert set(coverage["symbol"]) == set("ABCDEFG")
    statuses = coverage.set_index("symbol")["coverage_status"].to_dict()
    assert statuses == {
        "A": "ranked",
        "B": "omitted",
        "C": "omitted",
        "D": "not_found",
        "E": "insufficient_history",
        "F": "missing_shared_session",
        "G": "not_requested",
    }
    assert rankings["symbol"].tolist() == ["A", "A", "A"]
    assert rankings["horizon_sessions"].tolist() == [5, 20, 126]
    assert rankings["excess_momentum"].gt(0).all()
    assert rankings["as_of"].dt.tz is not None
    assert coverage["as_of"].dt.tz is not None
    assert coverage.set_index("symbol").loc["A", "source_file"] == "batch-0000.json"
    assert coverage.set_index("symbol").loc["A", "excluded_bar_count"] == 3


@pytest.mark.parametrize(
    "fault",
    ["unrequested", "duplicate", "bar_duplicate", "future", "format", "flag_zero", "flag_one"],
)
def test_invalid_capture_fails_closed(tmp_path: Path, fault: str) -> None:
    manifest, history, dates = _setup(tmp_path)
    result = _bars("A", dates)
    path = _capture(history, "batch-0000.json", ["A"], [result])
    payload = json.loads(path.read_text())
    if fault == "unrequested":
        payload["data"]["results"][0]["symbol"] = "B"
    elif fault == "duplicate":
        payload["data"]["results"].append(result)
    elif fault == "bar_duplicate":
        payload["data"]["results"][0]["bars"].append(result["bars"][0])
    elif fault == "future":
        payload["data"]["results"][0]["bars"][-1]["begins_at"] = "2026-10-01T00:00:00Z"
    elif fault.startswith("flag_"):
        payload["data"]["results"][0]["bars"][-1]["interpolated"] = int(fault == "flag_one")
    else:
        payload["request"]["adjustment_type"] = "none"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        scan_captures(manifest, history)


def test_cli_writes_full_coverage_without_paper_ledger(tmp_path: Path) -> None:
    manifest, history, dates = _setup(tmp_path)
    _capture(history, "supplement-0000.json", ["A"], [_bars("A", dates)])
    rankings = tmp_path / "rankings.csv"
    coverage = tmp_path / "coverage.csv"
    args = [
        "--manifest",
        str(manifest),
        "--history",
        str(history),
        "--rankings",
        str(rankings),
        "--coverage",
        str(coverage),
    ]
    assert main(args) == 0
    assert len(pd.read_csv(rankings)) == 3
    assert len(pd.read_csv(coverage)) == 7
    assert not (tmp_path / "paper.sqlite").exists()
    archived = tmp_path / "nasdaqlisted.txt"
    original = archived.read_bytes()
    assert main([*args[:5], str(archived), *args[6:]]) == 2
    assert archived.read_bytes() == original
    protected_db = tmp_path / "paper.sqlite"
    protected_db.write_bytes(b"untouched paper state")
    assert main([*args[:5], str(protected_db), *args[6:]]) == 2
    assert protected_db.read_bytes() == b"untouched paper state"


def test_one_invalid_ohlc_symbol_is_quarantined_without_hiding_good_rank(tmp_path: Path) -> None:
    manifest, history, dates = _setup(tmp_path)
    bad = _bars("B", dates)
    bad["bars"][-1]["low_price"] = "200"
    _capture(history, "batch-0000.json", ["A", "B"], [_bars("A", dates), bad])
    ranks, coverage = scan_captures(manifest, history)
    assert set(ranks["symbol"]) == {"A"}
    row = coverage.set_index("symbol").loc["B"]
    assert row["coverage_status"] == "invalid_bar"
    assert "OHLC" in row["reason"]
