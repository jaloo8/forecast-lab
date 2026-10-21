"""Artificial accounting and failure fixtures; no market or broker performance."""

from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from threading import Barrier

import pytest

from kq.equities import local_paper as paper

T0 = datetime(2027, 1, 11, 15, 0, tzinfo=UTC)
SHA = "a" * 64
OPTION = "SPY270111C00600000"


def stamp(seconds: float = 0) -> str:
    return (T0 + timedelta(seconds=seconds)).isoformat()


def registration(kind: str = "stock", book_id: str = "trial-a") -> dict:
    instrument = {
        "instrument_id": "SPY" if kind == "stock" else OPTION,
        "symbol": "SPY" if kind == "stock" else OPTION,
        "definition_sha256": SHA,
        "definition_source": "artificial-contract-fixture",
        "multiplier": 1 if kind == "stock" else 100,
    }
    if kind == "option":
        instrument.update(
            underlying="SPY",
            right="call",
            strike="600.00",
            expiration_date="2027-01-11",
            last_tradable_at=stamp(3600),
            standard_deliverable=True,
        )
    return {
        "schema_version": 1,
        "book_id": book_id,
        "strategy_id": "artificial-accounting-fixture-v1",
        "strategy_sha256": SHA,
        "initial_cash": "1000.00",
        "asset_type": kind,
        "instruments": [instrument],
        "allowed_sources": ["fixture-feed"],
        "stock_slippage_bps": "10",
        "stock_fee_per_order": "0.00",
        "option_slippage_per_unit": "0.01",
        "option_fee_per_contract": "0.65",
        "max_entry_debit": "1000.00" if kind == "stock" else "100.00",
        "max_quote_age_seconds": 60,
        "max_capture_delay_seconds": 5,
    }


def intent(
    ident: str = "buy-a", *, side: str = "buy", quantity: int = 2, kind: str = "stock"
) -> dict:
    return {
        "intent_id": ident,
        "instrument_id": "SPY" if kind == "stock" else OPTION,
        "side": side,
        "quantity": quantity,
        "max_debit": ("300.00" if kind == "stock" else "100.00") if side == "buy" else "0.00",
        "signal_observed_at": stamp(0.5),
        "signal_evidence_sha256": SHA,
    }


def quote(
    ident: str = "q-a",
    *,
    at: float = 2,
    kind: str = "stock",
    bid: str = "100.00",
    ask: str = "100.10",
) -> dict:
    return {
        "quote_id": ident,
        "instrument_id": "SPY" if kind == "stock" else OPTION,
        "source_id": "fixture-feed",
        "payload_sha256": hashlib.sha256(ident.encode()).hexdigest(),
        "event_time": stamp(at),
        "received_at": stamp(at + 0.1),
        "bid": bid,
        "ask": ask,
        "bid_size": 10,
        "ask_size": 10,
        "data_status": "real_time",
        "quote_condition": "regular",
    }


@pytest.fixture
def clock(monkeypatch):
    current = [T0]
    monkeypatch.setattr(paper, "_utcnow", lambda: current[0])

    def advance(seconds: float) -> None:
        current[0] = T0 + timedelta(seconds=seconds)

    return advance


def new_book(tmp_path: Path, clock, kind: str = "stock", book_id: str = "trial-a") -> Path:
    clock(0)
    paper.create_book(tmp_path, registration(kind, book_id))
    return tmp_path / book_id


def money(status: dict, key: str) -> Decimal:
    return Decimal(status[key])


def buy_stock(book: Path, clock) -> None:
    clock(1)
    paper.submit_intent(book, intent())
    clock(3)
    paper.observe_quote(book, quote())
    paper.fill_intent(book, "buy-a", "q-a")


def buy_option(book: Path, clock) -> None:
    clock(1)
    paper.submit_intent(book, intent(quantity=1, kind="option"))
    clock(3)
    paper.observe_quote(book, quote(kind="option", bid="0.70", ask="0.80"))
    paper.fill_intent(book, "buy-a", "q-a")


def test_stock_money_reconciles_without_engine_arithmetic(tmp_path, clock):
    book = new_book(tmp_path, clock)
    buy_stock(book, clock)
    bought = paper.inspect_book(book)
    assert money(bought, "cash") == Decimal("799.59")
    assert money(bought, "restricted_cash") == 0
    assert money(bought, "nav") == Decimal("999.39")
    clock(4)
    closing = intent("sell-a", side="sell")
    closing["signal_observed_at"] = stamp(3.5)
    paper.submit_intent(book, closing)
    clock(6)
    paper.observe_quote(book, quote("q-close", at=5, bid="109.90", ask="110.00"))
    paper.fill_intent(book, "sell-a", "q-close")
    closed = paper.inspect_book(book)
    assert money(closed, "cash") == Decimal("1019.17")
    assert money(closed, "restricted_cash") == Decimal("219.58")
    assert money(closed, "spendable_cash") == Decimal("799.59")
    assert money(closed, "nav") == Decimal("1019.17")
    assert money(closed, "exit_fee_reserve") == 0


def test_option_contract_multiplier_fees_and_settlement_reserve(tmp_path, clock):
    book = new_book(tmp_path, clock, "option")
    buy_option(book, clock)
    bought = paper.inspect_book(book)
    assert money(bought, "cash") == Decimal("918.35")
    assert money(bought, "exit_fee_reserve") == Decimal("0.65")
    assert money(bought, "spendable_cash") == Decimal("917.70")
    assert money(bought, "nav") == Decimal("986.70")
    assert money(bought, "cumulative_fees") == Decimal("0.65")
    clock(4)
    closing = intent("sell-a", side="sell", quantity=1, kind="option")
    closing["signal_observed_at"] = stamp(3.5)
    paper.submit_intent(book, closing)
    clock(6)
    paper.observe_quote(book, quote("q-close", at=5, kind="option", bid="1.20", ask="1.30"))
    paper.fill_intent(book, "sell-a", "q-close")
    closed = paper.inspect_book(book)
    assert money(closed, "cash") == Decimal("1036.70")
    assert money(closed, "nav") == Decimal("1036.70")
    assert money(closed, "restricted_cash") == Decimal("118.35")
    assert money(closed, "spendable_cash") == Decimal("918.35")
    assert money(closed, "exit_fee_reserve") == 0
    assert money(closed, "cumulative_fees") == Decimal("1.30")


def test_books_have_independent_balances_and_initialization_never_resets(tmp_path, clock):
    first = new_book(tmp_path, clock)
    second = new_book(tmp_path, clock, book_id="trial-b")
    buy_stock(first, clock)
    before = paper.inspect_book(first)
    with pytest.raises(paper.PaperError):
        paper.create_book(tmp_path, registration())
    assert paper.inspect_book(first) == before
    assert money(paper.inspect_book(second), "cash") == Decimal("1000.00")


@pytest.mark.parametrize(
    "change",
    [
        {"initial_cash": "100"},
        {"initial_cash": "NaN"},
        {"asset_type": "future"},
        {"book_id": "../escape"},
        {"book_id": "trial/a"},
        {"stock_slippage_bps": "-1"},
        {"option_fee_per_contract": "-0.01"},
        {"max_entry_debit": "1001.00"},
    ],
)
def test_invalid_registration_cannot_create_account(tmp_path, clock, change):
    clock(0)
    spec = registration()
    spec.update(change)
    with pytest.raises(paper.PaperError):
        paper.create_book(tmp_path, spec)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "change",
    [
        {"multiplier": 10},
        {"multiplier": 1000},
        {"standard_deliverable": False},
        {"right": "spread"},
        {"strike": "0.00"},
        {"last_tradable_at": stamp(-1)},
        {"definition_sha256": "not-a-hash"},
    ],
)
def test_nonstandard_or_expired_option_definition_rejected(tmp_path, clock, change):
    clock(0)
    spec = registration("option")
    spec["instruments"][0].update(change)
    with pytest.raises(paper.PaperError):
        paper.create_book(tmp_path, spec)


@pytest.mark.parametrize("quantity", [0, -1, 0.5, True, "2"])
def test_only_positive_integer_quantity_can_be_reserved(tmp_path, clock, quantity):
    book = new_book(tmp_path, clock)
    clock(1)
    request = intent()
    request["quantity"] = quantity
    with pytest.raises(paper.PaperError):
        paper.submit_intent(book, request)
    assert money(paper.inspect_book(book), "pending_cash_reserve") == 0


def test_no_unfunded_long_or_naked_short(tmp_path, clock):
    book = new_book(tmp_path, clock)
    clock(1)
    with pytest.raises(paper.PaperError):
        paper.submit_intent(book, intent(side="sell"))
    request = intent()
    request["max_debit"] = "1000.01"
    with pytest.raises(paper.PaperError):
        paper.submit_intent(book, request)
    assert money(paper.inspect_book(book), "cash") == Decimal("1000.00")


@pytest.mark.parametrize("when", [-1, 1.1])
def test_signal_must_be_since_launch_and_no_later_than_intent(tmp_path, clock, when):
    book = new_book(tmp_path, clock)
    clock(1)
    request = intent()
    request["signal_observed_at"] = stamp(when)
    with pytest.raises(paper.PaperError):
        paper.submit_intent(book, request)


def test_exact_retries_are_idempotent_conflicts_are_rejected(tmp_path, clock):
    book = new_book(tmp_path, clock)
    clock(1)
    paper.submit_intent(book, intent())
    first = paper.inspect_book(book)
    clock(2)
    paper.submit_intent(book, intent())
    assert paper.inspect_book(book)["event_count"] == first["event_count"]
    conflict = intent(quantity=3)
    with pytest.raises(paper.PaperError):
        paper.submit_intent(book, conflict)
    clock(3)
    paper.observe_quote(book, quote())
    observed = paper.inspect_book(book)
    paper.observe_quote(book, quote())
    assert paper.inspect_book(book)["event_count"] == observed["event_count"]
    conflict = quote(ask="100.11")
    with pytest.raises(paper.PaperError):
        paper.observe_quote(book, conflict)
    paper.fill_intent(book, "buy-a", "q-a")
    filled = paper.inspect_book(book)
    paper.fill_intent(book, "buy-a", "q-a")
    assert paper.inspect_book(book) == filled


def test_cancel_releases_money_without_trade_and_is_idempotent(tmp_path, clock):
    book = new_book(tmp_path, clock)
    clock(1)
    paper.submit_intent(book, intent())
    assert money(paper.inspect_book(book), "pending_cash_reserve") == Decimal("300.00")
    paper.cancel_intent(book, "buy-a")
    cancelled = paper.inspect_book(book)
    assert money(cancelled, "pending_cash_reserve") == 0
    assert money(cancelled, "cash") == Decimal("1000.00")
    paper.cancel_intent(book, "buy-a")
    assert paper.inspect_book(book) == cancelled
    clock(3)
    paper.observe_quote(book, quote())
    with pytest.raises(paper.PaperError):
        paper.fill_intent(book, "buy-a", "q-a")


@pytest.mark.parametrize(
    "change",
    [
        {"bid": "101.00"},
        {"bid": "NaN"},
        {"ask": "Infinity"},
        {"ask": "-1"},
        {"bid_size": 0},
        {"ask_size": -1},
        {"ask_size": True},
        {"data_status": "indicative"},
        {"quote_condition": "halted"},
        {"source_id": "unregistered-feed"},
        {"instrument_id": "QQQ"},
        {"payload_sha256": "bad"},
        {"event_time": stamp(4)},
        {"received_at": stamp(4)},
        {"received_at": stamp(1)},
        {"event_time": "2027-01-11T15:00:02"},
    ],
)
def test_unqualified_quote_rejected_without_cash_change(tmp_path, clock, change):
    book = new_book(tmp_path, clock)
    clock(1)
    paper.submit_intent(book, intent())
    clock(3)
    malformed = quote()
    malformed.update(change)
    quality_fields = {"bid", "ask", "bid_size", "ask_size", "data_status", "quote_condition"}
    if set(change) <= quality_fields:
        assert paper.observe_quote(book, malformed)["accepted"] is False
        with pytest.raises(paper.PaperError):
            paper.fill_intent(book, "buy-a", malformed["quote_id"])
    else:
        with pytest.raises(paper.PaperError):
            paper.observe_quote(book, malformed)
    assert money(paper.inspect_book(book), "cash") == Decimal("1000.00")


def test_quote_delay_and_staleness_are_independent_gates(tmp_path, clock):
    book = new_book(tmp_path, clock)
    clock(1)
    paper.submit_intent(book, intent())
    clock(10)
    delayed = quote()
    delayed["received_at"] = stamp(8)
    assert paper.observe_quote(book, delayed)["accepted"] is False
    clock(70)
    stale = quote("older-received", at=8)
    assert paper.observe_quote(book, stale)["accepted"] is False


def test_quote_before_committed_intent_cannot_fill(tmp_path, clock):
    book = new_book(tmp_path, clock)
    clock(1)
    paper.observe_quote(book, quote(at=0.7))
    clock(2)
    paper.submit_intent(book, intent())
    with pytest.raises(paper.PaperError):
        paper.fill_intent(book, "buy-a", "q-a")
    assert money(paper.inspect_book(book), "cash") == Decimal("1000.00")


def test_stale_quote_at_execution_cannot_be_used_after_valid_capture(tmp_path, clock):
    book = new_book(tmp_path, clock)
    clock(1)
    paper.submit_intent(book, intent())
    clock(3)
    paper.observe_quote(book, quote())
    clock(63)
    with pytest.raises(paper.PaperError):
        paper.fill_intent(book, "buy-a", "q-a")
    assert money(paper.inspect_book(book), "cash") == Decimal("1000.00")


def test_insufficient_display_size_never_partially_fills(tmp_path, clock):
    book = new_book(tmp_path, clock)
    clock(1)
    paper.submit_intent(book, intent(quantity=3))
    clock(3)
    shallow = quote(ask="90.00", bid="89.90")
    shallow["ask_size"] = 2
    paper.observe_quote(book, shallow)
    with pytest.raises(paper.PaperError):
        paper.fill_intent(book, "buy-a", "q-a")
    status = paper.inspect_book(book)
    assert money(status, "cash") == Decimal("1000.00")
    assert money(status, "pending_cash_reserve") == Decimal("300.00")


def test_entry_budget_includes_commission_and_reserved_exit_commission(tmp_path, clock):
    book = new_book(tmp_path, clock, "option")
    clock(1)
    paper.submit_intent(book, intent(quantity=1, kind="option"))
    clock(3)
    paper.observe_quote(book, quote(kind="option", ask="0.98", bid="0.97"))
    with pytest.raises(paper.PaperError):
        paper.fill_intent(book, "buy-a", "q-a")
    assert money(paper.inspect_book(book), "cash") == Decimal("1000.00")


def test_unmarked_or_expired_option_is_unknown_and_never_zero_settled(tmp_path, clock):
    book = new_book(tmp_path, clock, "option")
    buy_option(book, clock)
    clock(64)
    stale = paper.inspect_book(book)
    assert stale["nav"] is None
    assert money(stale, "cash") == Decimal("918.35")
    clock(3601)
    expired = paper.inspect_book(book)
    assert expired["nav"] is None
    assert money(expired, "cash") == Decimal("918.35")
    assert money(expired, "exit_fee_reserve") == Decimal("0.65")
    with pytest.raises(paper.PaperError):
        paper.submit_intent(book, intent("late-close", side="sell", quantity=1, kind="option"))


def test_clock_rollback_cannot_backdate_mutations(tmp_path, clock):
    book = new_book(tmp_path, clock)
    buy_stock(book, clock)
    clock(2)
    with pytest.raises(paper.PaperError):
        paper.submit_intent(book, intent("late-close", side="sell"))


def test_simultaneous_intents_cannot_double_reserve_cash(tmp_path, clock):
    book = new_book(tmp_path, clock)
    clock(1)
    barrier = Barrier(2)

    def reserve(ident):
        barrier.wait(timeout=5)
        request = intent(ident)
        request["max_debit"] = "700.00"
        try:
            paper.submit_intent(book, request)
        except paper.PaperError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reserve, ["race-a", "race-b"]))
    assert sorted(results) == [False, True]
    status = paper.inspect_book(book)
    assert money(status, "pending_cash_reserve") == Decimal("700.00")
    assert money(status, "cash") == Decimal("1000.00")
    assert money(status, "spendable_cash") == Decimal("300.00")


def test_partial_sale_preserves_remaining_units_and_restricts_only_proceeds(tmp_path, clock):
    book = new_book(tmp_path, clock)
    buy_stock(book, clock)
    clock(4)
    request = intent("sell-one", side="sell", quantity=1)
    request["signal_observed_at"] = stamp(3.5)
    paper.submit_intent(book, request)
    clock(6)
    paper.observe_quote(book, quote("q-close", at=5, bid="109.90", ask="110.00"))
    paper.fill_intent(book, "sell-one", "q-close")
    status = paper.inspect_book(book)
    assert money(status, "cash") == Decimal("909.38")
    assert money(status, "restricted_cash") == Decimal("109.79")
    assert money(status, "nav") == Decimal("1019.17")
    clock(7)
    oversell = intent("sell-too-many", side="sell", quantity=2)
    oversell["signal_observed_at"] = stamp(6.5)
    with pytest.raises(paper.PaperError):
        paper.submit_intent(book, oversell)


def test_sale_proceeds_do_not_enable_an_unsettled_purchase(tmp_path, clock):
    book = new_book(tmp_path, clock)
    buy_stock(book, clock)
    clock(4)
    request = intent("sell-a", side="sell")
    request["signal_observed_at"] = stamp(3.5)
    paper.submit_intent(book, request)
    clock(6)
    paper.observe_quote(book, quote("q-close", at=5, bid="109.90", ask="110.00"))
    paper.fill_intent(book, "sell-a", "q-close")
    clock(7)
    request = intent("unsettled-buy")
    request.update(max_debit="800.00", signal_observed_at=stamp(6.5))
    with pytest.raises(paper.PaperError):
        paper.submit_intent(book, request)
    status = paper.inspect_book(book)
    assert money(status, "cash") == Decimal("1019.17")
    assert money(status, "spendable_cash") == Decimal("799.59")


def test_a_filled_quote_cannot_fund_a_second_intent(tmp_path, clock):
    book = new_book(tmp_path, clock)
    buy_stock(book, clock)
    clock(4)
    request = intent("buy-b")
    request["signal_observed_at"] = stamp(3.5)
    paper.submit_intent(book, request)
    with pytest.raises(paper.PaperError):
        paper.fill_intent(book, "buy-b", "q-a")
    assert money(paper.inspect_book(book), "cash") == Decimal("799.59")


def test_caller_mutation_does_not_rewrite_persisted_registration(tmp_path, clock):
    clock(0)
    original = registration()
    before = copy.deepcopy(original)
    paper.create_book(tmp_path, original)
    original["initial_cash"] = "50000.00"
    original["instruments"][0]["multiplier"] = 100
    book = tmp_path / before["book_id"]
    assert money(paper.inspect_book(book), "cash") == Decimal("1000.00")
    buy_stock(book, clock)
    assert money(paper.inspect_book(book), "cash") == Decimal("799.59")


def test_existing_book_cannot_be_parent_of_an_overlapping_book(tmp_path, clock):
    book = new_book(tmp_path, clock)
    with pytest.raises(paper.PaperError):
        paper.create_book(book, registration(book_id="nested"))
    assert not (book / "nested").exists()


def test_wrong_host_can_inspect_but_cannot_mutate(tmp_path, clock, monkeypatch):
    book = new_book(tmp_path, clock)
    clock(1)
    monkeypatch.setattr(paper.platform, "node", lambda: "a-different-machine")
    status = paper.inspect_book(book)
    assert status["writer_identity_matches"] is False
    with pytest.raises(paper.PaperError):
        paper.submit_intent(book, intent())
    assert paper.inspect_book(book)["event_count"] == 1


def test_modified_engine_refuses_existing_book_mutation(tmp_path, clock, monkeypatch):
    book = new_book(tmp_path, clock)
    clock(1)
    monkeypatch.setattr(paper, "_engine_hash", lambda: "f" * 64)
    assert paper.inspect_book(book)["writer_identity_matches"] is False
    with pytest.raises(paper.PaperError):
        paper.submit_intent(book, intent())


def test_failure_after_insert_rolls_back_entire_fill(tmp_path, clock, monkeypatch):
    book = new_book(tmp_path, clock)
    clock(1)
    paper.submit_intent(book, intent())
    clock(3)
    paper.observe_quote(book, quote())
    before = paper.inspect_book(book)
    append = paper._append

    def crash_after_insert(*args, **kwargs):
        append(*args, **kwargs)
        raise OSError("artificial failure after SQL insertion before commit")

    with monkeypatch.context() as patch:
        patch.setattr(paper, "_append", crash_after_insert)
        with pytest.raises(paper.PaperError):
            paper.fill_intent(book, "buy-a", "q-a")
    assert paper.inspect_book(book) == before
    paper.fill_intent(book, "buy-a", "q-a")
    assert money(paper.inspect_book(book), "cash") == Decimal("799.59")


def test_concurrent_identical_fill_debits_exactly_once(tmp_path, clock):
    book = new_book(tmp_path, clock)
    clock(1)
    paper.submit_intent(book, intent())
    clock(3)
    paper.observe_quote(book, quote())
    before = paper.inspect_book(book)["event_count"]
    barrier = Barrier(2)

    def fill(_):
        barrier.wait(timeout=5)
        return paper.fill_intent(book, "buy-a", "q-a")

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(fill, [0, 1]))
    assert sorted(item["replayed"] for item in results) == [False, True]
    status = paper.inspect_book(book)
    assert money(status, "cash") == Decimal("799.59")
    assert status["event_count"] == before + 1


@pytest.mark.parametrize(
    "corruption", ["payload", "hash", "missing-interior", "duplicate-json-key"]
)
def test_corrupt_history_is_rejected_without_automatic_repair(tmp_path, clock, corruption):
    book = new_book(tmp_path, clock)
    buy_stock(book, clock)
    database = book / paper.DATABASE_NAME
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TRIGGER events_no_update")
        connection.execute("DROP TRIGGER events_no_delete")
        if corruption == "payload":
            connection.execute("UPDATE events SET payload='{}' WHERE kind='FILL'")
        elif corruption == "hash":
            connection.execute("UPDATE events SET event_hash=? WHERE kind='FILL'", ("f" * 64,))
        elif corruption == "missing-interior":
            connection.execute("DELETE FROM events WHERE sequence=2")
        else:
            connection.execute(
                "UPDATE events SET payload=? WHERE kind='FILL'",
                ('{"intent_id":"buy-a","intent_id":"buy-b"}',),
            )
    before = database.read_bytes()
    with pytest.raises(paper.PaperError):
        paper.inspect_book(book)
    with pytest.raises(paper.PaperError):
        paper.submit_intent(book, intent("another"))
    assert database.read_bytes() == before


def test_even_a_rehashed_wrong_cash_fill_fails_accounting_replay(tmp_path, clock):
    book = new_book(tmp_path, clock)
    buy_stock(book, clock)
    with sqlite3.connect(book / paper.DATABASE_NAME) as connection:
        connection.execute("DROP TRIGGER events_no_update")
        row = connection.execute(
            "SELECT sequence,at,kind,payload,previous_hash FROM events WHERE kind='FILL'"
        ).fetchone()
        payload = json.loads(row[3])
        payload["cash_amount"] = "1.00"
        body = {
            "sequence": row[0],
            "at": row[1],
            "kind": row[2],
            "payload": payload,
            "previous_hash": row[4],
        }
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False)
        connection.execute(
            "UPDATE events SET payload=?,event_hash=? WHERE kind='FILL'",
            (
                json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False),
                hashlib.sha256(canonical.encode()).hexdigest(),
            ),
        )
    with pytest.raises(paper.PaperError, match="economics"):
        paper.inspect_book(book)


def test_missing_database_is_not_recreated_by_read_or_write(tmp_path, clock):
    book = new_book(tmp_path, clock)
    (book / paper.DATABASE_NAME).unlink()
    with pytest.raises(paper.PaperError):
        paper.inspect_book(book)
    with pytest.raises(paper.PaperError):
        paper.submit_intent(book, intent())
    assert not (book / paper.DATABASE_NAME).exists()


def test_zero_net_option_sale_is_unresolved_without_invented_cash(tmp_path, clock):
    book = new_book(tmp_path, clock, "option")
    buy_option(book, clock)
    clock(4)
    request = intent("sell-a", side="sell", quantity=1, kind="option")
    request["signal_observed_at"] = stamp(3.5)
    paper.submit_intent(book, request)
    clock(6)
    paper.observe_quote(
        book, quote("nearly-worthless", at=5, kind="option", bid="0.01", ask="0.02")
    )
    with pytest.raises(paper.PaperError):
        paper.fill_intent(book, "sell-a", "nearly-worthless")
    status = paper.inspect_book(book)
    assert status["nav"] is None
    assert money(status, "cash") == Decimal("918.35")
    assert money(status, "exit_fee_reserve") == Decimal("0.65")


def test_newer_bad_quote_blocks_good_quote_fill_and_then_recovers(tmp_path, clock):
    book = new_book(tmp_path, clock)
    clock(1)
    paper.submit_intent(book, intent())
    clock(3)
    paper.observe_quote(book, quote())
    clock(5)
    crossed = quote("bad-latest", at=4, bid="101.00", ask="100.00")
    assert paper.observe_quote(book, crossed)["accepted"] is False
    rejected = paper.inspect_book(book)
    assert paper.observe_quote(book, crossed)["replayed"] is True
    assert paper.inspect_book(book)["event_count"] == rejected["event_count"]
    for quote_id in ("q-a", "bad-latest"):
        with pytest.raises(paper.PaperError):
            paper.fill_intent(book, "buy-a", quote_id)
    clock(7)
    paper.observe_quote(book, quote("good-again", at=6))
    paper.fill_intent(book, "buy-a", "good-again")
    assert money(paper.inspect_book(book), "cash") == Decimal("799.59")


def test_newer_halt_makes_open_position_nav_unknown(tmp_path, clock):
    book = new_book(tmp_path, clock)
    buy_stock(book, clock)
    assert paper.inspect_book(book)["nav"] is not None
    clock(5)
    halted = quote("halted", at=4)
    halted["quote_condition"] = "halted"
    assert paper.observe_quote(book, halted)["accepted"] is False
    status = paper.inspect_book(book)
    assert status["nav"] is None
    assert money(status, "cash") == Decimal("799.59")
    assert status["positions"][0]["quantity"] == 2


def test_same_payload_cannot_be_retimestamped_as_a_new_quote(tmp_path, clock):
    book = new_book(tmp_path, clock)
    clock(1)
    old = quote("old", at=0.7)
    paper.observe_quote(book, old)
    clock(2)
    paper.submit_intent(book, intent())
    clock(4)
    forged = quote("new-identifier", at=3)
    forged["payload_sha256"] = old["payload_sha256"]
    with pytest.raises(paper.PaperError):
        paper.observe_quote(book, forged)
    assert money(paper.inspect_book(book), "cash") == Decimal("1000.00")


def test_interrupted_readiness_preserves_cash_reservation_and_requires_later_quote(
    tmp_path, clock, monkeypatch
):
    book = new_book(tmp_path, clock)
    clock(1)
    append = paper._append

    def interrupt_readiness(connection, state, kind, payload, now):
        if kind == "INTENT_READY":
            raise OSError("artificial interruption after durable intent commit")
        return append(connection, state, kind, payload, now)

    with monkeypatch.context() as patch:
        patch.setattr(paper, "_append", interrupt_readiness)
        with pytest.raises(paper.PaperError):
            paper.submit_intent(book, intent())
    interrupted = paper.inspect_book(book)
    assert money(interrupted, "cash") == Decimal("1000.00")
    assert money(interrupted, "pending_cash_reserve") == Decimal("300.00")
    clock(3)
    paper.observe_quote(book, quote("before-recovery", at=2))
    with pytest.raises(paper.PaperError):
        paper.fill_intent(book, "buy-a", "before-recovery")
    clock(4)
    paper.submit_intent(book, intent())
    assert money(paper.inspect_book(book), "pending_cash_reserve") == Decimal("300.00")
    with pytest.raises(paper.PaperError):
        paper.fill_intent(book, "buy-a", "before-recovery")
    clock(6)
    paper.observe_quote(book, quote("after-recovery", at=5))
    paper.fill_intent(book, "buy-a", "after-recovery")
    status = paper.inspect_book(book)
    assert money(status, "cash") == Decimal("799.59")
    assert money(status, "pending_cash_reserve") == 0


@pytest.mark.parametrize("ask,accepted", [("0.977", True), ("0.977001", False)])
def test_exact_options_cap_and_conservative_subcent_rounding(tmp_path, clock, ask, accepted):
    book = new_book(tmp_path, clock, "option")
    clock(1)
    paper.submit_intent(book, intent(quantity=1, kind="option"))
    clock(3)
    paper.observe_quote(book, quote(kind="option", bid="0.97", ask=ask))
    if accepted:
        paper.fill_intent(book, "buy-a", "q-a")
        status = paper.inspect_book(book)
        assert money(status, "cash") == Decimal("900.65")
        assert money(status, "spendable_cash") == Decimal("900.00")
        assert money(status, "exit_fee_reserve") == Decimal("0.65")
    else:
        with pytest.raises(paper.PaperError):
            paper.fill_intent(book, "buy-a", "q-a")
        assert money(paper.inspect_book(book), "cash") == Decimal("1000.00")


def test_option_cannot_fill_at_exact_cutoff_even_with_fresh_valid_quote(tmp_path, clock):
    book = new_book(tmp_path, clock, "option")
    clock(3598)
    request = intent(quantity=1, kind="option")
    request["signal_observed_at"] = stamp(3597)
    paper.submit_intent(book, request)
    clock(3599.5)
    paper.observe_quote(book, quote(kind="option", at=3599, bid="0.70", ask="0.80"))
    clock(3600)
    with pytest.raises(paper.PaperError):
        paper.fill_intent(book, "buy-a", "q-a")
    assert money(paper.inspect_book(book), "cash") == Decimal("1000.00")
