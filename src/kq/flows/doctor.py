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

1. **venue-contact** — TOTAL loss of venue contact (every series fetch
   failed or returned zero markets) is CRIT: it is exactly the audit's
   silent-zero class, and per-series WARNs alone never page.
2. **payload-shape** — fetch live markets per weather series; the parser
   must yield non-None prices in [0, 1] (the exact failure class of audit
   finding #1: prod moved to ``*_dollars`` fields and every price parsed as
   None, silently, for weeks). A mostly-unpriced book escalates by fraction:
   < 50% priced is WARN, < 10% is CRIT.
3. **parser-coverage** — how many live markets are eligible for trading
   under the current matcher (strike-type guard); reports visible/total and
   the strike-type mix so "the book shrank" is loud, not silent.
4. **settlement-source** — extract the station named in ``rules_primary``
   and compare against our ICAO mapping (the audit's Central Park finding:
   KXHIGHNY settles on KNYC; the pipeline modeled KJFK until PR-C rerouted
   it). Any future mismatch is CRIT — visible beats silent. Matching is
   scoped to the settlement phrase ("recorded in/at <station>"), so an
   incidental mention of the modeled station elsewhere in the rules can't
   false-green the check.
5. **orderbook-shape** — fetch up to ``ORDERBOOK_PROBE_LIMIT`` live
   orderbooks; the parser must produce a usable book (audit finding: prod
   moved to ``orderbook_fp`` and every snapshot parsed empty). A
   legitimately empty book (raw payload carries no ladder levels) is WARN,
   not CRIT — only "raw has levels, parser sees none" is wire drift.
6. **observed-truth freshness** — ``weather_observed`` recency in the live
   DB; stale truth means settlement silently never fires (audit finding #7).
7. **phase5-clocks** — settled-trade count, last settlement, last priced
   book snap: the "is the evidence clock actually ticking?" panel.

The DB is opened READ-ONLY and never created: a diagnostics flow must
observe the database, not materialize an empty one on a bad path. A missing
database is CRIT ("no database"); a transient writer-lock conflict is WARN
("busy, retry next tick"), never REALITY DRIFT.

Exit codes match health-check: 0 = all OK, 1 = WARN, 2 = CRIT.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from itertools import zip_longest
from pathlib import Path
from typing import Any, Literal

import duckdb
import httpx
import structlog

from kq.backtest.bracket_match import parsed_weather_markets
from kq.clients.kalshi._parsers import _parse_market, _parse_orderbook
from kq.clients.kalshi._ticker_parser_index import parse_index_market_ticker
from kq.clients.kalshi._ticker_parser_nfl import parse_nfl_market_ticker
from kq.clients.kalshi._types import Market
from kq.clients.stations import STATIONS
from kq.config import get_settings
from kq.flows.ingest_weather import _db_path_from_settings
from kq.storage.duckdb_store import connect, is_lock_conflict

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
    # Phase B expansion (2026-07-02). The rules_primary settlement phrase for
    # these series names only the CITY ("recorded at Phoenix for ..."); the
    # exact station is pinned by rules_secondary's CLI product and encoded in
    # stations.py / _ticker_parser.py. This check catches Kalshi rewording
    # the settlement phrase out from under us.
    "KXHIGHTPHX": "Phoenix",
    "KXHIGHTHOU": "Houston",  # CLIHOU — Hobby, not Intercontinental
    "KXHIGHTNOLA": "New Orleans",
    "KXHIGHTBOS": "Boston",
    "KXHIGHTDAL": "Dallas",  # CLIDFW — DFW Intl, not Love Field
    "KXHIGHTSATX": "San Antonio",
    "KXHIGHTSEA": "Seattle",
    "KXHIGHTOKC": "Oklahoma City",
    "KXHIGHTMIN": "Minneapolis",
    "KXHIGHPHIL": "Philadelphia",  # rules name Philadelphia International Airport
    "KXHIGHTLV": "Las Vegas",
    "KXHIGHTDC": "Washington DC",  # CLIDCA — Reagan National, not Dulles/BWI
    "KXHIGHTATL": "Atlanta",
    "KXHIGHTSFO": "San Francisco",
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
    # Phase B expansion (2026-07-02): each ICAO below is the CLI product's
    # station, verified 2026-07-02 (see stations.py module docstring).
    "KXHIGHTPHX": "Phoenix",  # KPHX — matches (CLIPHX)
    "KXHIGHTHOU": "Houston",  # KHOU Hobby — matches (CLIHOU, NOT KIAH)
    "KXHIGHTNOLA": "New Orleans",  # KMSY — matches (CLIMSY)
    "KXHIGHTBOS": "Boston",  # KBOS Logan — matches (CLIBOS)
    "KXHIGHTDAL": "Dallas",  # KDFW — matches (CLIDFW, NOT Love Field)
    "KXHIGHTSATX": "San Antonio",  # KSAT — matches (CLISAT)
    "KXHIGHTSEA": "Seattle",  # KSEA — matches (CLISEA)
    "KXHIGHTOKC": "Oklahoma City",  # KOKC Will Rogers — matches (CLIOKC)
    "KXHIGHTMIN": "Minneapolis",  # KMSP — matches (CLIMSP)
    "KXHIGHPHIL": "Philadelphia",  # KPHL — matches (CLIPHL)
    "KXHIGHTLV": "Las Vegas",  # KLAS Harry Reid — matches (CLILAS)
    "KXHIGHTDC": "Washington DC",  # KDCA Reagan National — matches (CLIDCA)
    "KXHIGHTATL": "Atlanta",  # KATL — matches (CLIATL)
    "KXHIGHTSFO": "San Francisco",  # KSFO — matches (CLISFO)
}


@dataclass(frozen=True, slots=True)
class DoctorCheck:
    name: str
    severity: Severity
    detail: str


# Payload-shape escalation by priced fraction (2026-07-01 audit: 1/12 priced
# reported OK because only zero-priced was CRIT).
PRICED_WARN_FRACTION = 0.5  # below this, WARN — half the book is unpriceable
PRICED_CRIT_FRACTION = 0.1  # below this, CRIT — effectively the finding-#1 class

# How many live orderbooks to probe before concluding on wire shape. One
# arbitrary (possibly legitimately empty) book CRIT'd as drift pre-audit.
ORDERBOOK_PROBE_LIMIT = 3

# NFL game-winner series (Phase B, 2026-07-02). Probed season-aware: an
# empty book is INFO (Feb-Jun off-season is real), never CRIT — but live
# markets whose tickers the parser can't read are CRIT (that's the
# "verify the format on first live markets" tripwire; the format + all 32
# team codes were verified live 2026-07-02, fixture recorded).
NFL_SERIES_TICKER = "KXNFLGAME"

# Index-brackets daily range series (Phase C, 2026-07-02). Probed
# market-hours-aware: the daily events list overnight (~02:30Z) and close at
# the bell (20:00Z or earlier on early-close sessions), so an empty book
# off-hours / weekends / market holidays is INFO, never CRIT. Live markets
# whose tickers don't parse, or whose rules_primary no longer names the
# end-of-day index value, are CRIT (format/settlement drift tripwires;
# format verified live 2026-07-02, fixture recorded).
INDEX_SERIES_TICKERS: tuple[str, ...] = ("KXINX", "KXNASDAQ100")
INDEX_EXPECTED_RULES_SUBSTRING: dict[str, str] = {
    "KXINX": "end-of-day S&P 500 index value",
    "KXNASDAQ100": "end-of-day Nasdaq 100 index value",
}


def _fetch_json(client: httpx.Client, path: str, params: dict[str, Any] | None = None) -> Any:
    resp = client.get(f"{PROD_BASE}{path}", params=params)
    resp.raise_for_status()
    return resp.json()


def _raw_markets(payload: dict[str, Any]) -> list[Any]:
    """Tolerate ``"markets": null`` / non-list junk in one series payload —
    a single degraded payload must not TypeError the whole doctor run."""
    markets = payload.get("markets")
    return markets if isinstance(markets, list) else []


def _is_priced(m: Market) -> bool:
    """Both sides parsed AND within [0, 1] — an out-of-range 'price' is wire
    junk, not a price."""
    return (
        m.yes_bid is not None
        and m.yes_ask is not None
        and 0.0 <= m.yes_bid <= 1.0
        and 0.0 <= m.yes_ask <= 1.0
    )


def check_venue_contact(series_payloads: dict[str, Any]) -> list[DoctorCheck]:
    """The audit's silent-zero guard: TOTAL venue-contact loss must page.

    A single failed/empty series is WARN in payload-shape (one series can
    legitimately lull), but when EVERY series either failed to fetch or
    returned zero markets, the system is flying fully blind — the weekly
    probe pages only on CRIT, so this exact class was silent pre-audit.
    """
    if not series_payloads:
        return [DoctorCheck("venue-contact", "crit", "no series probed — STATIONS empty?")]
    n_failed = sum(1 for p in series_payloads.values() if isinstance(p, Exception))
    n_empty = sum(
        1 for p in series_payloads.values() if not isinstance(p, Exception) and not _raw_markets(p)
    )
    n_live = len(series_payloads) - n_failed - n_empty
    if n_live == 0:
        return [
            DoctorCheck(
                "venue-contact",
                "crit",
                f"0/{len(series_payloads)} series returned any market "
                f"({n_failed} fetch failures, {n_empty} empty) — TOTAL venue-contact "
                "loss: network egress, rate-limit wall, or Kalshi renamed every "
                "weather series (the audit's silent-zero class)",
            )
        ]
    return [
        DoctorCheck(
            "venue-contact",
            "ok",
            f"{n_live}/{len(series_payloads)} series returned markets",
        )
    ]


def check_payload_shape(series_payloads: dict[str, Any]) -> list[DoctorCheck]:
    """Audit finding #1 guard: live markets must parse with usable prices."""
    out: list[DoctorCheck] = []
    for series, payload in series_payloads.items():
        if isinstance(payload, Exception):
            out.append(DoctorCheck(f"payload-shape.{series}", "warn", f"fetch failed: {payload}"))
            continue
        raw_markets = _raw_markets(payload)
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
        priced = [m for m in parsed if _is_priced(m)]
        out_of_range = sum(
            1
            for m in parsed
            if m.yes_bid is not None and m.yes_ask is not None and not _is_priced(m)
        )
        range_note = f"; {out_of_range} with prices outside [0,1]" if out_of_range else ""
        striked = [m for m in parsed if m.strike_type in {"greater", "less", "between"}]
        priced_fraction = len(priced) / len(parsed)
        if not priced:
            out.append(
                DoctorCheck(
                    f"payload-shape.{series}",
                    "crit",
                    f"{len(parsed)} markets, 0 with parseable prices{range_note} — wire "
                    "format drifted again (this is exactly audit finding #1; update "
                    "_parsers.py + fixtures)",
                )
            )
        elif priced_fraction < PRICED_CRIT_FRACTION:
            out.append(
                DoctorCheck(
                    f"payload-shape.{series}",
                    "crit",
                    f"only {len(priced)}/{len(parsed)} markets priced "
                    f"(< {PRICED_CRIT_FRACTION:.0%}){range_note} — wire format drifted for "
                    "essentially the whole book (audit finding #1 class)",
                )
            )
        elif priced_fraction < PRICED_WARN_FRACTION:
            out.append(
                DoctorCheck(
                    f"payload-shape.{series}",
                    "warn",
                    f"only {len(priced)}/{len(parsed)} markets priced "
                    f"(< {PRICED_WARN_FRACTION:.0%}){range_note} — partial payload drift "
                    "or a half-dead book; watch this",
                )
            )
        elif len(striked) < len(parsed):
            # WARN by design: PR-H fails closed on prod (unstriked markets are
            # skipped, never guessed), so missing strike fields shrink the
            # tradeable book instead of inverting sides — parser-coverage
            # keeps the shrinkage loud.
            out.append(
                DoctorCheck(
                    f"payload-shape.{series}",
                    "warn",
                    f"{len(parsed) - len(striked)}/{len(parsed)} markets missing strike_type "
                    "(PR-H fails closed: these are skipped, never guessed)",
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
        parsed = [_parse_market(m) for m in _raw_markets(payload)]
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


# The settlement phrase in Kalshi weather rules_primary reads "... the
# highest temperature recorded in <STATION> for <DATE> ...". Matching the
# station INSIDE this phrase (not anywhere in the rules text) is what stops
# an incidental mention of the modeled station elsewhere in the rules from
# suppressing the Central-Park-class CRIT (2026-07-01 audit: false-green).
_SOURCE_PHRASE_RE = re.compile(
    r"recorded\s+(?:in|at|near)\s+(.{1,120}?)"
    r"(?:\s+for\s+|\s+on\s+|\s+during\s+|\s+is\s+|\s+between\s+|[.;]|$)",
    re.IGNORECASE | re.DOTALL,
)


def _settlement_source_span(rules: str) -> str:
    """The station phrase from the settlement sentence ("recorded in/at X"),
    or the full rules text when the structure isn't recognized (fall back to
    the pre-audit whole-text match rather than fail closed on a rephrase)."""
    m = _SOURCE_PHRASE_RE.search(rules)
    return m.group(1) if m else rules


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
        markets = _raw_markets(payload)
        if not markets:
            out.append(
                DoctorCheck(f"settlement-source.{series}", "info", "no open market to probe")
            )
            continue
        rules = str(markets[0].get("rules_primary", ""))
        source_span = _settlement_source_span(rules)
        if expected not in source_span:
            out.append(
                DoctorCheck(
                    f"settlement-source.{series}",
                    "crit",
                    f"settlement phrase no longer mentions {expected!r} — Kalshi changed the "
                    f"settlement source; re-audit. rules: {rules[:140]!r}",
                )
            )
        elif expected != modeled and modeled not in source_span:
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


def check_nfl_series(payload: Any) -> list[DoctorCheck]:
    """KXNFLGAME venue + payload + ticker-parser checks, season-aware.

    Three findings ride on one fetch:

    * ``nfl-venue-contact`` — 0 open markets is INFO in the off-season
      (the series legitimately empties between the Super Bowl and the
      preseason listings), a fetch failure is WARN. Markets present = OK.
    * ``nfl-payload-shape`` — the same priced-fraction escalation the
      weather series use (audit finding #1 class: wire drift makes every
      price parse None, silently).
    * ``nfl-parser-coverage`` — every live ticker must parse through
      ``parse_nfl_market_ticker``. The format was verified against prod
      2026-07-02 (incl. Kalshi's ``JAC`` — not ``JAX`` — Jacksonville
      code); any future unparsable ticker means Kalshi changed the format
      or a team code, and the paper flow is silently blind to that game.
    """
    if isinstance(payload, Exception):
        return [DoctorCheck("nfl-venue-contact", "warn", f"fetch failed: {payload}")]
    raw_markets = _raw_markets(payload)
    if not raw_markets:
        return [
            DoctorCheck(
                "nfl-venue-contact",
                "info",
                "0 open KXNFLGAME markets — normal in the NFL off-season (Feb-Jun); "
                "expect preseason + Week-1 listings from late June",
            )
        ]
    out: list[DoctorCheck] = [
        DoctorCheck("nfl-venue-contact", "ok", f"{len(raw_markets)} open KXNFLGAME markets")
    ]

    parsed = [_parse_market(m) for m in raw_markets]
    priced = [m for m in parsed if _is_priced(m)]
    priced_fraction = len(priced) / len(parsed)
    if not priced:
        out.append(
            DoctorCheck(
                "nfl-payload-shape",
                "crit",
                f"{len(parsed)} markets, 0 with parseable prices — wire format "
                "drifted (audit finding #1 class; update _parsers.py + fixtures)",
            )
        )
    elif priced_fraction < PRICED_CRIT_FRACTION:
        out.append(
            DoctorCheck(
                "nfl-payload-shape",
                "crit",
                f"only {len(priced)}/{len(parsed)} markets priced "
                f"(< {PRICED_CRIT_FRACTION:.0%}) — wire drift for essentially the whole book",
            )
        )
    elif priced_fraction < PRICED_WARN_FRACTION:
        out.append(
            DoctorCheck(
                "nfl-payload-shape",
                "warn",
                f"only {len(priced)}/{len(parsed)} markets priced "
                f"(< {PRICED_WARN_FRACTION:.0%}) — partial drift or a half-dead book",
            )
        )
    else:
        out.append(
            DoctorCheck("nfl-payload-shape", "ok", f"{len(priced)}/{len(parsed)} markets priced")
        )

    tickers = [str(m.get("ticker", "")) for m in raw_markets if isinstance(m, dict)]
    unparsable = [t for t in tickers if parse_nfl_market_ticker(t) is None]
    if unparsable and len(unparsable) == len(tickers):
        out.append(
            DoctorCheck(
                "nfl-parser-coverage",
                "crit",
                f"0/{len(tickers)} live tickers parse — Kalshi changed the KXNFLGAME "
                f"format; first: {unparsable[0]!r} (update _ticker_parser_nfl.py + fixture)",
            )
        )
    elif unparsable:
        out.append(
            DoctorCheck(
                "nfl-parser-coverage",
                "crit",
                f"{len(unparsable)}/{len(tickers)} live tickers DON'T parse — the paper "
                f"flow is blind to those games; first: {unparsable[0]!r} "
                "(new team code or format drift)",
            )
        )
    else:
        out.append(
            DoctorCheck(
                "nfl-parser-coverage", "ok", f"{len(tickers)}/{len(tickers)} live tickers parse"
            )
        )
    return out


def check_index_series(series: str, payload: Any) -> list[DoctorCheck]:
    """KXINX / KXNASDAQ100 venue + parser + settlement checks (Phase C).

    Market-hours-aware: these daily range events list overnight and close at
    the bell, so an empty book is INFO (off-hours, weekend, market holiday),
    never CRIT. Live tickers that don't parse through
    ``parse_index_market_ticker`` are CRIT (format drift — the backtest and
    any future paper flow would be silently blind). ``rules_primary`` must
    still name the end-of-day index value: index contracts settling on
    anything else (intraday print, different index) is the Central-Park
    failure class for this lane.
    """
    if isinstance(payload, Exception):
        return [DoctorCheck(f"index-venue-contact.{series}", "warn", f"fetch failed: {payload}")]
    raw_markets = _raw_markets(payload)
    if not raw_markets:
        return [
            DoctorCheck(
                f"index-venue-contact.{series}",
                "info",
                f"0 open {series} markets — normal off-hours (events list ~02:30Z, "
                "close at the bell), weekends, and market holidays",
            )
        ]
    out: list[DoctorCheck] = [
        DoctorCheck(
            f"index-venue-contact.{series}", "ok", f"{len(raw_markets)} open {series} markets"
        )
    ]

    parsed = [_parse_market(m) for m in raw_markets]
    priced = [m for m in parsed if _is_priced(m)]
    priced_fraction = len(priced) / len(parsed)
    if priced_fraction < PRICED_CRIT_FRACTION:
        out.append(
            DoctorCheck(
                f"index-payload-shape.{series}",
                "crit",
                f"only {len(priced)}/{len(parsed)} markets priced "
                f"(< {PRICED_CRIT_FRACTION:.0%}) — wire drift for essentially the whole "
                "book (audit finding #1 class; update _parsers.py + fixtures)",
            )
        )
    elif priced_fraction < PRICED_WARN_FRACTION:
        out.append(
            DoctorCheck(
                f"index-payload-shape.{series}",
                "warn",
                f"only {len(priced)}/{len(parsed)} markets priced "
                f"(< {PRICED_WARN_FRACTION:.0%}) — partial drift or a half-dead book",
            )
        )
    else:
        out.append(
            DoctorCheck(
                f"index-payload-shape.{series}",
                "ok",
                f"{len(priced)}/{len(parsed)} markets priced",
            )
        )

    tickers = [str(m.get("ticker", "")) for m in raw_markets if isinstance(m, dict)]
    unparsable = [t for t in tickers if parse_index_market_ticker(t) is None]
    no_strike_fields = sum(1 for m in parsed if m.strike_type is None)
    if unparsable:
        out.append(
            DoctorCheck(
                f"index-parser-coverage.{series}",
                "crit",
                f"{len(unparsable)}/{len(tickers)} live tickers DON'T parse — Kalshi "
                f"changed the {series} format; first: {unparsable[0]!r} "
                "(update _ticker_parser_index.py + fixture)",
            )
        )
    elif no_strike_fields:
        out.append(
            DoctorCheck(
                f"index-parser-coverage.{series}",
                "crit",
                f"{no_strike_fields}/{len(parsed)} live markets carry NO API strike "
                "fields — resolution semantics unknowable (ticker text never "
                "disambiguates; PR-B lesson)",
            )
        )
    else:
        out.append(
            DoctorCheck(
                f"index-parser-coverage.{series}",
                "ok",
                f"{len(tickers)}/{len(tickers)} live tickers parse; strike fields present",
            )
        )

    expected = INDEX_EXPECTED_RULES_SUBSTRING.get(series)
    rules = str(raw_markets[0].get("rules_primary", "")) if isinstance(raw_markets[0], dict) else ""
    if expected is None:  # pragma: no cover — series list and map move together
        pass
    elif expected not in rules:
        out.append(
            DoctorCheck(
                f"index-settlement-source.{series}",
                "crit",
                f"rules no longer say {expected!r} — Kalshi changed the settlement "
                f"definition; re-audit before trusting the HAR-RV benchmark. "
                f"rules: {rules[:140]!r}",
            )
        )
    else:
        out.append(
            DoctorCheck(f"index-settlement-source.{series}", "ok", f"settles on {expected!r}")
        )
    return out


def _payload_carries_levels(node: object) -> bool:
    """True when the raw orderbook JSON contains ANY non-empty list anywhere —
    a book that carries ladder levels the parser failed to see is wire drift;
    a book with no levels at all is just legitimately empty."""
    if isinstance(node, list):
        return len(node) > 0
    if isinstance(node, dict):
        return any(_payload_carries_levels(v) for v in node.values())
    return False


def _orderbook_probe_tickers(series_payloads: dict[str, Any]) -> list[str]:
    """Up to ``ORDERBOOK_PROBE_LIMIT`` tickers, round-robin across series so a
    single thin series can't monopolize the probe budget."""
    per_series = [
        _raw_markets(payload)
        for payload in series_payloads.values()
        if not isinstance(payload, Exception)
    ]
    tickers: list[str] = []
    for tier in zip_longest(*per_series):
        for market in tier:
            if isinstance(market, dict) and market.get("ticker"):
                tickers.append(str(market["ticker"]))
            if len(tickers) >= ORDERBOOK_PROBE_LIMIT:
                return tickers
    return tickers


def check_orderbook_shape(
    client: httpx.Client, series_payloads: dict[str, Any]
) -> list[DoctorCheck]:
    """Audit orderbook_fp guard: a live book must parse to a usable snapshot.

    Probes up to ``ORDERBOOK_PROBE_LIMIT`` markets (2026-07-01 audit: probing
    ONE arbitrary market CRIT'd a legitimately empty book as wire drift):

    * any book parses with depth              -> OK (stop probing)
    * raw payload has levels, parser sees none -> CRIT (wire format drifted)
    * raw payload has no levels                -> legitimately empty; keep
      probing, and WARN (not CRIT) if every probed book is empty.
    """
    tickers = _orderbook_probe_tickers(series_payloads)
    if not tickers:
        return [DoctorCheck("orderbook-shape", "info", "no open market found to probe")]
    empty_books: list[str] = []
    fetch_errors: list[str] = []
    for i, ticker in enumerate(tickers):
        if i:
            time.sleep(0.5)  # politeness gap; public endpoint rate-limits
        try:
            book = _fetch_json(client, f"/markets/{ticker}/orderbook")
        except httpx.HTTPError as exc:
            fetch_errors.append(f"{ticker}: {exc}")
            continue
        snap = _parse_orderbook(book, ticker=ticker, snap_time=datetime.now(tz=UTC))
        if snap.yes_bids or snap.yes_asks:
            return [
                DoctorCheck(
                    "orderbook-shape",
                    "ok",
                    f"{ticker}: bid={snap.yes_bid} ask={snap.yes_ask} "
                    f"depth={len(snap.yes_bids)}/{len(snap.yes_asks)} "
                    f"({len(empty_books)} empty book(s) probed first)",
                )
            ]
        if _payload_carries_levels(book):
            return [
                DoctorCheck(
                    "orderbook-shape",
                    "crit",
                    f"{ticker}: book parsed EMPTY while raw payload keys={list(book.keys())} "
                    "carry ladder levels — orderbook wire format drifted "
                    "(audit finding class #1)",
                )
            ]
        empty_books.append(ticker)
    if empty_books:
        return [
            DoctorCheck(
                "orderbook-shape",
                "warn",
                f"{len(empty_books)}/{len(tickers)} probed books legitimately empty "
                f"(no ladder levels in the raw payload) — thin/quiet market, not wire "
                f"drift: {empty_books}",
            )
        ]
    return [
        DoctorCheck(
            "orderbook-shape",
            "warn",
            f"all {len(fetch_errors)} orderbook fetches failed; first: {fetch_errors[0]}",
        )
    ]


def _open_db_read_only(
    db_path: Path, check_name: str
) -> duckdb.DuckDBPyConnection | list[DoctorCheck]:
    """Read-only connection or the DoctorCheck(s) explaining why not.

    Never creates a database (the pre-audit doctor opened read-WRITE and
    silently materialized an empty DB on a bad path — the worst possible
    behavior for a diagnostics flow). Severity is deliberately graded:
    missing DB = CRIT (no truth at all), writer-lock conflict = WARN (busy,
    retry next tick — not reality drift), anything else = CRIT (unreadable
    truth is worse than empty truth, not better).
    """
    if not db_path.exists():
        return [
            DoctorCheck(
                check_name,
                "crit",
                f"no database at {db_path} — nothing has ever been ingested on this "
                "machine (run `kq setup`); refusing to create an empty one",
            )
        ]
    try:
        return connect(db_path, read_only=True)
    except Exception as exc:
        if is_lock_conflict(exc):
            return [
                DoctorCheck(
                    check_name,
                    "warn",
                    "database busy (another process holds the write lock) — retry next tick",
                )
            ]
        return [DoctorCheck(check_name, "crit", f"database unreadable: {exc}")]


def check_observed_truth(db_path: Path) -> list[DoctorCheck]:
    """Audit finding #7 guard: settlement is impossible without fresh truth."""
    con_or_checks = _open_db_read_only(db_path, "observed-truth")
    if isinstance(con_or_checks, list):
        return con_or_checks
    con = con_or_checks
    try:
        row = con.execute("SELECT MAX(valid_date) FROM weather_observed").fetchone()
    except Exception as exc:  # table missing — truth is inaccessible, worse than empty
        return [
            DoctorCheck(
                "observed-truth",
                "crit",
                f"weather_observed unreadable: {exc} — settlement truth is "
                "inaccessible (fresh clone? run `kq setup`)",
            )
        ]
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
    if not db_path.exists():
        # observed-truth already carries the CRIT for a missing DB; this
        # informational panel just says why it has nothing to report.
        return [DoctorCheck("phase5-clocks", "warn", f"no database at {db_path}")]
    try:
        con = connect(db_path, read_only=True)
    except Exception as exc:
        if is_lock_conflict(exc):
            return [
                DoctorCheck(
                    "phase5-clocks",
                    "warn",
                    "database busy (another process holds the write lock) — retry next tick",
                )
            ]
        return [DoctorCheck("phase5-clocks", "warn", f"database unreadable: {exc}")]
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
        checks += check_venue_contact(series_payloads)
        checks += check_payload_shape(series_payloads)
        checks += check_parser_coverage(series_payloads)
        checks += check_settlement_source(series_payloads)
        checks += check_orderbook_shape(client, series_payloads)
        # Sports series ride the same client, after a politeness gap. NFL is
        # deliberately OUTSIDE check_venue_contact's total-loss calculation:
        # that check pages on WEATHER venue loss; an off-season empty NFL
        # book must never mask (or trigger) it.
        time.sleep(0.5)
        try:
            nfl_payload: Any = _fetch_json(
                client,
                "/markets",
                {"series_ticker": NFL_SERIES_TICKER, "status": "open", "limit": 100},
            )
        except httpx.HTTPError as exc:
            nfl_payload = exc
        checks += check_nfl_series(nfl_payload)
        # Index-brackets series (Phase C) — same politeness cadence; also
        # outside check_venue_contact's total-loss calculation (an off-hours
        # empty index book must never mask or trigger the weather pager).
        for series in INDEX_SERIES_TICKERS:
            time.sleep(0.5)
            try:
                index_payload: Any = _fetch_json(
                    client,
                    "/markets",
                    {"series_ticker": series, "status": "open", "limit": 50},
                )
            except httpx.HTTPError as exc:
                index_payload = exc
            checks += check_index_series(series, index_payload)
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


__all__ = ["DoctorCheck", "check_nfl_series", "check_venue_contact", "main", "run_doctor"]
