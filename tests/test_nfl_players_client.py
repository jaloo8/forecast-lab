"""Tests for the NFL player-stats client (Fantasy F1a).

Every DataFrame here is a RECORDED REAL nflverse payload slice (2024 week 1,
KC + PHI; probe 2026-07-27) — the audit lesson: fixtures from reality, not
hand-written mocks. The nfl_data_py calls themselves are patched at the
``_import_*`` indirection points; the autouse network guard would kill any
un-patched fetch loudly.

Real-data pins worth knowing: Mahomes' week-1 line is 291 pass yds / 1 TD /
1 INT / 3 rush yds / 1 rec for 2 yds -> 14.14 standard points (the
4-pt-pass-TD arithmetic verified by hand) and 15.14 PPR.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from kq.clients import nfl_players
from kq.clients.nfl_players import (
    PlayerWeekStats,
    SnapCountRow,
    fetch_pfr_to_gsis,
    fetch_snap_counts,
    fetch_weekly_rosters,
    fetch_weekly_stats,
    merge_player_weeks,
    normalize_player_name,
)

FIXTURES = Path(__file__).parent / "fixtures" / "nfl_players"

MAHOMES_GSIS = "00-0033873"
MAHOMES_PFR = "MahoPa00"


def _weekly_df() -> pd.DataFrame:
    return pd.read_csv(FIXTURES / "weekly_2024_w1_kc_phi.csv")


def _snaps_df() -> pd.DataFrame:
    return pd.read_csv(FIXTURES / "snap_counts_2024_w1_kc_phi.csv")


def _rosters_df() -> pd.DataFrame:
    return pd.read_csv(FIXTURES / "weekly_rosters_2024_w1_kc_phi.csv")


def _ids_df() -> pd.DataFrame:
    return pd.read_csv(FIXTURES / "ids_kc_phi_2024w1.csv")


@pytest.fixture
def patched_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_weekly(years: list[int]) -> pd.DataFrame:
        df = _weekly_df()
        return df[df["season"].isin(years)].copy()

    def fake_snaps(years: list[int]) -> pd.DataFrame:
        df = _snaps_df()
        return df[df["season"].isin(years)].copy()

    def fake_rosters(years: list[int]) -> pd.DataFrame:
        df = _rosters_df()
        return df[df["season"].isin(years)].copy()

    monkeypatch.setattr(nfl_players, "_import_weekly", fake_weekly)
    monkeypatch.setattr(nfl_players, "_import_snap_counts", fake_snaps)
    monkeypatch.setattr(nfl_players, "_import_weekly_rosters", fake_rosters)
    monkeypatch.setattr(nfl_players, "_import_ids", _ids_df)


# --------------------------- weekly stats ---------------------------


def test_fetch_weekly_converts_all_fixture_rows(patched_sources: None) -> None:
    rows = fetch_weekly_stats([2024])
    assert len(rows) == 19  # every KC/PHI skill-player line in the recorded slice
    assert {r.team for r in rows} == {"KC", "PHI"}
    assert all(r.week == 1 and r.season == 2024 and r.season_type == "REG" for r in rows)


def test_fetch_weekly_real_mahomes_line(patched_sources: None) -> None:
    rows = {r.player_id: r for r in fetch_weekly_stats([2024])}
    m = rows[MAHOMES_GSIS]
    assert m.player_name == "Patrick Mahomes"
    assert m.position == "QB"
    assert m.opponent == "BAL"
    assert m.passing_yards == pytest.approx(291.0)
    assert m.passing_tds == 1
    assert m.interceptions == pytest.approx(1.0)
    assert m.carries == 2
    assert m.rushing_yards == pytest.approx(3.0)
    assert m.targets == 1
    assert m.receptions == 1
    assert m.receiving_yards == pytest.approx(2.0)
    assert m.fumbles_lost == pytest.approx(0.0)
    assert m.fantasy_points_std == pytest.approx(14.14, abs=1e-4)
    assert m.fantasy_points_ppr == pytest.approx(15.14, abs=1e-4)


def test_fetch_weekly_skips_failing_season_keeps_rest(
    monkeypatch: pytest.MonkeyPatch, patched_sources: None
) -> None:
    real = nfl_players._import_weekly

    def flaky(years: list[int]) -> pd.DataFrame:
        if 2023 in years:
            raise RuntimeError("404: season not published")
        return real(years)

    def no_new_scheme(_url: str) -> pd.DataFrame:
        raise RuntimeError("404: no new-scheme asset either")

    monkeypatch.setattr(nfl_players, "_import_weekly", flaky)
    monkeypatch.setattr(nfl_players.pd, "read_parquet", no_new_scheme)
    rows = fetch_weekly_stats([2023, 2024])
    assert len(rows) == 19
    assert {r.season for r in rows} == {2024}


# --------------------------- new-scheme fallback (2025+) ---------------------------


def _new_scheme_raw_df() -> pd.DataFrame:
    """RECORDED REAL 2025 payload (new nflverse release scheme, original
    column names incl. `team` / `passing_interceptions`, 145 columns)."""
    return pd.read_csv(FIXTURES / "stats_player_week_2025_w1_kc_phi.csv")


def test_fetch_weekly_2025_falls_back_to_new_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    """nfl_data_py's legacy asset 404s for 2025+ (live-verified): the
    fetcher must recover via the new-scheme asset and produce identically
    shaped rows."""
    seen_urls: list[str] = []

    def legacy_404(years: list[int]) -> pd.DataFrame:
        raise RuntimeError("HTTP Error 404: Not Found")

    def fake_read_parquet(url: str) -> pd.DataFrame:
        seen_urls.append(url)
        return _new_scheme_raw_df()

    monkeypatch.setattr(nfl_players, "_import_weekly", legacy_404)
    monkeypatch.setattr(nfl_players.pd, "read_parquet", fake_read_parquet)

    rows = fetch_weekly_stats([2025])
    assert seen_urls == [nfl_players.NFLVERSE_WEEKLY_URL_TEMPLATE.format(season=2025)]
    assert len(rows) == 22  # every KC/PHI offense-skill line in the recorded slice
    assert all(r.season == 2025 and r.week == 1 and r.season_type == "REG" for r in rows)
    assert {r.team for r in rows} == {"KC", "PHI"}
    mahomes = next(r for r in rows if r.player_id == MAHOMES_GSIS)
    assert mahomes.position == "QB"
    assert mahomes.passing_yards is not None and mahomes.passing_yards > 0
    # Real-data invariant verified at record time on all 22 rows: the new
    # scheme's PPR points equal standard + receptions, exactly.
    for r in rows:
        assert r.fantasy_points_ppr == pytest.approx(
            (r.fantasy_points_std or 0.0) + (r.receptions or 0), abs=0.02
        )


def test_new_scheme_reader_filters_and_renames(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = _new_scheme_raw_df()
    defense_row = raw.iloc[[0]].copy()
    defense_row["position_group"] = "DL"
    defense_row["player_id"] = "00-DEFENSE"
    monkeypatch.setattr(nfl_players.pd, "read_parquet", lambda url: pd.concat([raw, defense_row]))
    df = nfl_players._read_weekly_new_scheme(2025)
    assert "recent_team" in df.columns and "interceptions" in df.columns
    assert "00-DEFENSE" not in set(df["player_id"])
    assert len(df) == 22


def test_fetch_weekly_rejects_column_drift(
    monkeypatch: pytest.MonkeyPatch, patched_sources: None
) -> None:
    """A frame missing a required column is refused wholesale — parsing
    around schema drift would silently corrupt the training set."""
    df = _weekly_df().drop(columns=["fantasy_points"])
    monkeypatch.setattr(nfl_players, "_import_weekly", lambda years: df.copy())
    assert fetch_weekly_stats([2024]) == []


# --------------------------- snap counts ---------------------------


def test_fetch_snaps_converts_fixture(patched_sources: None) -> None:
    rows = fetch_snap_counts([2024])
    assert len(rows) == 93  # includes OL/defense — snap data is roster-wide
    taylor = next(r for r in rows if r.pfr_player_id == "TaylJa02")
    assert taylor.player_name == "Jawaan Taylor"
    assert taylor.team == "KC"
    assert taylor.opponent == "BAL"
    assert taylor.game_type == "REG"
    assert taylor.offense_snaps == pytest.approx(54.0)
    assert taylor.offense_pct == pytest.approx(1.0)


# --------------------------- rosters ---------------------------


def test_fetch_rosters_converts_fixture(patched_sources: None) -> None:
    rows = fetch_weekly_rosters([2024])
    assert len(rows) == 67
    assert {r.team for r in rows} == {"KC", "PHI"}
    assert MAHOMES_GSIS in {r.player_id for r in rows}
    assert any(r.depth_chart_position for r in rows)


# --------------------------- id crosswalk ---------------------------


def test_fetch_pfr_to_gsis_maps_real_ids(patched_sources: None) -> None:
    mapping = fetch_pfr_to_gsis()
    assert mapping[MAHOMES_PFR] == MAHOMES_GSIS


def test_fetch_pfr_to_gsis_failure_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> pd.DataFrame:
        raise RuntimeError("nflverse down")

    monkeypatch.setattr(nfl_players, "_import_ids", boom)
    assert fetch_pfr_to_gsis() == {}


# --------------------------- name normalization ---------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Patrick Mahomes", "patrick mahomes"),
        ("Marvin Harrison Jr.", "marvin harrison"),
        ("Odell Beckham Jr", "odell beckham"),
        ("De'Von Achane", "devon achane"),
        ("Amon-Ra St. Brown", "amon ra st brown"),
        ("Robert Griffin III", "robert griffin"),
    ],
)
def test_normalize_player_name(raw: str, expected: str) -> None:
    assert normalize_player_name(raw) == expected


# --------------------------- merge ---------------------------


def test_merge_real_fixture_joins_snaps_onto_stats(patched_sources: None) -> None:
    stats = fetch_weekly_stats([2024])
    snaps = fetch_snap_counts([2024])
    mapping = fetch_pfr_to_gsis()

    merged = merge_player_weeks(stats, snaps, mapping)
    assert len(merged) == 19  # one output row per stats row; snap-only players dropped
    m = next(r for r in merged if r.player_id == MAHOMES_GSIS)
    assert m.snaps == pytest.approx(54.0)  # KC ran 54 offensive plays vs BAL
    assert m.snap_pct == pytest.approx(1.0)
    assert m.fantasy_points_std == pytest.approx(14.14, abs=1e-4)
    assert m.red_zone_touches is None  # reserved column — no PBP aggregation yet
    n_matched = sum(1 for r in merged if r.snaps is not None)
    assert n_matched == 19  # every recorded skill player has a snap row


def _stats_row(*, player_id: str = "00-0099001", name: str = "Test Player") -> PlayerWeekStats:
    return PlayerWeekStats(
        player_id=player_id,
        player_name=name,
        position="WR",
        team="KC",
        season=2024,
        week=1,
        season_type="REG",
        opponent="BAL",
        targets=5,
        receptions=4,
        carries=0,
        passing_yards=None,
        passing_tds=None,
        interceptions=None,
        rushing_yards=None,
        rushing_tds=None,
        receiving_yards=61.0,
        receiving_tds=1,
        fumbles_lost=0.0,
        fantasy_points_std=12.1,
        fantasy_points_ppr=16.1,
    )


def _snap_row(
    *, name: str = "Test Player Jr.", pfr_id: str | None = "TestPl00", pct: float = 0.8
) -> SnapCountRow:
    return SnapCountRow(
        season=2024,
        week=1,
        game_type="REG",
        team="KC",
        opponent="BAL",
        player_name=name,
        pfr_player_id=pfr_id,
        position="WR",
        offense_snaps=40.0,
        offense_pct=pct,
    )


def test_merge_name_fallback_when_crosswalk_misses() -> None:
    """No id mapping -> the normalized-name fallback still joins
    ("Test Player" == "Test Player Jr.")."""
    merged = merge_player_weeks([_stats_row()], [_snap_row()], {})
    assert merged[0].snaps == pytest.approx(40.0)
    assert merged[0].snap_pct == pytest.approx(0.8)


def test_merge_name_collision_refuses_ambiguous_fallback() -> None:
    """Two distinct players collapsing to one normalized name in the same
    (team, week) make the name key ambiguous: better NULL than wrong."""
    snaps = [
        _snap_row(name="Test Player Jr.", pfr_id="TestPl00", pct=0.8),
        _snap_row(name="Test Player Sr.", pfr_id="TestPl01", pct=0.2),
    ]
    merged = merge_player_weeks([_stats_row()], snaps, {})
    assert merged[0].snaps is None
    assert merged[0].snap_pct is None


def test_merge_exact_id_join_wins_over_ambiguous_name() -> None:
    """The gsis join is immune to name collisions — with the crosswalk
    present the right row still attaches."""
    snaps = [
        _snap_row(name="Test Player Jr.", pfr_id="TestPl00", pct=0.8),
        _snap_row(name="Test Player Sr.", pfr_id="TestPl01", pct=0.2),
    ]
    merged = merge_player_weeks([_stats_row()], snaps, {"TestPl00": "00-0099001"})
    assert merged[0].snap_pct == pytest.approx(0.8)


def test_merge_no_snap_match_keeps_stats_with_null_snaps() -> None:
    merged = merge_player_weeks([_stats_row()], [], {})
    assert len(merged) == 1
    assert merged[0].snaps is None
    assert merged[0].receiving_yards == pytest.approx(61.0)
