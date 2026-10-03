# Unit test forecast_code ForecastingAssistant

import numpy as np
import pandas as pd
import re

import pytest


from skforecast_ai import ForecastingAssistant
from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.schemas import CodeGenerationResult, PreprocessingStep

from tests.fixtures_assistant import (
    df_multi_long,
    df_multi_wide,
    df_no_exog,
    df_range_index,
    df_single,
)
from tests.fixtures_datasets import (
    df_h2o,
    df_h2o_daily,
)


# =============================================================================
# Tests: forecast_code with pre-computed profile and plan
# =============================================================================
def test_forecast_code_with_profile_and_plan_when_single_series():
    """
    Test that forecast_code() with pre-computed profile and plan produces
    a valid Python script for single series.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    result = assistant.forecast_code(
        data=df_single, target="sales", steps=10, profile=profile, plan=plan
    )

    assert isinstance(result, CodeGenerationResult)
    assert isinstance(result.code, str)
    assert "import" in result.code
    assert "ForecasterRecursive" in result.code
    assert "fit" in result.code or "predict" in result.code


def test_forecast_code_with_profile_and_plan_when_multi_series():
    """
    Test that forecast_code() with pre-computed profile and plan produces
    code containing the multi-series forecaster class.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=df_multi_long,
        target="value",
        date_column="date",
        series_id_column="series_id",
    )
    plan = assistant.plan(profile, steps=5)

    result = assistant.forecast_code(
        data=df_multi_long, target="value", steps=5, profile=profile, plan=plan
    )

    assert isinstance(result, CodeGenerationResult)
    assert "ForecasterRecursiveMultiSeries" in result.code


def test_forecast_code_with_profile_and_plan_when_statistical():
    """
    Test that forecast_code() with pre-computed profile and plan produces
    code for statistical models (ForecasterStats).
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(
        profile, steps=10, forecaster="ForecasterStats"
    )

    result = assistant.forecast_code(
        data=df_single, target="sales", steps=10, profile=profile, plan=plan
    )

    assert isinstance(result, CodeGenerationResult)
    assert "ForecasterStats" in result.code


def test_forecast_code_with_profile_and_plan_when_baseline():
    """
    Test that forecast_code() with pre-computed profile and plan produces
    code for the baseline (ForecasterEquivalentDate) without exogenous
    variables.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(
        profile, steps=10, forecaster="ForecasterEquivalentDate"
    )

    result = assistant.forecast_code(
        data=df_single, profile=profile, plan=plan
    )

    assert isinstance(result, CodeGenerationResult)
    assert "ForecasterEquivalentDate(" in result.code
    assert "offset    = 7," in result.code
    assert "exog" not in result.code


def test_forecast_code_with_profile_and_plan_contains_frequency():
    """
    Test that generated code includes the frequency assignment.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    result = assistant.forecast_code(
        data=df_single, target="sales", steps=10, profile=profile, plan=plan
    )

    assert "freq" in result.code.lower() or "asfreq" in result.code


# =============================================================================
# Tests: forecast_code: basic output
# =============================================================================
def test_forecast_code_output_when_single_series():
    """
    Test that forecast_code() returns a CodeGenerationResult with all
    fields populated for a single-series dataset.
    """
    assistant = ForecastingAssistant()
    result = assistant.forecast_code(
        data=df_single, target="sales", date_column="date", steps=10
    )

    assert isinstance(result, CodeGenerationResult)
    assert isinstance(result.code, str)
    assert result.plan.steps == 10
    assert result.profile is not None
    assert "import" in result.code


def test_forecast_code_output_when_forecaster_selected():
    """
    Test that forecast_code() generates code for an explicitly selected
    forecaster.
    """
    assistant = ForecastingAssistant()
    result = assistant.forecast_code(
        data=df_single,
        target="sales",
        date_column="date",
        steps=10,
        forecaster="ForecasterDirect",
    )

    assert result.plan.forecaster == "ForecasterDirect"
    assert "ForecasterDirect" in result.code


def test_forecast_code_output_when_no_exog():
    """
    Test that forecast_code() works correctly for data without exogenous
    variables.
    """
    assistant = ForecastingAssistant()
    result = assistant.forecast_code(
        data=df_no_exog, target="sales", date_column="date", steps=10
    )

    assert isinstance(result, CodeGenerationResult)
    assert result.plan.use_exog is False


def test_forecast_code_output_when_interval_requested():
    """
    Test that forecast_code() includes interval logic when interval is
    specified.
    """
    assistant = ForecastingAssistant()
    result = assistant.forecast_code(
        data=df_single,
        target="sales",
        date_column="date",
        steps=10,
        interval=[0.1, 0.9],
    )

    assert result.plan.interval == [0.1, 0.9]
    assert "interval" in result.code.lower() or "predict_interval" in result.code


# =============================================================================
# Tests: evaluation vs prediction mode
# =============================================================================
def test_forecast_code_prediction_mode_when_test_size_not_set():
    """
    Test that forecast_code() generates prediction-mode code by default
    (no test_size): no train/test split, no metrics, fit on the full data.
    """
    assistant = ForecastingAssistant()
    result = assistant.forecast_code(
        data=df_no_exog, target="sales", date_column="date", steps=10
    )

    assert result.plan.end_train is None
    assert "# Train/test split" not in result.code
    assert "data_train" not in result.code
    assert "# Evaluate on test set" not in result.code


def test_forecast_code_evaluation_mode_when_test_size_set():
    """
    Test that forecast_code() generates evaluation-mode code when test_size
    is set: train/test split, metrics, and a concrete end_train date.
    """
    assistant = ForecastingAssistant()
    result = assistant.forecast_code(
        data=df_no_exog, target="sales", date_column="date", steps=10,
        test_size=10,
    )

    assert result.plan.end_train is not None
    assert "# Train/test split" in result.code
    assert "data_train" in result.code
    assert "# Evaluate on test set" in result.code


# =============================================================================
# Tests: exog argument (mirrors forecast, validation only)
# =============================================================================
def test_forecast_code_does_not_require_exog_in_prediction_mode():
    """
    Test that forecast_code() generates prediction-mode code for data with
    exogenous variables without requiring future `exog` (unlike forecast(),
    the script loads the future values from a CSV at run time).
    """
    assistant = ForecastingAssistant()
    result = assistant.forecast_code(
        data=df_single, target="sales", date_column="date", steps=10
    )

    assert result.plan.end_train is None
    assert "data_train" not in result.code
    assert "exog_future" in result.code


def test_forecast_code_output_when_data_has_final_rows_without_target():
    """
    Test that forecast_code() renders the script for data with final rows
    without a target value: only forecast(), which runs the script, checks
    the last values of the target.
    """
    future = pd.DataFrame({
        "date": pd.date_range("2023-04-11", periods=5, freq="D"),
        "sales": np.nan,
        "promo": 0.0,
    })
    data = pd.concat([df_single, future], ignore_index=True)

    result = ForecastingAssistant().forecast_code(
        data=data, target="sales", date_column="date", steps=5
    )

    assert isinstance(result, CodeGenerationResult)
    assert "predictions = forecaster.predict(" in result.code


def test_forecast_code_ValueError_when_test_size_and_exog_combined():
    """
    Test that forecast_code() rejects `test_size` and `exog` supplied
    together, mirroring forecast().
    """
    future_dates = pd.date_range("2023-04-11", periods=10, freq="D")
    exog = pd.DataFrame(
        {"promo": np.tile([0.0, 1.0], 5)}, index=future_dates
    )

    assistant = ForecastingAssistant()
    with pytest.raises(ValueError, match="only used for future prediction"):
        assistant.forecast_code(
            data=df_single, target="sales", date_column="date", steps=10,
            test_size=10, exog=exog,
        )


def test_forecast_code_ValueError_when_exog_without_exog_data():
    """
    Test that forecast_code() rejects future `exog` when the data has no
    exogenous variables, mirroring forecast().
    """
    future_dates = pd.date_range("2023-04-11", periods=10, freq="D")
    exog = pd.DataFrame(
        {"promo": np.tile([0.0, 1.0], 5)}, index=future_dates
    )

    assistant = ForecastingAssistant()
    with pytest.raises(ValueError, match="data contains no exogenous"):
        assistant.forecast_code(
            data=df_no_exog, target="sales", date_column="date", steps=10,
            exog=exog,
        )


# =============================================================================
# Tests: plan overrides
# =============================================================================
def test_forecast_code_output_when_interval_passed_with_plan():
    """
    Test that an `interval` passed alongside a pre-built plan replaces the
    plan's interval in the rendered script, so the script predicts the
    requested bounds.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    result = assistant.forecast_code(
        data=df_single,
        target="sales",
        steps=10,
        interval=[0.1, 0.9],
        profile=profile,
        plan=plan,
    )

    assert result.plan.interval == [0.1, 0.9]
    assert "predict_interval" in result.code


def test_forecast_code_ValueError_when_window_features_differ_from_plan():
    """
    Test that forecast_code() rejects a `window_features` override that
    differs from the window features of the pre-built plan, naming the
    argument, because the planning stage that consumes it is skipped.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    with pytest.raises(ValueError, match=re.escape("['window_features']")):
        assistant.forecast_code(
            data=df_single,
            target="sales",
            date_column="date",
            steps=10,
            window_features=[{"stats": ["mean"], "window_size": 3}],
            profile=profile,
            plan=plan,
        )


def test_forecast_code_ValueError_when_estimator_differs_from_plan():
    """
    Test that forecast_code() rejects an `estimator` override that differs
    from the estimator of the pre-built plan, and that the message points
    to `refine_plan()`.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10, estimator="Ridge")

    with pytest.raises(ValueError, match=re.escape("refine_plan()")):
        assistant.forecast_code(
            data=df_single,
            target="sales",
            steps=10,
            estimator="LGBMRegressor",
            profile=profile,
            plan=plan,
        )


def test_forecast_code_ValueError_when_data_conflicts_with_profile():
    """
    Test that forecast_code() checks supplied data against the supplied
    profile, so a dataset lacking the profile's target is reported before
    any script is rendered.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    with pytest.raises(ValueError, match=re.escape("column(s) ['sales']")):
        assistant.forecast_code(
            data=df_single.drop(columns=["sales"]), profile=profile, plan=plan
        )


def test_forecast_code_ValueError_when_steps_conflicts_with_plan():
    """
    Test that forecast_code() rejects a `steps` different from
    `plan.steps`, like forecast() does.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=7)

    with pytest.raises(ValueError, match="does not match `plan.steps`"):
        assistant.forecast_code(steps=3, profile=profile, plan=plan)


def test_forecast_code_ValueError_when_neither_steps_nor_plan():
    """
    Test that forecast_code() without `steps` and without a plan raises a
    clear ValueError.
    """
    assistant = ForecastingAssistant()

    with pytest.raises(ValueError, match="`steps` is required"):
        assistant.forecast_code(data=df_single, target="sales", date_column="date")


def test_forecast_code_output_when_received_plan_is_valid():
    """
    Test that a valid received plan is used as it is: the result refers to
    the object the caller passed.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_no_exog, target="sales", date_column="date")
    plan = assistant.plan(profile=profile, steps=5, estimator="Ridge")

    result = assistant.forecast_code(profile=profile, plan=plan)

    assert result.plan is plan


@pytest.mark.parametrize(
    "update",
    [
        {"steps": 5.0},
        {"preprocessing_steps": [
            {
                "action": "drop_duplicates",
                "reason": "Timestamps repeated in identical rows.",
                "code_snippet": "data = data[~data.index.duplicated(keep='first')]",
                "blocking": True,
            }
        ]},
    ],
    ids=["steps as an integral float", "preprocessing steps as dicts"],
)
def test_forecast_code_output_when_received_plan_holds_values_of_another_type(update):
    """
    Test that a received plan whose values validation converts to another
    type (set with `model_copy`) is replaced by the validated copy, so the
    script is rendered from the validated values.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_no_exog, target="sales", date_column="date")
    plan = assistant.plan(profile=profile, steps=5, estimator="Ridge").model_copy(
        update=update
    )

    result = assistant.forecast_code(profile=profile, plan=plan)

    assert result.plan is not plan
    assert type(result.plan.steps) is int
    assert all(
        isinstance(step, PreprocessingStep) for step in result.plan.preprocessing_steps
    )


# =============================================================================
# Tests: error code and field
# =============================================================================
def test_forecast_code_InvalidInputError_field_when_arguments_differ_from_plan():
    """
    Test that arguments that differ from a pre-built plan raise
    InvalidInputError with the first of them as field, the argument to omit.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10, estimator="Ridge")

    err_msg = re.escape(
        "A pre-built `plan` was provided and the following argument(s) differ "
        "from what it holds: ['estimator', 'lags']. Omit them to use the plan "
        "as is, or refine the plan with `refine_plan()` first."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        assistant.forecast_code(
            data      = df_single,
            target    = "sales",
            steps     = 10,
            estimator = "LGBMRegressor",
            lags      = 2,
            profile   = profile,
            plan      = plan,
        )

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "estimator"


def test_forecast_code_loads_data_path_when_saved_profile(tmp_path):
    """
    Test that forecast_code() with a saved profile and data given as
    another CSV path returns a script that loads the path given.
    """
    old_path = tmp_path / "old.csv"
    new_path = tmp_path / "new.csv"
    df_single.to_csv(old_path, index=False)
    df_single.to_csv(new_path, index=False)
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=old_path, target="sales", date_column="date")

    result = assistant.forecast_code(
        data=new_path, steps=5, test_size=5, profile=profile
    )

    assert f"data = pd.read_csv({str(new_path)!r})" in result.code
    assert result.profile.data_profile.data_path == str(new_path)


# =============================================================================
# Tests: plan received for data of another structure
# =============================================================================
_PLAN_OF_ANOTHER_STRUCTURE = [
    (
        {"data": df_single, "target": "sales", "date_column": "date"},
        "monthly",
        "The plan was built for data of frequency 'MS', and the data has "
        "frequency 'D'. Build the plan from the profile of these data with "
        "`plan()`.",
        "plan",
    ),
    (
        {
            "data": df_multi_wide,
            "target": ["series_a", "series_b"],
            "date_column": "date",
        },
        "daily",
        "Task type 'single_series' supports a single series only, but the "
        "input contains 2 series (['series_a', 'series_b']). Use a "
        "multi-series forecaster (e.g. 'ForecasterRecursiveMultiSeries') or "
        "provide a single series.",
        "forecaster",
    ),
    (
        {"data": df_no_exog, "target": "sales", "date_column": "date"},
        "daily",
        "The plan uses exogenous variables and the data has none. Build the "
        "plan from the profile of these data with `plan()`.",
        "plan",
    ),
    (
        {"data": df_range_index, "target": "sales"},
        "no_frequency",
        "The plan has calendar features, which need dates, and the data has "
        "no datetime index. Build the plan from the profile of these data "
        "with `plan()`.",
        "plan",
    ),
]


def _plan_for(kind):
    """
    Return the plan of the case: one built for monthly data (h2o), or a
    daily one of df_single (edited to frequency None and without exog for
    the case of data without frequency).
    """
    assistant = ForecastingAssistant()
    if kind == "monthly":
        return assistant.plan(assistant.profile(data=df_h2o, target="x"), steps=5)
    plan = assistant.plan(
        assistant.profile(data=df_single, target="sales", date_column="date"),
        steps=5,
    )
    if kind == "no_frequency":
        plan = plan.model_copy(update={"frequency": None, "use_exog": False})
    return plan


@pytest.mark.parametrize(
    "data_kwargs, plan_kind, message, field",
    _PLAN_OF_ANOTHER_STRUCTURE,
    ids=["frequency", "task_type", "exog", "calendar_features"],
)
def test_forecast_code_InvalidInputError_when_plan_built_for_other_data(
    data_kwargs, plan_kind, message, field
):
    """
    Test that forecast_code() raises InvalidInputError when the plan was built for
    data of another frequency, shape, exogenous variables or index type
    than the data received.
    """
    assistant = ForecastingAssistant()

    with pytest.raises(InvalidInputError, match=re.escape(message)) as exc_info:
        assistant.forecast_code(steps=5, plan=_plan_for(plan_kind), **data_kwargs)

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == field


def test_forecast_code_output_when_plan_carries_end_train_without_test_size():
    """
    Test that forecast_code() with a plan that carries the `end_train` of an
    evaluation and no `test_size` renders the evaluation script (train/test
    split) and keeps the plan, while forecast() raises in that case.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    split_date = str(df_single["date"].iloc[-6].date())
    plan = assistant.plan(profile, steps=5).model_copy(
        update={"end_train": split_date}
    )

    result = assistant.forecast_code(
        data=df_single, steps=5, profile=profile, plan=plan
    )

    assert result.plan.end_train == split_date
    assert "forecaster.fit(y=data_train['sales'], exog=data_train[exog_features])" in (
        result.code
    )
    assert "# Evaluate on test set" in result.code
    assert "mean_absolute_error(actual, predictions)" in result.code


# =============================================================================
# Tests: data against a saved profile
# =============================================================================
def test_forecast_code_output_when_data_have_more_rows_than_profile():
    """
    Test that forecast_code() with data that extend the saved profile (192
    rows in the profile, 204 in the data) returns the new profile with the
    note, and a script of the same shape as the one of the saved profile.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_h2o.iloc[:192], target="x")

    result = assistant.forecast_code(data=df_h2o, profile=profile, steps=3)
    saved_result = assistant.forecast_code(
        data=df_h2o.iloc[:192], profile=profile, steps=3
    )

    assert result.profile.data_profile.n_total_observations == 204
    assert result.profile.data_profile.warnings == [
        "The data differ in their values from the profile passed (changed: "
        "series_lengths, span_index_length, n_total_observations, "
        "target_stats): the profile was computed again from these data."
    ]
    assert saved_result.profile.data_profile.warnings == []
    assert result.code == saved_result.code


def test_forecast_code_output_when_data_equal_to_profile():
    """
    Test that forecast_code() with data equal to the saved profile returns
    the profile unchanged, without a note.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_h2o, target="x")

    result = assistant.forecast_code(data=df_h2o, profile=profile, steps=3)

    assert result.profile.data_profile == profile.data_profile
    assert result.profile.data_profile.warnings == []


def test_forecast_code_output_when_same_data_in_another_csv_file(tmp_path):
    """
    Test that forecast_code() given a saved profile of a CSV file and a copy
    of that file under another path keeps the profile (the path is not a
    difference of values): no note is added, and the profile and the script
    record the path passed.
    """
    first_path = tmp_path / "first.csv"
    copy_path = tmp_path / "copy.csv"
    df_single.to_csv(first_path, index=False)
    df_single.to_csv(copy_path, index=False)
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=first_path, target="sales", date_column="date"
    )

    result = assistant.forecast_code(data=copy_path, profile=profile, steps=3)

    assert result.profile.data_profile.warnings == profile.data_profile.warnings
    assert result.profile.data_profile.data_path == str(copy_path)
    assert result.profile.data_profile.model_dump(
        exclude={"data_path"}
    ) == profile.data_profile.model_dump(exclude={"data_path"})
    assert f"data = pd.read_csv({str(copy_path)!r})" in result.code


@pytest.mark.parametrize(
    "data, differences",
    [
        (df_h2o_daily, "(frequency: 'MS' != 'D')"),
    ],
    ids=["frequency"],
)
def test_forecast_code_InvalidInputError_when_data_have_other_structure_than_profile(
    data, differences
):
    """
    Test that forecast_code() raises InvalidInputError with the field
    'profile' when the data have another frequency
    than the saved profile.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_h2o, target="x")

    err_msg = re.escape(
        f"The data do not have the structure of the profile passed {differences}: "
        f"profile these data and build the plan from that profile."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        assistant.forecast_code(data=data, profile=profile, steps=3)

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "profile"


def test_forecast_code_output_when_metric_given():
    """
    Test that forecast_code() builds its plan with `metric`, so the script
    of an evaluation computes only the metrics chosen.
    """
    assistant = ForecastingAssistant()

    result = assistant.forecast_code(
        data=df_no_exog, target="sales", date_column="date", steps=5,
        test_size=5, metric="mean_squared_error",
    )

    assert result.plan.metrics_to_compute == ["mean_squared_error"]
    assert "from sklearn.metrics import mean_squared_error\n" in result.code
    assert "mean_absolute_error" not in result.code


def test_forecast_code_output_when_use_exog_false():
    """
    Test that forecast_code() builds its plan with `use_exog=False`, whose
    prediction script does not load future exogenous values.
    """
    assistant = ForecastingAssistant()

    result = assistant.forecast_code(
        data=df_single, target="sales", date_column="date", steps=5,
        use_exog=False,
    )

    assert result.plan.use_exog is False
    assert "exog_future.csv" not in result.code
