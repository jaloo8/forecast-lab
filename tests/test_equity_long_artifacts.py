import json
from pathlib import Path

import pytest

from kq.equities.strategy_lab import long_artifacts as target


def test_local_writer_refused_before_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("kq.equities.strategy_lab.authority.platform.node", lambda: "test-local")
    with pytest.raises(ValueError, match="A8"):
        target.publish_long(tmp_path / "capture", tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_publishes_manifest_before_computation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "output"
    monkeypatch.setattr(target, "require_authority", lambda _: None)
    monkeypatch.setattr(target, "LONG_ROOT", root)
    monkeypatch.setattr(
        target, "load_long_capture", lambda _: (None, {"captured_at": "2026-09-29T01:00:00Z"})
    )

    def compare(_):
        assert len(list(root.glob("runs/*/manifest.json"))) == 1
        return {"results": [{"status": "complete"}], "limitations": ["test fixture"]}

    monkeypatch.setattr(target, "compare_long", compare)
    pointer = target.publish_long(tmp_path, root)
    report = json.loads((root / pointer["report_file"]).read_bytes())
    assert report["source"]["captured_at"] == "2026-09-29T01:00:00Z"
    assert report["results"][0]["status"] == "complete"
    assert not (root / "writer.lock").exists()


def test_failure_preserves_prior_result_and_records_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "output"
    root.mkdir()
    (root / "latest.json").write_text('{"old":true}')
    monkeypatch.setattr(target, "require_authority", lambda _: None)
    monkeypatch.setattr(target, "LONG_ROOT", root)

    def fail(_):
        raise ValueError("bad source")

    monkeypatch.setattr(target, "load_long_capture", fail)
    with pytest.raises(ValueError, match="bad source"):
        target.publish_long(tmp_path, root)
    assert (root / "latest.json").read_text() == '{"old":true}'
    assert len(list(root.glob("runs/*/failure.json"))) == 1
    assert json.loads((root / "latest-attempt.json").read_text())["status"] == "failure"


def test_lock_and_read_only_mirror_refuse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(target, "require_authority", lambda _: None)
    (tmp_path / "READ_ONLY_MIRROR.txt").touch()
    with pytest.raises(ValueError, match="mirror"):
        target.publish_long(tmp_path, tmp_path / "out")


def test_cannot_overwrite_short_history_pointer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(target, "require_authority", lambda _: None)
    with pytest.raises(ValueError, match="long-history"):
        target.publish_long(tmp_path, tmp_path / "strategy-lab")
    assert not (tmp_path / "strategy-lab").exists()
