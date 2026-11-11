# Unit test describe_left_out_candidates

from skforecast_ai._last_window import describe_left_out_candidates


def test_describe_left_out_candidates_output_when_one_candidate():
    """
    Test the text for one candidate that left a series out of some folds:
    the candidates without series left out are not named.
    """
    result = describe_left_out_candidates(
        {"ridge": {"item_2": (7, 8)}, "short": {}}
    )

    assert result == (
        "Some series were not forecast in every test fold where they have "
        "values to evaluate in the backtest of the candidate 'ridge' "
        "('item_2': in 7 of its 8 folds with values): their metrics, and the "
        "average across series that ranks the candidate, leave the other "
        "folds out."
    )


def test_describe_left_out_candidates_output_when_several_candidates():
    """
    Test that several candidates are named in the order given, each with
    its series, and with the plural.
    """
    result = describe_left_out_candidates({
        "ridge": {"item_2": (7, 8)},
        "lgbm": {"item_2": (6, 8), "item_3": (1, 2)},
    })

    assert result == (
        "Some series were not forecast in every test fold where they have "
        "values to evaluate in the backtest of the candidates 'ridge' "
        "('item_2': in 7 of its 8 folds with values), 'lgbm' ('item_2': in 6 "
        "of its 8 folds with values; 'item_3': in 1 of its 2 folds with "
        "values): their metrics, and the average across series that ranks "
        "the candidates, leave the other folds out."
    )


def test_describe_left_out_candidates_names_at_most_five_candidates():
    """
    Test that at most 5 candidates are named, with the number of the others.
    """
    result = describe_left_out_candidates(
        {f"c{i}": {"item_2": (1, 2)} for i in range(7)}
    )

    assert "'c4' ('item_2': in 1 of its 2 folds with values) and 2 more:" in result
    assert "'c5'" not in result


def test_describe_left_out_candidates_None_when_no_candidate_left_a_series_out():
    """
    Test that nothing is described when no candidate left a series out.
    """
    assert describe_left_out_candidates({}) is None
    assert describe_left_out_candidates({"ridge": {}}) is None
