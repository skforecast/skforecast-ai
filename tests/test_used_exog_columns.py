# Unit test used_exog_columns

import ast
import re

import pytest

from skforecast_ai._future_exog import used_exog_columns
from skforecast_ai.execution.forecast_runner import render_forecast_script

from tests.fixtures_future_exog import (
    plan_daily_ridge,
    plan_long_early_foundation,
    plan_long_ridge,
    plans_daily_by_forecaster,
    profile_daily,
    profile_long,
    profile_long_early,
)


def _columns_read_by_script(code: str, profile) -> list[str]:
    """
    Return the columns of `exog_future` that a generated forecast script
    reads: a list of columns taken from it, `exog_features`, or every column
    (a foundation model fitted on `exog = data[[...]]`).
    """
    match = re.search(r"exog_future\[(\[[^\]]*\])\]", code)
    if match:
        columns = ast.literal_eval(match.group(1))
        return [
            column for column in columns
            if column not in (profile.series_id_column, profile.date_column)
        ]
    if "exog=exog_future[exog_features]" in code:
        match = re.search(r"^exog_features = (\[.*\])$", code, re.MULTILINE)
        return ast.literal_eval(match.group(1))
    if "exog=exog_future)" in code:
        match = re.search(r"^exog = data\[(\[.*\])\]$", code, re.MULTILINE)
        return ast.literal_eval(match.group(1))

    return []


def test_used_exog_columns_output():
    """
    Test the exogenous columns the generated code reads: every one for an
    ML forecaster, the numeric ones for ForecasterStats (which leaves the
    categorical ones out), and none when the plan does not use them.
    """
    stats = plan_daily_ridge.model_copy(update={"forecaster": "ForecasterStats"})
    no_exog = plan_daily_ridge.model_copy(update={"use_exog": False})

    assert used_exog_columns(plan_daily_ridge, profile_daily) == ["promo", "weekday"]
    assert used_exog_columns(stats, profile_daily) == ["promo"]
    assert used_exog_columns(no_exog, profile_daily) == []


@pytest.mark.parametrize(
    "plan, profile, expected",
    [
        (plan_daily_ridge, profile_daily, ["promo", "weekday"]),
        (plans_daily_by_forecaster["direct"], profile_daily, ["promo", "weekday"]),
        (plans_daily_by_forecaster["stats"], profile_daily, ["promo"]),
        (
            plans_daily_by_forecaster["foundation"], profile_daily,
            ["promo", "weekday"],
        ),
        (plans_daily_by_forecaster["foundation_numeric"], profile_daily, ["promo"]),
        (plans_daily_by_forecaster["baseline"], profile_daily, []),
        (plan_long_ridge, profile_long, ["price"]),
        (plan_long_early_foundation, profile_long_early, ["price"]),
    ],
    ids=["recursive", "direct", "stats", "foundation", "foundation_numeric",
         "baseline", "multiseries_long", "foundation_long"],
)
def test_used_exog_columns_output_equals_columns_of_generated_script(
    plan, profile, expected
):
    """
    Test that the columns checked are those the generated forecast script
    reads from the future exogenous variables, for every forecaster family,
    so the checks cannot drift from the rendering.
    """
    code = render_forecast_script(profile=profile, plan=plan).core

    assert used_exog_columns(plan, profile) == expected
    assert _columns_read_by_script(code, profile) == expected
