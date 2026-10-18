import gzip
import hashlib
import json

import pytest
from scripts.run_reel_pairs_study import load_symbol


def capture(tmp_path, *, volume=1000, symbol="KO"):
    raw = json.dumps(
        {
            "chart": {
                "result": [
                    {
                        "meta": {"symbol": symbol, "currency": "USD"},
                        "timestamp": [1136298600, 1136385000],
                        "indicators": {
                            "quote": [
                                {
                                    "open": [100, 101],
                                    "high": [102, 103],
                                    "low": [99, 100],
                                    "close": [101, 102],
                                    "volume": [volume, volume],
                                }
                            ],
                            "adjclose": [{"adjclose": [50.5, 51]}],
                        },
                    }
                ]
            }
        }
    ).encode()
    (tmp_path / "KO.json.gz").write_bytes(gzip.compress(raw))
    (tmp_path / "KO.receipt.json").write_text(
        json.dumps({"status": "ok", "sha256": hashlib.sha256(raw).hexdigest()})
    )


def test_adjusted_open_retains_open_to_close_return(tmp_path):
    capture(tmp_path)
    frame, _ = load_symbol(tmp_path, "KO")
    assert frame.open.iloc[0] == 50
    assert frame.close.iloc[0] / frame.open.iloc[0] - 1 == pytest.approx(0.01)


def test_tampered_capture_is_rejected(tmp_path):
    capture(tmp_path)
    (tmp_path / "KO.receipt.json").write_text(json.dumps({"status": "ok", "sha256": "wrong"}))
    with pytest.raises(ValueError, match="receipt"):
        load_symbol(tmp_path, "KO")


def test_zero_volume_placeholder_cannot_become_a_valid_price(tmp_path):
    capture(tmp_path, volume=0)
    with pytest.raises(ValueError, match="OHLCV"):
        load_symbol(tmp_path, "KO")


def test_mislabeled_ticker_is_rejected(tmp_path):
    capture(tmp_path, symbol="PEP")
    with pytest.raises(ValueError, match="identity"):
        load_symbol(tmp_path, "KO")
