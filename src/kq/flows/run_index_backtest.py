"""``kq backtest-index`` — HAR-RV index-brackets backtest + manifest.

Phase C playbook gate 4 (honest backtest vs the benchmark). Reads the
backfilled ``index_daily`` closes, runs the rolling-origin HAR-RV vs
constant-vol comparison per symbol, attempts the market-implied comparison
where book snaps exist, and writes ``models/backtest_index_manifest.json``
(atomic, same pattern as the weather manifests).

PAPER TRADING IS DELIBERATELY ABSENT for the index lane: playbook gate 5
(paper with pre-registered N and bar) only opens once THIS flow's verdict
exists and has been reviewed — there is no ``paper-index-trade`` flow yet,
and none should be added until the manifest shows a verdict worth papering.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from kq.backtest.index_brackets import (
    IndexBacktestConfig,
    count_index_book_snaps,
    market_implied_comparison,
    run_index_backtest,
)
from kq.clients.yahoo_chart import INDEX_SYMBOLS
from kq.config import get_settings
from kq.flows.ingest_weather import _db_path_from_settings
from kq.flows.run_backtest import MODELS_DIR, write_manifest_atomic
from kq.storage.duckdb_store import connect
from kq.storage.repositories.index_daily import load_daily_closes

log = structlog.get_logger(__name__)

INDEX_BACKTEST_MANIFEST_PATH = MODELS_DIR / "backtest_index_manifest.json"


def main(*, db_path: Path | None = None) -> int:
    """Entrypoint. Returns 0 on success, 1 when no symbol had enough data."""
    settings = get_settings()
    path = db_path or _db_path_from_settings(settings.database_url)
    cfg = IndexBacktestConfig()
    log.info("backtest_index.starting", db=str(path))

    con = connect(path, read_only=True)
    symbols: dict[str, Any] = {}
    market_implied: dict[str, Any] = {}
    snap_counts: dict[str, int] = {}
    try:
        for symbol in INDEX_SYMBOLS:
            df = load_daily_closes(con, symbol)
            dates = list(df["valid_date"])
            closes = df["close"].to_numpy()
            result = run_index_backtest(dates, closes, symbol=symbol, config=cfg)
            if result is None:
                symbols[symbol] = {
                    "skipped": (
                        f"only {len(dates)} stored sessions — need > "
                        f"{cfg.initial_train_size + cfg.test_window_size + 1} "
                        "(run `kq backfill-index`)"
                    )
                }
            else:
                symbols[symbol] = result.to_summary_dict()
            snap_counts[symbol] = count_index_book_snaps(con, symbol)
            comparison = market_implied_comparison(con, dates, closes, symbol=symbol)
            market_implied[symbol] = (
                comparison if isinstance(comparison, str) else comparison.to_summary_dict()
            )
    finally:
        con.close()

    ran_market_implied = any(not isinstance(v, str) for v in market_implied.values())
    manifest: dict[str, Any] = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "strategy": "index_brackets_har_rv_v1",
        "evaluation": "rolling_origin_cv",
        # THE LINE THAT SAYS WHICH COMPARISON RAN — do not soften it.
        "comparison_ran": (
            "har_rv_vs_constant_vol AND har_rv_vs_market_implied"
            if ran_market_implied
            else "har_rv_vs_constant_vol ONLY (market-implied skipped; see market_implied)"
        ),
        "config": {
            "initial_train_size": cfg.initial_train_size,
            "test_window_size": cfg.test_window_size,
            "embargo": cfg.embargo,
            "ladder_half_brackets": cfg.ladder_half_brackets,
        },
        "index_book_snaps_stored": snap_counts,
        "honest_caveats": [
            "RV proxy is the squared daily close-to-close return (no intraday "
            "data on the free tier) — noisier than the literature's 5-minute "
            "realized variance; expect attenuated HAR coefficients.",
            "Return distribution is Normal(0, sigma): fat tails are underpriced; "
            "far-tail bracket probabilities are understated. Student-t is a v2 "
            "ticket.",
            "Synthetic ladder is centered on the prior close; the venue freezes "
            "its ladder at listing time overnight, so bracket alignment differs "
            "slightly on gap days.",
            "Brier-vs-constant-vol says whether HAR-RV has vol-dynamics skill; "
            "it says NOTHING about edge vs the market. Only the market-implied "
            "comparison (needs accumulated book snaps on the box) can show that, "
            "and paper trading stays OFF until it does.",
            "OHLC substrate is Yahoo's unofficial chart endpoint (Stooq is behind "
            "a JS wall as of 2026-07-02) — personal-use terms, no SLA; see "
            "kq/clients/yahoo_chart.py.",
        ],
        "symbols": symbols,
        "market_implied": market_implied,
    }
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    write_manifest_atomic(INDEX_BACKTEST_MANIFEST_PATH, manifest)
    log.info("backtest_index.done", manifest=str(INDEX_BACKTEST_MANIFEST_PATH))

    print(f"index backtest manifest -> {INDEX_BACKTEST_MANIFEST_PATH}")
    print(f"comparison ran: {manifest['comparison_ran']}")
    any_ran = False
    for symbol, summary in symbols.items():
        if "skipped" in summary:
            print(f"  {symbol}: skipped — {summary['skipped']}")
            continue
        any_ran = True
        print(
            f"  {symbol}: days={summary['n_days']:>4}  "
            f"brier_har={summary['brier_har_rv']:.4f} "
            f"vs_const={summary['brier_constant_vol']:.4f} "
            f"({summary['improvement_vs_const_pct']:+.1f}%)  "
            f"PIT mean={summary['pit_mean']:.3f} std={summary['pit_std']:.3f}"
        )
    for symbol, mi in market_implied.items():
        detail = (
            mi
            if isinstance(mi, str)
            else (
                f"days={mi['n_days']} brier_har={mi['brier_har_rv']:.4f} "
                f"vs_market={mi['brier_market_implied']:.4f}"
            )
        )
        print(f"  {symbol} market-implied: {detail}")
    return 0 if any_ran else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
