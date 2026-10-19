from pathlib import Path

import pandas as pd
import pytest
from scripts.run_options_pilot import cash_summary, select_pair


def chain() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "raw_symbol": f"SPY   261009C{strike * 1000:08d}",
                "strike_price": str(strike),
                "expiration": "2026-10-09T00:00:00Z",
                "instrument_class": "C",
                "underlying": "SPY",
                "security_update_action": "A",
                "contract_multiplier": "100",
                "ts_recv": "2026-10-08T10:30:00Z",
                "ts_event": "2026-10-08T10:29:59Z",
            }
            for strike in (774, 775, 776, 777)
        ]
    )


def test_nearest_signal_close_tie_lower_and_next_calendar_expiry(tmp_path: Path) -> None:
    path = tmp_path / "chain.csv"
    chain().to_csv(path, index=False)
    assert select_pair(path, pd.Timestamp("2026-10-08T13:50:00Z"), 775.5) == (
        "SPY   261009C00775000",
        "SPY   261009C00776000",
    )


def test_future_listing_and_deleted_short_are_not_available(tmp_path: Path) -> None:
    frame = chain()
    frame.loc[frame.strike_price.eq("775"), "ts_recv"] = "2026-10-08T14:00:00Z"
    path = tmp_path / "chain.csv"
    frame.to_csv(path, index=False)
    with pytest.raises(ValueError, match="short"):
        select_pair(path, pd.Timestamp("2026-10-08T13:50:00Z"), 775)
    frame = chain()
    frame.loc[frame.strike_price.eq("776"), "security_update_action"] = "D"
    frame.to_csv(path, index=False)
    with pytest.raises(ValueError, match="short"):
        select_pair(path, pd.Timestamp("2026-10-08T13:50:00Z"), 775)


def test_no_friday_to_monday_expiry_substitution(tmp_path: Path) -> None:
    frame = chain()
    frame["expiration"] = "2026-10-12T00:00:00Z"
    frame["ts_recv"] = "2026-10-09T10:30:00Z"
    path = tmp_path / "chain.csv"
    frame.to_csv(path, index=False)
    with pytest.raises(ValueError, match="chain"):
        select_pair(path, pd.Timestamp("2026-10-09T13:50:00Z"), 775)


@pytest.mark.parametrize(
    "field,value", [("ts_recv", "2026-10-08T00:30:00Z"), ("contract_multiplier", "10")]
)
def test_previous_local_day_and_nonstandard_contract_cannot_win(tmp_path: Path, field, value):
    frame = chain()
    frame.loc[frame.strike_price.eq("774"), field] = value
    path = tmp_path / "chain.csv"
    frame.to_csv(path, index=False)
    assert select_pair(path, pd.Timestamp("2026-10-08T13:50:00Z"), 774.2)[0].endswith("00775000")


def test_undefined_multiplier_requires_explicit_mapping(tmp_path: Path):
    frame = chain()
    frame["contract_multiplier"] = "2147483647"
    path = tmp_path / "chain.csv"
    frame.to_csv(path, index=False)
    with pytest.raises(ValueError, match="chain"):
        select_pair(path, pd.Timestamp("2026-10-08T13:50:00Z"), 775)
    assert select_pair(
        path, pd.Timestamp("2026-10-08T13:50:00Z"), 775, confirm_standard_spy_100=True
    )


def test_unresolved_totals_are_not_reported_as_zero_profit():
    frame = pd.DataFrame(
        {
            "status": ["unresolved_exit", "skipped_entry"],
            "net_cash": [None, None],
            "entry_debit": [50, None],
        }
    )
    assert cash_summary(frame) == {
        "closed_net_cash": None,
        "closed_count": 0,
        "unresolved": 1,
        "unresolved_entry_debit": 50,
    }
