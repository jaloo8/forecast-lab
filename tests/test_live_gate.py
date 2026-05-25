"""Tests for the live-trading gate. This is the most important safety test."""

from __future__ import annotations

import os

import pytest

from kq import config
from kq.execution.live import LiveExecutor, LiveTradingNotAllowedError, assert_live_allowed


def test_ack_false_refused() -> None:
    with pytest.raises(LiveTradingNotAllowedError):
        assert_live_allowed(ack=False)


def test_ack_true_but_env_false_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KQ_LIVE", "false")
    config.get_settings.cache_clear()
    with pytest.raises(LiveTradingNotAllowedError):
        assert_live_allowed(ack=True)
    config.get_settings.cache_clear()


def test_ack_true_and_env_true_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The positive control: with BOTH the CLI ack AND `KQ_LIVE=true`, the
    gate must OPEN (return without raising).

    Every other test here asserts the gate *refuses*; this one pins that it
    actually opens under the exact §5/§9 conditions — so a regression that
    made the gate refuse unconditionally (trading could never be enabled) or,
    worse, made it require only ONE of the two conditions, fails here. This
    is purely the gate predicate — it does not construct an executor or place
    any order.
    """
    monkeypatch.setenv("KQ_LIVE", "true")
    config.get_settings.cache_clear()
    try:
        # Must NOT raise. (Returns None.)
        assert assert_live_allowed(ack=True) is None
    finally:
        config.get_settings.cache_clear()


def test_live_executor_always_raises_on_construction() -> None:
    """The LiveExecutor should refuse to instantiate without the gate."""
    config.get_settings.cache_clear()
    os.environ.pop("KQ_LIVE", None)
    with pytest.raises(LiveTradingNotAllowedError):
        LiveExecutor()
