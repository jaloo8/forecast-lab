import argparse
import json
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from scripts.acquire_options_extension import credit_evidence, reserve_amount, wait_done


@pytest.mark.parametrize("estimate", ["NaN", "Infinity", "-1"])
def test_reservation_refuses_bad_estimates(estimate):
    with pytest.raises(ValueError, match="estimate"):
        reserve_amount(estimate)


def test_reservation_has_margin_and_never_rounds_down():
    assert reserve_amount("0.026882439852") == Decimal("0.0303")
    assert reserve_amount("0") == Decimal("0.0001")


def test_authorization_and_snapshot_age_are_not_fabricated(tmp_path):
    path = tmp_path / "evidence.json"
    now = datetime.now(UTC)
    evidence = dict(
        available="124",
        observed_at=now.isoformat(),
        expires_at=(now + timedelta(days=1)).isoformat(),
        verified=True,
        cash_budget_usd="0",
        additional_cap_usd="10",
    )
    path.write_text(json.dumps(evidence))
    args = argparse.Namespace(submit_approved=False, credit_evidence=path)
    with pytest.raises(ValueError, match="approval"):
        credit_evidence(args)
    args.submit_approved = True
    _, snapshot = credit_evidence(args)
    assert snapshot.observed_at == now and snapshot.deduct_imports
    with pytest.raises(ValueError, match="fresh"):
        snapshot.validate(Decimal("0.1"), now + timedelta(minutes=6))
    evidence["cash_budget_usd"] = "1"
    path.write_text(json.dumps(evidence))
    with pytest.raises(ValueError, match="authorization"):
        credit_evidence(args)


def test_polling_never_resubmits(monkeypatch):
    class Client:
        def __init__(self, states):
            self.states = iter(states)

        def details(self, job):
            assert job == "known"
            return {"state": next(self.states)}

    monkeypatch.setattr(time, "sleep", lambda _: None)
    assert wait_done(Client(["queued", "done"]), "known", time.monotonic() + 10) == {
        "state": "done"
    }
    assert wait_done(Client(["processing"]), "known", time.monotonic() - 1) is None
    with pytest.raises(ValueError, match="Unexpected"):
        wait_done(Client(["failed"]), "known", time.monotonic() + 10)
