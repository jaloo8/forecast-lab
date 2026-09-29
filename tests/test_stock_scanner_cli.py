import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


@pytest.fixture
def cli() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "scripts/run_stock_scanner.py"
    spec = importlib.util.spec_from_file_location("stock_scanner_cli", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_file(tmp_path: Path) -> Path:
    path = tmp_path / "snapshot.json"
    path.write_text(
        json.dumps(
            dict(
                universe=["AAA"],
                source_errors={"OTHER": "timeout"},
                unavailable={"OTHER": "not_found"},
                source_metadata=dict(
                    catalogue_sha256="a" * 64,
                    catalogue_captured_at="2026-09-29T00:00:00Z",
                    input_sha256={"raw.json": "b" * 64},
                    input_captured_at={"raw.json": "2026-09-29T01:00:00Z"},
                ),
            )
        ),
        encoding="utf-8",
    )
    return path


def test_authority_refusal_precedes_all_other_actions(
    cli: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["scanner", "--snapshot", str(tmp_path / "absent.json")])

    def refuse(_: Path) -> None:
        raise ValueError("not authoritative")

    monkeypatch.setattr(cli, "require_authority", refuse)
    monkeypatch.setattr(cli, "require_writable_research", lambda _: pytest.fail("too late"))
    assert cli.main() == 2
    assert "not authoritative" in capsys.readouterr().err


def test_valid_wiring_preserves_provenance_and_hashes_actual_bytes(
    cli: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, root = source_file(tmp_path), tmp_path / "research"
    monkeypatch.setattr(sys, "argv", ["scanner", "--snapshot", str(path), "--root", str(root)])
    calls = []
    monkeypatch.setattr(cli, "require_authority", lambda value: calls.append(("authority", value)))
    monkeypatch.setattr(
        cli, "require_writable_research", lambda value: calls.append(("mirror", value))
    )

    def publish(snapshot: dict[str, Any], source: dict[str, Any], target: Path) -> dict[str, str]:
        assert calls == [("authority", root), ("mirror", root)]
        assert source["universe"] == snapshot["universe"] == ["AAA"]
        assert source["raw_snapshot_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert source["source_errors"] == snapshot["source_errors"]
        assert source["unavailable"] == snapshot["unavailable"]
        assert target == root
        return {"run_id": "fixture"}

    monkeypatch.setattr(cli, "publish_scan", publish)
    assert cli.main() == 0
    assert not root.exists()


@pytest.mark.parametrize("fault", ["metadata", "publish"])
def test_missing_metadata_and_backend_exception_exit_honestly(
    cli: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fault: str,
) -> None:
    path = source_file(tmp_path)
    monkeypatch.setattr(sys, "argv", ["scanner", "--snapshot", str(path)])
    monkeypatch.setattr(cli, "require_authority", lambda _: None)
    monkeypatch.setattr(cli, "require_writable_research", lambda _: None)
    if fault == "metadata":
        path.write_text('{"universe":["AAA"]}', encoding="utf-8")

    def failed(*_: Any) -> None:
        raise ValueError("no intended session")

    monkeypatch.setattr(cli, "publish_scan", failed)
    assert cli.main() == 2
    assert "Scanner failed:" in capsys.readouterr().err
