"""Tests for ``kq doctor`` — the reality-contact diagnostics.

Testing philosophy (post-2026-06-11 audit): these tests cover the
EVALUATION LOGIC using recorded prod payloads, where the test author
cannot bias what the venue returned. The live-probe path is deliberately
NOT unit-tested — it runs against reality itself (weekly via
``scripts/reality-probe.sh``), and mocking it here would recreate the
exact self-confirmation failure the doctor exists to prevent.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import httpx
import pytest

from kq.clients.stations import STATIONS
from kq.flows import doctor
from kq.flows.doctor import (
    check_observed_truth,
    check_orderbook_shape,
    check_parser_coverage,
    check_payload_shape,
    check_phase5_clocks,
    check_settlement_source,
    check_venue_contact,
)
from kq.storage.duckdb_store import bootstrap

_FIXTURES = Path(__file__).parent / "fixtures"


def _recorded_lax_payload() -> dict[str, object]:
    return json.loads((_FIXTURES / "kalshi_prod_markets_weather.json").read_text(encoding="utf-8"))


# --------------------------- payload-shape ---------------------------


def test_payload_shape_ok_on_recorded_prod_payload() -> None:
    checks = check_payload_shape({"KXHIGHLAX": _recorded_lax_payload()})
    assert len(checks) == 1
    assert checks[0].severity == "ok"
    assert "12/12 priced" in checks[0].detail


def test_payload_shape_crit_when_wire_format_drifts() -> None:
    """Simulate the audit-finding-#1 failure class: markets present but no
    field the parser understands carries a price."""
    drifted = {
        "markets": [
            {"ticker": "KXHIGHLAX-X-T75", "status": "active", "yes_bid_v3": "0.42"},
        ]
    }
    checks = check_payload_shape({"KXHIGHLAX": drifted})
    assert checks[0].severity == "crit"
    assert "wire format drifted" in checks[0].detail


def test_payload_shape_warns_on_fetch_failure_and_empty_series() -> None:
    checks = check_payload_shape({"KXHIGHAUS": RuntimeError("boom"), "KXHIGHMIA": {"markets": []}})
    by_name = {c.name: c for c in checks}
    assert by_name["payload-shape.KXHIGHAUS"].severity == "warn"
    assert by_name["payload-shape.KXHIGHMIA"].severity == "warn"


# --------------------------- parser-coverage ---------------------------


def test_parser_coverage_full_book_tradeable_since_pr_b() -> None:
    """PR-B: the strike-aware matcher admits the ENTIRE recorded prod book
    (greater + less + between), not just the 2 T-greater tail markets the
    PR-A interim guard allowed."""
    checks = check_parser_coverage({"KXHIGHLAX": _recorded_lax_payload()})
    assert checks[0].severity == "ok"
    assert "12/12 tradeable" in checks[0].detail
    assert "'between': 8" in checks[0].detail


def test_parser_coverage_crit_when_nothing_tradeable() -> None:
    """A book whose strike fields are missing on unguessable tickers (a
    between-market without API semantics) is untradeable -> crit."""
    between_without_strike_fields = {
        "markets": [
            {
                "ticker": "KXHIGHLAX-26JUN11-B74.5",
                "status": "active",
                "yes_bid_dollars": "0.40",
                "yes_ask_dollars": "0.41",
            }
        ]
    }
    checks = check_parser_coverage({"KXHIGHLAX": between_without_strike_fields})
    assert checks[0].severity == "crit"
    assert "0/1 tradeable" in checks[0].detail


# --------------------------- settlement-source ---------------------------


def _ny_payload(rules: str) -> dict[str, object]:
    return {"markets": [{"ticker": "KXHIGHNY-26JUN11-T95", "rules_primary": rules}]}


def test_settlement_source_ok_for_ny_since_pr_c() -> None:
    """2026-06-11 audit root cause #4, closed by PR-C: the pipeline now
    models Central Park (KNYC), so the real KXHIGHNY contract text — which
    used to CRIT against our KJFK mapping — must pass."""
    rules = (
        "If the highest temperature recorded in Central Park, New York for "
        "June 11, 2026 ... is greater than 95°, then the market resolves to Yes."
    )
    checks = check_settlement_source({"KXHIGHNY": _ny_payload(rules)})
    assert checks[0].severity == "ok"
    assert "Central Park" in checks[0].detail


def test_settlement_source_crit_on_station_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    """The Central Park failure class, encoded permanently: contract names a
    station the pipeline does not model -> CRIT until actually fixed. All six
    live mappings match since PR-C, so simulate a regression to the pre-PR-C
    state (pipeline modeling JFK) to keep the branch pinned."""
    monkeypatch.setitem(doctor.PIPELINE_STATION_NAME, "KXHIGHNY", "JFK")
    rules = (
        "If the highest temperature recorded in Central Park, New York for "
        "June 11, 2026 ... is greater than 95°, then the market resolves to Yes."
    )
    checks = check_settlement_source({"KXHIGHNY": _ny_payload(rules)})
    assert checks[0].severity == "crit"
    assert "Central Park" in checks[0].detail
    assert "JFK" in checks[0].detail


def test_settlement_source_crit_when_kalshi_changes_the_source() -> None:
    rules = "If the highest temperature recorded at LaGuardia Airport ..."
    checks = check_settlement_source({"KXHIGHNY": _ny_payload(rules)})
    assert checks[0].severity == "crit"
    assert "no longer mentions" in checks[0].detail


def test_settlement_source_ok_when_aligned() -> None:
    payload = {
        "markets": [
            {
                "ticker": "KXHIGHDEN-26JUN11-T93",
                "rules_primary": "If the highest temperature recorded in Denver ...",
            }
        ]
    }
    checks = check_settlement_source({"KXHIGHDEN": payload})
    assert checks[0].severity == "ok"


def test_settlement_source_dicts_cover_every_station_series() -> None:
    """Every series the pipeline trades (STATIONS) must have BOTH doctor
    entries, and no orphan entries may linger for series we no longer model —
    otherwise the Central-Park guard silently skips a series."""
    series = {s.kalshi_series_ticker for s in STATIONS}
    assert set(doctor.EXPECTED_RULES_SUBSTRING) == series
    assert set(doctor.PIPELINE_STATION_NAME) == series


# rules_primary settlement phrases recorded live from prod on 2026-07-02
# (Phase B discovery), one per new series. These pin the doctor's phrase
# matching against the REAL contract wording, not the author's guess.
_PHASE_B_RULES: list[tuple[str, str]] = [
    (
        "KXHIGHTPHX",
        "If the maximum temperature recorded at Phoenix for Jul 3, 2026, is "
        "greater than 111 fahrenheit according to the National Weather Service's "
        "Climatological Report (Daily), then the market resolves to Yes.",
    ),
    (
        "KXHIGHTHOU",
        "If the maximum temperature recorded at Houston for Jul 3, 2026, is "
        "greater than 98 fahrenheit according to the National Weather Service's "
        "Climatological Report (Daily), then the market resolves to Yes.",
    ),
    (
        "KXHIGHTNOLA",
        "If the maximum temperature recorded at New Orleans for Jul 3, 2026, is "
        "greater than 98 fahrenheit according to the National Weather Service's "
        "Climatological Report (Daily), then the market resolves to Yes.",
    ),
    (
        "KXHIGHTBOS",
        "If the maximum temperature recorded at Boston for Jul 3, 2026, is less "
        "than 99 fahrenheit according to the National Weather Service's "
        "Climatological Report (Daily), then the market resolves to Yes.",
    ),
    (
        "KXHIGHTDAL",
        "If the maximum temperature recorded at Dallas for Jul 3, 2026, is less "
        "than 95 fahrenheit according to the National Weather Service's "
        "Climatological Report (Daily), then the market resolves to Yes.",
    ),
    (
        "KXHIGHTSATX",
        "If the maximum temperature recorded at San Antonio for Jul 3, 2026, is "
        "greater than 99 fahrenheit according to the National Weather Service's "
        "Climatological Report (Daily), then the market resolves to Yes.",
    ),
    (
        "KXHIGHTSEA",
        "If the maximum temperature recorded at Seattle for Jul 3, 2026, is "
        "greater than 78 fahrenheit according to the National Weather Service's "
        "Climatological Report (Daily), then the market resolves to Yes.",
    ),
    (
        "KXHIGHTOKC",
        "If the maximum temperature recorded at Oklahoma City for Jul 3, 2026, "
        "is less than 93 fahrenheit according to the National Weather Service's "
        "Climatological Report (Daily), then the market resolves to Yes.",
    ),
    (
        "KXHIGHTMIN",
        "If the maximum temperature recorded at Minneapolis for Jul 3, 2026, is "
        "greater than 90 fahrenheit according to the National Weather Service's "
        "Climatological Report (Daily), then the market resolves to Yes.",
    ),
    (
        "KXHIGHPHIL",
        "If the highest temperature recorded at Philadelphia International "
        "Airport for July 03, 2026 as reported by the National Weather Service's "
        "Climatological Report (Daily), is greater than 108, then the market "
        "resolves to Yes.",
    ),
    (
        "KXHIGHTLV",
        "If the maximum temperature recorded at Las Vegas for Jul 3, 2026, is "
        "less than 99 fahrenheit according to the National Weather Service's "
        "Climatological Report (Daily), then the market resolves to Yes.",
    ),
    (
        "KXHIGHTDC",
        "If the maximum temperature recorded at Washington DC for Jul 3, 2026, "
        "is greater than 108 fahrenheit according to the National Weather "
        "Service's Climatological Report (Daily), then the market resolves to Yes.",
    ),
    (
        "KXHIGHTATL",
        "If the maximum temperature recorded at Atlanta for Jul 3, 2026, is less "
        "than 94 fahrenheit according to the National Weather Service's "
        "Climatological Report (Daily), then the market resolves to Yes.",
    ),
    (
        "KXHIGHTSFO",
        "If the maximum temperature recorded at San Francisco for Jul 3, 2026, "
        "is greater than 73 fahrenheit according to the National Weather "
        "Service's Climatological Report (Daily), then the market resolves to Yes.",
    ),
]


@pytest.mark.parametrize(("series", "rules"), _PHASE_B_RULES)
def test_settlement_source_ok_for_phase_b_series(series: str, rules: str) -> None:
    payload = {"markets": [{"ticker": f"{series}-26JUL03-T99", "rules_primary": rules}]}
    checks = check_settlement_source({series: payload})
    assert checks[0].severity == "ok"
    assert doctor.EXPECTED_RULES_SUBSTRING[series] in checks[0].detail


def test_settlement_source_crit_if_houston_series_moves_to_intercontinental() -> None:
    """Hobby is the settlement station (CLIHOU). If Kalshi ever rewords the
    contract to Intercontinental, the expected substring 'Houston' still
    matches — so pin the reverse: a wording that drops 'Houston' entirely
    must CRIT rather than pass silently."""
    rules = "If the maximum temperature recorded at George Bush Intercontinental ..."
    payload = {"markets": [{"ticker": "KXHIGHTHOU-26JUL03-T98", "rules_primary": rules}]}
    checks = check_settlement_source({"KXHIGHTHOU": payload})
    assert checks[0].severity == "crit"
    assert "no longer mentions" in checks[0].detail


# --------------------------- observed-truth + clocks ---------------------------


def test_observed_truth_crit_when_empty_and_when_stale(tmp_path: Path) -> None:
    db = tmp_path / "t.duckdb"
    bootstrap(db)
    checks = check_observed_truth(db)
    assert checks[0].severity == "crit"
    assert "EMPTY" in checks[0].detail

    con = duckdb.connect(str(db))
    try:
        stale = (datetime.now(tz=UTC) - timedelta(days=30)).date()
        con.execute(
            "INSERT INTO weather_observed (station, valid_date, high_f, low_f, fetched_at) "
            "VALUES ('KLAX', ?, 75.0, 60.0, now())",
            [stale],
        )
    finally:
        con.close()
    checks = check_observed_truth(db)
    assert checks[0].severity == "crit"
    assert "stale" in checks[0].detail


def test_observed_truth_ok_when_fresh(tmp_path: Path) -> None:
    db = tmp_path / "t.duckdb"
    bootstrap(db)
    con = duckdb.connect(str(db))
    try:
        con.execute(
            "INSERT INTO weather_observed (station, valid_date, high_f, low_f, fetched_at) "
            "VALUES ('KLAX', ?, 75.0, 60.0, now())",
            [datetime.now(tz=UTC).date() - timedelta(days=1)],
        )
    finally:
        con.close()
    checks = check_observed_truth(db)
    assert checks[0].severity == "ok"


def test_phase5_clocks_reports_zero_state(tmp_path: Path) -> None:
    db = tmp_path / "t.duckdb"
    bootstrap(db)
    checks = check_phase5_clocks(db)
    assert checks[0].severity == "info"
    assert "settled_trades=0/500" in checks[0].detail


# --------------------------- venue-contact (audit silent-zero class) ---------------------------


def test_venue_contact_crit_when_every_series_fails() -> None:
    """TOTAL venue-contact loss (all fetches fail) must be CRIT — the weekly
    probe pages only on CRIT, so WARN-only left this class silent."""
    payloads: dict[str, object] = {s: RuntimeError("boom") for s in ("KXHIGHLAX", "KXHIGHNY")}
    checks = check_venue_contact(payloads)
    assert checks[0].severity == "crit"
    assert "TOTAL venue-contact loss" in checks[0].detail


def test_venue_contact_crit_when_every_series_empty() -> None:
    payloads: dict[str, object] = {
        "KXHIGHLAX": {"markets": []},
        "KXHIGHNY": {"markets": None},  # null-markets counts as empty too
        "KXHIGHDEN": RuntimeError("boom"),
    }
    checks = check_venue_contact(payloads)
    assert checks[0].severity == "crit"
    assert "0/3" in checks[0].detail


def test_venue_contact_ok_when_any_series_has_markets() -> None:
    payloads: dict[str, object] = {
        "KXHIGHLAX": _recorded_lax_payload(),
        "KXHIGHNY": {"markets": []},
        "KXHIGHDEN": RuntimeError("boom"),
    }
    checks = check_venue_contact(payloads)
    assert checks[0].severity == "ok"
    assert "1/3" in checks[0].detail


# ------------------- payload-shape: fraction thresholds + price range -------------------


def _priced_market(i: int, *, bid: str = "0.4000", ask: str = "0.4200") -> dict[str, object]:
    return {
        "ticker": f"KXHIGHLAX-26JUN11-T{70 + i}",
        "status": "active",
        "yes_bid_dollars": bid,
        "yes_ask_dollars": ask,
        "strike_type": "greater",
        "floor_strike": float(70 + i),
    }


def _unpriced_market(i: int) -> dict[str, object]:
    m = _priced_market(i)
    del m["yes_bid_dollars"], m["yes_ask_dollars"]
    return m


def test_payload_shape_crit_when_almost_nothing_priced() -> None:
    """1/12 priced used to report OK (only zero-priced was CRIT). Below 10%
    priced is the finding-#1 class."""
    markets = [_priced_market(0)] + [_unpriced_market(i) for i in range(1, 12)]
    checks = check_payload_shape({"KXHIGHLAX": {"markets": markets}})
    assert checks[0].severity == "crit"
    assert "1/12" in checks[0].detail


def test_payload_shape_warn_when_half_the_book_unpriced() -> None:
    markets = [_priced_market(i) for i in range(4)] + [_unpriced_market(i) for i in range(4, 12)]
    checks = check_payload_shape({"KXHIGHLAX": {"markets": markets}})
    assert checks[0].severity == "warn"
    assert "4/12" in checks[0].detail


def test_payload_shape_rejects_prices_outside_unit_interval() -> None:
    """A 'price' of 1.50 is wire junk, not a price — it must not count as
    priced, and the detail must call it out."""
    markets = [_priced_market(i, bid="1.5000", ask="1.6000") for i in range(12)]
    checks = check_payload_shape({"KXHIGHLAX": {"markets": markets}})
    assert checks[0].severity == "crit"
    assert "outside [0,1]" in checks[0].detail


def test_payload_shape_tolerates_null_markets() -> None:
    """`"markets": null` in one series payload must degrade to the empty-series
    WARN, not TypeError the whole doctor run."""
    checks = check_payload_shape({"KXHIGHLAX": {"markets": None}})
    assert checks[0].severity == "warn"
    assert "0 open markets" in checks[0].detail
    # parser-coverage + settlement-source share the tolerance
    assert check_parser_coverage({"KXHIGHLAX": {"markets": None}})[0].severity == "info"
    assert check_settlement_source({"KXHIGHNY": {"markets": None}})[0].severity == "info"


# ------------------- settlement-source: strict phrase matching -------------------


def test_settlement_source_incidental_mention_cannot_false_green(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The modeled station appearing ANYWHERE in the rules used to suppress
    the Central-Park-class CRIT. Matching is now scoped to the settlement
    phrase ('recorded in <station>'), so an incidental mention elsewhere
    can't false-green the NY sentinel."""
    monkeypatch.setitem(doctor.PIPELINE_STATION_NAME, "KXHIGHNY", "JFK")
    rules = (
        "If the highest temperature recorded in Central Park, New York for "
        "June 11, 2026 is greater than 95F, then the market resolves to Yes. "
        "Readings are generally consistent with those at JFK Airport."
    )
    checks = check_settlement_source({"KXHIGHNY": _ny_payload(rules)})
    assert checks[0].severity == "crit"
    assert "Central Park" in checks[0].detail
    assert "JFK" in checks[0].detail


def test_settlement_source_span_extracts_station_phrase() -> None:
    span = doctor._settlement_source_span(
        "If the highest temperature recorded in Los Angeles Airport, CA for "
        "June 12, 2026 as reported by the NWS, is greater than 81F, then ..."
    )
    assert span == "Los Angeles Airport, CA"
    # Unrecognized structure falls back to the whole text (never fail closed
    # on a Kalshi rephrase).
    assert doctor._settlement_source_span("totally new rules text") == "totally new rules text"


# ------------------- orderbook-shape: N probes, empty vs unparseable -------------------


def _orderbook_client(books: dict[str, object]) -> httpx.Client:
    """Hermetic client: serves canned orderbook JSON per ticker (recorded-
    payload style — we pin the classification logic, not the venue)."""

    def handler(request: httpx.Request) -> httpx.Response:
        ticker = request.url.path.split("/")[-2]
        body = books.get(ticker)
        if body is None:
            return httpx.Response(404, json={"error": "no such market"})
        return httpx.Response(200, json=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _series_with_tickers(*tickers: str) -> dict[str, object]:
    return {"KXHIGHLAX": {"markets": [{"ticker": t} for t in tickers]}}


_EMPTY_BOOK: dict[str, object] = {"orderbook": {"yes": None, "no": None}}
_PARSEABLE_BOOK: dict[str, object] = {"orderbook": {"yes": [[40, 100]], "no": [[55, 200]]}}
_DRIFTED_BOOK: dict[str, object] = {"orderbook_v9": {"yes_levels": [["0.40", "100"]]}}


def test_orderbook_probe_skips_legit_empty_book_and_finds_depth() -> None:
    """A legitimately empty first book must NOT CRIT as wire drift — the
    probe moves on and OKs on the next market with depth."""
    client = _orderbook_client({"T1": _EMPTY_BOOK, "T2": _PARSEABLE_BOOK})
    checks = check_orderbook_shape(client, _series_with_tickers("T1", "T2"))
    assert checks[0].severity == "ok"
    assert "T2" in checks[0].detail


def test_orderbook_all_probed_books_empty_is_warn_not_crit() -> None:
    client = _orderbook_client(dict.fromkeys(("T1", "T2", "T3", "T4"), _EMPTY_BOOK))
    checks = check_orderbook_shape(client, _series_with_tickers("T1", "T2", "T3", "T4"))
    assert checks[0].severity == "warn"
    assert "legitimately empty" in checks[0].detail
    limit = doctor.ORDERBOOK_PROBE_LIMIT
    assert f"{limit}/{limit}" in checks[0].detail


def test_orderbook_crit_when_raw_payload_has_levels_parser_sees_none() -> None:
    """Wire drift proper: the raw payload carries ladder levels under keys
    the parser doesn't know — that's the audit finding class, CRIT."""
    client = _orderbook_client({"T1": _DRIFTED_BOOK})
    checks = check_orderbook_shape(client, _series_with_tickers("T1"))
    assert checks[0].severity == "crit"
    assert "wire format drifted" in checks[0].detail


def test_orderbook_warns_when_every_fetch_fails() -> None:
    client = _orderbook_client({})  # every ticker 404s
    checks = check_orderbook_shape(client, _series_with_tickers("T1", "T2"))
    assert checks[0].severity == "warn"
    assert "fetches failed" in checks[0].detail


# ------------------- DB access: never create, busy != drift -------------------


def test_observed_truth_crit_on_missing_db_and_never_creates_it(tmp_path: Path) -> None:
    """The pre-audit doctor opened read-WRITE and silently materialized an
    empty DB on a bad path — worst possible diagnostics behavior. Missing DB
    is CRIT 'no database', and the path must stay untouched."""
    missing = tmp_path / "never" / "created.duckdb"
    checks = check_observed_truth(missing)
    assert checks[0].severity == "crit"
    assert "no database" in checks[0].detail
    assert not missing.exists()
    assert not missing.parent.exists()

    clocks = check_phase5_clocks(missing)
    assert clocks[0].severity == "warn"
    assert not missing.exists()


def test_doctor_db_checks_warn_busy_on_lock_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A writer holding the DuckDB lock is 'busy, retry next tick' (WARN) —
    never a REALITY-DRIFT page."""
    db = tmp_path / "t.duckdb"
    bootstrap(db)

    def _locked(*_a: object, **_k: object) -> object:
        raise duckdb.IOException(
            'IO Error: Could not set lock on file "t.duckdb": Conflicting lock is held'
        )

    monkeypatch.setattr(doctor, "connect", _locked)
    truth = check_observed_truth(db)
    assert truth[0].severity == "warn"
    assert "busy" in truth[0].detail
    clocks = check_phase5_clocks(db)
    assert clocks[0].severity == "warn"
    assert "busy" in clocks[0].detail
