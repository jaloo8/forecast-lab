"""Artificial schema fixtures only: these tests are not market backtests."""

import csv
import gzip
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from scripts.inspect_cbbo_schema import main

from kq.equities import cbbo_schema
from kq.equities.cbbo_schema import inspect_cbbo_schema

SYMBOL = "SPY   250117C00600000"


def _request(day: str = "2025-01-02") -> dict[str, Any]:
    return {
        "name": "artificial-opening",
        "dataset": "OPRA.PILLAR",
        "schema": "cbbo-1m",
        "symbols": ["SPY.OPT"],
        "stype_in": "parent",
        "start": f"{day}T14:30:00Z",
        "end": f"{day}T14:50:00Z",
    }


def _row(**changes: str) -> dict[str, str]:
    return {
        "ts_recv": "2025-01-02T14:31:00.000000000Z",
        "ts_event": "",
        "rtype": "193",
        "instrument_id": "11",
        "publisher_id": "30",
        "flags": "130",
        "bid_px_00": "1.10",
        "ask_px_00": "1.20",
        "bid_sz_00": "10",
        "ask_sz_00": "12",
        "bid_pb_00": "21",
        "ask_pb_00": "22",
        "symbol": SYMBOL,
        **changes,
    }


def _definition(**changes: str) -> dict[str, str]:
    return {
        "ts_recv": "2025-01-02T00:00:00Z",
        "ts_event": "2025-01-02T00:00:00Z",
        "rtype": "19",
        "publisher_id": "30",
        "instrument_id": "11",
        "raw_symbol": SYMBOL,
        "expiration": "2025-01-17T00:00:00Z",
        "strike_price": "600",
        "instrument_class": "C",
        "underlying": "SPY",
        "security_update_action": "A",
        "contract_multiplier": "100",
        **changes,
    }


def _csv(path: Path, rows: list[dict[str, str]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def _files(
    tmp_path: Path, rows: list[dict[str, str]], request: dict[str, Any] | None = None
) -> tuple[Path, Path, dict[str, Any]]:
    request = request or _request()
    metadata = {
        "version": 1,
        "job_id": "ARTIFICIAL",
        "query": {
            **{k: v for k, v in request.items() if k != "name"},
            "start": pd.Timestamp(request["start"]).value,
            "end": pd.Timestamp(request["end"]).value,
            "stype_out": "instrument_id",
            "encoding": "csv",
            "limit": None,
        },
        "customizations": {"pretty_px": True, "pretty_ts": True, "map_symbols": True},
    }
    meta = tmp_path / "metadata.json"
    meta.write_text(json.dumps(metadata), encoding="utf-8")
    return _csv(tmp_path / "quotes.csv", rows), meta, request


def test_modern_missing_trade_is_not_missing_quote_and_gaps_are_not_loss(tmp_path: Path) -> None:
    quotes, meta, request = _files(tmp_path, [_row(), _row(ts_recv="2025-01-02T14:33:00Z")])
    definitions = _csv(tmp_path / "defs.csv", [_definition()])
    report = inspect_cbbo_schema(
        quotes,
        request=request,
        metadata_path=meta,
        definitions_path=definitions,
    )
    assert report["status"] == "SCHEMA_INSPECTED_NOT_BACKTESTED"
    assert report["counts"]["standard_spy_100"] == 2
    assert report["counts"]["earliest_interval_availability_known"] == 2
    assert report["counts"]["missing_last_trade_timestamp"] == 2
    assert report["counts"]["flag_publisher_specific"] == 2
    assert report["timestamps"]["quote_update_timestamp_available"] is False
    assert report["intervals"]["unobserved_instrument_minute_labels"] == 18
    assert "Not a count of lost data" in report["intervals"]["interpretation"]


def test_legacy_override_never_establishes_receive_availability(tmp_path: Path) -> None:
    request = _request("2020-03-16")
    quotes, meta, request = _files(
        tmp_path,
        [
            _row(ts_recv="2020-03-16T14:31:12Z", ts_event="2020-03-16T14:31:12Z", flags="138"),
            _row(ts_recv="2020-03-16T14:32:00Z", flags="128"),
        ],
        request,
    )
    report = inspect_cbbo_schema(quotes, request=request, metadata_path=meta)
    assert report["legacy_subsampled"] is True
    assert report["counts"]["earliest_interval_availability_known"] == 0
    assert report["counts"]["legacy_missing_bad_timestamp_flag"] == 1
    assert report["counts"]["receive_equals_last_trade"] == 1
    assert report["timestamps"]["availability"] == "unknown_event_clock_override"


def test_price_flags_sizes_and_invalid_records_remain_visible(tmp_path: Path) -> None:
    quotes, meta, request = _files(
        tmp_path,
        [
            _row(bid_px_00="", ask_px_00="0", bid_sz_00="0", flags="142"),
            _row(bid_px_00="2", ask_px_00="1", flags="4"),
            _row(bid_px_00="-1", ask_px_00="-1", flags="1"),
            _row(bid_px_00="Infinity"),
            _row(rtype="177"),
        ],
    )
    report = inspect_cbbo_schema(quotes, request=request, metadata_path=meta)
    counts = report["counts"]
    assert counts["rows"] == 5 and counts["invalid_typed_rows"] == 1
    assert counts["missing_bid"] == counts["zero_ask"] == counts["crossed_quotes"] == 1
    assert counts["negative_bid"] == counts["locked_quotes"] == counts["zero_bid_size"] == 1
    assert counts["flag_maybe_bad_book"] == 2
    assert counts["unexpected_rtype"] == 1


def test_no_future_definition_and_no_fallback_past_latest_delete(tmp_path: Path) -> None:
    quotes, meta, request = _files(tmp_path, [_row(), _row(ts_recv="2025-01-02T14:34:00Z")])
    definitions = _csv(
        tmp_path / "defs.csv",
        [
            _definition(ts_recv="2025-01-02T14:32:00Z"),
            _definition(ts_recv="2025-01-02T14:33:00Z", security_update_action="D"),
        ],
    )
    report = inspect_cbbo_schema(
        quotes,
        request=request,
        metadata_path=meta,
        definitions_path=definitions,
    )
    assert report["counts"]["no_definition_at_or_before_label"] == 1
    assert report["counts"]["inactive_definition"] == 1
    assert report["counts"].get("standard_spy_100", 0) == 0


def test_future_definition_event_and_equal_time_conflicts_refused(tmp_path: Path) -> None:
    quotes, meta, request = _files(tmp_path, [_row()])
    definitions = _csv(
        tmp_path / "defs.csv",
        [
            _definition(ts_event="2025-01-02T14:40:00Z"),
            _definition(strike_price="599"),
            _definition(),
            _definition(),
        ],
    )
    report = inspect_cbbo_schema(
        quotes,
        request=request,
        metadata_path=meta,
        definitions_path=definitions,
    )
    assert report["counts"]["no_definition_at_or_before_label"] == 1


def test_undefined_multiplier_is_not_confirmed_100(tmp_path: Path) -> None:
    quotes, meta, request = _files(tmp_path, [_row()])
    definitions = _csv(tmp_path / "defs.csv", [_definition(contract_multiplier="2147483647")])
    report = inspect_cbbo_schema(
        quotes,
        request=request,
        metadata_path=meta,
        definitions_path=definitions,
    )
    assert report["counts"]["undefined_multiplier"] == 1


def test_wrong_definition_schema_cannot_supply_contract(tmp_path: Path) -> None:
    quotes, meta, request = _files(tmp_path, [_row()])
    definitions = _csv(tmp_path / "defs.csv", [_definition(rtype="177")])
    report = inspect_cbbo_schema(
        quotes,
        request=request,
        metadata_path=meta,
        definitions_path=definitions,
    )
    assert report["definitions"]["unexpected_rtype_or_publisher"] == 1
    assert report["counts"]["no_definition_at_or_before_label"] == 1


def test_invalid_latest_definition_does_not_fall_back(tmp_path: Path) -> None:
    quotes, meta, request = _files(tmp_path, [_row()])
    definitions = _csv(
        tmp_path / "defs.csv",
        [_definition(), _definition(ts_recv="2025-01-02T14:30:00Z", rtype="177")],
    )
    report = inspect_cbbo_schema(
        quotes,
        request=request,
        metadata_path=meta,
        definitions_path=definitions,
    )
    assert report["counts"]["no_definition_at_or_before_label"] == 1
    assert report["counts"].get("standard_spy_100", 0) == 0


def test_mutated_input_does_not_receive_a_completed_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    quotes, meta, request = _files(tmp_path, [_row()])
    original = cbbo_schema._Inspection.observe

    def mutate(self: cbbo_schema._Inspection, row: dict[str, str]) -> None:
        original(self, row)
        # Change an unopened input, avoiding Windows sharing semantics.
        meta.write_text(meta.read_text() + "\n", encoding="utf-8")

    monkeypatch.setattr(cbbo_schema._Inspection, "observe", mutate)
    with pytest.raises(ValueError, match="Input changed"):
        inspect_cbbo_schema(quotes, request=request, metadata_path=meta)


def test_expired_definition_is_reported_without_feasibility_claim(tmp_path: Path) -> None:
    symbol = SYMBOL.replace("250117", "241220")
    quotes, meta, request = _files(tmp_path, [_row(symbol=symbol)])
    definitions = _csv(
        tmp_path / "defs.csv",
        [
            _definition(raw_symbol=symbol, expiration="2024-12-20T00:00:00Z"),
        ],
    )
    report = inspect_cbbo_schema(
        quotes,
        request=request,
        metadata_path=meta,
        definitions_path=definitions,
    )
    assert report["counts"]["definition_expiration_date_before_quote_date"] == 1


def test_gzip_raw_ns_and_exclusive_end(tmp_path: Path) -> None:
    quotes, meta, request = _files(
        tmp_path,
        [
            _row(ts_recv=str(pd.Timestamp("2025-01-02T14:31:00Z").value)),
            _row(ts_recv="2025-01-02T14:50:00Z"),
            _row(ts_recv="2025-01-02T14:30:59.999999999Z", ts_event="18446744073709551615"),
        ],
    )
    compressed = tmp_path / "quotes.csv.gz"
    compressed.write_bytes(gzip.compress(quotes.read_bytes()))
    report = inspect_cbbo_schema(compressed, request=request, metadata_path=meta)
    assert report["counts"]["outside_request_receive_time"] == 1
    assert report["counts"]["unaligned_receive_timestamp"] == 1
    assert report["counts"]["earliest_interval_availability_known"] == 1


def test_dated_mapping_expiration_and_embedded_mismatch(tmp_path: Path) -> None:
    quotes, meta, request = _files(tmp_path, [_row()])
    mapping = tmp_path / "symbology.json"
    mapping.write_text(
        json.dumps(
            {
                "stype_in": "instrument_id",
                "stype_out": "raw_symbol",
                "result": {
                    "11": [
                        {"d0": "2025-01-01", "d1": "2025-01-02", "s": SYMBOL},
                        {"d0": "2025-01-02", "d1": "2025-01-03", "s": SYMBOL.replace("600", "601")},
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    report = inspect_cbbo_schema(
        quotes,
        request=request,
        metadata_path=meta,
        symbology_path=mapping,
    )
    assert report["counts"]["embedded_mapping_mismatch"] == 1
    assert report["counts"]["ambiguous_dated_mapping"] == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema", "cmbp-1"),
        ("start", "2025-01-02T14:29:00Z"),
        ("symbols", ["QQQ.OPT"]),
        ("encoding", "dbn"),
        ("limit", 5),
    ],
)
def test_metadata_request_or_encoding_mismatch_refused(
    tmp_path: Path,
    field: str,
    value: Any,
) -> None:
    quotes, meta, request = _files(tmp_path, [_row()])
    obj = json.loads(meta.read_text())
    obj["query"][field] = value
    meta.write_text(json.dumps(obj), encoding="utf-8")
    with pytest.raises(ValueError):
        inspect_cbbo_schema(quotes, request=request, metadata_path=meta)


def test_raw_price_encoding_refused(tmp_path: Path) -> None:
    quotes, meta, request = _files(tmp_path, [_row()])
    obj = json.loads(meta.read_text())
    obj["customizations"]["pretty_px"] = False
    meta.write_text(json.dumps(obj), encoding="utf-8")
    with pytest.raises(ValueError, match="decimal-price"):
        inspect_cbbo_schema(quotes, request=request, metadata_path=meta)


def test_memory_limit_refuses_instead_of_silently_sampling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    quotes, meta, request = _files(tmp_path, [_row(), _row(instrument_id="12")])
    monkeypatch.setattr(cbbo_schema, "MAX_INSTRUMENTS", 1)
    with pytest.raises(ValueError, match="Instrument state limit"):
        inspect_cbbo_schema(quotes, request=request, metadata_path=meta)


def test_duplicate_and_out_of_order_intervals_preserved(tmp_path: Path) -> None:
    quotes, meta, request = _files(
        tmp_path,
        [
            _row(ts_recv="2025-01-02T14:33:00Z"),
            _row(),
            _row(),
        ],
    )
    report = inspect_cbbo_schema(quotes, request=request, metadata_path=meta)
    assert report["counts"]["out_of_order_per_instrument"] == 1
    assert report["counts"]["duplicate_instrument_minute"] == 1
    assert report["intervals"]["observed_instrument_minute_labels"] == 2


def test_cli_writes_report_once_and_does_not_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    quotes, meta, request = _files(tmp_path, [_row()])
    plan, output = tmp_path / "plan.json", tmp_path / "report.json"
    plan.write_text(json.dumps([request]), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "inspect",
            "--quotes",
            str(quotes),
            "--metadata",
            str(meta),
            "--requests",
            str(plan),
            "--request-name",
            request["name"],
            "--output",
            str(output),
        ],
    )
    main()
    assert json.loads(output.read_text())["counts"]["rows"] == 1
    with pytest.raises(FileExistsError):
        main()
