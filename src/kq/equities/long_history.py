"""Monthly research-index simulations; no broker, acquisition, or ETF history claims."""

import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]
INITIAL = 1000.0
BUDGET = 0.98
CONTROLS = ("CZERO", "CRF", "CMKT", "CEQ49")


@dataclass(frozen=True)
class MonthlyData:
    months: tuple[str, ...]
    symbols: tuple[str, ...]
    returns: FloatArray
    rf: FloatArray


def read_first_monthly(path: Path) -> pd.DataFrame:
    """Read only the first monthly section, rejecting duplicate or unordered dates."""
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip().startswith(","))
    end = start + 1
    while end < len(lines) and re.match(r"^\s*\d{6},", lines[end]):
        end += 1
    frame = pd.read_csv(io.StringIO("\n".join(lines[start:end])), index_col=0)
    frame.columns = frame.columns.str.strip()
    months = pd.PeriodIndex(frame.index.astype(str), freq="M")
    if months.has_duplicates or not months.is_monotonic_increasing:
        raise ValueError("Duplicate or unordered source months")
    frame.index = months
    return frame


def load_monthly(folder: Path) -> MonthlyData:
    expected = pd.period_range("1969-07", "2025-12", freq="M")
    industry = read_first_monthly(folder / "49_Industry_Portfolios.csv")
    factors = read_first_monthly(folder / "F-F_Research_Data_Factors.csv")
    industry = industry[(industry.index >= expected[0]) & (industry.index <= expected[-1])]
    factors = factors[(factors.index >= expected[0]) & (factors.index <= expected[-1])]
    if (
        not industry.index.equals(expected)
        or not factors.index.equals(expected)
        or len(industry.columns) != 49
        or industry.columns.has_duplicates
        or not {"Mkt-RF", "RF"} <= set(factors)
    ):
        raise ValueError("Source coverage or schema mismatch")
    raw = np.column_stack((industry.to_numpy(float), factors[["Mkt-RF", "RF"]]))
    if not np.isfinite(raw).all() or np.isin(raw, [-99.99, -999]).any():
        raise ValueError("Missing or nonfinite source return")
    returns = np.column_stack((industry.to_numpy(float), factors["Mkt-RF"] + factors["RF"])) / 100
    rf = factors["RF"].to_numpy(float) / 100
    if (returns <= -1).any() or (rf <= -1).any():
        raise ValueError("Invalid gross return")
    return MonthlyData(tuple(map(str, expected)), (*map(str, industry.columns), "MKT"), returns, rf)


def _rank_weights(score: FloatArray, symbols: tuple[str, ...], count: int) -> FloatArray:
    if not np.isfinite(score).all() or not 1 <= count <= len(score):
        raise ValueError("Invalid ranking")
    order = sorted(range(len(score)), key=lambda i: (-score[i], symbols[i]))
    result = np.zeros(50)
    result[order[:count]] = 1 / count
    return result


def static_target(  # noqa: PLR0912, PLR0915 -- explicit registered-family dispatch
    policy: dict[str, Any], data: MonthlyData, cutoff: int
) -> FloatArray:
    """Unscaled risky target. Cutoff is the last included completed return month."""
    family = policy["family"]
    length = int(policy["lookback"])
    stop = cutoff + 1 - int(family == "SKIPMOM")
    if stop - length < 0:
        raise ValueError("Insufficient signal warmup")
    block = data.returns[stop - length : stop, :49]
    rf = data.rf[stop - length : stop]
    if block.shape != (length, 49):
        raise ValueError("Invalid signal window")
    total = np.prod(1 + block, axis=0) - 1
    excess = block - rf[:, None]
    vol = np.std(block, axis=0, ddof=1) if length > 1 else np.zeros(49)
    downside = np.sqrt(np.mean(np.minimum(excess, 0) ** 2, axis=0))
    wealth = np.vstack((np.ones(49), np.cumprod(1 + block, axis=0)))
    target = np.zeros(50)
    score = None
    if family in {"MOM", "SKIPMOM"}:
        score = total
    elif family == "VOLMOM":
        score = total / np.maximum(vol, 0.001)
    elif family == "DOWNMOM":
        score = total / np.maximum(downside, 0.001)
    elif family in {"SHORTREV", "LONGREV"}:
        score = -total
    elif family == "LOWVOL":
        score = -vol
    elif family == "LOWBETA":
        market = data.returns[stop - length : stop, -1] - rf
        centered = market - market.mean()
        denominator = float(centered @ centered)
        score = -(centered @ (excess - excess.mean(axis=0))) / max(denominator, 1e-12)
    elif family == "LOWDD":
        score = np.min(wealth / np.maximum.accumulate(wealth, axis=0) - 1, axis=0)
    elif family == "ABSMOM":
        target[:49] = (total > np.prod(1 + rf) - 1) / 49
    elif family == "SMA":
        target[:49] = (wealth[-1] > wealth[-length:].mean(axis=0)) / 49
    elif family == "CHANNEL":
        low, high = wealth[-length:].min(axis=0), wealth[-length:].max(axis=0)
        score = np.divide(wealth[-1] - low, high - low, out=np.full(49, 0.5), where=high > low)
    elif family == "REGTREND":
        x = np.arange(length + 1, dtype=float)
        x -= x.mean()
        y = np.log(wealth)
        slope = (x @ y) / (x @ x)
        error = y - y.mean(axis=0) - x[:, None] * slope
        se = np.sqrt(np.sum(error**2, axis=0) / (length - 1) / (x @ x))
        score = slope / np.maximum(se, 1e-12)
    elif family == "CONSISTENCY":
        score = np.mean(excess > 0, axis=0)
    elif family in {"INVERSEVOL", "INVERSEDOWN"}:
        inverse = 1 / np.maximum(vol if family == "INVERSEVOL" else downside, 0.001)
        target[:49] = inverse / inverse.sum()
    elif family in {"VOLCAPEQ", "VOLCAPMKT"}:
        series = (
            block.mean(axis=1) if family == "VOLCAPEQ" else data.returns[stop - length : stop, -1]
        )
        annual_vol = float(np.std(series, ddof=1) * np.sqrt(12))
        scale = min(1.0, float(policy["target_vol"]) / max(annual_vol, 1e-12))
        if family == "VOLCAPEQ":
            target[:49] = scale / 49
        else:
            target[-1] = scale
    else:
        raise ValueError(f"Unknown static family: {family}")
    if score is not None:
        target = _rank_weights(score, data.symbols[:49], int(policy["top_k"]))
    if not np.isfinite(target).all() or target.min() < 0 or target.sum() > 1 + 1e-12:
        raise ValueError("Invalid calculated weights")
    return target


def insurance_target(policy: dict[str, Any], nav: float, peak: float) -> FloatArray:
    if nav <= 0 or peak < INITIAL or not np.isfinite([nav, peak]).all():
        raise ValueError("Invalid insurance state")
    base = peak if policy["family"] == "CPPIRATCHET" else INITIAL
    floor = float(policy["floor_fraction"]) * base
    exposure = np.clip(float(policy["multiplier"]) * (nav - floor) / nav, 0, 1)
    target = np.zeros(50)
    target[-1] = exposure
    return target


def rebalance_values(
    values: FloatArray, cash: float, weights: FloatArray, rate: float
) -> tuple[FloatArray, float, float, float]:
    """Fund all orders and costs from existing wealth; fixed-point fee solve."""
    if (
        values.shape != weights.shape
        or not np.isfinite(values).all()
        or not np.isfinite(weights).all()
        or values.min() < 0
        or weights.min() < 0
        or weights.sum() > 1 + 1e-12
        or cash < 0
        or not 0 <= rate < 1
    ):
        raise ValueError("Invalid account or target")
    before = float(values.sum() + cash)
    after = before
    for _ in range(100):
        updated = before - rate * float(np.abs(weights * after - values).sum())
        if abs(updated - after) < 1e-12 * max(before, 1.0):
            after = updated
            break
        after = updated
    else:
        raise ValueError("Fee solve did not converge")
    new_values = weights * after
    turnover = float(np.abs(new_values - values).sum())
    fee = rate * turnover
    new_cash = before - float(new_values.sum()) - fee
    if new_cash < -1e-8 or after <= 0:
        raise ValueError("Unfunded account")
    return new_values, max(0.0, new_cash), turnover, fee


def summarize_monthly(frame: pd.DataFrame) -> dict[str, Any]:
    ends = frame.ending_nav.to_numpy(float)
    beginnings = np.r_[INITIAL, ends[:-1]]
    returns = ends / beginnings - 1
    years = np.array([month[:4] for month in frame.month])
    annual = {year: float(np.prod(1 + returns[years == year]) - 1) for year in sorted(set(years))}
    marks = np.r_[
        INITIAL,
        frame[["before_nav", "after_cost_nav", "ending_before_terminal", "ending_nav"]]
        .to_numpy()
        .ravel(),
    ]
    drawdown = float(np.min(marks / np.maximum.accumulate(marks) - 1))
    result: dict[str, Any] = {
        "months": len(frame),
        "ending_nav": float(ends[-1]),
        "cagr": float((ends[-1] / INITIAL) ** (12 / len(frame)) - 1),
        "max_drawdown": drawdown,
        "annual": annual,
        "worst_year": min(annual.values()),
        "losing_years": sum(x < 0 for x in annual.values()),
        "years_ge_10pct": sum(x >= 0.1 for x in annual.values()),
        "years_ge_25pct": sum(x >= 0.25 for x in annual.values()),
        "all_years_ge_10pct": all(x >= 0.1 for x in annual.values()),
        "fees": float(frame.fee.sum()),
        "turnover": float(frame.turnover.sum()),
        "mean_risky_fraction": float(frame.risky_fraction.mean()),
        "trade_legs": int(frame.trade_legs.sum()),
        "sub_dollar_legs": int(frame.sub_dollar_legs.sum()),
    }
    for length in (12, 60, 120):
        if len(ends) >= length:
            ratio = np.r_[INITIAL, ends]
            rolling = (ratio[length:] / ratio[:-length]) ** (12 / length) - 1
            result[f"worst_rolling_{length}m_cagr"] = float(rolling.min())
    return result


def simulate_monthly(  # noqa: PLR0915 -- keep chronological accounting in one place
    data: MonthlyData,
    policy: dict[str, Any],
    start: str,
    end: str,
    cost_bps: int,
    lag: int,
    targets: FloatArray | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """One fresh funded account; price proxies and returned cash are monthly."""
    if lag not in (1, 2) or cost_bps not in (10, 25, 50):
        raise ValueError("Unregistered cost or lag")
    first, last = data.months.index(start), data.months.index(end)
    if first > last or first < 74:
        raise ValueError("Invalid account interval")
    family, identity = policy["family"], policy["id"]
    values, cash = np.zeros(50), INITIAL
    endings: list[float] = []
    rows: list[dict[str, Any]] = []
    position_rows: list[FloatArray] = []
    rate = cost_bps / 10000
    for pos in range(first, last + 1):
        local = pos - first
        cutoff = pos - lag
        before = float(values.sum() + cash)
        old = values.copy()
        reference = endings[local - lag] if local >= lag else INITIAL
        peak = max([INITIAL, *endings[: local - lag + 1]]) if local >= lag else INITIAL
        weights = np.zeros(50)
        if identity == "CMKT":
            weights[-1] = BUDGET
        elif identity == "CEQ49":
            weights[:49] = BUDGET / 49
        elif family in {"CPPIFIXED", "CPPIRATCHET"}:
            weights = BUDGET * insurance_target(policy, reference, peak)
        elif identity not in CONTROLS:
            if targets is None:
                raise ValueError("Static targets required")
            weights = BUDGET * targets[pos]
        if identity == "CMKT" and local > 0:
            turnover, fee = 0.0, 0.0
        else:
            values, cash, turnover, fee = rebalance_values(values, cash, weights, rate)
        changes = np.abs(values - old)
        trade_legs = int(np.sum(changes > 1e-9))
        tiny = int(np.sum((changes > 1e-9) & (changes < 1)))
        after_cost = float(values.sum() + cash)
        position_rows.append(values.copy())
        cash_after_cost = cash
        risky_fraction = float(values.sum() / after_cost)
        risky_pnl = float(values @ data.returns[pos])
        cash_pnl = cash * data.rf[pos] if identity != "CZERO" else 0.0
        values *= 1 + data.returns[pos]
        cash += cash_pnl
        ending_before_terminal = float(values.sum() + cash)
        terminal_fee = 0.0
        if pos == last:
            terminal_turnover = float(values.sum())
            terminal_fee = rate * terminal_turnover
            trade_legs += int(np.sum(values > 1e-9))
            tiny += int(np.sum((values > 1e-9) & (values < 1)))
            turnover += terminal_turnover
            cash += terminal_turnover - terminal_fee
            values[:] = 0
        ending = float(values.sum() + cash)
        endings.append(ending)
        rows.append(
            {
                "month": data.months[pos],
                "as_of": str(pd.Period(data.months[cutoff], freq="M").end_time.date()),
                "before_nav": before,
                "after_cost_nav": after_cost,
                "cash_after_cost": cash_after_cost,
                "ending_before_terminal": ending_before_terminal,
                "ending_nav": ending,
                "fee": fee + terminal_fee,
                "terminal_fee": terminal_fee,
                "turnover": turnover,
                "risky_pnl": risky_pnl,
                "cash_pnl": cash_pnl,
                "risky_fraction": risky_fraction,
                "reference_nav": reference,
                "reference_peak": peak,
                "trade_legs": trade_legs,
                "sub_dollar_legs": tiny,
            }
        )
    frame = pd.DataFrame(rows)
    frame.attrs["risky_after_cost"] = np.asarray(position_rows)
    return frame, summarize_monthly(frame)


def causal_regimes(data: MonthlyData, lag: int) -> dict[str, str]:
    """Labels from completed returns only; never future recession announcements."""
    vol: list[float] = []
    by_cutoff: dict[int, str] = {}
    for cutoff in range(11, len(data.months)):
        r = data.returns[cutoff - 11 : cutoff + 1, -1]
        cash = data.rf[cutoff - 11 : cutoff + 1]
        value = float(np.std(r, ddof=1))
        vol.append(value)
        trend = "up" if np.prod(1 + r) > np.prod(1 + cash) else "down"
        risk = "high_vol" if value > np.median(vol) else "low_vol"
        by_cutoff[cutoff] = trend + "_" + risk
    return {month: by_cutoff[i - lag] for i, month in enumerate(data.months) if i - lag >= 11}


def max_mean_bootstrap(excess: FloatArray, repeats: int = 2000) -> dict[str, Any]:
    """Centered stationary-block maximum-mean diagnostic, shared calendar resamples."""
    if (
        excess.ndim != 2
        or not np.isfinite(excess).all()
        or len(excess) < 12
        or not isinstance(repeats, int)
        or isinstance(repeats, bool)
        or repeats <= 0
        or excess.shape[1] == 0
    ):
        raise ValueError("Invalid bootstrap input")
    rng = np.random.default_rng(20261020)
    observed = excess.mean(axis=0)
    centered = excess - observed
    count, policies = excess.shape
    maxima = np.empty(repeats)
    unadjusted = np.zeros(policies)
    for b in range(repeats):
        indices = np.empty(count, dtype=int)
        indices[0] = rng.integers(count)
        for t in range(1, count):
            indices[t] = (
                rng.integers(count) if rng.random() < 1 / 6 else (indices[t - 1] + 1) % count
            )
        average = centered[indices].mean(axis=0)
        maxima[b] = average.max()
        unadjusted += average >= observed
    adjusted = (1 + (maxima[:, None] >= observed).sum(axis=0)) / (repeats + 1)
    return {
        "replicates": repeats,
        "seed": 20261020,
        "mean_block_months": 6,
        "mean_monthly_excess": observed.tolist(),
        "familywise_p": adjusted.tolist(),
        "unadjusted_p": ((1 + unadjusted) / (repeats + 1)).tolist(),
        "scope": (
            "Within these registered candidates only; current-vintage history "
            "and prior project selection remain limitations."
        ),
    }
