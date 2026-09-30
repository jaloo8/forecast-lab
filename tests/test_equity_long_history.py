import hashlib
import json
from pathlib import Path

import pytest

from kq.equities.strategy_lab.long_history import load_long_capture


def capture(tmp_path: Path) -> Path:
    request = dict(
        symbols=["SPY", "AAA", "OLD"],
        start_time="2006-09-30T00:00:00Z",
        end_time="2006-10-05T00:00:00Z",
        interval="day",
        bounds="regular",
        adjustment_type="split",
    )
    bars = [
        dict(
            begins_at=f"2006-10-0{d}T00:00:00Z",
            open_price="10",
            high_price="12",
            low_price="9",
            close_price="11",
            volume=1000,
            session="reg",
            interpolated=False,
        )
        for d in (2, 3, 4)
    ]
    response = dict(
        structuredContent=dict(
            data=dict(
                not_found=["OLD"],
                results=[
                    dict(symbol=s, bounds="regular", interval="day", bars=bars)
                    for s in ("SPY", "AAA")
                ],
            )
        )
    )
    raw = dict(request=request, retrieved_at="2026-09-29T01:00:00Z", response=response)
    (tmp_path / "batch.json").write_text(json.dumps(raw))
    manifest = dict(
        protocol="long-study-v1",
        universe=["AAA", "OLD"],
        benchmark="SPY",
        adjustment_type="split",
        start_time=request["start_time"],
        end_time=request["end_time"],
        catalogue_sha256="a" * 64,
        catalogue_captured_at="2026-09-28T01:00:00Z",
        selection_rule="test fixture",
        requests=[dict(file="batch.json", request=request)],
    )
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    refresh(tmp_path)
    return tmp_path


def refresh(path: Path) -> None:
    def digest(name: str) -> str:
        return hashlib.sha256((path / name).read_bytes()).hexdigest()

    (path / "receipt.json").write_text(
        json.dumps(
            dict(
                manifest_sha256=digest("manifest.json"),
                inputs=[dict(file="batch.json", sha256=digest("batch.json"))],
            )
        )
    )


def mutate(path: Path, fn: object) -> None:
    raw = json.loads((path / "batch.json").read_text())
    fn(raw)
    (path / "batch.json").write_text(json.dumps(raw))
    refresh(path)


def test_load_and_preserve_actual_vs_simulated_times(tmp_path: Path) -> None:
    bars, source = load_long_capture(capture(tmp_path))
    assert len(bars) == 6
    assert source["not_found"]["batch.json"] == ["OLD"]
    assert source["last_session"] == "2006-10-04"
    assert source["captured_at"].startswith("2026-09-29")
    assert str(bars.as_of.min()).startswith("2006-10-02 20:00")


def test_hash_tampering_fails(tmp_path: Path) -> None:
    path = capture(tmp_path)
    with (path / "batch.json").open("a") as f:
        f.write(" ")
    with pytest.raises(ValueError, match="hash"):
        load_long_capture(path)


def test_synthetic_prelisting_is_excluded_not_backfilled(tmp_path: Path) -> None:
    path = capture(tmp_path)
    mutate(
        path,
        lambda r: r["response"]["structuredContent"]["data"]["results"][1]["bars"][0].update(
            interpolated=True, volume=0
        ),
    )
    bars, source = load_long_capture(path)
    assert len(bars[bars.symbol == "AAA"]) == 2
    assert source["excluded_bars"]["AAA"] == 1


@pytest.mark.parametrize("kind", ["missing", "duplicate", "bounds", "request", "future", "error"])
def test_invalid_evidence_fails(tmp_path: Path, kind: str) -> None:
    path = capture(tmp_path)

    def change(r: dict) -> None:
        data = r["response"]["structuredContent"]["data"]
        if kind == "missing":
            data["results"].pop()
        if kind == "duplicate":
            data["results"][1]["bars"].append(data["results"][1]["bars"][0])
        if kind == "bounds":
            data["results"][0]["bounds"] = "extended"
        if kind == "request":
            r["request"]["adjustment_type"] = "none"
        if kind == "future":
            r["retrieved_at"] = "2099-01-01T00:00:00Z"
        if kind == "error":
            r["response"]["isError"] = True

    mutate(path, change)
    with pytest.raises(ValueError):
        load_long_capture(path)


def test_newer_optional_bar_cannot_extend_benchmark(tmp_path: Path) -> None:
    path = capture(tmp_path)
    mutate(
        path,
        lambda r: r["response"]["structuredContent"]["data"]["results"][0]["bars"][-1].update(
            interpolated=True, volume=0
        ),
    )
    bars, source = load_long_capture(path)
    assert source["last_session"] == "2006-10-03"
    assert str(bars.session_date.max()) == "2006-10-03"
    assert source["beyond_benchmark"] == 1


@pytest.mark.parametrize("index", [0, 1])
def test_bad_prices_counted_but_benchmark_fails(tmp_path: Path, index: int) -> None:
    path = capture(tmp_path)
    mutate(
        path,
        lambda r: r["response"]["structuredContent"]["data"]["results"][index]["bars"][0].update(
            high_price="1"
        ),
    )
    if index == 0:
        with pytest.raises(ValueError, match="OHLC"):
            load_long_capture(path)
    else:
        bars, source = load_long_capture(path)
        assert len(bars[bars.symbol == "AAA"]) == 2
        assert source["invalid_bars"][0]["symbol"] == "AAA"


def test_boolean_benchmark_volume_is_not_a_zero_volume_placeholder(tmp_path: Path) -> None:
    path = capture(tmp_path)
    mutate(
        path,
        lambda r: r["response"]["structuredContent"]["data"]["results"][0]["bars"][0].update(
            volume=False
        ),
    )
    with pytest.raises(ValueError, match="Boolean"):
        load_long_capture(path)
