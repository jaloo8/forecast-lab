import json
from datetime import UTC, datetime
from hashlib import sha256

import httpx
import pytest
from scripts import recover_databento_batches as recovery
from scripts.recover_databento_batches import eligible

from kq.clients.databento_batch import BatchClient


def test_existing_jobs_inspection_is_get_only_and_accepts_current_short_response():
    calls = []

    def handler(request):
        calls.append(request)
        assert request.method == "GET"
        assert request.url.path == "/v0/batch.list_jobs"
        assert request.url.params["since"] == "2026-10-18T00:00:00+00:00"
        return httpx.Response(200, json=[{"id": "OPRA-20261019-EXAMPLE", "state": "done"}])

    with BatchClient("test-credential", transport=httpx.MockTransport(handler)) as client:
        assert len(client.list_jobs(datetime(2026, 10, 18, tzinfo=UTC))) == 1
    assert len(calls) == 1


@pytest.mark.parametrize("payload", [{}, [{"id": "../escape"}], [{"state": "done"}]])
def test_existing_job_listing_rejects_bad_identity(payload):
    with (
        BatchClient(
            "test-credential",
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)),
        ) as client,
        pytest.raises(ValueError, match="inventory"),
    ):
        client.list_jobs(datetime(2026, 10, 18, tzinfo=UTC))


def test_listing_errors_do_not_disclose_response_or_credential():
    with BatchClient(
        "test-credential",
        transport=httpx.MockTransport(lambda _: httpx.Response(401, text="sensitive response")),
    ) as client:
        with pytest.raises(RuntimeError) as error:
            client.list_jobs(datetime(2026, 10, 18, tzinfo=UTC))
        assert str(error.value) == "Databento batch HTTP 401; reconcile before retry"


def test_recovery_scope_excludes_nonspy_and_unfinished_jobs():
    job = {
        "state": "done",
        "encoding": "csv",
        "dataset": "OPRA.PILLAR",
        "schema": "definition",
        "symbols": "SPY.OPT",
    }
    assert eligible(job)
    assert not eligible({**job, "symbols": "QQQ.OPT"})
    assert not eligible({**job, "state": "expired"})
    assert not eligible({**job, "schema": "mbo"})
    assert eligible({**job, "schema": "cmbp-1", "symbols": ["SPY   261009C00775000"]})
    assert eligible({**job, "schema": "ohlcv-1m", "dataset": "EQUS.MINI", "symbols": "SPY"})


def test_cli_downloads_only_retained_files_and_redacts_metadata(tmp_path, monkeypatch):
    payload = b"verified fixture\n"
    calls = []
    job = {
        "id": "OPRA-EXAMPLE",
        "state": "done",
        "encoding": "csv",
        "dataset": "OPRA.PILLAR",
        "schema": "definition",
        "symbols": "SPY.OPT",
        "api_key": "private-fixture",
        "user_id": "private-account",
    }
    manifest = [
        {
            "filename": "data.csv",
            "size": len(payload),
            "hash": "sha256:" + sha256(payload).hexdigest(),
            "urls": {
                "https": "https://api.databento.com/v0/batch/download/TEAM/OPRA-EXAMPLE/data.csv"
            },
        }
    ]

    def handler(request):
        assert request.method == "GET"
        calls.append(request.url.path)
        if request.url.path.endswith("list_jobs"):
            return httpx.Response(200, json=[job])
        if request.url.path.endswith("get_job_details"):
            return httpx.Response(200, json=job)
        if request.url.path.endswith("list_files"):
            return httpx.Response(200, json=manifest)
        assert request.url.path.endswith("/OPRA-EXAMPLE/data.csv")
        return httpx.Response(200, content=payload)

    monkeypatch.setattr(recovery, "load_key", lambda _: "private-fixture")
    monkeypatch.setattr(
        recovery,
        "BatchClient",
        lambda key: BatchClient(key, transport=httpx.MockTransport(handler)),
    )
    output = tmp_path / "recovery"
    monkeypatch.setattr(
        "sys.argv", ["recover", "--credentials", "unused", "--output", str(output), "--download"]
    )
    recovery.main()
    assert len(calls) == 4
    assert (output / "OPRA-EXAMPLE/files/data.csv").read_bytes() == payload
    for file in output.rglob("*.json"):
        assert "private-fixture" not in file.read_text()
        assert "private-account" not in file.read_text()
    report = json.loads((output / "recovery.json").read_text())
    assert report["new_jobs_submitted"] == 0
    assert report["jobs"][0]["files"][0]["verified_download"]
