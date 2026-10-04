# Unit test backtest_code ForecastingAssistant

import re

import pytest

from skforecast.model_selection import TimeSeriesFold

from skforecast_ai import CodeGenerationResult, ForecastingAssistant
from skforecast_ai.exceptions import InvalidInputError, InvalidInputTypeError

from tests.fixtures_assistant import (
    df_multi_long,
    df_multi_wide,
    df_no_exog,
    df_single,
)
from tests.fixtures_datasets import (
    df_h2o,
    df_h2o_daily,
)

assistant = ForecastingAssistant()


# =============================================================================
# Tests: error / validation
# =============================================================================
def test_backtest_code_ValueError_when_cv_steps_differs_from_plan_steps():
    """
    Test that backtest_code() raises ValueError when cv.steps != plan.steps
    and plan is explicitly provided.
    """
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    cv = TimeSeriesFold(steps=5, initial_train_size=70, verbose=False)

    err_msg = re.escape("cv.steps (5) does not match plan.steps (10)")
    with pytest.raises(ValueError, match=err_msg):
        assistant.backtest_code(
            data=df_single,
            target="sales",
            date_column="date",
            cv=cv,
            profile=profile,
            plan=plan,
        )


# =============================================================================
# Tests: basic output
# =============================================================================
def test_backtest_code_output_when_single_series():
    """
    Test that backtest_code() returns a CodeGenerationResult with valid
    backtesting code for a single-series dataset.
    """
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    cv = assistant.create_cv(profile, plan).cv

    result = assistant.backtest_code(
        data=df_single,
        target="sales",
        date_column="date",
        cv=cv,
        profile=profile,
        plan=plan,
    )

    assert isinstance(result, CodeGenerationResult)
    assert isinstance(result.code, str)
    assert result.profile is not None
    assert result.plan is not None
    assert result.plan.steps == 5
    assert "backtesting_forecaster" in result.code
    assert "TimeSeriesFold" in result.code
    assert "skforecast" in result.code


def test_backtest_code_output_when_multi_series():
    """
    Test that backtest_code() generates code containing the multi-series
    backtesting call for a long-format multi-series dataset.
    """
    profile = assistant.profile(
        data=df_multi_long,
        target="value",
        date_column="date",
        series_id_column="series_id",
    )
    plan = assistant.plan(profile, steps=5)
    cv = assistant.create_cv(profile, plan).cv

    result = assistant.backtest_code(
        data=df_multi_long,
        target="value",
        date_column="date",
        series_id_column="series_id",
        cv=cv,
        profile=profile,
        plan=plan,
    )

    assert isinstance(result, CodeGenerationResult)
    assert "backtesting_forecaster_multiseries" in result.code
    assert "ForecasterRecursiveMultiSeries" in result.code


def test_backtest_code_output_when_no_profile_or_plan():
    """
    Test that backtest_code() auto-generates profile and plan when not
    provided.
    """
    cv = TimeSeriesFold(steps=5, initial_train_size=70, verbose=False)

    result = assistant.backtest_code(
        data=df_single,
        target="sales",
        date_column="date",
        cv=cv,
    )

    assert isinstance(result, CodeGenerationResult)
    assert result.plan.steps == 5
    assert "backtesting_forecaster" in result.code


def test_backtest_code_output_when_no_exog():
    """
    Test that backtest_code() works correctly for data without exogenous
    variables.
    """
    cv = TimeSeriesFold(steps=5, initial_train_size=70, verbose=False)

    result = assistant.backtest_code(
        data=df_no_exog,
        target="sales",
        date_column="date",
        cv=cv,
    )

    assert isinstance(result, CodeGenerationResult)
    assert result.plan.use_exog is False
    assert "backtesting_forecaster" in result.code


def test_backtest_code_contains_cv_configuration():
    """
    Test that the generated code includes TimeSeriesFold configuration
    matching the provided cv object.
    """
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    cv = TimeSeriesFold(
        steps=5, initial_train_size=70, refit=False, verbose=False
    )

    result = assistant.backtest_code(
        data=df_single,
        target="sales",
        date_column="date",
        cv=cv,
        profile=profile,
        plan=plan,
    )

    assert "initial_train_size" in result.code
    assert "refit" in result.code


def test_backtest_code_output_when_cv_result_given():
    """
    Test that backtest_code() accepts a CVResult and embeds the same
    TimeSeriesFold construction in the generated script.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    cv_result = assistant.create_cv(profile, plan, initial_train_size=60)

    result = assistant.backtest_code(
        data=df_single, cv=cv_result, profile=profile, plan=plan
    )

    assert "cv = TimeSeriesFold(" in result.code
    assert "initial_train_size = 60" in result.code


def test_backtest_code_loads_data_path_when_saved_profile(tmp_path):
    """
    Test that backtest_code() with a saved profile and data given as
    another CSV path returns a script that loads the path given; without
    data it keeps the path of the profile.
    """
    old_path = tmp_path / "old.csv"
    new_path = tmp_path / "new.csv"
    df_single.to_csv(old_path, index=False)
    df_single.to_csv(new_path, index=False)
    profile = assistant.profile(data=old_path, target="sales", date_column="date")
    cv = TimeSeriesFold(steps=5, initial_train_size=60)

    with_data = assistant.backtest_code(data=new_path, cv=cv, profile=profile)
    without_data = assistant.backtest_code(data=None, cv=cv, profile=profile)

    assert f"data = pd.read_csv({str(new_path)!r})" in with_data.code
    assert f"data = pd.read_csv({str(old_path)!r})" in without_data.code
    assert without_data.profile is profile


@pytest.mark.parametrize(
    "cv, type_name",
    [({"steps": 5}, "dict"), (None, "NoneType"), (5, "int")],
    ids=["dict", "None", "int"],
)
def test_backtest_code_InvalidInputTypeError_when_cv_wrong_type(cv, type_name):
    """
    Test that backtest_code() raises InvalidInputTypeError (a TypeError) with
    the field 'cv' when it is not a TimeSeriesFold or a CVResult.
    """
    err_msg = re.escape(
        f"`cv` must be a skforecast TimeSeriesFold or the CVResult of "
        f"create_cv(), got {type_name}."
    )
    with pytest.raises(InvalidInputTypeError, match=err_msg) as exc_info:
        assistant.backtest_code(
            data=df_single, cv=cv, target="sales", date_column="date"
        )

    assert isinstance(exc_info.value, TypeError)
    assert exc_info.value.field == "cv"


# =============================================================================
# Tests: coherence of the CVResult, the plan and the profile
# =============================================================================
def test_backtest_code_output_when_cv_result_without_plan_keeps_its_plan():
    """
    Test that backtest_code() with the CVResult of create_cv() and no
    `plan`, `forecaster`, `estimator`, `estimator_kwargs` or `interval`
    renders the plan of the CVResult: its estimator and interval are kept.
    """
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(
        profile, steps=5, estimator="LGBMRegressor", interval=[0.1, 0.9]
    )
    cv_result = assistant.create_cv(profile, plan, initial_train_size=60)

    result = assistant.backtest_code(
        data=df_single, target="sales", date_column="date", cv=cv_result
    )

    assert result.plan == cv_result.plan
    assert "from lightgbm import LGBMRegressor" in result.code
    assert "estimator            = LGBMRegressor(random_state=123, verbose=-1)," in (
        result.code
    )
    assert "interval          = [0.1, 0.9]," in result.code


def test_backtest_code_output_when_cv_result_and_estimator_passed_builds_new_plan():
    """
    Test that backtest_code() with the CVResult and an `estimator` renders a
    new plan with it, without the interval of the plan of the CVResult.
    """
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(
        profile, steps=5, estimator="LGBMRegressor", interval=[0.1, 0.9]
    )
    cv_result = assistant.create_cv(profile, plan, initial_train_size=60)

    result = assistant.backtest_code(
        data=df_single,
        target="sales",
        date_column="date",
        cv=cv_result,
        estimator="Ridge",
    )

    assert result.plan.estimator == "Ridge"
    assert result.plan.interval is None
    assert "estimator            = Ridge()," in result.code
    assert "LGBMRegressor" not in result.code
    assert "interval" not in result.code


def test_backtest_code_output_when_bare_time_series_fold_builds_default_plan():
    """
    Test that backtest_code() with the TimeSeriesFold of a CVResult builds
    the default plan, not the plan of the CVResult.
    """
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(
        profile, steps=5, estimator="LGBMRegressor", interval=[0.1, 0.9]
    )
    cv_result = assistant.create_cv(profile, plan, initial_train_size=60)

    result = assistant.backtest_code(
        data=df_single, target="sales", date_column="date", cv=cv_result.cv
    )

    assert result.plan == assistant.plan(profile, steps=5)
    assert "estimator            = Ridge()," in result.code
    assert "LGBMRegressor" not in result.code


def test_backtest_code_InvalidInputError_when_cv_result_of_another_structure():
    """
    Test that backtest_code() raises InvalidInputError with the field 'cv'
    when the CVResult was created for data of another structure.
    """
    h2o_profile = assistant.profile(data=df_h2o, target="x")
    cv_result = assistant.create_cv(h2o_profile, assistant.plan(h2o_profile, steps=5))

    err_msg = re.escape(
        "The CVResult was created for data of another structure "
        "(data_format: 'single' != 'wide'; "
        "target: 'x' != ['series_a', 'series_b']; "
        "date_column: None != 'date'; "
        "frequency: 'MS' != 'D'). Create the strategy from the profile of "
        "these data with `create_cv()`, or pass its TimeSeriesFold "
        "(`cv.cv`)."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        assistant.backtest_code(
            data=df_multi_wide,
            target=["series_a", "series_b"],
            date_column="date",
            cv=cv_result,
        )

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "cv"


def test_backtest_code_output_when_cv_result_of_same_data_shorter():
    """
    Test that backtest_code() accepts a CVResult created for the same data
    with more observations (same structure).
    """
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    cv_result = assistant.create_cv(profile, assistant.plan(profile, steps=5))

    result = assistant.backtest_code(
        data=df_single.iloc[:80], target="sales", date_column="date", cv=cv_result
    )

    assert "TimeSeriesFold" in result.code


def test_backtest_code_InvalidInputError_when_plan_of_another_frequency():
    """
    Test that backtest_code() raises InvalidInputError with the field
    'plan' when the plan was built for monthly data and the data is daily.
    """
    h2o_profile = assistant.profile(data=df_h2o, target="x")
    h2o_plan = assistant.plan(h2o_profile, steps=5)
    cv = TimeSeriesFold(steps=5, initial_train_size=60, refit=False)

    err_msg = re.escape(
        "The plan was built for data of frequency 'MS', and the data has "
        "frequency 'D'. Build the plan from the profile of these data with "
        "`plan()`."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        assistant.backtest_code(
            data=df_single,
            target="sales",
            date_column="date",
            cv=cv,
            plan=h2o_plan,
        )

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "plan"


# =============================================================================
# Tests: data against a saved profile
# =============================================================================
def test_backtest_code_output_when_data_have_more_rows_than_profile():
    """
    Test that backtest_code() with data that extend the saved profile (192
    rows in the profile, 204 in the data) returns the new profile with the
    note.
    """
    cv = TimeSeriesFold(steps=3, initial_train_size=100, verbose=False)
    profile = assistant.profile(data=df_h2o.iloc[:192], target="x")

    result = assistant.backtest_code(data=df_h2o, cv=cv, profile=profile)

    assert isinstance(result, CodeGenerationResult)
    assert result.profile.data_profile.n_total_observations == 204
    assert result.profile.data_profile.warnings == [
        "The data differ in their values from the profile passed (changed: "
        "series_lengths, span_index_length, n_total_observations, "
        "target_stats): the profile was computed again from these data."
    ]


def test_backtest_code_profiles_the_same_data_once(monkeypatch):
    """
    Test that backtest_code() called again with the same data and saved
    profile reuses the data profile it computed, with the same result, and
    that data with another value are profiled again and get the new profile
    with the note.
    """
    from skforecast_ai import assistant as assistant_module

    calls = []
    create_data_profile = assistant_module.create_data_profile

    def counting(*args, **kwargs):
        calls.append(1)
        return create_data_profile(*args, **kwargs)

    monkeypatch.setattr(assistant_module, "create_data_profile", counting)
    fresh_assistant = ForecastingAssistant()
    cv = TimeSeriesFold(steps=3, initial_train_size=100, verbose=False)
    profile = fresh_assistant.profile(data=df_h2o, target="x")
    n_profile = len(calls)

    first = fresh_assistant.backtest_code(data=df_h2o, cv=cv, profile=profile)
    second = fresh_assistant.backtest_code(data=df_h2o.copy(), cv=cv, profile=profile)
    changed = df_h2o.copy()
    changed.iloc[10, 0] = 0.5
    third = fresh_assistant.backtest_code(data=changed, cv=cv, profile=profile)

    assert len(calls) - n_profile == 3
    assert second == first
    assert first.profile is profile
    assert third.profile.data_profile.warnings == [
        "The data differ in their values from the profile passed (changed: "
        "target_stats): the profile was computed again from these data."
    ]


def test_backtest_code_profiles_again_data_left_out_of_the_kept_profiles(
    monkeypatch,
):
    """
    Test that the data profiles kept by the assistant are the 8 used last
    (data used 9 calls ago are profiled again) and that data without a
    fingerprint (an object column with numbers and text) are profiled on
    every call, and that a saved profile still pickles and deep-copies the
    assistant.
    """
    import copy
    import pickle

    from skforecast_ai import assistant as assistant_module

    calls = []
    create_data_profile = assistant_module.create_data_profile

    def counting(*args, **kwargs):
        calls.append(1)
        return create_data_profile(*args, **kwargs)

    monkeypatch.setattr(assistant_module, "create_data_profile", counting)
    fresh_assistant = ForecastingAssistant()
    cv = TimeSeriesFold(steps=3, initial_train_size=100, verbose=False)
    profile = fresh_assistant.profile(data=df_h2o, target="x")
    frames = [df_h2o.iloc[i:] for i in range(10)]

    # Data that differ from the saved profile are profiled twice (the data
    # profile and `profile()`); the same data as the profile, once.
    for frame in frames:
        fresh_assistant.backtest_code(data=frame, cv=cv, profile=profile)
    calls.clear()
    fresh_assistant.backtest_code(data=frames[9], cv=cv, profile=profile)
    kept = len(calls)
    fresh_assistant.backtest_code(data=frames[0], cv=cv, profile=profile)
    evicted = len(calls) - kept

    mixed = df_h2o.assign(label=["a", 1] * 102)
    mixed_profile = fresh_assistant.profile(data=mixed, target="x")
    calls.clear()
    for _ in range(2):
        fresh_assistant.backtest_code(data=mixed, cv=cv, profile=mixed_profile)

    assert kept == 1
    assert evicted == 1
    assert len(calls) == 2
    restored = pickle.loads(pickle.dumps(fresh_assistant))
    assert isinstance(restored, ForecastingAssistant)
    assert isinstance(copy.deepcopy(fresh_assistant), ForecastingAssistant)


@pytest.mark.parametrize(
    "data, differences",
    [
        (df_h2o_daily, "(frequency: 'MS' != 'D')"),
    ],
    ids=["frequency"],
)
def test_backtest_code_InvalidInputError_when_data_have_other_structure_than_profile(
    data, differences
):
    """
    Test that backtest_code() raises InvalidInputError with the field
    'profile' when the data have another frequency
    than the saved profile.
    """
    cv = TimeSeriesFold(steps=3, initial_train_size=50, verbose=False)
    profile = assistant.profile(data=df_h2o, target="x")

    err_msg = re.escape(
        f"The data do not have the structure of the profile passed {differences}: "
        f"profile these data and build the plan from that profile."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        assistant.backtest_code(data=data, cv=cv, profile=profile)

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "profile"


def test_backtest_code_output_when_lags_window_features_and_metric_given():
    """
    Test that backtest_code() builds its plan with `lags`,
    `window_features` and `metric`, written into the script.
    """
    cv = TimeSeriesFold(steps=5, initial_train_size=60)

    result = assistant.backtest_code(
        data            = df_single,
        target          = "sales",
        date_column     = "date",
        cv              = cv,
        lags            = 3,
        window_features = [{"stats": ["mean"], "window_size": 3}],
        metric          = ["mean_squared_error", "mean_absolute_error"],
    )

    assert result.plan.overridden_fields == ["lags", "window_features", "metric"]
    assert re.search(r"\n    lags +=", result.code)
    assert result.plan.forecaster_kwargs["lags"] == 3
    assert (
        "    metric            = ['mean_squared_error', 'mean_absolute_error'],\n"
    ) in result.code


def test_backtest_code_output_when_use_exog_false():
    """
    Test that backtest_code() builds its plan with `use_exog=False`, whose
    script passes no exogenous variables, and rejects it against a plan
    that uses them.
    """
    cv = TimeSeriesFold(steps=5, initial_train_size=60)
    inputs = {"data": df_single, "target": "sales", "date_column": "date", "cv": cv}

    result = assistant.backtest_code(**inputs, use_exog=False)

    assert result.plan.use_exog is False
    assert "exog" not in result.code.split("# Run backtesting")[1]
    with pytest.raises(InvalidInputError, match=re.escape("['use_exog']")):
        assistant.backtest_code(
            **inputs, plan=assistant.plan(result.profile, steps=5), use_exog=False
        )


def test_backtest_code_InvalidInputError_when_direct_forecaster_with_gap():
    """
    Test that backtest_code() rejects, as backtest() does, a ForecasterDirect
    plan with a cv whose gap is greater than 0, with `cv` as field: the
    script would fail, since each fold asks the forecaster for steps + gap
    steps.
    """
    profile = assistant.profile(data=df_no_exog, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5, forecaster="ForecasterDirect")
    cv = TimeSeriesFold(steps=5, initial_train_size=70, gap=2, verbose=False)

    err_msg = re.escape(
        "ForecasterDirect is trained to predict 5 steps, and with `gap=2` "
        "each fold needs steps + gap = 7 steps ahead, so skforecast would "
        "fail. Use a strategy without gap, or a recursive forecaster."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        assistant.backtest_code(
            data    = df_no_exog,
            cv      = cv,
            profile = profile,
            plan    = plan,
        )

    assert exc_info.value.field == "cv"


@pytest.mark.parametrize(
    "forecaster, gap, expected_import, expected_gap",
    [
        (
            "ForecasterRecursive", 2,
            "from skforecast.recursive import ForecasterRecursive",
            "    gap                = 2,\n",
        ),
        (
            "ForecasterDirect", 0,
            "from skforecast.direct import ForecasterDirect",
            None,
        ),
    ],
    ids=["recursive_with_gap", "direct_without_gap"],
)
def test_backtest_code_output_when_gap_can_run(
    forecaster, gap, expected_import, expected_gap
):
    """
    Test that backtest_code() returns the script of a recursive forecaster
    with a gap, which the strategy of the script carries, and of a direct
    forecaster without one.
    """
    profile = assistant.profile(data=df_no_exog, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5, forecaster=forecaster)
    cv = TimeSeriesFold(steps=5, initial_train_size=70, gap=gap, verbose=False)

    result = assistant.backtest_code(
        data    = df_no_exog,
        cv      = cv,
        profile = profile,
        plan    = plan,
    )

    assert expected_import in result.code
    if expected_gap is None:
        assert "gap " not in result.code
    else:
        assert expected_gap in result.code


def test_backtest_code_InvalidInputError_when_first_window_shorter_than_forecaster():
    """
    Test that backtest_code() rejects a strategy whose first training window
    is not longer than the window of the forecaster, as backtest() does: the
    script would fail inside skforecast.
    """
    profile = assistant.profile(data=df_no_exog, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5, lags=30)
    cv = TimeSeriesFold(steps=5, initial_train_size=30, verbose=False)

    err_msg = re.escape(
        "The first training window of the strategy has 30 observations, and "
        "ForecasterRecursive needs at least 31 (more than its window size, "
        "30), so skforecast would fail. Use a later `initial_train_size`, or "
        "a shorter horizon (`steps`), fewer lags or smaller window features."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        assistant.backtest_code(
            data    = df_no_exog,
            cv      = cv,
            profile = profile,
            plan    = plan,
        )

    assert exc_info.value.code == "insufficient_data"
    assert exc_info.value.field == "cv"


def test_backtest_code_output_when_strategy_cannot_be_split():
    """
    Test that backtest_code() returns the script of a strategy that
    skforecast cannot split (an `initial_train_size` as long as the data),
    without the check of the first training window failing first.
    """
    profile = assistant.profile(data=df_no_exog, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    cv = TimeSeriesFold(steps=5, initial_train_size=100, verbose=False)

    result = assistant.backtest_code(
        data    = df_no_exog,
        cv      = cv,
        profile = profile,
        plan    = plan,
    )

    assert "initial_train_size = 100," in result.code
