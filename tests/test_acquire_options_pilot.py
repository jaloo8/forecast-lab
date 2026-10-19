from datetime import UTC, datetime

import pytest
from scripts.acquire_options_pilot import request_from_receipt, validate_job

from tests.test_databento_batch import spec


def test_request_uses_exact_bounds_not_estimate_rounding() -> None:
    item = {
        "params": {
            "dataset": "OPRA.PILLAR",
            "schema": "cmbp-1",
            "symbols": "SPY   261009C00775000,SPY   261009C00776000",
            "stype_in": "raw_symbol",
            "start": "2026-10-08T13:30:00Z",
            "end": "2026-10-08T20:00:00Z",
        },
        "requested_start": "2026-10-08T13:31:00Z",
        "requested_end": "2026-10-08T19:59:00Z",
    }
    request = request_from_receipt(item)
    assert request.encoding == "csv"
    assert len(request.symbols) == 2
    assert request.start == datetime(2026, 10, 8, 13, 31, tzinfo=UTC)
    item["requested_start"] = "2026-10-08T13:31:00"
    with pytest.raises(ValueError, match="timezone"):
        request_from_receipt(item)


@pytest.mark.parametrize(
    "field,value",
    [
        ("symbols", "OTHER"),
        ("start", "2026-10-08T14:00:00Z"),
        ("limit", 1),
        ("pretty_px", False),
        ("map_symbols", False),
    ],
)
def test_reject_wrong_job_before_cache_admission(field: str, value: object) -> None:
    request = spec()
    details = {
        "dataset": request.dataset,
        "schema": request.schema,
        "encoding": "csv",
        "compression": "none",
        "stype_in": request.stype_in,
        "stype_out": request.stype_out,
        "symbols": ",".join(request.symbols),
        "start": request.start.isoformat(),
        "end": request.end.isoformat(),
        "pretty_px": True,
        "pretty_ts": True,
        "map_symbols": True,
        "limit": None,
    }
    validate_job(request, details)
    del details["limit"]
    with pytest.raises(ValueError):
        validate_job(request, details)
    details["limit"] = None
    details["compression"] = None
    validate_job(request, details)
    details[field] = value
    with pytest.raises(ValueError):
        validate_job(request, details)
