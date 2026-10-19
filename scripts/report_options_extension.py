"""Offline fixed-rule replay; all session statuses and unresolved debits retained."""

import argparse
import json
import shutil
from dataclasses import asdict, replace
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd
from scripts.run_options_pilot import payload

from kq.equities.options_cache import OptionsCache, Request
from kq.equities.options_replay import ReplayResult, read_call_quotes, replay_trade


def stressed(result: ReplayResult, extra: float) -> ReplayResult:
    """Additional dollars/share per leg per side, with unchanged $100 funding rule."""
    if result.entry_debit is None:
        return result
    entry_extra = 200 * extra
    debit = result.entry_debit + entry_extra
    if debit + 1.30 > 100 or (debit - 1.30) / 100 >= 1:
        return ReplayResult("skipped_entry", "Stress costs exceed entry funding limit")
    if result.exit_cash is None:
        return replace(result, entry_debit=debit)
    cash = result.exit_cash - entry_extra
    return replace(result, entry_debit=debit, exit_cash=cash, net_cash=cash - debit)


def summarize(frame: pd.DataFrame) -> dict:
    closed = frame.loc[frame.status.eq("closed")]
    pnl = closed.net_cash.astype(float)
    equity = pd.Series([0.0, *pnl.cumsum().tolist()])
    return {
        "sessions": len(frame),
        "closed": len(closed),
        "closed_net_usd": float(pnl.sum()) if len(closed) else None,
        "closed_mean_usd": float(pnl.mean()) if len(closed) else None,
        "closed_win_rate": float(pnl.gt(0).mean()) if len(closed) else None,
        "closed_max_drawdown_usd": float((equity.cummax() - equity).max()),
        "unresolved": int(frame.status.eq("unresolved_exit").sum()),
        "unresolved_debit_usd": float(
            frame.loc[frame.status.eq("unresolved_exit"), "entry_debit"].sum()
        ),
        "statuses": frame.status.value_counts().to_dict(),
        "largest_entry_debit_usd": float(frame.entry_debit.max())
        if frame.entry_debit.notna().any()
        else None,
    }


def block_interval(frame: pd.DataFrame) -> list[float] | None:
    """Exploratory closed-trade mean CI; resample blocks of five census sessions."""
    pnl = frame.net_cash.where(frame.status.eq("closed")).to_numpy(dtype=float)
    if np.isfinite(pnl).sum() < 10:
        return None
    rng = np.random.default_rng(20261018)
    means = []
    for _ in range(2000):
        starts = rng.integers(0, len(pnl) - 4, size=(len(pnl) + 4) // 5)
        values = pnl[(starts[:, None] + np.arange(5)).ravel()[: len(pnl)]]
        if np.isfinite(values).any():
            means.append(float(np.nanmean(values)))
    return np.quantile(means, [0.025, 0.975]).tolist()


def run(args: argparse.Namespace) -> None:
    if args.output.exists():
        raise FileExistsError("Choose a new output directory")
    args.output.mkdir(parents=True)
    rows, observations = [], {}
    with OptionsCache(args.root, budget=Decimal("85")) as cache:
        for item in json.loads(args.selections.read_text()):
            if item["status"] != "selected":
                rows.append(
                    {
                        "session": item["session"],
                        "status": item["status"],
                        "reason": item.get("reason"),
                    }
                )
                continue
            definition = payload(cache, Request.decode(item["definition"]))
            combined = args.output / (item["session"] + "-quotes.csv")
            with combined.open("wb") as target:
                for i, canonical in enumerate(item["quotes"]):
                    with payload(cache, Request.decode(canonical)).open("rb") as source:
                        if i:
                            source.readline()
                        shutil.copyfileobj(source, target)
            signal, entry, exit_at = map(
                pd.Timestamp, (item["signal_at"], item["entry_at"], item["exit_at"])
            )
            obs = read_call_quotes(
                definition,
                combined,
                tuple(item["symbols"]),
                signal,
                (entry, exit_at),
                confirm_standard_spy_100=True,
            )
            result = replay_trade(obs, signal_at=signal, entry_at=entry, exit_at=exit_at)
            observations[item["session"]] = {
                str(at): v if isinstance(v, str) else [asdict(q) for q in v]
                for at, v in obs.items()
            }
            for extra in (0, 0.01, 0.02):
                rows.append(
                    {
                        "session": item["session"],
                        "extra_per_leg_side": extra,
                        **asdict(stressed(result, extra)),
                    }
                )
    census = pd.read_csv(args.census)
    outcomes = pd.DataFrame(rows).reindex(
        columns=[
            "session",
            "extra_per_leg_side",
            "status",
            "reason",
            "entry_debit",
            "exit_cash",
            "net_cash",
        ]
    )
    report = {}
    for extra in (0, 0.01, 0.02):
        selected = outcomes.loc[
            outcomes.extra_per_leg_side.eq(extra) | outcomes.extra_per_leg_side.isna()
        ]
        frame = census.rename(columns={"status": "underlying_status"}).merge(
            selected, on="session", how="left", validate="one_to_one"
        )
        frame["status"] = frame.status.fillna(frame.underlying_status)
        frame.loc[frame.pilot_options_cached, "status"] = "pilot_separate"
        frame.loc[
            frame.next_day_weekend & frame.underlying_status.eq("underlying_only"), "status"
        ] = "weekend_expiry"
        if frame.status.eq("underlying_only").any():
            raise ValueError("An eligible candidate has no recorded outcome or refusal")
        frame.to_csv(args.output / f"sessions-stress-{extra:.2f}.csv", index=False)
        summaries = {"overall": summarize(frame), "closed_mean_block95": block_interval(frame)}
        for column in ("year", "volatility", "trend"):
            summaries[column] = {
                str(label): summarize(group) for label, group in frame.groupby(column)
            }
        report[str(extra)] = summaries
    (args.output / "report.json").write_text(json.dumps(report, indent=2))
    (args.output / "observations.json").write_text(json.dumps(observations, indent=2, default=str))
    print(json.dumps(report["0"]["overall"], indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "selections", "census", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    run(parser.parse_args())
