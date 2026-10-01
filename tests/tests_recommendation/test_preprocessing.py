# Unit test derive_preprocessing_steps recommendation/preprocessing

import re

import pytest
from skforecast.foundation import get_model_info

from skforecast_ai.recommendation import derive_preprocessing_steps
from skforecast_ai.schemas import DataProfile, PreprocessingStep


def test_derive_steps_returns_empty_when_no_issues():
    profile = DataProfile(
        series_lengths={"y": 365},
        n_series=1,
        index_type="datetime",
        frequency="D",
        target="y",
        data_format="single",
        frequency_is_set=True,
        index_is_monotonic=True,
        has_duplicate_timestamps=False,
        has_gaps=False,
        target_dtype="numeric",
    )
    steps = derive_preprocessing_steps(profile, "ForecasterRecursive")
    assert steps == []


def test_derive_steps_no_sort_index_step():
    """sort_index is now handled by the template, not preprocessing steps."""
    profile = DataProfile(
        series_lengths={"y": 100},
        n_series=1,
        index_type="datetime",
        frequency="D",
        target="y",
        index_is_monotonic=False,
        frequency_is_set=True,
    )
    steps = derive_preprocessing_steps(profile, "ForecasterRecursive")
    actions = [s.action for s in steps]
    assert "sort_index" not in actions


@pytest.mark.parametrize(
    "profile_kwargs, forecaster, expected_snippet",
    [
        (
            {"series_lengths": {"y": 100}, "n_series": 1, "target": "y"},
            "ForecasterRecursive",
            "data = data[~data.index.duplicated(keep='first')]",
        ),
        (
            {
                "series_lengths": {"A": 100, "B": 100},
                "n_series": 2,
                "target": "value",
                "data_format": "long",
                "date_column": "date",
                "series_id_column": "series_id",
            },
            "ForecasterRecursiveMultiSeries",
            "data = data.drop_duplicates(subset=[{series_id_column}, "
            "{date_column}], keep='first')",
        ),
    ],
    ids=["single, dates in the index", "long, dates in a column"],
)
def test_derive_steps_drop_duplicates_snippet_per_data_format(
    profile_kwargs, forecaster, expected_snippet
):
    """
    Test that timestamps repeated in identical rows add a blocking
    drop_duplicates step that deduplicates on the index, or on the series
    identifier and date columns for long-format data, whose dates are still
    a column when the step runs.
    """
    profile = DataProfile(
        index_type               = "datetime",
        frequency                = "D",
        has_duplicate_timestamps = True,
        frequency_is_set         = True,
        **profile_kwargs,
    )

    steps = derive_preprocessing_steps(profile, forecaster)

    expected = PreprocessingStep(
        action       = "drop_duplicates",
        reason       = (
            "Timestamps repeated in identical rows are removed: skforecast "
            "needs one row per timestamp."
        ),
        code_snippet = expected_snippet,
        blocking     = True,
    )
    assert [step for step in steps if step.action == "drop_duplicates"] == [
        expected
    ]


def test_derive_steps_no_asfreq_step():
    """asfreq is now handled by the template, not preprocessing steps."""
    profile = DataProfile(
        series_lengths={"y": 100},
        n_series=1,
        index_type="datetime",
        frequency="D",
        target="y",
        frequency_is_set=False,
    )
    steps = derive_preprocessing_steps(profile, "ForecasterRecursive")
    actions = [s.action for s in steps]
    assert "asfreq" not in actions


def test_derive_steps_no_set_datetime_index_step():
    """set_datetime_index is now handled by the template."""
    profile = DataProfile(
        series_lengths={"y": 100},
        n_series=1,
        index_type="other",
        target="y",
        date_column="date",
    )
    steps = derive_preprocessing_steps(profile, "ForecasterRecursive")
    actions = [s.action for s in steps]
    assert "set_datetime_index" not in actions


def test_derive_steps_provides_datetime_index_when_no_date_column():
    """provide_datetime_index is kept for unresolvable case."""
    profile = DataProfile(
        series_lengths={"y": 100},
        n_series=1,
        index_type="other",
        target="y",
        date_column=None,
    )
    steps = derive_preprocessing_steps(profile, "ForecasterRecursive")
    actions = [s.action for s in steps]
    assert "provide_datetime_index" in actions


def test_derive_steps_no_reshape_for_multi_series_long():
    """reshape_long_to_dict is now handled by the template."""
    profile = DataProfile(
        series_lengths={"value": 300},
        n_series=3,
        index_type="datetime",
        frequency="D",
        target="value",
        date_column="date",
        series_id_column="series_id",
        data_format="long",
        frequency_is_set=True,
    )
    steps = derive_preprocessing_steps(
        profile, "ForecasterRecursiveMultiSeries"
    )
    actions = [s.action for s in steps]
    assert "reshape_long_to_dict" not in actions


def test_derive_steps_no_reshape_for_multi_series_wide():
    profile = DataProfile(
        series_lengths={"value": 300},
        n_series=3,
        index_type="datetime",
        frequency="D",
        target="value",
        data_format="wide",
        frequency_is_set=True,
    )
    steps = derive_preprocessing_steps(
        profile, "ForecasterRecursiveMultiSeries"
    )
    actions = [s.action for s in steps]
    assert "reshape_long_to_dict" not in actions


def test_derive_steps_includes_encode_target_when_non_numeric():
    profile = DataProfile(
        series_lengths={"y": 100},
        n_series=1,
        index_type="datetime",
        frequency="D",
        target="y",
        target_dtype="categorical",
        frequency_is_set=True,
    )
    steps = derive_preprocessing_steps(profile, "ForecasterRecursive")
    actions = [s.action for s in steps]
    assert "encode_target" in actions


def test_derive_steps_includes_handle_missing_values_when_missing_target():
    """handle_missing_values step is added when the target has NaNs."""
    profile = DataProfile(
        series_lengths={"y": 100},
        n_series=1,
        index_type="datetime",
        frequency="D",
        target="y",
        missing_target={"y": 3},
        frequency_is_set=True,
    )
    steps = derive_preprocessing_steps(profile, "ForecasterRecursive")
    actions = [s.action for s in steps]
    assert "handle_missing_values" in actions


def test_derive_steps_includes_handle_categorical_exog_when_categorical():
    """handle_categorical_exog step is added when categorical exog present."""
    profile = DataProfile(
        series_lengths={"y": 100},
        n_series=1,
        index_type="datetime",
        frequency="D",
        target="y",
        exog_columns=["holiday"],
        categorical_exog=["holiday"],
        frequency_is_set=True,
    )
    steps = derive_preprocessing_steps(profile, "ForecasterRecursive")
    actions = [s.action for s in steps]
    assert "handle_categorical_exog" in actions


@pytest.mark.parametrize(
    "forecaster, model_id, expected, not_expected",
    [
        (
            "ForecasterRecursive",
            None,
            "categorical_features='auto'",
            "consumes categorical covariates",
        ),
        (
            "ForecasterFoundation",
            "autogluon/chronos-2-small",
            "'autogluon/chronos-2-small' consumes categorical covariates natively",
            "categorical_features='auto'",
        ),
        (
            "ForecasterFoundation",
            "google/timesfm-3.0-pytorch",
            "'google/timesfm-3.0-pytorch' only accepts numeric covariates, "
            "so these columns are excluded",
            "consumes categorical covariates",
        ),
        (
            "ForecasterStats",
            None,
            "only accept numeric exogenous variables",
            "categorical_features='auto'",
        ),
    ],
    ids=lambda dt: f"forecaster, model_id, expected, not_expected: {dt}",
)
def test_derive_steps_handle_categorical_exog_reason_per_forecaster(
    forecaster, model_id, expected, not_expected
):
    """
    Test that the handle_categorical_exog reason matches the mechanism the
    forecaster actually offers. Only the ML forecasters take a
    `categorical_features` argument, and a foundation model either consumes
    categorical covariates natively or has them excluded.
    """
    profile = DataProfile(
        series_lengths={"y": 100},
        n_series=1,
        index_type="datetime",
        frequency="D",
        target="y",
        exog_columns=["holiday"],
        categorical_exog=["holiday"],
        frequency_is_set=True,
    )
    foundation_model = get_model_info(model_id) if model_id else None
    steps = derive_preprocessing_steps(
        profile          = profile,
        forecaster       = forecaster,
        foundation_model = foundation_model,
    )
    reason = next(
        s.reason for s in steps if s.action == "handle_categorical_exog"
    )

    assert expected in reason
    assert not_expected not in reason


def test_derive_steps_no_handle_categorical_exog_when_foundation_model_without_covariates():
    """
    Test that no handle_categorical_exog step is added for a foundation
    model that accepts no covariates: no exogenous variable reaches it, so
    there is nothing to encode or exclude.
    """
    profile = DataProfile(
        series_lengths={"y": 100},
        n_series=1,
        index_type="datetime",
        frequency="D",
        target="y",
        exog_columns=["holiday"],
        categorical_exog=["holiday"],
        frequency_is_set=True,
    )
    steps = derive_preprocessing_steps(
        profile          = profile,
        forecaster       = "ForecasterFoundation",
        foundation_model = get_model_info("Salesforce/moirai-2.0-R-small"),
    )

    assert "handle_categorical_exog" not in [s.action for s in steps]


def test_derive_steps_ValueError_when_foundation_without_foundation_model():
    """
    Test that a ForecasterFoundation with categorical exog and no
    `foundation_model` raises ValueError, since the step depends on the
    capabilities of the model.
    """
    profile = DataProfile(
        series_lengths={"y": 100},
        n_series=1,
        index_type="datetime",
        frequency="D",
        target="y",
        exog_columns=["holiday"],
        categorical_exog=["holiday"],
        frequency_is_set=True,
    )

    err_msg = re.escape(
        "`foundation_model` is required to derive the preprocessing steps of "
        "'ForecasterFoundation'."
    )
    with pytest.raises(ValueError, match=err_msg):
        derive_preprocessing_steps(profile, "ForecasterFoundation")


@pytest.mark.parametrize(
    "missing_target, missing_exog, expected",
    [
        (
            {"y": 3},
            {},
            "'autogluon/chronos-2-small' accepts missing values in the series "
            "used as context, so they are passed as they are.",
        ),
        (
            {},
            {"promo": 2},
            "Missing values in the exogenous variables are passed to the model "
            "unchanged; impute them to control how they are filled.",
        ),
    ],
    ids=lambda dt: f"missing_target, missing_exog, expected: {dt}",
)
def test_derive_steps_handle_missing_values_when_foundation(
    missing_target, missing_exog, expected
):
    """
    Test that a foundation model gets a non-blocking missing-values step
    based on what the backend accepts, not the ML advice about
    `dropna_from_series` or NaN-tolerant estimators, which do not apply.
    """
    profile = DataProfile(
        series_lengths={"y": 100},
        n_series=1,
        index_type="datetime",
        frequency="D",
        target="y",
        exog_columns=["promo"],
        missing_target=missing_target,
        missing_exog=missing_exog,
        frequency_is_set=True,
    )
    steps = derive_preprocessing_steps(
        profile          = profile,
        forecaster       = "ForecasterFoundation",
        foundation_model = get_model_info("autogluon/chronos-2-small"),
    )
    step = next(s for s in steps if s.action == "handle_missing_values")

    assert step.reason == expected
    assert step.blocking is False
    assert "dropna_from_series" not in step.reason


def test_derive_steps_no_handle_categorical_exog_when_baseline():
    """
    Test that no handle_categorical_exog step is added for the baseline,
    which uses no exogenous variables at all.
    """
    profile = DataProfile(
        series_lengths={"y": 100},
        n_series=1,
        index_type="datetime",
        frequency="D",
        target="y",
        exog_columns=["holiday"],
        categorical_exog=["holiday"],
        frequency_is_set=True,
    )
    steps = derive_preprocessing_steps(profile, "ForecasterEquivalentDate")
    actions = [s.action for s in steps]

    assert "handle_categorical_exog" not in actions


@pytest.mark.parametrize(
    "missing_target, missing_exog, has_gaps, expected_actions",
    [
        ({"y": 3}, {}, False, ["handle_missing_values"]),
        ({}, {}, True, ["handle_missing_values"]),
        ({}, {"holiday": 2}, False, []),
    ],
    ids=lambda value: f"{value}",
)
def test_derive_steps_handle_missing_values_when_baseline(
    missing_target, missing_exog, has_gaps, expected_actions
):
    """
    Test that the baseline gets its own missing-values advice (impute the
    target) when the target has missing values or missing timestamps, and
    none for missing exogenous values, which it does not use.
    """
    profile = DataProfile(
        series_lengths={"y": 100},
        n_series=1,
        index_type="datetime",
        frequency="D",
        target="y",
        exog_columns=["holiday"],
        missing_target=missing_target,
        missing_exog=missing_exog,
        has_gaps=has_gaps,
        frequency_is_set=True,
    )
    steps = derive_preprocessing_steps(profile, "ForecasterEquivalentDate")

    assert [s.action for s in steps] == expected_actions
    if expected_actions:
        assert steps[0] == PreprocessingStep(
            action="handle_missing_values",
            reason=(
                "Impute the missing target values before training. "
                "ForecasterEquivalentDate repeats past values, so a missing "
                "value at an equivalent date becomes a missing prediction and "
                "the metrics cannot be computed."
            ),
            code_snippet=(
                "# Impute missing target values, for example:\n"
                "# data[target] = data[target].interpolate()"
            ),
            blocking=False,
        )


def test_derive_steps_handle_gaps_is_non_blocking():
    profile = DataProfile(
        series_lengths={"y": 100},
        n_series=1,
        index_type="datetime",
        frequency="D",
        target="y",
        has_gaps=True,
        frequency_is_set=True,
    )
    steps = derive_preprocessing_steps(profile, "ForecasterRecursive")
    gap_steps = [s for s in steps if s.action == "handle_gaps"]
    assert len(gap_steps) == 1
    assert gap_steps[0].blocking is False


def test_derive_steps_all_steps_are_preprocessing_step_instances():
    profile = DataProfile(
        series_lengths={"value": 100},
        n_series=3,
        index_type="datetime",
        frequency="D",
        target="value",
        date_column="date",
        series_id_column="series_id",
        data_format="long",
        frequency_is_set=False,
        has_gaps=True,
        index_is_monotonic=False,
    )
    steps = derive_preprocessing_steps(
        profile, "ForecasterRecursiveMultiSeries"
    )
    assert all(isinstance(s, PreprocessingStep) for s in steps)
    assert len(steps) >= 1  # handle_gaps (non-blocking)
