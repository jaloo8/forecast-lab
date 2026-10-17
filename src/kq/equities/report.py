"""Offline, escaped research report. Scores describe history, not probabilities."""

from __future__ import annotations

import math
from html import escape
from typing import Any
from urllib.parse import urlparse

import pandas as pd


def _number(value: Any, *, percent: bool = False, money: bool = False) -> str:
    try:
        number = float(value)
    except (ValueError, TypeError):
        return "Unavailable"
    if not math.isfinite(number):
        return "Unavailable"
    if percent:
        return f"{number * 100:,.2f}%"
    return f"${number:,.2f}" if money else f"{number:,.2f}"


def _text(value: Any) -> str:
    return escape(str(value))


def _rankings(research: pd.DataFrame) -> str:
    sections: list[str] = []
    for horizon, label in (
        (5, "Short · 5 sessions"),
        (20, "Medium · 20 sessions"),
        (126, "Long · 126 sessions"),
    ):
        rows = research[research.horizon_sessions == horizon] if not research.empty else research
        cells = []
        for row in rows.to_dict("records"):
            cells.append(
                "<tr>"
                + "".join(
                    f"<td>{cell}</td>"
                    for cell in (
                        _text(row["symbol"]),
                        _number(row["excess_momentum"], percent=True),
                        _number(row["momentum"], percent=True),
                        _number(row["volatility_20d"], percent=True),
                        _text(row["status"]),
                    )
                )
                + "</tr>"
            )
        table = (
            "<div class='scroll'><table><thead><tr><th>Stock</th><th>vs SPY</th>"
            "<th>Past return</th><th>20-day volatility*</th><th>Coverage</th>"
            "</tr></thead><tbody>" + "".join(cells) + "</tbody></table></div>"
        )
        sections.append(
            f"<section><h2>{label}</h2>"
            + (table if cells else "<p>No eligible stocks at this horizon.</p>")
            + "</section>"
        )
    return "".join(sections)


def _context(snapshot: dict[str, Any], research: pd.DataFrame) -> str:
    cards = []
    rows = research.drop_duplicates("symbol").to_dict("records") if not research.empty else []
    for row in rows:
        cards.append(
            f"<article><h3>{_text(row['symbol'])}</h3>"
            f"<p>{_text(row.get('sector', 'Unavailable'))}</p>"
            f"<p>P/E {_number(row.get('pe_ratio'))} · Market cap "
            f"{_number(row.get('market_cap'), money=True)}</p>"
            f"<p>Latest EPS {_number(row.get('latest_eps_actual'))} / "
            f"estimate {_number(row.get('latest_eps_estimate'))}</p></article>"
        )
    stories = []
    for item in snapshot.get("news", []):
        title = _text(item.get("title", "Untitled"))
        url = str(item.get("url", ""))
        parsed = urlparse(url)
        if parsed.scheme == "https" and parsed.netloc and not parsed.username:
            title = f"<a href='{escape(url, quote=True)}' rel='noreferrer'>{title}</a>"
        stories.append(
            f"<li><b>{_text(item.get('symbol', ''))}</b> {title}<small>"
            f"Source available: {_text(item.get('published_at', 'unknown'))} · "
            f"First retrieved: {_text(item.get('retrieved_at', 'unknown'))}</small></li>"
        )
    return (
        "<section><h2>Earnings &amp; financial context</h2><div class='cards'>"
        + "".join(cards)
        + "</div><p>Current snapshots only; not historical model inputs.</p>"
        "<h2>News &amp; filings</h2>"
        + (
            "<ul>" + "".join(stories) + "</ul>"
            if stories
            else "<p>No verified news in this snapshot.</p>"
        )
        + "<p>News is evidence for review. Its predictive value is not yet measured.</p></section>"
    )


def _outcomes(summary: dict[str, Any]) -> str:
    rows = []
    for result in summary.get("forecast_by_horizon", []):
        count = int(result["count"])
        cells = [_text(result["horizon_sessions"]), str(count)]
        cells.extend(
            _number(result.get(key), percent=True) if count else "Not yet measured"
            for key in ("mean_stock_return", "mean_benchmark_return", "mean_excess_return")
        )
        rows.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>")
    table = (
        (
            "<div class='scroll'><table><tr><th>Sessions</th><th>Scored</th>"
            "<th>Stock return</th><th>Matched SPY</th><th>Difference</th></tr>"
            + "".join(rows)
            + "</table></div>"
        )
        if rows
        else "<p>Not yet measured.</p>"
    )
    if summary.get("equity_valid") is False or summary.get("forecast_valid") is False:
        table = (
            "<p class='warning'>Historical prices changed. Outcomes need review; "
            "any displayed portfolio value is the last trusted estimate.</p>" + table
        )
    return (
        "<section><h2>Forward outcomes</h2>"
        + table
        + "<p>All recorded stocks, not just selected paper positions. Means are price returns "
        "before trading costs and dividends. Daily forecasts overlap and are not independent "
        "trials; these counts do not establish statistical confidence.</p></section>"
    )


def render_report(
    snapshot: dict[str, Any], research: pd.DataFrame, summary: dict[str, Any], snapshot_hash: str
) -> str:
    """Render local HTML without JavaScript, remote assets, or broker actions."""
    stats = {
        "Virtual equity": _number(summary.get("equity"), money=True),
        "Cash": _number(summary.get("cash"), money=True),
        "Reserved": _number(summary.get("reserved_cash"), money=True),
        "Profit / loss": _number(summary.get("pnl"), money=True),
    }
    tiles = "".join(
        f"<article><small>{name}</small><strong>{value}</strong></article>"
        for name, value in stats.items()
    )
    warnings = "".join(f"<li>{_text(value)}</li>" for value in snapshot.get("source_errors", []))
    if summary.get("delayed_recovery"):
        warnings += (
            "<li>Outage recovery: pre-existing paper instructions were recognized late. "
            "Their historical simulated fills are not evidence of on-time execution. "
            "No stock selections were created for missed sessions.</li>"
        )
    expected = set(snapshot.get("universe", [])) or {
        item["symbol"] for item in snapshot.get("bars", []) if item.get("symbol") != "SPY"
    }
    eligible = set(research["symbol"]) if not research.empty else set()
    excluded = sorted(expected - eligible)
    if excluded:
        warnings += (
            "<li>Excluded from rankings (missing, stale or incomplete history): "
            + _text(", ".join(excluded))
            + ". No successful outcome is inferred.</li>"
        )
    if summary.get("stale_symbols"):
        warnings += "<li>Stale paper marks: " + _text(summary["stale_symbols"]) + "</li>"
    paused = (
        f"<p class='warning'>New paper entries paused: "
        f"{_text(summary.get('pause_reason', 'review required'))}</p>"
        if summary.get("paused")
        else ""
    )
    counts = " · ".join(
        f"{label}: {_text(summary.get(key, 0))}"
        for key, label in (
            ("pending_count", "Pending"),
            ("open_count", "Open"),
            ("closed_count", "Closed"),
            ("forecast_settled_count", "Scored forecasts"),
        )
    )
    css = """
    :root{color-scheme:light}*{box-sizing:border-box}body{margin:0;background:#f4f6f8;
    color:#152635;font:16px/1.55 system-ui,sans-serif}main{max-width:1120px;margin:auto;
    padding:32px 24px}h1{font-size:36px;line-height:1.15;margin:14px 0}h2{font-size:22px}
    h3{margin:0}section{margin:24px 0;background:white;padding:24px;border-radius:12px}
    .tag{color:#126c58;font-weight:700;letter-spacing:.1em;font-size:12px}.cards{display:grid;
    grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}article{background:#edf3f5;
    padding:18px;border-radius:8px}strong{display:block;font-size:28px}small{display:block;
    color:#536775;overflow-wrap:anywhere}.scroll{overflow-x:auto}table{border-collapse:collapse;
    width:100%;white-space:nowrap}th,td{text-align:left;border-bottom:1px solid #e0e7ec;
    padding:12px 14px}th{font-size:13px;color:#536775}a{color:#126c58}li{margin:12px 0}
    .warning{background:#fff1db;padding:14px;border-radius:8px}footer{font-size:12px;
    overflow-wrap:anywhere;color:#536775}@media(max-width:600px){main{padding:18px 12px}
    section{padding:16px}h1{font-size:30px}}
    """
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>Stock Paper Lab</title><style>{css}</style></head><body><main>"
        "<span class='tag'>PAPER ONLY · BASELINE EXPERIMENT</span><h1>Stock Paper Lab</h1>"
        f"<p>Captured {_text(snapshot.get('captured_at'))} · Benchmark SPY</p>"
        "<p>Six-stock research pilot. No live orders. A ranking is not a probability "
        "or a recommendation. Forecasting skill is not established.</p>"
        f"<section><h2>$100 virtual pilot</h2><div class='cards'>{tiles}</div>"
        f"<p>{counts}</p>{paused}<p>Medium horizon only · $10 per position · up to five "
        "positions · 0.10% adverse execution each way · pause at $10 marked loss.</p>"
        "<p>Orders wait for a later session. Returns exclude dividends and taxes. "
        "The pause threshold cannot guarantee a maximum loss.</p></section>"
        + _outcomes(summary)
        + "<h2>Historical strength, by horizon</h2><p>Sorted by past return minus SPY "
        "over the same sessions. These are baseline features, not predicted returns.</p>"
        + _rankings(research)
        + "<p>*Volatility is the daily standard deviation "
        "of the most recent 20 daily returns.</p>"
        + _context(snapshot, research)
        + f"<section><h2>Data limitations &amp; refresh</h2><ul>{warnings}</ul>"
        "<p>This report is a saved snapshot. It does not refresh itself. Import a new "
        "dated snapshot to update pending orders and outcomes. No profitable record "
        "can be inferred until forecasts mature.</p></section>"
        f"<footer>Method: momentum_baseline_v1 · Snapshot SHA-256: {_text(snapshot_hash)}"
        "</footer></main></body></html>"
    )
