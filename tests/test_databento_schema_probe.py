"""Artificial fixtures only: these checks are not historical trading results."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Any

import httpx
import pytest
from scripts.acquire_cbbo_schema_probe import main

from kq.clients.databento_metadata import MetadataClient
from kq.clients.databento_schema_probe import (
    CEILING,
    DEFAULT_PLAN,
    PLAN_SHA256,
    SchemaProbeClient,
    load_plan,
    quote_plan,
    read_credits,
    request_params,
    reserved_cost,
    sanitized,
    save_receipt,
    validate_estimate,
)
from kq.equities.options_cache import CreditSnapshot, OptionsCache, RawFile, Request


def credit(**changes: Any) -> CreditSnapshot:
    now = datetime.now(UTC)
    return replace(CreditSnapshot(Decimal("116"), now, now + timedelta(days=1), True), **changes)


def quotes(cost: str = "0.01") -> dict[str, Any]:
    with MetadataClient(
        "fixture", transport=httpx.MockTransport(lambda _: httpx.Response(200, json=cost))
    ) as metadata:
        return quote_plan(metadata)


def detail(request: Request, **changes: Any) -> dict[str, Any]:
    return {
        **request_params(request),
        "id": "OPRA-fixture",
        "state": "done",
        "encoding": "csv",
        "compression": None,
        "stype_out": "instrument_id",
        "pretty_px": True,
        "pretty_ts": True,
        "map_symbols": True,
        "limit": None,
        "record_count": 1,
        "cost_usd": "0.01",
        **changes,
    }


def cached_file(cache: OptionsCache, request: Request, actual: str = "0.01") -> None:
    path = cache.root / "fixture.csv"
    path.write_bytes(b"a,b\n1,2\n")
    cache.import_files(
        request.key,
        (RawFile(path, 8, sha256(path.read_bytes()).hexdigest()),),
        complete=True,
        actual_cost=Decimal(actual),
        license_evidence="artificial fixture",
        conditions="artificial fixture",
    )


def test_exact_plan_and_request_versions_are_pinned(tmp_path: Path) -> None:
    plan = load_plan()
    assert len(plan) == len({item.key for _, item in plan}) == 9
    assert sha256(DEFAULT_PLAN.read_bytes()).hexdigest() == PLAN_SHA256
    changed = tmp_path / "changed.json"
    changed.write_bytes(DEFAULT_PLAN.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="hash"):
        load_plan(changed)
    with pytest.raises(ValueError, match="pinned"):
        request_params(replace(plan[0][1], protocol_version="changed"))


@pytest.mark.parametrize(
    ("cost", "expected"),
    [("0", "0.0001"), ("0.01", "0.0120"), ("0.00010001", "0.0002")],
)
def test_reservations_round_up_per_job(cost: str, expected: str) -> None:
    assert reserved_cost(Decimal(cost)) == Decimal(expected)


@pytest.mark.parametrize("cost", ["NaN", "Infinity", "-0.01"])
def test_invalid_price_rejected(cost: str) -> None:
    with pytest.raises(ValueError, match="finite"):
        reserved_cost(Decimal(cost))


def test_free_quote_uses_only_nine_get_requests() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.method == "GET"
        assert request.url.path == "/v0/metadata.get_cost"
        return httpx.Response(200, json="0.01")

    with MetadataClient("fixture", transport=httpx.MockTransport(handler)) as metadata:
        receipt = quote_plan(metadata)
    assert len(calls) == 9
    assert receipt["reservation_total_usd"] == "0.1080"
    assert receipt["new_billable_jobs"] == 0


@pytest.mark.parametrize("change", ["identity", "stale", "future", "naive"])
def test_estimate_must_be_current_and_for_exact_request(change: str) -> None:
    request = load_plan()[0][1]
    receipt = quotes()["requests"][0]["estimate"]
    if change == "identity":
        receipt["params"]["schema"] = "cbbo-1m"
    else:
        instant = datetime.now(UTC) + timedelta(minutes=10 if change == "future" else -10)
        receipt["as_of"] = (
            instant.replace(tzinfo=None).isoformat() if change == "naive" else instant.isoformat()
        )
    with pytest.raises(ValueError, match=r"identity|Fresh"):
        validate_estimate(request, receipt)


def test_before_post_intent_is_durable_and_timeout_never_reposts(tmp_path: Path) -> None:
    request = load_plan()[1][1]
    calls = []
    with OptionsCache(tmp_path, budget=CEILING) as cache:

        def handler(http_request: httpx.Request) -> httpx.Response:
            calls.append(http_request.method)
            if http_request.method == "GET":
                return httpx.Response(200, json=[])
            assert cache.job(request.key).state == "uncertain"
            assert cache.job(request.key).reserved_cost == Decimal("0.0120")
            assert list((cache.root / "runs" / request.key).glob("*-pre-submit-quotes.json"))
            raise httpx.ReadTimeout("db-" + "A" * 29)

        with SchemaProbeClient("fixture", transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(RuntimeError, match="uncertain") as failure:
                client.submit_probe(cache, request, quotes(), credit())
            assert "db-" not in str(failure.value)
            with pytest.raises(ValueError, match="never resubmit"):
                client.submit_probe(cache, request, quotes(), credit())
            assert client.resume(cache, request, license_evidence="")["state"] == "uncertain"
        assert calls == ["GET", "POST"]


def test_wrong_plan_order_and_total_block_before_transport(tmp_path: Path) -> None:
    request = load_plan()[1][1]
    with (
        OptionsCache(tmp_path, budget=CEILING) as cache,
        SchemaProbeClient(
            "fixture", transport=httpx.MockTransport(lambda _: pytest.fail("network"))
        ) as client,
    ):
        too_large = quotes("0.05")
        assert too_large["within_ceiling"] is False
        with pytest.raises(ValueError, match="Whole-plan"):
            client.submit_probe(cache, request, too_large, credit())
        reordered = quotes()
        reordered["requests"].reverse()
        with pytest.raises(ValueError, match="order"):
            client.submit_probe(cache, request, reordered, credit())


def test_actual_prior_charge_counts_against_ceiling(tmp_path: Path) -> None:
    first, second = [item for _, item in load_plan()[:2]]
    with (
        OptionsCache(tmp_path, budget=CEILING) as cache,
        SchemaProbeClient(
            "fixture", transport=httpx.MockTransport(lambda _: pytest.fail("network"))
        ) as client,
    ):
        cache.reserve(first, Decimal("0.01"), credit())
        cache.mark_submitted(first.key, "first")
        cached_file(cache, first, actual="0.49")
        with pytest.raises(ValueError, match="Whole-plan"):
            client.submit_probe(cache, second, quotes(), credit())


@pytest.mark.parametrize(
    "changes",
    [
        {"verified": False},
        {"available": Decimal("0.001")},
        {"observed_at": datetime.now(UTC) - timedelta(minutes=10)},
        {"expires_at": datetime.now(UTC) - timedelta(minutes=1)},
    ],
)
def test_credit_checks_block_every_post(tmp_path: Path, changes: dict[str, Any]) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        assert request.method == "GET"
        return httpx.Response(200, json=[])

    with (
        OptionsCache(tmp_path, budget=CEILING) as cache,
        SchemaProbeClient("fixture", transport=httpx.MockTransport(handler)) as client,
        pytest.raises(ValueError, match="credits"),
    ):
        client.submit_probe(cache, load_plan()[0][1], quotes(), credit(**changes))
    assert calls == ["GET"]


def test_existing_vendor_job_blocks_repurchase_even_without_catalog(tmp_path: Path) -> None:
    request = load_plan()[0][1]
    calls = []

    def handler(http_request: httpx.Request) -> httpx.Response:
        calls.append(http_request.method)
        assert http_request.method == "GET"
        if http_request.url.path.endswith("list_jobs"):
            return httpx.Response(200, json=[{"id": "OPRA-fixture"}])
        return httpx.Response(200, json=detail(request, symbols=["SPY.OPT"], compression="zstd"))

    with (
        OptionsCache(tmp_path, budget=CEILING) as cache,
        SchemaProbeClient("fixture", transport=httpx.MockTransport(handler)) as client,
        pytest.raises(ValueError, match="without repurchase"),
    ):
        client.submit_probe(cache, request, quotes(), credit())
    assert calls == ["GET", "GET"]


def test_one_successful_post_then_cache_blocks_other_request(tmp_path: Path) -> None:
    request = load_plan()[0][1]
    calls = []

    def handler(http_request: httpx.Request) -> httpx.Response:
        calls.append(http_request.method)
        if http_request.method == "GET":
            return httpx.Response(200, json=[])
        assert b"pretty_px=true" in http_request.content
        assert b"pretty_ts=true" in http_request.content
        assert b"limit=" not in http_request.content
        return httpx.Response(200, json={"id": "OPRA-fixture"})

    with (
        OptionsCache(tmp_path, budget=CEILING) as cache,
        SchemaProbeClient("fixture", transport=httpx.MockTransport(handler)) as client,
    ):
        assert client.submit_probe(cache, request, quotes(), credit())["state"] == "submitted"
        with pytest.raises(ValueError, match="unresolved"):
            client.submit_probe(cache, load_plan()[1][1], quotes(), credit())
    assert calls.count("POST") == 1


def test_uncertain_submission_reconciles_only_matching_existing_job(tmp_path: Path) -> None:
    request = load_plan()[0][1]
    supplied = detail(request, schema="cbbo-1m")
    with OptionsCache(tmp_path, budget=CEILING) as cache:
        cache.reserve(request, Decimal("0.02"), credit())
        cache.mark_submission_unknown(request.key)

        def handler(http_request: httpx.Request) -> httpx.Response:
            assert http_request.method == "GET"
            return httpx.Response(200, json=supplied)

        with SchemaProbeClient("fixture", transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(ValueError, match="differs"):
                client.reconcile(cache, request, "OPRA-fixture")
            assert cache.job(request.key).job_id is None
            supplied["schema"] = request.schema
            client.reconcile(cache, request, "OPRA-fixture")
        assert cache.job(request.key).job_id == "OPRA-fixture"


def test_resume_verifies_delivery_and_reuses_cache_without_network(tmp_path: Path) -> None:
    request = load_plan()[1][1]
    payload = b"a,b\n1,2\n"
    calls = []
    manifest = {
        "filename": "data.csv",
        "size": len(payload),
        "hash": "sha256:" + sha256(payload).hexdigest(),
        "urls": {
            "https": "https://hist.databento.com/v0/batch/download/team/OPRA-fixture/data.csv"
        },
    }

    def handler(http_request: httpx.Request) -> httpx.Response:
        calls.append(http_request)
        assert http_request.method == "GET"
        if http_request.url.path.endswith("get_job_details"):
            return httpx.Response(200, json=detail(request))
        if http_request.url.path.endswith("list_files"):
            return httpx.Response(200, json=[manifest])
        return httpx.Response(200, content=payload)

    with OptionsCache(tmp_path, budget=CEILING) as cache:
        cache.reserve(request, Decimal("0.02"), credit())
        cache.mark_submitted(request.key, "OPRA-fixture")
        with SchemaProbeClient("fixture", transport=httpx.MockTransport(handler)) as client:
            result = client.resume(cache, request, license_evidence="artificial fixture")
            assert result["state"] == "complete"
            assert result["new_billable_jobs"] == 0
            assert client.resume(cache, request, license_evidence="")["state"] == "cached"
        assert len(calls) == 3
        assert cache.local_files(request)[0].read_bytes() == payload


def test_resume_empty_cache_never_submits(tmp_path: Path) -> None:
    with (
        OptionsCache(tmp_path, budget=CEILING) as cache,
        SchemaProbeClient(
            "fixture", transport=httpx.MockTransport(lambda _: pytest.fail("network"))
        ) as client,
    ):
        assert (
            client.resume(cache, load_plan()[0][1], license_evidence="")["state"] == "not_acquired"
        )


def test_credit_file_and_secret_redaction(tmp_path: Path) -> None:
    evidence = {
        "available": "116.00",
        "observed_at": datetime.now(UTC).isoformat(),
        "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        "verified": True,
        "cash_budget_usd": "0",
        "license_evidence": "artificial fixture only",
        "outstanding_usage_reconciled": True,
        "deduct_imports": True,
    }
    path = tmp_path / "credit.json"
    path.write_text(json.dumps(evidence))
    snapshot, _ = read_credits(path)
    assert snapshot.deduct_imports
    evidence["verified"] = False
    path.write_text(json.dumps(evidence))
    with pytest.raises(ValueError, match="verified"):
        read_credits(path)
    secret = "db-" + "A" * 29
    receipt = tmp_path / "receipt.json"
    save_receipt(receipt, {"api_key": secret, "nested": [{"message": secret, "email": "private"}]})
    assert secret not in receipt.read_text()
    assert "private" not in receipt.read_text()
    assert sanitized({"authorization": secret}) == {}
    with pytest.raises(FileExistsError):
        save_receipt(receipt, {})


def test_cli_offline_and_status_need_no_key_or_network(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main(["--offline"])
    assert json.loads(capsys.readouterr().out)["new_billable_jobs"] == 0
    main(["--status", "--root", str(tmp_path / "absent")])
    assert json.loads(capsys.readouterr().out)["state"] == "no_catalog"
    assert not (tmp_path / "absent").exists()
    with OptionsCache(tmp_path, budget=CEILING):
        pass
    main(["--status", "--root", str(tmp_path)])
    assert json.loads(capsys.readouterr().out)["persistent_budget_usd"] == "0.50"


def test_cli_existing_output_rejected_before_any_network(tmp_path: Path) -> None:
    output = tmp_path / "receipt.json"
    output.write_text("old evidence")
    with pytest.raises(FileExistsError, match="preserved"):
        main(["--output", str(output)])
    assert output.read_text() == "old evidence"


def test_probe_client_disables_inherited_legacy_submit(tmp_path: Path) -> None:
    with (
        OptionsCache(tmp_path, budget=CEILING) as cache,
        SchemaProbeClient(
            "fixture", transport=httpx.MockTransport(lambda _: pytest.fail("network"))
        ) as client,
        pytest.raises(ValueError, match="Legacy submission is disabled"),
    ):
        client.submit(cache, load_plan()[0][1], Decimal("0.01"), credit())


def test_slow_inventory_invalidates_quote_before_post(tmp_path: Path) -> None:
    receipt = quotes()
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        assert request.method == "GET"
        receipt["requests"][0]["estimate"]["as_of"] = (
            datetime.now(UTC) - timedelta(minutes=10)
        ).isoformat()
        return httpx.Response(200, json=[])

    with (
        OptionsCache(tmp_path, budget=CEILING) as cache,
        SchemaProbeClient("fixture", transport=httpx.MockTransport(handler)) as client,
        pytest.raises(ValueError, match="Fresh estimate"),
    ):
        client.submit_probe(cache, load_plan()[0][1], receipt, credit())
    assert calls == ["GET"]
