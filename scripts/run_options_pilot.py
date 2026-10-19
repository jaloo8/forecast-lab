"""Offline three-session conditional quote replay; never acquire missing data."""

import argparse
import hashlib
import json
from dataclasses import asdict
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
from scripts.acquire_options_pilot import request_from_receipt

from kq.equities.opening_range import underlying_diagnostic
from kq.equities.options_cache import OptionsCache, Request
from kq.equities.options_replay import read_call_quotes, replay_trade


def select_pair(
    path: Path, signal_at: pd.Timestamp, close: float, *, confirm_standard_spy_100: bool = False
) -> tuple[str, str]:
    """Select from the dated chain, nearest signal close; tie goes to lower strike."""
    frame = pd.read_csv(path, dtype=str)
    for col in ("ts_recv", "ts_event", "expiration"):
        frame[col] = pd.to_datetime(frame[col], utc=True, format="ISO8601")
    day = signal_at.tz_convert("America/New_York").date()
    frame = frame.loc[
        (frame.ts_recv <= signal_at)
        & (frame.ts_recv.dt.tz_convert("America/New_York").dt.date == day)
    ]
    frame = frame.sort_values("ts_recv", kind="stable").groupby("raw_symbol").tail(1)
    frame = frame.loc[
        frame.raw_symbol.str.fullmatch(r"SPY   \d{6}C\d{8}")
        & frame.expiration.dt.date.eq(day + timedelta(days=1))
        & frame.instrument_class.eq("C")
        & frame.underlying.eq("SPY")
    ]
    if frame.ts_event.gt(signal_at).any():
        raise ValueError("Future event timestamp in chain")
    frame = frame.loc[frame.security_update_action.isin(["A", "M"])]
    occ = frame.raw_symbol.str.extract(r"SPY   (\d{6})C(\d{8})")
    allowed = ["100", "2147483647"] if confirm_standard_spy_100 else ["100"]
    frame = frame.loc[
        frame.contract_multiplier.isin(allowed)
        & frame.strike_price.astype(float).eq(occ[1].astype(float) / 1000)
        & frame.expiration.dt.strftime("%y%m%d").eq(occ[0])
    ]
    if frame.empty or not Decimal(str(close)).is_finite() or close <= 0:
        raise ValueError("No eligible chain or invalid signal close")
    strikes = {Decimal(row.strike_price): row.raw_symbol for row in frame.itertuples()}
    selected = min(strikes, key=lambda k: (abs(k - Decimal(str(close))), k))
    if selected + 1 not in strikes:
        raise ValueError("Exact one-dollar short strike not listed")
    return strikes[selected], strikes[selected + 1]


def cash_summary(frame: pd.DataFrame) -> dict[str, float | int | None]:
    closed = frame.loc[frame.status.eq("closed")]
    unresolved = frame.loc[frame.status.eq("unresolved_exit")]
    return {
        "closed_net_cash": float(closed.net_cash.sum()) if len(closed) else None,
        "closed_count": len(closed),
        "unresolved": len(unresolved),
        "unresolved_entry_debit": float(unresolved.entry_debit.sum()),
    }


def payload(cache: OptionsCache, request: Request) -> Path:
    files = cache.local_files(request)
    candidates = []
    for path in files:
        with path.open("rb") as stream:
            if stream.read(8).startswith(b"ts_"):
                candidates.append(path)
    if len(candidates) != 1:
        raise ValueError("Expected one hash-verified CSV payload")
    return candidates[0]


def yahoo_bars(path: Path, receipt: Path) -> pd.DataFrame:
    raw = path.read_bytes()
    expected = json.loads(receipt.read_text())["sha256"]
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("Original underlying capture changed")
    data = json.loads(raw)["chart"]["result"][0]
    if data["meta"]["symbol"] != "SPY" or data["meta"]["currency"] != "USD":
        raise ValueError("Wrong underlying")
    return pd.DataFrame(
        data["indicators"]["quote"][0], index=pd.to_datetime(data["timestamp"], unit="s", utc=True)
    )


def run(args: argparse.Namespace) -> None:
    if args.output.exists():
        raise FileExistsError("Preserve prior replay: choose a new output directory")
    requests = [request_from_receipt(x) for x in json.loads(args.plan.read_text())["requests"]]
    if len(requests) != 7:
        raise ValueError("Expected the approved seven-request pilot")
    bars = yahoo_bars(args.yahoo, args.yahoo_receipt)
    signals = underlying_diagnostic(bars)
    rows, evidence, sources = [], {}, []
    args.output.mkdir(parents=True)
    with OptionsCache(args.root, budget=Decimal("85")) as cache:
        for di, qi in ((1, 4), (2, 5), (3, 6)):
            definitions, quotes = payload(cache, requests[di]), payload(cache, requests[qi])
            session = str(requests[qi].start.date())
            signal = signals.loc[signals.session.eq(session)].iloc[0]
            if signal.status != "underlying_only":
                raise ValueError("Original pilot trigger no longer reproduced")
            signal_close = float(bars.loc[signal.signal_at - pd.Timedelta(minutes=1), "close"])
            pair = select_pair(
                definitions, signal.signal_at, signal_close, confirm_standard_spy_100=True
            )
            if tuple(sorted(pair)) != requests[qi].symbols:
                raise ValueError("Downloaded contracts differ from causal chain selection")
            observations = read_call_quotes(
                definitions,
                quotes,
                pair,
                signal.signal_at,
                (signal.entry_at, signal.exit_at),
                confirm_standard_spy_100=True,
            )
            result = replay_trade(
                observations,
                signal_at=signal.signal_at,
                entry_at=signal.entry_at,
                exit_at=signal.exit_at,
            )
            rows.append(
                {
                    "session": session,
                    "signal_at": signal.signal_at,
                    "entry_at": signal.entry_at,
                    "exit_at": signal.exit_at,
                    "long_symbol": pair[0],
                    "short_symbol": pair[1],
                    "signal_close": signal_close,
                    **asdict(result),
                }
            )
            evidence[session] = {
                str(at): obs if isinstance(obs, str) else [asdict(q) for q in obs]
                for at, obs in observations.items()
            }
            for i in (di, qi):
                job = cache.job(requests[i].key)
                sources.append(
                    {
                        "request": requests[i].key,
                        "job": job.job_id,
                        "actual_credit_usd": str(job.actual_cost),
                    }
                )
        minute_path = payload(cache, requests[0])
        mini = pd.read_csv(minute_path)
        if set(mini.symbol) != {"SPY"} or set(mini.rtype) != {33}:
            raise ValueError("Wrong underlying payload")
        mini.index = pd.to_datetime(mini.ts_event, utc=True, format="ISO8601")
        regular = mini.tz_convert("America/New_York").between_time("09:30", "15:59")
        extended = underlying_diagnostic(regular.tz_convert("UTC"))
        extended.to_csv(args.output / "underlying-extended.csv", index=False)
        overlap = signals.merge(extended, on="session", suffixes=("_yahoo", "_mini"))
        overlap.to_csv(args.output / "underlying-overlap.csv", index=False)
        sources.append(
            {
                "request": requests[0].key,
                "job": cache.job(requests[0].key).job_id,
                "actual_credit_usd": str(cache.job(requests[0].key).actual_cost),
            }
        )
    result_frame = pd.DataFrame(rows)
    result_frame.to_csv(args.output / "options-results.csv", index=False)
    (args.output / "quote-evidence.json").write_text(json.dumps(evidence, indent=2, default=str))
    report: dict[str, Any] = {
        "status": "three_previously_viewed_diagnostic_sessions_not_holdout",
        "options_counts": result_frame.status.value_counts().to_dict(),
        **cash_summary(result_frame),
        "underlying_counts": extended.status.value_counts().to_dict(),
        "sources": sources,
        "credits_used": str(
            sum((Decimal(str(x["actual_credit_usd"])) for x in sources), Decimal(0))
        ),
        "standard_multiplier": "100 via Cboe standard SPY spec, not vendor sentinel",
        "limitations": "Conditional separate-leg fills, not atomic execution proof; three viewed "
        "sessions cannot establish edge. Extended underlying results are not options returns. "
        "EQUS.MINI is a component feed; no zero-volume interpolation or calendar "
        "completeness claim.",
    }
    (args.output / "summary.json").write_text(json.dumps(report, indent=2, allow_nan=False))
    print(result_frame.to_string(index=False))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("plan", "root", "output", "yahoo", "yahoo-receipt"):
        parser.add_argument("--" + field, type=Path, required=True)
    run(parser.parse_args())
