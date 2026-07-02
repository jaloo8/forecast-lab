"""Open-Meteo ensemble + previous-runs forecast client.

Public surface:
    OpenMeteoClient, BASE_URL, PREVIOUS_RUNS_BASE_URL    (from .client)
    EnsembleForecast                                     (from ._types)
    MODEL_ID_MAP, PREV_DAY1_MODEL_NAME                   (from ._parsers)

See docs/TESTING.md for the testing matrix and docs/research/PASS-1-FEASIBILITY.md
for the product rationale. The old backdated-``as_of`` historical path
(``fetch_historical_deterministic`` / ``model='gfs_hist'``) was deleted in
PR-F — 2026-06-11 audit root cause #8.
"""

from __future__ import annotations

from kq.clients.openmeteo._parsers import (
    MODEL_ID_MAP,
    PREV_DAY1_LEAD_HOURS,
    PREV_DAY1_MEMBER,
    PREV_DAY1_MODEL_NAME,
    _gather_members,
    _parse_payload,
    parse_previous_runs_payload,
    previous_day1_as_of,
)
from kq.clients.openmeteo._types import EnsembleForecast
from kq.clients.openmeteo.client import (
    BASE_URL,
    PREV_DAY1_HOURLY_VAR,
    PREV_DAY1_MODEL_ID,
    PREVIOUS_RUNS_BASE_URL,
    OpenMeteoClient,
)

__all__ = [
    "BASE_URL",
    "MODEL_ID_MAP",
    "PREVIOUS_RUNS_BASE_URL",
    "PREV_DAY1_HOURLY_VAR",
    "PREV_DAY1_LEAD_HOURS",
    "PREV_DAY1_MEMBER",
    "PREV_DAY1_MODEL_ID",
    "PREV_DAY1_MODEL_NAME",
    "EnsembleForecast",
    "OpenMeteoClient",
    "_gather_members",  # exported for tests
    "_parse_payload",  # exported for tests
    "parse_previous_runs_payload",
    "previous_day1_as_of",
]
