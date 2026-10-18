"""The source notice only trusts complete, local, time-valid review evidence."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from streamlit.testing.v1 import AppTest


def _app(folder: Path) -> AppTest:
    return AppTest.from_string(
        "from pathlib import Path\n"
        "from kq.equities.vintage_panel import render_source_reconciliation\n"
        f"render_source_reconciliation(Path({str(folder)!r}))"
    ).run()


def _bar() -> dict:
    return {
        "session_date": "2026-09-28",
        "session": "reg",
        "synthetic": False,
        "open_price": "10",
        "high_price": "11",
        "low_price": "9",
        "close_price": "10",
        "volume": 100,
    }


def _publish(folder: Path, *, reviews: list[tuple[str, list[str]]] | None = None) -> dict:
    observed = (datetime.now(UTC) - timedelta(hours=1)).replace(microsecond=119000).isoformat()
    review_specs = reviews or [
        ("baseline", ["supplement"] * 7),
        ("parallel", ["supplement"] * 49 + ["volume_correction"] * 7),
        ("forward", ["supplement"] * 49 + ["volume_correction"] * 7),
    ]
    rows = []
    for lane, kinds in review_specs:
        relative = f"source-reconciliation/reviews/{lane}.json"
        path = folder / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        review = {
            "schema_version": 1,
            "policy": "finite_2026_09_28_source_vintage",
            "reviewed_at": observed,
            "entries": [
                {
                    "symbol": f"S{index:03d}",
                    "session_date": "2026-09-28",
                    "kind": kind,
                    "accepted_bar": _bar(),
                    "published_bar": _bar(),
                }
                for index, kind in enumerate(kinds)
            ],
        }
        raw = json.dumps(review).encode()
        path.write_bytes(raw)
        rows.append(
            {
                "lane": lane,
                "review_file": relative,
                "review_sha256": hashlib.sha256(raw).hexdigest(),
                "entry_count": len(kinds),
                "supplement_count": kinds.count("supplement"),
                "volume_correction_count": kinds.count("volume_correction"),
            }
        )
    report = {
        "schema_version": 1,
        "status": "validated",
        "kind": "manual_source_review",
        "captured_at": observed,
        "reviews": rows,
    }
    report_relative = "source-reconciliation/runs/test/report.json"
    path = folder / report_relative
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(report).encode()
    path.write_bytes(raw)
    (folder / "source-reconciliation.json").write_text(
        json.dumps(
            {"report_file": report_relative, "report_sha256": hashlib.sha256(raw).hexdigest()}
        ),
        encoding="utf-8",
    )
    return report


def _replace_report(folder: Path, report: dict) -> None:
    pointer_path = folder / "source-reconciliation.json"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    raw = json.dumps(report).encode()
    (folder / pointer["report_file"]).write_bytes(raw)
    pointer["report_sha256"] = hashlib.sha256(raw).hexdigest()
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")


def test_missing_report_is_silent_and_does_not_write(tmp_path: Path) -> None:
    app = _app(tmp_path)
    assert not app.exception
    assert not app.error
    assert not app.caption
    assert not list(tmp_path.iterdir())


def test_valid_review_discloses_per_lane_counts_and_limits(tmp_path: Path) -> None:
    _publish(tmp_path)
    before = sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*"))
    app = _app(tmp_path)
    after = sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*"))
    assert not app.exception
    assert not app.error
    assert before == after
    shown = " ".join(item.value for item in app.caption)
    assert "September 28" in shown
    assert "daily bars" in shown
    assert "scheduled" in shown
    assert "profit" in shown
    assert "baseline: 7" in shown
    assert "parallel: 56" in shown
    assert "forward: 56" in shown
    counts = next(
        item.value for item in app.caption if "Reviewed differences by book" in item.value
    )
    assert "119" not in counts


def test_report_digest_tamper_is_error(tmp_path: Path) -> None:
    report = _publish(tmp_path)
    report["status"] = "failed"
    (tmp_path / "source-reconciliation/runs/test/report.json").write_text(
        json.dumps(report), encoding="utf-8"
    )
    app = _app(tmp_path)
    assert not app.exception
    assert app.error
    assert not app.caption


def test_escaping_report_path_is_error(tmp_path: Path) -> None:
    _publish(tmp_path)
    pointer = tmp_path / "source-reconciliation.json"
    row = json.loads(pointer.read_text(encoding="utf-8"))
    row["report_file"] = "../outside.json"
    pointer.write_text(json.dumps(row), encoding="utf-8")
    app = _app(tmp_path)
    assert not app.exception
    assert app.error
    assert not app.caption


def test_review_digest_tamper_and_claimed_counts_are_errors(tmp_path: Path) -> None:
    report = _publish(tmp_path)
    review = tmp_path / report["reviews"][0]["review_file"]
    review.write_text("{}", encoding="utf-8")
    assert _app(tmp_path).error
    _publish(tmp_path)
    report["reviews"][0]["entry_count"] = 8
    _replace_report(tmp_path, report)
    assert _app(tmp_path).error


def test_future_and_naive_review_times_are_errors(tmp_path: Path) -> None:
    report = _publish(tmp_path)
    report["captured_at"] = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    _replace_report(tmp_path, report)
    assert _app(tmp_path).error
    report = _publish(tmp_path)
    review_row = report["reviews"][0]
    review_path = tmp_path / review_row["review_file"]
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["reviewed_at"] = datetime.now(UTC).replace(tzinfo=None).isoformat()
    raw = json.dumps(review).encode()
    review_path.write_bytes(raw)
    review_row["review_sha256"] = hashlib.sha256(raw).hexdigest()
    _replace_report(tmp_path, report)
    assert _app(tmp_path).error


def test_other_session_cannot_be_presented_as_september_review(tmp_path: Path) -> None:
    report = _publish(tmp_path)
    review_row = report["reviews"][0]
    review_path = tmp_path / review_row["review_file"]
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["entries"][0]["session_date"] = "2026-09-29"
    raw = json.dumps(review).encode()
    review_path.write_bytes(raw)
    review_row["review_sha256"] = hashlib.sha256(raw).hexdigest()
    _replace_report(tmp_path, report)
    assert _app(tmp_path).error


def test_review_without_preserved_primary_bar_is_error(tmp_path: Path) -> None:
    report = _publish(tmp_path)
    review_row = report["reviews"][0]
    review_path = tmp_path / review_row["review_file"]
    review = json.loads(review_path.read_text(encoding="utf-8"))
    del review["entries"][0]["published_bar"]
    raw = json.dumps(review).encode()
    review_path.write_bytes(raw)
    review_row["review_sha256"] = hashlib.sha256(raw).hexdigest()
    _replace_report(tmp_path, report)
    assert _app(tmp_path).error
