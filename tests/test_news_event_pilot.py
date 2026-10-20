"""Artificial feed fixtures and mocked HTTP, not historical trading tests."""

import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

SPEC = importlib.util.spec_from_file_location(
    "news_event_pilot", Path(__file__).parents[1] / "scripts" / "news_event_pilot.py"
)
assert SPEC is not None and SPEC.loader is not None
pilot = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pilot
SPEC.loader.exec_module(pilot)
NOW = datetime(2026, 10, 20, 12, tzinfo=UTC)


def rss(title="Release", date="Mon, 19 Oct 2026 14:00:00 GMT", link=None):
    link = link or "https://www.federalreserve.gov/newsevents/pressreleases/test.htm"
    return (
        f"<rss><channel><item><title>{title}</title><link>{link}</link>"
        f"<pubDate>{date}</pubDate><description>Official statement</description>"
        "</item></channel></rss>"
    ).encode()


def test_publication_is_not_first_observation():
    row = pilot.normalize(rss(), pilot.SOURCES[0], NOW)[0]
    assert row["published_at"] == "2026-10-19T14:00:00+00:00"
    assert row["first_seen_at"] == NOW.isoformat()
    assert row["retrieved_at"] == NOW.isoformat()
    assert pilot.as_of_reasons(row, NOW) == []
    assert pilot.as_of_reasons(row, NOW - timedelta(days=1)) == [
        "first_seen_at_after_as_of",
        "published_at_after_as_of",
        "retrieved_at_after_as_of",
    ]
    assert row["security_id"] is None
    assert row["entity_link_status"] == "official_institution_source_not_security"


@pytest.mark.parametrize(
    "date",
    [
        "",
        "yesterday",
        "2026-10-19T14:00:00",
        "19 Oct 2026 14:00",
        "0001-01-01T00:00:00+01:00",
        "9999-12-31T23:59:59-01:00",
    ],
)
def test_no_invented_publication_time(date):
    row = pilot.normalize(rss(date=date), pilot.SOURCES[0], NOW)[0]
    assert row["published_at"] is None
    assert "published_at_unknown" in pilot.as_of_reasons(row, NOW)


def test_offset_and_future_publication():
    row = pilot.normalize(rss(date="2026-10-20T06:00:00-07:00"), pilot.SOURCES[0], NOW)[0]
    assert row["published_at"] == "2026-10-20T13:00:00+00:00"
    assert "publication_after_retrieval" in pilot.as_of_reasons(row, NOW)


def test_revised_content_starts_new_version():
    original = pilot.normalize(rss(), pilot.SOURCES[0], NOW)[0]
    previous = {original["content_hash"]: original["first_seen_at"]}
    later = NOW + timedelta(days=1)
    same = pilot.normalize(rss(), pilot.SOURCES[0], later, previous)[0]
    changed = pilot.normalize(rss(title="Revised"), pilot.SOURCES[0], later, previous)[0]
    assert same["first_seen_at"] == original["first_seen_at"]
    assert same["retrieved_at"] == later.isoformat()
    assert "retrieved_at_after_as_of" in pilot.as_of_reasons(same, NOW)
    assert changed["event_id"] == original["event_id"]
    assert changed["content_hash"] != original["content_hash"]
    assert changed["first_seen_at"] == later.isoformat()


def test_cross_feed_exact_duplicates_share_hash():
    first = pilot.normalize(rss(), pilot.SOURCES[0], NOW)[0]
    second = pilot.normalize(rss(), pilot.SOURCES[1], NOW)[0]
    assert first["content_hash"] == second["content_hash"]
    assert second["event_class"] == "monetary_policy"


@pytest.mark.parametrize(
    "link",
    [
        "http://www.federalreserve.gov/test",
        "https://www.federalreserve.gov.evil.example/test",
        "https://user:password@www.federalreserve.gov/test",
        "https://www.federalreserve.gov:8443/test",
        "file:///some/path",
    ],
)
def test_untrusted_links_not_eligible(link):
    row = pilot.normalize(rss(link=link), pilot.SOURCES[0], NOW)[0]
    assert "unsafe_or_missing_item_url" in pilot.as_of_reasons(row, NOW)


def test_atom_updated_does_not_replace_unknown_publication():
    payload = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry>
      <id>id1</id><title>Event</title><updated>2026-10-19T14:00:00Z</updated>
      <link href="https://www.federalreserve.gov/event"/>
      </entry></feed>"""
    row = pilot.normalize(payload, pilot.SOURCES[0], NOW)[0]
    assert row["source_item_id"] == "id1"
    assert row["published_at"] is None


@pytest.mark.parametrize(
    "payload",
    [
        b'<!DOCTYPE rss [<!ENTITY example "unsafe">]><rss/>',
        b"x" * (pilot.MAX_BYTES + 1),
        b"<html>Not a feed</html>",
        b"<rss>" + b"<item/>" * (pilot.MAX_ITEMS + 1) + b"</rss>",
    ],
    ids=["entity", "bytes", "html", "items"],
)
def test_parser_bounds(payload):
    with pytest.raises(ValueError):
        pilot.normalize(payload, pilot.SOURCES[0], NOW)


def test_non_feed_root_rejected_even_with_valid_item():
    payload = rss().replace(b"<rss>", b"<html>").replace(b"</rss>", b"</html>")
    with pytest.raises(ValueError, match="not an RSS/Atom feed"):
        pilot.normalize(payload, pilot.SOURCES[0], NOW)


def test_overflowing_publication_retains_observations_and_receipt(tmp_path):
    payload = rss(date="0001-01-01T00:00:00+01:00")
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=payload))
    ) as client:
        receipt = pilot.collect(tmp_path / "overflow", client, now=lambda: NOW)
    assert receipt["observations"] == 3
    assert receipt["eligible_observations_at_finish"] == 0
    assert receipt["issue_counts"]["missing_invalid_or_naive_publication_time"] == 3
    assert all(source["status"] == "ok" for source in receipt["sources"])
    saved = json.loads((tmp_path / "overflow" / "receipt.json").read_bytes())
    assert saved == receipt


def test_collect_exactly_three_gets_dedup_and_retains_http_failure(tmp_path):
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.host == "nvidianews.nvidia.com":
            return httpx.Response(302, headers={"Location": "https://untrusted.example/"})
        return httpx.Response(200, content=rss())

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        receipt = pilot.collect(tmp_path / "snapshot", client, now=lambda: NOW)
    assert len(requests) == 3
    assert all(request.method == "GET" for request in requests)
    assert receipt["observations"] == 2
    assert receipt["unique_events"] == 1
    assert receipt["duplicate_content_rows"] == 1
    assert receipt["eligible_observations_at_finish"] == 2
    assert receipt["sources"][-1]["http_status"] == 302
    assert receipt["sources"][-1]["status"] == "http_error"
    assert receipt["model_calls"] == receipt["paid_data_calls"] == receipt["orders"] == 0
    assert receipt["pnl_calculated"] is False
    payload = (tmp_path / "snapshot" / "observations.jsonl").read_bytes()
    assert pilot.digest(payload) == receipt["observations_sha256"]
    previous, hashed = pilot.load_previous(tmp_path / "snapshot")
    assert len(previous) == 1 and hashed == receipt["observations_sha256"]


def test_existing_directory_refused_before_network(tmp_path):
    def handler(_request):
        pytest.fail("Existing output directory must fail before request")

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(FileExistsError),
    ):
        pilot.collect(tmp_path, client)


def test_previous_hash_and_chronology_are_checked(tmp_path):
    row = pilot.normalize(rss(), pilot.SOURCES[0], NOW)[0]
    payload = json.dumps(row).encode() + b"\n"
    (tmp_path / "observations.jsonl").write_bytes(payload)
    receipt = {"observations_sha256": "wrong"}
    (tmp_path / "receipt.json").write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="hash"):
        pilot.load_previous(tmp_path)
    row["first_seen_at"] = (NOW + timedelta(days=1)).isoformat()
    payload = json.dumps(row).encode() + b"\n"
    (tmp_path / "observations.jsonl").write_bytes(payload)
    (tmp_path / "receipt.json").write_text(
        json.dumps({"observations_sha256": pilot.digest(payload)})
    )
    with pytest.raises(ValueError, match="chronology"):
        pilot.load_previous(tmp_path)


def test_feed_payload_too_large_in_transport(tmp_path):
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=b"x" * (pilot.MAX_BYTES + 1))
        )
    ) as client:
        receipt = pilot.collect(tmp_path / "large", client, now=lambda: NOW)
    assert receipt["observations"] == 0
    assert all(source["status"] == "fetch_or_parse_error" for source in receipt["sources"])
