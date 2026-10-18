"""Point-in-time contracts for the isolated stock research pilot."""

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from kq.equities.research import daily_bars, scan


def snapshot() -> dict[str, object]:
    dates = pd.bdate_range("2026-03-30", periods=130)
    captured = datetime(2026, 9, 29, 12, tzinfo=UTC)

    def history(symbol: str, growth: float) -> dict[str, object]:
        return {
            "symbol": symbol,
            "interval": "day",
            "bounds": "regular",
            "bars": [
                {
                    "begins_at": day.strftime("%Y-%m-%dT00:00:00Z"),
                    "open_price": str(100 + i * growth - 0.2),
                    "close_price": str(100 + i * growth),
                    "high_price": str(101 + i * growth),
                    "low_price": str(99 + i * growth),
                    "volume": 1000000,
                    "session": "reg",
                }
                for i, day in enumerate(dates)
            ],
        }

    return {
        "captured_at": captured.isoformat(),
        "benchmark": "SPY",
        "bars": {"data": {"results": [history("SPY", 0.1), history("MSFT", 0.3)]}},
        "fundamentals": {"data": {"results": []}},
        "earnings": {"data": {"results": []}},
        "news": [],
        "source_errors": [],
    }


def test_complete_actual_bars_and_ranked_horizons() -> None:
    data = snapshot()
    bars = daily_bars(data)
    assert list(bars.columns) == ["symbol", "session_date", "open", "close", "volume", "as_of"]
    assert bars["as_of"].dt.tz is not None
    ranked = scan(data)
    assert list(ranked.columns) == [
        "symbol",
        "horizon_sessions",
        "as_of",
        "session_date",
        "close",
        "benchmark_close",
        "momentum",
        "benchmark_momentum",
        "excess_momentum",
        "volatility_20d",
        "pe_ratio",
        "market_cap",
        "sector",
        "latest_eps_actual",
        "latest_eps_estimate",
        "news_count",
        "status",
    ]
    assert ranked["symbol"].tolist() == ["MSFT"] * 3
    assert ranked["horizon_sessions"].tolist() == [5, 20, 126]
    assert ranked["excess_momentum"].gt(0).all()
    assert ranked["pe_ratio"].isna().all()


def test_synthetic_and_capture_day_bars_are_excluded() -> None:
    data = snapshot()
    entries = data["bars"]["data"]["results"]  # type: ignore[index]
    stock_bars = entries[1]["bars"]  # type: ignore[index]
    stock_bars[-1]["is_synthetic"] = True  # type: ignore[index]
    stock_bars.append({**stock_bars[-2], "begins_at": "2026-09-29T00:00:00Z"})  # type: ignore[index]
    assert daily_bars(data).query("symbol == 'MSFT'").shape[0] == 129
    assert scan(data).empty


def test_stale_and_missing_shared_history_do_not_rank() -> None:
    data = snapshot()
    data["captured_at"] = datetime(2026, 10, 5, 12, tzinfo=UTC).isoformat()
    with pytest.raises(ValueError, match="stale"):
        scan(data)
    data["captured_at"] = datetime(2026, 9, 29, 12, tzinfo=UTC).isoformat()
    data["bars"]["data"]["results"][0]["bars"] = []  # type: ignore[index]
    with pytest.raises(ValueError, match="benchmark"):
        scan(data)


@pytest.mark.parametrize("bad", ["NaN", "inf", "-1", "0", "bad"])
def test_invalid_financial_values_fail_loudly(bad: str) -> None:
    data = snapshot()
    data["bars"]["data"]["results"][1]["bars"][0]["close_price"] = bad  # type: ignore[index]
    with pytest.raises(ValueError, match="close_price"):
        daily_bars(data)


def test_future_news_and_naive_capture_fail_loudly() -> None:
    data = snapshot()
    data["captured_at"] = "2026-09-29T12:00:00"
    with pytest.raises(ValueError, match="captured_at"):
        scan(data)
    data = snapshot()
    data["news"] = [
        {
            "symbol": "MSFT",
            "title": "Filing",
            "url": "https://example.com/filing",
            "kind": "filing",
            "published_at": "2026-09-29T13:00:00Z",
            "retrieved_at": "2026-09-29T13:01:00Z",
        }
    ]
    with pytest.raises(ValueError, match="future"):
        scan(data)


def test_news_context_counts_only_valid_observations() -> None:
    data = snapshot()
    captured = datetime.fromisoformat(data["captured_at"])  # type: ignore[arg-type]
    data["news"] = [
        {
            "symbol": "MSFT",
            "title": "Filing",
            "url": "https://example.com/filing",
            "kind": "filing",
            "published_at": (captured - timedelta(days=1)).isoformat(),
            "retrieved_at": (captured - timedelta(hours=1)).isoformat(),
        }
    ]
    assert scan(data)["news_count"].tolist() == [1, 1, 1]


def test_interpolated_bar_is_never_used() -> None:
    data = snapshot()
    data["bars"]["data"]["results"][1]["bars"][-1]["interpolated"] = True  # type: ignore[index]
    assert scan(data).empty


def test_actual_provider_context_is_prospective_only() -> None:
    data = snapshot()
    data["fundamentals"] = [
        {
            "symbol": "MSFT",
            "market_date": "2026-09-25",
            "pe_ratio": "39.098736",
            "market_cap": "4977205968000.000000",
            "sector": "Electronic Technology",
        }
    ]
    data["earnings"] = [
        {
            "symbol": "MSFT",
            "eps": {"actual": "2.02", "estimate": "1.89"},
            "report": {"date": "2026-07-30", "timing": "pm", "verified": True},
        },
        {
            "symbol": "MSFT",
            "eps": {"actual": None, "estimate": "2.20"},
            "report": {"date": "2026-10-30", "timing": "pm", "verified": False},
        },
    ]
    row = scan(data).iloc[0]
    assert row["pe_ratio"] == pytest.approx(39.098736)
    assert row["latest_eps_actual"] == pytest.approx(2.02)
    assert row["latest_eps_estimate"] == pytest.approx(1.89)


def test_news_symbol_must_match_snapshot_coverage() -> None:
    data = snapshot()
    data["news"] = [
        {
            "symbol": "FAKE",
            "title": "Unrelated",
            "kind": "news",
            "url": "https://example.com/story",
            "published_at": "2026-09-25T12:00:00Z",
            "retrieved_at": "2026-09-26T12:00:00Z",
        }
    ]
    with pytest.raises(ValueError, match="news symbol"):
        scan(data)


def test_negative_pe_is_finite_context_and_boolean_price_is_invalid() -> None:
    data = snapshot()
    data["fundamentals"] = [{"symbol": "MSFT", "pe_ratio": "-12.5"}]
    assert scan(data).iloc[0]["pe_ratio"] == pytest.approx(-12.5)
    data["bars"]["data"]["results"][1]["bars"][0]["close_price"] = True  # type: ignore[index]
    with pytest.raises(ValueError, match="close_price"):
        daily_bars(data)


def test_unreported_earnings_do_not_replace_latest_actual() -> None:
    data = snapshot()
    data["earnings"] = [
        {
            "symbol": "MSFT",
            "eps": {"actual": "2.02", "estimate": "1.89"},
            "report": {"date": "2026-07-30"},
        },
        {
            "symbol": "MSFT",
            "eps": {"actual": None, "estimate": "2.20"},
            "report": {"date": "2026-09-26"},
        },
        {"symbol": "MSFT", "eps": {"actual": None, "estimate": "2.25"}, "report": None},
    ]
    row = scan(data).iloc[0]
    assert row["latest_eps_actual"] == pytest.approx(2.02)
    assert row["latest_eps_estimate"] == pytest.approx(1.89)


def test_missing_benchmark_fails_closed() -> None:
    data = snapshot()
    data["bars"]["data"]["results"].pop(0)  # type: ignore[index]
    with pytest.raises(ValueError, match="benchmark"):
        scan(data)


def test_only_spy_is_supported_as_benchmark() -> None:
    data = snapshot()
    data["benchmark"] = "QQQ"
    data["bars"]["data"]["results"][0]["symbol"] = "QQQ"  # type: ignore[index]
    with pytest.raises(ValueError, match="SPY"):
        scan(data)


def test_duplicate_news_url_counts_once_and_unsafe_news_fails() -> None:
    data = snapshot()
    event = {
        "symbol": "MSFT",
        "title": "Filing",
        "kind": "filing",
        "url": "https://example.com/filing",
        "published_at": "2026-09-25T12:00:00Z",
        "retrieved_at": "2026-09-26T12:00:00Z",
    }
    data["news"] = [event, dict(event)]
    assert scan(data).iloc[0]["news_count"] == 1
    data["news"] = [{**event, "title": " "}]
    with pytest.raises(ValueError, match="title"):
        scan(data)
    data["news"] = [{**event, "url": "https://name:secret@example.com/filing"}]
    with pytest.raises(ValueError, match="HTTPS URL"):
        scan(data)


def test_missing_interior_stock_session_prevents_ranking() -> None:
    data = snapshot()
    data["bars"]["data"]["results"][1]["bars"].pop(-20)  # type: ignore[index]
    assert scan(data).empty
