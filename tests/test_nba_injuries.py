"""Tests for the NBA injury parser + repository + ingest flow.

Coverage:
- parse_status: canonical forms + the common synonyms + reject path.
- parse_as_of: ISO with offset, ISO with Z, date-only.
- parse_csv_rows / parse_csv_text: round-trip on synthetic rows;
  rejection on missing columns; tolerance of empty optional fields.
- Repository: upsert idempotency, fetch_latest_per_player picks max
  as_of per player, team filter, date filter.
- Flow: no-op without --csv (the safe-to-cron property), end-to-end
  ingest from a real CSV file, FileNotFoundError on bad path.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from kq.clients.nba_injuries import (
    INJURY_STATUSES,
    InjuryRow,
    parse_as_of,
    parse_csv_file,
    parse_csv_rows,
    parse_csv_text,
    parse_status,
)
from kq.flows.ingest_nba_injuries import main as run_ingest
from kq.storage.duckdb_store import bootstrap
from kq.storage.repositories.nba_injuries import (
    fetch_for_team,
    fetch_latest_per_player,
    upsert_injuries,
)

# --------------------------- parse_status ---------------------------


def test_parse_status_canonical_forms() -> None:
    for s in INJURY_STATUSES:
        assert parse_status(s) == s
        assert parse_status(s.lower()) == s
        assert parse_status(s.title()) == s


def test_parse_status_synonyms() -> None:
    assert parse_status("Day-to-Day") == "QUESTIONABLE"
    assert parse_status("Game Time Decision") == "QUESTIONABLE"
    assert parse_status("GTD") == "QUESTIONABLE"
    assert parse_status("Active") == "AVAILABLE"
    assert parse_status("Inactive") == "OUT"


def test_parse_status_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="unknown injury status"):
        parse_status("Maybe playing")


def test_parse_status_strips_whitespace() -> None:
    assert parse_status("  out  ") == "OUT"


# --------------------------- parse_as_of ---------------------------


def test_parse_as_of_iso_with_offset() -> None:
    parsed = parse_as_of("2026-05-04T18:30:00+00:00")
    assert parsed == datetime(2026, 5, 4, 18, 30, tzinfo=UTC)


def test_parse_as_of_iso_with_z() -> None:
    parsed = parse_as_of("2026-05-04T18:30:00Z")
    assert parsed == datetime(2026, 5, 4, 18, 30, tzinfo=UTC)


def test_parse_as_of_date_only_becomes_midnight_utc() -> None:
    parsed = parse_as_of("2026-05-04")
    assert parsed == datetime(2026, 5, 4, 0, 0, tzinfo=UTC)


def test_parse_as_of_rejects_empty() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        parse_as_of("")


def test_parse_as_of_rejects_garbage() -> None:
    with pytest.raises(ValueError, match="unparseable"):
        parse_as_of("not a date")


# --------------------------- parse_csv_rows ---------------------------


def _good_row() -> dict[str, str]:
    return {
        "player_id": "2544",
        "player_name": "LeBron James",
        "team_abbr": "LAL",
        "status": "Questionable",
        "reason": "left ankle sprain",
        "as_of": "2026-05-04T18:30:00Z",
    }


def test_parse_csv_rows_one_good_row() -> None:
    rows = parse_csv_rows([_good_row()])
    assert len(rows) == 1
    r = rows[0]
    assert r.player_id == "2544"
    assert r.player_name == "LeBron James"
    assert r.team_abbr == "LAL"
    assert r.status == "QUESTIONABLE"
    assert r.reason == "left ankle sprain"
    assert r.as_of == datetime(2026, 5, 4, 18, 30, tzinfo=UTC)


def test_parse_csv_rows_handles_empty_reason() -> None:
    raw = _good_row()
    raw["reason"] = ""
    rows = parse_csv_rows([raw])
    assert rows[0].reason is None


def test_parse_csv_rows_skips_incomplete_row() -> None:
    """An empty player_id row is silently skipped, not raised."""
    raw = _good_row()
    raw["player_id"] = ""
    rows = parse_csv_rows([raw])
    assert rows == []


def test_parse_csv_rows_normalizes_team_abbr_case() -> None:
    raw = _good_row()
    raw["team_abbr"] = "lal"
    rows = parse_csv_rows([raw])
    assert rows[0].team_abbr == "LAL"


def test_parse_csv_rows_rejects_missing_required_column() -> None:
    raw = _good_row()
    del raw["status"]
    with pytest.raises(ValueError, match="missing required CSV columns"):
        parse_csv_rows([raw])


def test_parse_csv_rows_skips_row_with_unknown_status() -> None:
    """2026-07-01 audit (Tier 2): one unrecognized status must not abort
    the whole report — skip-and-count, keep the good rows."""
    bad = _good_row()
    bad["player_id"] = "9999"
    bad["status"] = "Maybe playing"
    rows = parse_csv_rows([_good_row(), bad])
    assert len(rows) == 1
    assert rows[0].player_id == "2544"


def test_parse_csv_rows_skips_row_with_bad_timestamp() -> None:
    bad = _good_row()
    bad["player_id"] = "9999"
    bad["as_of"] = "yesterday-ish"
    rows = parse_csv_rows([_good_row(), bad])
    assert len(rows) == 1
    assert rows[0].player_id == "2544"


def test_parse_csv_rows_raises_when_all_rows_malformed() -> None:
    """A systematically-broken export (every row unparseable) still fails
    loudly instead of quietly ingesting nothing."""
    bad1 = _good_row()
    bad1["status"] = "Maybe playing"
    bad2 = _good_row()
    bad2["player_id"] = "9999"
    bad2["as_of"] = "not a date"
    with pytest.raises(ValueError, match="all 2 rows malformed"):
        parse_csv_rows([bad1, bad2])


def test_parse_csv_text_survives_one_malformed_row() -> None:
    csv_text = (
        "player_id,player_name,team_abbr,status,reason,as_of\n"
        "2544,LeBron James,LAL,Out,Left ankle sprain,2026-05-04T18:30:00Z\n"
        "1628369,Jayson Tatum,BOS,Vibes only,,2026-05-04\n"  # unknown status
        "201939,Stephen Curry,GSW,Available,,2026-05-04\n"
    )
    rows = parse_csv_text(csv_text)
    assert {r.player_id for r in rows} == {"2544", "201939"}


def test_parse_csv_text_round_trip() -> None:
    csv_text = (
        "player_id,player_name,team_abbr,status,reason,as_of\n"
        "2544,LeBron James,LAL,Out,Left ankle sprain,2026-05-04T18:30:00Z\n"
        "1628369,Jayson Tatum,BOS,Available,,2026-05-04\n"
    )
    rows = parse_csv_text(csv_text)
    assert len(rows) == 2
    assert {r.player_id for r in rows} == {"2544", "1628369"}
    assert rows[0].status == "OUT"
    assert rows[1].status == "AVAILABLE"
    assert rows[1].reason is None
    assert rows[1].as_of == datetime(2026, 5, 4, 0, 0, tzinfo=UTC)


def test_parse_csv_file_round_trip(tmp_path: Path) -> None:
    csv_path = tmp_path / "injuries.csv"
    csv_path.write_text(
        "player_id,player_name,team_abbr,status,reason,as_of\n"
        "2544,LeBron James,LAL,Out,Left ankle,2026-05-04T18:30:00Z\n",
        encoding="utf-8",
    )
    rows = parse_csv_file(csv_path)
    assert len(rows) == 1
    assert rows[0].player_name == "LeBron James"


# --------------------------- repository ---------------------------


def _new_db(tmp_path: Path) -> Path:
    db = tmp_path / "injuries.duckdb"
    bootstrap(db)
    return db


def test_upsert_round_trip(tmp_path: Path) -> None:
    db = _new_db(tmp_path)
    con = duckdb.connect(str(db))
    rows = [
        InjuryRow(
            player_id="2544",
            player_name="LeBron James",
            team_abbr="LAL",
            status="OUT",
            reason="left ankle",
            as_of=datetime(2026, 5, 4, 18, 30, tzinfo=UTC),
        ),
    ]
    n = upsert_injuries(con, rows)
    assert n == 1
    out = fetch_latest_per_player(con)
    assert len(out) == 1
    assert out[0]["player_id"] == "2544"
    assert out[0]["status"] == "OUT"
    con.close()


def test_upsert_empty_is_noop(tmp_path: Path) -> None:
    db = _new_db(tmp_path)
    con = duckdb.connect(str(db))
    assert upsert_injuries(con, []) == 0
    assert fetch_latest_per_player(con) == []
    con.close()


def test_upsert_is_idempotent_on_pk(tmp_path: Path) -> None:
    """Re-upserting same (player_id, as_of) -> one row in the table."""
    db = _new_db(tmp_path)
    con = duckdb.connect(str(db))
    row = InjuryRow(
        player_id="2544",
        player_name="LeBron James",
        team_abbr="LAL",
        status="OUT",
        reason=None,
        as_of=datetime(2026, 5, 4, 18, 30, tzinfo=UTC),
    )
    upsert_injuries(con, [row])
    upsert_injuries(con, [row])
    count = con.execute("SELECT COUNT(*) FROM nba_injury").fetchone()
    assert count is not None and count[0] == 1
    con.close()


def test_fetch_latest_per_player_picks_max_as_of(tmp_path: Path) -> None:
    """Two rows for the same player at different as_of -> latest wins."""
    db = _new_db(tmp_path)
    con = duckdb.connect(str(db))
    early = datetime(2026, 5, 3, 18, 0, tzinfo=UTC)
    late = early + timedelta(days=1)
    upsert_injuries(
        con,
        [
            InjuryRow(
                player_id="2544",
                player_name="LeBron James",
                team_abbr="LAL",
                status="QUESTIONABLE",
                reason=None,
                as_of=early,
            ),
            InjuryRow(
                player_id="2544",
                player_name="LeBron James",
                team_abbr="LAL",
                status="OUT",
                reason="left ankle",
                as_of=late,
            ),
        ],
    )
    latest = fetch_latest_per_player(con)
    assert len(latest) == 1
    assert latest[0]["status"] == "OUT"
    assert latest[0]["as_of"] == late.replace(tzinfo=None)
    # Both rows should still be in the raw table.
    raw = con.execute("SELECT COUNT(*) FROM nba_injury").fetchone()
    assert raw is not None and raw[0] == 2
    con.close()


def test_fetch_latest_per_player_team_filter(tmp_path: Path) -> None:
    db = _new_db(tmp_path)
    con = duckdb.connect(str(db))
    upsert_injuries(
        con,
        [
            InjuryRow(
                player_id="2544",
                player_name="LeBron James",
                team_abbr="LAL",
                status="OUT",
                reason=None,
                as_of=datetime(2026, 5, 4, tzinfo=UTC),
            ),
            InjuryRow(
                player_id="1628369",
                player_name="Jayson Tatum",
                team_abbr="BOS",
                status="QUESTIONABLE",
                reason=None,
                as_of=datetime(2026, 5, 4, tzinfo=UTC),
            ),
        ],
    )
    lal_only = fetch_latest_per_player(con, team_abbr="LAL")
    assert {r["player_id"] for r in lal_only} == {"2544"}
    bos_only = fetch_for_team(con, "BOS")
    assert {r["player_id"] for r in bos_only} == {"1628369"}
    con.close()


def test_fetch_latest_per_player_traded_player_follows_new_team(tmp_path: Path) -> None:
    """A traded player's latest row belongs to his NEW team: filtering by the
    OLD team must not resurrect the stale pre-trade row (the old query
    computed max(as_of) within the team filter, so the LAL query served the
    pre-trade LAL row forever), and the new team's query must serve the
    post-trade status."""
    db = _new_db(tmp_path)
    con = duckdb.connect(str(db))
    pre_trade = datetime(2026, 4, 1, 18, 0, tzinfo=UTC)
    post_trade = datetime(2026, 5, 4, 18, 0, tzinfo=UTC)
    upsert_injuries(
        con,
        [
            InjuryRow(
                player_id="2544",
                player_name="LeBron James",
                team_abbr="LAL",
                status="QUESTIONABLE",
                reason="left ankle",
                as_of=pre_trade,
            ),
            InjuryRow(
                player_id="2544",
                player_name="LeBron James",
                team_abbr="BOS",  # traded
                status="AVAILABLE",
                reason=None,
                as_of=post_trade,
            ),
        ],
    )
    lal = fetch_latest_per_player(con, team_abbr="LAL")
    bos = fetch_latest_per_player(con, team_abbr="BOS")
    unfiltered = fetch_latest_per_player(con)
    con.close()
    assert lal == []  # old team no longer claims him
    assert len(bos) == 1
    assert bos[0]["status"] == "AVAILABLE"
    assert bos[0]["as_of"] == post_trade.replace(tzinfo=None)
    assert len(unfiltered) == 1  # still exactly one latest row per player
    assert unfiltered[0]["team_abbr"] == "BOS"


def test_fetch_latest_per_player_date_filter(tmp_path: Path) -> None:
    db = _new_db(tmp_path)
    con = duckdb.connect(str(db))
    upsert_injuries(
        con,
        [
            InjuryRow(
                player_id="A",
                player_name="A",
                team_abbr="LAL",
                status="OUT",
                reason=None,
                as_of=datetime(2026, 4, 1, tzinfo=UTC),
            ),
            InjuryRow(
                player_id="B",
                player_name="B",
                team_abbr="LAL",
                status="OUT",
                reason=None,
                as_of=datetime(2026, 5, 4, tzinfo=UTC),
            ),
        ],
    )
    recent = fetch_latest_per_player(con, on_or_after=date(2026, 5, 1))
    assert {r["player_id"] for r in recent} == {"B"}
    con.close()


# --------------------------- flow ---------------------------


def test_main_skips_when_csv_unset(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """No CSV provided -> warning + return 0 + no table writes."""
    db = _new_db(tmp_path)
    n = run_ingest(csv_path=None, db_path=db)
    assert n == 0
    captured = capsys.readouterr().out
    assert "skipping" in captured.lower()
    # Confirm table is still empty.
    con = duckdb.connect(str(db), read_only=True)
    try:
        count = con.execute("SELECT COUNT(*) FROM nba_injury").fetchone()
        assert count is not None and count[0] == 0
    finally:
        con.close()


def test_main_round_trips_a_csv_file(tmp_path: Path) -> None:
    db = _new_db(tmp_path)
    csv_path = tmp_path / "injuries.csv"
    csv_path.write_text(
        "player_id,player_name,team_abbr,status,reason,as_of\n"
        "2544,LeBron James,LAL,Out,Left ankle,2026-05-04T18:30:00Z\n"
        "1628369,Jayson Tatum,BOS,Available,,2026-05-04\n",
        encoding="utf-8",
    )
    n = run_ingest(csv_path=csv_path, db_path=db)
    assert n == 2
    con = duckdb.connect(str(db), read_only=True)
    try:
        out = fetch_latest_per_player(con)
    finally:
        con.close()
    assert {r["player_id"] for r in out} == {"2544", "1628369"}


def test_main_empty_csv_returns_zero(tmp_path: Path) -> None:
    db = _new_db(tmp_path)
    csv_path = tmp_path / "empty.csv"
    csv_path.write_text("player_id,player_name,team_abbr,status,reason,as_of\n", encoding="utf-8")
    n = run_ingest(csv_path=csv_path, db_path=db)
    assert n == 0


def test_main_raises_on_missing_csv_path(tmp_path: Path) -> None:
    db = _new_db(tmp_path)
    with pytest.raises(FileNotFoundError):
        run_ingest(csv_path=tmp_path / "does_not_exist.csv", db_path=db)
