"""The price-source command creates local, immutable captures only."""

from __future__ import annotations

import hashlib
import json
import runpy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest


def _snapshot() -> dict[str, Any]:
    bars = []
    for symbol in ("AAA", "SPY"):
        series = []
        for index, day in enumerate(pd.bdate_range(end="2026-09-28", periods=140)):
            price = 100 + index / 10 if symbol == "AAA" else 100
            series.append(
                dict(
                    begins_at=day.isoformat() + "Z",
                    session="reg",
                    interpolated=False,
                    open_price=str(price),
                    high_price=str(price),
                    low_price=str(price),
                    close_price=str(price),
                    volume=1_000_000,
                )
            )
        bars.append(dict(symbol=symbol, interval="day", bounds="regular", bars=series))
    return dict(
        captured_at="2026-09-29T01:00:00+00:00",
        price_as_of="2026-09-29T01:00:00+00:00",
        adjustment_type="split",
        universe=["AAA"],
        benchmark="SPY",
        bars=bars,
    )


def _main(monkeypatch: pytest.MonkeyPatch) -> Any:
    class Clock(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            return datetime(2026, 9, 29, 1, 30, tzinfo=UTC).astimezone(tz)

    script = Path(__file__).parents[1] / "scripts/reconcile_stock_daily.py"
    namespace = runpy.run_path(str(script))
    main = namespace["main"]
    monkeypatch.setitem(main.__globals__, "datetime", Clock)
    return main


def test_primary_capture_is_immutable_and_records_raw_input_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.json"
    raw = json.dumps(_snapshot()).encode()
    source.write_bytes(raw)
    output = tmp_path / "primary.json"
    main = _main(monkeypatch)
    args = [
        "--primary-only",
        "--snapshot",
        str(source),
        "--output",
        str(output),
        "--required",
        "AAA",
    ]

    assert main(args) == 0
    result = json.loads(output.read_bytes())
    assert result["bars"] == _snapshot()["bars"]
    receipt = json.loads((tmp_path / "primary.json.sources.json").read_bytes())
    assert receipt["inputs_sha256"]["snapshot"] == hashlib.sha256(raw).hexdigest()
    assert main(args) == 2
    assert (
        output.read_bytes()
        == json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    )


def test_malformed_review_refuses_capture_without_creating_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.json"
    prior = tmp_path / "prior.json"
    review = tmp_path / "review.json"
    output = tmp_path / "legacy.json"
    source.write_text(json.dumps(_snapshot()), encoding="utf-8")
    prior.write_text(json.dumps(_snapshot()), encoding="utf-8")
    review.write_text('{"accepted_pairs": []}', encoding="utf-8")

    main = _main(monkeypatch)
    args = [
        "--snapshot",
        str(source),
        "--prior",
        str(prior),
        "--review",
        str(review),
        "--output",
        str(output),
        "--required",
        "AAA",
    ]
    assert main(args) == 2
    assert not output.exists()
    assert not (tmp_path / "legacy.json.sources.json").exists()


def test_review_command_binds_exact_input_files_and_legacy_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prior = _snapshot()
    prior["bars"][0]["symbol"] = "AMST"
    prior["universe"] = ["AMST"]
    published = json.loads(json.dumps(prior))
    published["captured_at"] = "2026-09-29T01:05:00+00:00"
    published["price_as_of"] = published["captured_at"]
    published["bars"][0]["bars"][-1]["volume"] += 1
    old_path = tmp_path / "prior.json"
    source_path = tmp_path / "source.json"
    review_path = tmp_path / "review.json"
    result_path = tmp_path / "legacy.json"
    old_path.write_text(json.dumps(prior), encoding="utf-8")
    source_path.write_text(json.dumps(published), encoding="utf-8")
    main = _main(monkeypatch)

    missing_path = tmp_path / "missing-review.json"
    assert (
        main(
            [
                "--create-review",
                "--snapshot",
                str(source_path),
                "--prior",
                str(old_path),
                "--output",
                str(missing_path),
                "--required",
                "MISSING",
                "--note",
                "Volume-only revision",
            ]
        )
        == 2
    )
    assert not missing_path.exists()
    assert not (tmp_path / "missing-review.json.sources.json").exists()

    assert (
        main(
            [
                "--create-review",
                "--snapshot",
                str(source_path),
                "--prior",
                str(old_path),
                "--output",
                str(review_path),
                "--required",
                "AMST",
                "--note",
                "Volume-only revision",
            ]
        )
        == 0
    )
    review = json.loads(review_path.read_bytes())
    assert review["entries"][0]["kind"] == "volume_correction"
    assert (
        main(
            [
                "--snapshot",
                str(source_path),
                "--prior",
                str(old_path),
                "--review",
                str(review_path),
                "--output",
                str(result_path),
                "--required",
                "AMST",
            ]
        )
        == 0
    )
    result = json.loads(result_path.read_bytes())
    assert result["bars"][0]["bars"][-1]["volume"] == 1_000_000
    receipt = json.loads((tmp_path / "legacy.json.sources.json").read_bytes())
    assert (
        receipt["inputs_sha256"]["review"] == hashlib.sha256(review_path.read_bytes()).hexdigest()
    )
