"""One-shot, free official-feed observation pilot; no signals, models or orders.

Feed publication dates are source assertions. First-seen time is when this
collector actually observed the exact content version, never a historical fill.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

VERSION = "news-observation-v1"
MAX_BYTES = 2 * 1024 * 1024
MAX_ITEMS = 500
Record = dict[str, Any]


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    host: str
    entity: str
    entity_status: str


SOURCES = (
    Source(
        "fed_all",
        "https://www.federalreserve.gov/feeds/press_all.xml",
        "www.federalreserve.gov",
        "Federal Reserve Board",
        "official_institution_source_not_security",
    ),
    Source(
        "fed_monetary",
        "https://www.federalreserve.gov/feeds/press_monetary.xml",
        "www.federalreserve.gov",
        "Federal Reserve Board",
        "official_institution_source_not_security",
    ),
    Source(
        "nvidia_releases",
        "https://nvidianews.nvidia.com/releases.xml",
        "nvidianews.nvidia.com",
        "NVIDIA Corporation",
        "official_issuer_source_subjects_unresolved",
    ),
)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode() + b"\n"


def stamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timezone-aware timestamp required")
    return value.astimezone(UTC).isoformat()


def parse_time(value: str) -> datetime | None:
    if not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (ValueError, TypeError, OverflowError):
            return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    try:
        return parsed.astimezone(UTC)
    except (OverflowError, ValueError):
        return None


def clean_text(value: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]*>", " ", value)).split())


def safe_url(value: str, source: Source) -> str | None:
    try:
        parts = urlsplit(value.strip())
        if (
            parts.scheme != "https"
            or parts.hostname != source.host
            or parts.username is not None
            or parts.password is not None
            or parts.port not in (None, 443)
        ):
            return None
    except ValueError:
        return None
    return urlunsplit(("https", source.host, parts.path, parts.query, ""))


def child_text(node: ET.Element, names: tuple[str, ...]) -> str:
    for name in names:
        for child in node:
            if child.tag.rsplit("}", 1)[-1] == name:
                return "".join(child.itertext()).strip()
    return ""


def item_link(node: ET.Element) -> str:
    for child in node:
        if (
            child.tag.rsplit("}", 1)[-1] == "link"
            and child.attrib.get("rel", "alternate") == "alternate"
        ):
            return child.attrib.get("href", "".join(child.itertext())).strip()
    return ""


def classify(title: str, source: Source) -> str:
    """Descriptive tags only; keywords do not measure surprise or sentiment."""
    lowered = title.lower()
    if source.name == "fed_monetary" or "federal open market committee" in lowered:
        return "monetary_policy"
    if "financial results" in lowered or "earnings" in lowered:
        return "issuer_earnings_mention"
    return "unclassified_release"


def version_hash(record: Record) -> str:
    return digest(
        json_bytes({key: record[key] for key in ("item_url", "title", "summary", "published_raw")})
    )


def normalize(
    payload: bytes,
    source: Source,
    retrieved_at: datetime,
    previous: dict[str, str] | None = None,
) -> list[Record]:
    retrieved = stamp(retrieved_at)
    if len(payload) > MAX_BYTES:
        raise ValueError("Feed exceeds byte ceiling")
    payload.decode("utf-8-sig")
    if b"\x00" in payload:
        raise ValueError("Only UTF-8 XML is accepted")
    if re.search(rb"<!\s*(?:DOCTYPE|ENTITY)\b", payload, re.IGNORECASE):
        raise ValueError("XML declarations/entities are not accepted")
    root = ET.fromstring(payload)
    if root.tag.rsplit("}", 1)[-1] not in ("rss", "feed", "RDF"):
        raise ValueError("Response is not an RSS/Atom feed")
    items = [node for node in root.iter() if node.tag.rsplit("}", 1)[-1] in ("item", "entry")]
    if len(items) > MAX_ITEMS:
        raise ValueError("Feed exceeds item ceiling")
    records = []
    for item in items:
        raw_link = item_link(item)
        url = safe_url(raw_link, source)
        published_raw = child_text(item, ("pubDate", "published", "date"))
        published = parse_time(published_raw)
        issues = []
        if url is None:
            issues.append("unsafe_or_missing_item_url")
        if published is None:
            issues.append("missing_invalid_or_naive_publication_time")
        elif published > retrieved_at:
            issues.append("publication_after_retrieval")
        record: Record = {
            "schema_version": VERSION,
            "source_id": source.name,
            "source_url": source.url,
            "source_item_id": child_text(item, ("guid", "id")),
            "item_url": url or raw_link,
            "title": clean_text(child_text(item, ("title",))),
            "summary": clean_text(child_text(item, ("description", "summary", "content"))),
            "published_raw": published_raw,
            "published_at": stamp(published) if published is not None else None,
            "retrieved_at": retrieved,
            "first_seen_at": retrieved,
            "publication_time_status": "source_assertion_not_independently_verified",
            "entity": source.entity,
            "entity_link_status": source.entity_status,
            "security_id": None,
            "classifier_version": "release-keywords-v1",
            "event_class": classify(child_text(item, ("title",)), source),
            "issues": issues,
        }
        record["event_id"] = digest(record["item_url"].encode())
        record["content_hash"] = version_hash(record)
        prior_seen = (previous or {}).get(record["content_hash"])
        if prior_seen is not None:
            first_seen = parse_time(prior_seen)
            if first_seen is None or first_seen > retrieved_at:
                raise ValueError("Previous first-seen time is invalid or in the future")
            record["first_seen_at"] = stamp(first_seen)
        records.append(record)
    return records


def as_of_reasons(record: Record, as_of: datetime) -> list[str]:
    """An observed record cannot be used before its own retrieval snapshot."""
    stamp(as_of)
    reasons = list(record["issues"])
    for key in ("published_at", "first_seen_at", "retrieved_at"):
        parsed = parse_time(record.get(key) or "")
        if parsed is None:
            reasons.append(f"{key}_unknown")
        elif parsed > as_of:
            reasons.append(f"{key}_after_as_of")
    return sorted(set(reasons))


def load_previous(directory: Path | None) -> tuple[dict[str, str], str | None]:
    if directory is None:
        return {}, None
    receipt = json.loads((directory / "receipt.json").read_bytes())
    payload = (directory / "observations.jsonl").read_bytes()
    if len(payload) > 10 * MAX_BYTES or digest(payload) != receipt["observations_sha256"]:
        raise ValueError("Previous observations have invalid size or hash")
    previous: dict[str, str] = {}
    for line in payload.splitlines():
        row = json.loads(line)
        if row["schema_version"] != VERSION or version_hash(row) != row["content_hash"]:
            raise ValueError("Previous observation version/hash mismatch")
        first = parse_time(row["first_seen_at"])
        retrieved = parse_time(row["retrieved_at"])
        if first is None or retrieved is None or first > retrieved:
            raise ValueError("Previous observation has invalid chronology")
        key = row["content_hash"]
        previous[key] = min(previous.get(key, stamp(first)), stamp(first))
    return previous, digest(payload)


def fetch(client: httpx.Client, source: Source) -> tuple[bytes, int]:
    """Exactly one GET; redirects/retries absent; streamed decoded byte bound."""
    with client.stream("GET", source.url, follow_redirects=False) as response:
        status = response.status_code
        if status != 200:
            return b"", status
        chunks = []
        length = 0
        for chunk in response.iter_bytes():
            length += len(chunk)
            if length > MAX_BYTES:
                raise ValueError("Response exceeds byte ceiling")
            chunks.append(chunk)
        return b"".join(chunks), status


def collect(
    destination: Path,
    client: httpx.Client,
    previous_directory: Path | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> Record:
    previous, previous_hash = load_previous(previous_directory)
    destination.mkdir(parents=True, exist_ok=False)
    started_at = stamp(now())
    records: list[Record] = []
    receipts: list[Record] = []
    for source in SOURCES:
        entry: Record = {"source_id": source.name, "source_url": source.url}
        try:
            payload, status = fetch(client, source)
            retrieved = now()
            entry.update(http_status=status, retrieved_at=stamp(retrieved))
            if status != 200:
                entry.update(status="http_error", normalized_rows=0)
            else:
                raw_name = f"{source.name}.xml"
                (destination / raw_name).write_bytes(payload)
                entry.update(raw_file=raw_name, raw_sha256=digest(payload), raw_bytes=len(payload))
                normalized = normalize(payload, source, retrieved, previous)
                records.extend(normalized)
                for row in normalized:
                    key = row["content_hash"]
                    previous[key] = min(
                        previous.get(key, row["first_seen_at"]), row["first_seen_at"]
                    )
                entry.update(status="ok", normalized_rows=len(normalized))
        except (httpx.HTTPError, ValueError, ET.ParseError) as exc:
            entry.update(status="fetch_or_parse_error", error_type=type(exc).__name__)
        receipts.append(entry)
    finished = now()
    body = b"".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True).encode() + b"\n" for row in records
    )
    (destination / "observations.jsonl").write_bytes(body)
    unique_versions = len({row["content_hash"] for row in records})
    receipt = {
        "schema_version": VERSION,
        "started_at": started_at,
        "finished_at": stamp(finished),
        "requested_feeds": len(SOURCES),
        "sources": receipts,
        "observations": len(records),
        "unique_events": len({row["event_id"] for row in records}),
        "unique_content_versions": unique_versions,
        "duplicate_content_rows": len(records) - unique_versions,
        "eligible_observations_at_finish": sum(not as_of_reasons(row, finished) for row in records),
        "issue_counts": dict(Counter(issue for row in records for issue in row["issues"])),
        "entity_link_status_counts": dict(Counter(row["entity_link_status"] for row in records)),
        "event_class_counts": dict(Counter(row["event_class"] for row in records)),
        "observations_sha256": digest(body),
        "previous_observations_sha256": previous_hash,
        "collector_sha256": digest(Path(__file__).read_bytes()),
        "model_calls": 0,
        "paid_data_calls": 0,
        "orders": 0,
        "pnl_calculated": False,
        "scope": "Current observation snapshot, not historical headline availability or causality.",
    }
    (destination / "receipt.json").write_bytes(json_bytes(receipt))
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New private/ignored directory")
    parser.add_argument(
        "--previous", type=Path, help="Prior immutable pilot directory, if available"
    )
    args = parser.parse_args()
    with httpx.Client(
        timeout=20,
        follow_redirects=False,
        headers={"User-Agent": "forecast-lab-news-research/1.0 (personal research)"},
    ) as client:
        receipt = collect(args.output, client, args.previous)
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
