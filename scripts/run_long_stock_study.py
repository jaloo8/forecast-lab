"""Run the frozen long-history exploratory study on the isolated A8 release."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from kq.equities.strategy_lab.long_artifacts import publish_long


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument(
        "--root", type=Path, default=Path("data/equities/strategy-lab/long-history")
    )
    args = parser.parse_args()
    try:
        pointer = publish_long(args.capture, args.root)
    except (ValueError, TypeError, KeyError, OSError) as exc:
        print(f"Long study failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(pointer))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
