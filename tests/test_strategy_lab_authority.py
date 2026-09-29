"""The operational runner must never turn a desktop into a research writer."""

from pathlib import Path

import pytest

from kq.equities.strategy_lab import authority


def test_non_a8_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(authority.platform, "node", lambda: "desktop")
    with pytest.raises(ValueError, match="A8"):
        authority.require_authority(tmp_path)


def test_a8_requires_isolated_release(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(authority.platform, "node", lambda: "A8")
    monkeypatch.setattr(authority, "RELEASE", tmp_path)
    with pytest.raises(ValueError, match="release"):
        authority.require_authority(tmp_path / "data/equities/strategy-lab")


def test_a8_valid_research_root_and_escaped_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(authority.platform, "node", lambda: "A8")
    monkeypatch.setattr(authority, "RELEASE", tmp_path)
    monkeypatch.setattr(
        authority, "__file__", str(tmp_path / "src/kq/equities/strategy_lab/authority.py")
    )
    authority.require_authority(tmp_path / "data/equities/strategy-lab")
    with pytest.raises(ValueError, match="output"):
        authority.require_authority(tmp_path / "data/equities")
