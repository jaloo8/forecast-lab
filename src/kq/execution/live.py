"""Live executor — GATED.

All paths that place real-money orders must call `assert_live_allowed(...)`
first. The gate requires BOTH the `--i-understand-the-risks` CLI flag AND
the `KQ_LIVE=true` environment variable. See CLAUDE.md §5 and §9.

Phase 5+ only. Before enabling, the gate criteria in CLAUDE.md §5 must be
satisfied and explicitly acknowledged by the human operator.
"""

from __future__ import annotations

from kq.config import get_settings


class LiveTradingNotAllowedError(RuntimeError):
    """Raised when something attempts to use the live endpoint without the gate."""


def assert_live_allowed(*, ack: bool) -> None:
    """Raise unless both the CLI ack flag and `KQ_LIVE=true` env are set."""
    settings = get_settings()
    if not ack:
        raise LiveTradingNotAllowedError(
            "Live trading requires --i-understand-the-risks on the CLI. Refusing."
        )
    if not settings.kq_live:
        raise LiveTradingNotAllowedError(
            "Live trading requires KQ_LIVE=true in the environment. Refusing."
        )


class LiveExecutor:
    """Not implemented until Phase 5 gate passed."""

    def __init__(self) -> None:
        assert_live_allowed(ack=False)  # always raises — intentional

    def submit(self) -> None:
        raise NotImplementedError("Phase 5 gate")
