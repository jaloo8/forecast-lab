"""Inspect a private CBBO CSV against its registered request, without network access."""

import argparse
import json
from pathlib import Path

from kq.equities.cbbo_schema import inspect_cbbo_schema


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quotes", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--requests", type=Path, required=True)
    parser.add_argument("--request-name", required=True)
    parser.add_argument("--definitions", type=Path)
    parser.add_argument("--symbology", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    requests = json.loads(args.requests.read_text(encoding="utf-8"))
    matches = [request for request in requests if request.get("name") == args.request_name]
    if len(matches) != 1:
        raise ValueError("Request name must match exactly one registered envelope")
    report = inspect_cbbo_schema(
        args.quotes,
        request=matches[0],
        metadata_path=args.metadata,
        definitions_path=args.definitions,
        symbology_path=args.symbology,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": report["status"], "rows": report["counts"].get("rows", 0)}))


if __name__ == "__main__":
    main()
