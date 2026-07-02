"""``kq doctor`` — reality-contact diagnostics.

The 2026-06-11 audit found that 1,101 green tests coexisted with a system
that could not place a single prod trade: every test validated the code
against the author's assumptions, and the fixtures encoded those same
assumptions. This flow is the standing antidote — it checks the system
against the *live venue* and the *real database*, the two things a hermetic
suite structurally cannot see.

Posture: deliberately NON-hermetic. ``kq health-check`` is the cron-safe,
local-only heartbeat; ``kq doctor`` makes real network calls to Kalshi's
public market endpoints (no auth required — verified 2026-06-11) and reads
the live DuckDB. Run it manually after any deploy, and weekly via
``scripts/reality-probe.sh`` (alerts on CRIT).

Checks:

1. **payload-shape** — fetch live markets per weather series; the parser
   must yield non-None prices (the exact failure class of audit finding #1:
   prod moved to ``*_dollars`` fields and every price parsed as None,
   silently, for weeks).
2. **parser-coverage** — how many live markets are eligible for trading
   under the current matcher (strike-type guard); reports visible/total and
   the strike-type mix so "the book shrank" is loud, not silent.
3. **settlement-source** — extract the station named in ``rules_primary``
   and compare against our ICAO mapping (the audit's Central Park finding:
   KXHIGHNY settles on KNYC; the pipeline modeled KJFK until PR-C rerouted
   it). Any future mismatch is CRIT — visible beats silent.
4. **orderbook-shape** — fetch one live orderbook; the parser must produce
   a usable book (audit finding: prod moved to ``orderbook_fp`` and every
   snapshot parsed empty).
5. **observed-truth freshness** — ``weather_observed`` recency in the live
   DB; stale truth means settlement silently never fires (audit finding #7).
6. **phase5-clocks** — settled-trade count, last settlement, last priced
   book snap: the "is the evidence clock actually ticking?" panel.

Exit codes match health-check: 0 = all OK, 1 = WARN, 2 = CRIT.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx
import structlog

from kq.backtest.bracket_match import parsed_weather_markets
from kq.clients.kalshi._parsers import _parse_market, _parse_orderbook
from kq.clients.stations import STATIONS
from kq.config import get_settings
from kq.flows.ingest_weather import _db_path_from_settings
from kq.storage.duckdb_store import connect

log = structlog.get_logger(__name__)

Severity = Literal["ok", "warn", "crit", "info"]

# Public (unauthenticated) prod market-data endpoints, verified 2026-06-11.
PROD_BASE = "https://api.elections.kalshi.com/trade-api/v2"

# Expected settlement station per Kalshi weather series, from rules_primary.
# THE MAPPING ENCODES THE AUDIT'S CENTRAL PARK FINDING (root cause #4):
# Kalshi's NY series settles on Central Park (KNYC). PR-C rerouted the whole
# NY pipeline from KJFK to KNYC, so the check now passes — it stays here to
# catch Kalshi ever moving a settlement source out from under us.
EXPECTED_RULES_SUBSTRING: dict[str, str] = {
    "KXHIGHLAX": "Los Angeles",
    "KXHIGHNY": "Central Park",
    "KXHIGHCHI": "Midway",
    "KXHIGHMIA": "Miami",
    "KXHIGHDEN": "Denver",
    "KXHIGHAUS": "Austin",
}

# What our pipeline CURRENTLY models per series (stations.py). The doctor
# cross-checks this against Kalshi's rules text.
PIPELINE_STATION_NAME: dict[str, str] = {
    "KXHIGHLAX": "Los Angeles",  # KLAX — matches
    "KXHIGHNY": "Central Park",  # KNYC — matches since PR-C (audit root cause #4)
    "KXHIGHCHI": "Midway",  # KMDW — matches
    "KXHIGHMIA": "Miami",  # KMIA — matches
    "KXHIGHDEN": "Denver",  # KDEN — matches
    "KXHIGHAUS": "Austin",  # KAUS — matches
}


@dataclass(frozen=True, slots=True)
class DoctorCheck:
    name: str
    severity: Severity
    detail: str


def _fetch_json(client: httpx.Client, path: str, params: dict[str, Any] | None = None) -> Any:
    resp = client.get(f"{PROD_BASE}{path}", params=params)
    resp.raise_for_status()
    return resp.json()


def check_payload_shape(series_payloads: dict[str, Any]) -> list[DoctorCheck]:
    """Audit finding #1 guard: live markets must parse with usable prices."""
    out: list[DoctorCheck] = []
    for series, payload in series_payloads.items():
        if isinstance(payload, Exception):
            out.append(DoctorCheck(f"payload-shape.{series}", "warn", f"fetch failed: {payload}"))
            continue
        raw_markets = payload.get("markets", [])
        if not raw_markets:
            out.append(
                DoctorCheck(
                    f"payload-shape.{series}",
                    "warn",
                    "0 open markets (seasonal lull or series renamed — verify manually)",
                )
            )
            continue
        parsed = [_parse_market(m) for m in raw_markets]
        priced = [m for m in parsed if m.yes_bid is not None and m.yes_ask is not None]
        striked = [m for m in parsed if m.strike_type in {"greater", "less", "between"}]
        if not priced:
            out.append(
                DoctorCheck(
                    f"payload-shape.{series}",
                    "crit",
                    f"{len(parsed)} markets, 0 with parseable prices — wire format drifted "
                    "again (this is exactly audit finding #1; update _parsers.py + fixtures)",
                )
            )
        elif len(striked) < len(parsed):
            out.append(
                DoctorCheck(
                    f"payload-shape.{series}",
                    "warn",
                    f"{len(parsed) - len(striked)}/{len(parsed)} markets missing strike_type",
                )
            )
        else:
            out.append(
                DoctorCheck(
                    f"payload-shape.{series}",
                    "ok",
                    f"{len(priced)}/{len(parsed)} priced, strike fields present",
                )
            )
    return out


def check_parser_coverage(series_payloads: dict[str, Any]) -> list[DoctorCheck]:
    """How much of the live book can the matcher actually trade right now?

    Since PR-B the strike-aware matcher admits greater, less, AND between
    markets; anything ineligible here means missing/inconsistent strike
    fields (payload drift) — keep this number loud so 'cron green' is never
    mistaken for 'trading the whole book'.
    """
    out: list[DoctorCheck] = []
    for series, payload in series_payloads.items():
        if isinstance(payload, Exception):
            out.append(DoctorCheck(f"parser-coverage.{series}", "warn", f"fetch failed: {payload}"))
            continue
        parsed = [_parse_market(m) for m in payload.get("markets", [])]
        if not parsed:
            out.append(DoctorCheck(f"parser-coverage.{series}", "info", "0 open markets"))
            continue
        eligible = parsed_weather_markets(parsed)
        mix: dict[str, int] = {}
        for m in parsed:
            mix[m.strike_type or "none"] = mix.get(m.strike_type or "none", 0) + 1
        sev: Severity = "ok" if eligible else "crit"
        out.append(
            DoctorCheck(
                f"parser-coverage.{series}",
                sev,
                f"{len(eligible)}/{len(parsed)} tradeable under current matcher; mix={mix}",
            )
        )
    return out


def check_settlement_source(series_payloads: dict[str, Any]) -> list[DoctorCheck]:
    """Audit Central-Park-class guard: rules_primary must name the station
    our pipeline models. A mismatch means we forecast the wrong place."""
    out: list[DoctorCheck] = []
    for series, payload in series_payloads.items():
        expected = EXPECTED_RULES_SUBSTRING.get(series)
        modeled = PIPELINE_STATION_NAME.get(series)
        if expected is None or modeled is None:
            continue
        if isinstance(payload, Exception):
            out.append(
                DoctorCheck(f"settlement-source.{series}", "warn", f"fetch failed: {payload}")
            )
            continue
        markets = payload.get("markets", [])
        if not markets:
            out.append(
                DoctorCheck(f"settlement-source.{series}", "info", "no open market to probe")
            )
            continue
        rules = str(markets[0].get("rules_primary", ""))
        if expected not in rules:
            out.append(
                DoctorCheck(
                    f"settlement-source.{series}",
                    "crit",
                    f"rules_primary no longer mentions {expected!r} — Kalshi changed the "
                    f"settlement source; re-audit. rules: {rules[:140]!r}",
                )
            )
        elif expected != modeled and modeled not in rules:
            out.append(
                DoctorCheck(
                    f"settlement-source.{series}",
                    "crit",
                    f"contract settles on {expected!r} but pipeline models {modeled!r} "
                    "(the Central-Park failure class — must stay loud until actually fixed)",
                )
            )
        else:
            out.append(DoctorCheck(f"settlement-source.{series}", "ok", f"settles on {expected!r}"))
    return out


def check_orderbook_shape(
    client: httpx.Client, series_payloads: dict[str, Any]
) -> list[DoctorCheck]:
    """Audit orderbook_fp guard: one live book must parse to a usable snapshot."""
    for payload in series_payloads.values():
        if isinstance(payload, Exception):
            continue
        markets = payload.get("markets", [])
        if not markets:
            continue
        ticker = str(markets[0]["ticker"])
        try:
            book = _fetch_json(client, f"/markets/{ticker}/orderbook")
        except httpx.HTTPError as exc:
            return [DoctorCheck("orderbook-shape", "warn", f"fetch failed: {exc}")]
        snap = _parse_orderbook(book, ticker=ticker, snap_time=datetime.now(tz=UTC))
        if not snap.yes_bids and not snap.yes_asks:
            return [
                DoctorCheck(
                    "orderbook-shape",
                    "crit",
                    f"{ticker}: book parsed EMPTY while raw payload keys={list(book.keys())} — "
                    "orderbook wire format drifted (audit finding class #1)",
                )
            ]
        return [
            DoctorCheck(
                "orderbook-shape",
                "ok",
                f"{ticker}: bid={snap.yes_bid} ask={snap.yes_ask} "
                f"depth={len(snap.yes_bids)}/{len(snap.yes_asks)}",
            )
        ]
    return [DoctorCheck("orderbook-shape", "info", "no open market found to probe")]


def check_observed_truth(db_path: Path) -> list[DoctorCheck]:
    """Audit finding #7 guard: settlement is impossible without fresh truth."""
    con = connect(db_path)
    try:
        row = con.execute("SELECT MAX(valid_date) FROM weather_observed").fetchone()
    except Exception as exc:  # table missing on a fresh clone
        return [DoctorCheck("observed-truth", "warn", f"weather_observed unreadable: {exc}")]
    finally:
        con.close()
    latest = row[0] if row else None
    if latest is None:
        return [
            DoctorCheck(
                "observed-truth", "crit", "weather_observed is EMPTY — settlement can never fire"
            )
        ]
    age_days = (datetime.now(tz=UTC).date() - latest).days
    if age_days > 3:
        return [
            DoctorCheck(
                "observed-truth",
                "crit",
                f"truth is {age_days} days stale (latest {latest}) — paper trades will sit "
                "unsettled; check the ACIS ingest cron (PR-G)",
            )
        ]
    return [DoctorCheck("observed-truth", "ok", f"latest observed {latest} ({age_days}d old)")]


def check_phase5_clocks(db_path: Path) -> list[DoctorCheck]:
    """The 'is the evidence clock actually ticking?' panel."""
    con = connect(db_path)
    try:
        try:
            n_settled = con.execute(
                "SELECT COUNT(*) FROM paper_trade WHERE settled_at IS NOT NULL"
            ).fetchone()
            last_settle = con.execute("SELECT MAX(settled_at) FROM paper_trade").fetchone()
            last_snap = con.execute(
                "SELECT MAX(snap_time) FROM kalshi_book_snap WHERE yes_bid IS NOT NULL"
            ).fetchone()
        except Exception as exc:
            return [DoctorCheck("phase5-clocks", "warn", f"tables unreadable: {exc}")]
    finally:
        con.close()
    settled = int(n_settled[0]) if n_settled and n_settled[0] is not None else 0
    detail = (
        f"settled_trades={settled}/500 (Phase 5 #1), "
        f"last_settlement={last_settle[0] if last_settle else None}, "
        f"last_PRICED_book_snap={last_snap[0] if last_snap else None}"
    )
    return [DoctorCheck("phase5-clocks", "info", detail)]


def run_doctor(*, db_path: Path | None = None, timeout_s: float = 15.0) -> list[DoctorCheck]:
    settings = get_settings()
    path = db_path or _db_path_from_settings(settings.database_url)
    checks: list[DoctorCheck] = []
    with httpx.Client(
        timeout=timeout_s, headers={"User-Agent": "forecast-lab kq-doctor"}
    ) as client:
        # Fetch each series ONCE and share across checks -- three separate
        # fetch loops earned a 429 on the first live run of this flow.
        series_payloads: dict[str, Any] = {}
        for i, station in enumerate(STATIONS):
            if i:
                time.sleep(0.5)  # politeness gap; public endpoint rate-limits
            series = station.kalshi_series_ticker
            try:
                series_payloads[series] = _fetch_json(
                    client, "/markets", {"series_ticker": series, "status": "open", "limit": 50}
                )
            except httpx.HTTPError as exc:
                series_payloads[series] = exc
        checks += check_payload_shape(series_payloads)
        checks += check_parser_coverage(series_payloads)
        checks += check_settlement_source(series_payloads)
        checks += check_orderbook_shape(client, series_payloads)
    checks += check_observed_truth(path)
    checks += check_phase5_clocks(path)
    return checks


def main(*, json_output: bool = False, db_path: Path | None = None) -> int:
    """``python -m kq doctor`` entrypoint. Exit: 0 OK / 1 WARN / 2 CRIT."""
    try:
        checks = run_doctor(db_path=db_path)
    except Exception:
        log.exception("doctor.fatal")
        return 2
    rank = {"crit": 2, "warn": 1, "ok": 0, "info": 0}
    worst = max((rank[c.severity] for c in checks), default=0)
    if json_output:
        print(json.dumps([asdict(c) for c in checks], indent=1, default=str))
    else:
        icon = {"ok": "[OK  ]", "warn": "[WARN]", "crit": "[CRIT]", "info": "[INFO]"}
        print("=== kq doctor — reality-contact diagnostics ===")
        for c in checks:
            print(f"{icon[c.severity]} {c.name}: {c.detail}")
        verdict = {0: "HEALTHY", 1: "DEGRADED (warn)", 2: "REALITY DRIFT (crit)"}[worst]
        print(f"\nverdict: {verdict}")
    return worst


__all__ = ["DoctorCheck", "main", "run_doctor"]
