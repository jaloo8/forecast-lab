"""Frozen settings and independent accounting for parallel virtual books."""

import sqlite3
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from kq.equities.ledger import update_ledger

_LAUNCH = datetime(2026, 9, 27, 12, tzinfo=UTC)
_FRIDAY = date(2026, 9, 25)
_SESSIONS = [
    day for offset in range(30) if (day := date(2026, 9, 28) + timedelta(days=offset)).weekday() < 5
]


def _research(score: float = 0.2, holding: int = 20) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "AAA",
                "horizon_sessions": holding,
                "as_of": _LAUNCH,
                "session_date": _FRIDAY,
                "excess_momentum": score,
                "status": "ranked",
            }
        ]
    )


def _bars(days: list[date], close: float = 100.0) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": symbol,
                "session_date": day,
                "open": 100.0,
                "close": close if symbol == "AAA" and day != _FRIDAY else 100.0,
                "volume": 1000.0,
                "as_of": datetime.combine(day, datetime.min.time(), UTC) + timedelta(hours=21),
            }
            for day in [_FRIDAY, *days]
            for symbol in ("AAA", "SPY")
        ]
    )


def _state(path: Path) -> dict[str, str]:
    with sqlite3.connect(path) as con:
        return dict(con.execute("SELECT key,value FROM state"))


def test_five_and_twenty_session_books_exit_independently(tmp_path: Path) -> None:
    five = tmp_path / "five.sqlite"
    twenty = tmp_path / "twenty.sqlite"
    for path, hold, protocol in ((five, 5, "momentum-5"), (twenty, 20, "momentum-20")):
        first = update_ledger(
            path,
            _research(holding=hold),
            _bars([]),
            snapshot_hash="launch",
            as_of=_LAUNCH,
            holding_sessions=hold,
            protocol_id=protocol,
        )
        assert first["cash"] == 100.0
        assert first["pending_count"] == 1
        assert _state(path)["launched_at"] == _LAUNCH.isoformat()

    for index, day in enumerate(_SESSIONS[:20], start=1):
        outcomes = [
            update_ledger(
                path,
                _research().iloc[:0],
                _bars(_SESSIONS[:index]),
                snapshot_hash=f"session-{index}",
                as_of=datetime.combine(day, datetime.min.time(), UTC) + timedelta(hours=22),
                holding_sessions=hold,
                protocol_id=protocol,
            )
            for path, hold, protocol in ((five, 5, "momentum-5"), (twenty, 20, "momentum-20"))
        ]
        if index == 4:
            assert [result["open_count"] for result in outcomes] == [1, 1]
        if index == 5:
            assert [result["closed_count"] for result in outcomes] == [1, 0]
            assert [result["cash"] for result in outcomes] == [pytest.approx(99.98), 90.0]
        if index == 20:
            assert [result["closed_count"] for result in outcomes] == [1, 1]
            assert outcomes[1]["cash"] == pytest.approx(99.98)
    with sqlite3.connect(five) as con:
        assert con.execute("SELECT exit_date FROM paper_trades").fetchone() == (
            _SESSIONS[4].isoformat(),
        )
    with sqlite3.connect(twenty) as con:
        assert con.execute("SELECT exit_date FROM paper_trades").fetchone() == (
            _SESSIONS[19].isoformat(),
        )


def test_protocol_and_holding_period_cannot_change_even_on_replay(tmp_path: Path) -> None:
    path = tmp_path / "book.sqlite"
    first = update_ledger(
        path,
        _research(holding=5),
        _bars([]),
        snapshot_hash="launch",
        as_of=_LAUNCH,
        holding_sessions=5,
        protocol_id="momentum-5",
    )
    for hold, protocol in ((20, "momentum-5"), (5, "changed")):
        with pytest.raises(ValueError, match=r"protocol|holding"):
            update_ledger(
                path,
                _research(holding=5),
                _bars([]),
                snapshot_hash="launch",
                as_of=_LAUNCH,
                holding_sessions=hold,
                protocol_id=protocol,
            )
    replay = update_ledger(
        path,
        _research(holding=5),
        _bars([]),
        snapshot_hash="launch",
        as_of=_LAUNCH,
        holding_sessions=5,
        protocol_id="momentum-5",
    )
    assert replay == first
    assert _state(path)["holding_sessions"] == "5"
    assert _state(path)["protocol_id"] == "momentum-5"


def test_populated_legacy_book_cannot_adopt_variant(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite"
    update_ledger(path, _research(), _bars([]), snapshot_hash="launch", as_of=_LAUNCH)
    with sqlite3.connect(path) as con:
        con.execute(
            "DELETE FROM state WHERE key IN ('holding_sessions','protocol_id','launched_at')"
        )
    with pytest.raises(ValueError, match=r"legacy|protocol"):
        update_ledger(
            path,
            _research(),
            _bars([]),
            snapshot_hash="launch",
            as_of=_LAUNCH,
            holding_sessions=5,
            protocol_id="momentum-5",
        )
    assert "protocol_id" not in _state(path)
    update_ledger(path, _research(), _bars([]), snapshot_hash="launch", as_of=_LAUNCH)
    assert _state(path)["protocol_id"] == "legacy-v1"
    assert _state(path)["holding_sessions"] == "20"


def test_launch_time_is_import_time_and_replay_keeps_it(tmp_path: Path) -> None:
    path = tmp_path / "delayed.sqlite"
    imported = _LAUNCH + timedelta(hours=3)
    update_ledger(
        path,
        _research(),
        _bars([]),
        snapshot_hash="launch",
        as_of=imported,
        protocol_id="momentum-20",
    )
    assert _state(path)["launched_at"] == imported.isoformat()
    update_ledger(
        path,
        _research(),
        _bars([]),
        snapshot_hash="launch",
        as_of=imported + timedelta(hours=1),
        protocol_id="momentum-20",
    )
    assert _state(path)["launched_at"] == imported.isoformat()


@pytest.mark.parametrize("holding,protocol", [(0, "valid"), (10, "valid"), (20, "")])
def test_invalid_protocol_settings_do_not_create_book(
    tmp_path: Path, holding: int, protocol: str
) -> None:
    path = tmp_path / "invalid.sqlite"
    with pytest.raises(ValueError, match=r"protocol|holding"):
        update_ledger(
            path,
            _research(),
            _bars([]),
            snapshot_hash="launch",
            as_of=_LAUNCH,
            holding_sessions=holding,
            protocol_id=protocol,
        )
    assert not path.exists()
