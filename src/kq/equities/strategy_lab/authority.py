"""Positive operational writer identity for the owner-approved isolated release."""

import platform
from pathlib import Path

RELEASE = Path("C:/Users/jloo1/Documents/stock-paper-lab-20260928")


def require_authority(root: Path) -> None:
    """Require both A8 and this release; restrict artifacts to its research tree."""
    if platform.node().casefold() != "a8":
        raise ValueError("Only A8 may run the durable research writer")
    if Path(__file__).resolve().parents[4] != RELEASE.resolve():
        raise ValueError("Research writer requires the isolated stock release")
    if not root.resolve().is_relative_to((RELEASE / "data/equities/strategy-lab").resolve()):
        raise ValueError("Research output must remain in the isolated research directory")
