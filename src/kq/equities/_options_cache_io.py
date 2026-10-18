"""Value objects and local file integrity primitives for the options cache."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import uuid
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path


def utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("explicit timezone required")
    return value.astimezone(UTC)


def money(value: Decimal) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise ValueError("finite nonnegative Decimal required")
    return value


@dataclass(frozen=True)
class Request:
    """Explicit symbols and half-open UTC coverage; versions never mix."""

    dataset: str
    schema: str
    symbols: tuple[str, ...]
    start: datetime
    end: datetime
    stype_in: str
    stype_out: str
    encoding: str
    protocol_version: str
    normalization_version: str
    source_version: str

    def __post_init__(self) -> None:
        for value in (
            self.dataset,
            self.schema,
            self.stype_in,
            self.stype_out,
            self.encoding,
            self.protocol_version,
            self.normalization_version,
            self.source_version,
        ):
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", value) or value in {".", ".."}:
                raise ValueError("explicit request dimensions required")
        if (
            not self.symbols
            or isinstance(self.symbols, str)
            or any(
                not symbol.strip()
                or symbol != symbol.strip()
                or symbol.upper() == "ALL_SYMBOLS"
                or any(char in symbol for char in "*?[]\n\r\x00")
                for symbol in self.symbols
            )
        ):
            raise ValueError("explicit bounded symbols required")
        object.__setattr__(self, "symbols", tuple(sorted(set(self.symbols))))
        object.__setattr__(self, "start", utc(self.start))
        object.__setattr__(self, "end", utc(self.end))
        if self.start >= self.end:
            raise ValueError("nonempty bounded time interval required")

    @property
    def canonical(self) -> str:
        values = asdict(self)
        values.update(start=self.start.isoformat(), end=self.end.isoformat())
        return json.dumps(values, sort_keys=True, separators=(",", ":"))

    @property
    def key(self) -> str:
        return hashlib.sha256(self.canonical.encode()).hexdigest()

    @property
    def dimensions(self) -> str:
        values = json.loads(self.canonical)
        for name in ("symbols", "start", "end"):
            del values[name]
        return json.dumps(values, sort_keys=True)

    @classmethod
    def decode(cls, canonical: str) -> Request:
        values = json.loads(canonical)
        values["start"] = datetime.fromisoformat(values["start"])
        values["end"] = datetime.fromisoformat(values["end"])
        values["symbols"] = tuple(values["symbols"])
        return cls(**values)


@dataclass(frozen=True)
class CreditSnapshot:
    """Caller-verified account evidence, never a balance fetched by this cache."""

    available: Decimal | None
    observed_at: datetime
    expires_at: datetime
    verified: bool

    def validate(self, cost: Decimal, now: datetime) -> None:
        age = utc(now) - utc(self.observed_at)
        if (
            self.verified is not True
            or self.available is None
            or not timedelta(0) <= age <= timedelta(minutes=5)
            or utc(self.expires_at) <= utc(now)
        ):
            raise ValueError("fresh verified unexpired credits required")
        if money(self.available) < cost:
            raise ValueError("insufficient credits")


@dataclass(frozen=True)
class RawFile:
    """Supplied expected byte size and SHA-256, independent of the local payload."""

    path: Path
    size: int
    sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.size) is not int
            or self.size < 0
            or not re.fullmatch("[0-9a-f]{64}", self.sha256)
        ):
            raise ValueError("valid size and SHA-256 required")

    def verify(self) -> None:
        try:
            with self.path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
                size = stream.tell()
            if size != self.size or digest != self.sha256:
                raise ValueError("raw file integrity failure")
        except OSError:
            raise ValueError("raw file unavailable") from None


@dataclass(frozen=True)
class Job:
    request: Request
    state: str
    job_id: str | None
    reserved_cost: Decimal
    actual_cost: Decimal | None


def publish(raw: RawFile, target: Path) -> None:
    """A crash can leave an orphan blob, but never a partially published blob."""
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".import-", dir=target.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as output, raw.path.open("rb") as source:
            shutil.copyfileobj(source, output)
            output.flush()
            os.fsync(output.fileno())
        RawFile(temporary, raw.size, raw.sha256).verify()
        if target.exists():
            try:
                RawFile(target, raw.size, raw.sha256).verify()
                return
            except ValueError:
                os.replace(target, target.with_name(target.name + ".corrupt-" + uuid.uuid4().hex))
        if not target.exists():
            os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def manifest_files(root: Path, manifest: str) -> tuple[RawFile, ...]:
    files = []
    for item in json.loads(manifest):
        path = root / item["path"]
        if not path.resolve().is_relative_to((root / "raw").resolve()):
            raise ValueError("invalid raw path")
        files.append(RawFile(path, item["size"], item["sha256"]))
    if not files:
        raise ValueError("empty file manifest")
    return tuple(files)


def copy_snapshot(source: Path, destination: Path, *, restore: bool) -> None:
    """Publish a checked SQLite snapshot and its blobs to a new directory only."""
    if destination.exists() or destination.resolve().is_relative_to(source.resolve()):
        raise ValueError("backup/restore requires a new separate directory")
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".snapshot-", dir=destination.parent))
    try:
        database = stage / "catalog.sqlite"
        if restore:
            if any(
                (source / ("catalog.sqlite" + suffix)).exists()
                for suffix in ("-wal", "-shm", "-journal")
            ):
                raise ValueError("snapshot contains unverified SQLite sidecar")
            expected = (source / "catalog.sha256").read_text(encoding="ascii").strip()
            publish(
                RawFile(
                    source / "catalog.sqlite", (source / "catalog.sqlite").stat().st_size, expected
                ),
                database,
            )
        else:
            with (
                closing(
                    sqlite3.connect((source / "catalog.sqlite").as_uri() + "?mode=ro", uri=True)
                ) as src,
                closing(sqlite3.connect(database)) as dst,
            ):
                src.backup(dst)
        with closing(sqlite3.connect(database)) as dst:
            dst.execute("PRAGMA journal_mode=DELETE")
            if dst.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise ValueError("catalog integrity failure")
            for (manifest,) in dst.execute("SELECT manifest FROM jobs WHERE state='complete'"):
                for raw in manifest_files(source, manifest):
                    target = stage / raw.path.relative_to(source)
                    publish(raw, target)
                    RawFile(target, raw.size, raw.sha256).verify()
        with database.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        (stage / "catalog.sha256").write_text(digest, encoding="ascii")
        os.replace(stage, destination)
    finally:
        if stage.exists():
            if stage.resolve().parent != destination.parent.resolve():
                raise ValueError("snapshot cleanup escaped its staging directory")
            shutil.rmtree(stage)
