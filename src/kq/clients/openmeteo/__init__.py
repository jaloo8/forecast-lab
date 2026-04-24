"""Open-Meteo ensemble forecast client.

Public surface:
    OpenMeteoClient, BASE_URL                   (from .client)
    EnsembleForecast                            (from ._types)
    MODEL_ID_MAP                                (from ._parsers)

See docs/TESTING.md for the testing matrix and docs/research/PASS-1-FEASIBILITY.md
for the product rationale.
"""

from __future__ import annotations

from kq.clients.openmeteo._parsers import (
    MODEL_ID_MAP,
    _coerce_run_time,
    _gather_members,
    _parse_payload,
)
from kq.clients.openmeteo._types import EnsembleForecast
from kq.clients.openmeteo.client import BASE_URL, OpenMeteoClient

__all__ = [
    "BASE_URL",
    "MODEL_ID_MAP",
    "EnsembleForecast",
    "OpenMeteoClient",
    "_coerce_run_time",  # exported for tests
    "_gather_members",  # exported for tests
    "_parse_payload",  # exported for tests
]
