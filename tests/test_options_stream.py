from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest

from kq.clients.databento_stream import StreamClient
from kq.equities.options_cache import CreditSnapshot, OptionsCache, Request


def request():
    return Request(
        "OPRA.PILLAR",
        "cmbp-1",
        ("SPY   261009C00775000",),
        datetime(2026, 10, 8, 14, tzinfo=UTC),
        datetime(2026, 10, 8, 14, 10, tzinfo=UTC),
        "raw_symbol",
        "instrument_id",
        "csv",
        "pilot-v1",
        "raw",
        "original",
    )


def credits():
    now = datetime.now(UTC)
    return CreditSnapshot(Decimal("120"), now, now + timedelta(days=1), True)


@pytest.mark.parametrize("body", [b"wrong\n", b"ts_recv,ts_event,instrument_id,symbol\n"])
def test_truncated_or_wrong_csv_stays_uncertain_and_cannot_repeat(tmp_path, body):
    calls = []

    def handler(req):
        calls.append(req)
        assert req.method == "POST" and req.url.path.endswith("timeseries.get_range")
        return httpx.Response(200, content=body)

    with (
        OptionsCache(tmp_path, budget=Decimal("85")) as cache,
        StreamClient("secret", transport=httpx.MockTransport(handler)) as client,
    ):
        with pytest.raises(ValueError):
            client.acquire(
                cache,
                request(),
                Decimal("0.01"),
                credits(),
                expected_records=1,
                estimate=Decimal("0.005"),
                license_evidence="test",
            )
        assert cache.job(request().key).state == "uncertain"
        with pytest.raises(ValueError, match="unresolved"):
            client.acquire(
                cache,
                request(),
                Decimal("0.01"),
                credits(),
                expected_records=1,
                estimate=Decimal("0.005"),
                license_evidence="test",
            )
        assert len(calls) == 1


def test_scope_and_budget_fail_before_network(tmp_path):
    with (
        OptionsCache(tmp_path, budget=Decimal("85")) as cache,
        StreamClient(
            "secret", transport=httpx.MockTransport(lambda _: pytest.fail("network"))
        ) as client,
    ):
        for spec, cost in [
            (replace(request(), end=request().end + timedelta(seconds=1)), Decimal("1")),
            (request(), Decimal("17.01")),
        ]:
            with pytest.raises(ValueError):
                client.acquire(
                    cache,
                    spec,
                    cost,
                    credits(),
                    expected_records=1,
                    estimate=Decimal("0.1"),
                    license_evidence="test",
                )


@pytest.mark.parametrize("status", [200, 206])
def test_complete_stream_is_cached_and_conservatively_accounted(tmp_path, status):
    body = b"ts_recv,ts_event,instrument_id,symbol\n2026-10-08,2026-10-08,123,SPY\n"
    with (
        OptionsCache(tmp_path, budget=Decimal("85")) as cache,
        StreamClient(
            "secret", transport=httpx.MockTransport(lambda _: httpx.Response(status, content=body))
        ) as client,
    ):
        client.acquire(
            cache,
            request(),
            Decimal("0.01"),
            credits(),
            expected_records=1,
            estimate=Decimal("0.005"),
            license_evidence="test",
        )
        assert cache.job(request().key).actual_cost == Decimal("0.01")
        assert cache.local_files(request())[0].read_bytes() == body
