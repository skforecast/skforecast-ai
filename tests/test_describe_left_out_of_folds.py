# Unit test describe_left_out_of_folds

from skforecast_ai._last_window import describe_left_out_of_folds

from tests.fixtures_last_window import plan_long_foundation, plan_long_ridge

_START = (
    "Some series were not forecast in every test fold where they have values "
    "to evaluate ("
)
_END = (
    "), so their metrics, and the average across series, leave the other "
    "folds out. "
)


def test_describe_left_out_of_folds_output_when_ForecasterRecursiveMultiSeries():
    """
    Test the text for ForecasterRecursiveMultiSeries: each series with the
    folds that forecast it, and why skforecast leaves a series out.
    """
    result = describe_left_out_of_folds(
        {"item_2": (7, 8), "item_3": (1, 2)}, plan_long_ridge
    )

    assert result == (
        f"{_START}'item_2': in 7 of its 8 folds with values; 'item_3': in 1 of "
        f"its 2 folds with values{_END}ForecasterRecursiveMultiSeries leaves a "
        "series out of a fold when the training window of the fold has too few "
        "of its observations, or when it cannot predict it from the values "
        "before the fold."
    )


def test_describe_left_out_of_folds_output_when_ForecasterFoundation():
    """
    Test that the reason of a ForecasterFoundation model is its context,
    with the context length of the model (8192 for Chronos-2 small).
    """
    result = describe_left_out_of_folds({"item_2": (6, 7)}, plan_long_foundation)

    assert result == (
        f"{_START}'item_2': in 6 of its 7 folds with values{_END}"
        "ForecasterFoundation leaves a series out of a fold when the 8192 "
        "observations before the fold, the context of the model, have no "
        "value of it."
    )


def test_describe_left_out_of_folds_lists_at_most_five_series():
    """
    Test that at most 5 series are named, with the number of the others.
    """
    left_out = {f"s{i}": (1, 2) for i in range(7)}

    result = describe_left_out_of_folds(left_out, plan_long_ridge)

    assert "'s4': in 1 of its 2 folds with values; and 2 more series)" in result
    assert "'s5'" not in result


def test_describe_left_out_of_folds_None_when_no_series_is_left_out():
    """
    Test that nothing is described when no series is left out.
    """
    assert describe_left_out_of_folds({}, plan_long_ridge) is None
