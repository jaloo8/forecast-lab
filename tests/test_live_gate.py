"""Tests for the live-trading gate. This is the most important safety test."""

from __future__ import annotations

import os

import pytest

from kq.execution.live import LiveExecutor, LiveTradingNotAllowedError, assert_live_allowed


def test_ack_false_refused() -> None:
    with pytest.raises(LiveTradingNotAllowedError):
        assert_live_allowed(ack=False)


def test_ack_true_but_env_false_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KQ_LIVE", "false")
    from kq import config

    config.get_settings.cache_clear()
    with pytest.raises(LiveTradingNotAllowedError):
        assert_live_allowed(ack=True)
    config.get_settings.cache_clear()


def test_live_executor_always_raises_on_construction() -> None:
    """The LiveExecutor should refuse to instantiate without the gate."""
    # Clear any cached settings from other tests
    from kq import config

    config.get_settings.cache_clear()
    os.environ.pop("KQ_LIVE", None)
    with pytest.raises(LiveTradingNotAllowedError):
        LiveExecutor()
