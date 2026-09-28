"""Coverage evidence must not imply prices, forecasts or complete news coverage."""

import hashlib
import json
from pathlib import Path

from streamlit.testing.v1 import AppTest


def _app(folder: Path) -> AppTest:
    return AppTest.from_string(
        "from pathlib import Path\nfrom kq.equities.coverage_panel import render_coverage\n"
        f"render_coverage(Path({str(folder)!r}))"
    ).run()


def test_empty_coverage_never_creates_databases(tmp_path: Path) -> None:
    app = _app(tmp_path)
    assert not app.exception
    assert app.info
    assert not list(tmp_path.iterdir())


def test_broad_losses_and_unready_long_horizon_are_visible(tmp_path: Path) -> None:
    (tmp_path / "broad-historical-study.json").write_text(
        json.dumps(
            {
                "coverage": {
                    "study_stock_count": 4447,
                    "first_session": "2026-03-02",
                    "last_session": "2026-09-25",
                },
                "groups": [
                    {
                        "horizon_sessions": 5,
                        "cohort_count": 27,
                        "mean_net_return": -0.06,
                        "mean_excess_vs_matched_spy": -0.061,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    app = _app(tmp_path)
    assert not app.exception
    table = next(item.value for item in app.dataframe if "Mean net return" in item.value)
    assert table.iloc[0]["Mean net return"] == "-6.00%"
    assert any("126-session: no mature" in item.value for item in app.info)
    assert any("not the $100" in item.value for item in app.warning)


def test_price_research_discloses_partial_coverage(tmp_path: Path) -> None:
    (tmp_path / "broad-coverage.csv").write_text(
        "symbol,coverage_status,as_of\nAAA,ranked,2026-09-28T04:00:00+00:00\n"
        "BBB,not_requested,2026-09-28T04:00:00+00:00\n",
        encoding="utf-8",
    )
    app = _app(tmp_path)
    assert not app.exception
    assert any("1 of 2" in item.value for item in app.caption)
    assert any("not_requested" in str(item.value) for item in app.dataframe)


def test_catalogue_counts_and_bad_digest_are_visible(tmp_path: Path) -> None:
    folder = tmp_path / "universe"
    folder.mkdir()
    sources = []
    files = {
        "nasdaqlisted.txt": (
            "Symbol|Security Name|Market Category|Test Issue|Financial Status|"
            "Round Lot Size|ETF|NextShares\n"
            "AAA|Example Common Stock|Q|N|N|100|N|N\n"
            "FUND|Example ETF|G|N|N|100|Y|N\n"
            "File Creation Time: 0925202621:31|||||||\n"
        ),
        "otherlisted.txt": (
            "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|"
            "Test Issue|NASDAQ Symbol\n"
            "BBB|Example Ordinary Shares|N|BBB|N|100|N|BBB\n"
            "File Creation Time: 0925202621:31||||||\n"
        ),
    }
    for name, content in files.items():
        raw = content.encode()
        (folder / name).write_bytes(raw)
        sources.append(
            {
                "file": name,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "url": "https://www.nasdaqtrader.com/dynamic/SymDir/" + name,
                "trailer": content.splitlines()[-1],
                "lines": len(content.splitlines()),
            }
        )
    (folder / "manifest.json").write_text(
        json.dumps(
            {
                "captured_at": "2026-09-28T04:00:00+00:00",
                "sources": sources,
            }
        ),
        encoding="utf-8",
    )
    app = _app(tmp_path)
    assert not app.exception
    assert not app.error
    assert app.metric[0].value == "3"
    assert any("historical" in warning.value for warning in app.warning)
    assert len(app.dataframe[0].value) == 3
    (folder / "nasdaqlisted.txt").write_text("corrupted", encoding="utf-8")
    invalid = _app(tmp_path)
    assert not invalid.exception
    assert invalid.error
    assert not invalid.metric
