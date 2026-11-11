# Unit test detect_numbers_as_text

import pandas as pd
import pytest

from skforecast_ai.profiling.data_profile import detect_numbers_as_text

from .fixtures_profiling import df_dirty_exog

# Columns of 10 values at the share of 90 % (one 'n.d.') and below it (two).
df_share = pd.DataFrame({
    "at_share": ["1%"] * 9 + ["n.d."],
    "below_share": ["1%"] * 8 + ["n.d.", "?"],
})


def test_detect_numbers_as_text_output_when_percentages():
    """
    Test that a column of percentages is reported with every value read as a
    number, the final '%' as what makes it text and one level per value.
    """
    result = detect_numbers_as_text(df_dirty_exog, ["pct"])

    assert result == {"pct": (30, 30, ["numbers with a final '%'"], 30)}


def test_detect_numbers_as_text_output_when_dashes_for_missing_values():
    """
    Test that a column of numbers with a '-' for its missing values is
    reported with the '-' cells as what makes it text (the plain numbers are
    not) and one level for those cells.
    """
    result = detect_numbers_as_text(df_dirty_exog, ["dash"])

    assert result == {"dash": (30, 30, ["cells of '-'"], 28)}


def test_detect_numbers_as_text_output_when_mixed_markers():
    """
    Test that a column mixing plain numbers, percentages with and without
    spaces, a '-' and a blank cell is reported with each of them as what
    makes it text, and no value of the data.
    """
    result = detect_numbers_as_text(df_dirty_exog, ["mixed"])

    assert result == {
        "mixed": (
            30,
            30,
            [
                "numbers with a final '%'",
                "cells of '-'",
                "blank cells",
                "numbers with spaces",
            ],
            30,
        )
    }


def test_detect_numbers_as_text_output_when_true_categories():
    """
    Test that true categories are not reported: labels ('A', 'B'), product
    codes ('P-001', '007', whose leading zero marks a code), a column with
    few numbers among labels, a numeric column and a column of the
    `category` dtype holding numbers.
    """
    data = df_dirty_exog.assign(
        category=pd.Categorical(["1", "2", "3"] * 10)
    )

    result = detect_numbers_as_text(
        data, ["store", "code", "few", "x_na", "category"]
    )

    assert result == {}


@pytest.mark.parametrize(
    "column, expected",
    [
        ("at_share", {"at_share": (9, 10, ["numbers with a final '%'"], 2)}),
        ("below_share", {}),
    ],
    ids=["at the share", "below the share"],
)
def test_detect_numbers_as_text_output_at_the_share(column, expected):
    """
    Test that a column is reported when 90 % of its values read as numbers
    and not when fewer do.
    """
    result = detect_numbers_as_text(df_share, [column])

    assert result == expected


def test_detect_numbers_as_text_output_when_decimal_comma():
    """
    Test that, with the decimal mark ',' of the CSV file, '1,5%' and '2,5'
    read as numbers.
    """
    data = pd.DataFrame({"x": ["1,5%", "2,5", "-"]})

    result = detect_numbers_as_text(data, ["x"], decimal=",")

    assert result == {"x": (3, 3, ["numbers with a final '%'", "cells of '-'"], 3)}


def test_detect_numbers_as_text_output_when_only_markers():
    """
    Test that a column made only of '-' cells (and missing values) is not
    reported: it holds no number.
    """
    data = pd.DataFrame({"x": ["-", None, "-"]})

    result = detect_numbers_as_text(data, ["x"])

    assert result == {}


def test_detect_numbers_as_text_output_when_numbers_stored_as_text():
    """
    Test that a column of plain numbers stored as text (a DataFrame built
    from strings) is reported with nothing else that makes it text.
    """
    data = pd.DataFrame({"x": ["1.5", "2", "-3e2"]})

    result = detect_numbers_as_text(data, ["x"])

    assert result == {"x": (3, 3, [], 3)}
