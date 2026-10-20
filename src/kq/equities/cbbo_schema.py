"""Offline CBBO schema inspection, never a quote-fill or performance model.

CSV records stream one at a time. Instrument/definition state and JSON inputs
have explicit limits; exceeding a limit refuses the inspection, never samples it.
"""

from __future__ import annotations

import bisect
import csv
import gzip
import hashlib
import json
import re
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pandas as pd

MINUTE_NS = 60_000_000_000
LEGACY_END = pd.Timestamp("2023-03-28T00:00:00Z").value
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_INSTRUMENTS = 20_000
MAX_DEFINITIONS = 100_000
QUOTE_FIELDS = frozenset(
    [
        "ts_recv",
        "ts_event",
        "rtype",
        "publisher_id",
        "instrument_id",
        "flags",
        "bid_px_00",
        "ask_px_00",
        "bid_sz_00",
        "ask_sz_00",
        "bid_pb_00",
        "ask_pb_00",
    ]
)
DEFINITION_FIELDS = frozenset(
    [
        "ts_recv",
        "ts_event",
        "rtype",
        "publisher_id",
        "instrument_id",
        "raw_symbol",
        "expiration",
        "strike_price",
        "instrument_class",
        "underlying",
        "security_update_action",
        "contract_multiplier",
    ]
)
FLAG_NAMES = {
    128: "last",
    64: "top_of_book",
    32: "snapshot",
    16: "aggregated_level",
    8: "bad_receive_timestamp",
    4: "maybe_bad_book",
    2: "publisher_specific",
    1: "reserved",
}
SOURCES = [
    "https://databento.com/docs/schemas-and-data-formats/cbbo",
    "https://databento.com/docs/knowledge-base/datasets/opra-pillar",
    "https://databento.com/docs/standards-and-conventions/common-fields-enums-types",
]


def _stamp(value: Any) -> int | None:
    text = str(value).strip()
    if text in {"", "None", "null", "NaT", "18446744073709551615"}:
        return None
    if re.fullmatch(r"\d+", text):
        stamp = pd.Timestamp(int(text), unit="ns", tz="UTC")
    else:
        stamp = pd.Timestamp(text)
        if stamp.tzinfo is None:
            raise ValueError("Explicit UTC offset required")
    if pd.isna(stamp):
        raise ValueError("Invalid timestamp")
    return int(stamp.value)


def _required_stamp(value: Any) -> int:
    result = _stamp(value)
    if result is None:
        raise ValueError("Required timestamp absent")
    return result


def _json(path: Path) -> dict[str, Any]:
    if path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError("JSON input exceeds bounded inspection limit")
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise ValueError("Expected JSON object")
    return result


def _fingerprint(path: Path) -> dict[str, Any]:
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"name": path.name, "bytes": path.stat().st_size, "sha256": digest}


def _rows(path: Path, required: frozenset[str]) -> Iterator[dict[str, str]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames or []
        if len(fields) > 512 or len(fields) != len(set(fields)) or not required <= set(fields):
            raise ValueError("Missing, duplicate or excessive CSV columns")
        for row in reader:
            if None in row or any(value is None or len(value) > 4096 for value in row.values()):
                raise ValueError("Malformed or oversized CSV row")
            yield row


def _number(value: str) -> Decimal | None:
    if not value.strip() or value in {"null", "NaN", "nan", "9223372036854775807"}:
        return None
    number = Decimal(value)
    if not number.is_finite():
        raise ValueError("Nonfinite price")
    return number


def _integer(value: str, ceiling: int = 2**32 - 1) -> int:
    result = int(value)
    if not 0 <= result <= ceiling:
        raise ValueError("Unsigned integer outside schema bounds")
    return result


def _metadata(path: Path, request: dict[str, Any]) -> dict[str, Any]:
    obj = _json(path)
    query = obj.get("query", obj)
    custom = obj.get("customizations", obj)
    if not isinstance(query, dict) or not isinstance(custom, dict):
        raise ValueError("Invalid batch metadata")
    for key in ("dataset", "schema", "stype_in"):
        if query.get(key) != request.get(key):
            raise ValueError(f"Metadata request mismatch: {key}")
    symbols = query.get("symbols")
    if isinstance(symbols, str):
        symbols = symbols.split(",")
    if symbols != request.get("symbols"):
        raise ValueError("Metadata request mismatch: symbols")
    for key in ("start", "end"):
        if _required_stamp(query.get(key)) != _required_stamp(request[key]):
            raise ValueError(f"Metadata request mismatch: {key}")
    if custom.get("pretty_px") is not True or query.get("encoding") != "csv":
        raise ValueError("This inspector requires decimal-price CSV metadata")
    if query.get("limit") not in (None, 0):
        raise ValueError("Truncated requests are not a complete schema probe")
    return {"request_identity_matches": True, "decimal_prices": True, **_fingerprint(path)}


def _definitions(
    path: Path | None,
) -> tuple[dict[int, list[tuple[int, dict[str, str]]]], Counter[str]]:
    result: dict[int, list[tuple[int, dict[str, str]]]] = {}
    counts: Counter[str] = Counter()
    if path is None:
        return result, counts
    for row in _rows(path, DEFINITION_FIELDS):
        counts["rows"] += 1
        if counts["rows"] > MAX_DEFINITIONS:
            raise ValueError("Definition row limit exceeded; inspection refused")
        try:
            instrument = _integer(row["instrument_id"])
            available = max(_required_stamp(row["ts_recv"]), _required_stamp(row["ts_event"]))
        except (ValueError, OverflowError):
            counts["invalid_identity_or_timestamp"] += 1
            continue
        selected = {key: row[key] for key in DEFINITION_FIELDS}
        try:
            valid_schema = (
                _integer(row["rtype"], 255) == 19 and _integer(row["publisher_id"], 65535) == 30
            )
        except ValueError:
            valid_schema = False
        if not valid_schema:
            counts["unexpected_rtype_or_publisher"] += 1
            selected["_invalid_schema"] = "true"
        result.setdefault(instrument, []).append((available, selected))
    for history in result.values():
        history.sort(key=lambda pair: pair[0])
    counts["instruments"] = len(result)
    return result, counts


def _definition_at(history: list[tuple[int, dict[str, str]]], at: int) -> dict[str, str] | None:
    index = bisect.bisect_right(history, at, key=lambda pair: pair[0]) - 1
    if index < 0:
        return None
    row = history[index][1]
    if row.get("_invalid_schema"):
        return None
    # Equal-time conflicting updates do not have a known causal ordering.
    first = bisect.bisect_left(history, history[index][0], key=lambda pair: pair[0])
    if any(prior != row for _, prior in history[first:index]):
        return None
    return row


def _identity(definition: dict[str, str], symbol: str | None) -> str:  # noqa: PLR0911
    if definition["security_update_action"] not in {"A", "M"}:
        return "inactive_definition"
    raw_symbol = definition["raw_symbol"]
    if symbol and symbol != raw_symbol:
        return "symbol_definition_mismatch"
    occ = re.fullmatch(r"SPY   (\d{6})([CP])(\d{8})", raw_symbol)
    if occ is None or definition["underlying"] != "SPY":
        return "nonstandard_spy_definition"
    try:
        expiry = pd.Timestamp(definition["expiration"]).strftime("%y%m%d")
        strike = _number(definition["strike_price"])
        if (
            expiry != occ[1]
            or definition["instrument_class"] != occ[2]
            or strike != Decimal(occ[3]) / 1000
        ):
            return "contract_definition_mismatch"
        multiplier = int(definition["contract_multiplier"])
    except (ValueError, InvalidOperation):
        return "invalid_contract_definition"
    if multiplier == 2147483647:
        return "undefined_multiplier"
    return "standard_spy_100" if multiplier == 100 else "nonstandard_multiplier"


def _mappings(path: Path | None) -> dict[int, list[tuple[int, int, str]]]:
    if path is None:
        return {}
    obj = _json(path)
    source, destination = obj.get("stype_in"), obj.get("stype_out")
    if (source, destination) not in {
        ("instrument_id", "raw_symbol"),
        ("raw_symbol", "instrument_id"),
    } or not isinstance(obj.get("result"), dict):
        raise ValueError("Dated symbology needs explicit raw_symbol/instrument_id directions")
    result: dict[int, list[tuple[int, int, str]]] = {}
    total = 0
    for key, rows in obj["result"].items():
        if not isinstance(rows, list):
            raise ValueError("Invalid dated symbology")
        for row in rows:
            total += 1
            if total > MAX_DEFINITIONS or not isinstance(row, dict):
                raise ValueError("Invalid or oversized dated symbology")
            instrument = _integer(str(key if source == "instrument_id" else row["s"]))
            symbol = str(row["s"] if source == "instrument_id" else key)
            start = _required_stamp(f"{row['d0']}T00:00:00Z")
            end = _required_stamp(f"{row['d1']}T00:00:00Z")
            if end <= start or len(symbol) > 64:
                raise ValueError("Invalid mapping interval or symbol")
            result.setdefault(instrument, []).append((start, end, symbol))
    return result


@dataclass
class _Instrument:
    previous: int | None = None
    minutes: int = 0
    rows: int = 0


@dataclass
class _Inspection:
    start: int
    end: int
    legacy: bool
    definitions: dict[int, list[tuple[int, dict[str, str]]]]
    mappings: dict[int, list[tuple[int, int, str]]]
    counts: Counter[str] = field(default_factory=Counter)
    flags: Counter[str] = field(default_factory=Counter)
    rtypes: Counter[str] = field(default_factory=Counter)
    instruments: dict[int, _Instrument] = field(default_factory=dict)
    minimum_recv: int | None = None
    maximum_recv: int | None = None

    def observe(self, row: dict[str, str]) -> None:
        self.counts["rows"] += 1
        try:
            rtype = _integer(row["rtype"], 255)
            self.rtypes[str(rtype)] += 1
            instrument = _integer(row["instrument_id"])
            flags = _integer(row["flags"], 255)
            recv = _stamp(row["ts_recv"])
            event = _stamp(row["ts_event"])
            publisher = _integer(row["publisher_id"], 65535)
            for name in ("bid_pb_00", "ask_pb_00"):
                _integer(row[name], 65535)
            prices = (_number(row["bid_px_00"]), _number(row["ask_px_00"]))
            sizes = (_integer(row["bid_sz_00"]), _integer(row["ask_sz_00"]))
        except (ValueError, InvalidOperation, OverflowError):
            self.counts["invalid_typed_rows"] += 1
            return
        self.flags[str(flags)] += 1
        for bit, label in FLAG_NAMES.items():
            self.counts[f"flag_{label}"] += bool(flags & bit)
        self.counts["unexpected_rtype"] += rtype != 193
        self.counts["unexpected_publisher"] += publisher != 30
        self._prices(prices, sizes)
        if recv is None:
            self.counts["missing_receive_timestamp"] += 1
            return
        self.minimum_recv = recv if self.minimum_recv is None else min(self.minimum_recv, recv)
        self.maximum_recv = recv if self.maximum_recv is None else max(self.maximum_recv, recv)
        self.counts["missing_last_trade_timestamp"] += event is None
        self.counts["last_trade_after_label"] += event is not None and event > recv
        self.counts["receive_equals_last_trade"] += recv == event
        self.counts["unaligned_receive_timestamp"] += recv % MINUTE_NS != 0
        self.counts["outside_request_receive_time"] += not self.start <= recv < self.end
        self.counts["legacy_missing_bad_timestamp_flag"] += self.legacy and not bool(flags & 8)
        self.counts["earliest_interval_availability_known"] += (
            not self.legacy
            and recv % MINUTE_NS == 0
            and not bool(flags & 8)
            and rtype == 193
            and publisher == 30
            and self.start <= recv < self.end
            and (event is None or event <= recv)
        )
        local = pd.Timestamp(recv, unit="ns", tz="UTC").tz_convert("America/New_York")
        minute = local.hour * 60 + local.minute
        self.counts["label_at_1600_new_york"] += minute == 960 and recv % MINUTE_NS == 0
        self.counts["opening_first_ten_minutes_labels"] += (
            570 < minute <= 580 and recv % MINUTE_NS == 0
        )
        self._interval(instrument, recv)
        self._definition(instrument, recv, row.get("symbol"))

    def _prices(
        self, prices: tuple[Decimal | None, Decimal | None], sizes: tuple[int, int]
    ) -> None:
        for side, price, size in zip(("bid", "ask"), prices, sizes, strict=True):
            self.counts[f"missing_{side}"] += price is None
            self.counts[f"zero_{side}"] += price == 0
            self.counts[f"negative_{side}"] += price is not None and price < 0
            self.counts[f"zero_{side}_size"] += size == 0
        bid, ask = prices
        if bid is not None and ask is not None:
            self.counts["crossed_quotes"] += bid > ask
            self.counts["locked_quotes"] += bid == ask

    def _interval(self, instrument: int, recv: int) -> None:
        if instrument not in self.instruments:
            if len(self.instruments) >= MAX_INSTRUMENTS:
                raise ValueError("Instrument state limit exceeded; inspection refused")
            self.instruments[instrument] = _Instrument()
        state = self.instruments[instrument]
        state.rows += 1
        if state.previous is not None:
            self.counts["out_of_order_per_instrument"] += recv < state.previous
            self.counts["same_timestamp_per_instrument"] += recv == state.previous
        state.previous = recv
        if self.start <= recv < self.end and recv % MINUTE_NS == 0:
            slot = (recv - self.start) // MINUTE_NS
            self.counts["duplicate_instrument_minute"] += bool(state.minutes & (1 << slot))
            state.minutes |= 1 << slot

    def _definition(self, instrument: int, recv: int, symbol: str | None) -> None:
        self.counts["missing_embedded_symbol"] += not bool(symbol)
        mapped = {s for start, end, s in self.mappings.get(instrument, []) if start <= recv < end}
        if self.mappings:
            self.counts["missing_dated_mapping"] += not mapped
            self.counts["ambiguous_dated_mapping"] += len(mapped) > 1
            if len(mapped) == 1:
                mapped_symbol = next(iter(mapped))
                self.counts["embedded_mapping_mismatch"] += bool(symbol and symbol != mapped_symbol)
                symbol = symbol or mapped_symbol
        definition = _definition_at(self.definitions.get(instrument, []), recv)
        if definition is None:
            self.counts["no_definition_at_or_before_label"] += 1
            return
        self.counts[_identity(definition, symbol)] += 1
        try:
            expiry = pd.Timestamp(definition["expiration"]).date()
            quote_date = (
                pd.Timestamp(recv, unit="ns", tz="UTC").tz_convert("America/New_York").date()
            )
            self.counts["definition_expiration_date_before_quote_date"] += expiry < quote_date
        except (ValueError, TypeError):
            self.counts["invalid_definition_expiration"] += 1
        self.counts["definition_timestamp_order_only"] += self.legacy
        self.counts["definition_available_by_interval_label"] += not self.legacy


def inspect_cbbo_schema(
    quotes_path: Path,
    *,
    request: dict[str, Any],
    metadata_path: Path,
    definitions_path: Path | None = None,
    symbology_path: Path | None = None,
) -> dict[str, Any]:
    """Inspect one registered SPY minute envelope; no data acquisition or trading.

    Metadata must be the matching vendor metadata.json or job-details.json.
    Definitions and symbology are optional, with missing coverage reported.
    External mappings establish dated identity, not historical publication time.
    Modern labels are the earliest possible interval availability, not execution
    times. Legacy event-clock labels establish no receive-time availability.
    """
    if (
        request.get("dataset") != "OPRA.PILLAR"
        or request.get("schema") != "cbbo-1m"
        or request.get("symbols") != ["SPY.OPT"]
        or request.get("stype_in") != "parent"
    ):
        raise ValueError("Expected parent SPY OPRA CBBO-1m request")
    start, end = (_required_stamp(request[k]) for k in ("start", "end"))
    if not 0 < end - start <= 24 * 60 * MINUTE_NS or start % MINUTE_NS or end % MINUTE_NS:
        raise ValueError("Require minute-aligned request of at most one day")
    if start < LEGACY_END < end:
        raise ValueError("Do not combine legacy and capture-clock regimes")
    paths = {"quotes": quotes_path, "metadata": metadata_path}
    for label, path in (("definitions", definitions_path), ("symbology", symbology_path)):
        if path:
            paths[label] = path
    inputs = {label: _fingerprint(path) for label, path in paths.items()}
    metadata = _metadata(metadata_path, request)
    opener = gzip.open if quotes_path.suffix == ".gz" else open
    with opener(quotes_path, "rt", encoding="utf-8-sig", newline="") as stream:
        columns = next(csv.reader(stream), [])
    definitions, definition_counts = _definitions(definitions_path)
    state = _Inspection(start, end, start < LEGACY_END, definitions, _mappings(symbology_path))
    for row in _rows(quotes_path, QUOTE_FIELDS):
        state.observe(row)
    slots = (end - start) // MINUTE_NS
    observed = sum(item.minutes.bit_count() for item in state.instruments.values())
    for label, path in paths.items():
        if _fingerprint(path) != inputs[label]:
            raise ValueError("Input changed during inspection; report refused")
    inputs["metadata"].update(metadata)
    return {
        "status": "SCHEMA_INSPECTED_NOT_BACKTESTED",
        "as_of": pd.Timestamp.now(tz="UTC").isoformat(),
        "schema": "cbbo-1m",
        "expected_rtype": 193,
        "inputs": inputs,
        "columns": columns,
        "validated_field_types": {
            "timestamps": "ts_recv/ts_event: offset ISO8601 or integer nanoseconds; null allowed",
            "integers": "rtype/flags uint8; publisher IDs uint16; instrument/quote sizes uint32",
            "prices": "bid_px_00/ask_px_00 finite decimal or documented undefined sentinel",
            "other_columns": "Preserved in input file; no type or trading semantics inferred",
        },
        "request": {
            k: request[k] for k in ("dataset", "schema", "symbols", "stype_in", "start", "end")
        },
        "legacy_subsampled": state.legacy,
        "counts": dict(sorted(state.counts.items())),
        "flag_histogram": dict(sorted(state.flags.items())),
        "rtype_histogram": dict(sorted(state.rtypes.items())),
        "definitions": dict(definition_counts),
        "timestamps": {
            "minimum_receive_ns": state.minimum_recv,
            "maximum_receive_ns": state.maximum_recv,
            "quote_update_timestamp_available": False,
            "receive_is_verified_capture_time": False,
            "availability": "unknown_event_clock_override"
            if state.legacy
            else "no_earlier_than_label",
            "definition_joins": "latest max(ts_recv,ts_event)<=label; conflicts unresolved",
        },
        "intervals": {
            "observed_instruments": len(state.instruments),
            "grid_slots_per_observed_instrument": slots,
            "observed_instrument_minute_labels": observed,
            "unobserved_instrument_minute_labels": slots * len(state.instruments) - observed,
            "interpretation": (
                "Receive-label grid only; no-record intervals may mean no trade/quote update. "
                "Not a count of lost data. Unobserved instruments are not included. "
                "Legacy labels are not verified interval ends."
            ),
        },
        "limitations": [
            "Local hashes identify inputs; vendor integrity verification belongs to acquisition.",
            "A minute snapshot does not establish quote freshness, an executable or atomic fill.",
            "Last-trade ts_event can be absent or old; it is not quote age.",
            "Publisher flag value 2 is preserved and has no additional OPRA meaning.",
            "Bad-book and bad-receive-time flags remain reported; no flag is erased.",
            "Legacy best-venue fields are not reliable venue attribution.",
            "No trades, P&L, annual return, strategy selection or broker action computed.",
        ],
        "sources": SOURCES,
    }
