"""Cache publication must retain integrity on long native Windows paths."""

import hashlib
import json
from pathlib import Path

import pytest

from kq.equities._options_cache_io import RawFile, manifest_files, publish


@pytest.mark.parametrize("parent_length", [230, 300])
def test_long_path_publish_retry_and_corrupt_blob_recovery(
    tmp_path: Path, parent_length: int
) -> None:
    content = b"independently retained vendor bytes"
    source = tmp_path / "vendor.raw"
    source.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    raw = RawFile(source, len(content), digest)
    directory = tmp_path / "raw"
    while len(str(directory)) < parent_length:
        directory /= "nested-cache-segment"
    target = directory / (digest + ".raw")
    assert len(str(target)) > 260

    publish(raw, target)
    RawFile(target, len(content), digest).verify()
    manifest = json.dumps(
        [{"path": target.relative_to(tmp_path).as_posix(), "size": len(content), "sha256": digest}]
    )
    # Consumers get an ordinary usable Path, including when Windows needs its
    # extended-length spelling. The catalog keeps the portable relative path.
    target = manifest_files(tmp_path, manifest)[0].path
    directory = target.parent
    first_identity = target.stat().st_ino
    publish(raw, target)
    assert target.stat().st_ino == first_identity
    assert not list(directory.glob("*.corrupt-*"))

    damaged = b"damaged cached payload"
    target.write_bytes(damaged)
    publish(raw, target)
    assert target.read_bytes() == source.read_bytes() == content
    quarantined = list(directory.glob("*.corrupt-*"))
    assert len(quarantined) == 1
    assert quarantined[0].read_bytes() == damaged
    assert not list(directory.glob(".import-*"))
