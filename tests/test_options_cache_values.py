from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from kq.equities import _options_cache_io as oc


@pytest.fixture
def request_spec() -> oc.Request:
    return oc.Request(
        dataset="OPRA.PILLAR",
        schema="mbp-1",
        symbols=("SPY C", "SPY P"),
        start=datetime(2026, 10, 1, 14, tzinfo=UTC),
        end=datetime(2026, 10, 1, 15, tzinfo=UTC),
        stype_in="raw_symbol",
        stype_out="instrument_id",
        encoding="dbn",
        protocol_version="v0",
        normalization_version="raw",
        source_version="original",
    )


def credits(now: datetime, amount: str = "125") -> oc.CreditSnapshot:
    return oc.CreditSnapshot(
        available=Decimal(amount),
        observed_at=now,
        expires_at=now + timedelta(days=1),
        verified=True,
    )


def test_request_canonicalization(request_spec: oc.Request) -> None:
    other = replace(
        request_spec,
        symbols=("SPY P", "SPY C", "SPY C"),
        start=request_spec.start.astimezone(timezone(timedelta(hours=-4))),
    )
    assert request_spec.key == other.key
    assert request_spec.canonical == other.canonical
    assert request_spec.key != replace(request_spec, schema="trades").key
    assert request_spec.key != replace(request_spec, source_version="correction-1").key


@pytest.mark.parametrize(
    "change",
    [
        {"symbols": ()},
        {"symbols": ("ALL_SYMBOLS",)},
        {"symbols": ("*",)},
        {"start": datetime(2026, 10, 1)},
        {"dataset": ""},
        {"end": datetime(2026, 10, 1, 14, tzinfo=UTC)},
    ],
)
def test_unbounded_requests_rejected(request_spec: oc.Request, change: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        replace(request_spec, **change)  # type: ignore[arg-type]


@pytest.mark.parametrize("case", ["unknown", "expired", "stale", "unverified", "insufficient"])
def test_credit_evidence_must_be_current_and_sufficient(case: str) -> None:
    now = datetime.now(UTC)
    snapshot = credits(now)
    changes = {
        "unknown": {"available": None},
        "expired": {"expires_at": now},
        "stale": {"observed_at": now - timedelta(minutes=6)},
        "unverified": {"verified": False},
        "insufficient": {"available": Decimal("0.01")},
    }
    snapshot = replace(snapshot, **changes[case])
    with pytest.raises(ValueError):
        snapshot.validate(Decimal("0.10"), now)
