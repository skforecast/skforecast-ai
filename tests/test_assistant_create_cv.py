# Unit test create_cv ForecastingAssistant

import ast
import contextlib
import re
import warnings

import numpy as np
import pandas as pd
import pytest

from skforecast.exceptions import IgnoredArgumentWarning
from skforecast.model_selection import TimeSeriesFold

from skforecast_ai import ForecastingAssistant, LLMRequiredError
from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.recommendation.backtesting import _compute_min_train_size
from skforecast_ai.schemas import CV_OVERRIDE_NAMES, CVParams, CVResult
from tests.fixtures_assistant import (
    df_single,
    df_multi_long,
    df_multi_long_staggered,
    df_range_index,
    df_short,
)
from tests.fixtures_datasets import df_h2o, df_hourly_madrid_spring


# =============================================================================
# Tests: error / validation
# =============================================================================
@pytest.mark.parametrize(
    "value",
    [0.0, 1.0, -0.1, 1.5],
    ids=lambda v: f"initial_train_size: {v}",
)
def test_create_cv_ValueError_when_initial_train_size_float_out_of_range(value):
    """
    Test that create_cv() raises ValueError when initial_train_size is a
    float outside the open interval (0, 1).
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    err_msg = re.escape(
        "initial_train_size as float must satisfy 0 < value < 1"
    )
    with pytest.raises(ValueError, match=err_msg):
        assistant.create_cv(profile, plan, initial_train_size=value)


def test_create_cv_ValueError_when_fewer_than_2_folds():
    """
    Test that create_cv() raises ValueError when the configuration
    produces fewer than 2 folds.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_short, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    err_msg = re.escape("At least 2 are required")
    with pytest.raises(ValueError, match=err_msg):
        assistant.create_cv(profile, plan, initial_train_size=20)


def test_create_cv_ValueError_when_initial_train_size_date_unparseable():
    """
    Test that create_cv() raises a ValueError naming initial_train_size
    when the date string cannot be parsed, instead of a raw pandas error.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    err_msg = re.escape(
        "`initial_train_size` date 'not-a-date' could not be parsed. Use an "
        "ISO date such as '2023-03-01'."
    )
    with pytest.raises(ValueError, match=err_msg):
        assistant.create_cv(profile, plan, initial_train_size="not-a-date")


@pytest.mark.parametrize(
    "initial_train_size",
    ["2023-03-01", pd.Timestamp("2023-03-01")],
    ids=["str", "Timestamp"],
)
def test_create_cv_ValueError_when_date_initial_train_size_without_datetime_index(
    initial_train_size,
):
    """
    Test that a date-based initial_train_size (string or Timestamp, the
    latter normalised to its string form) raises ValueError on a dataset
    without a datetime index, where the split date cannot be located.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_range_index, target="sales")
    plan = assistant.plan(profile, steps=10)

    err_msg = re.escape(
        "`initial_train_size` is a date ('2023-03-01') but the dataset has no "
        "datetime index with a known frequency, so the split date cannot be "
        "located. Pass an integer number of observations instead."
    )
    with pytest.raises(ValueError, match=err_msg):
        assistant.create_cv(profile, plan, initial_train_size=initial_train_size)


# =============================================================================
# Tests: basic output
# =============================================================================
def test_create_cv_output_when_single_series_defaults():
    """
    Test that create_cv() returns a CVResult carrying the splitter, the
    resolved configuration, the snippet and the explanation, plus the
    profile and plan it was derived from.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    result = assistant.create_cv(profile, plan)

    assert isinstance(result, CVResult)
    assert isinstance(result.cv, TimeSeriesFold)
    assert isinstance(result.explanation, str)
    assert result.profile is profile
    assert result.plan is plan


def test_create_cv_cv_config_matches_splitter_and_counts_folds():
    """
    Test that `cv_config` mirrors every TimeSeriesFold parameter,
    including `skip_folds` and `allow_incomplete_fold`, and reports the
    fold count the splitter actually produces and the folds that train the
    forecaster.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    result = assistant.create_cv(
        profile, plan, initial_train_size=60, refit=False,
        allow_incomplete_fold=False,
    )

    cv = result.cv
    assert result.cv_config == {
        "steps": 10,
        "initial_train_size": cv.initial_train_size,
        "refit": False,
        "fixed_train_size": cv.fixed_train_size,
        "gap": 0,
        "fold_stride": 10,
        "skip_folds": None,
        "allow_incomplete_fold": False,
        "differentiation": None,
        "n_folds": 4,
        "n_fits": 1,
    }
    assert "4 folds" in result.explanation


def test_create_cv_code_builds_the_same_splitter():
    """
    Test that the `code` snippet is a standalone construction of the
    splitter: executing it yields a TimeSeriesFold with the same
    parameters as `result.cv`.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    result = assistant.create_cv(profile, plan, initial_train_size=60, refit=False)

    namespace: dict = {}
    exec(result.code, namespace)  # noqa: S102
    rebuilt = namespace["cv"]

    assert result.code.startswith("from skforecast.model_selection import TimeSeriesFold")
    assert rebuilt.steps == result.cv.steps
    assert rebuilt.initial_train_size == result.cv.initial_train_size
    assert rebuilt.refit == result.cv.refit


def test_create_cv_TypeError_when_result_is_unpacked():
    """
    Test that unpacking the result as the former `(cv, explanation)` tuple
    fails with a message that points to the new attributes. A pydantic
    model would otherwise iterate over its fields and fail with a puzzling
    "too many values to unpack".
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    with pytest.raises(TypeError, match=re.escape("Use `result.cv`")):
        cv, explanation = assistant.create_cv(profile, plan)


def test_create_cv_display_shows_explanation_and_configuration():
    """
    Test that rendering the result to text shows the explanation panel
    and the configuration table with the fold count.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    text = str(assistant.create_cv(profile, plan, initial_train_size=60))

    assert "Cross-Validation Explanation" in text
    assert "Cross-Validation Configuration" in text
    assert "n_folds" in text


def test_create_cv_output_when_default_initial_train_size():
    """
    Test that the default initial_train_size is a date string corresponding
    to approximately 70% of data when a datetime index is available.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    cv = assistant.create_cv(profile, plan).cv

    # 70% of 100 daily observations starting 2023-01-01 → position 70 → date at
    # index 69 = 2023-01-01 + 69 days = 2023-03-11
    assert cv.initial_train_size == "2023-03-11"


def test_create_cv_output_when_steps_from_plan():
    """
    Test that cv.steps equals plan.steps.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=7)

    cv = assistant.create_cv(profile, plan).cv

    assert cv.steps == 7


def test_create_cv_output_when_multi_series_defaults():
    """
    Test that create_cv() works for multi-series profiles.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=df_multi_long,
        target="value",
        date_column="date",
        series_id_column="series_id",
    )
    plan = assistant.plan(profile, steps=5)

    cv_result = assistant.create_cv(profile, plan)
    cv, explanation = cv_result.cv, cv_result.explanation

    assert isinstance(cv, TimeSeriesFold)
    assert cv.steps == 5
    assert "5-step horizon" in explanation


# =============================================================================
# Tests: explicit overrides
# =============================================================================
def test_create_cv_output_when_initial_train_size_int_override():
    """
    Test that an explicit int initial_train_size is used directly.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    cv = assistant.create_cv(profile, plan, initial_train_size=50).cv

    assert cv.initial_train_size == 50


def test_create_cv_output_when_initial_train_size_float_override():
    """
    Test that a float initial_train_size is converted to a fraction of
    n_observations.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    cv = assistant.create_cv(profile, plan, initial_train_size=0.5).cv

    # 50% of 100 observations = 50
    assert cv.initial_train_size == 50


def test_create_cv_output_when_initial_train_size_str_date():
    """
    Test that a str (date) initial_train_size is passed through and
    validated against a DatetimeIndex built from the profile.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    cv_result = assistant.create_cv(
        profile, plan, initial_train_size="2023-03-01"
    )
    cv = cv_result.cv

    assert isinstance(cv, TimeSeriesFold)
    assert cv.initial_train_size == "2023-03-01"


def test_create_cv_ValueError_when_initial_train_size_str_date_too_late():
    """
    Test that a str (date) initial_train_size leaving fewer than 2 folds
    raises ValueError, mirroring the integer validation path.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    # df_single has 100 daily observations (2023-01-01 .. 2023-04-10). A
    # near-final training date leaves too few observations for 2 folds.
    err_msg = re.escape("At least 2 are required")
    with pytest.raises(ValueError, match=err_msg):
        assistant.create_cv(profile, plan, initial_train_size="2023-04-09")


@pytest.mark.parametrize(
    "forecaster, expected_explanation",
    [
        (
            None,
            "Initial training up to 2023-03-11, trained once (no refit), "
            "10-step horizon, 3 folds.",
        ),
        (
            "ForecasterDirect",
            "Initial training up to 2023-03-11, trained once (no refit), "
            "10-step horizon, 3 folds. ForecasterDirect fits one estimator per "
            "step, so each training fits 10 estimators (10 fits in all).",
        ),
    ],
    ids=["recursive", "direct"],
)
def test_create_cv_output_when_default_refit(forecaster, expected_explanation):
    """
    Test that the default strategy trains the forecaster once (refit=False,
    the skforecast default), since refitting in every fold multiplies the
    cost by the number of folds, and that the explanation states the cost,
    including the estimator fits of a direct forecaster.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10, forecaster=forecaster)

    result = assistant.create_cv(profile, plan)

    assert result.cv.refit is False
    assert result.cv_config["n_fits"] == 1
    assert result.explanation == expected_explanation


def test_create_cv_output_when_refit_override():
    """
    Test that explicit refit value overrides the default.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    cv = assistant.create_cv(profile, plan, refit=3).cv

    assert cv.refit == 3


def test_create_cv_output_when_fixed_train_size_override():
    """
    Test that explicit fixed_train_size overrides the default when the
    forecaster is refitted.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    cv = assistant.create_cv(profile, plan, refit=True, fixed_train_size=True).cv

    assert cv.fixed_train_size is True


@pytest.mark.parametrize("fixed_train_size", [True, False])
@pytest.mark.parametrize("refit", [None, False, 0])
def test_create_cv_IgnoredArgumentWarning_when_fixed_train_size_without_refit(
    refit, fixed_train_size
):
    """
    Test that create_cv warns that `fixed_train_size` has no effect when it
    is passed for a forecaster that is trained once (`refit` False, 0 or the
    default), and returns the strategy that runs without it.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    expected = assistant.create_cv(profile, plan, refit=refit)

    resolved = False if refit is None else refit
    warn_msg = re.escape(
        f"`fixed_train_size={fixed_train_size!r}` has no effect: with "
        f"`refit={resolved!r}` the forecaster is trained once, on a single "
        f"training window. Pass `refit=True` (or an integer) to refit it, or "
        f"omit `fixed_train_size` to avoid this warning."
    )
    with pytest.warns(IgnoredArgumentWarning, match=warn_msg):
        result = assistant.create_cv(
            profile, plan, refit=refit, fixed_train_size=fixed_train_size
        )

    assert result.cv_config["n_folds"] == expected.cv_config["n_folds"]
    assert result.cv_config["n_fits"] == expected.cv_config["n_fits"] == 1
    assert result.explanation == expected.explanation


def test_create_cv_output_when_fixed_train_size_with_integer_refit():
    """
    Test that `fixed_train_size` is accepted with an integer `refit`.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    cv = assistant.create_cv(profile, plan, refit=2, fixed_train_size=False).cv

    assert cv.refit == 2
    assert cv.fixed_train_size is False


def test_create_cv_output_when_gap_override():
    """
    Test that explicit gap value overrides the default.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    cv = assistant.create_cv(profile, plan, gap=2).cv

    assert cv.gap == 2


# =============================================================================
# Tests: task-type floor logic
# =============================================================================
def test_create_cv_output_when_floor_by_lags_int():
    """
    Test that initial_train_size is floored to (lags + steps) when lags
    is int and that value exceeds the forecaster's window_size.
    """
    assistant = ForecastingAssistant()
    # Use short data where 70% = 17, but lags force a higher floor
    profile = assistant.profile(data=df_short, target="sales", date_column="date")
    # Steps=1 so we can get many folds even with small data
    plan = assistant.plan(profile, steps=1)

    # Override lags in the plan to force a specific floor
    plan.forecaster_kwargs["lags"] = 20  # floor = 20 + 1 = 21

    cv = assistant.create_cv(profile, plan).cv

    # With 25 obs, 70% = 17. Floor = 21 (> 17). Ceiling = 25 - 2*1 = 23.
    # So initial_train_size = 21. Date at index 20 = 2023-01-21.
    assert cv.initial_train_size == "2023-01-21"


def test_create_cv_output_when_floor_by_lags_list():
    """
    Test that initial_train_size floor uses max(lags) + steps when lags
    is a list, and that the result exceeds the forecaster's window_size.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_short, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=1)

    plan.forecaster_kwargs["lags"] = [1, 5, 22]  # floor = 22 + 1 = 23

    cv = assistant.create_cv(profile, plan).cv

    # With 25 obs, 70% = 17. Floor = 23 (> 17). Ceiling = 25 - 2*1 = 23.
    # Both constraints give 23. Date at index 22 = 2023-01-23.
    assert cv.initial_train_size == "2023-01-23"


def test_create_cv_output_when_statistical_floor():
    """
    Test that statistical task uses 2 * steps as floor.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(
        profile, steps=10, forecaster="ForecasterStats"
    )

    cv = assistant.create_cv(profile, plan).cv

    # floor = 2*10 = 20, 70% of 100 = 70. 70 > 20, so 70 is used.
    # ceiling = 100 - 2*10 = 80. So initial_train_size = 70.
    # Date at index 69 = 2023-01-01 + 69 days = 2023-03-11.
    assert cv.initial_train_size == "2023-03-11"


def test_create_cv_output_when_baseline_floor():
    """
    Test that a baseline plan uses 2 * steps as floor when its window
    (`offset * n_offsets`) is shorter than one horizon.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(
        profile, steps=10, forecaster="ForecasterEquivalentDate"
    )

    cv = assistant.create_cv(profile, plan).cv

    # offset = 7, floor = max(7 + 10, 2*10) = 20, 70% of 100 = 70.
    # ceiling = 100 - 2*10 = 80. So initial_train_size = 70.
    # Date at index 69 = 2023-01-01 + 69 days = 2023-03-11.
    assert cv.initial_train_size == "2023-03-11"


def test_create_cv_output_when_floor_by_baseline_window():
    """
    Test that the initial_train_size floor of a baseline plan is
    `offset * n_offsets + steps`, so every fold finds its equivalent dates.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_short, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=1, forecaster="ForecasterEquivalentDate")

    plan.forecaster_kwargs["offset"] = 20  # floor = 20 * 1 + 1 = 21

    cv = assistant.create_cv(profile, plan).cv

    # With 25 obs, 70% = 17. Floor = 21 (> 17). Ceiling = 25 - 2*1 = 23.
    # So initial_train_size = 21. Date at index 20 = 2023-01-21.
    assert cv.initial_train_size == "2023-01-21"


def test_create_cv_output_when_differentiation_set():
    """
    Test that differentiation flows from plan.forecaster_kwargs to the
    TimeSeriesFold.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    plan.forecaster_kwargs["differentiation"] = 1

    cv = assistant.create_cv(profile, plan).cv

    assert cv.differentiation == 1


def test_create_cv_output_when_floor_by_window_features():
    """
    Test that initial_train_size accounts for window_features when the
    max window_size exceeds max(lags), preventing skforecast ValueError.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    # Lags = 10 (window_size from lags alone = 10)
    # Window features with window_size = 60 → effective window = 60
    plan.forecaster_kwargs["lags"] = 10
    plan.forecaster_kwargs["window_features"] = [
        {"stats": ["mean"], "window_size": 60}
    ]

    cv = assistant.create_cv(profile, plan).cv

    # Floor = effective_window + steps = 60 + 5 = 65.
    # 70% of 100 = 70. max(70, 65) = 70. Ceiling = 100 - 10 = 90.
    # initial_train_size = 70. Date at index 69 = 2023-03-11.
    assert cv.initial_train_size == "2023-03-11"


# =============================================================================
# Tests: explanation
# =============================================================================
def test_create_cv_explanation_contains_key_params():
    """
    Test that the explanation string mentions the key parameters.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    explanation = assistant.create_cv(profile, plan).explanation

    assert "10-step horizon" in explanation
    assert "Initial training up to" in explanation


def test_create_cv_output_when_forecaster_is_stats():
    """
    Test that for a ForecasterStats plan the splitter keeps the parameters
    given, while `cv_config`, the snippet and the explanation state what
    skforecast runs: refit in every fold on a fixed window, one training
    per fold.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_h2o, target="x")
    plan = assistant.plan(profile, steps=12, forecaster="ForecasterStats")

    result = assistant.create_cv(profile, plan)

    assert result.cv.refit is False
    assert result.cv.fixed_train_size is False
    assert result.cv_config["refit"] is True
    assert result.cv_config["fixed_train_size"] is True
    assert result.cv_config["n_folds"] == 6
    assert result.cv_config["n_fits"] == 6
    assert "refit              = True,\n" in result.code
    assert "fixed_train_size   = True,\n" in result.code
    assert result.explanation == (
        "Initial training up to 2003-04-01, fixed window, refit every fold "
        "(6 trainings), 12-step horizon, 6 folds. ForecasterStats is "
        "refitted in every fold whatever `refit` says: skforecast requires "
        "it for ARIMA models."
    )


@pytest.mark.parametrize(
    "kwargs, ignored, fixed",
    [
        ({"refit": False}, "`refit=False`", True),
        (
            {"refit": False, "fixed_train_size": False},
            "`refit=False` and `fixed_train_size=False`",
            True,
        ),
        ({"refit": 2}, "`refit=2`", False),
    ],
    ids=["refit_false", "refit_false_expanding", "refit_integer"],
)
def test_create_cv_IgnoredArgumentWarning_when_stats_arguments_do_not_run(
    kwargs, ignored, fixed
):
    """
    Test that an explicit `refit` or `fixed_train_size` that ForecasterStats
    does not run is warned about: skforecast refits it in every fold, which
    `cv_config` and the explanation already state.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_h2o, target="x")
    plan = assistant.plan(profile, steps=12, forecaster="ForecasterStats")

    warn_msg = re.escape(
        f"{ignored} do not apply to ForecasterStats: skforecast refits it in "
        f"every fold, so its backtest runs with `refit=True` and "
        f"`fixed_train_size={fixed}`. Pass those values to avoid this warning."
    )
    with pytest.warns(IgnoredArgumentWarning, match=warn_msg):
        result = assistant.create_cv(profile, plan, **kwargs)

    assert result.cv.refit == kwargs["refit"]
    assert result.cv_config["refit"] is True


@pytest.mark.parametrize(
    "kwargs",
    [{}, {"refit": True}, {"refit": True, "fixed_train_size": False}],
    ids=["defaults", "refit_true", "refit_true_expanding"],
)
def test_create_cv_no_warning_when_stats_arguments_run(kwargs):
    """
    Test that ForecasterStats gives no warning with the default strategy or
    with arguments it runs as given.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_h2o, target="x")
    plan = assistant.plan(profile, steps=12, forecaster="ForecasterStats")

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assistant.create_cv(profile, plan, **kwargs)


def test_create_cv_output_when_initial_train_size_timestamp():
    """
    Test that a pandas Timestamp initial_train_size is accepted, stored as
    a date string on the splitter and in cv_config, and rendered as a
    quoted string so the snippet is valid Python.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    result = assistant.create_cv(
        profile, plan, initial_train_size=pd.Timestamp("2023-03-01")
    )

    assert result.cv.initial_train_size == "2023-03-01"
    assert result.cv_config["initial_train_size"] == "2023-03-01"
    assert result.cv_config["n_folds"] == 4
    assert "initial_train_size = '2023-03-01'," in result.code
    ast.parse(result.code)


# =============================================================================
# Tests: LLM path
# =============================================================================
def test_create_cv_LLMRequiredError_when_prompt_but_no_llm():
    """
    Test that create_cv() raises LLMRequiredError when prompt is
    provided but no LLM is configured.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    err_msg = re.escape(
        "`create_cv()` requires an LLM. "
        "Pass `llm=...` when creating ForecastingAssistant."
    )
    with pytest.raises(LLMRequiredError, match=err_msg):
        assistant.create_cv(profile, plan, prompt="I retrain weekly")


def test_create_cv_llm_success(monkeypatch):
    """
    Test that create_cv() uses LLM-returned parameters when prompt is
    provided and LLM is configured.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    # Mock the CV agent to return specific params
    cv_params = CVParams(
        initial_train_size=50,
        refit=False,
        fixed_train_size=True,
        gap=2,
        fold_stride=None,
        skip_folds=None,
        allow_incomplete_fold=True,
        reasoning="Weekly retraining with 2-day gap.",
    )

    class _FakeResult:
        output = cv_params

    class _FakeAgent:
        async def run(self, msg, **kw):
            return _FakeResult()

    monkeypatch.setattr(assistant, "_cv_agent", _FakeAgent())

    def _mock_resolve_model(self_=None):
        return "fake-model-string"

    monkeypatch.setattr(assistant, "_resolve_model", _mock_resolve_model)

    cv_result = assistant.create_cv(
        profile, plan, prompt="I retrain weekly"
    )
    cv, explanation = cv_result.cv, cv_result.explanation

    assert isinstance(cv, TimeSeriesFold)
    assert cv.initial_train_size == 50
    assert cv.refit is False
    assert cv.fixed_train_size is True
    assert cv.gap == 2
    assert "Weekly retraining" in explanation


def test_create_cv_llm_kwargs_override_llm(monkeypatch):
    """
    Test that explicit kwargs override LLM-returned parameters.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    cv_params = CVParams(
        initial_train_size=50,
        refit=True,
        fixed_train_size=False,
        gap=0,
        fold_stride=None,
        skip_folds=None,
        allow_incomplete_fold=True,
        reasoning="Default strategy.",
    )

    class _FakeResult:
        output = cv_params

    class _FakeAgent:
        async def run(self, msg, **kw):
            return _FakeResult()

    monkeypatch.setattr(assistant, "_cv_agent", _FakeAgent())

    def _mock_resolve_model(self_=None):
        return "fake-model-string"

    monkeypatch.setattr(assistant, "_resolve_model", _mock_resolve_model)

    # Override refit and gap
    cv = assistant.create_cv(
        profile, plan, prompt="I retrain weekly", refit=3, gap=1
    ).cv

    assert cv.refit == 3
    assert cv.gap == 1
    # LLM values preserved for non-overridden params
    assert cv.initial_train_size == 50


def test_create_cv_prompt_ignored_when_all_params_explicit(monkeypatch):
    """
    Test that create_cv() skips the LLM entirely (with a UserWarning) when
    every CV parameter the LLM would decide is supplied explicitly.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    class _RaisingAgent:
        async def run(self, msg, **kw):
            raise AssertionError("LLM should not be called")

    monkeypatch.setattr(assistant, "_cv_agent", _RaisingAgent())

    def _mock_resolve_model(self_=None):
        return "fake-model-string"

    monkeypatch.setattr(assistant, "_resolve_model", _mock_resolve_model)

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        cv = assistant.create_cv(
            profile,
            plan,
            prompt="I retrain weekly",
            initial_train_size=50,
            fold_stride=5,
            refit=True,
            fixed_train_size=True,
            gap=0,
            skip_folds=1,
            allow_incomplete_fold=True,
        ).cv

    assert isinstance(cv, TimeSeriesFold)
    assert cv.initial_train_size == 50
    assert cv.refit is True
    assert cv.fixed_train_size is True
    assert cv.gap == 0
    ignored = [
        x
        for x in w
        if "Prompt ignored: all CV parameters were set explicitly" in str(x.message)
    ]
    assert len(ignored) == 1


def test_create_cv_llm_retry_then_success(monkeypatch):
    """
    Test that create_cv() retries on validation failure and succeeds
    on the second attempt.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    n_obs = profile.data_profile.series_lengths["sales"].length

    # First call: initial_train_size too large (only 1 fold)
    bad_params = CVParams(
        initial_train_size=n_obs - 3,  # Too large for 2 folds
        refit=True,
        fixed_train_size=False,
        gap=0,
        fold_stride=None,
        skip_folds=None,
        allow_incomplete_fold=True,
        reasoning="Bad first attempt.",
    )
    good_params = CVParams(
        initial_train_size=50,
        refit=True,
        fixed_train_size=False,
        gap=0,
        fold_stride=None,
        skip_folds=None,
        allow_incomplete_fold=True,
        reasoning="Fixed after retry.",
    )

    call_count = {"n": 0}

    class _FakeResult:
        def __init__(self, params):
            self.output = params

    class _FakeAgent:
        async def run(self, msg, **kw):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return _FakeResult(bad_params)
            return _FakeResult(good_params)

    monkeypatch.setattr(assistant, "_cv_agent", _FakeAgent())

    def _mock_resolve_model(self_=None):
        return "fake-model-string"

    monkeypatch.setattr(assistant, "_resolve_model", _mock_resolve_model)

    cv = assistant.create_cv(profile, plan, prompt="Forecast ahead").cv

    assert cv.initial_train_size == 50
    assert call_count["n"] == 2


def test_create_cv_llm_all_retries_fail_deterministic_fallback(monkeypatch):
    """
    Test that create_cv() falls back to deterministic defaults after
    all LLM retries are exhausted, emitting a UserWarning.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    n_obs = profile.data_profile.series_lengths["sales"].length

    # Always return params that are too large
    bad_params = CVParams(
        initial_train_size=n_obs - 3,
        refit=True,
        fixed_train_size=False,
        gap=0,
        fold_stride=None,
        skip_folds=None,
        allow_incomplete_fold=True,
        reasoning="Always bad.",
    )

    class _FakeResult:
        output = bad_params

    class _FakeAgent:
        async def run(self, msg, **kw):
            return _FakeResult()

    monkeypatch.setattr(assistant, "_cv_agent", _FakeAgent())

    def _mock_resolve_model(self_=None):
        return "fake-model-string"

    monkeypatch.setattr(assistant, "_resolve_model", _mock_resolve_model)

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        cv = assistant.create_cv(profile, plan, prompt="Bad scenario").cv

    # Should have fallen back to deterministic defaults
    assert isinstance(cv, TimeSeriesFold)
    assert cv.steps == 5
    # Deterministic default: 70% of 100 daily obs = date string '2023-03-11'
    assert cv.initial_train_size == "2023-03-11"

    # Should have emitted a warning
    llm_warnings = [x for x in w if "LLM CV configuration failed" in str(x.message)]
    assert len(llm_warnings) == 1


def _make_cv_params(initial_train_size, reasoning: str) -> CVParams:
    """Build CVParams around `initial_train_size` with neutral defaults."""
    return CVParams(
        initial_train_size    = initial_train_size,
        refit                 = True,
        fixed_train_size      = False,
        gap                   = 0,
        fold_stride           = None,
        skip_folds            = None,
        allow_incomplete_fold = True,
        reasoning             = reasoning,
    )


def _install_fake_cv_agent(monkeypatch, assistant, outputs: list[CVParams]) -> dict:
    """Install a fake CV agent yielding `outputs` in order (last one repeats)."""
    call_count = {"n": 0}

    class _FakeResult:
        def __init__(self, params):
            self.output = params

    class _FakeAgent:
        async def run(self, msg, **kw):
            i = min(call_count["n"], len(outputs) - 1)
            call_count["n"] += 1
            return _FakeResult(outputs[i])

    monkeypatch.setattr(assistant, "_cv_agent", _FakeAgent())
    monkeypatch.setattr(assistant, "_resolve_model", lambda self_=None: "fake-model")
    return call_count


def test_create_cv_llm_retry_then_success_when_date_out_of_range(monkeypatch):
    """
    Test that a date-based initial_train_size outside the series range
    is caught inside the LLM retry loop (not after it) and the second
    suggestion is used.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    call_count = _install_fake_cv_agent(
        monkeypatch,
        assistant,
        [
            _make_cv_params("2030-01-01", "Beyond the last date."),
            _make_cv_params(50, "Fixed after retry."),
        ],
    )

    cv = assistant.create_cv(profile, plan, prompt="Forecast ahead").cv

    assert cv.initial_train_size == 50
    assert call_count["n"] == 2


def test_create_cv_llm_deterministic_fallback_when_date_unparseable(monkeypatch):
    """
    Test that an unparseable date-based initial_train_size exhausts the
    LLM retries and create_cv() degrades to the deterministic defaults
    with a UserWarning, instead of raising a pandas parsing error.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    call_count = _install_fake_cv_agent(
        monkeypatch, assistant, [_make_cv_params("next spring", "Always bad.")]
    )

    warn_msg = re.escape(
        "LLM CV configuration failed after 3 attempts (last error: "
        "`initial_train_size` date 'next spring' could not be parsed. Use an "
        "ISO date such as '2023-03-01'.). Falling back to deterministic "
        "defaults."
    )
    with pytest.warns(UserWarning, match=warn_msg):
        cv = assistant.create_cv(profile, plan, prompt="Bad scenario").cv

    assert call_count["n"] == 3
    assert cv.initial_train_size == "2023-03-11"


def test_create_cv_llm_deterministic_fallback_when_date_on_range_index(monkeypatch):
    """
    Test that a date-based LLM suggestion on a dataset without a datetime
    index is rejected inside the retry loop and the deterministic integer
    default is used, with a UserWarning.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_range_index, target="sales")
    plan = assistant.plan(profile, steps=5)

    _install_fake_cv_agent(
        monkeypatch, assistant, [_make_cv_params("2023-03-01", "A date.")]
    )

    warn_msg = re.escape(
        "`initial_train_size` is a date ('2023-03-01') but the dataset has no "
        "datetime index with a known frequency"
    )
    with pytest.warns(UserWarning, match=warn_msg):
        cv = assistant.create_cv(profile, plan, prompt="Some scenario").cv

    assert cv.initial_train_size == 70


@pytest.mark.parametrize(
    "data, profile_kwargs, expected",
    [
        (df_single, {"date_column": "date"}, ("2023-01-01", "2023-04-10")),
        (df_range_index, {}, (None, None)),
    ],
    ids=["datetime_index", "range_index"],
)
def test_create_cv_llm_deps_carry_date_range(
    monkeypatch, data, profile_kwargs, expected
):
    """
    Test that the CV agent receives the first and last date of the series
    when the dataset has a datetime index with a known frequency, and no
    dates otherwise, matching the rule `count_cv_folds` applies.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=data, target="sales", **profile_kwargs)
    plan = assistant.plan(profile, steps=5)
    captured = {}

    class _FakeResult:
        output = _make_cv_params(50, "Fifty observations.")

    class _FakeAgent:
        async def run(self, msg, **kw):
            captured["deps"] = kw["deps"]
            return _FakeResult()

    monkeypatch.setattr(assistant, "_cv_agent", _FakeAgent())
    monkeypatch.setattr(assistant, "_resolve_model", lambda self_=None: "fake-model")

    assistant.create_cv(profile, plan, prompt="Retrain weekly.")

    deps = captured["deps"]
    assert (deps.start_date, deps.end_date) == expected
    assert deps.n_observations == 100


def test_create_cv_llm_explanation_includes_reasoning(monkeypatch):
    """
    Test that the explanation includes the LLM's reasoning field.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    cv_params = CVParams(
        initial_train_size=60,
        refit=True,
        fixed_train_size=False,
        gap=0,
        fold_stride=None,
        skip_folds=None,
        allow_incomplete_fold=True,
        reasoning="Expanding window chosen because data has no concept drift.",
    )

    class _FakeResult:
        output = cv_params

    class _FakeAgent:
        async def run(self, msg, **kw):
            return _FakeResult()

    monkeypatch.setattr(assistant, "_cv_agent", _FakeAgent())

    def _mock_resolve_model(self_=None):
        return "fake-model-string"

    monkeypatch.setattr(assistant, "_resolve_model", _mock_resolve_model)

    explanation = assistant.create_cv(
        profile, plan, prompt="Use expanding window"
    ).explanation

    assert "concept drift" in explanation


def test_create_cv_deterministic_when_no_prompt_and_llm_configured():
    """
    Test that create_cv() uses deterministic defaults when no prompt is
    provided, even if an LLM is configured. No LLM call is made.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    # No prompt → deterministic path. _cv_agent is never called.
    # If it were called, it would fail because no mock is set up and
    # _resolve_model would fail for "openai:fake-model" without env var.
    cv_result = assistant.create_cv(profile, plan)
    cv, explanation = cv_result.cv, cv_result.explanation

    assert isinstance(cv, TimeSeriesFold)
    assert cv.steps == 5
    assert "Initial training up to" in explanation


def test_create_cv_explanation_when_foundation_plan():
    """
    Test that the explanation of the strategy for a foundation plan does
    not describe a training window or refits, which do not apply to a model
    that is not trained, and states its cost in inference windows instead
    (one per series and fold).
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5, forecaster="ForecasterFoundation")

    result = assistant.create_cv(profile, plan)

    assert "no training (each fold forecasts from the observations before it)" in (
        result.explanation
    )
    assert "refit" not in result.explanation
    assert "training window" not in result.explanation
    assert "expanding window" not in result.explanation
    assert "fixed window" not in result.explanation
    assert result.explanation.endswith(
        "The model forecasts each series in each fold where it has data (up "
        "to 6 inference windows)."
    )
    assert result.cv_config["inference_windows"] == 6


# =============================================================================
# Tests: error code and field
# =============================================================================
@pytest.mark.parametrize(
    "data, initial_train_size, expected_code, expected_field, err_msg",
    [
        (
            df_single, 1.5, "invalid_argument", "initial_train_size",
            "initial_train_size as float must satisfy 0 < value < 1, got 1.5.",
        ),
        (
            df_single, "not-a-date", "invalid_argument", "initial_train_size",
            "`initial_train_size` date 'not-a-date' could not be parsed. Use "
            "an ISO date such as '2023-03-01'.",
        ),
        (
            df_short, 20, "insufficient_data", None,
            "The resolved CV configuration produces only 1 fold(s). At least "
            "2 are required.",
        ),
    ],
    ids=["float_out_of_range", "date_unparseable", "fewer_than_2_folds"],
)
def test_create_cv_InvalidInputError_code_and_field(
    data, initial_train_size, expected_code, expected_field, err_msg
):
    """
    Test that the errors of create_cv() are InvalidInputError with the
    argument at fault as field, and that a configuration with too few folds
    for the data has the code 'insufficient_data'.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=data, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    with pytest.raises(InvalidInputError, match=re.escape(err_msg)) as exc_info:
        assistant.create_cv(profile, plan, initial_train_size=initial_train_size)

    assert exc_info.value.code == expected_code
    assert exc_info.value.field == expected_field


# =============================================================================
# Tests: early input checks
# =============================================================================
_STRATEGY_HINT = (
    "Change the arguments of the strategy (`initial_train_size`, "
    "`fold_stride`, `gap`, `skip_folds`) or the `steps` of the plan so that "
    "at least two folds fit in the data."
)


@pytest.mark.parametrize(
    "kwargs, field, reason",
    [
        (
            {"gap": -1},
            "gap",
            "`gap` must be an integer greater than or equal to 0. Got -1.",
        ),
        (
            {"fold_stride": 0},
            "fold_stride",
            "`fold_stride` must be an integer greater than 0. Got 0.",
        ),
        (
            {"initial_train_size": 500},
            "initial_train_size",
            "The time series must have more than `initial_train_size + gap` "
            "observations to create at least one fold. Time series length: "
            "100 Required > 500 initial_train_size: 500 gap: 0",
        ),
        (
            {"skip_folds": [0]},
            "skip_folds",
            "`skip_folds` list must contain integers greater than or equal "
            "to 1. The first fold is always needed to train the forecaster. "
            "Got [0].",
        ),
    ],
    ids=["gap", "fold_stride", "initial_train_size", "skip_folds"],
)
def test_create_cv_InvalidInputError_when_strategy_cannot_be_built(
    kwargs, field, reason
):
    """
    Test that create_cv() raises an InvalidInputError that names the argument
    that TimeSeriesFold rejects, with the message of skforecast and a hint
    (the folds when the strategy does not fit, the argument otherwise).
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    err_msg = re.escape(f"The cross-validation strategy cannot be built: {reason}")
    with pytest.raises(InvalidInputError, match="^" + err_msg + "$") as exc_info:
        assistant.create_cv(profile, plan, **kwargs)

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == field
    assert exc_info.value.hint == (
        _STRATEGY_HINT if field == "initial_train_size"
        else f"Pass a value that `TimeSeriesFold` accepts for `{field}`."
    )


def test_create_cv_InvalidInputError_when_skip_folds_do_not_exist():
    """
    Test that create_cv() rejects `skip_folds` that name folds beyond the
    strategy (6 folds, numbered from 0 to 5), which TimeSeriesFold ignores.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    err_msg = re.escape(
        "`skip_folds` names folds that do not exist ([100]): the strategy has "
        "6 folds, numbered from 0 to 5."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        assistant.create_cv(profile, plan, skip_folds=[100])

    assert exc_info.value.field == "skip_folds"


def test_create_cv_output_when_skip_folds_in_range():
    """
    Test that create_cv() accepts `skip_folds` within the folds of the
    strategy.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    cv = assistant.create_cv(profile, plan, skip_folds=[1, 2]).cv

    assert cv.skip_folds == [1, 2]


def test_create_cv_output_when_plan_has_differentiation():
    """
    Test that the strategy of a plan with a differentiation order carries
    it and says so, and that the order adds to the minimum size of the
    first training window.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_h2o, target="x")
    plain = assistant.plan(profile, steps=12, lags=12)
    plan = assistant.plan(profile, steps=12, lags=12, differentiation=2)

    result = assistant.create_cv(profile, plan)

    assert result.cv.differentiation == 2
    assert result.cv_config["differentiation"] == 2
    assert result.explanation.endswith("differentiation order 2.")
    assert _compute_min_train_size(plan) == _compute_min_train_size(plain) + 2


def test_create_cv_UserWarning_when_direct_forecaster_with_gap():
    """
    Test that create_cv() builds a strategy with a gap for a ForecasterDirect
    plan, whose backtest raises, with a UserWarning that says so: the
    strategy can still serve the candidates of compare() that are not
    direct.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_h2o, target="x")
    plan = assistant.plan(profile, steps=6, forecaster="ForecasterDirect")

    warn_msg = re.escape(
        "ForecasterDirect is trained to predict 6 steps, and with `gap=2` "
        "each fold needs steps + gap = 8 steps ahead, so skforecast would "
        "fail: `backtest()` and `backtest_code()` of this plan with this "
        "strategy raise. The strategy can still serve the candidates of "
        "`compare()` that are not direct; use a strategy without gap to "
        "backtest this plan."
    )
    with pytest.warns(UserWarning, match=warn_msg):
        result = assistant.create_cv(profile, plan, gap=2)

    assert result.cv.gap == 2


@pytest.mark.parametrize(
    "forecaster, gap",
    [("ForecasterRecursive", 2), ("ForecasterDirect", 0)],
    ids=["recursive_with_gap", "direct_without_gap"],
)
def test_create_cv_no_warning_when_gap_can_run(forecaster, gap):
    """
    Test that create_cv() gives no warning for a recursive forecaster with a
    gap or a direct forecaster without one.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_h2o, target="x")
    plan = assistant.plan(profile, steps=6, forecaster=forecaster)

    # Warnings are errors in this suite.
    result = assistant.create_cv(profile, plan, gap=gap)

    assert result.cv.gap == gap


def test_create_cv_UserWarning_when_llm_sets_gap_for_direct_forecaster(monkeypatch):
    """
    Test that create_cv() warns about a direct forecaster with a gap also
    when the LLM chose the gap.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5, forecaster="ForecasterDirect")
    cv_params = CVParams(
        initial_train_size    = 50,
        refit                 = False,
        fixed_train_size      = False,
        gap                   = 2,
        fold_stride           = None,
        skip_folds            = None,
        allow_incomplete_fold = True,
        reasoning             = "Two days of delay before each forecast.",
    )

    class _FakeResult:
        output = cv_params

    class _FakeAgent:
        async def run(self, msg, **kw):
            return _FakeResult()

    monkeypatch.setattr(assistant, "_cv_agent", _FakeAgent())
    monkeypatch.setattr(assistant, "_resolve_model", lambda self_=None: "fake")

    warn_msg = re.escape(
        "ForecasterDirect is trained to predict 5 steps, and with `gap=2` "
        "each fold needs steps + gap = 7 steps ahead"
    )
    with pytest.warns(UserWarning, match=warn_msg):
        result = assistant.create_cv(profile, plan, prompt="Two days of delay")

    assert result.cv.gap == 2


def test_create_cv_UserWarning_when_first_window_shorter_than_forecaster():
    """
    Test that create_cv() builds the default strategy of a horizon that
    leaves no room for the window of the forecaster (h2o, 204 observations,
    `steps=100`: 2 folds take 200 and leave 4, and the default plan reads
    36), with a UserWarning that its backtest raises.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_h2o, target="x")
    plan = assistant.plan(profile, steps=100)

    warn_msg = re.escape(
        "The first training window of the strategy has 4 observations, and "
        "ForecasterRecursive needs at least 37 (more than its window size, "
        "36), so skforecast would fail: `backtest()` of this plan with this "
        "strategy raises. The strategy can still serve the candidates of "
        "`compare()` with a smaller window; use a later `initial_train_size`, "
        "or a shorter horizon, to backtest this plan."
    )
    with pytest.warns(UserWarning, match=warn_msg):
        result = assistant.create_cv(profile, plan)

    assert result.cv_config["n_folds"] == 2


def test_create_cv_output_when_long_series_start_on_different_dates():
    """
    Test that the default strategy of long data whose series start on
    different dates counts from the first date of the span, not from the
    latest first date of the series: the first training set ends inside the
    data, and backtest() runs the folds that `cv_config` states.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data             = df_multi_long_staggered,
        target           = "value",
        date_column      = "date",
        series_id_column = "series_id",
    )
    plan = assistant.plan(profile, steps=5)

    result = assistant.create_cv(profile, plan)
    backtest = assistant.backtest(
        data          = df_multi_long_staggered,
        cv            = result,
        profile       = profile,
        plan          = plan,
        show_progress = False,
    )

    assert profile.data_profile.start_date == "2023-03-02"
    assert profile.data_profile.span_start_date == "2023-01-01"
    assert result.cv_config["initial_train_size"] == "2023-03-11"
    assert result.cv_config["n_folds"] == 6
    assert backtest.predictions["fold"].nunique() == 6


def test_create_cv_output_when_dates_cross_a_daylight_saving_change():
    """
    Test that the default strategy of hourly data in a time zone with a
    daylight saving change is counted on the local times of the data: its
    date is an hour that exists (03:00, since 02:00 is skipped on
    2023-03-26), and backtest() runs the folds and the training size that
    `cv_config` states.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_hourly_madrid_spring, target="y")
    plan = assistant.plan(
        profile, steps=24, forecaster="ForecasterRecursive", estimator="Ridge",
        lags=24,
    )

    result = assistant.create_cv(profile, plan)
    backtest = assistant.backtest(
        data          = df_hourly_madrid_spring,
        cv            = result,
        profile       = profile,
        plan          = plan,
        show_progress = False,
    )

    assert profile.data_profile.time_zone == "Europe/Madrid"
    assert result.cv_config["initial_train_size"] == "2023-03-26 03:00:00"
    assert result.cv_config["n_folds"] == 3
    assert "    initial_train_size = 147," in backtest.code
    assert backtest.predictions.groupby("fold").size().tolist() == [24, 24, 15]


@pytest.mark.parametrize(
    "start, initial_train_size",
    [
        ("2012-11-20 18:00", "2012-11-29 11:00:00"),
        ("2023-03-20 18:00", "2023-03-29 12:00:00"),
    ],
    ids=["winter", "across the spring change"],
)
def test_create_cv_output_when_dates_with_time_zone_do_not_start_at_midnight(
    start, initial_train_size
):
    """
    Test that hourly data in a time zone whose first date is not midnight
    get a default strategy written in local time, and that its backtest
    runs the folds it states. The profile wrote the first date with its UTC
    offset, the strategy carried that offset, and the script failed with
    "Start and end cannot both be tz-aware with different timezones".
    """
    assistant = ForecastingAssistant()
    index = pd.date_range(start, periods=300, freq="h", tz="Europe/Madrid")
    data = pd.DataFrame({"y": np.arange(300, dtype=float) % 24}, index=index)
    profile = assistant.profile(data=data, target="y")
    plan = assistant.plan(
        profile, steps=24, forecaster="ForecasterRecursive", estimator="Ridge",
        lags=24,
    )

    result = assistant.create_cv(profile, plan)
    backtest = assistant.backtest(
        data=data, cv=result, profile=profile, plan=plan, show_progress=False
    )

    assert profile.data_profile.start_date == f"{start}:00"
    assert result.cv_config["initial_train_size"] == initial_train_size
    assert "    initial_train_size = 210," in backtest.code
    assert backtest.predictions["fold"].nunique() == result.cv_config["n_folds"]


# =============================================================================
# Tests: provenance of the strategy
# =============================================================================
_INITIAL_TRAIN_SIZE_DEFAULT = (
    "Initial training size by default: 70% of the 100 observations (70), up "
    "to 2023-03-11."
)
_TRAINED_ONCE_DEFAULT = (
    "Trained once by default: refitting in every fold would multiply the "
    "training cost by the 6 folds."
)


def test_create_cv_provenance_when_no_arguments():
    """
    Test that create_cv() without arguments records that nothing was
    passed, no LLM, and explains the two defaults with a rule: the share of
    the observations and the single training. The explanation of the
    strategy does not contain that text.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    result = assistant.create_cv(profile, plan)

    assert result.overridden_fields == []
    assert result.fields_without_effect == []
    assert result.llm_configured is False
    assert result.defaults_explanation == (
        f"{_INITIAL_TRAIN_SIZE_DEFAULT} {_TRAINED_ONCE_DEFAULT}"
    )
    assert result.explanation == (
        "Initial training up to 2023-03-11, trained once (no refit), 5-step "
        "horizon, 6 folds."
    )
    assert result.defaults_explanation not in result.explanation


def test_create_cv_provenance_names_in_the_same_order_as_backtest():
    """
    Test that the text of create_cv() names the parameters passed in the
    canonical order of `overridden_fields` (`fold_stride` before `refit`),
    so backtest() of the same strategy, which rebuilds the text from that
    list, says the same.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    result = assistant.create_cv(profile, plan, refit=True, fold_stride=5)
    backtested = assistant.backtest(
        data=df_single, cv=result, profile=profile, plan=plan, show_progress=False
    )

    assert result.overridden_fields == ["fold_stride", "refit"]
    assert result.defaults_explanation == (
        f"{_INITIAL_TRAIN_SIZE_DEFAULT} `fold_stride` and `refit` as requested."
    )
    assert backtested.cv_defaults_explanation == result.defaults_explanation


def test_create_cv_provenance_when_value_equal_to_default():
    """
    Test that an argument whose value equals the default is recorded as
    passed: the user decided it, whatever the rules would have said.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    result = assistant.create_cv(
        profile, plan, refit=False, gap=0, allow_incomplete_fold=True
    )

    assert result.overridden_fields == ["refit", "gap", "allow_incomplete_fold"]
    assert result.fields_without_effect == []
    assert result.defaults_explanation == (
        f"{_INITIAL_TRAIN_SIZE_DEFAULT} `refit`, `gap` and "
        "`allow_incomplete_fold` as requested."
    )


@pytest.mark.parametrize(
    "skip_folds, expected",
    [([], ["skip_folds"]), (1, ["skip_folds"]), ([1], ["skip_folds"])],
    ids=["empty_list", "integer", "list"],
)
def test_create_cv_provenance_when_skip_folds(skip_folds, expected):
    """
    Test that any value of `skip_folds` other than None is recorded as
    passed, an empty list included: it is applied to the strategy like
    the others, also over what the LLM would set.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    result = assistant.create_cv(profile, plan, skip_folds=skip_folds)

    assert result.overridden_fields == expected


def test_create_cv_provenance_when_all_arguments_passed():
    """
    Test that every argument passed is recorded, in the canonical order of
    CV_OVERRIDE_NAMES, and that no default is explained.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    result = assistant.create_cv(
        profile, plan, initial_train_size=60, fold_stride=5, refit=True,
        fixed_train_size=True, gap=0, skip_folds=1, allow_incomplete_fold=True,
    )

    assert result.overridden_fields == list(CV_OVERRIDE_NAMES)
    assert result.fields_without_effect == []
    assert "by default" not in result.defaults_explanation
    assert result.defaults_explanation.endswith(" as requested.")


def test_create_cv_provenance_when_fixed_train_size_without_refit():
    """
    Test that a `fixed_train_size` passed for a forecaster trained once
    (it warns) is recorded as passed and as without effect, and the text
    says so instead of "as requested".
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    with pytest.warns(IgnoredArgumentWarning, match="`fixed_train_size=True`"):
        result = assistant.create_cv(profile, plan, fixed_train_size=True)

    assert result.overridden_fields == ["fixed_train_size"]
    assert result.fields_without_effect == ["fixed_train_size"]
    assert result.defaults_explanation == (
        f"{_INITIAL_TRAIN_SIZE_DEFAULT} {_TRAINED_ONCE_DEFAULT} "
        "`fixed_train_size` was passed but has no effect on this forecaster."
    )


@pytest.mark.parametrize(
    "kwargs, without_effect, expected",
    [
        (
            {"refit": False},
            ["refit"],
            "`refit` was passed but has no effect on this forecaster.",
        ),
        (
            {"refit": False, "fixed_train_size": False},
            ["refit", "fixed_train_size"],
            "`refit` and `fixed_train_size` were passed but have no effect on "
            "this forecaster.",
        ),
        ({"refit": True}, [], "`refit` as requested."),
    ],
    ids=["refit_false", "refit_false_expanding", "refit_true"],
)
def test_create_cv_provenance_when_forecaster_is_stats(
    kwargs, without_effect, expected
):
    """
    Test that for ForecasterStats the arguments skforecast does not run are
    without effect (it refits in every fold), the text has no sentence about
    refit as a default, and an argument it runs is "as requested".
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_h2o, target="x")
    plan = assistant.plan(profile, steps=12, forecaster="ForecasterStats")

    warns = (
        pytest.warns(IgnoredArgumentWarning, match="do not apply to ForecasterStats")
        if without_effect else contextlib.nullcontext()
    )
    with warns:
        result = assistant.create_cv(profile, plan, **kwargs)

    assert result.overridden_fields == list(kwargs)
    assert result.fields_without_effect == without_effect
    assert result.defaults_explanation == (
        "Initial training size by default: 70% of the 204 observations "
        f"(142), up to 2003-04-01. {expected}"
    )


def test_create_cv_provenance_when_forecaster_is_stats_without_arguments():
    """
    Test that ForecasterStats without arguments explains the initial
    training size only: refit is not a default it chose.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_h2o, target="x")
    plan = assistant.plan(profile, steps=12, forecaster="ForecasterStats")

    result = assistant.create_cv(profile, plan)

    assert result.defaults_explanation == (
        "Initial training size by default: 70% of the 204 observations "
        "(142), up to 2003-04-01."
    )


@pytest.mark.parametrize(
    "kwargs, without_effect, expected",
    [
        ({}, [], ""),
        (
            {"refit": True, "fixed_train_size": True},
            ["refit", "fixed_train_size"],
            " `refit` and `fixed_train_size` were passed but have no effect on "
            "this forecaster.",
        ),
        ({"gap": 1}, [], " `gap` as requested."),
    ],
    ids=["defaults", "refit_and_fixed_train_size", "gap"],
)
def test_create_cv_provenance_when_plan_is_foundation(
    kwargs, without_effect, expected
):
    """
    Test that for a foundation plan the text says "First fold start by
    default", has no sentence about refit, and reports `refit` and
    `fixed_train_size` as without effect because the model is not trained.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5, forecaster="ForecasterFoundation")

    result = assistant.create_cv(profile, plan, **kwargs)

    assert result.overridden_fields == list(kwargs)
    assert result.fields_without_effect == without_effect
    assert result.defaults_explanation == (
        "First fold start by default: 70% of the 100 observations (70), up "
        f"to 2023-03-11.{expected}"
    )


def test_create_cv_provenance_when_llm_succeeds(monkeypatch):
    """
    Test that when the LLM sets the parameters `llm_configured` is True and
    no default is explained (its reasoning, in the explanation, does it);
    the names the user passed are still said "as requested".
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    _install_fake_cv_agent(
        monkeypatch, assistant, [_make_cv_params(50, "Retrain every fold.")]
    )

    result = assistant.create_cv(profile, plan, prompt="I retrain weekly")
    result_with_gap = assistant.create_cv(
        profile, plan, prompt="I retrain weekly", gap=1
    )

    assert result.llm_configured is True
    assert result.overridden_fields == []
    assert result.defaults_explanation == ""
    assert result.explanation.startswith("Retrain every fold.")
    assert result_with_gap.llm_configured is True
    assert result_with_gap.overridden_fields == ["gap"]
    assert result_with_gap.defaults_explanation == "`gap` as requested."


def test_create_cv_provenance_when_llm_fails(monkeypatch):
    """
    Test that when the LLM fails after its retries and the deterministic
    defaults are used, `llm_configured` is False and the defaults are
    explained.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    n_obs = profile.data_profile.series_lengths["sales"].length
    _install_fake_cv_agent(
        monkeypatch, assistant, [_make_cv_params(n_obs - 3, "Always bad.")]
    )

    with pytest.warns(UserWarning, match=re.escape("LLM CV configuration failed")):
        result = assistant.create_cv(profile, plan, prompt="Bad scenario")

    assert result.llm_configured is False
    assert result.overridden_fields == []
    assert result.defaults_explanation == (
        f"{_INITIAL_TRAIN_SIZE_DEFAULT} {_TRAINED_ONCE_DEFAULT}"
    )


def test_create_cv_provenance_when_prompt_ignored(monkeypatch):
    """
    Test that when the prompt is ignored because every parameter was passed
    the LLM did not configure anything: `llm_configured` is False and the
    seven names are recorded as passed.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    call_count = _install_fake_cv_agent(
        monkeypatch, assistant, [_make_cv_params(50, "Not used.")]
    )

    with pytest.warns(UserWarning, match=re.escape("Prompt ignored")):
        result = assistant.create_cv(
            profile, plan, prompt="I retrain weekly", initial_train_size=50,
            fold_stride=5, refit=True, fixed_train_size=True, gap=0,
            skip_folds=1, allow_incomplete_fold=True,
        )

    assert call_count["n"] == 0
    assert result.llm_configured is False
    assert result.overridden_fields == list(CV_OVERRIDE_NAMES)
    assert "by default" not in result.defaults_explanation
    assert result.defaults_explanation.endswith(" as requested.")
