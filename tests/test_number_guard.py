"""Level 4 fix: the number guard flags figures the LLM worked out itself."""
from backend.services.number_guard import add_warning, unverified_numbers


def test_self_calculated_difference_is_flagged():
    answer = "Revenue was $441.2 million, up 10.7%, an increase of $42.5 million [1]."
    evidence = "Revenue was $441.2 million in fiscal 2025, up 10.7% from $398.7 million."
    assert unverified_numbers(answer, evidence) == ["$42.5"]


def test_scale_is_allowed():
    assert unverified_numbers("Net sales were $478.8 billion [2].", "Total net sales 478,834") == []


def test_rounding_allowed_and_small_counts_and_years_ignored():
    assert unverified_numbers("The net margin was a 14% margin.", "Net margin 14.03") == []
    assert unverified_numbers("There are 3 risks on page 2 in 2025.", "unrelated text") == []


def test_warning_only_when_something_is_missing():
    assert add_warning("All good.", []) == "All good."
    warned = add_warning("Up $42.5 million.", ["$42.5"])
    assert "⚠ Check" in warned and "$42.5" in warned
