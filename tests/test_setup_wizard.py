"""Tests for `kq setup` (the guided first-run wizard).

The wizard is the first thing a brand-new user runs, so its automatic
(``--yes``) path must work on a completely empty directory with zero
credentials, and re-running must never clobber existing state.
"""

from __future__ import annotations

from pathlib import Path

from kq.flows.setup_wizard import _set_env_value, run_wizard
from kq.storage.duckdb_store import connect

EXAMPLE = "KALSHI_API_KEY_ID=\nKALSHI_PRIVATE_KEY_PATH=./secrets/kalshi.pem\nLOG_LEVEL=INFO\n"


def _paths(tmp_path: Path) -> tuple[Path, Path, Path]:
    db = tmp_path / "data" / "lab.duckdb"
    env = tmp_path / ".env"
    example = tmp_path / ".env.example"
    example.write_text(EXAMPLE, encoding="utf-8")
    return db, env, example


def test_yes_mode_bootstraps_everything_from_nothing(tmp_path: Path) -> None:
    db, env, example = _paths(tmp_path)
    code = run_wizard(yes=True, db_path=db, env_path=env, env_example_path=example)
    assert code == 0
    assert db.exists(), "database must be created"
    assert env.read_text(encoding="utf-8") == EXAMPLE, ".env created from template verbatim"
    con = connect(db)
    try:
        tables = con.execute("SELECT COUNT(*) FROM duckdb_tables()").fetchone()
    finally:
        con.close()
    assert tables is not None and tables[0] >= 8, "schema bootstrap must run"


def test_rerun_is_idempotent_and_preserves_env_edits(tmp_path: Path) -> None:
    db, env, example = _paths(tmp_path)
    assert run_wizard(yes=True, db_path=db, env_path=env, env_example_path=example) == 0
    env.write_text(EXAMPLE + "MY_CUSTOM_TWEAK=1\n", encoding="utf-8")
    assert run_wizard(yes=True, db_path=db, env_path=env, env_example_path=example) == 0
    assert "MY_CUSTOM_TWEAK=1" in env.read_text(encoding="utf-8"), "re-run must not clobber .env"


def test_set_env_value_rewrites_in_place_and_appends(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("# comment stays\nKALSHI_API_KEY_ID=\nLOG_LEVEL=INFO\n", encoding="utf-8")
    _set_env_value(env, "KALSHI_API_KEY_ID", "abc-123")
    _set_env_value(env, "BRAND_NEW_KEY", "hello")
    text = env.read_text(encoding="utf-8")
    assert "# comment stays" in text
    assert "KALSHI_API_KEY_ID=abc-123" in text
    assert text.count("KALSHI_API_KEY_ID") == 1
    assert text.rstrip().endswith("BRAND_NEW_KEY=hello")
    assert "LOG_LEVEL=INFO" in text
