"""Offline, integrity-checked options payloads and a durable acquisition ledger.

No API client, submit method, downloader, or network fallback. Reserve locally,
record uncertainty BEFORE any external submission, reconcile its job ID, then
import the existing job's complete files. Credit evidence is supplied by the
caller; reservations cannot guarantee a vendor's eventual charge. Source files
are opaque: this layer asserts byte integrity and caller-declared completeness,
not record semantics, future-quote joins, license validity, or absence of trades.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from types import TracebackType

from kq.equities._options_cache_io import (
    CreditSnapshot,
    Job,
    RawFile,
    Request,
    copy_snapshot,
    manifest_files,
    money,
    publish,
    utc,
)

__all__ = ["CreditSnapshot", "Job", "OptionsCache", "RawFile", "Request"]


class OptionsCache:
    """One unresolved acquisition at a time, serialized by SQLite BEGIN IMMEDIATE.

    Budget is fixed on first open and cumulative across billing periods. Charges
    retain at least their reservation, even if actual usage proves lower. The
    caller must reconcile all outstanding usage before supplying fresh credits.
    Each connection belongs to its opening thread; use separate instances across
    threads/processes. Store this directory outside disposable source checkouts.
    """

    def __init__(self, root: Path, *, budget: Decimal) -> None:
        money(budget)
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.root / "catalog.sqlite", isolation_level=None, timeout=10)
        self._db.row_factory = sqlite3.Row
        try:
            with self._write():
                self._db.execute(
                    "CREATE TABLE IF NOT EXISTS policy (id INTEGER PRIMARY KEY, budget TEXT)"
                )
                self._db.execute("INSERT OR IGNORE INTO policy VALUES (1, ?)", (str(budget),))
                if (
                    Decimal(self._db.execute("SELECT budget FROM policy WHERE id=1").fetchone()[0])
                    != budget
                ):
                    raise ValueError("persistent budget cannot be reset")
                self._db.execute("""CREATE TABLE IF NOT EXISTS jobs (
                    key TEXT PRIMARY KEY, request TEXT NOT NULL, state TEXT NOT NULL,
                    job_id TEXT UNIQUE, reserved TEXT NOT NULL, actual TEXT,
                    credit TEXT NOT NULL, created TEXT NOT NULL, completed TEXT,
                    manifest TEXT, license TEXT, conditions TEXT)""")
        except BaseException:
            self._db.close()
            raise

    def __enter__(self) -> OptionsCache:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._db.close()

    @contextmanager
    def _write(self) -> Iterator[None]:
        self._db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self._db.commit()
        except BaseException:
            self._db.rollback()
            raise

    def _row(self, key: str) -> sqlite3.Row:
        row = self._db.execute("SELECT * FROM jobs WHERE key=?", (key,)).fetchone()
        if row is None:
            raise ValueError("unknown reservation")
        return row  # type: ignore[no-any-return]

    def job(self, key: str) -> Job:
        """Return durable resume metadata without contacting the vendor."""
        row = self._row(key)
        return Job(
            Request.decode(row["request"]),
            row["state"],
            row["job_id"],
            Decimal(row["reserved"]),
            Decimal(row["actual"]) if row["actual"] else None,
        )

    def _coverage(self, request: Request) -> list[tuple[Request, tuple[RawFile, ...]]]:
        result = []
        for row in self._db.execute("SELECT request, manifest FROM jobs WHERE state='complete'"):
            candidate = Request.decode(row["request"])
            if (
                candidate.dimensions != request.dimensions
                or candidate.end <= request.start
                or candidate.start >= request.end
                or not set(candidate.symbols) & set(request.symbols)
            ):
                continue
            try:
                files = manifest_files(self.root, row["manifest"])
                for raw in files:
                    raw.verify()
            except (ValueError, OSError):
                continue
            result.append((candidate, files))
        return result

    @staticmethod
    def _gaps(
        request: Request, coverage: list[tuple[Request, tuple[RawFile, ...]]]
    ) -> tuple[Request, ...]:
        gaps: dict[tuple[datetime, datetime], list[str]] = {}
        for symbol in request.symbols:
            cursor = request.start
            intervals = sorted(
                (max(request.start, item.start), min(request.end, item.end))
                for item, _ in coverage
                if symbol in item.symbols
            )
            for start, end in intervals:
                if start > cursor:
                    gaps.setdefault((cursor, start), []).append(symbol)
                cursor = max(cursor, end)
            if cursor < request.end:
                gaps.setdefault((cursor, request.end), []).append(symbol)
        return tuple(
            replace(request, symbols=tuple(symbols), start=start, end=end)
            for (start, end), symbols in sorted(gaps.items())
        )

    def missing(self, request: Request) -> tuple[Request, ...]:
        """Verified uncovered intervals, grouped by identical per-symbol gaps."""
        return self._gaps(request, self._coverage(request))

    def local_files(self, request: Request) -> tuple[Path, ...]:
        """Verified raw sources; the decoder must filter rows to the requested subset."""
        coverage = self._coverage(request)
        if self._gaps(request, coverage):
            raise ValueError("incomplete local coverage")
        return tuple(sorted({raw.path for _, files in coverage for raw in files}))

    def reserve(
        self,
        request: Request,
        cost: Decimal,
        credits: CreditSnapshot,
        *,
        now: datetime | None = None,
        ceiling: Decimal | None = None,
    ) -> str:
        """Persist a conservative cost ceiling; never perform external submission."""
        cost = money(cost)
        if ceiling is not None:
            money(ceiling)
        now = utc(now or datetime.now(UTC))
        credits.validate(cost, now)
        with self._write():
            rows = self._db.execute("SELECT * FROM jobs").fetchall()
            if any(row["state"] not in {"complete", "abandoned"} for row in rows):
                raise ValueError("unresolved acquisition blocks reservation")
            if any(row["key"] == request.key for row in rows):
                raise ValueError("duplicate reservation; resume the existing job")
            if self.missing(request) != (request,):
                raise ValueError("coverage already acquired; reserve only uncovered intervals")
            total = sum(
                (Fraction(max(Decimal(row["reserved"]), Decimal(row["actual"]))) for row in rows),
                Fraction(cost),
            )
            budget = Decimal(self._db.execute("SELECT budget FROM policy WHERE id=1").fetchone()[0])
            if ceiling is not None:
                budget = min(budget, ceiling)
            if total > Fraction(budget):
                raise ValueError("cumulative budget exhausted")
            debited = sum(
                (
                    Decimal(row["actual"])
                    for row in rows
                    if datetime.fromisoformat(row["completed"]) > utc(credits.observed_at)
                ),
                Decimal("0"),
            )
            if credits.deduct_imports:
                assert credits.available is not None
                if credits.available - debited < cost:
                    raise ValueError("insufficient credits after subsequent imports")
            elif rows and utc(credits.observed_at) < max(
                datetime.fromisoformat(row["completed"]) for row in rows
            ):
                raise ValueError("credits must be reconciled after the previous import")
            receipt = json.dumps(
                {
                    "available": str(credits.available),
                    "verified": credits.verified,
                    "observed_at": utc(credits.observed_at).isoformat(),
                    "expires_at": utc(credits.expires_at).isoformat(),
                    "deduct_imports": credits.deduct_imports,
                    "subsequent_import_cost": str(debited),
                }
            )
            self._db.execute(
                """INSERT INTO jobs
                (key, request, state, reserved, credit, created)
                VALUES (?, ?, 'reserved', ?, ?, ?)""",
                (request.key, request.canonical, str(cost), receipt, now.isoformat()),
            )
        return request.key

    def abandon(self, key: str, *, reason: str) -> None:
        """Explicit operator write-off of an interrupted stream; never erase its charge."""
        with self._write():
            row = self._row(key)
            if row["state"] != "uncertain" or row["job_id"] is not None or not reason.strip():
                raise ValueError("Only a documented uncertain stream may be abandoned")
            self._db.execute(
                "UPDATE jobs SET state='abandoned', actual=reserved, completed=?, conditions=? "
                "WHERE key=?",
                (datetime.now(UTC).isoformat(), reason, key),
            )

    def mark_submission_unknown(self, key: str) -> None:
        """Persist BEFORE an external submit attempt; uncertainty never expires automatically."""
        with self._write():
            row = self._row(key)
            if row["state"] not in {"reserved", "uncertain"}:
                raise ValueError("submission already reconciled")
            self._db.execute("UPDATE jobs SET state='uncertain' WHERE key=?", (key,))

    def mark_submitted(self, key: str, job_id: str) -> None:
        """Record an externally obtained/reconciled job ID, without calling any API."""
        if not job_id.strip():
            raise ValueError("explicit external job ID required")
        with self._write():
            row = self._row(key)
            if row["job_id"] == job_id:
                return
            if row["job_id"] is not None or row["state"] not in {"reserved", "uncertain"}:
                raise ValueError("job ID is immutable")
            self._db.execute(
                "UPDATE jobs SET state='submitted', job_id=? WHERE key=?", (job_id, key)
            )

    def import_files(
        self,
        key: str,
        files: tuple[RawFile, ...],
        *,
        complete: bool,
        actual_cost: Decimal,
        license_evidence: str,
        conditions: str,
    ) -> None:
        """Atomically catalog an entire job; retry the same job after any failed import.

        The complete manifest must come from independent delivery evidence, not
        hashes computed merely to bless a possibly truncated downloaded file.
        Zero-record responses need an explicit (possibly empty) payload file.
        """
        money(actual_cost)
        if complete is not True or not files or not license_evidence.strip():
            raise ValueError("explicit complete files and license evidence required")
        with self._write():
            job = self.job(key)
            if job.job_id is None:
                raise ValueError("known external job required")
            request = job.request
            directory = Path("raw", request.dataset, request.schema, str(request.start.date()), key)
            manifest = json.dumps(
                sorted(
                    [
                        {
                            "path": (directory / (raw.sha256 + ".raw")).as_posix(),
                            "size": raw.size,
                            "sha256": raw.sha256,
                        }
                        for raw in files
                    ],
                    key=lambda item: str(item["path"]),
                ),
                sort_keys=True,
            )
            row = self._row(key)
            if job.state == "complete" and (
                row["manifest"] != manifest or job.actual_cost != actual_cost
            ):
                raise ValueError("completed source version is immutable")
            for raw in files:
                publish(raw, self.root / directory / (raw.sha256 + ".raw"))
            if job.state == "complete":
                return
            self._db.execute(
                """UPDATE jobs SET state='complete', actual=?, manifest=?,
                completed=?, license=?, conditions=? WHERE key=?""",
                (
                    str(actual_cost),
                    manifest,
                    datetime.now(UTC).isoformat(),
                    license_evidence,
                    conditions,
                    key,
                ),
            )

    def backup(self, destination: Path) -> None:
        """Create a consistent local SQLite snapshot and verified raw copies."""
        copy_snapshot(self.root, destination.resolve(), restore=False)

    @staticmethod
    def restore(source: Path, destination: Path) -> None:
        """Verify the catalog hash and all complete payloads before publishing."""
        copy_snapshot(source.resolve(), destination.resolve(), restore=True)
