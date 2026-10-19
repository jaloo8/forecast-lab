import pytest
from scripts.audit_prior_study_targets import screen


def test_partial_first_year_is_not_counted_and_upper_reference_is_not_a_ceiling():
    result = screen(
        {
            "start": "2004-08-20",
            "end": "2006-12-31",
            "calendar_years": [{"year": 2005, "return": 0.1}, {"year": 2006, "return": 0.3}],
        }
    )
    assert result["all_complete_years_at_least_10"]
    assert not result["at_least_ten_complete_years"]
    assert result["years_above_20"] == 1


@pytest.mark.parametrize(
    "annual",
    [
        [],
        [{"year": 2005, "return": 0.2}],
        [{"year": 2005, "return": 0.2}, {"year": 2005, "return": 0.2}],
    ],
)
def test_missing_or_duplicate_years_refused(annual):
    with pytest.raises(ValueError, match="cover"):
        screen({"start": "2005-01-01", "end": "2006-12-31", "calendar_years": annual})


def test_cash_and_losing_years_are_preserved():
    result = screen(
        {
            "start": "2005-01-01",
            "end": "2006-12-31",
            "calendar_years": [{"year": 2005, "return": 0.0}, {"year": 2006, "return": -0.1}],
        }
    )
    assert not result["all_complete_years_at_least_10"]
    assert result["years_below_10"] == 2
    assert result["losing_years"] == 1
