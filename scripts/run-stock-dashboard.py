"""Launch the isolated, read-only stock dashboard from Windows Task Scheduler."""

import os
import runpy
import sys
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    source = str(root / "src")
    os.environ["PYTHONPATH"] = source
    sys.path.insert(0, source)
    sys.argv = [
        "streamlit",
        "run",
        str(root / "src/kq/equities/dashboard.py"),
        "--server.address",
        "127.0.0.1",
        "--server.port",
        "8502",
        "--server.headless",
        "true",
        "--browser.gatherUsageStats",
        "false",
    ]
    runpy.run_module("streamlit", run_name="__main__")


if __name__ == "__main__":
    main()
