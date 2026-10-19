from dataclasses import replace

import pandas as pd
import pytest

from kq.equities import options_replay as replay

SYMBOLS = ("SPY   261009C00775000", "SPY   261009C00776000")
SIGNAL = pd.Timestamp("2026-10-08T13:30:00Z")
ENTRY = SIGNAL + pd.Timedelta(seconds=2)
EXIT = SIGNAL + pd.Timedelta(seconds=12)


@pytest.fixture
def source(tmp_path):
    before = str(SIGNAL - pd.Timedelta(hours=1))
    definitions = pd.DataFrame(
        {
            "instrument_id": [0, 1],
            "raw_symbol": SYMBOLS,
            "strike_price": ["775", "776"],
        }
    ).assign(
        ts_recv=before,
        ts_event=before,
        expiration="2026-10-09T00:00:00Z",
        instrument_class="C",
        underlying="SPY",
        security_update_action="A",
        contract_multiplier=2147483647,
    )
    quotes = pd.DataFrame(
        {
            "instrument_id": [0, 1] * 2,
            "symbol": SYMBOLS * 2,
            "ts_recv": [str(t - pd.Timedelta(nanoseconds=1)) for t in (ENTRY, ENTRY, EXIT, EXIT)],
            "ts_event": [str(t - pd.Timedelta(nanoseconds=2)) for t in (ENTRY, ENTRY, EXIT, EXIT)],
            "bid_px_00": [1.1, 0.7] * 2,
            "ask_px_00": [1.2, 0.8] * 2,
        }
    ).assign(action="A", flags=192, bid_sz_00=5, ask_sz_00=5, rtype=177, publisher_id=30)

    def read(defs=definitions, rows=quotes, confirm=True, allow_publisher=False):
        defs.to_csv(tmp_path / "defs.csv", index=False)
        rows.to_csv(tmp_path / "quotes.csv", index=False)
        return replay.read_call_quotes(
            tmp_path / "defs.csv",
            tmp_path / "quotes.csv",
            SYMBOLS,
            SIGNAL,
            (ENTRY, EXIT),
            confirm_standard_spy_100=confirm,
            allow_opra_publisher_flag=allow_publisher,
            chunksize=1,
        )

    return definitions, quotes, read


def test_nanosecond_selection_expiry_and_round_trip_costs(source):
    _, _, read = source
    seen = read()
    assert seen[ENTRY][0].as_of == ENTRY - pd.Timedelta(nanoseconds=1)
    assert str(seen[ENTRY][0].expiry) == "2026-10-09"
    result = replay.replay_trade(seen, signal_at=SIGNAL, entry_at=ENTRY, exit_at=EXIT)
    assert result.status == "closed"
    assert result.entry_debit == pytest.approx(53.3)
    assert result.exit_cash == pytest.approx(26.7)
    assert result.net_cash == pytest.approx(-26.6)


@pytest.mark.parametrize(
    "field,value",
    [
        ("flags", 8),
        ("flags", 4),
        ("flags", 2),
        ("flags", 1),
        ("action", "R"),
        ("ask_sz_00", 0),
        ("bid_px_00", 2),
        ("instrument_id", 999),
    ],
)
def test_latest_invalid_blocks_older_good_quote(source, field, value):
    _, rows, read = source
    bad = rows.iloc[[0]].assign(ts_recv=str(ENTRY), ts_event=str(ENTRY))
    bad[field] = value
    seen = read(rows=pd.concat([rows, bad], ignore_index=True))
    assert isinstance(seen[ENTRY], str)
    result = replay.replay_trade(seen, signal_at=SIGNAL, entry_at=ENTRY, exit_at=EXIT)
    assert result.status == "skipped_entry" and result.net_cash is None


@pytest.mark.parametrize("column", ["ts_recv", "ts_event"])
def test_future_receive_ignored_but_latest_future_event_blocks(source, column):
    _, rows, read = source
    future = rows.iloc[[0]].assign(ts_recv=str(ENTRY), ts_event=str(ENTRY), ask_sz_00=0)
    future[column] = str(ENTRY + pd.Timedelta(nanoseconds=1))
    assert isinstance(read(rows=pd.concat([rows, future]))[ENTRY], str) == (column == "ts_event")


def test_trade_cannot_refresh_stale_book_and_missing_exit_retains_debit(source):
    _, rows, read = source
    trade = rows.iloc[2:].assign(action="T")
    seen = read(rows=pd.concat([rows.iloc[:2], trade]))
    assert isinstance(seen[EXIT], str)
    result = replay.replay_trade(seen, signal_at=SIGNAL, entry_at=ENTRY, exit_at=EXIT)
    assert result.status == "unresolved_exit" and result.entry_debit == pytest.approx(53.3)
    assert result.exit_cash is None and result.net_cash is None
    assert (
        replay.replay_trade(
            {ENTRY: seen[ENTRY]}, signal_at=SIGNAL, entry_at=ENTRY, exit_at=EXIT
        ).status
        == "unresolved_exit"
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("strike_price", "776"),
        ("strike_price", "bad"),
        ("instrument_class", "P"),
        ("raw_symbol", "SPY7  261009C00775000"),
        ("expiration", "2026-10-08T00:00:00Z"),
        ("ts_recv", str(SIGNAL + pd.Timedelta(nanoseconds=1))),
        ("ts_event", str(SIGNAL + pd.Timedelta(nanoseconds=1))),
        ("ts_recv", "2026-10-07T13:00:00Z"),
        ("security_update_action", "D"),
        ("contract_multiplier", 10),
    ],
)
def test_mismatched_or_unavailable_definition_refused(source, field, value):
    defs, _, read = source
    defs.loc[0, field] = value
    assert isinstance(read(defs=defs)[ENTRY], str)


def test_undefined_multiplier_requires_confirmation(source):
    _, _, read = source
    assert "multiplier" in read(confirm=False)[ENTRY].lower()


def test_nanosecond_age_and_sync_boundaries(source):
    _, _, read = source
    seen = read()
    a, b = seen[ENTRY]
    for delta in (pd.Timedelta(seconds=5, nanoseconds=1), pd.Timedelta(seconds=1, nanoseconds=1)):
        changed = {
            ENTRY: (replace(a, as_of=ENTRY - delta), replace(b, as_of=ENTRY)),
            EXIT: seen[EXIT],
        }
        assert (
            replay.replay_trade(
                changed, signal_at=SIGNAL - pd.Timedelta(minutes=1), entry_at=ENTRY, exit_at=EXIT
            ).status
            == "skipped_entry"
        )


def test_definition_received_at_signal_is_causal(source):
    defs, _, read = source
    defs["ts_recv"] = str(SIGNAL)
    assert not isinstance(read(defs=defs)[ENTRY], str)


def test_publisher_flag_is_explicit_sensitivity_not_default(source):
    _, rows, read = source
    rows = rows.assign(flags=194)
    assert "publisher-specific" in read(rows=rows)[ENTRY]
    seen = read(rows=rows, allow_publisher=True)
    assert (
        replay.replay_trade(seen, signal_at=SIGNAL, entry_at=ENTRY, exit_at=EXIT).status == "closed"
    )


@pytest.mark.parametrize(
    "field,value",
    [("flags", 198), ("flags", 202), ("flags", 195), ("publisher_id", 22), ("rtype", 1)],
)
def test_publisher_sensitivity_never_allows_quality_failures_or_wrong_feed(source, field, value):
    _, rows, read = source
    rows = rows.assign(flags=194)
    rows[field] = value
    assert isinstance(read(rows=rows, allow_publisher=True)[ENTRY], str)
