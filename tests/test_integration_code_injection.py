# Integration test: values from a plan, a profile or the data never run as code
# Each payload creates the file `MARKER` in the working directory of the test
# (`tmp_path`) if the generated script executes it. The same payloads did so
# before the render boundary: every value now reaches the script through
# `repr()`, a closed map or an escaped comment, or rendering raises.

import copy
import json
import re

import pandas as pd
import pytest
from pydantic import ValidationError
from skforecast.model_selection import TimeSeriesFold
from typer.testing import CliRunner

from skforecast_ai import ForecastingAssistant
from skforecast_ai.cli import app
from skforecast_ai.exceptions import ForecastExecutionError
from skforecast_ai.execution.backtesting_runner import run_backtest
from skforecast_ai.execution.forecast_runner import run_forecast
from skforecast_ai.schemas import DataProfile, ForecastPlan, PreprocessingStep

from tests.fixtures_assistant import (
    df_categorical_exog,
    df_multi_long,
    df_multi_wide,
    df_no_exog,
)
from tests.tests_execution.fixtures_execution import (
    cv_explanation_single,
    cv_single,
    df_multi,
    df_single,
    plan_baseline,
    plan_multi,
    plan_single,
    plan_single_with_intervals,
    profile_multi,
    profile_single,
)

MARKER = "pwned"
PAYLOAD = f"open({MARKER!r}, 'w').close()"

runner = CliRunner()


def _hostile(plan: ForecastPlan, **fields) -> ForecastPlan:
    """
    Copy `plan` with `fields` replaced, skipping validation, as a plan
    edited with `model_construct` or by assignment would.
    """
    return ForecastPlan.model_construct(**{**dict(plan), **fields})


def _hostile_kwargs(plan: ForecastPlan, **kwargs) -> ForecastPlan:
    """
    Copy `plan` with `kwargs` merged into `forecaster_kwargs`, skipping
    validation.
    """
    return _hostile(plan, forecaster_kwargs={**plan.forecaster_kwargs, **kwargs})


# Plans of the templates without an execution fixture, built from the
# fixtures of the other templates.
plan_statistical = _hostile(
    plan_single,
    task_type         = "statistical",
    forecaster        = "ForecasterStats",
    forecaster_kwargs = {},
    estimator         = None,
)
plan_foundation = _hostile(
    plan_single,
    task_type         = "foundation",
    forecaster        = "ForecasterFoundation",
    forecaster_kwargs = {},
    estimator         = "autogluon/chronos-2-small",
)
plan_multivariate = _hostile(
    plan_multi,
    task_type         = "multivariate",
    forecaster        = "ForecasterDirectMultiVariate",
    forecaster_kwargs = {"lags": 7},
)
# Multivariate data in wide format, the layout whose script reaches the
# prediction (in long format it fails when fitting, before predicting).
profile_multivariate_wide = DataProfile(
    data_format    = "wide",
    n_series       = 2,
    series_lengths = {"series_a": 100, "series_b": 100},
    target         = ["series_a", "series_b"],
    date_column    = "date",
    index_type     = "datetime",
    frequency      = "D",
)
plan_multivariate_wide = _hostile(plan_multivariate, end_train="2023-04-05")
_with_interval = {"interval": [0.1, 0.9]}


# =============================================================================
# Plan values outside a closed set: rendering raises
# =============================================================================
@pytest.mark.parametrize(
    "data, profile, plan, err_msg",
    [
        (
            df_single,
            profile_single,
            _hostile(plan_single, preprocessing_steps=[
                PreprocessingStep(
                    action       = "drop_duplicates",
                    reason       = "Injected.",
                    code_snippet = PAYLOAD,
                    blocking     = True,
                )
            ]),
            "The blocking preprocessing step 'drop_duplicates' is not one of "
            "the steps the scripts can contain",
        ),
        (
            df_single,
            profile_single,
            _hostile(
                plan_single,
                forecaster=f"ForecasterRecursive\n{PAYLOAD}\nForecasterRecursive",
            ),
            "cannot be rendered by this script template",
        ),
        (
            df_single,
            profile_single,
            _hostile_kwargs(plan_single, transformer_y=f"({PAYLOAD} or StandardScaler)"),
            "is not a supported transformer",
        ),
        (
            df_multi,
            profile_multi,
            _hostile_kwargs(
                plan_multi, transformer_series=f"({PAYLOAD} or StandardScaler)"
            ),
            "is not a supported transformer",
        ),
        (
            df_single,
            profile_single,
            _hostile(
                plan_single,
                estimator_kwargs={f"alpha=({PAYLOAD}) or 1.0, fit_intercept": True},
            ),
            "`estimator_kwargs` keys must be valid Python parameter names",
        ),
        (
            df_single,
            profile_single,
            _hostile(
                plan_statistical,
                estimator_kwargs={f"d=({PAYLOAD}) or 1, max_p": 3},
            ),
            "`estimator_kwargs` keys must be valid Python parameter names",
        ),
        (
            df_single,
            profile_single,
            _hostile(
                plan_foundation,
                estimator_kwargs={f"device=({PAYLOAD}) or 'cpu', x": 1},
            ),
            "`estimator_kwargs` keys must be valid Python parameter names",
        ),
        (
            df_single,
            profile_single,
            _hostile(
                plan_single_with_intervals,
                interval_method=f"bootstrapping' if {PAYLOAD} is None else '",
            ),
            "cannot be rendered. Supported methods",
        ),
        (
            df_multi,
            profile_multi,
            _hostile(
                plan_multi,
                **_with_interval,
                interval_method=f"bootstrapping' if {PAYLOAD} is None else '",
            ),
            "cannot be rendered. Supported methods",
        ),
        (
            df_multi_wide,
            profile_multivariate_wide,
            _hostile(
                plan_multivariate_wide,
                **_with_interval,
                interval_method=f"bootstrapping' if {PAYLOAD} is None else '",
            ),
            "cannot be rendered. Supported methods",
        ),
        (
            df_single,
            profile_single,
            _hostile(
                plan_baseline,
                interval_method=f"conformal' if {PAYLOAD} is None else '",
            ),
            "cannot be rendered. Supported methods",
        ),
        (
            df_single,
            profile_single,
            _hostile(plan_single, steps=f"10 if {PAYLOAD} is None else 10"),
            "`steps` must be an integer, got",
        ),
        (
            df_multi,
            profile_multi,
            _hostile(plan_multi, steps=f"5 if {PAYLOAD} is None else 5"),
            "`steps` must be an integer, got",
        ),
        (
            df_multi_wide,
            profile_multivariate_wide,
            _hostile(plan_multivariate_wide, steps=f"5 if {PAYLOAD} is None else 5"),
            "`steps` must be an integer, got",
        ),
        (
            df_single,
            profile_single,
            _hostile(plan_baseline, steps=f"5 if {PAYLOAD} is None else 5"),
            "`steps` must be an integer, got",
        ),
        (
            df_single,
            profile_single,
            _hostile(plan_statistical, steps=f"5 if {PAYLOAD} is None else 5"),
            "`steps` must be an integer, got",
        ),
        (
            df_single,
            profile_single,
            _hostile(plan_foundation, steps=f"5 if {PAYLOAD} is None else 5"),
            "`steps` must be an integer, got",
        ),
        (
            df_single,
            profile_single,
            _hostile(plan_single, steps=2.9),
            "`steps` must be an integer, got 2.9.",
        ),
    ],
    ids=[
        "preprocessing code_snippet",
        "forecaster",
        "transformer_y",
        "transformer_series",
        "estimator_kwargs key, single series",
        "estimator_kwargs key, statistical",
        "estimator_kwargs key, foundation",
        "interval_method, single series",
        "interval_method, multi-series",
        "interval_method, multivariate",
        "interval_method, baseline",
        "steps, single series",
        "steps, multi-series",
        "steps, multivariate",
        "steps, baseline",
        "steps, statistical",
        "steps, foundation",
        "steps, not an integer",
    ],
)
def test_run_forecast_ValueError_when_plan_value_outside_closed_set(
    monkeypatch, tmp_path, data, profile, plan, err_msg
):
    """
    Test that a plan value written into the script from a closed set (the
    preprocessing templates, the forecaster imports, the transformer
    constructors, the interval methods, Python parameter names, an integer
    horizon) raises a ValueError when rendering, in every script template,
    instead of writing the payload, which is never run.
    """
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match=re.escape(err_msg)):
        run_forecast(data=data, profile=profile, plan=plan)
    assert not (tmp_path / MARKER).exists()


# =============================================================================
# Plan and profile values written with repr(): skforecast rejects them
# =============================================================================
_hostile_frequency = "D') if open('pwned', 'w').close() is None else data.asfreq('D"


@pytest.mark.parametrize(
    "data, profile, plan, error_type, expected_line",
    [
        (
            df_single,
            profile_single,
            _hostile_kwargs(
                plan_single,
                categorical_features=f"auto' if {PAYLOAD} is None else '",
            ),
            ValueError,
            "    categorical_features = "
            "\"auto' if open('pwned', 'w').close() is None else '\",",
        ),
        (
            df_multi,
            profile_multi,
            _hostile_kwargs(plan_multi, encoding=f"ordinal' if {PAYLOAD} is None else '"),
            ValueError,
            "    encoding           = "
            "\"ordinal' if open('pwned', 'w').close() is None else '\",",
        ),
        (
            df_single,
            profile_single,
            _hostile_kwargs(plan_single, differentiation=f"{PAYLOAD} or 1"),
            ValueError,
            "    differentiation    = \"open('pwned', 'w').close() or 1\",",
        ),
        (
            df_single,
            profile_single,
            _hostile_kwargs(
                plan_single,
                calendar_features={
                    "features": f"[{PAYLOAD}] and ['month']",
                    "encoding": None,
                },
            ),
            ValueError,
            "    features = \"[open('pwned', 'w').close()] and ['month']\",",
        ),
        (
            df_single,
            profile_single,
            _hostile_kwargs(plan_single, lags=f"({PAYLOAD}) or 7"),
            TypeError,
            "    lags               = \"(open('pwned', 'w').close()) or 7\",",
        ),
        (
            df_single,
            profile_single,
            _hostile_kwargs(plan_baseline, offset=f"{PAYLOAD} or 7"),
            TypeError,
            "    offset    = \"open('pwned', 'w').close() or 7\",",
        ),
        (
            df_single,
            profile_single,
            _hostile_kwargs(plan_baseline, n_offsets=f"{PAYLOAD} or 1"),
            TypeError,
            "    n_offsets = \"open('pwned', 'w').close() or 1\",",
        ),
        (
            df_single,
            DataProfile.model_construct(
                **{**dict(profile_single), "frequency": _hostile_frequency}
            ),
            plan_single,
            ValueError,
            "data = data.asfreq(\"D') if open('pwned', 'w').close() is None "
            "else data.asfreq('D\")",
        ),
        (
            df_single,
            DataProfile.model_construct(**{
                **dict(profile_single),
                "frequency": _hostile_frequency,
                "has_duplicate_timestamps": True,
            }),
            _hostile(plan_single, preprocessing_steps=[
                PreprocessingStep(
                    action       = "drop_duplicates",
                    reason       = "Timestamps repeated in identical rows.",
                    code_snippet = "data = data[~data.index.duplicated(keep='first')]",
                    blocking     = True,
                )
            ]),
            ValueError,
            "data = data.asfreq(\"D') if open('pwned', 'w').close() is None "
            "else data.asfreq('D\")",
        ),
        (
            df_multi,
            DataProfile.model_construct(
                **{**dict(profile_multi), "frequency": _hostile_frequency}
            ),
            plan_multivariate,
            ValueError,
            "series = series.asfreq(\"D') if open('pwned', 'w').close() is None "
            "else data.asfreq('D\")",
        ),
    ],
    ids=[
        "categorical_features",
        "encoding",
        "differentiation",
        "calendar features",
        "lags",
        "offset",
        "n_offsets",
        "profile frequency, index setup",
        "profile frequency, after deduplication",
        "profile frequency, pivot to wide",
    ],
)
def test_run_forecast_ForecastExecutionError_when_plan_value_written_with_repr(
    monkeypatch, tmp_path, data, profile, plan, error_type, expected_line
):
    """
    Test that a plan or profile value outside the closed sets is written as
    a string literal (`repr()`), so the payload in it is never run and the
    script fails when skforecast or pandas reject the value.
    """
    monkeypatch.chdir(tmp_path)

    with pytest.raises(
        ForecastExecutionError, match="Error executing generated forecasting code"
    ) as exc_info:
        run_forecast(data=data, profile=profile, plan=plan)
    assert isinstance(exc_info.value.original_error, error_type)
    assert expected_line in exc_info.value.generated_code.splitlines()
    assert not (tmp_path / MARKER).exists()


def test_run_forecast_output_when_dropna_from_series_is_a_string(
    monkeypatch, tmp_path
):
    """
    Test that a string `dropna_from_series` is written as a string literal:
    the forecast runs without running the payload. Rejecting the value is
    the job of the plan validator.
    """
    monkeypatch.chdir(tmp_path)
    plan = _hostile_kwargs(plan_single, dropna_from_series=f"{PAYLOAD} or False")

    result = run_forecast(data=df_single, profile=profile_single, plan=plan)

    expected_line = (
        "    dropna_from_series = \"open('pwned', 'w').close() or False\","
    )
    assert expected_line in result["rendered_code"].core.splitlines()
    assert not (tmp_path / MARKER).exists()


# =============================================================================
# Backtesting scripts
# =============================================================================
@pytest.mark.parametrize(
    "plan, err_msg",
    [
        (
            _hostile(
                plan_baseline,
                steps=10,
                interval_method=f"conformal' if {PAYLOAD} is None else '",
            ),
            "cannot be rendered. Supported methods",
        ),
        (
            _hostile(plan_single, preprocessing_steps=[
                PreprocessingStep(
                    action       = "encode_target",
                    reason       = "Injected.",
                    code_snippet = PAYLOAD,
                    blocking     = True,
                )
            ]),
            "The blocking preprocessing step 'encode_target' is not one of "
            "the steps the scripts can contain",
        ),
    ],
    ids=["interval_method", "preprocessing code_snippet"],
)
def test_run_backtest_ValueError_when_plan_value_outside_closed_set(
    monkeypatch, tmp_path, plan, err_msg
):
    """
    Test that the backtesting script raises a ValueError when rendering a
    plan value outside its closed set (the interval method of the
    backtesting call, a blocking preprocessing snippet), and never runs
    the payload.
    """
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match=re.escape(err_msg)):
        run_backtest(
            data           = df_single,
            profile        = profile_single,
            plan           = plan,
            cv             = cv_single,
            cv_explanation = cv_explanation_single,
            show_progress  = False,
        )
    assert not (tmp_path / MARKER).exists()


@pytest.mark.parametrize(
    "attribute, value, err_msg",
    [
        ("gap", f"1 if {PAYLOAD} is None else 1", "`gap` must be an integer"),
        ("fold_stride", f"5 if {PAYLOAD} is None else 5", "`fold_stride` must be an integer"),
        ("skip_folds", f"[1] if {PAYLOAD} is None else [1]", "`skip_folds` must be an integer"),
        ("differentiation", f"1 if {PAYLOAD} is None else 1", "`differentiation` must be an integer"),
        ("refit", f"True if {PAYLOAD} is None else True", "`refit` must be an integer"),
    ],
    ids=["gap", "fold_stride", "skip_folds", "differentiation", "refit"],
)
def test_run_backtest_ValueError_when_cv_attribute_assigned_after_creation(
    monkeypatch, tmp_path, attribute, value, err_msg
):
    """
    Test that a TimeSeriesFold attribute assigned after the fold was created
    (which skips the checks of its constructor) is checked again when the
    cross-validation is written into the script, and never run.
    """
    monkeypatch.chdir(tmp_path)
    cv = copy.deepcopy(cv_single)
    setattr(cv, attribute, value)

    with pytest.raises(ValueError, match=re.escape(err_msg)):
        run_backtest(
            data           = df_single,
            profile        = profile_single,
            plan           = plan_single,
            cv             = cv,
            cv_explanation = cv_explanation_single,
            show_progress  = False,
        )
    assert not (tmp_path / MARKER).exists()


# =============================================================================
# Column names taken from a CSV
# =============================================================================
def test_forecast_output_when_long_format_column_names_carry_a_payload(
    monkeypatch, tmp_path
):
    """
    Test that long-format data with repeated identical rows, whose series
    identifier column name closes a quote and carries a payload, is
    deduplicated with the column name written as a string literal: the
    forecast runs and the payload does not.
    """
    monkeypatch.chdir(tmp_path)
    series_id = f"sid', 'date'] if {PAYLOAD} is None else ['sid"
    data = pd.concat(
        [df_multi_long, df_multi_long.iloc[[-10]]], ignore_index=True
    ).rename(columns={"series_id": series_id})
    data.to_csv(tmp_path / "data.csv", index=False)

    result = ForecastingAssistant().forecast(
        data             = tmp_path / "data.csv",
        target           = "value",
        date_column      = "date",
        series_id_column = series_id,
        steps            = 5,
        test_size        = 5,
        estimator        = "Ridge",
    )

    expected_line = (
        "data = data.drop_duplicates(subset=[\"sid', 'date'] if "
        "open('pwned', 'w').close() is None else ['sid\", 'date'], keep='first')"
    )
    assert expected_line in result.code.splitlines()
    assert result.predictions.shape[0] == 10
    assert not (tmp_path / MARKER).exists()


def test_forecast_output_when_categorical_exog_name_holds_newlines_statistical(
    monkeypatch, tmp_path
):
    """
    Test that a categorical exogenous column whose name holds newlines and
    a payload (a CSV accepts it between quotes) is written escaped in the
    comment of the ForecasterStats script: the comment stays on one line,
    the forecast runs and the payload does not.
    """
    monkeypatch.chdir(tmp_path)
    column = f"weekday\n{PAYLOAD}\n#"
    df_categorical_exog.rename(columns={"weekday": column}).to_csv(
        tmp_path / "data.csv", index=False
    )

    result = ForecastingAssistant().forecast(
        data             = tmp_path / "data.csv",
        target           = "sales",
        date_column      = "date",
        steps            = 5,
        test_size        = 5,
        forecaster       = "ForecasterStats",
        estimator_kwargs = {"order": [1, 0, 0], "seasonal_order": [0, 0, 0]},
    )

    expected_comment = (
        "# Categorical exog excluded (weekday\\nopen('pwned', 'w').close()\\n#): "
        "statistical models only accept numeric exogenous variables"
    )
    assert expected_comment in result.code.splitlines()
    assert result.predictions.shape[0] == 5
    assert not (tmp_path / MARKER).exists()


class _FoundationModelStub:
    """
    Stand-in for `skforecast.foundation.FoundationModel` that fails on
    creation, so a foundation script runs up to the model without any
    backend or weights.
    """

    def __init__(self, **kwargs):
        raise RuntimeError("Foundation model not loaded in this test.")


def test_forecast_ForecastExecutionError_when_foundation_categorical_exog_name_holds_newlines(
    monkeypatch, tmp_path
):
    """
    Test that a categorical exogenous column name (from a CSV) holding
    newlines and a payload is written escaped in the comment of the
    ForecasterFoundation script, which runs up to the model creation
    without running the payload.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("skforecast.foundation.FoundationModel", _FoundationModelStub)
    # The script runs up to the model creation, stubbed: its backend is
    # taken as installed.
    monkeypatch.setattr(
        "skforecast_ai._foundation.foundation_backend_installed", lambda info: True
    )
    column = f"weekday\n{PAYLOAD}\n#"
    df_categorical_exog.rename(columns={"weekday": column}).to_csv(
        tmp_path / "data.csv", index=False
    )

    err_msg = re.escape("Foundation model not loaded in this test.")
    with pytest.raises(ForecastExecutionError, match=err_msg) as exc_info:
        ForecastingAssistant().forecast(
            data        = tmp_path / "data.csv",
            target      = "sales",
            date_column = "date",
            steps       = 5,
            test_size   = 5,
            forecaster  = "ForecasterFoundation",
            estimator   = "soda-inria/tabicl",
        )
    expected_comment = (
        "# Categorical exog excluded (weekday\\nopen('pwned', 'w').close()\\n#): "
        "'soda-inria/tabicl' only accepts numeric covariates"
    )
    assert isinstance(exc_info.value.original_error, RuntimeError)
    assert expected_comment in exc_info.value.generated_code.splitlines()
    assert not (tmp_path / MARKER).exists()


def test_forecast_ValueError_when_foundation_model_id_carries_a_payload(
    monkeypatch, tmp_path
):
    """
    Test that a foundation model ID made of a supported prefix followed by
    newlines and a payload (an `estimator` override) raises ValueError when
    the plan is built, before any script is rendered or run.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("skforecast.foundation.FoundationModel", _FoundationModelStub)
    estimator = f"autogluon/chronos-2-small\n{PAYLOAD}\n#"

    err_msg = re.escape(f"{estimator!r} is not a valid Hugging Face model ID.")
    with pytest.raises(ValueError, match=err_msg):
        ForecastingAssistant().forecast(
            data        = df_no_exog,
            target      = "sales",
            date_column = "date",
            steps       = 5,
            test_size   = 5,
            forecaster  = "ForecasterFoundation",
            estimator   = estimator,
        )
    assert not (tmp_path / MARKER).exists()


def test_run_forecast_ValueError_when_foundation_model_id_skipped_validation(
    monkeypatch, tmp_path
):
    """
    Test that a foundation plan built without validation, whose model ID is
    a supported prefix followed by newlines and a payload, raises ValueError
    when the script is rendered, which checks the ID again.
    """
    monkeypatch.chdir(tmp_path)
    estimator = f"autogluon/chronos-2-small\n{PAYLOAD}\n#"
    plan = _hostile(plan_foundation, estimator=estimator)

    err_msg = re.escape(f"{estimator!r} is not a valid Hugging Face model ID.")
    with pytest.raises(ValueError, match=err_msg):
        run_forecast(data=df_single, profile=profile_single, plan=plan)
    assert not (tmp_path / MARKER).exists()


# =============================================================================
# Plans received by the public methods
# =============================================================================
@pytest.mark.parametrize(
    "update, err_msg",
    [
        (
            {"preprocessing_steps": [
                PreprocessingStep(
                    action       = "drop_duplicates",
                    reason       = "Injected.",
                    code_snippet = PAYLOAD,
                    blocking     = True,
                )
            ]},
            "The blocking preprocessing step 'drop_duplicates' is not one of "
            "the steps the scripts can contain",
        ),
        (
            {"forecaster": f"ForecasterRecursive\n{PAYLOAD}\nForecasterRecursive"},
            "is not a supported forecaster",
        ),
        (
            {"forecaster_kwargs": {"lags": 7, "dropna_from_series": f"{PAYLOAD} or False"}},
            "`forecaster_kwargs['dropna_from_series']` must be a bool",
        ),
        (
            {"forecaster_kwargs": {"lags": 7, "categorical_features": f"auto' if {PAYLOAD} is None else '"}},
            "`forecaster_kwargs['categorical_features']` must be 'auto' or None",
        ),
        (
            {"estimator_kwargs": {f"alpha=({PAYLOAD}) or 1.0, fit_intercept": True}},
            "`estimator_kwargs` keys must be valid Python parameter names",
        ),
        (
            {"steps": f"5 if {PAYLOAD} is None else 5"},
            "`steps` must be an integer greater than or equal to 1",
        ),
    ],
    ids=[
        "preprocessing snippet",
        "forecaster",
        "dropna_from_series",
        "categorical_features",
        "estimator_kwargs key",
        "steps",
    ],
)
@pytest.mark.parametrize(
    "method",
    ["forecast", "forecast_code", "backtest", "backtest_code"],
    ids=lambda method: f"{method}()",
)
def test_methods_ValidationError_when_received_plan_skipped_validation(
    monkeypatch, tmp_path, method, update, err_msg
):
    """
    Test that a plan edited with `model_copy(update=...)`, which skips the
    validators, is validated again by `forecast()`, `forecast_code()`,
    `backtest()` and `backtest_code()` before rendering. Each case raises
    ValidationError and nothing runs, including a `dropna_from_series`
    string, which the rendering alone would write as a literal and run.
    """
    monkeypatch.chdir(tmp_path)
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_no_exog, target="sales", date_column="date")
    plan = assistant.plan(profile=profile, steps=5, estimator="Ridge").model_copy(
        update=update
    )
    cv = TimeSeriesFold(steps=5, initial_train_size=70, verbose=False)
    calls = {
        "forecast": lambda: assistant.forecast(
            data=df_no_exog, profile=profile, plan=plan, test_size=5
        ),
        "forecast_code": lambda: assistant.forecast_code(
            profile=profile, plan=plan, test_size=5
        ),
        "backtest": lambda: assistant.backtest(
            data=df_no_exog, cv=cv, profile=profile, plan=plan, show_progress=False
        ),
        "backtest_code": lambda: assistant.backtest_code(
            data=None, cv=cv, profile=profile, plan=plan
        ),
    }

    with pytest.raises(ValidationError, match=re.escape(err_msg)):
        calls[method]()
    assert not (tmp_path / MARKER).exists()


# =============================================================================
# CLI with a saved plan
# =============================================================================
@pytest.mark.parametrize(
    "tamper",
    [
        {
            "preprocessing_steps": [
                {
                    "action": "drop_duplicates",
                    "reason": "Injected.",
                    "code_snippet": PAYLOAD,
                    "blocking": True,
                }
            ]
        },
        {"forecaster_kwargs": {"lags": 7, "dropna_from_series": f"{PAYLOAD} or False"}},
        {"forecaster": f"ForecasterRecursive\n{PAYLOAD}\nForecasterRecursive"},
    ],
    ids=["preprocessing snippet", "forecaster_kwargs value", "forecaster"],
)
@pytest.mark.parametrize(
    "command",
    [
        ["forecast", "data.csv", "--from-plan", "plan.json", "--test-size", "5"],
        ["backtest", "data.csv", "--from-plan", "plan.json"],
        ["forecast-code", "--from-plan", "plan.json"],
        ["backtest-code", "--from-plan", "plan.json"],
    ],
    ids=["forecast", "backtest", "forecast-code", "backtest-code"],
)
def test_cli_exits_with_error_when_plan_bundle_is_tampered(
    monkeypatch, tmp_path, command, tamper
):
    """
    Test that a plan bundle edited to carry code (a blocking preprocessing
    step, a forecaster argument, the forecaster name) is rejected when it
    is loaded: the command exits with code 1 and "Invalid input data",
    without running the code (`forecast`, `backtest`) or printing a script
    (`forecast-code`, `backtest-code`).
    """
    monkeypatch.chdir(tmp_path)
    df_no_exog.to_csv(tmp_path / "data.csv", index=False)
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=tmp_path / "data.csv", target="sales", date_column="date"
    )
    plan = assistant.plan(profile=profile, steps=5, estimator="Ridge")
    bundle = {
        "profile": profile.model_dump(mode="json"),
        "plan": {**plan.model_dump(mode="json"), **tamper},
    }
    (tmp_path / "plan.json").write_text(json.dumps(bundle))

    result = runner.invoke(app, command)

    assert result.exit_code == 1
    assert "Invalid input data" in result.output
    assert "import pandas as pd" not in result.output
    assert not (tmp_path / MARKER).exists()


@pytest.mark.parametrize(
    "command",
    [
        ["forecast", "data.csv", "--from-plan", "plan.json", "--test-size", "5"],
        ["backtest", "data.csv", "--from-plan", "plan.json"],
        ["compare", "data.csv", "--from-profile", "profile.json", "--steps", "5"],
    ],
    ids=["forecast", "backtest", "compare"],
)
def test_cli_exits_with_error_when_saved_profile_frequency_carries_a_payload(
    monkeypatch, tmp_path, command
):
    """
    Test that a saved profile (in a plan bundle or on its own) whose
    frequency was edited to carry a payload is rejected when it is loaded:
    the command exits with code 1 and "Invalid input data", and runs
    nothing.
    """
    monkeypatch.chdir(tmp_path)
    df_no_exog.to_csv(tmp_path / "data.csv", index=False)
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=tmp_path / "data.csv", target="sales", date_column="date"
    )
    plan = assistant.plan(profile=profile, steps=5, estimator="Ridge")
    profile_json = profile.model_dump(mode="json")
    profile_json["data_profile"]["frequency"] = (
        f"D') if {PAYLOAD} is None else data.asfreq('D"
    )
    (tmp_path / "plan.json").write_text(
        json.dumps({"profile": profile_json, "plan": plan.model_dump(mode="json")})
    )
    (tmp_path / "profile.json").write_text(json.dumps(profile_json))

    result = runner.invoke(app, command)

    assert result.exit_code == 1
    assert "Invalid input data" in result.output
    assert not (tmp_path / MARKER).exists()
