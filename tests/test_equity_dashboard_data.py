"""Read-only stock dashboard data contracts."""

import hashlib
import json
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

from kq.equities.dashboard_data import load_dashboard
from kq.equities.ledger import update_ledger


def _capture(path: Path, snapshot: dict[str, object]) -> str:
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _make_data(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    source = {"captured_at": "2026-09-27T12:00:00+00:00", "benchmark": "SPY", "news": []}
    digest = _capture(tmp_path / "snapshot-first.json", source)
    at = datetime(2026, 9, 27, 12, tzinfo=UTC)
    research = pd.DataFrame(
        [
            {
                "symbol": "AAA",
                "horizon_sessions": 20,
                "as_of": at,
                "session_date": date(2026, 9, 25),
                "excess_momentum": 0.2,
                "status": "ranked",
                "close": 100.0,
                "benchmark_close": 100.0,
            }
        ]
    )
    bars = pd.DataFrame(
        [
            {
                "symbol": symbol,
                "session_date": date(2026, 9, 25),
                "open": 100.0,
                "close": 100.0,
                "volume": 1000.0,
                "as_of": datetime(2026, 9, 25, 21, tzinfo=UTC),
            }
            for symbol in ("AAA", "SPY")
        ]
    )
    update_ledger(tmp_path / "paper.sqlite", research, bars, snapshot_hash=digest, as_of=at)
    return tmp_path, source


def test_missing_ledger_never_creates_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_dashboard(tmp_path)
    assert not (tmp_path / "paper.sqlite").exists()


def test_adapter_reads_consistent_committed_state_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir, source = _make_data(tmp_path)
    ledger = data_dir / "paper.sqlite"
    before = hashlib.sha256(ledger.read_bytes()).hexdigest()
    real_connect = sqlite3.connect
    uris: list[str] = []

    def tracked_connect(
        uri: str, *, uri_mode: bool = False, **kwargs: object
    ) -> sqlite3.Connection:
        uris.append(uri)
        return real_connect(uri, uri=uri_mode, **kwargs)

    def adapter_connect(path: str, **kwargs: object) -> sqlite3.Connection:
        return tracked_connect(path, uri_mode=bool(kwargs.pop("uri", False)), **kwargs)

    monkeypatch.setattr("kq.equities.dashboard_data.sqlite3.connect", adapter_connect)
    result = load_dashboard(data_dir)
    assert result["summary"]["pending_count"] == 1
    assert result["summary"]["closed_count"] == 0
    assert result["win_rate"] is None
    assert result["source"] == source
    assert result["source_warning"] == ""
    assert result["latest_snapshot"]["snapshot_hash"] == result["state"]["last_hash"]
    assert list(result["orders"]["status"]) == ["pending"]
    assert result["trades"].empty
    assert result["forecasts"].iloc[0]["created_at"] == "2026-09-27T12:00:00+00:00"
    assert hashlib.sha256(ledger.read_bytes()).hexdigest() == before
    assert uris == [ledger.resolve().as_uri() + "?mode=ro"]
    with (
        real_connect(uris[0], uri=True) as con,
        pytest.raises(sqlite3.OperationalError, match="readonly"),
    ):
        con.execute("UPDATE state SET value='changed' WHERE key='last_hash'")


def test_unimported_and_corrupt_captures_do_not_replace_evidence(tmp_path: Path) -> None:
    data_dir, source = _make_data(tmp_path)
    _capture(data_dir / "snapshot-newer.json", {"captured_at": "2026-09-28T12:00:00+00:00"})
    (data_dir / "snapshot-corrupt.json").write_text("{not-json", encoding="utf-8")
    result = load_dashboard(data_dir)
    assert result["source"] == source
    assert result["source_warning"]
    (data_dir / "snapshot-first.json").unlink()
    missing = load_dashboard(data_dir)
    assert missing["source"] is None
    assert "match" in missing["source_warning"].lower()


def test_hit_rate_uses_closed_trade_pnl_only(tmp_path: Path) -> None:
    data_dir, _ = _make_data(tmp_path)
    with sqlite3.connect(data_dir / "paper.sqlite") as con:
        for symbol, pnl in (("BBB", 5.0), ("CCC", -2.0)):
            order = con.execute(
                "INSERT INTO paper_orders(symbol,created_at,snapshot_hash,status,reserved) "
                "VALUES(?,?,?,?,?) RETURNING id",
                (symbol, "2026-09-27T12:00:00+00:00", "test", "filled", 0.0),
            ).fetchone()[0]
            con.execute(
                "INSERT INTO paper_trades(order_id,symbol,entry_date,entry_open,shares,"
                "entry_cost,exit_date,exit_close,proceeds,net_pnl) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    order,
                    symbol,
                    "2026-09-28",
                    10.0,
                    1.0,
                    10.0,
                    "2026-10-23",
                    10.0 + pnl,
                    10.0 + pnl,
                    pnl,
                ),
            )
    result = load_dashboard(data_dir)
    assert result["win_rate"] == 0.5
    assert sorted(result["trades"]["net_pnl"].tolist()) == [-2.0, 5.0]


def test_legacy_pending_only_ledger_is_readable_with_warning(tmp_path: Path) -> None:
    data_dir, _ = _make_data(tmp_path)
    with sqlite3.connect(data_dir / "paper.sqlite") as con:
        con.execute("DELETE FROM state WHERE key IN ('last_summary','cash')")
    result = load_dashboard(data_dir)
    assert result["summary"]["cash"] == 100.0
    assert result["summary"]["reserved_cash"] == 10.0
    assert result["summary"]["equity_valid"] is True
    assert "reconstruct" in result["source_warning"].lower()


def test_malformed_state_fails_clearly(tmp_path: Path) -> None:
    data_dir, _ = _make_data(tmp_path)
    with sqlite3.connect(data_dir / "paper.sqlite") as con:
        con.execute("UPDATE state SET value='bad-json' WHERE key='last_summary'")
    with pytest.raises(ValueError, match="last_summary"):
        load_dashboard(data_dir)


def test_legacy_settled_forecasts_and_cash_are_not_reported_as_zero(tmp_path: Path) -> None:
    data_dir, _ = _make_data(tmp_path)
    with sqlite3.connect(data_dir / "paper.sqlite") as con:
        con.execute("DELETE FROM state WHERE key='last_summary'")
        con.execute("INSERT INTO state(key,value) VALUES('cash','103')")
        con.execute(
            "UPDATE forecasts SET entry_date='2026-09-28',exit_date='2026-10-02',"
            "stock_return=0.1,benchmark_return=0.05"
        )
    result = load_dashboard(data_dir)
    assert result["summary"]["pnl"] == 3.0
    assert result["summary"]["forecast_settled_count"] == 1
    assert result["summary"]["forecast_by_horizon"][1] == {
        "horizon_sessions": 20,
        "count": 1,
        "mean_stock_return": 0.1,
        "mean_benchmark_return": 0.05,
        "mean_excess_return": 0.05,
    }
    with sqlite3.connect(data_dir / "paper.sqlite") as con:
        con.execute(
            "INSERT INTO state(key,value) VALUES('pause_reason','history revision for AAA')"
        )
    assert load_dashboard(data_dir)["summary"]["forecast_valid"] is False


def test_latest_source_timestamp_must_match_snapshot_row(tmp_path: Path) -> None:
    data_dir, _ = _make_data(tmp_path)
    with sqlite3.connect(data_dir / "paper.sqlite") as con:
        con.execute(
            "UPDATE state SET value='2020-01-01T00:00:00+00:00' WHERE key='last_source_as_of'"
        )
    with pytest.raises(ValueError, match="last_source_as_of"):
        load_dashboard(data_dir)
