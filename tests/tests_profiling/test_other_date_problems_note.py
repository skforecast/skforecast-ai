# Unit test _other_date_problems_note

import pandas as pd

from skforecast_ai.profiling.data_profile import _other_date_problems_note


def test_other_date_problems_note_counts_identical_rows_and_missing_dates():
    """
    Test that the note counts the timestamps repeated in identical rows and
    the timestamps missing from the frequency of the distinct dates, as they
    will be once the repeated rows are solved.
    """
    dates = pd.date_range("2020-01-01", periods=60, freq="MS").delete([10, 11, 30])
    dates = dates.append(dates[[2, 2, 9]])

    note = _other_date_problems_note(n_identical=1, dates=dates, ids=None)

    assert note == (
        " The same data also has 1 other timestamp repeated in identical rows "
        "(profiling keeps one of them) and 3 timestamps missing at the 'MS' "
        "frequency, which will still be missing once the repeated rows are "
        "solved."
    )


def test_other_date_problems_note_only_what_was_found():
    """
    Test that the note names only what was found (singular when it is one),
    and is empty when the dates have no other problem or no frequency can be
    inferred from them.
    """
    complete = pd.date_range("2020-01-01", periods=60, freq="D")
    one_gap = complete.delete(4)
    irregular = pd.DatetimeIndex(["2020-01-01", "2020-01-02"])

    identical = _other_date_problems_note(n_identical=2, dates=complete, ids=None)
    missing = _other_date_problems_note(n_identical=0, dates=one_gap, ids=None)

    assert identical == (
        " The same data also has 2 other timestamps repeated in identical "
        "rows (profiling keeps one of them)."
    )
    assert missing == (
        " The same data also has 1 timestamp missing at the 'D' frequency, "
        "which will still be missing once the repeated rows are solved."
    )
    assert _other_date_problems_note(n_identical=0, dates=complete, ids=None) == ""
    assert _other_date_problems_note(n_identical=0, dates=irregular, ids=None) == ""


def test_other_date_problems_note_long_format_sums_the_series():
    """
    Test that for long format the missing timestamps are counted per series
    and summed, and that time zone aware dates leave them out.
    """
    dates = pd.date_range("2020-01-01", periods=24, freq="MS")
    series_a = dates.delete([3])
    series_b = dates.delete([10, 11])
    stacked = series_a.append(series_b)
    ids = pd.Series(["a"] * len(series_a) + ["b"] * len(series_b))

    naive = _other_date_problems_note(n_identical=0, dates=stacked, ids=ids)
    aware = _other_date_problems_note(
        n_identical=0, dates=stacked.tz_localize("Europe/Madrid"), ids=ids
    )

    assert naive == (
        " The same data also has 3 timestamps missing at the 'MS' frequency, "
        "which will still be missing once the repeated rows are solved."
    )
    assert aware == ""
