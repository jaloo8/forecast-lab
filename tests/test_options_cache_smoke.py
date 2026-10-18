from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

import pytest

from kq.equities.options_cache import CreditSnapshot, OptionsCache, RawFile, Request


def test_offline_acquisition_replay_and_restore(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    request = Request(
        dataset="OPRA.PILLAR",
        schema="cmbp-1",
        symbols=("SPY C",),
        start=now - timedelta(days=2),
        end=now - timedelta(days=1),
        stype_in="raw_symbol",
        stype_out="instrument_id",
        encoding="dbn",
        protocol_version="v0",
        normalization_version="raw",
        source_version="original",
    )
    source = tmp_path / "source"
    source.write_bytes(b"independently verified sample")
    raw = RawFile(source, source.stat().st_size, sha256(source.read_bytes()).hexdigest())
    with OptionsCache(tmp_path / "cache", budget=Decimal("5")) as cache:
        key = cache.reserve(
            request,
            Decimal("0.10"),
            CreditSnapshot(Decimal("125"), now, now + timedelta(days=1), True),
        )
        cache.mark_submission_unknown(key)
        with pytest.raises(ValueError, match="unresolved"):
            cache.reserve(
                request,
                Decimal("0.10"),
                CreditSnapshot(Decimal("125"), now, now + timedelta(days=1), True),
            )
        cache.mark_submitted(key, "already-existing-vendor-job")
        cache.import_files(
            key,
            (raw,),
            complete=True,
            actual_cost=Decimal("0.10"),
            license_evidence="verified test terms",
            conditions="complete test payload",
        )
        assert cache.missing(request) == ()
        assert cache.local_files(request)[0].read_bytes() == source.read_bytes()
        cache.backup(tmp_path / "backup")
    OptionsCache.restore(tmp_path / "backup", tmp_path / "restored")
    with OptionsCache(tmp_path / "restored", budget=Decimal("5")) as cache:
        assert cache.job(key).job_id == "already-existing-vendor-job"
        assert cache.local_files(request)[0].read_bytes() == source.read_bytes()
