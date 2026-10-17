"""Delayed recognition preserves old instructions without hindsight decisions."""

import json
import sqlite3
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from kq.equities import ledger
from kq.equities.ledger import update_ledger

START = date(2026, 9, 25)
CREATED = datetime(2026, 9, 27, 12, tzinfo=UTC)
OBSERVED = datetime(2026, 10, 10, 12, tzinfo=UTC)
DAYS = [START + timedelta(days=n) for n in range(15) if (START + timedelta(days=n)).weekday() < 5]


def _bars(symbols: tuple[str, ...] = ("AAA",), days: list[date] = DAYS) -> pd.DataFrame:
    return pd.DataFrame(
        [
            dict(
                symbol=symbol,
                session_date=day,
                open=100.0,
                close=100.0,
                volume=1000.0,
                as_of=CREATED if day == START else OBSERVED,
            )
            for day in days
            for symbol in (*symbols, "SPY")
        ]
    )


def _research(at: datetime, horizon: int, symbols: tuple[str, ...] = ("AAA",)) -> pd.DataFrame:
    return pd.DataFrame(
        [
            dict(
                symbol=symbol,
                horizon_sessions=horizon,
                as_of=at,
                session_date=START if at == CREATED else DAYS[-1],
                excess_momentum=0.2,
                status="ranked",
            )
            for symbol in symbols
        ]
    )


def _seed(path: Path, horizon: int = 5, symbols: tuple[str, ...] = ("AAA",)) -> None:
    update_ledger(
        path,
        _research(CREATED, horizon, symbols),
        _bars(symbols, [START]),
        snapshot_hash="initial",
        as_of=CREATED,
        holding_sessions=horizon,
    )


def _dump(path: Path) -> str:
    with sqlite3.connect(path) as con:
        return "\n".join(con.iterdump())


@pytest.mark.parametrize("horizon,closed,opened", [(5, 1, 0), (20, 0, 1)])
def test_recovery_recognizes_only_existing_instructions_and_uses_actual_clock(
    tmp_path: Path, horizon: int, closed: int, opened: int
) -> None:
    path = tmp_path / "paper.sqlite"
    _seed(path, horizon)
    result = update_ledger(
        path,
        _research(OBSERVED, horizon),
        _bars(),
        snapshot_hash="recovered",
        as_of=OBSERVED,
        holding_sessions=horizon,
        recover_missed_sessions=True,
    )
    assert (result["closed_count"], result["open_count"]) == (closed, opened)
    assert result["delayed_recovery"]["prior_session"] == START.isoformat()
    assert result["delayed_recovery"]["through_session"] == DAYS[-1].isoformat()
    assert result["delayed_recovery"]["recognized_at"] == OBSERVED.isoformat()
    assert result["delayed_recovery"]["missed_sessions_count"] == len(DAYS) - 1
    assert result["delayed_recovery"]["fill_count"] == 1
    assert result["delayed_recovery"]["exit_count"] == closed
    with sqlite3.connect(path) as con:
        trades = con.execute("SELECT entry_date,exit_date FROM paper_trades").fetchall()
        assert trades == [("2026-09-28", "2026-10-02" if horizon == 5 else None)]
        orders = con.execute("SELECT created_at,status FROM paper_orders ORDER BY id").fetchall()
        assert orders == [(CREATED.isoformat(), "filled")] + (
            [(OBSERVED.isoformat(), "pending")] if horizon == 5 else []
        )
        assert con.execute("SELECT count(*) FROM forecasts").fetchone()[0] == 2
        assert con.execute("SELECT count(*) FROM snapshots").fetchone()[0] == 2
        audit = con.execute(
            "SELECT observed_at,snapshot_hash,prior_session,current_session,"
            "sessions,events FROM recovery_runs"
        ).fetchone()
        assert audit[:4] == (
            OBSERVED.isoformat(),
            "recovered",
            START.isoformat(),
            DAYS[-1].isoformat(),
        )
        assert json.loads(audit[4]) == [day.isoformat() for day in DAYS[1:]]
        events = json.loads(audit[5])
        assert any(e["kind"] == "delayed_fill" and e["order_id"] == 1 for e in events)
        assert any(e["kind"] == "delayed_exit" for e in events) == bool(closed)
    before = _dump(path)
    assert (
        update_ledger(
            path,
            _research(OBSERVED, horizon),
            _bars(),
            snapshot_hash="recovered",
            as_of=OBSERVED,
            holding_sessions=horizon,
            recover_missed_sessions=True,
        )
        == result
    )
    assert _dump(path) == before


def test_intermediate_loss_stays_paused_after_rebound(tmp_path: Path) -> None:
    path = tmp_path / "paper.sqlite"
    symbols = ("AAA", "BBB")
    _seed(path, 5, symbols)
    bars = _bars(symbols)
    bars.loc[(bars.session_date == DAYS[2]) & (bars.symbol != "SPY"), "close"] = 1.0
    result = update_ledger(
        path,
        _research(OBSERVED, 5, symbols),
        bars,
        snapshot_hash="recovery",
        as_of=OBSERVED,
        holding_sessions=5,
        recover_missed_sessions=True,
    )
    assert result["paused"]
    assert result["equity"] > 99
    assert result["closed_count"] == 2
    assert result["pending_count"] == 0
    assert result["delayed_recovery"]["max_drawdown_recovered"] > 0.19
    assert result["delayed_recovery"]["minimum_equity"] < 81
    assert result["delayed_recovery"]["peak_equity"] == 100
    assert result["delayed_recovery"]["last_run_peak_equity"] == 100
    assert result["delayed_recovery"]["last_run_minimum_equity"] < 81
    with sqlite3.connect(path) as con:
        events = json.loads(con.execute("SELECT events FROM recovery_runs").fetchone()[0])
        assert any(
            e["kind"] == "loss_pause" and e["session"] == DAYS[2].isoformat() for e in events
        )


@pytest.mark.parametrize("failure", ["held", "benchmark", "zero_volume", "synthetic", "revision"])
def test_recovery_refuses_incomplete_or_revised_evidence_atomically(
    tmp_path: Path, failure: str
) -> None:
    path = tmp_path / "paper.sqlite"
    _seed(path, 20)
    first = _bars(days=DAYS[:2])
    first["as_of"] = datetime(2026, 9, 28, 22, tzinfo=UTC)
    update_ledger(
        path,
        _research(CREATED, 20).iloc[:0],
        first,
        snapshot_hash="first-fill",
        as_of=datetime(2026, 9, 28, 23, tzinfo=UTC),
    )
    bars = _bars()
    if failure in ("held", "benchmark"):
        symbol = "AAA" if failure == "held" else "SPY"
        bars = bars[~((bars.symbol == symbol) & (bars.session_date == DAYS[3]))]
    elif failure == "revision":
        bars.loc[(bars.symbol == "AAA") & (bars.session_date == DAYS[1]), "open"] = 99
    elif failure == "zero_volume":
        bars.loc[(bars.symbol == "SPY") & (bars.session_date == DAYS[3]), "volume"] = 0
    else:
        bars["interpolated"] = False
        bars.loc[(bars.symbol == "AAA") & (bars.session_date == DAYS[3]), "interpolated"] = True
    before = _dump(path)
    with pytest.raises(ValueError, match=r"missing|genuine|revision"):
        update_ledger(
            path,
            _research(OBSERVED, 20),
            bars,
            snapshot_hash="bad",
            as_of=OBSERVED,
            recover_missed_sessions=True,
        )
    assert _dump(path) == before


def test_default_outage_guard_remains(tmp_path: Path) -> None:
    path = tmp_path / "paper.sqlite"
    _seed(path, 20)
    before = _dump(path)
    with pytest.raises(ValueError, match="cannot catch up"):
        update_ledger(
            path, _research(OBSERVED, 20), _bars(), snapshot_hash="no-opt-in", as_of=OBSERVED
        )
    assert _dump(path) == before


def test_recovery_label_survives_normal_refresh(tmp_path: Path) -> None:
    path = tmp_path / "paper.sqlite"
    _seed(path, 20)
    recovered = update_ledger(
        path,
        _research(OBSERVED, 20),
        _bars(),
        snapshot_hash="recover",
        as_of=OBSERVED,
        recover_missed_sessions=True,
    )
    latest = datetime(2026, 10, 12, 22, tzinfo=UTC)
    bars = _bars(days=[*DAYS, date(2026, 10, 12)])
    bars["as_of"] = latest
    result = update_ledger(
        path, _research(latest, 20).iloc[:0], bars, snapshot_hash="normal", as_of=latest
    )
    assert result["delayed_recovery"] == recovered["delayed_recovery"]


def test_transaction_rolls_back_if_daily_recognition_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "paper.sqlite"
    _seed(path, 20)
    before = _dump(path)

    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("injected interrupted recovery")

    monkeypatch.setattr(ledger, "_summary", fail)
    with pytest.raises(RuntimeError, match="interrupted"):
        update_ledger(
            path,
            _research(OBSERVED, 20),
            _bars(),
            snapshot_hash="interrupted",
            as_of=OBSERVED,
            recover_missed_sessions=True,
        )
    assert _dump(path) == before


def test_after_open_order_is_not_filled_at_an_earlier_open(tmp_path: Path) -> None:
    path = tmp_path / "paper.sqlite"
    created = datetime(2026, 9, 28, 15, tzinfo=UTC)
    research = _research(CREATED, 5)
    research["as_of"] = created
    update_ledger(
        path,
        research,
        _bars(days=[START]),
        snapshot_hash="created-after-open",
        as_of=created,
        holding_sessions=5,
    )
    update_ledger(
        path,
        _research(OBSERVED, 5).iloc[:0],
        _bars(),
        snapshot_hash="recovered",
        as_of=OBSERVED,
        holding_sessions=5,
        recover_missed_sessions=True,
    )
    with sqlite3.connect(path) as con:
        assert con.execute("SELECT entry_date,exit_date FROM paper_trades").fetchall() == [
            ("2026-09-29", "2026-10-05")
        ]


@pytest.mark.parametrize("invalid", ["after_benchmark", "weekend"])
def test_recovery_rejects_non_session_marks(tmp_path: Path, invalid: str) -> None:
    path = tmp_path / "paper.sqlite"
    _seed(path, 20)
    bars = _bars()
    extra = (
        _bars(days=[date(2026, 10, 3)])
        if invalid == "weekend"
        else _bars(days=[OBSERVED.date()]).query("symbol == 'AAA'")
    )
    bars = pd.concat([bars, extra], ignore_index=True)
    before = _dump(path)
    with pytest.raises(ValueError, match=r"session|benchmark"):
        update_ledger(
            path,
            _research(OBSERVED, 20),
            bars,
            snapshot_hash="invalid-session",
            as_of=OBSERVED,
            recover_missed_sessions=True,
        )
    assert _dump(path) == before


def test_fresh_same_session_recovery_is_read_only(tmp_path: Path) -> None:
    path = tmp_path / "paper.sqlite"
    _seed(path, 20)
    result = update_ledger(
        path,
        _research(OBSERVED, 20),
        _bars(),
        snapshot_hash="recovered",
        as_of=OBSERVED,
        recover_missed_sessions=True,
    )
    before = _dump(path)
    later = OBSERVED + timedelta(hours=1)
    bars = _bars()
    bars["as_of"] = later
    changed = _research(later, 20, ("BBB",))
    assert (
        update_ledger(
            path,
            changed,
            bars,
            snapshot_hash="fresh-same-session",
            as_of=later,
            recover_missed_sessions=True,
        )
        == result
    )
    assert _dump(path) == before
    for invalid in ("missing", "revision"):
        bad = bars.copy()
        if invalid == "missing":
            bad = bad[~((bad.symbol == "AAA") & (bad.session_date == DAYS[2]))]
        else:
            bad.loc[(bad.symbol == "AAA") & (bad.session_date == DAYS[1]), "open"] = 99
        with pytest.raises(ValueError, match=r"coverage|revision"):
            update_ledger(
                path,
                changed,
                bad,
                snapshot_hash="invalid-same-session",
                as_of=later,
                recover_missed_sessions=True,
            )
        assert _dump(path) == before


def test_one_new_session_with_recovery_enabled_is_normal_recognition(tmp_path: Path) -> None:
    path = tmp_path / "paper.sqlite"
    _seed(path, 20)
    bars = _bars(days=DAYS[:2])
    now = datetime(2026, 9, 29, 1, tzinfo=UTC)
    bars["as_of"] = now
    result = update_ledger(
        path,
        _research(now, 20).iloc[:0],
        bars,
        snapshot_hash="one-session",
        as_of=now,
        recover_missed_sessions=True,
    )
    assert result["open_count"] == 1
    assert result["delayed_recovery"] is None
    with sqlite3.connect(path) as con:
        assert not con.execute(
            "SELECT name FROM sqlite_master WHERE name='recovery_runs'"
        ).fetchone()
