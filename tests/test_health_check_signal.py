"""Signal quality of the health check: it must alarm on news, not on weather.

CONTEXT (audit 2026-08-08). The 8-hourly status report said ATTENTION in 39 of
39 editions — it had never once reported healthy. A verdict that is always on
carries no information, and the cost was measurable: a genuinely failing job
(the reforecast backtest) sat visible in every edition for a week and was only
noticed when the owner asked someone to look.

Two of the three drivers were miscalibration rather than fact:

* ``metar_obs`` warned past 30 minutes, a threshold copied from our INGEST
  cadence when the check actually reads OBSERVATION age — and stations publish
  routine METAR hourly. Measured over 14 days on the host, a healthy system
  spent 11.6% of wall-clock above that line, and the CRIT escalation (90min)
  sat BELOW the observed healthy maximum gap of 120min, so normal operation
  could page.
* ``calibration_summary`` re-reported the same five permanently-failing
  stations forever. That failure is the documented reason the weather lane is
  halted; restating it every 8 hours is not news.

These tests pin the corrected behaviour so a future "let's tighten the alarms"
change has to argue with the measurements rather than with a vibe.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kq.clients.stations import STATIONS_BY_ICAO
from kq.flows.health_check import (
    ACKNOWLEDGED_RELIABILITY_FAILURES,
    DEFAULT_MAX_AGE_METAR_MIN,
    DEFAULT_METAR_CRIT_MULTIPLIER,
    _calibration_check,
)


def _manifest(tmp_path: Path, failing: list[str], *, passing: list[str] | None = None) -> Path:
    stations: dict[str, dict] = {
        icao: {"reliability_summary": {"passes_bar": False}} for icao in failing
    }
    for icao in passing or []:
        stations[icao] = {"reliability_summary": {"passes_bar": True}}
    path = tmp_path / "backtest_manifest.json"
    path.write_text(json.dumps({"stations": stations}), encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# METAR threshold — set from the data's real publication cadence
# --------------------------------------------------------------------------


def test_metar_threshold_exceeds_hourly_publication_cadence() -> None:
    """The threshold must sit above METAR's hourly publication, not our ingest.

    Measured per-station publication gaps on the host: median 60min, p90 60min.
    Anything at or below 60 is guaranteed to fire on a healthy system.
    """
    assert DEFAULT_MAX_AGE_METAR_MIN > 60.0, (
        "METAR publishes hourly; a threshold at or under 60min warns on a "
        "perfectly healthy pipeline (the pre-2026-08-08 value was 30)"
    )


def test_metar_crit_clears_observed_healthy_maximum() -> None:
    """CRIT pages the operator, so it must clear the worst HEALTHY observation.

    Worst newest-obs gap measured over 14 healthy days: 120min. The old config
    escalated at 3 x 30 = 90min — below that — so normal operation could page.
    """
    crit_minutes = DEFAULT_MAX_AGE_METAR_MIN * DEFAULT_METAR_CRIT_MULTIPLIER
    assert crit_minutes > 120.0, (
        f"metar CRIT at {crit_minutes:.0f}min is inside the observed healthy "
        "range (max gap 120min) — a healthy system would page"
    )
    # ...but loosening WARN must not also slow the page to uselessness.
    assert crit_minutes <= 240.0, "metar CRIT is so loose a real outage goes unpaged for hours"


# --------------------------------------------------------------------------
# Calibration — alert on CHANGE, not on the acknowledged steady state
# --------------------------------------------------------------------------


def test_acknowledged_failures_do_not_warn(tmp_path: Path) -> None:
    """Exactly the known-failing set is OK — and still says so out loud."""
    path = _manifest(tmp_path, sorted(ACKNOWLEDGED_RELIABILITY_FAILURES))
    check = _calibration_check(path)

    assert check.severity == "ok", "the acknowledged steady state must not warn"
    # Acknowledged is not hidden: every failing station is still named.
    for icao in ACKNOWLEDGED_RELIABILITY_FAILURES:
        assert icao in check.detail, f"{icao} vanished from the detail — that's silencing, not ack"


def test_a_new_failing_station_warns(tmp_path: Path) -> None:
    """A station failing that we have NOT accepted is news, and must warn."""
    path = _manifest(tmp_path, [*sorted(ACKNOWLEDGED_RELIABILITY_FAILURES), "KAUS"])
    check = _calibration_check(path)

    assert check.severity == "warn"
    assert "KAUS" in check.detail
    assert "NEW" in check.detail, "a new failure must be distinguishable from the known ones"


def test_recovery_is_surfaced(tmp_path: Path) -> None:
    """A station that starts passing is good news — and must not be silent."""
    still_failing = sorted(ACKNOWLEDGED_RELIABILITY_FAILURES - {"KLAX"})
    path = _manifest(tmp_path, still_failing, passing=["KLAX"])
    check = _calibration_check(path)

    assert check.severity == "ok"
    assert "RECOVERED" in check.detail and "KLAX" in check.detail


def test_a_station_dropping_out_is_not_a_recovery(tmp_path: Path) -> None:
    """Absence is not recovery.

    A station missing from the manifest hasn't started passing — it stopped
    being scored. Reporting that as RECOVERED would be a cheerful lie.
    """
    path = _manifest(tmp_path, sorted(ACKNOWLEDGED_RELIABILITY_FAILURES - {"KLAX"}))
    check = _calibration_check(path)

    assert "RECOVERED" not in check.detail
    assert check.severity == "ok"


def test_all_clear_still_reports_ok(tmp_path: Path) -> None:
    """The happy path survives: nothing failing anywhere is OK."""
    path = _manifest(tmp_path, [], passing=sorted(ACKNOWLEDGED_RELIABILITY_FAILURES))
    check = _calibration_check(path)

    assert check.severity == "ok"
    assert "clear" in check.detail


def test_conformal_breach_still_warns(tmp_path: Path) -> None:
    """The acknowledgement covers RELIABILITY only — conformal drift is news."""
    path = tmp_path / "backtest_manifest.json"
    path.write_text(
        json.dumps(
            {
                "stations": {
                    "KLAX": {
                        "reliability_summary": {"passes_bar": False},
                        "conformal_summary": {"empirical_coverage": 0.60},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    check = _calibration_check(path)

    assert check.severity == "warn", "conformal under-coverage must still warn"
    assert "conformal" in check.detail


@pytest.mark.parametrize("icao", sorted(ACKNOWLEDGED_RELIABILITY_FAILURES))
def test_every_acknowledgement_is_a_real_station(icao: str) -> None:
    """Keep the acknowledgement list from rotting into a wildcard."""
    assert icao in STATIONS_BY_ICAO, (
        f"{icao} is acknowledged as a known reliability failure but is not a "
        "known station — stale entries turn an acknowledgement into a silencer"
    )
