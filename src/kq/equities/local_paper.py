"""Isolated, manual local paper accounting; never a broker or market-data client.

One immutable registration starts a new $1,000 book at the actual local UTC time.
Only later, explicitly imported quotes can fill an already persisted intent. Input
source identities/hashes are attribution supplied by the operator, not independent
authentication of a feed. Sale proceeds stay restricted: v1 has no settlement,
corporate-action, assignment, exercise, spread, short, or historical replay API.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Any

Json = dict[str, Any]
CENT = Decimal("0.01")
ZERO = Decimal("0.00")
DATABASE_NAME = "local-paper.sqlite"
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}\Z")
_BOOK_ID = re.compile(r"[a-z][a-z0-9-]{0,63}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_NUMBER = re.compile(r"(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,8})?\Z")
_MAX_EVENTS = 100_000
_SCHEMA = """
CREATE TABLE events (
    sequence INTEGER PRIMARY KEY,
    at TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    previous_hash TEXT NOT NULL,
    event_hash TEXT NOT NULL UNIQUE
);
CREATE TRIGGER events_no_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'append-only events'); END;
CREATE TRIGGER events_no_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'append-only events'); END;
"""


class PaperError(ValueError):
    """A fail-closed contract, state, provenance, or accounting refusal."""


def _utcnow() -> datetime:
    """Private clock seam for artificial tests; public APIs never accept a clock."""
    return datetime.now(UTC)


def _stamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise PaperError("Timezone-aware UTC clock required")
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def _time(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or len(value) > 40:
        raise PaperError(f"{name} must be an ISO timestamp with an explicit timezone")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PaperError(f"Invalid {name}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PaperError(f"{name} requires an explicit timezone")
    return parsed.astimezone(UTC)


def _decimal(value: Any, name: str, *, cents: bool = False) -> Decimal:
    if not isinstance(value, str) or _NUMBER.fullmatch(value) is None:
        raise PaperError(f"{name} must be a bounded, nonnegative plain Decimal string")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:  # Defensive even if the lexical gate changes.
        raise PaperError(f"Invalid {name}") from exc
    if cents and result != result.quantize(CENT):
        raise PaperError(f"{name} must be an exact number of cents")
    return result


def _integer(value: Any, name: str, maximum: int = 1_000_000) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        raise PaperError(f"{name} must be a positive bounded integer")
    return value


def _text(value: Any, name: str, *, digest: bool = False) -> str:
    pattern = _DIGEST if digest else _IDENTIFIER
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise PaperError(f"Invalid {name}")
    return value


def _keys(value: Any, expected: set[str], name: str) -> Json:
    if not isinstance(value, dict) or set(value) != expected:
        raise PaperError(f"{name} requires exactly these fields: {sorted(expected)}")
    return value


def _canonical(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise PaperError("Only finite JSON values are accepted") from exc


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _engine_hash() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _safe_path(value: Path, *, directory: bool = True) -> Path:
    """Reject links/junctions, UNC storage, traversal, and ambiguous path aliases."""
    path = Path(value)
    if ".." in path.parts or str(path).startswith(("\\\\", "//")):
        raise PaperError("Book storage must use a local path without traversal")
    path = path.absolute()
    for item in (*reversed(path.parents), path):
        if item.is_symlink() or item.is_junction():
            raise PaperError("Linked or junction book paths are refused")
    if not path.exists() or (directory and not path.is_dir()):
        raise PaperError("An existing, ordinary local directory is required")
    if not directory and (not path.is_file() or path.stat().st_nlink != 1):
        raise PaperError("An ordinary, non-hardlinked database is required")
    return path


def _instrument(value: Any, asset_type: str) -> Json:
    fields = {"instrument_id", "symbol", "definition_sha256", "definition_source", "multiplier"}
    if asset_type == "option":
        fields |= {
            "underlying",
            "right",
            "strike",
            "expiration_date",
            "last_tradable_at",
            "standard_deliverable",
        }
    obj = _keys(value, fields, "instrument")
    _text(obj["instrument_id"], "instrument_id")
    # A provider contract ID is allowed; standard deliverables require explicit evidence.
    if not isinstance(obj["symbol"], str) or not re.fullmatch(r"[A-Z0-9 .-]{1,32}", obj["symbol"]):
        raise PaperError("Invalid symbol")
    _text(obj["definition_sha256"], "definition_sha256", digest=True)
    source = obj["definition_source"]
    if (
        not isinstance(source, str)
        or not 1 <= len(source) <= 256
        or any(ord(char) < 32 for char in source)
    ):
        raise PaperError("Definition source must be a bounded printable attribution")
    expected_multiplier = 1 if asset_type == "stock" else 100
    if type(obj["multiplier"]) is not int or obj["multiplier"] != expected_multiplier:
        raise PaperError("Only whole stocks or standard 100-share long options are supported")
    if asset_type == "option":
        if obj["standard_deliverable"] is not True or obj["right"] not in ("call", "put"):
            raise PaperError("Option must have an explicitly evidenced standard deliverable")
        _text(obj["underlying"], "underlying")
        if _decimal(obj["strike"], "strike") <= 0:
            raise PaperError("Option strike must be positive")
        cutoff = _time(obj["last_tradable_at"], "last_tradable_at")
        try:
            expiration = date.fromisoformat(obj["expiration_date"])
        except (TypeError, ValueError) as exc:
            raise PaperError("expiration_date must be an ISO date") from exc
        if cutoff.date() > expiration or expiration.isoformat() != obj["expiration_date"]:
            raise PaperError("Last tradable cutoff cannot follow the stated expiration date")
    return json.loads(_canonical(obj))  # type: ignore[no-any-return]


def _registration(value: Any, launched: datetime) -> Json:  # noqa: PLR0912 - explicit frozen gates.
    fields = {
        "schema_version",
        "book_id",
        "strategy_id",
        "strategy_sha256",
        "initial_cash",
        "asset_type",
        "instruments",
        "allowed_sources",
        "stock_slippage_bps",
        "stock_fee_per_order",
        "option_slippage_per_unit",
        "option_fee_per_contract",
        "max_entry_debit",
        "max_quote_age_seconds",
        "max_capture_delay_seconds",
    }
    obj = _keys(value, fields, "registration")
    if type(obj["schema_version"]) is not int or obj["schema_version"] != 1:
        raise PaperError("Unsupported registration version")
    if not isinstance(obj["book_id"], str) or _BOOK_ID.fullmatch(obj["book_id"]) is None:
        raise PaperError("Book ID must be a lower-case directory-safe identifier")
    _text(obj["strategy_id"], "strategy_id")
    _text(obj["strategy_sha256"], "strategy_sha256", digest=True)
    if _decimal(obj["initial_cash"], "initial_cash", cents=True) != Decimal("1000.00"):
        raise PaperError("Every new book starts with exactly $1,000")
    if obj["asset_type"] not in ("stock", "option"):
        raise PaperError("Only stock or option books are supported")
    instruments = obj["instruments"]
    if not isinstance(instruments, list) or not 1 <= len(instruments) <= 100:
        raise PaperError("Register between one and 100 exact instruments")
    checked = [_instrument(item, obj["asset_type"]) for item in instruments]
    if len({item["instrument_id"] for item in checked}) != len(checked):
        raise PaperError("Duplicate instrument IDs")
    if len({item["symbol"] for item in checked}) != len(checked):
        raise PaperError("Duplicate instrument symbols")
    if obj["asset_type"] == "option" and any(
        _time(item["last_tradable_at"], "last_tradable_at") <= launched for item in checked
    ):
        raise PaperError("Option definitions must remain tradable after launch")
    sources = obj["allowed_sources"]
    if not isinstance(sources, list) or not 1 <= len(sources) <= 20:
        raise PaperError("Register a bounded source allowlist")
    for source in sources:
        _text(source, "source_id")
    if len(set(sources)) != len(sources):
        raise PaperError("Duplicate source IDs")
    fixed_costs = {
        "stock_slippage_bps": Decimal("10"),
        "stock_fee_per_order": ZERO,
        "option_slippage_per_unit": Decimal("0.01"),
        "option_fee_per_contract": Decimal("0.65"),
    }
    for name, expected in fixed_costs.items():
        if _decimal(obj[name], name) != expected:
            raise PaperError(f"v1 requires the registered fixed cost {name}={expected}")
    maximum = _decimal(obj["max_entry_debit"], "max_entry_debit", cents=True)
    if not ZERO < maximum <= Decimal("1000.00"):
        raise PaperError("max_entry_debit must be positive and at most $1,000")
    _integer(obj["max_quote_age_seconds"], "max_quote_age_seconds", 60)
    _integer(obj["max_capture_delay_seconds"], "max_capture_delay_seconds", 5)
    return json.loads(_canonical(obj))  # type: ignore[no-any-return]


@dataclass
class _Ledger:
    registration: Json
    launch: Json
    events: list[Json] = field(default_factory=list)
    cash: Decimal = Decimal("1000.00")
    restricted: Decimal = ZERO
    positions: dict[str, int] = field(default_factory=dict)
    intents: dict[str, Json] = field(default_factory=dict)
    quotes: dict[str, Json] = field(default_factory=dict)
    latest_quotes: dict[str, str] = field(default_factory=dict)
    filled_quotes: set[str] = field(default_factory=set)

    def instrument(self, identifier: str) -> Json:
        for item in self.registration["instruments"]:
            if item["instrument_id"] == identifier:
                return dict(item)
        raise PaperError("Instrument is not registered")

    def pending(self) -> Json | None:
        return next((item for item in self.intents.values() if item["status"] == "PENDING"), None)

    def exit_reserve(self) -> Decimal:
        if self.registration["asset_type"] == "stock":
            return ZERO
        return sum((Decimal(qty) * Decimal("0.65") for qty in self.positions.values()), ZERO)

    def available(self) -> Decimal:
        return self.cash - self.restricted - self.exit_reserve()

    def expired(self, now: datetime) -> list[str]:
        if self.registration["asset_type"] != "option":
            return []
        return [
            key
            for key, quantity in self.positions.items()
            if quantity
            and now >= _time(self.instrument(key)["last_tradable_at"], "last_tradable_at")
        ]


def _validate_intent(state: _Ledger, value: Any, now: datetime) -> Json:
    fields = {
        "intent_id",
        "instrument_id",
        "side",
        "quantity",
        "max_debit",
        "signal_observed_at",
        "signal_evidence_sha256",
    }
    obj = _keys(value, fields, "intent")
    _text(obj["intent_id"], "intent_id")
    _text(obj["instrument_id"], "instrument_id")
    instrument = state.instrument(obj["instrument_id"])
    _text(obj["signal_evidence_sha256"], "signal_evidence_sha256", digest=True)
    observed = _time(obj["signal_observed_at"], "signal_observed_at")
    if not _time(state.launch["launched_at"], "launched_at") <= observed <= now:
        raise PaperError("Signal observation must be after launch and no later than local receipt")
    if obj["side"] not in ("buy", "sell"):
        raise PaperError("Only a long buy or held-position sell is supported")
    quantity = _integer(obj["quantity"], "quantity")
    cap = _decimal(obj["max_debit"], "max_debit", cents=True)
    if state.pending() is not None:
        raise PaperError("Only one pending intent per book is permitted")
    if state.expired(now):
        raise PaperError("Unresolved expired positions block new intents")
    if state.registration["asset_type"] == "option" and now >= _time(
        instrument["last_tradable_at"], "last_tradable_at"
    ):
        raise PaperError("Option is at or beyond its last tradable instant")
    if obj["side"] == "buy":
        if not ZERO < cap <= Decimal(state.registration["max_entry_debit"]):
            raise PaperError("Intent debit exceeds the immutable entry cap")
        if cap > state.available():
            raise PaperError("Insufficient spendable settled cash for the reservation")
    elif cap != ZERO or quantity > state.positions.get(obj["instrument_id"], 0):
        raise PaperError("Sell requires held units and zero debit cap; shorts are refused")
    return json.loads(_canonical(obj))  # type: ignore[no-any-return]


def _quote_envelope(state: _Ledger, value: Any, now: datetime) -> Json:
    fields = {
        "quote_id",
        "instrument_id",
        "source_id",
        "payload_sha256",
        "event_time",
        "received_at",
        "bid",
        "ask",
        "bid_size",
        "ask_size",
        "data_status",
        "quote_condition",
    }
    obj = _keys(value, fields, "quote")
    if len(_canonical(obj)) > 4096:
        raise PaperError("Quote record exceeds the bounded input size")
    for key in ("quote_id", "instrument_id", "source_id"):
        _text(obj[key], key)
    state.instrument(obj["instrument_id"])
    _text(obj["payload_sha256"], "payload_sha256", digest=True)
    if any(
        item["request"]["payload_sha256"] == obj["payload_sha256"] for item in state.quotes.values()
    ):
        raise PaperError("Known payload bytes cannot become another quote observation")
    if obj["source_id"] not in state.registration["allowed_sources"]:
        raise PaperError("Quote source is not registered")
    event = _time(obj["event_time"], "event_time")
    received = _time(obj["received_at"], "received_at")
    launch = _time(state.launch["launched_at"], "launched_at")
    if not launch < event <= received <= now:
        raise PaperError("Quote timestamps must follow launch and precede local import")
    previous_id = state.latest_quotes.get(obj["instrument_id"])
    if previous_id is not None:
        previous = state.quotes[previous_id]["request"]
        if event <= _time(previous["event_time"], "event_time") or received < _time(
            previous["received_at"], "received_at"
        ):
            raise PaperError("Regressing or ambiguous replacement quote")
    return json.loads(_canonical(obj))  # type: ignore[no-any-return]


def _quote_quality(state: _Ledger, obj: Json, now: datetime) -> str | None:
    """A known newer bad observation invalidates any earlier good book state."""
    try:
        if obj["data_status"] != "real_time" or obj["quote_condition"] != "regular":
            raise PaperError("Delayed, indicative, or unknown-condition quotes are refused")
        bid, ask = _decimal(obj["bid"], "bid"), _decimal(obj["ask"], "ask")
        if ask <= ZERO or bid > ask:
            raise PaperError("Quote must have a positive ask and an uncrossed bid/ask")
        _integer(obj["bid_size"], "bid_size", 1_000_000_000)
        _integer(obj["ask_size"], "ask_size", 1_000_000_000)
        event = _time(obj["event_time"], "event_time")
        received = _time(obj["received_at"], "received_at")
        if (received - event).total_seconds() > state.registration["max_capture_delay_seconds"]:
            raise PaperError("Capture delay exceeds the registered limit")
        if (now - event).total_seconds() > state.registration["max_quote_age_seconds"]:
            raise PaperError("Stale quote")
    except PaperError as exc:
        return str(exc)
    return None


def _economics(state: _Ledger, quote: Json, quantity: int, side: str) -> Json:
    """Conservative cents for cash; preserve the exact Decimal execution price."""
    with localcontext() as context:
        context.prec = 40
        stock = state.registration["asset_type"] == "stock"
        raw = Decimal(quote["ask"] if side == "buy" else quote["bid"])
        slip = raw * Decimal("0.001") if stock else Decimal("0.01")
        price = raw + slip if side == "buy" else raw - slip
        if price <= ZERO:
            raise PaperError("No positive liquidation/execution price after slippage")
        units = quantity * (1 if stock else 100)
        gross = (price * units).quantize(
            CENT, rounding=ROUND_CEILING if side == "buy" else ROUND_FLOOR
        )
        fee = ZERO if stock else Decimal(quantity) * Decimal("0.65")
        cash_amount = gross + fee if side == "buy" else gross - fee
        if cash_amount <= ZERO:
            raise PaperError("No positive cash proceeds after fees")
        return {
            "execution_price": str(price),
            "gross": f"{gross:.2f}",
            "fee": f"{fee:.2f}",
            "cash_amount": f"{cash_amount:.2f}",
            "exit_reserve_added": f"{fee if side == 'buy' else ZERO:.2f}",
        }


def _execution(  # noqa: PLR0912 - explicit fill eligibility gates.
    state: _Ledger, intent_id: str, quote_id: str, now: datetime
) -> Json:
    intent = state.intents.get(intent_id)
    quote = state.quotes.get(quote_id)
    if intent is None or intent["status"] != "PENDING" or quote is None:
        raise PaperError("A pending intent and an already imported quote are required")
    request, observation = intent["request"], quote["request"]
    if request["instrument_id"] != observation["instrument_id"]:
        raise PaperError("Quote and intent instruments differ")
    if quote_id in state.filled_quotes:
        raise PaperError("A quote cannot be reused for another fill")
    if state.latest_quotes[request["instrument_id"]] != quote_id:
        raise PaperError("Only the latest observed quote can be used")
    if quote["rejection_reason"] is not None:
        raise PaperError("The latest quote is unqualified")
    if intent["ready_at"] is None:
        raise PaperError("Intent requires its post-commit readiness marker")
    intent_at = _time(intent["ready_at"], "intent readiness time")
    event_at = _time(observation["event_time"], "event_time")
    if not intent_at < event_at or not intent_at < _time(quote["at"], "import time"):
        raise PaperError("Quote must occur and be imported strictly after durable intent")
    if (
        not event_at <= now
        or (now - event_at).total_seconds() > state.registration["max_quote_age_seconds"]
    ):
        raise PaperError("Quote expired before execution")
    if state.expired(now):
        raise PaperError("Unresolved expired positions block execution")
    instrument = state.instrument(request["instrument_id"])
    if state.registration["asset_type"] == "option" and now >= _time(
        instrument["last_tradable_at"], "last_tradable_at"
    ):
        raise PaperError("Option reached its last tradable instant")
    quantity, side = request["quantity"], request["side"]
    if observation["ask_size" if side == "buy" else "bid_size"] < quantity:
        raise PaperError("Displayed side size cannot cover the whole order; no partial fills")
    result = _economics(state, observation, quantity, side)
    amount = Decimal(result["cash_amount"])
    if side == "buy":
        total = amount + Decimal(result["exit_reserve_added"])
        if total > Decimal(request["max_debit"]) or total > state.available():
            raise PaperError("Fill and exit reserve exceed funded intent cap")
    elif quantity > state.positions.get(request["instrument_id"], 0):
        raise PaperError("Sell quantity exceeds held units")
    return {
        "intent_id": intent_id,
        "quote_id": quote_id,
        "instrument_id": request["instrument_id"],
        "side": side,
        "quantity": quantity,
        **result,
    }


def _event(sequence: int, at: str, kind: str, payload: Json, previous: str) -> Json:
    body = {
        "sequence": sequence,
        "at": at,
        "kind": kind,
        "payload": payload,
        "previous_hash": previous,
    }
    return {**body, "event_hash": _hash(body)}


def _apply(state: _Ledger, event: Json) -> None:  # noqa: PLR0912, PLR0915 - single event transition.
    kind, payload = event["kind"], event["payload"]
    now = _time(event["at"], "event time")
    if kind == "INTENT":
        request = _validate_intent(state, payload, now)
        if request["intent_id"] in state.intents:
            raise PaperError("Repeated intent event")
        state.intents[request["intent_id"]] = {
            "request": request,
            "at": event["at"],
            "status": "PENDING",
            "ready_at": None,
        }
    elif kind == "INTENT_READY":
        _keys(payload, {"intent_id"}, "intent readiness")
        intent = state.intents.get(payload["intent_id"])
        if intent is None or intent["status"] != "PENDING" or intent["ready_at"] is not None:
            raise PaperError("Readiness requires an existing unready pending intent")
        intent["ready_at"] = event["at"]
    elif kind in {"QUOTE", "QUOTE_REJECTED"}:
        envelope = (
            payload
            if kind == "QUOTE"
            else _keys(payload, {"request", "rejection_reason"}, "rejected quote")["request"]
        )
        request = _quote_envelope(state, envelope, now)
        reason = _quote_quality(state, request, now)
        if (kind == "QUOTE" and reason is not None) or (
            kind == "QUOTE_REJECTED" and (reason is None or reason != payload["rejection_reason"])
        ):
            raise PaperError("Quote quality event does not match its recorded evidence")
        if request["quote_id"] in state.quotes:
            raise PaperError("Repeated quote event")
        state.quotes[request["quote_id"]] = {
            "request": request,
            "at": event["at"],
            "rejection_reason": reason,
        }
        state.latest_quotes[request["instrument_id"]] = request["quote_id"]
    elif kind == "CANCEL":
        _keys(payload, {"intent_id"}, "cancellation")
        intent = state.intents.get(payload["intent_id"])
        if intent is None or intent["status"] != "PENDING":
            raise PaperError("Cancellation requires a pending intent")
        intent["status"] = "CANCELLED"
    elif kind == "FILL":
        expected = _execution(state, payload.get("intent_id", ""), payload.get("quote_id", ""), now)
        if payload != expected:
            raise PaperError("Fill economics fail deterministic event replay")
        intent = state.intents[payload["intent_id"]]
        key, quantity = payload["instrument_id"], payload["quantity"]
        amount = Decimal(payload["cash_amount"])
        if payload["side"] == "buy":
            state.cash -= amount
            state.positions[key] = state.positions.get(key, 0) + quantity
        else:
            state.cash += amount
            state.restricted += amount
            state.positions[key] -= quantity
        intent["status"] = "FILLED"
        intent["fill"] = payload
        state.filled_quotes.add(payload["quote_id"])
        if (
            state.cash < ZERO
            or state.available() < ZERO
            or any(q < 0 for q in state.positions.values())
        ):
            raise PaperError("Funding invariant violated")
    else:
        raise PaperError("Unknown event kind")
    state.events.append(event)


def _load(connection: sqlite3.Connection) -> _Ledger:
    rows = connection.execute(
        "SELECT sequence,at,kind,payload,previous_hash,event_hash "
        "FROM events ORDER BY sequence LIMIT ?",
        (_MAX_EVENTS + 1,),
    ).fetchall()
    if not rows or len(rows) > _MAX_EVENTS:
        raise PaperError("Missing launch or event limit exceeded")
    state: _Ledger | None = None
    previous = "0" * 64
    previous_at: datetime | None = None
    for count, row in enumerate(rows, start=1):
        try:
            payload = json.loads(row[3])
        except (ValueError, TypeError) as exc:
            raise PaperError("Invalid stored event JSON") from exc
        if not isinstance(payload, dict) or _canonical(payload) != row[3]:
            raise PaperError("Stored event must be canonical JSON without duplicate keys")
        expected = _event(count, row[1], row[2], payload, previous)
        if row[0] != count or row[4] != previous or row[5] != expected["event_hash"]:
            raise PaperError("Event sequence or hash chain is corrupt")
        at = _time(row[1], "event time")
        if previous_at is not None and at < previous_at:
            raise PaperError("Event chronology regressed")
        if count == 1:
            _keys(
                payload,
                {"registration", "launched_at", "hostname", "book_path", "engine_sha256"},
                "launch",
            )
            if row[2] != "LAUNCH" or payload["launched_at"] != row[1]:
                raise PaperError("Invalid immutable launch event")
            registration = _registration(payload["registration"], at)
            state = _Ledger(registration, payload, [expected])
        else:
            if state is None:  # pragma: no cover - established by first row.
                raise PaperError("No launch")
            _apply(state, expected)
        previous, previous_at = expected["event_hash"], at
    if state is None:  # pragma: no cover - empty rows rejected above.
        raise PaperError("No launch")
    return state


def _append(
    connection: sqlite3.Connection, state: _Ledger, kind: str, payload: Json, now: datetime
) -> Json:
    if len(state.events) >= _MAX_EVENTS:
        raise PaperError("Event limit reached; do not reset this book")
    event = _event(
        len(state.events) + 1, _stamp(now), kind, payload, state.events[-1]["event_hash"]
    )
    _apply(state, event)
    connection.execute(
        "INSERT INTO events VALUES (?,?,?,?,?,?)",
        (
            event["sequence"],
            event["at"],
            kind,
            _canonical(payload),
            event["previous_hash"],
            event["event_hash"],
        ),
    )
    return event


def _identity_matches(state: _Ledger, path: Path) -> bool:
    return bool(
        state.launch["hostname"] == platform.node().casefold()
        and state.launch["book_path"] == str(path)
        and state.launch["engine_sha256"] == _engine_hash()
    )


@contextmanager
def _open(
    book_path: Path, *, write: bool
) -> Iterator[tuple[sqlite3.Connection, _Ledger, datetime]]:
    path = _safe_path(book_path)
    database = _safe_path(path / DATABASE_NAME, directory=False)
    uri = database.as_uri() + ("?mode=rw" if write else "?mode=ro")
    try:
        connection = sqlite3.connect(uri, uri=True, timeout=10, isolation_level=None)
    except sqlite3.Error as exc:
        raise PaperError(f"Local storage failed: {type(exc).__name__}") from exc
    try:
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        state = _load(connection)
        now = _time(_stamp(_utcnow()), "local clock")
        if now < _time(state.events[-1]["at"], "last event time"):
            raise PaperError("Local clock regressed behind durable events")
        if write and not _identity_matches(state, path):
            raise PaperError("Writer host, local path or engine fingerprint differs from launch")
        yield connection, state, now
        connection.commit()
    except (sqlite3.Error, OSError) as exc:
        connection.rollback()
        raise PaperError(f"Local storage failed: {type(exc).__name__}") from exc
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def create_book(root: Path, registration: Json) -> Json:
    """Create one new empty book; an existing directory is never reused/reset."""
    parent = _safe_path(root)
    if any((item / DATABASE_NAME).exists() for item in (parent, *parent.parents)):
        raise PaperError("A new book cannot overlap an existing book directory")
    now = _time(_stamp(_utcnow()), "local clock")
    reg = _registration(registration, now)
    destination = parent / reg["book_id"]
    if os.path.lexists(destination):
        raise PaperError("Book destination already exists; no reset or replacement is allowed")
    try:
        destination.mkdir(mode=0o700)
    except OSError as exc:
        raise PaperError("Could not claim a new independent book directory") from exc
    launch = {
        "registration": reg,
        "launched_at": _stamp(now),
        "hostname": platform.node().casefold(),
        "book_path": str(destination),
        "engine_sha256": _engine_hash(),
    }
    event = _event(1, _stamp(now), "LAUNCH", launch, "0" * 64)
    try:
        with closing(sqlite3.connect(destination / DATABASE_NAME)) as connection:
            connection.execute("PRAGMA synchronous=FULL")
            connection.executescript(_SCHEMA)
            connection.execute(
                "INSERT INTO events VALUES (?,?,?,?,?,?)",
                (
                    1,
                    event["at"],
                    "LAUNCH",
                    _canonical(launch),
                    event["previous_hash"],
                    event["event_hash"],
                ),
            )
            connection.commit()
    except (OSError, sqlite3.Error) as exc:
        raise PaperError(
            "Initialization failed; preserve the incomplete directory for inspection"
        ) from exc
    return inspect_book(destination)


def submit_intent(book_path: Path, intent: Json) -> Json:
    """Durably reserve cash or held units before a future quote is observed."""
    replayed = False
    with _open(book_path, write=True) as (connection, state, now):
        if not isinstance(intent, dict):
            raise PaperError("Intent must be an object")
        identifier = _text(intent.get("intent_id"), "intent_id")
        existing = state.intents.get(identifier)
        if existing is not None:
            if _canonical(existing["request"]) != _canonical(intent):
                raise PaperError("Conflicting retry for intent ID")
            if existing["ready_at"] is not None or existing["status"] != "PENDING":
                return {"replayed": True, "intent": existing}
            replayed = True
        else:
            request = _validate_intent(state, intent, now)
            _append(connection, state, "INTENT", request, now)
    # The first transaction has committed before this timestamp is sampled.
    # A crash here leaves a reservation that cannot fill; an identical retry
    # safely completes readiness. No future quote may precede this marker.
    with _open(book_path, write=True) as (connection, state, now):
        existing = state.intents[identifier]
        if existing["status"] != "PENDING" or existing["ready_at"] is not None:
            return {"replayed": replayed, "intent": existing}
        event = _append(connection, state, "INTENT_READY", {"intent_id": identifier}, now)
        return {"replayed": replayed, "event": event, "intent": state.intents[identifier]}


def observe_quote(book_path: Path, quote: Json) -> Json:
    """Import one attributed quote; this does not fill any pending order."""
    with _open(book_path, write=True) as (connection, state, now):
        if not isinstance(quote, dict):
            raise PaperError("Quote must be an object")
        identifier = _text(quote.get("quote_id"), "quote_id")
        existing = state.quotes.get(identifier)
        if existing is not None:
            if _canonical(existing["request"]) != _canonical(quote):
                raise PaperError("Conflicting retry for quote ID")
            return {
                "replayed": True,
                "accepted": existing["rejection_reason"] is None,
                "quote": existing,
            }
        request = _quote_envelope(state, quote, now)
        reason = _quote_quality(state, request, now)
        kind = "QUOTE" if reason is None else "QUOTE_REJECTED"
        payload = request if reason is None else {"request": request, "rejection_reason": reason}
        event = _append(connection, state, kind, payload, now)
        return {
            "replayed": False,
            "accepted": reason is None,
            "event": event,
            "quote": state.quotes[identifier],
        }


def fill_intent(book_path: Path, intent_id: str, quote_id: str) -> Json:
    """Explicitly simulate one whole fill, atomically conserving funded cash."""
    _text(intent_id, "intent_id")
    _text(quote_id, "quote_id")
    with _open(book_path, write=True) as (connection, state, now):
        existing = state.intents.get(intent_id)
        if existing is not None and existing["status"] == "FILLED":
            if existing["fill"]["quote_id"] != quote_id:
                raise PaperError("Conflicting retry for filled intent")
            return {"replayed": True, "fill": existing["fill"]}
        result = _execution(state, intent_id, quote_id, now)
        event = _append(connection, state, "FILL", result, now)
        return {"replayed": False, "event": event, "fill": result}


def cancel_intent(book_path: Path, intent_id: str) -> Json:
    """Release an unfilled reservation without deleting its original intent."""
    _text(intent_id, "intent_id")
    with _open(book_path, write=True) as (connection, state, now):
        existing = state.intents.get(intent_id)
        if existing is None:
            raise PaperError("Unknown intent")
        if existing["status"] == "CANCELLED":
            return {"replayed": True, "intent": existing}
        if existing["status"] != "PENDING":
            raise PaperError("A filled intent cannot be cancelled")
        event = _append(connection, state, "CANCEL", {"intent_id": intent_id}, now)
        return {"replayed": False, "event": event, "intent": state.intents[intent_id]}


def _valuation(state: _Ledger, now: datetime) -> tuple[list[Json], Decimal | None]:
    positions: list[Json] = []
    nav: Decimal | None = state.cash
    for identifier, quantity in sorted(state.positions.items()):
        if not quantity:
            continue
        mark: Decimal | None = None
        reason = "MISSING_QUOTE"
        quote_id = state.latest_quotes.get(identifier)
        if identifier in state.expired(now):
            reason = "UNRESOLVED_EXPIRY"
        elif quote_id is not None:
            observation = state.quotes[quote_id]["request"]
            age = (now - _time(observation["event_time"], "event_time")).total_seconds()
            if state.quotes[quote_id]["rejection_reason"] is not None:
                reason = "REJECTED_LATEST_QUOTE"
            elif age > state.registration["max_quote_age_seconds"]:
                reason = "STALE_QUOTE"
            elif observation["bid_size"] < quantity:
                reason = "INSUFFICIENT_BID_SIZE"
            else:
                try:
                    mark = Decimal(_economics(state, observation, quantity, "sell")["cash_amount"])
                    reason = "OBSERVED_NET_LIQUIDATION_MODEL"
                except PaperError:
                    reason = "NO_POSITIVE_NET_LIQUIDATION_PRICE"
        if mark is None:
            nav = None
        elif nav is not None:
            nav += mark
        positions.append(
            {
                "instrument_id": identifier,
                "quantity": quantity,
                "mark_status": reason,
                "net_liquidation_value": None if mark is None else f"{mark:.2f}",
                "quote_id": quote_id,
            }
        )
    return positions, nav


def inspect_book(book_path: Path) -> Json:
    """Replay and validate every event, then report conservative known/unknown NAV."""
    path = _safe_path(book_path)
    with _open(path, write=False) as (_, state, now):
        pending = state.pending()
        reservation = ZERO if pending is None else Decimal(pending["request"]["max_debit"])
        positions, nav = _valuation(state, now)
        status = "READY_NO_POSITIONS" if not positions else "OPEN_POSITIONS"
        if nav is None:
            status = "UNPRICED_POSITIONS"
        if state.expired(now):
            status = "UNRESOLVED_EXPIRY"
        fees = sum(
            (Decimal(item["payload"]["fee"]) for item in state.events if item["kind"] == "FILL"),
            ZERO,
        )
        return {
            "evidence_level": "local_input_simulation",
            "book_id": state.registration["book_id"],
            "book_path": str(path),
            "registration_sha256": _hash(state.registration),
            "registration": state.registration,
            "launch_at": state.launch["launched_at"],
            "last_event_at": state.events[-1]["at"],
            "observed_at": _stamp(now),
            "event_count": len(state.events),
            "last_event_hash": state.events[-1]["event_hash"],
            "cumulative_fees": f"{fees:.2f}",
            "writer_identity_matches": _identity_matches(state, path),
            "broker_connected": False,
            "automated_execution": False,
            "status": status,
            "cash": f"{state.cash:.2f}",
            "restricted_cash": f"{state.restricted:.2f}",
            "exit_fee_reserve": f"{state.exit_reserve():.2f}",
            "pending_cash_reserve": f"{reservation:.2f}",
            "spendable_cash": f"{state.available() - reservation:.2f}",
            "pending_intent": pending,
            "positions": positions,
            "nav": None if nav is None else f"{nav:.2f}",
            "sale_proceeds_policy": "restricted_without_settlement_adapter",
            "input_authenticity": "operator_attributed_not_independently_authenticated",
        }
