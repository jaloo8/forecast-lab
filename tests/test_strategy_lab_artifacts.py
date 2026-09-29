"""Immutable research runs cannot masquerade as trading or erase failure evidence."""

import hashlib
import json
import os
from pathlib import Path

import pandas as pd
import pytest

from kq.equities.strategy_lab import artifacts
from kq.equities.strategy_lab.artifacts import publish_run


def test_mirror_refuses_before_computation(tmp_path: Path) -> None:
    (tmp_path / "READ_ONLY_MIRROR.txt").write_text("read only")
    with pytest.raises(ValueError, match="mirror"):
        publish_run(pd.DataFrame(), {}, tmp_path / "strategy-lab")
    assert not (tmp_path / "strategy-lab").exists()


def test_manifest_precedes_evaluation_and_failure_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(bars: pd.DataFrame) -> dict:
        runs = list((tmp_path / "runs").glob("*"))
        assert len(runs) == 1
        assert (runs[0] / "manifest.json").exists()
        manifest = json.loads((runs[0] / "manifest.json").read_text())
        assert (
            manifest["code_sha256"]["strategy_lab/artifacts.py"]
            == hashlib.sha256(Path(artifacts.__file__).read_bytes()).hexdigest()
        )
        assert len(manifest["method_hash"]) == 64
        raise ValueError("bad source")

    monkeypatch.setattr(artifacts, "compare", fail)
    with pytest.raises(ValueError, match="bad source"):
        publish_run(pd.DataFrame(), {"source_hash": "abc"}, tmp_path)
    failure = list((tmp_path / "runs").glob("*/failure.json"))
    assert json.loads(failure[0].read_text())["error"] == "bad source"
    assert not (tmp_path / "latest.json").exists()


def test_publish_digest_and_distinct_immutable_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        artifacts,
        "compare",
        lambda bars: {"results": [], "cohorts": [], "controls": [], "limitations": []},
    )
    first = publish_run(pd.DataFrame(), {"source_hash": "abc"}, tmp_path)
    second = publish_run(pd.DataFrame(), {"source_hash": "abc"}, tmp_path)
    assert first["run_id"] != second["run_id"]
    pointer = json.loads((tmp_path / "latest.json").read_text())
    raw = (tmp_path / pointer["report_file"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == pointer["report_sha256"]
    assert (tmp_path / first["report_file"]).exists()
    assert json.loads(raw)["status"] == "success"


def test_manifest_serialization_failure_is_recorded_without_partial_json(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        publish_run(pd.DataFrame(), {"invalid": float("nan")}, tmp_path)
    runs = list((tmp_path / "runs").iterdir())
    assert len(runs) == 1
    assert not (runs[0] / "manifest.json").exists()
    failure = json.loads((runs[0] / "failure.json").read_text())
    assert failure["error_type"] == "ValueError"
    assert failure["prior_latest_unchanged"] is True
    assert not (tmp_path / "latest.json").exists()


def test_interrupted_artifact_flush_never_exposes_partial_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def interrupted(fd: int) -> None:
        raise OSError("simulated interrupted flush")

    target = tmp_path / "report.json"
    with monkeypatch.context() as patch:
        patch.setattr(os, "fsync", interrupted)
        with pytest.raises(OSError, match="interrupted"):
            artifacts._write(target, {"value": "complete"})
    assert not target.exists()
    artifacts._write(target, {"value": "complete"})
    assert json.loads(target.read_text()) == {"value": "complete"}


def test_failed_report_preserves_prior_latest_and_complete_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prior = b'{"prior":"unchanged"}'
    (tmp_path / "latest.json").write_bytes(prior)
    monkeypatch.setattr(artifacts, "compare", lambda bars: {"bad": float("nan")})
    with pytest.raises(ValueError):
        publish_run(pd.DataFrame(), {}, tmp_path)
    run = next((tmp_path / "runs").iterdir())
    assert json.loads((run / "manifest.json").read_text())["run_id"] == run.name
    assert (run / "failure.json").is_file()
    assert not (run / "report.json").exists()
    assert (tmp_path / "latest.json").read_bytes() == prior


def test_atomic_writer_never_replaces_existing_artifact(tmp_path: Path) -> None:
    target = tmp_path / "report.json"
    artifacts._write(target, {"version": 1})
    original = target.read_bytes()
    with pytest.raises(FileExistsError):
        artifacts._write(target, {"version": 2})
    assert target.read_bytes() == original
    assert list(tmp_path.glob("*.tmp")) == []
