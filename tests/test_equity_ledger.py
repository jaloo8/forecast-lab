"""Forward-only forecast and virtual-book invariants."""

import sqlite3
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from kq.equities.ledger import update_ledger


def _research(at: datetime, score: float = 0.2) -> pd.DataFrame:
    return pd.DataFrame(
        [
            dict(
                symbol="AAA",
                horizon_sessions=h,
                as_of=at,
                session_date=date(2026, 9, 25),
                close=100.0,
                benchmark_close=100.0,
                momentum=score,
                benchmark_momentum=0.0,
                excess_momentum=score,
                volatility_20d=0.2,
                pe_ratio=20.0,
                market_cap=1e10,
                sector="Technology",
                latest_eps_actual=1.0,
                latest_eps_estimate=0.9,
                news_count=0,
                status="ranked",
            )
            for h in (5, 20, 126)
        ]
    )


def _bars(days: list[date], *, aaa_open: float = 100.0, aaa_close: float = 100.0) -> pd.DataFrame:
    rows = []
    for day in sorted({date(2026, 9, 25), *days}):
        for symbol, open_, close in (("AAA", aaa_open, aaa_close), ("SPY", 100.0, 100.0)):
            rows.append(
                dict(
                    symbol=symbol,
                    session_date=day,
                    open=open_,
                    close=close,
                    volume=1000.0,
                    as_of=datetime.combine(day, datetime.min.time(), UTC) + timedelta(hours=21),
                )
            )
    return pd.DataFrame(rows)


def test_forward_fills_and_forecast_horizons(tmp_path: Path) -> None:
    path = tmp_path / "paper.sqlite"
    sunday = datetime(2026, 9, 27, 12, tzinfo=UTC)
    initial = update_ledger(
        path, _research(sunday), _bars([date(2026, 9, 25)]), snapshot_hash="first", as_of=sunday
    )
    assert initial["cash"] == 100.0
    assert initial["reserved_cash"] == 10.0
    assert initial["pending_count"] == 1
    assert initial["open_count"] == 0
    assert (
        update_ledger(
            path, _research(sunday), _bars([date(2026, 9, 25)]), snapshot_hash="first", as_of=sunday
        )["pending_count"]
        == 1
    )

    days = [
        date(2026, 9, 28) + timedelta(days=n)
        for n in range(30)
        if (date(2026, 9, 28) + timedelta(days=n)).weekday() < 5
    ]
    one = update_ledger(
        path,
        _research(sunday).iloc[:0],
        _bars(days[:1]),
        snapshot_hash="second",
        as_of=datetime(2026, 9, 28, 22, tzinfo=UTC),
    )
    assert one["open_count"] == 1
    assert one["pending_count"] == 0
    assert one["cash"] == 90.0
    assert one["forecast_settled_count"] == 0
    replay_old = update_ledger(
        path,
        _research(sunday),
        _bars([date(2026, 9, 25)]),
        snapshot_hash="first",
        as_of=datetime(2026, 9, 28, 23, tzinfo=UTC),
    )
    assert replay_old == one
    results = {}
    for n in range(2, 21):
        day = days[n - 1]
        results[n] = update_ledger(
            path,
            _research(sunday).iloc[:0],
            _bars(days[:n]),
            snapshot_hash=f"session-{n}",
            as_of=datetime.combine(day, datetime.min.time(), UTC) + timedelta(hours=22),
        )
    four = results[4]
    assert four["forecast_settled_count"] == 0
    five = results[5]
    assert five["forecast_settled_count"] == 1
    assert five["forecast_by_horizon"][0] == {
        "horizon_sessions": 5,
        "count": 1,
        "mean_stock_return": 0.0,
        "mean_benchmark_return": 0.0,
        "mean_excess_return": 0.0,
    }
    assert five["open_count"] == 1
    end = results[20]
    assert end["forecast_settled_count"] == 2
    assert end["closed_count"] == 1
    assert end["cash"] == pytest.approx(99.98, abs=0.001)
    assert end["closed_trades"][0]["net_pnl"] == pytest.approx(-0.02, abs=0.001)


def test_conflicting_forecast_replay_is_atomic(tmp_path: Path) -> None:
    path = tmp_path / "paper.sqlite"
    at = datetime(2026, 9, 27, 12, tzinfo=UTC)
    bars = _bars([date(2026, 9, 25)])
    update_ledger(path, _research(at), bars, snapshot_hash="same", as_of=at)
    with pytest.raises(ValueError, match="conflict"):
        update_ledger(path, _research(at, 0.3), bars, snapshot_hash="same", as_of=at)
    with sqlite3.connect(path) as con:
        assert con.execute("SELECT count(*) FROM forecasts").fetchone()[0] == 3
        assert con.execute("SELECT count(*) FROM paper_orders").fetchone()[0] == 1


def test_no_entry_without_common_future_bar_and_old_snapshot_rejected(tmp_path: Path) -> None:
    path = tmp_path / "paper.sqlite"
    at = datetime(2026, 9, 27, 12, tzinfo=UTC)
    update_ledger(path, _research(at), _bars([date(2026, 9, 25)]), snapshot_hash="one", as_of=at)
    monday_stock_only = _bars([date(2026, 9, 28)])
    monday_stock_only = monday_stock_only[
        (monday_stock_only.session_date == date(2026, 9, 25)) | (monday_stock_only.symbol == "AAA")
    ]
    result = update_ledger(
        path,
        _research(at).iloc[:0],
        monday_stock_only,
        snapshot_hash="two",
        as_of=datetime(2026, 9, 28, 22, tzinfo=UTC),
    )
    assert result["pending_count"] == 1
    assert result["open_count"] == 0
    with pytest.raises(ValueError, match="older"):
        update_ledger(
            path, _research(at).iloc[:0], _bars([date(2026, 9, 25)]), snapshot_hash="old", as_of=at
        )


def test_entered_history_revision_halts(tmp_path: Path) -> None:
    path = tmp_path / "paper.sqlite"
    at = datetime(2026, 9, 27, 12, tzinfo=UTC)
    update_ledger(path, _research(at), _bars([date(2026, 9, 25)]), snapshot_hash="one", as_of=at)
    monday = date(2026, 9, 28)
    update_ledger(
        path,
        _research(at).iloc[:0],
        _bars([monday]),
        snapshot_hash="two",
        as_of=datetime(2026, 9, 28, 22, tzinfo=UTC),
    )
    revised = _bars([monday], aaa_open=50.0)
    revised["as_of"] = datetime(2026, 9, 29, 21, tzinfo=UTC)
    result = update_ledger(
        path,
        _research(at).iloc[:0],
        revised,
        snapshot_hash="three",
        as_of=datetime(2026, 9, 29, 22, tzinfo=UTC),
    )
    assert result["paused"] is True
    assert "revision" in result["pause_reason"].lower()
    assert result["open_count"] == 1


def test_invalid_numeric_rejected_without_creating_ledger(tmp_path: Path) -> None:
    path = tmp_path / "paper.sqlite"
    at = datetime(2026, 9, 27, 12, tzinfo=UTC)
    bad = _bars([date(2026, 9, 25)])
    bad.loc[0, "open"] = float("nan")
    with pytest.raises(ValueError):
        update_ledger(path, _research(at), bad, snapshot_hash="one", as_of=at)
    assert not path.exists()


def test_five_reservations_limit_book_and_marked_loss_pauses(tmp_path: Path) -> None:
    path = tmp_path / "paper.sqlite"
    at = datetime(2026, 9, 27, 12, tzinfo=UTC)
    candidates = []
    for symbol in ("AAA", "BBB", "CCC", "DDD", "EEE", "FFF"):
        row = _research(at).query("horizon_sessions == 20").copy()
        row["symbol"] = symbol
        candidates.append(row)
    research = pd.concat(candidates, ignore_index=True)
    queued = update_ledger(
        path, research, _bars([date(2026, 9, 25)]), snapshot_hash="initial", as_of=at
    )
    assert queued["pending_count"] == 5
    assert queued["reserved_cash"] == 50.0
    assert queued["cash"] == 100.0
    with sqlite3.connect(path) as con:
        assert [r[0] for r in con.execute("SELECT symbol FROM paper_orders ORDER BY id")] == [
            "AAA",
            "BBB",
            "CCC",
            "DDD",
            "EEE",
        ]

    monday = date(2026, 9, 28)
    plunge = _bars([monday], aaa_close=1.0)
    bbb = plunge[plunge.symbol == "AAA"].copy()
    bbb["symbol"] = "BBB"
    plunge = pd.concat([plunge, bbb], ignore_index=True)
    marked = update_ledger(
        path,
        research.iloc[:0],
        plunge,
        snapshot_hash="next",
        as_of=datetime(2026, 9, 28, 22, tzinfo=UTC),
    )
    assert marked["paused"] is True
    assert marked["open_count"] == 2
    assert marked["pending_count"] == 3
    assert marked["equity"] < 90.0
    tuesday = date(2026, 9, 29)
    ccc = _bars([tuesday], aaa_close=1.0)
    ccc.loc[ccc.symbol == "AAA", "symbol"] = "CCC"
    ccc = pd.concat([plunge, ccc], ignore_index=True)
    after_pause = update_ledger(
        path,
        research.iloc[:0],
        ccc,
        snapshot_hash="later",
        as_of=datetime(2026, 9, 29, 22, tzinfo=UTC),
    )
    assert after_pause["pending_count"] == 3
    assert after_pause["open_count"] == 2


def test_sunday_night_utc_can_enter_monday_but_post_open_cannot(tmp_path: Path) -> None:
    monday = date(2026, 9, 28)
    completed = _bars([monday])
    sunday_night = datetime(2026, 9, 28, 3, 15, tzinfo=UTC)
    path = tmp_path / "early.sqlite"
    update_ledger(
        path,
        _research(sunday_night),
        _bars([date(2026, 9, 25)]),
        snapshot_hash="one",
        as_of=sunday_night,
    )
    early = update_ledger(
        path,
        _research(sunday_night).iloc[:0],
        completed,
        snapshot_hash="two",
        as_of=datetime(2026, 9, 28, 22, tzinfo=UTC),
    )
    assert early["open_count"] == 1

    after_open = datetime(2026, 9, 28, 13, 31, tzinfo=UTC)
    late_path = tmp_path / "late.sqlite"
    update_ledger(
        late_path,
        _research(after_open),
        _bars([date(2026, 9, 25)]),
        snapshot_hash="one",
        as_of=after_open,
    )
    late = update_ledger(
        late_path,
        _research(after_open).iloc[:0],
        completed,
        snapshot_hash="two",
        as_of=datetime(2026, 9, 28, 22, tzinfo=UTC),
    )
    assert late["pending_count"] == 1
    assert late["open_count"] == 0
    assert late["forecast_settled_count"] == 0


def test_forecast_without_trade_anchors_entry_against_revision(tmp_path: Path) -> None:
    path = tmp_path / "negative.sqlite"
    at = datetime(2026, 9, 27, 12, tzinfo=UTC)
    first = update_ledger(
        path, _research(at, -0.1), _bars([date(2026, 9, 25)]), snapshot_hash="one", as_of=at
    )
    assert first["pending_count"] == 0
    monday = date(2026, 9, 28)
    update_ledger(
        path,
        _research(at).iloc[:0],
        _bars([monday]),
        snapshot_hash="two",
        as_of=datetime(2026, 9, 28, 22, tzinfo=UTC),
    )
    revised_bars = _bars([monday], aaa_open=50)
    revised_bars["as_of"] = datetime(2026, 9, 29, 21, tzinfo=UTC)
    revised = update_ledger(
        path,
        _research(at).iloc[:0],
        revised_bars,
        snapshot_hash="three",
        as_of=datetime(2026, 9, 29, 22, tzinfo=UTC),
    )
    assert revised["paused"] is True
    assert revised["equity_valid"] is False
    assert revised["forecast_settled_count"] == 0


def test_missing_stock_session_does_not_stretch_forecast_horizon(tmp_path: Path) -> None:
    path = tmp_path / "missing.sqlite"
    at = datetime(2026, 9, 27, 12, tzinfo=UTC)
    update_ledger(
        path, _research(at, -0.1), _bars([date(2026, 9, 25)]), snapshot_hash="one", as_of=at
    )
    days = [date(2026, 9, 28) + timedelta(days=n) for n in (0, 1, 2, 3, 4, 7)]
    bars = _bars(days)
    bars = bars[~((bars.symbol == "AAA") & (bars.session_date == days[1]))]
    result = update_ledger(
        path,
        _research(at).iloc[:0],
        bars,
        snapshot_hash="two",
        as_of=datetime(2026, 10, 5, 22, tzinfo=UTC),
    )
    assert result["forecast_settled_count"] == 0


def test_delayed_import_uses_import_time_and_replay_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "delayed.sqlite"
    captured = datetime(2026, 9, 28, 3, 15, tzinfo=UTC)
    imported = datetime(2026, 9, 28, 14, tzinfo=UTC)
    old_bars = _bars([date(2026, 9, 25)])
    initial = update_ledger(
        path, _research(captured), old_bars, snapshot_hash="capture", as_of=imported
    )
    assert initial["pending_count"] == 1
    replay = update_ledger(
        path,
        _research(captured),
        old_bars,
        snapshot_hash="capture",
        as_of=imported + timedelta(hours=1),
    )
    assert replay["pending_count"] == 1
    with sqlite3.connect(path) as con:
        assert con.execute("SELECT count(*) FROM forecasts").fetchone()[0] == 3
        assert con.execute("SELECT count(*) FROM paper_orders").fetchone()[0] == 1
        assert (
            con.execute("SELECT created_at FROM forecasts LIMIT 1").fetchone()[0]
            == imported.isoformat()
        )
    with pytest.raises(ValueError, match="conflicting"):
        update_ledger(
            path,
            _research(captured),
            old_bars,
            snapshot_hash="changed",
            as_of=imported + timedelta(hours=2),
        )

    monday = _bars([date(2026, 9, 28)])
    seen = update_ledger(
        path,
        _research(captured).iloc[:0],
        monday,
        snapshot_hash="monday",
        as_of=datetime(2026, 9, 28, 22, tzinfo=UTC),
    )
    assert seen["pending_count"] == 1
    assert seen["open_count"] == 0


def test_entry_date_is_fixed_before_maturity(tmp_path: Path) -> None:
    path = tmp_path / "fixed-entry.sqlite"
    at = datetime(2026, 9, 27, 12, tzinfo=UTC)
    friday = date(2026, 9, 25)
    monday = date(2026, 9, 28)
    update_ledger(path, _research(at, -0.1), _bars([friday]), snapshot_hash="one", as_of=at)
    update_ledger(
        path,
        _research(at).iloc[:0],
        _bars([friday, monday]),
        snapshot_hash="two",
        as_of=datetime(2026, 9, 28, 22, tzinfo=UTC),
    )
    with sqlite3.connect(path) as con:
        assert con.execute("SELECT DISTINCT entry_date FROM forecasts").fetchall() == [
            (monday.isoformat(),)
        ]
    later = _bars(
        [
            friday,
            date(2026, 9, 29),
            date(2026, 9, 30),
            date(2026, 10, 1),
            date(2026, 10, 2),
            date(2026, 10, 5),
        ]
    )
    with pytest.raises(ValueError, match=r"coverage|truncat"):
        update_ledger(
            path,
            _research(at).iloc[:0],
            later,
            snapshot_hash="three",
            as_of=datetime(2026, 10, 5, 22, tzinfo=UTC),
        )
    with sqlite3.connect(path) as con:
        assert con.execute("SELECT DISTINCT entry_date FROM forecasts").fetchall() == [
            (monday.isoformat(),)
        ]
        assert (
            con.execute("SELECT count(*) FROM forecasts WHERE exit_date IS NOT NULL").fetchone()[0]
            == 0
        )


def test_close_drawdown_cannot_cancel_same_day_pending_open(tmp_path: Path) -> None:
    path = tmp_path / "chronology.sqlite"
    friday, monday, tuesday, wednesday = (
        date(2026, 9, 25),
        date(2026, 9, 28),
        date(2026, 9, 29),
        date(2026, 9, 30),
    )
    at = datetime(2026, 9, 27, 12, tzinfo=UTC)
    ccc_research = _research(at).copy()
    ccc_research["symbol"] = "CCC"
    starting_research = pd.concat([_research(at), ccc_research], ignore_index=True)
    friday_bars = _bars([friday])
    ccc = friday_bars[friday_bars.symbol == "AAA"].copy()
    ccc["symbol"] = "CCC"
    friday_bars = pd.concat([friday_bars, ccc], ignore_index=True)
    update_ledger(path, starting_research, friday_bars, snapshot_hash="one", as_of=at)
    monday_bars = _bars([monday])
    ccc = monday_bars[monday_bars.symbol == "AAA"].copy()
    ccc["symbol"] = "CCC"
    monday_bars = pd.concat([monday_bars, ccc], ignore_index=True)
    update_ledger(
        path,
        starting_research.iloc[:0],
        monday_bars,
        snapshot_hash="two",
        as_of=datetime(2026, 9, 28, 22, tzinfo=UTC),
    )
    tuesday_bars = _bars([monday, tuesday])
    bbb = tuesday_bars[tuesday_bars.symbol == "AAA"].copy()
    bbb["symbol"] = "BBB"
    ccc = tuesday_bars[tuesday_bars.symbol == "AAA"].copy()
    ccc["symbol"] = "CCC"
    tuesday_bars = pd.concat([tuesday_bars, bbb, ccc], ignore_index=True)
    research = (
        _research(datetime(2026, 9, 29, 22, tzinfo=UTC)).query("horizon_sessions == 20").copy()
    )
    research["symbol"] = "BBB"
    queued = update_ledger(
        path,
        research,
        tuesday_bars,
        snapshot_hash="three",
        as_of=datetime(2026, 9, 29, 22, tzinfo=UTC),
    )
    assert queued["pending_count"] == 1
    wednesday_bars = _bars([monday, tuesday, wednesday])
    bbb = wednesday_bars[wednesday_bars.symbol == "AAA"].copy()
    bbb["symbol"] = "BBB"
    ccc = wednesday_bars[wednesday_bars.symbol == "AAA"].copy()
    ccc["symbol"] = "CCC"
    wednesday_bars = pd.concat([wednesday_bars, bbb, ccc], ignore_index=True)
    wednesday_bars.loc[
        wednesday_bars.symbol.isin(["AAA", "CCC"]) & (wednesday_bars.session_date == wednesday),
        "close",
    ] = 1.0
    result = update_ledger(
        path,
        research.iloc[:0],
        wednesday_bars,
        snapshot_hash="four",
        as_of=datetime(2026, 9, 30, 22, tzinfo=UTC),
    )
    assert result["open_count"] == 3
    assert result["pending_count"] == 0
    assert result["paused"] is True


def test_active_book_rejects_multi_session_catchup_atomically(tmp_path: Path) -> None:
    path = tmp_path / "gap.sqlite"
    at = datetime(2026, 9, 27, 12, tzinfo=UTC)
    update_ledger(path, _research(at), _bars([date(2026, 9, 25)]), snapshot_hash="one", as_of=at)
    with pytest.raises(ValueError, match="multiple sessions"):
        update_ledger(
            path,
            _research(at).iloc[:0],
            _bars([date(2026, 9, 28), date(2026, 9, 29)]),
            snapshot_hash="two",
            as_of=datetime(2026, 9, 29, 22, tzinfo=UTC),
        )
    with sqlite3.connect(path) as con:
        assert con.execute("SELECT count(*) FROM snapshots").fetchone()[0] == 1
        assert con.execute("SELECT status FROM paper_orders").fetchone()[0] == "pending"


def test_existing_ledger_without_coverage_or_cached_summary_upgrades(tmp_path: Path) -> None:
    path = tmp_path / "existing.sqlite"
    at = datetime(2026, 9, 27, 12, tzinfo=UTC)
    friday, monday = date(2026, 9, 25), date(2026, 9, 28)
    first = update_ledger(path, _research(at), _bars([friday]), snapshot_hash="one", as_of=at)
    with sqlite3.connect(path) as con:
        con.execute("DROP TABLE capture_coverage")
        con.execute("DELETE FROM state WHERE key IN ('last_summary','last_processed_session')")
    replay = update_ledger(
        path, _research(at), _bars([friday]), snapshot_hash="one", as_of=at + timedelta(hours=1)
    )
    assert replay == first
    next_day = update_ledger(
        path,
        _research(at).iloc[:0],
        _bars([friday, monday]),
        snapshot_hash="two",
        as_of=datetime(2026, 9, 28, 22, tzinfo=UTC),
    )
    assert next_day["open_count"] == 1
    assert next_day["pending_count"] == 0
