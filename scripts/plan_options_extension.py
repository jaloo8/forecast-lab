"""Offline extension census and free-metadata request plans; no acquisition API."""

import argparse
import hashlib
import json
from dataclasses import replace
from decimal import ROUND_HALF_DOWN, Decimal
from pathlib import Path

import numpy as np
import pandas as pd
from scripts.acquire_options_pilot import request_from_receipt
from scripts.run_options_pilot import payload

from kq.equities.opening_range import underlying_diagnostic
from kq.equities.options_cache import OptionsCache, Request


def regimes(close: pd.Series) -> pd.DataFrame:
    """Lagged raw-price regimes; one observed session close per aware timestamp."""
    if (
        not isinstance(close.index, pd.DatetimeIndex)
        or close.index.tz is None
        or not close.index.is_unique
        or not close.index.is_monotonic_increasing
        or close.empty
    ):
        raise ValueError("Expected ordered unique aware session closes")
    clean = close.where(np.isfinite(close) & close.gt(0))
    vol = clean.pct_change(fill_method=None).rolling(20).std().shift(1) * np.sqrt(252)
    average = clean.rolling(60).mean().shift(1)
    result = pd.DataFrame(index=close.index)
    result["session"] = close.index.tz_convert("America/New_York").strftime("%Y-%m-%d")
    result["regime_as_of"] = pd.Series(close.index.tz_convert("UTC"), index=close.index).shift(1)
    result["prior_20d_vol"] = vol
    result["volatility"] = np.select(
        [vol.isna(), vol.lt(0.15), vol.lt(0.25)], ["warmup", "low", "medium"], "high"
    )
    result["trend"] = np.select(
        [average.isna() | clean.shift(1).isna(), clean.shift(1).ge(average)],
        ["warmup", "above_60d"],
        "below_60d",
    )
    return result.reset_index(drop=True)


def provisional_pair(session: str, close: float) -> list[str]:
    """Cost-estimation candidates ONLY; dated definitions must establish eligibility."""
    price = Decimal(str(close))
    if not price.is_finite() or price <= 0:
        raise ValueError("Invalid signal close")
    strike = int(price.quantize(Decimal("1"), rounding=ROUND_HALF_DOWN))
    expiry = (pd.Timestamp(session) + pd.Timedelta(days=1)).strftime("%y%m%d")
    return [f"SPY   {expiry}C{k * 1000:08d}" for k in (strike, strike + 1)]


def cost_sample(rows: pd.DataFrame) -> pd.DataFrame:
    """First/last dates per fixed year/vol/trend cell, never outcome-selected."""
    rows = rows.sort_values("session")
    grouped = rows.groupby(["year", "volatility", "trend"], sort=True)
    return (
        pd.concat([grouped.head(1), grouped.tail(1)])
        .drop_duplicates("session")
        .sort_values("session")
    )


def definition_ranges(sessions: list[str]) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Coalesce only consecutive candidate days; retain half-open UTC boundaries."""
    dates = pd.Series(pd.to_datetime(sorted(set(sessions)), utc=True))
    groups = dates.diff().ne(pd.Timedelta(days=1)).cumsum()
    return [(g.iloc[0], g.iloc[-1] + pd.Timedelta(days=1)) for _, g in dates.groupby(groups)]


def estimate_request(request: Request, name: str) -> dict[str, object]:
    return {
        "name": name,
        "dataset": request.dataset,
        "schema": request.schema,
        "symbols": list(request.symbols),
        "stype_in": request.stype_in,
        "start": request.start.isoformat(),
        "end": request.end.isoformat(),
    }


def run(args: argparse.Namespace) -> None:
    if args.output.exists():
        raise FileExistsError("Choose a new directory; preserve previous evidence")
    items = json.loads(args.pilot_plan.read_text())["requests"]
    requests = [request_from_receipt(x) for x in items]
    with OptionsCache(args.root, budget=Decimal("85")) as cache:
        path = payload(cache, requests[0])
        frame = pd.read_csv(path)
        if set(frame.symbol) != {"SPY"} or set(frame.rtype) != {33}:
            raise ValueError("Wrong underlying payload")
        frame.index = pd.to_datetime(frame.ts_event, utc=True, format="ISO8601")
        bars = frame.tz_convert("America/New_York").between_time("09:30", "15:59")
        census = underlying_diagnostic(bars.tz_convert("UTC"))
        last = bars.groupby(bars.index.date).tail(1).copy()
        last.index = last.index + pd.Timedelta(minutes=1)
        census = census.merge(regimes(last.close), on="session", validate="one_to_one")
        census["year"] = census.session.str[:4].astype(int)
        census["next_day_weekend"] = (
            pd.to_datetime(census.session) + pd.Timedelta(days=1)
        ).dt.dayofweek.ge(5)
        cached_dates = []
        for request in requests:
            if request.schema == "cmbp-1":
                cache.local_files(request)  # Verify bytes before counting reuse.
                cached_dates.append(str(request.start.date()))
        census["pilot_options_cached"] = census.session.isin(cached_dates)
        signals = census.loc[census.status.eq("underlying_only")].copy()
        candidates = signals.loc[~signals.next_day_weekend & ~signals.pilot_options_cached]
        sample = cost_sample(candidates)
        quote_plan = []
        for row in sample.itertuples():
            at = row.signal_at - pd.Timedelta(minutes=1)
            symbols = provisional_pair(str(row.session), float(bars.loc[at, "close"]))
            base = {
                "dataset": "OPRA.PILLAR",
                "schema": "cmbp-1",
                "symbols": symbols,
                "stype_in": "raw_symbol",
            }
            for label, decision in (("entry", row.entry_at), ("exit", row.exit_at)):
                quote_plan.append(
                    {
                        "name": f"{row.session}-{label}-provisional",
                        **base,
                        "start": (decision - pd.Timedelta(seconds=10)).isoformat(),
                        "end": (decision + pd.Timedelta(seconds=1)).isoformat(),
                    }
                )
        full_definitions = replace(requests[1], start=requests[0].start, end=requests[0].end)
        definition_plan = [
            estimate_request(r, f"missing-definitions-{i}")
            for i, r in enumerate(cache.missing(full_definitions))
        ]
        uncovered = [
            missing
            for a, b in definition_ranges(candidates.session.tolist())
            for missing in cache.missing(replace(requests[1], start=a, end=b))
        ]
        targeted_definitions = [
            estimate_request(r, f"candidate-definitions-{i}") for i, r in enumerate(uncovered)
        ]
    args.output.mkdir(parents=True)
    census.to_csv(args.output / "session-census.csv", index=False)
    sample.to_csv(args.output / "cost-sample.csv", index=False)
    for column in ("year", "volatility", "trend"):
        signals.groupby(column).agg(
            signals=("session", "size"),
            mean_raw=("raw_return", "mean"),
            mean_net_5bp=("net_5bp", "mean"),
        ).to_csv(args.output / f"underlying-by-{column}.csv")
    (args.output / "definition-plan.json").write_text(json.dumps(definition_plan, indent=2))
    for i in range(0, len(quote_plan), 100):
        (args.output / f"quote-plan-{i // 100}.json").write_text(
            json.dumps(quote_plan[i : i + 100], indent=2)
        )
    for i in range(0, len(targeted_definitions), 100):
        (args.output / f"candidate-definitions-{i // 100}.json").write_text(
            json.dumps(targeted_definitions[i : i + 100], indent=2)
        )
    report = {
        "status": "options_extension_not_yet_acquired_or_backtested",
        "source_request": requests[0].key,
        "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "statuses": census.status.value_counts().to_dict(),
        "weekend_expiry_signals": int(signals.next_day_weekend.sum()),
        "cached_pilot_dates": cached_dates,
        "new_weekday_candidates": len(candidates),
        "cost_sample_dates": len(sample),
        "quote_estimate_requests": len(quote_plan),
        "definitions_requests_excluding_cache": len(definition_plan),
        "targeted_definition_ranges": len(targeted_definitions),
        "limits": "Observed sessions only; no calendar completeness claim. Raw close-price "
        "regimes, not dividend-adjusted total returns. Provisional symbols are NOT chain "
        "eligibility. Historical definitions and quotes required before scoring options. "
        "Underlying outcomes already viewed; no pristine holdout claim.",
    }
    (args.output / "summary.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "pilot-plan", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    run(parser.parse_args())
