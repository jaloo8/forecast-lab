"""Smoke test for Settings - ensures defaults load and gates are sane."""

from __future__ import annotations

from kq.config import Settings


def test_default_settings_refuse_live_trading() -> None:
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.kq_live is False, "kq_live must default to False"
    assert 0 < s.kq_kelly_fraction <= 1
    assert s.kq_max_daily_loss_pct > 0
    assert s.kq_max_position_usd > 0


def test_settings_are_frozen() -> None:
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    try:
        s.kq_live = True  # type: ignore[misc]
    except (TypeError, ValueError):
        return
    raise AssertionError("Settings should be frozen; mutation should have raised")
