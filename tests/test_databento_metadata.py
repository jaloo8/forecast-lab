from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from kq.clients.databento_metadata import MetadataClient, load_key

KEY = "db-" + "x" * 29


def test_only_free_get_endpoints_and_header_auth() -> None:
    seen = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=["OPRA.PILLAR"])

    with MetadataClient(KEY, transport=httpx.MockTransport(handle)) as client:
        assert client.get("metadata.list_datasets") == ["OPRA.PILLAR"]
        for endpoint in ("timeseries.get_range", "batch.submit_job", "../batch.submit_job"):
            with pytest.raises(ValueError, match="free endpoint"):
                client.get(endpoint)
    assert len(seen) == 1
    assert seen[0].method == "GET"
    assert seen[0].url.host == "hist.databento.com"
    assert KEY not in str(seen[0].url)
    assert seen[0].headers["authorization"].startswith("Basic ")


@pytest.mark.parametrize("status", [302, 401, 429, 500])
def test_error_body_and_credentials_never_exposed(status: int) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text=KEY, headers={"location": "https://example.org"})

    with (
        MetadataClient(KEY, transport=httpx.MockTransport(handle)) as client,
        pytest.raises(RuntimeError) as error,
    ):
        client.get("metadata.list_datasets")
    assert str(status) in str(error.value)
    assert KEY not in str(error.value)
    assert error.value.__cause__ is None


def test_estimate_rounds_outward_and_records_exact_request() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.params["start"] == "2026-10-16T14:00:00+00:00"
        assert request.url.params["end"] == "2026-10-16T14:20:00+00:00"
        assert request.url.params["symbols"] == "SPY.OPT"
        return httpx.Response(200, json=1.25)

    with MetadataClient(KEY, transport=httpx.MockTransport(handle)) as client:
        quote = client.estimate(
            dataset="OPRA.PILLAR",
            schema="cmbp-1",
            symbols=["SPY.OPT"],
            stype_in="parent",
            start="2026-10-16T14:01:01Z",
            end="2026-10-16T14:11:01Z",
        )
    assert quote["estimated_usd"] == "1.25"
    assert len(quote["request_sha256"]) == 64
    assert quote["requested_start"] == "2026-10-16T14:01:01Z"


def test_definition_estimate_uses_whole_utc_days() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.params["start"] == "2026-10-16T00:00:00+00:00"
        assert request.url.params["end"] == "2026-10-17T00:00:00+00:00"
        return httpx.Response(200, json=0)

    with MetadataClient(KEY, transport=httpx.MockTransport(handle)) as client:
        assert (
            client.estimate(
                dataset="OPRA.PILLAR",
                schema="definition",
                symbols=["SPY.OPT"],
                stype_in="parent",
                start="2026-10-16T13:30:00Z",
                end="2026-10-16T20:00:00Z",
            )["estimated_usd"]
            == "0"
        )


@pytest.mark.parametrize(
    "symbols,start,end",
    [
        ([], "2026-10-16T00:00:00Z", "2026-10-17T00:00:00Z"),
        (["ALL_SYMBOLS"], "2026-10-16T00:00:00Z", "2026-10-17T00:00:00Z"),
        (["SPY"], "2026-10-16", "2026-10-17"),
        (["SPY"], "2026-10-17T00:00:00Z", "2026-10-16T00:00:00Z"),
    ],
)
def test_unbounded_estimate_refused_without_transport(symbols, start, end) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        pytest.fail("Invalid request reached network")

    with MetadataClient(KEY, transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(ValueError):
            client.estimate(
                dataset="OPRA.PILLAR",
                schema="cmbp-1",
                symbols=symbols,
                stype_in="raw_symbol",
                start=start,
                end=end,
            )
        with pytest.raises(ValueError):
            client.get("metadata.get_cost")


@pytest.mark.parametrize("cost", [-1, "NaN", "Infinity", True, {"cost": 4}])
def test_invalid_cost_never_accepted(cost) -> None:
    with (
        MetadataClient(
            KEY, transport=httpx.MockTransport(lambda request: httpx.Response(200, json=cost))
        ) as client,
        pytest.raises(RuntimeError, match="cost"),
    ):
        client.estimate(
            dataset="OPRA.PILLAR",
            schema="cmbp-1",
            symbols=["SPY.OPT"],
            stype_in="parent",
            start="2026-10-16T00:00:00Z",
            end="2026-10-17T00:00:00Z",
        )


def test_key_load_does_not_echo_bad_input(tmp_path: Path) -> None:
    path = tmp_path / "private.env"
    path.write_text("DATABENTO_API_KEY=" + KEY)
    assert load_key(path) == KEY
    path.write_text("DATABENTO_API_KEY=private-invalid-value")
    with pytest.raises(ValueError) as error:
        load_key(path)
    assert "private-invalid-value" not in str(error.value)


def test_estimate_as_of_is_utc() -> None:
    with MetadataClient(
        KEY, transport=httpx.MockTransport(lambda request: httpx.Response(200, json=0.1))
    ) as client:
        result = client.estimate(
            dataset="OPRA.PILLAR",
            schema="cmbp-1",
            symbols=["SPY.OPT"],
            stype_in="parent",
            start="2026-10-16T00:00:00Z",
            end="2026-10-17T00:00:00Z",
        )
    assert datetime.fromisoformat(result["as_of"]).utcoffset() == UTC.utcoffset(None)


def test_transport_failure_sanitizes_exception() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout(KEY, request=request)

    with (
        MetadataClient(KEY, transport=httpx.MockTransport(handle)) as client,
        pytest.raises(RuntimeError) as error,
    ):
        client.get("metadata.list_datasets")
    assert KEY not in str(error.value)
    assert error.value.__suppress_context__


@pytest.mark.parametrize("symbols", ["SPY", [""], [1], ["SPY,QQQ"], [" SPY"], ["*"]])
def test_malformed_symbol_lists_refused_before_transport(symbols) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        pytest.fail("Malformed symbols reached transport")

    with (
        MetadataClient(KEY, transport=httpx.MockTransport(handle)) as client,
        pytest.raises(ValueError, match="symbols"),
    ):
        client.estimate(
            dataset="EQUS.MINI",
            schema="ohlcv-1m",
            symbols=symbols,
            stype_in="raw_symbol",
            start="2026-10-15T00:00:00Z",
            end="2026-10-16T00:00:00Z",
        )
