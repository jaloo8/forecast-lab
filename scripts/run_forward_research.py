"""Create or evaluate a separate, immutable stock research decision."""

import argparse
import json
from pathlib import Path

from kq.equities.forward_study import evaluate, write_decision
from kq.equities.observations import observation_folder, prior_observation, save_observation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--decision", type=Path, required=True)
    parser.add_argument("--create", action="store_true")
    parser.add_argument("--observations", type=Path, required=True)
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    decision = (
        write_decision(snapshot, args.decision)
        if args.create
        else json.loads(args.decision.read_text(encoding="utf-8"))
    )
    journal = observation_folder(args.observations, decision)
    previous = prior_observation(journal, snapshot)
    outcomes = evaluate(decision, snapshot, previous_snapshot=previous)
    if any(status not in {"pending", "mature"} for status in outcomes["status"]):
        raise ValueError("invalid research outcomes; preserve source and investigate")
    save_observation(journal, snapshot)
    print(
        json.dumps(
            {
                "decision": str(args.decision),
                "created_at": decision["created_at"],
                "selected": decision["selected"],
                "method_hash": decision["method_hash"],
                "outcomes": json.loads(outcomes.to_json(orient="records", date_format="iso")),
            },
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
