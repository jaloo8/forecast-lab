"""Offline causal chain selection and nonoverlapping quote request plan."""

import argparse
import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pandas as pd
from scripts.acquire_options_pilot import request_from_receipt
from scripts.run_options_pilot import payload, select_pair

from kq.equities.options_cache import OptionsCache


def quote_windows(entry: pd.Timestamp, exit_at: pd.Timestamp) -> list[tuple]:
    windows = []
    for at in sorted([entry, exit_at]):
        start = (at - pd.Timedelta(seconds=10)).floor("10min")
        end = (at + pd.Timedelta(seconds=1)).ceil("10min")
        if windows and start <= windows[-1][1]:
            windows[-1] = (windows[-1][0], max(end, windows[-1][1]))
        else:
            windows.append((start, end))
    return windows


def run(args: argparse.Namespace) -> None:
    if args.output.exists():
        raise FileExistsError("Preserve prior plans; choose a new output directory")
    items = json.loads(args.definitions.read_text())
    definitions = [
        replace(request_from_receipt(i), source_version=i.get("source_version", "original"))
        for i in items
    ]
    census = pd.read_csv(args.census)
    candidates = census.loc[
        census.status.eq("underlying_only")
        & ~census.next_day_weekend
        & ~census.pilot_options_cached
    ]
    pilot = json.loads(args.pilot_plan.read_text())["requests"]
    selections, plans = [], []
    with OptionsCache(args.root, budget=Decimal("85")) as cache:
        bars = pd.read_csv(payload(cache, request_from_receipt(pilot[0])))
        bars.index = pd.to_datetime(bars.ts_event, utc=True, format="ISO8601")
        paths = {r.key: payload(cache, r) for r in definitions}
        for row in candidates.itertuples():
            signal, entry, exit_at = map(pd.Timestamp, (row.signal_at, row.entry_at, row.exit_at))
            definition = next(r for r in definitions if r.start <= signal < r.end)
            record = {
                "session": row.session,
                "signal_at": str(signal),
                "entry_at": str(entry),
                "exit_at": str(exit_at),
                "definition": definition.canonical,
            }
            try:
                pair = select_pair(
                    paths[definition.key],
                    signal,
                    float(bars.loc[signal - pd.Timedelta(minutes=1), "close"]),
                    confirm_standard_spy_100=True,
                )
            except ValueError as exc:
                selections.append(dict(record, status="no_eligible_chain", reason=str(exc)))
                continue
            requests = []
            for start, end in quote_windows(entry, exit_at):
                request = replace(
                    definition,
                    schema="cmbp-1",
                    symbols=tuple(sorted(pair)),
                    stype_in="raw_symbol",
                    start=start.to_pydatetime(),
                    end=end.to_pydatetime(),
                    source_version="original",
                )
                requests.append(request.canonical)
                plans.append(
                    {
                        "params": {
                            "dataset": request.dataset,
                            "schema": request.schema,
                            "symbols": ",".join(request.symbols),
                            "stype_in": request.stype_in,
                            "start": start.isoformat(),
                            "end": end.isoformat(),
                        },
                        "requested_start": start.isoformat(),
                        "requested_end": end.isoformat(),
                    }
                )
            selections.append(dict(record, status="selected", symbols=pair, quotes=requests))
    args.output.mkdir(parents=True)
    (args.output / "selections.json").write_text(json.dumps(selections, indent=2))
    (args.output / "quote-requests.json").write_text(json.dumps(plans, indent=2))
    print(
        json.dumps(
            {
                "candidates": len(selections),
                "quote_requests": len(plans),
                "statuses": pd.Series([r["status"] for r in selections]).value_counts().to_dict(),
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "definitions", "census", "pilot-plan", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    run(parser.parse_args())
