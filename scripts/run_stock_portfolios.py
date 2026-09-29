"""Import a fresh capture into nine independent virtual accounts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kq.equities.portfolio_runner import run_portfolios


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("data/equities/parallel-books"))
    args = parser.parse_args()
    result = run_portfolios(args.snapshot, args.root)
    print(json.dumps(result, allow_nan=False))
    if result["status"] != "ok":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
