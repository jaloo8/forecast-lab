"""Rolling-origin backtest of HAR-RV bracket probabilities (Phase C).

Judges the HAR-RV benchmark against a naive constant-vol null on a
synthetic bracket ladder that mirrors the live venue's geometry (25-point
S&P / 100-point Nasdaq between-brackets plus two tails, .9999-style cap
encoding, verified on prod 2026-07-02 — see
``kq.clients.kalshi._ticker_parser_index``).

Two comparisons exist; the manifest must say which one actually ran:

1. **HAR-RV vs constant-vol** on backfilled OHLC — always available once
   ``kq backfill-index`` has run. This is the v1 verdict.
2. **HAR-RV vs the market-implied distribution** reconstructed from stored
   ``kalshi_book_snap`` rows (the Pinnacle-analog) — activates on the box
   once the Kalshi ingest has accumulated index book snapshots. On a fresh
   clone there are none, and this comparison reports itself as skipped
   rather than silently vanishing.

CV discipline: ``kq.models.cv.rolling_origin_splits`` — growing train,
non-overlapping test windows, embargo. Every prediction for test day T+1
uses coefficients fit strictly on earlier returns and HAR features ending
at day T's realized return; nothing from T+1 onward can leak (pinned by
test: mutating future closes must not change earlier predictions).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Final

import duckdb
import numpy as np
import structlog

from kq.clients.kalshi._ticker_parser_index import (
    INDEX_BRACKET_WIDTH,
    INDEX_STRIKE_HALF_WIDTH,
    SYMBOL_TO_INDEX_SERIES,
    parse_index_market_ticker,
)
from kq.clients.kalshi.strikes import Strike, yes_outcome, yes_prob
from kq.models.calibration import brier_score
from kq.models.cv import rolling_origin_splits
from kq.models.har_rv import (
    MONTHLY_WINDOW,
    constant_vol_sigma,
    fit_har_rv,
    log_returns,
    make_prob_gt,
    pit_value,
    predict_sigma,
)

log = structlog.get_logger(__name__)

# Venue cap encoding: a between-cap sits epsilon below the next bracket's
# floor (S&P: 7824.9999; Nasdaq: 31599.99). Verified on prod 2026-07-02.
INDEX_STRIKE_EPSILON: Final[dict[str, float]] = {
    "SPX": 0.0001,
    "NDX": 0.01,
}

# Between-brackets per side of the center bracket. 7 x 25 = ±175 S&P points
# (≈ ±3 daily sigma at recent vol) before the tails absorb the rest —
# roughly the ladder depth the venue lists per event (30 markets).
LADDER_HALF_BRACKETS: Final = 7

# A usable market-implied ladder needs enough priced brackets to cover the
# distribution's body; below this the renormalized probs are mostly noise.
MIN_PRICED_BRACKETS: Final = 5


@dataclass(frozen=True, slots=True)
class IndexBacktestConfig:
    initial_train_size: int = 250  # ~1 trading year of returns
    test_window_size: int = 25
    embargo: int = 1
    ladder_half_brackets: int = LADDER_HALF_BRACKETS


@dataclass(frozen=True, slots=True)
class IndexBacktestResult:
    symbol: str
    n_folds: int
    n_days: int
    n_evaluated: int  # (day, bracket) pairs, each counted once
    brier_har: float
    brier_const: float
    improvement_vs_const_pct: float  # positive = HAR-RV better
    pit_mean: float  # ~0.5 when calibrated
    pit_std: float  # ~0.289 (sqrt(1/12)) when calibrated
    first_test_date: date
    last_test_date: date

    def to_summary_dict(self) -> dict[str, object]:
        return {
            "n_folds": self.n_folds,
            "n_days": self.n_days,
            "n_evaluated": self.n_evaluated,
            "brier_har_rv": round(self.brier_har, 6),
            "brier_constant_vol": round(self.brier_const, 6),
            "improvement_vs_const_pct": round(self.improvement_vs_const_pct, 2),
            "pit_mean": round(self.pit_mean, 4),
            "pit_std": round(self.pit_std, 4),
            "first_test_date": self.first_test_date.isoformat(),
            "last_test_date": self.last_test_date.isoformat(),
        }


def build_ladder(prev_close: float, *, symbol: str, half_brackets: int) -> list[Strike]:
    """Venue-mirroring strike ladder centered on the previous close.

    The real ladder is frozen by Kalshi when the event lists (overnight,
    near the prior close); centering on the prior close reproduces that
    geometry without a historical listings archive — an honest-caveats
    entry, not a hidden assumption.
    """
    width = INDEX_BRACKET_WIDTH[symbol]
    eps = INDEX_STRIKE_EPSILON[symbol]
    center_floor = float(np.floor(prev_close / width) * width)
    floors = [center_floor + k * width for k in range(-half_brackets, half_brackets + 1)]
    ladder: list[Strike] = [Strike(kind="less", floor=None, cap=floors[0])]
    ladder += [Strike(kind="between", floor=f, cap=f + width - eps) for f in floors]
    ladder.append(Strike(kind="greater", floor=floors[-1] + width - eps, cap=None))
    return ladder


def _ladder_probs(ladder: list[Strike], prev_close: float, sigma: float) -> np.ndarray:
    prob_gt = make_prob_gt(prev_close, sigma)
    return np.array(
        [yes_prob(s, prob_gt, half_width=INDEX_STRIKE_HALF_WIDTH) for s in ladder], dtype=float
    )


def _ladder_outcomes(ladder: list[Strike], observed_close: float) -> np.ndarray:
    return np.array(
        [
            1.0 if yes_outcome(s, observed_close, half_width=INDEX_STRIKE_HALF_WIDTH) else 0.0
            for s in ladder
        ],
        dtype=float,
    )


def run_index_backtest(
    dates: list[date],
    closes: np.ndarray,
    *,
    symbol: str,
    config: IndexBacktestConfig | None = None,
) -> IndexBacktestResult | None:
    """HAR-RV vs constant-vol over rolling-origin folds. None = not enough data."""
    cfg = config or IndexBacktestConfig()
    closes = np.asarray(closes, dtype=float)
    if len(dates) != len(closes):
        raise ValueError("dates and closes must be the same length")
    returns = log_returns(closes)  # returns[k] = return realized on day k+1

    probs_har: list[np.ndarray] = []
    probs_const: list[np.ndarray] = []
    outcomes: list[np.ndarray] = []
    pits: list[float] = []
    test_dates: list[date] = []
    n_folds = 0

    for train_idx, test_idx in rolling_origin_splits(
        len(returns),
        initial_train_size=cfg.initial_train_size,
        test_window_size=cfg.test_window_size,
        embargo=cfg.embargo,
    ):
        fit = fit_har_rv(returns[train_idx])
        sigma_const = constant_vol_sigma(returns[train_idx])
        n_folds += 1
        for k in test_idx:
            if k < MONTHLY_WINDOW:  # pragma: no cover — initial_train_size >> window
                continue
            prev_close = float(closes[k])
            observed_close = float(closes[k + 1])
            sigma_har = predict_sigma(fit, returns[:k])
            ladder = build_ladder(prev_close, symbol=symbol, half_brackets=cfg.ladder_half_brackets)
            probs_har.append(_ladder_probs(ladder, prev_close, sigma_har))
            probs_const.append(_ladder_probs(ladder, prev_close, sigma_const))
            outcomes.append(_ladder_outcomes(ladder, observed_close))
            pits.append(pit_value(prev_close, sigma_har, observed_close))
            test_dates.append(dates[k + 1])

    if not outcomes:
        return None
    p_har = np.concatenate(probs_har)
    p_const = np.concatenate(probs_const)
    y = np.concatenate(outcomes)
    brier_har = brier_score(p_har, y)
    brier_const = brier_score(p_const, y)
    improvement = (brier_const - brier_har) / brier_const * 100.0 if brier_const > 0 else 0.0
    pit_arr = np.asarray(pits, dtype=float)
    return IndexBacktestResult(
        symbol=symbol,
        n_folds=n_folds,
        n_days=len(test_dates),
        n_evaluated=int(y.size),
        brier_har=brier_har,
        brier_const=brier_const,
        improvement_vs_const_pct=improvement,
        pit_mean=float(np.mean(pit_arr)),
        pit_std=float(np.std(pit_arr)),
        first_test_date=min(test_dates),
        last_test_date=max(test_dates),
    )


@dataclass(frozen=True, slots=True)
class MarketImpliedResult:
    """HAR-RV vs market-implied Brier on the snap-covered subset."""

    symbol: str
    n_days: int
    n_evaluated: int
    brier_har: float
    brier_market: float

    def to_summary_dict(self) -> dict[str, object]:
        return {
            "n_days": self.n_days,
            "n_evaluated": self.n_evaluated,
            "brier_har_rv": round(self.brier_har, 6),
            "brier_market_implied": round(self.brier_market, 6),
        }


def count_index_book_snaps(con: duckdb.DuckDBPyConnection, symbol: str) -> int:
    """How many stored orderbook snapshots exist for this symbol's series."""
    series = SYMBOL_TO_INDEX_SERIES[symbol]
    row = con.execute(
        "SELECT COUNT(*) FROM kalshi_book_snap WHERE ticker LIKE ?",
        [f"{series}-%"],
    ).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def market_implied_comparison(
    con: duckdb.DuckDBPyConnection,
    dates: list[date],
    closes: np.ndarray,
    *,
    symbol: str,
) -> MarketImpliedResult | str:
    """Compare HAR-RV against the market-implied distribution where snaps exist.

    Reconstructs per-session bracket probabilities from the LAST stored
    orderbook snapshot per market (mid of yes_bid/yes_ask, renormalized
    over the priced part of the ladder) and scores both distributions on
    the SAME restricted strike set. Returns a reason string instead of a
    result when the comparison cannot run — the manifest prints it
    verbatim, so "didn't run" is always explicit, never a silent zero.
    """
    series = SYMBOL_TO_INDEX_SERIES[symbol]
    n_snaps = count_index_book_snaps(con, symbol)
    if n_snaps == 0:
        return (
            f"skipped: 0 {series} orderbook snapshots in kalshi_book_snap on this "
            "machine — activates once the Kalshi ingest accumulates index snaps"
        )
    rows = con.execute(
        """
        SELECT s.ticker, s.snap_time, s.yes_bid, s.yes_ask,
               m.strike_type, m.floor_strike, m.cap_strike
        FROM kalshi_book_snap s
        JOIN kalshi_market m ON s.ticker = m.ticker
        WHERE s.ticker LIKE ?
          AND s.yes_bid IS NOT NULL AND s.yes_ask IS NOT NULL
          AND m.strike_type IS NOT NULL
        ORDER BY s.snap_time
        """,
        [f"{series}-%"],
    ).fetchall()
    close_by_date = dict(zip(dates, (float(c) for c in closes), strict=True))
    prev_close_by_date = dict(zip(dates[1:], (float(c) for c in closes[:-1]), strict=True))
    returns = log_returns(np.asarray(closes, dtype=float))

    # Last snapshot wins per ticker (rows are snap_time-ordered).
    latest: dict[str, tuple[float, str, float | None, float | None]] = {}
    for ticker, _snap_time, yes_bid, yes_ask, strike_type, floor_s, cap_s in rows:
        mid = (float(yes_bid) + float(yes_ask)) / 2.0
        latest[str(ticker)] = (
            mid,
            str(strike_type),
            None if floor_s is None else float(floor_s),
            None if cap_s is None else float(cap_s),
        )

    by_session: dict[date, list[tuple[Strike, float]]] = {}
    for ticker, (mid, strike_type, floor_s, cap_s) in latest.items():
        ref = parse_index_market_ticker(ticker)
        if ref is None or strike_type not in ("greater", "less", "between"):
            continue
        try:
            strike = Strike(kind=strike_type, floor=floor_s, cap=cap_s)  # type: ignore[arg-type]
        except ValueError:
            continue
        by_session.setdefault(ref.valid_date, []).append((strike, mid))

    probs_har: list[float] = []
    probs_market: list[float] = []
    outcomes: list[float] = []
    n_days = 0
    for session, strike_mids in sorted(by_session.items()):
        observed = close_by_date.get(session)
        prev_close = prev_close_by_date.get(session)
        if observed is None or prev_close is None:
            continue
        if len(strike_mids) < MIN_PRICED_BRACKETS:
            continue
        date_pos = dates.index(session)
        train_returns = returns[: date_pos - 1]  # ends at prev session's realized return
        try:
            fit = fit_har_rv(train_returns)
            sigma = predict_sigma(fit, train_returns)
        except ValueError:  # not enough OHLC history before this session
            continue
        prob_gt = make_prob_gt(prev_close, sigma)
        total_mid = sum(mid for _s, mid in strike_mids)
        if total_mid <= 0.0:
            continue
        n_days += 1
        for strike, mid in strike_mids:
            probs_market.append(mid / total_mid)
            probs_har.append(yes_prob(strike, prob_gt, half_width=INDEX_STRIKE_HALF_WIDTH))
            outcomes.append(
                1.0 if yes_outcome(strike, observed, half_width=INDEX_STRIKE_HALF_WIDTH) else 0.0
            )
    if not outcomes:
        return (
            f"skipped: {n_snaps} {series} snaps exist but none joined to a settled "
            "session with enough priced brackets and OHLC history"
        )
    y = np.asarray(outcomes, dtype=float)
    return MarketImpliedResult(
        symbol=symbol,
        n_days=n_days,
        n_evaluated=int(y.size),
        brier_har=brier_score(np.asarray(probs_har), y),
        brier_market=brier_score(np.asarray(probs_market), y),
    )
