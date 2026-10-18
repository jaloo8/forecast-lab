"""Research observation history cannot silently rewrite prior market evidence."""

from pathlib import Path

import pytest

from kq.equities.observations import observation_folder, prior_observation, save_observation


def test_observations_are_idempotent_and_conflicting_times_are_rejected(tmp_path: Path) -> None:
    first = {"captured_at": "2026-09-28T03:00:00Z", "bars": [1]}
    second = {"captured_at": "2026-09-28T04:00:00Z", "bars": [2]}
    assert prior_observation(tmp_path, first) is None
    saved = save_observation(tmp_path, first)
    assert save_observation(tmp_path, first) == saved
    assert prior_observation(tmp_path, second) == first
    with pytest.raises(ValueError, match="conflicting"):
        save_observation(tmp_path, {**first, "bars": [3]})
    save_observation(tmp_path, second)
    assert prior_observation(tmp_path, second) == first
    with pytest.raises(ValueError, match="older"):
        prior_observation(tmp_path, first)


def test_tampered_archive_is_not_accepted(tmp_path: Path) -> None:
    snapshot = {"captured_at": "2026-09-28T03:00:00Z", "bars": []}
    path = save_observation(tmp_path, snapshot)
    path.write_text('{"captured_at":"2026-09-28T03:00:00Z","bars":[9]}', encoding="utf-8")
    with pytest.raises(ValueError, match="digest"):
        prior_observation(tmp_path, snapshot)


def test_another_decision_cannot_advance_prior_price_evidence(tmp_path: Path) -> None:
    first = observation_folder(tmp_path, {"selected": ["AAA"]})
    other = observation_folder(tmp_path, {"selected": ["BBB"]})
    original = {"captured_at": "2026-09-28T03:00:00Z", "bars": [1]}
    revised = {"captured_at": "2026-09-28T04:00:00Z", "bars": [2]}
    save_observation(first, original)
    save_observation(other, revised)
    assert prior_observation(first, revised) == original
