"""Summarize every registered bot trial without selecting new trading rules."""

# Report paragraphs and linked table rows are kept intact for editorial review.
# ruff: noqa: E501

import argparse
import json
from itertools import product
from pathlib import Path
from typing import Any

import pandas as pd


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def classify(summary: pd.DataFrame, annual: pd.DataFrame) -> tuple[dict[str, Any], pd.DataFrame]:
    rows = []
    candidates = summary[summary.rule.str.startswith("B")]
    for (symbol, rule), group in candidates.groupby(["symbol", "rule"]):
        main = group[group.window.isin(["full", "later"])]
        base = main[(main.cost_bps == 10) & (main.lag == 1)]
        control = summary[(summary.symbol == symbol) & (summary.rule == "C00")]
        compared = main.merge(
            control, on=["symbol", "window", "cost_bps", "lag"], suffixes=("", "_control")
        )
        if len(main) != 12 or len(compared) != 12 or len(base) != 2:
            raise ValueError("Incomplete classification comparison")
        years = annual[annual.trial.isin(base.trial) & annual.complete_calendar_year]
        rows.append(
            {
                "symbol": symbol,
                "rule": rule,
                "positive_all_12": bool((main.cagr > 0).all()),
                "stable_all_12": bool(
                    (main.cagr > 0).all() and (compared.drawdown > compared.drawdown_control).all()
                ),
                "cagr10_both_base": bool((base.cagr >= 0.10).all()),
                "cagr25_both_base": bool((base.cagr >= 0.25).all()),
                "beats_passive_all_12": bool((compared.cagr > compared.cagr_control).all()),
                "every_complete_year10_both_base": bool(
                    years.trial.nunique() == 2 and (years["return"] >= 0.10).all()
                ),
            }
        )
    frame = pd.DataFrame(rows)
    counts = {c: int(frame[c].sum()) for c in frame if c not in {"symbol", "rule"}}
    return {"candidate_configurations": len(frame), **counts}, frame


def short_summary(short: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for horizon, group in short[short.rule.str.startswith("B")].groupby("horizon"):
        best = group.loc[group["return"].idxmax()]
        worst = group.loc[group["return"].idxmin()]
        rows.append(
            {
                "horizon": int(horizon),
                "accounts": len(group),
                "positive": int((group["return"] > 0).sum()),
                "negative": int((group["return"] < 0).sum()),
                "zero_trade": int((group.trades == 0).sum()),
                "median_return": float(group["return"].median()),
                "p05_return": float(group["return"].quantile(0.05)),
                "p95_return": float(group["return"].quantile(0.95)),
                "gain10": int((group["return"] >= 0.10).sum()),
                "gain25": int((group["return"] >= 0.25).sum()),
                "double": int((group["return"] >= 1).sum()),
                "hundredfold": int((group["return"] >= 99).sum()),
                "loss20": int((group["return"] <= -0.20).sum()),
                "loss50": int((group["return"] <= -0.50).sum()),
                "best": best.to_dict(),
                "worst": worst.to_dict(),
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    summary = pd.read_csv(args.run / "summary.csv")
    reg = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "docs/research/bot-study-registration-2026-10-21.json"
        ).read_text(encoding="utf-8")
    )
    expected = set(
        product(
            [x["symbol"] for x in reg["inputs"]],
            [x["id"] for x in reg["rules"]],
            reg["periods"],
            reg["costs_bps_per_side"],
            reg["lags_sessions"],
        )
    )
    axes = ["symbol", "rule", "window", "cost_bps", "lag"]
    if (
        len(summary) != 7290
        or summary[axes].duplicated().any()
        or set(summary[axes].itertuples(index=False, name=None)) != expected
    ):
        raise ValueError("Unexpected trial inventory")
    annual = pd.read_csv(args.run / "annual.csv.gz")
    short = pd.read_parquet(args.run / "fresh_starts.parquet")
    counts, classification = classify(summary, annual)
    classification.to_csv(output / "classification.csv", index=False)
    starts = short_summary(short)
    base_later = summary[
        (summary.window == "later") & (summary.cost_bps == 10) & (summary.lag == 1)
    ]
    selected = pd.read_csv(args.run / "training_selection.csv")[["symbol", "rule"]]
    stresses = selected.merge(summary[summary.window == "later"], on=["symbol", "rule"])
    if len(stresses) != 162:
        raise ValueError("Missing selected-rule later stress")
    stresses.to_csv(output / "selected_later_stresses.csv", index=False)
    selection = selected.merge(base_later, on=["symbol", "rule"])
    passive = base_later[base_later.rule == "C00"][["symbol", "cagr", "drawdown"]]
    selection = selection.merge(passive, on="symbol", suffixes=("", "_passive"))
    minimum_year = annual[annual.complete_calendar_year].groupby("trial")["return"].min()
    selection["worst_complete_year"] = selection.trial.map(minimum_year)
    selection.to_csv(output / "selected_later.csv", index=False)
    later_candidates = base_later[base_later.rule.str.startswith("B")]
    result = {
        "classification": counts,
        "primary_accounts": len(summary),
        "all_fresh_start_accounts": len(short),
        "annual_rows": len(annual),
        "short_candidate_results": starts,
        "later_candidate_positive": int((later_candidates.cagr > 0).sum()),
        "later_candidate_cagr10": int((later_candidates.cagr >= 0.10).sum()),
        "later_candidate_cagr25": int((later_candidates.cagr >= 0.25).sum()),
        "selected_later_beat_passive": int((selection.cagr > selection.cagr_passive).sum()),
        "selected_later_positive": int((selection.cagr > 0).sum()),
        "selected_later_cagr10": int((selection.cagr >= 0.10).sum()),
        "selected_later_cagr25": int((selection.cagr >= 0.25).sum()),
        "later_hindsight_top10": later_candidates.sort_values("cagr", ascending=False)
        .head(10)
        .to_dict("records"),
    }
    write_json(output / "findings.json", result)
    summary.to_csv(output / "primary-summary.csv", index=False)
    annual.to_csv(output / "annual-returns.csv.gz", index=False)
    pd.DataFrame(
        [{k: v for k, v in row.items() if k not in {"best", "worst"}} for row in starts]
    ).to_csv(output / "short-summary.csv", index=False)
    lines = [
        "# Bot-rule backtests — October21,2026",
        "",
        f"Executed **{len(summary):,} primary funded-account simulations** and **{len(short):,} fresh monthly-start accounts** from preserved data. These are 15 fixed rules (12 candidates, 3 controls) across 27 instruments—not that many independent algorithms. No external bot was run or claimed reproduced.",
        "",
        "The 27 instruments are 11 ordinary ETFs, 11 preselected surviving stocks and 5 actual leveraged ETFs. Signals are completed before the 1/2-session execution lag. Accounts begin with $1,000 and trade fractional adjusted wealth units with 10/25/50 bps per side. Actual share granularity, dividend payable dates, cash settlement and broker fills remain unqualified. No synthetic leveraged history is used.",
        "",
        "## Complete candidate inventory",
        "",
        "Base means 10 bps per side with a one-session execution lag. Full and later refer to each instrument's actual available full history and fresh 2014-2025, respectively.",
        f"Of 324 rule/instrument candidates, **{counts['positive_all_12']}** are positive in all 12 full/later cost/lag scenarios; **{counts['stable_all_12']}** also have smaller drawdowns than passive ownership of the same instrument in every scenario. This is not a comparison against SPY and does not fill the earlier stock-market-stability quota. **{counts['cagr10_both_base']}** reach 10% CAGR in both base windows and **{counts['cagr25_both_base']}** reach 25%. Categories overlap. **{counts['every_complete_year10_both_base']}** meet 10% in every complete calendar year in both base windows.",
        "",
        "Full available histories differ by IPO/inception and warmup; later is fresh 2014-2025. A matched passive control uses each candidate's exact dates. These are already-known, current-vintage histories with survivor selection; the later period is chronological evaluation, not an untouched holdout.",
        "The five cases above 25% CAGR in both base windows are NVDA/B12 and TSLA/B01, B02, B05, B12. They concentrate in two famous surviving winners, so they do not establish a broad stock-selection edge or five independent sources of profit.",
        "",
        "## Training-selected choices, fresh 2014-2025",
        "",
        "Each asset's candidate is selected only by its 2000-2013 available-history CAGR at 10 bps and lag 1, with ascending-ID ties. Selection on very short pre-2014 histories is weak evidence. This is an explicit per-asset comparison, not a portfolio combining all rows.",
        "",
        f"**{int((selection.cagr > selection.cagr_passive).sum())}/27** selected choices beat that asset's passive CAGR later. All 162 later cost/lag cases for these choices are preserved in [selected_later_stresses.csv](evidence/2026-10-21-bot-study/selected_later_stresses.csv). Source code, inputs and registration are frozen; there was no retuning after this result.",
        "",
        "| Instrument | Training choice | Later CAGR | Drawdown | Worst full year | Passive CAGR |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in selection.sort_values("symbol").itertuples():
        lines.append(
            f"|{row.symbol}|{row.rule}|{row.cagr:.2%}|{row.drawdown:.2%}|{row.worst_complete_year:.2%}|{row.cagr_passive:.2%}|"
        )
    lines += [
        "",
        "## Short-period outcomes",
        "",
        "Fresh $1,000 starts at the first eligible session of each month, 10 bps/side, lag 1; final close liquidation includes selling cost. Zero-trade periods remain. These overlapping starts are not independent and do not cover every possible entry date or intraday extreme. Returns below are whole-account returns, not annualized.",
        "",
        "| Evaluation window | Candidate accounts | Losing | No trades | Best | Worst | Doubled |100x|",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in starts:
        lines.append(
            f"|{row['horizon']} sessions|{row['accounts']:,}|{row['negative']:,}|{row['zero_trade']:,}|{row['best']['return']:.2%}|{row['worst']['return']:.2%}|{row['double']}|{row['hundredfold']}|"
        )
    lines += [
        "",
        "The best 63-session candidate-rule case is TSLA/B01 (MACD), March 1-May 30, 2013: +152.68%. Passive TSLA on the same dates gained 195.27%. The candidate figure is a hindsight maximum among the 12 candidate rules, not a forecast or a selected prospective trade.",
        "A five-session test cannot verify an 18-hour social-media claim. Best/worst rows are descriptive hindsight extrema; all starts and gain/loss frequencies remain in the private ledger and public summary. No routine income or future 100x claim follows.",
        "",
        "## What the experiment establishes",
        "",
        "The study measures deterministic price/volume rules inspired by inspectable bots. It does not test historical Grok conversations, today's search results as past news, options Greeks inferred from stock returns, or brokerage execution. Gap rules use completed daily adjusted gaps and differ materially from a live current-movers screener.",
        "",
        "The independent checker reconstructs signals, cash, costs, annual returns and every fresh-start result without importing the simulator. Its receipt is the authority for checked counts. Unit tests use artificial fixtures and are separate evidence. Drawdown includes observed open/close and cost marks, but not intraday lows.",
        "",
        "No new data fees, paid model calls or orders were incurred. No strategy is automatically promoted to paper or live trading. The practical next step is an actual-instrument/whole-share execution qualification of a frozen candidate and a prospective comparison against passive exposure, with a separate trustworthy-options-data plan.",
        "",
        "## Sources and reproduction",
        "",
        "- [Frozen rule/data registration](bot-study-registration-2026-10-21.json) and [preperformance clarifications](BOT-STUDY-PREPERFORMANCE-AMENDMENT-2026-10-21.md).",
        "- [Primary-source bot catalog](BOT-SOURCE-CATALOG-2026-10-21.md), [price-data/design notes](BOT-STOCK-DESIGN-NOTES-2026-10-21.md), and [separate options-index results](OPTION-BENCHMARK-RESULTS-2026-10-21.md).",
        "- [Every primary account](evidence/2026-10-21-bot-study/primary-summary.csv), [classifications](evidence/2026-10-21-bot-study/classification.csv), [short-period findings](evidence/2026-10-21-bot-study/findings.json), [training-selected later cases](evidence/2026-10-21-bot-study/selected_later.csv).",
        "- Commands: `python scripts/run_bot_study.py --parent <QuantLab-root> --output <new-empty-path>`; `python scripts/check_bot_study.py --help` for independent replay. Source hashes and original-input hashes are saved in started.json. Private archives preserve full inputs/signals/ledgers; no credentials belong in them.",
        "",
    ]
    (output.parent.parent / "BOT-STUDY-RESULTS-2026-10-21.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                k: v
                for k, v in result.items()
                if k not in {"short_candidate_results", "later_hindsight_top10"}
            }
        )
    )


if __name__ == "__main__":
    main()
