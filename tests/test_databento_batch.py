from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

import httpx
import pytest

from kq.clients.databento_batch import BatchClient
from kq.equities.options_cache import CreditSnapshot, OptionsCache, RawFile, Request


def spec() -> Request:
    return Request(
        "OPRA.PILLAR",
        "cmbp-1",
        ("SPY   261009C00775000",),
        datetime(2026, 10, 8, 13, 30, tzinfo=UTC),
        datetime(2026, 10, 8, 20, tzinfo=UTC),
        "raw_symbol",
        "instrument_id",
        "csv",
        "pilot-v1",
        "raw",
        "original",
    )


def credit() -> CreditSnapshot:
    now = datetime.now(UTC)
    return CreditSnapshot(Decimal("125"), now, now + timedelta(days=1), True)


def test_uncertain_before_post_and_never_resubmit(tmp_path: Path) -> None:
    calls = []
    with OptionsCache(tmp_path, budget=Decimal("85")) as cache:

        def handler(req: httpx.Request) -> httpx.Response:
            calls.append(req)
            assert cache.job(spec().key).state == "uncertain"
            raise httpx.ReadTimeout("private response must not leak")

        with BatchClient("secret", transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(RuntimeError, match="uncertain"):
                client.submit(cache, spec(), Decimal("1"), credit())
            with pytest.raises(ValueError, match="unresolved"):
                client.submit(cache, spec(), Decimal("1"), credit())
        assert len(calls) == 1


def test_under_ten_dollar_ceiling_before_transport(tmp_path: Path) -> None:
    with (
        OptionsCache(tmp_path, budget=Decimal("85")) as cache,
        BatchClient(
            "secret", transport=httpx.MockTransport(lambda _: pytest.fail("network"))
        ) as client,
        pytest.raises(ValueError, match="budget"),
    ):
        client.submit(cache, spec(), Decimal("10"), credit())


@pytest.mark.parametrize(
    "change",
    [
        {"schema": "mbo"},
        {"symbols": ("SPY.OPT",), "stype_in": "parent"},
        {"symbols": ("SPY   261009C00775000,SPY.OPT",)},
        {"encoding": "dbn"},
    ],
)
def test_reject_unapproved_scope(tmp_path: Path, change: dict) -> None:
    with (
        OptionsCache(tmp_path, budget=Decimal("85")) as cache,
        BatchClient(
            "secret", transport=httpx.MockTransport(lambda _: pytest.fail("network"))
        ) as client,
        pytest.raises(ValueError, match="pilot"),
    ):
        client.submit(cache, replace(spec(), **change), Decimal("1"), credit())


def test_submit_explicit_csv_no_record_limit(tmp_path: Path) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.method == "POST" and req.url.path == "/v0/batch.submit_job"
        assert b"encoding=csv" in req.content and b"compression=none" in req.content
        assert b"limit=" not in req.content
        return httpx.Response(200, json={"id": "OPRA-test", "state": "queued"})

    with OptionsCache(tmp_path, budget=Decimal("85")) as cache:
        with BatchClient("secret", transport=httpx.MockTransport(handler)) as client:
            assert client.submit(cache, spec(), Decimal("1"), credit())["id"] == "OPRA-test"
        assert cache.job(spec().key).job_id == "OPRA-test"


def test_download_refuses_foreign_host_and_corrupt_bytes(tmp_path: Path) -> None:
    with BatchClient(
        "secret", transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"bad"))
    ) as client:
        meta = {
            "filename": "data.csv",
            "size": 3,
            "hash": "sha256:" + "a" * 64,
            "urls": {"https": "https://evil.test/v0/batch/download/x"},
        }
        with pytest.raises(ValueError, match="host"):
            client.download(meta, tmp_path)
        meta["urls"]["https"] = "https://hist.databento.com/v0/batch/download/x"
        with pytest.raises(ValueError, match="integrity"):
            client.download(meta, tmp_path)
        assert not (tmp_path / "data.csv").exists()


def test_download_preserves_existing_partial(tmp_path: Path) -> None:
    part = tmp_path / "data.csv.part"
    part.write_bytes(b"prior interrupted evidence")
    meta = {
        "filename": "data.csv",
        "size": 2,
        "hash": "sha256:" + sha256(b"ok").hexdigest(),
        "urls": {"https": "https://hist.databento.com/v0/batch/download/x"},
    }
    with (
        BatchClient(
            "secret", transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"ok"))
        ) as client,
        pytest.raises(FileExistsError),
    ):
        client.download(meta, tmp_path)
    assert part.read_bytes() == b"prior interrupted evidence"


def test_ceiling_counts_prior_completed_usage(tmp_path: Path) -> None:
    with OptionsCache(tmp_path, budget=Decimal("85")) as cache:
        key = cache.reserve(spec(), Decimal("6"), credit(), ceiling=Decimal("9.99"))
        cache.mark_submitted(key, "first")
        path = tmp_path / "original"
        path.write_bytes(b"original")
        cache.import_files(
            key,
            (RawFile(path, 8, sha256(b"original").hexdigest()),),
            complete=True,
            actual_cost=Decimal("6"),
            license_evidence="test",
            conditions="test",
        )
        later = replace(
            spec(), start=spec().start + timedelta(days=1), end=spec().end + timedelta(days=1)
        )
        with pytest.raises(ValueError, match="budget"):
            cache.reserve(later, Decimal("4"), credit(), ceiling=Decimal("9.99"))


def test_manifest_rejects_other_job_before_download() -> None:
    manifest = [
        {"urls": {"https": "https://api.databento.com/v0/batch/download/team/OTHER/data.csv"}}
    ]
    with (
        BatchClient(
            "secret", transport=httpx.MockTransport(lambda _: httpx.Response(200, json=manifest))
        ) as client,
        pytest.raises(ValueError, match="job"),
    ):
        client.files("EXPECTED")


def test_verified_delivery_reuses_local_bytes(tmp_path: Path) -> None:
    calls = []
    meta = {
        "filename": "data.csv",
        "size": 2,
        "hash": "sha256:" + sha256(b"ok").hexdigest(),
        "urls": {"https": "https://api.databento.com/v0/batch/download/team/JOB/data.csv"},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path.endswith("get_job_details"):
            return httpx.Response(200, json={"id": "JOB"})
        if request.url.path.endswith("list_files"):
            return httpx.Response(200, json=[meta])
        return httpx.Response(200, content=b"ok")

    with BatchClient("secret", transport=httpx.MockTransport(handler)) as client:
        assert client.details("JOB")["id"] == "JOB"
        item = client.files("JOB")[0]
        first = client.download(item, tmp_path)
        assert client.download(item, tmp_path) == first
    assert len(calls) == 3
