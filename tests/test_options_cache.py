"""Offline cache contracts; the shared autouse fixture forbids network egress."""

from __future__ import annotations

import hashlib
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from kq.equities import options_cache as oc


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


def payload(root: Path, content: bytes = b"raw precise vendor bytes") -> oc.RawFile:
    digest = hashlib.sha256(content).hexdigest()
    path = root / digest
    path.write_bytes(content)
    return oc.RawFile(path, len(content), digest)


def reserve(cache: oc.OptionsCache, spec: oc.Request, cost: str = "0.10") -> str:
    now = datetime.now(UTC)
    return cache.reserve(spec, Decimal(cost), credits(now), now=now)


def finish(cache: oc.OptionsCache, spec: oc.Request, raw: oc.RawFile) -> str:
    key = reserve(cache, spec)
    cache.mark_submission_unknown(key)
    cache.mark_submitted(key, "job-" + key)
    cache.import_files(
        key,
        (raw,),
        complete=True,
        actual_cost=Decimal("0.10"),
        license_evidence="local approved terms",
        conditions="unlimited response",
    )
    return key


def test_subset_gaps_and_adjacent_merge(request_spec: oc.Request, tmp_path: Path) -> None:
    with oc.OptionsCache(tmp_path / "cache", budget=Decimal("5")) as cache:
        middle = request_spec.start + timedelta(minutes=20)
        later = request_spec.start + timedelta(minutes=40)
        finish(cache, replace(request_spec, end=middle), payload(tmp_path, b"a"))
        finish(cache, replace(request_spec, start=later), payload(tmp_path, b"b"))
        assert cache.missing(request_spec) == (replace(request_spec, start=middle, end=later),)
        finish(cache, replace(request_spec, start=middle, end=later), payload(tmp_path))
        subset = replace(request_spec, symbols=("SPY C",), start=middle, end=later)
        assert cache.missing(subset) == ()
        assert len(cache.local_files(request_spec)) == 3
        with pytest.raises(ValueError, match="covered"):
            reserve(cache, subset)


def test_per_symbol_coverage_and_schema_separation(
    request_spec: oc.Request,
    tmp_path: Path,
) -> None:
    with oc.OptionsCache(tmp_path / "cache", budget=Decimal("5")) as cache:
        finish(cache, replace(request_spec, symbols=("SPY C",)), payload(tmp_path))
        assert cache.missing(request_spec) == (replace(request_spec, symbols=("SPY P",)),)
        for changed in (
            replace(request_spec, schema="trades"),
            replace(request_spec, normalization_version="v2"),
            replace(request_spec, source_version="corrected"),
        ):
            assert cache.missing(changed) == (changed,)
        with pytest.raises(ValueError, match="coverage"):
            cache.local_files(request_spec)


@pytest.mark.parametrize("damage", [b"wrong but same length!!!!", b"short"])
def test_corrupt_cache_never_counts_as_coverage(
    request_spec: oc.Request,
    tmp_path: Path,
    damage: bytes,
) -> None:
    with oc.OptionsCache(tmp_path / "cache", budget=Decimal("5")) as cache:
        finish(cache, request_spec, payload(tmp_path))
        cache.local_files(request_spec)[0].write_bytes(damage)
        assert cache.missing(request_spec) == (request_spec,)
        with pytest.raises(ValueError, match="coverage"):
            cache.local_files(request_spec)


def test_duplicate_reservation_survives_reopen(
    request_spec: oc.Request,
    tmp_path: Path,
) -> None:
    root = tmp_path / "cache"
    with oc.OptionsCache(root, budget=Decimal("5")) as cache:
        key = reserve(cache, request_spec)
    with oc.OptionsCache(root, budget=Decimal("5")) as reopened:
        assert reopened.job(key).state == "reserved"
        with pytest.raises(ValueError, match=r"duplicate|unresolved"):
            reserve(reopened, request_spec)
        with pytest.raises(ValueError, match="unresolved"):
            reserve(reopened, replace(request_spec, symbols=("OTHER",)))


def test_unknown_submission_requires_reconciliation_and_retains_job(
    request_spec: oc.Request,
    tmp_path: Path,
) -> None:
    root = tmp_path / "cache"
    with oc.OptionsCache(root, budget=Decimal("5")) as cache:
        key = reserve(cache, request_spec)
        cache.mark_submission_unknown(key)
    with oc.OptionsCache(root, budget=Decimal("5")) as cache:
        assert cache.job(key).state == "uncertain"
        with pytest.raises(ValueError):
            reserve(cache, request_spec)
        cache.mark_submitted(key, "known-vendor-job")
        cache.mark_submitted(key, "known-vendor-job")
        assert cache.job(key).job_id == "known-vendor-job"
        with pytest.raises(ValueError):
            cache.mark_submitted(key, "different-job")
        with pytest.raises(ValueError):
            reserve(cache, replace(request_spec, schema="trades"))


@pytest.mark.parametrize("kind", ["unknown", "unverified", "expired", "stale", "future", "low"])
def test_credit_snapshot_refusals(
    request_spec: oc.Request,
    tmp_path: Path,
    kind: str,
) -> None:
    now = datetime.now(UTC)
    snapshot = credits(now)
    if kind == "unknown":
        snapshot = replace(snapshot, available=None)
    elif kind == "unverified":
        snapshot = replace(snapshot, verified=False)
    elif kind == "expired":
        snapshot = replace(snapshot, expires_at=now)
    elif kind == "stale":
        snapshot = replace(snapshot, observed_at=now - timedelta(minutes=6))
    elif kind == "future":
        snapshot = replace(snapshot, observed_at=now + timedelta(seconds=1))
    elif kind == "low":
        snapshot = replace(snapshot, available=Decimal("0.09"))
    with (
        oc.OptionsCache(tmp_path / "cache", budget=Decimal("5")) as cache,
        pytest.raises(ValueError, match="credit"),
    ):
        cache.reserve(request_spec, Decimal("0.10"), snapshot, now=now)


def test_decimal_cumulative_budget_and_no_reset(
    request_spec: oc.Request,
    tmp_path: Path,
) -> None:
    root = tmp_path / "cache"
    with oc.OptionsCache(root, budget=Decimal("0.30")) as cache:
        finish(cache, request_spec, payload(tmp_path))
        finish(cache, replace(request_spec, source_version="v2"), payload(tmp_path, b"v2"))
    with oc.OptionsCache(root, budget=Decimal("0.30")) as cache:
        finish(cache, replace(request_spec, source_version="v3"), payload(tmp_path, b"v3"))
        with pytest.raises(ValueError, match="budget"):
            reserve(cache, replace(request_spec, source_version="v4"), "0.01")
    with pytest.raises(ValueError, match="budget"):
        oc.OptionsCache(root, budget=Decimal("999"))


@pytest.mark.parametrize("bad_cost", ["NaN", "Infinity", "-0.1"])
def test_invalid_money_rejected(
    request_spec: oc.Request,
    tmp_path: Path,
    bad_cost: str,
) -> None:
    with (
        oc.OptionsCache(tmp_path / "cache", budget=Decimal("5")) as cache,
        pytest.raises(ValueError),
    ):
        reserve(cache, request_spec, bad_cost)


@pytest.mark.parametrize("failure", ["partial", "size", "hash", "second-file"])
def test_failed_import_retry_preserves_reservation(
    request_spec: oc.Request,
    tmp_path: Path,
    failure: str,
) -> None:
    root = tmp_path / "cache"
    good = payload(tmp_path)
    bad = replace(good, size=good.size + 1) if failure == "size" else replace(good, sha256="0" * 64)
    files = (good, bad) if failure == "second-file" else (bad,)
    with oc.OptionsCache(root, budget=Decimal("5")) as cache:
        key = reserve(cache, request_spec)
        cache.mark_submitted(key, "resume-this-job")
        with pytest.raises(ValueError):
            cache.import_files(
                key,
                files,
                complete=failure != "partial",
                actual_cost=Decimal("0.10"),
                license_evidence="terms",
                conditions="unlimited",
            )
        assert cache.missing(request_spec) == (request_spec,)
        assert cache.job(key).state != "complete"
    with oc.OptionsCache(root, budget=Decimal("5")) as cache:
        assert cache.job(key).job_id == "resume-this-job"
        cache.import_files(
            key,
            (good,),
            complete=True,
            actual_cost=Decimal("0.10"),
            license_evidence="terms",
            conditions="unlimited",
        )
        paths = cache.local_files(request_spec)
        cache.import_files(
            key,
            (good,),
            complete=True,
            actual_cost=Decimal("0.10"),
            license_evidence="terms",
            conditions="unlimited",
        )
        assert cache.local_files(request_spec) == paths
        assert cache.job(key).actual_cost == Decimal("0.10")


def test_source_version_immutable_and_empty_response_explicit(
    request_spec: oc.Request,
    tmp_path: Path,
) -> None:
    with oc.OptionsCache(tmp_path / "cache", budget=Decimal("5")) as cache:
        key = finish(cache, request_spec, payload(tmp_path, b""))
        assert cache.missing(request_spec) == ()
        with pytest.raises(ValueError, match="immutable"):
            cache.import_files(
                key,
                (payload(tmp_path, b"correction"),),
                complete=True,
                actual_cost=Decimal("0.10"),
                license_evidence="terms",
                conditions="",
            )
        corrected = replace(request_spec, source_version="correction-1")
        finish(cache, corrected, payload(tmp_path, b"correction"))
        assert cache.local_files(request_spec)[0].read_bytes() == b""
        assert cache.local_files(corrected)[0].read_bytes() == b"correction"


def test_backup_restore_validates_hashes(
    request_spec: oc.Request,
    tmp_path: Path,
) -> None:
    backup = tmp_path / "backup"
    with oc.OptionsCache(tmp_path / "cache", budget=Decimal("5")) as cache:
        finish(cache, request_spec, payload(tmp_path))
        cache.backup(backup)
    oc.OptionsCache.restore(backup, tmp_path / "restored")
    with oc.OptionsCache(tmp_path / "restored", budget=Decimal("5")) as restored:
        assert restored.missing(request_spec) == ()
        assert restored.local_files(request_spec)[0].read_bytes() == b"raw precise vendor bytes"
    next((backup / "raw").rglob("*.raw")).write_bytes(b"corrupt")
    with pytest.raises(ValueError):
        oc.OptionsCache.restore(backup, tmp_path / "bad-restore")
    assert not (tmp_path / "bad-restore").exists()


def test_competing_writers_only_one_reserves(
    request_spec: oc.Request,
    tmp_path: Path,
) -> None:
    root = tmp_path / "cache"
    with oc.OptionsCache(root, budget=Decimal("5")):
        pass

    def contender(_: int) -> bool:
        with oc.OptionsCache(root, budget=Decimal("5")) as cache:
            try:
                reserve(cache, request_spec)
            except ValueError:
                return False
            return True

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(contender, range(2))) == [False, True]


@pytest.mark.parametrize("boundary", ["publish", "catalog"])
def test_crash_after_publish_or_before_catalog_commit_can_resume(
    request_spec: oc.Request,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
) -> None:
    root = tmp_path / "cache"
    raw = payload(tmp_path)
    real_replace = os.replace

    def interrupted_replace(src: str | Path, dst: str | Path) -> None:
        real_replace(src, dst)
        raise OSError("simulated process interruption after publish")

    with oc.OptionsCache(root, budget=Decimal("5")) as cache:
        key = reserve(cache, request_spec)
        cache.mark_submitted(key, "recover-existing-job")
        if boundary == "publish":
            monkeypatch.setattr(os, "replace", interrupted_replace)
        else:
            with sqlite3.connect(root / "catalog.sqlite") as db:
                db.execute("""CREATE TRIGGER interrupt BEFORE UPDATE OF state ON jobs
                    WHEN NEW.state = 'complete' BEGIN SELECT RAISE(ABORT, 'interrupted'); END""")
        with pytest.raises((OSError, sqlite3.DatabaseError)):
            cache.import_files(
                key,
                (raw,),
                complete=True,
                actual_cost=Decimal("0.10"),
                license_evidence="terms",
                conditions="unlimited",
            )
        assert cache.missing(request_spec) == (request_spec,)
    monkeypatch.undo()
    with sqlite3.connect(root / "catalog.sqlite") as db:
        db.execute("DROP TRIGGER IF EXISTS interrupt")
    with oc.OptionsCache(root, budget=Decimal("5")) as cache:
        cache.import_files(
            key,
            (raw,),
            complete=True,
            actual_cost=Decimal("0.10"),
            license_evidence="terms",
            conditions="unlimited",
        )
        assert cache.local_files(request_spec)[0].read_bytes() == raw.path.read_bytes()


def test_budget_comparison_never_rounds_away_small_cost(
    request_spec: oc.Request,
    tmp_path: Path,
) -> None:
    with oc.OptionsCache(tmp_path / "cache", budget=Decimal("0.10")) as cache:
        finish(cache, request_spec, payload(tmp_path))
        with localcontext() as context:
            context.prec = 2
            with pytest.raises(ValueError, match="budget"):
                reserve(cache, replace(request_spec, source_version="v2"), "0.00000001")


def test_actual_overrun_and_old_credit_receipt_fail_closed(
    request_spec: oc.Request,
    tmp_path: Path,
) -> None:
    with oc.OptionsCache(tmp_path / "cache", budget=Decimal("0.20")) as cache:
        old = credits(datetime.now(UTC))
        key = reserve(cache, request_spec)
        cache.mark_submitted(key, "overrun-job")
        cache.import_files(
            key,
            (payload(tmp_path),),
            complete=True,
            actual_cost=Decimal("0.25"),
            license_evidence="terms",
            conditions="unlimited",
        )
        assert cache.job(key).actual_cost == Decimal("0.25")
        with pytest.raises(ValueError, match="budget"):
            reserve(cache, replace(request_spec, source_version="v2"), "0.01")
    with oc.OptionsCache(tmp_path / "other", budget=Decimal("5")) as cache:
        finish(cache, request_spec, payload(tmp_path))
        with pytest.raises(ValueError, match="reconciled"):
            cache.reserve(replace(request_spec, source_version="v2"), Decimal("0.10"), old)


def test_backup_rejects_tampered_catalog_and_preserves_unknown_job(
    request_spec: oc.Request,
    tmp_path: Path,
) -> None:
    backup = tmp_path / "backup"
    with oc.OptionsCache(tmp_path / "cache", budget=Decimal("5")) as cache:
        key = reserve(cache, request_spec)
        cache.mark_submission_unknown(key)
        cache.backup(backup)
    oc.OptionsCache.restore(backup, tmp_path / "restored")
    with oc.OptionsCache(tmp_path / "restored", budget=Decimal("5")) as restored:
        assert restored.job(key).state == "uncertain"
        with pytest.raises(ValueError, match="unresolved"):
            reserve(restored, request_spec)
    with (backup / "catalog.sqlite").open("ab") as database:
        database.write(b"tampering")
    with pytest.raises(ValueError, match="integrity"):
        oc.OptionsCache.restore(backup, tmp_path / "bad")
    assert not (tmp_path / "bad").exists()


def test_verified_original_repairs_corruption_without_new_job(
    request_spec: oc.Request, tmp_path: Path
) -> None:
    raw = payload(tmp_path)
    with oc.OptionsCache(tmp_path / "cache", budget=Decimal("5")) as cache:
        key = finish(cache, request_spec, raw)
        cached = cache.local_files(request_spec)[0]
        cached.write_bytes(b"corrupted original")
        cache.import_files(
            key,
            (raw,),
            complete=True,
            actual_cost=Decimal("0.10"),
            license_evidence="terms",
            conditions="unlimited",
        )
        assert cache.local_files(request_spec)[0].read_bytes() == raw.path.read_bytes()
        quarantined = list(cached.parent.glob("*.corrupt-*"))
        assert len(quarantined) == 1
        assert quarantined[0].read_bytes() == b"corrupted original"
        assert cache.job(key).reserved_cost == Decimal("0.10")


def test_restore_refuses_unhashed_sqlite_sidecars(tmp_path: Path) -> None:
    root, backup = tmp_path / "cache", tmp_path / "backup"
    with oc.OptionsCache(root, budget=Decimal("5")) as cache:
        with sqlite3.connect(root / "catalog.sqlite") as db:
            db.execute("PRAGMA journal_mode=WAL")
        cache.backup(backup)
    # A sidecar may hold changes absent from the hashed main database.
    (backup / "catalog.sqlite-wal").write_bytes(b"unverified sidecar")
    with pytest.raises(ValueError, match="sidecar"):
        oc.OptionsCache.restore(backup, tmp_path / "restored")
    assert not (tmp_path / "restored").exists()


def test_reconciled_snapshot_deducts_imports_without_refreshing_age(request_spec, tmp_path):
    observed = datetime.now(UTC)
    evidence = replace(credits(observed, "0.15"), deduct_imports=True)
    with oc.OptionsCache(tmp_path / "cache", budget=Decimal("5")) as cache:
        finish(cache, request_spec, payload(tmp_path))
        later = replace(request_spec, symbols=("NEXT",))
        with pytest.raises(ValueError, match="insufficient"):
            cache.reserve(later, Decimal("0.06"), evidence)
        with pytest.raises(ValueError, match="fresh"):
            cache.reserve(later, Decimal("0.01"), evidence, now=observed + timedelta(minutes=6))
        cache.reserve(later, Decimal("0.05"), evidence)
