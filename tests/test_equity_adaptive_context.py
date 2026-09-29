"""Context timestamps and read-only loading regressions."""

from pathlib import Path

import pytest

from kq.equities import adaptive_journal as journal
from tests.test_equity_adaptive_journal import capture, reference
from tests.test_equity_adaptive_journal import wall_clock as wall_clock  # noqa: PLC0414


def test_read_missing_journal_does_not_create_files(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        journal.load_latest(tmp_path)
    assert not list(tmp_path.iterdir())


def test_future_news_not_attached_as_observed_evidence(tmp_path: Path) -> None:
    snapshot = capture()
    snapshot["news"] = [
        dict(
            symbol="AAA",
            title="Results",
            url="https://example.com/results",
            kind="news",
            published_at="2026-09-30T00:00:00Z",
            retrieved_at="2026-09-30T00:01:00Z",
        )
    ]
    with pytest.raises(ValueError, match="precedes source"):
        journal.record(snapshot, reference(), tmp_path)
    assert journal.load_latest(tmp_path)["decision"] is None
