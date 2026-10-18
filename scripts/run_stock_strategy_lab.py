"""Run immutable stock strategy comparisons on the A8 research release."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from kq.equities.strategy_lab.archive import load_archive
from kq.equities.strategy_lab.artifacts import publish_run, require_writable_research
from kq.equities.strategy_lab.authority import require_authority


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/equities"))
    parser.add_argument("--root", type=Path, default=Path("data/equities/strategy-lab"))
    args = parser.parse_args()
    try:
        require_authority(args.root)
        require_writable_research(args.root)
        bars, source = load_archive(args.data_dir)
        result = publish_run(bars, source, args.root)
    except (ValueError, TypeError, KeyError, OSError) as exc:
        print(f"Strategy comparison failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
