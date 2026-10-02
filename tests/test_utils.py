# Unit test _utils

import re
import urllib.error
import warnings
from pathlib import Path

import numpy as np
import pytest
import pandas as pd

from skforecast.model_selection import TimeSeriesFold

from skforecast_ai._utils import (
    _check_evaluated_target,
    _apply_interval_to_plan,
    _strip_code_blocks,
    _resolve_data_and_target,
    _resolve_inputs_with_profile,
    _validate_max_window_size,
    _validate_task_input,
)
from skforecast_ai import ForecastingAssistant
from skforecast_ai.exceptions import DataNotFoundError, InvalidInputError
from skforecast_ai.profiling import create_data_profile
from skforecast_ai.schemas import DataProfile

from tests.fixtures_assistant import df_single, series_single
from tests.fixtures_datasets import df_h2o_text


# =============================================================================
# _strip_code_blocks
# =============================================================================
@pytest.mark.parametrize(
    "text, expected",
    [
        (
            "Some text\n```python\nprint('hello')\n```\nMore text",
            "Some text\n"
            "(See `result.code` for the validated implementation.)\n"
            "More text",
        ),
        (
            "Intro\n```python\ncode1\n```\nMiddle\n```bash\ncode2\n```\nEnd",
            "Intro\n"
            "(See `result.code` for the validated implementation.)\n"
            "Middle\n"
            "(See `result.code` for the validated implementation.)\n"
            "End",
        ),
        (
            "Before\n```\nsome code\n```\nAfter",
            "Before\n"
            "(See `result.code` for the validated implementation.)\n"
            "After",
        ),
    ],
    ids=["single_block", "multiple_blocks", "no_language_specifier"],
)
def test_strip_code_blocks_output_when_code_blocks_present(text, expected):
    """
    Test that fenced code blocks are replaced with the pointer text.
    """
    result = _strip_code_blocks(text)
    assert result == expected


@pytest.mark.parametrize(
    "text",
    [
        "Just plain text without any code blocks.",
        "",
    ],
    ids=["plain_text", "empty_string"],
)
def test_strip_code_blocks_output_when_no_code_blocks(text):
    """
    Test that text without code blocks is returned unchanged.
    """
    result = _strip_code_blocks(text)
    assert result == text


# =============================================================================
# _resolve_data_and_target
# =============================================================================
def test_resolve_data_and_target_output_when_named_series():
    """
    Test that a named Series is framed and its name is used as the target.
    """
    index = pd.date_range("2020-01-01", periods=5, freq="D")
    series = pd.Series([1, 2, 3, 4, 5], index=index, name="sales")

    data, target = _resolve_data_and_target(series, target=None)

    assert isinstance(data, pd.DataFrame)
    assert target == "sales"
    assert list(data.columns) == ["sales"]
    pd.testing.assert_index_equal(data.index, index)


def test_resolve_data_and_target_output_when_named_series_matching_target():
    """
    Test that providing a target matching the Series name is accepted.
    """
    series = pd.Series([1, 2, 3], name="sales")

    data, target = _resolve_data_and_target(series, target="sales")

    assert target == "sales"
    assert list(data.columns) == ["sales"]


def test_resolve_data_and_target_warns_and_uses_y_when_series_unnamed():
    """
    Test that an unnamed Series triggers a warning and uses 'y' as target.
    """
    series = pd.Series([1, 2, 3])

    with pytest.warns(UserWarning, match="using 'y'"):
        data, target = _resolve_data_and_target(series, target=None)

    assert target == "y"
    assert list(data.columns) == ["y"]


def test_resolve_data_and_target_raises_when_target_mismatch_series_name():
    """
    Test that a target not matching the Series name raises ValueError.
    """
    series = pd.Series([1, 2, 3], name="sales")

    with pytest.raises(ValueError, match="must match the Series name"):
        _resolve_data_and_target(series, target="revenue")


def test_resolve_data_and_target_raises_when_dataframe_and_target_none():
    """
    Test that a DataFrame input with target=None raises ValueError.
    """
    df = pd.DataFrame({"sales": [1, 2, 3]})

    with pytest.raises(ValueError, match="`target` is required"):
        _resolve_data_and_target(df, target=None)


def test_resolve_data_and_target_output_when_dataframe_passthrough():
    """
    Test that a DataFrame input is returned unchanged with the given target.
    """
    df = pd.DataFrame({"sales": [1, 2, 3], "promo": [0, 1, 0]})

    data, target = _resolve_data_and_target(df, target="sales")

    assert target == "sales"
    pd.testing.assert_frame_equal(data, df)


@pytest.mark.parametrize(
    "path_type",
    [str, Path],
    ids=["str_path", "Path_object"],
)
def test_resolve_data_and_target_output_when_csv_path(tmp_path, path_type):
    """
    Test that a CSV file path (str or Path) is loaded into a DataFrame.
    """
    csv_path = tmp_path / "test_data.csv"
    df = pd.DataFrame({
        "date": ["2020-01-01", "2020-01-02", "2020-01-03"],
        "value": [10, 20, 30],
    })
    df.to_csv(csv_path, index=False)

    data, target = _resolve_data_and_target(path_type(csv_path), target="value")

    assert isinstance(data, pd.DataFrame)
    assert target == "value"
    assert "date" in data.columns
    assert "value" in data.columns
    assert len(data) == 3


@pytest.mark.parametrize(
    "path_type",
    [str, Path],
    ids=["str_path", "Path_object"],
)
def test_resolve_data_and_target_raises_when_csv_path_not_found(tmp_path, path_type):
    """
    Test that a clear FileNotFoundError is raised when the CSV path doesn't exist.
    """
    missing_path = tmp_path / "nonexistent.csv"
    with pytest.raises(FileNotFoundError, match="CSV file not found"):
        _resolve_data_and_target(path_type(missing_path), target="value")


def test_resolve_data_and_target_parses_date_column(tmp_path):
    """
    Test that a date column in a CSV is detected and parsed as datetime.
    """
    csv_path = tmp_path / "test_data.csv"
    df = pd.DataFrame({
        "date": ["2020-01-01", "2020-01-02", "2020-01-03"],
        "value": [10, 20, 30],
    })
    df.to_csv(csv_path, index=False)

    data, _ = _resolve_data_and_target(csv_path, target="value")

    assert pd.api.types.is_datetime64_any_dtype(data["date"])


def test_resolve_data_and_target_passes_date_column_to_csv_loader(tmp_path):
    """
    Test that `date_column` reaches the CSV loader: a column of dates with
    empty cells before the date column ('contract_end') is left as text
    with a warning without it, and without a warning with it.
    """
    df = df_h2o_text.copy()
    df.insert(0, "contract_end", df["date"])
    df.loc[list(range(10)), "contract_end"] = None
    csv_path = tmp_path / "data.csv"
    df.to_csv(csv_path, index=False)

    warn_msg = re.escape(
        "The dates of column 'contract_end' have 10 empty cell(s)"
    )
    with pytest.warns(UserWarning, match=warn_msg):
        data_without, _ = _resolve_data_and_target(csv_path, target="x")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        data_with, _ = _resolve_data_and_target(
                           data        = csv_path,
                           target      = "x",
                           date_column = "date",
                       )

    for data in (data_without, data_with):
        assert pd.api.types.is_object_dtype(data["contract_end"])
        assert pd.api.types.is_datetime64_any_dtype(data["date"])


def test_resolve_data_and_target_ValueError_when_csv_date_column_has_empty_cell(
    tmp_path
):
    """
    Test that the `date_column` of a CSV with an empty cell raises, without
    the advice to pass `date_column`.
    """
    df = df_h2o_text.copy()
    df.loc[100, "date"] = None
    csv_path = tmp_path / "data.csv"
    df.to_csv(csv_path, index=False)

    err_msg = re.escape(
        "The dates of column 'date' have 1 empty cell(s), at row position(s) "
        "100 (counting from 0, header excluded): every row needs a date. Fill "
        "in or drop those rows."
    )
    with pytest.raises(InvalidInputError, match=err_msg + "$"):
        _resolve_data_and_target(csv_path, target="x", date_column="date")


# =============================================================================
# _resolve_inputs_with_profile
# =============================================================================
profile_single = ForecastingAssistant().profile(
    data=df_single, target="sales", date_column="date"
)


def test_resolve_inputs_with_profile_delegates_when_no_profile():
    """
    Test that without a profile the inputs are resolved as before, so a
    DataFrame still requires an explicit target.
    """
    data, target, date_column, series_id_column = _resolve_inputs_with_profile(
        df_single, "sales", "date", None, profile=None
    )
    assert target == "sales"
    assert date_column == "date"
    assert series_id_column is None
    assert data is df_single

    with pytest.raises(ValueError, match="`target` is required"):
        _resolve_inputs_with_profile(df_single, None, None, None, profile=None)


def test_resolve_inputs_with_profile_fills_missing_values_from_profile():
    """
    Test that target, date_column and series_id_column default to the
    values recorded in the profile when they are not given.
    """
    _, target, date_column, series_id_column = _resolve_inputs_with_profile(
        df_single, None, None, None, profile=profile_single
    )

    assert target == "sales"
    assert date_column == "date"
    assert series_id_column is None


def test_resolve_inputs_with_profile_accepts_matching_values():
    """
    Test that explicit values equal to the recorded ones are accepted.
    """
    _, target, date_column, _ = _resolve_inputs_with_profile(
        df_single, "sales", "date", None, profile=profile_single
    )

    assert target == "sales"
    assert date_column == "date"


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"target": "other"}, "`target` 'other' does not match the target"),
        ({"date_column": "other"}, "`date_column` 'other' does not match"),
        ({"series_id_column": "id"}, "`series_id_column` 'id' does not match"),
    ],
    ids=["target", "date_column", "series_id_column"],
)
def test_resolve_inputs_with_profile_raises_when_value_conflicts(kwargs, match):
    """
    Test that a value different from the one recorded in the profile
    raises ValueError instead of being silently ignored.
    """
    args = {"target": None, "date_column": None, "series_id_column": None}
    args.update(kwargs)

    with pytest.raises(ValueError, match=match):
        _resolve_inputs_with_profile(
            df_single,
            args["target"],
            args["date_column"],
            args["series_id_column"],
            profile=profile_single,
        )


def test_resolve_inputs_with_profile_raises_when_columns_missing_in_data():
    """
    Test that data lacking a column the profile was built from fails
    early with a readable message, rather than inside the executed script.
    """
    with pytest.raises(ValueError, match=re.escape("column(s) ['sales']")):
        _resolve_inputs_with_profile(
            df_single.drop(columns=["sales"]), None, None, None,
            profile=profile_single,
        )


def test_resolve_inputs_with_profile_output_when_series_input():
    """
    Test that a pandas Series takes its target from its name and that a
    name different from the profile's target is rejected.
    """
    profile = ForecastingAssistant().profile(data=series_single)

    _, target, _, _ = _resolve_inputs_with_profile(
        series_single, None, None, None, profile=profile
    )
    assert target == "sales"

    with pytest.raises(ValueError, match="does not match the target"):
        _resolve_inputs_with_profile(
            series_single.rename("other"), None, None, None, profile=profile
        )


# =============================================================================
# Task-aware observation-count helpers
# =============================================================================
def _make_profile(
    series_lengths, frequency="D", n_series=None, **long_format
):
    """
    Build a minimal DataProfile for task input validation tests; pass
    `data_format`, `date_column` and `series_id_column` for long format.
    """
    return DataProfile(
        n_series=n_series if n_series is not None else len(series_lengths),
        series_lengths=series_lengths,
        target="value",
        index_type="datetime",
        frequency=frequency,
        **long_format,
    )


@pytest.mark.parametrize(
    "task_type",
    ["single_series", "statistical", "baseline"],
)
def test_validate_task_input_raises_when_single_task_with_multiple_series(
    task_type,
):
    """
    Test _validate_task_input raises ValueError when a single-series task
    receives more than one series.
    """
    profile = _make_profile({"A": {"length": 100}, "B": {"length": 100}})
    with pytest.raises(ValueError, match="supports a single series only"):
        _validate_task_input(profile, task_type)


def test_validate_task_input_raises_when_multivariate_unequal_lengths():
    """
    Test _validate_task_input raises ValueError when a multivariate task
    receives series of different lengths.
    """
    profile = _make_profile({"A": {"length": 100}, "B": {"length": 80}})
    with pytest.raises(ValueError, match="same length"):
        _validate_task_input(profile, "multivariate")


def test_validate_task_input_passes_when_valid():
    """
    Test _validate_task_input accepts compatible inputs (single-series
    task with one series; multivariate with equal lengths; foundation with
    one or several series, of equal or different lengths).
    """
    single = _make_profile({"value": {"length": 100}}, n_series=1)
    multivariate = _make_profile({"A": {"length": 100}, "B": {"length": 100}})
    uneven = _make_profile({"A": {"length": 100}, "B": {"length": 80}})

    assert _validate_task_input(single, "single_series") is None
    assert _validate_task_input(multivariate, "multivariate") is None
    assert _validate_task_input(single, "foundation") is None
    assert _validate_task_input(uneven, "foundation") is None


_LONG = {"data_format": "long", "series_id_column": "series"}


def test_validate_task_input_InvalidInputError_when_multivariate_long_format():
    """
    Test that ForecasterDirectMultiVariate is rejected on long-format data
    with several series: its script failed in every mode, with or without
    exogenous variables.
    """
    profile = _make_profile(
        {"A": {"length": 100}, "B": {"length": 100}},
        date_column="date", **_LONG,
    )

    err_msg = re.escape(
        "ForecasterDirectMultiVariate cannot forecast long-format data with "
        "several series. Use 'ForecasterRecursiveMultiSeries', or pass the "
        "series as columns (wide format) with `target` naming them."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        _validate_task_input(profile, "multivariate")
    assert exc_info.value.field == "forecaster"


@pytest.mark.parametrize("task_type", ["multi_series", "foundation"])
def test_validate_task_input_InvalidInputError_when_long_format_without_date_column(
    task_type,
):
    """
    Test that long-format data with several series and no date column (dated
    by its index) is rejected for the forecasters that split it into series:
    the script read a 'datetime' column that does not exist.
    """
    profile = _make_profile(
        {"A": {"length": 100}, "B": {"length": 100}}, **_LONG
    )

    err_msg = re.escape(
        "Long-format data with several series needs its dates in a column, "
        "named by `date_column`, which the generated script reads to split the "
        "series. With the dates in the index, move them to a column with "
        "`data.reset_index()`."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        _validate_task_input(profile, task_type)
    assert exc_info.value.field == "date_column"


def test_validate_task_input_passes_when_long_format_single_series_without_date_column():
    """
    Test that long-format data with a single series dated by its index is
    accepted: its script works.
    """
    profile = _make_profile({"A": {"length": 100}}, n_series=1, **_LONG)

    assert _validate_task_input(profile, "single_series") is None
    assert _validate_task_input(profile, "foundation") is None



# =============================================================================
# _validate_max_window_size
# =============================================================================
@pytest.mark.parametrize(
    "lags, window_features",
    [
        (33, None),
        ([1, 2, 33], None),
        (None, [{"stats": ["mean"], "window_size": 33}]),
        ([1, 7], [{"stats": ["mean"], "window_size": 33}]),
    ],
    ids=lambda value: f"{value!r}",
)
def test_validate_max_window_size_passes_when_within_budget(lags, window_features):
    """
    Test that lags and window sizes spanning up to 33% of the observations
    (33 of 100) pass the data budget check.
    """
    assert _validate_max_window_size(lags, window_features, 100) is None


@pytest.mark.parametrize(
    "lags, window_features",
    [
        (34, None),
        ([1, 2, 34], None),
        (None, [{"stats": ["mean"], "window_size": 34}]),
    ],
    ids=lambda value: f"{value!r}",
)
def test_validate_max_window_size_ValueError_when_span_exceeds_budget(
    lags, window_features
):
    """
    Test that a lag or window size spanning more than 33% of the
    observations raises ValueError with the span and the maximum allowed.
    """
    err_msg = re.escape(
        "Explicit lags/window_features span up to 34 observations, exceeding "
        "the maximum of 33 (33% of 100 observations). Reduce the largest lag "
        "or window size."
    )
    with pytest.raises(ValueError, match=err_msg):
        _validate_max_window_size(lags, window_features, 100)


@pytest.mark.parametrize(
    "lags, window_features, expected_field",
    [
        (34, None, "lags"),
        ([1, 2, 34], [{"stats": ["mean"], "window_size": 7}], "lags"),
        (3, [{"stats": ["mean"], "window_size": 34}], "window_features"),
    ],
    ids=lambda value: f"{value!r}",
)
def test_validate_max_window_size_code_and_field_when_span_exceeds_budget(
    lags, window_features, expected_field
):
    """
    Test that a span longer than the data allows has the code
    'insufficient_data' and names as field the override with the largest
    span.
    """
    err_msg = re.escape(
        "Explicit lags/window_features span up to 34 observations, exceeding "
        "the maximum of 33 (33% of 100 observations). Reduce the largest lag "
        "or window size."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        _validate_max_window_size(lags, window_features, 100)

    assert exc_info.value.code == "insufficient_data"
    assert exc_info.value.field == expected_field


def test_apply_interval_to_plan_uses_native_method_for_foundation_plan():
    """
    Test that applying an interval to a foundation plan without intervals
    selects the native interval method, extends the explanation, and leaves
    the original plan untouched, while a plan that already predicts the
    same interval is returned as is.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5, forecaster="ForecasterFoundation")
    assert plan.interval is None

    updated = _apply_interval_to_plan(plan, [0.1, 0.9])

    assert updated.interval == [0.1, 0.9]
    assert updated.interval_method == "native"
    assert updated.explanation == f"{plan.explanation} Prediction intervals via native."
    assert plan.interval is None
    assert _apply_interval_to_plan(updated, [0.1, 0.9]) is updated


def test_apply_interval_to_plan_ValueError_when_foundation_model_lacks_quantiles():
    """
    Test that applying an interval that the foundation model of the plan
    cannot predict raises ValueError, although the plan copy skips the
    schema validators.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(
        profile, steps=5, forecaster="ForecasterFoundation",
        estimator="google/timesfm-3.0-pytorch",
    )

    err_msg = re.escape(
        "'google/timesfm-3.0-pytorch' (TimesFM3Adapter) only predicts the "
        "quantile levels"
    )
    with pytest.raises(ValueError, match=err_msg):
        _apply_interval_to_plan(plan, [0.05, 0.95])


def test_apply_interval_to_plan_uses_conformal_for_baseline():
    """
    Test that applying an interval to a baseline plan selects the conformal
    method, the only one ForecasterEquivalentDate supports.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5, forecaster="ForecasterEquivalentDate")

    updated = _apply_interval_to_plan(plan, [0.1, 0.9])

    assert updated.interval == [0.1, 0.9]
    assert updated.interval_method == "conformal"


def _gapped_single_series(drop: list[int]) -> tuple[pd.DataFrame, DataProfile]:
    """Daily series of 100 days without the given positions, and its profile."""
    dates = pd.date_range("2023-01-01", periods=100, freq="D")
    data = pd.DataFrame(
        {"date": dates, "y": np.arange(100, dtype=float)}
    ).drop(index=drop).reset_index(drop=True)

    return data, create_data_profile(data, target="y", date_column="date")


def test_check_evaluated_target_ValueError_when_gap_in_test_folds():
    """
    Test that a missing timestamp inside a test fold is reported with its
    date before running, whatever the estimator, because skforecast cannot
    compute single-series metrics on it.
    """
    data, data_profile = _gapped_single_series(drop=[85])
    cv = TimeSeriesFold(steps=5, initial_train_size=70, verbose=False)

    err_msg = re.escape(
        "The target has 1 missing value(s) in the test folds "
        "(2023-03-27 00:00:00), counting the missing timestamps that asfreq() "
        "restores. skforecast cannot compute the metrics on them, whatever "
        "the estimator. Impute the target, or evaluate on dates without "
        "missing values."
    )
    with pytest.raises(ValueError, match=err_msg):
        _check_evaluated_target(data=data, data_profile=data_profile, cv=cv)


def test_check_evaluated_target_output_when_gap_only_in_training():
    """
    Test that a missing timestamp before the first test fold is accepted:
    the forecaster handles it in training and no metric is computed on it.
    """
    data, data_profile = _gapped_single_series(drop=[20, 21])
    cv = TimeSeriesFold(steps=5, initial_train_size=70, verbose=False)

    assert _check_evaluated_target(data=data, data_profile=data_profile, cv=cv) is None


def test_check_evaluated_target_ValueError_when_gap_in_test_split():
    """
    Test that a missing timestamp in the test split of an evaluation-mode
    forecast is reported, and one outside the evaluated steps is not.
    """
    data, data_profile = _gapped_single_series(drop=[97])

    err_msg = re.escape(
        "The target has 1 missing value(s) in the test split (2023-04-08 00:00:00)"
    )
    with pytest.raises(ValueError, match=err_msg):
        _check_evaluated_target(
            data         = data,
            data_profile = data_profile,
            end_train    = "2023-04-05",
            steps        = 5,
        )

    assert _check_evaluated_target(
        data         = data,
        data_profile = data_profile,
        end_train    = "2023-03-20",
        steps        = 5,
    ) is None


@pytest.mark.parametrize(
    "error, expected_code",
    [
        (urllib.error.URLError("unreachable"), "data_not_found"),
        (pd.errors.ParserError("bad row"), "data_unreadable"),
    ],
    ids=["unreachable", "not_a_csv"],
)
def test_resolve_data_and_target_code_when_url_cannot_be_read(
    monkeypatch, error, expected_code
):
    """
    Test that a URL that cannot be read raises DataNotFoundError (a
    FileNotFoundError) with the code 'data_not_found' when it cannot be
    reached, and 'data_unreadable' when it was downloaded but is not a CSV.
    """

    def _read_csv(*args, **kwargs):
        raise error

    monkeypatch.setattr(pd, "read_csv", _read_csv)

    err_msg = re.escape(
        f"Could not read CSV from URL: 'https://example.com/a.csv'. {error}"
    )
    with pytest.raises(DataNotFoundError, match=err_msg) as exc_info:
        _resolve_data_and_target("https://example.com/a.csv", "y")

    assert exc_info.value.code == expected_code
    assert exc_info.value.field == "data"


def test_resolve_inputs_with_profile_ValueError_when_csv_date_column_has_empty_cell(
    tmp_path
):
    """
    Test that a profile reused on a CSV whose date column (the one of the
    profile) has an empty cell raises, even when a later column holds
    complete dates, instead of leaving the dates as text for the generated
    script to fail on.
    """
    df = df_h2o_text.copy()
    df["period_end"] = (
        pd.to_datetime(df["date"]) + pd.offsets.MonthEnd(0)
    ).dt.strftime("%Y-%m-%d")
    clean_path = tmp_path / "clean.csv"
    df.to_csv(clean_path, index=False)
    profile = ForecastingAssistant().profile(data=clean_path, target="x")
    df.loc[100, "date"] = None
    csv_path = tmp_path / "data.csv"
    df.to_csv(csv_path, index=False)

    err_msg = re.escape(
        "The dates of column 'date' have 1 empty cell(s), at row position(s) "
        "100 (counting from 0, header excluded): every row needs a date. Fill "
        "in or drop those rows."
    )
    with pytest.raises(InvalidInputError, match=err_msg + "$"):
        _resolve_inputs_with_profile(csv_path, None, None, None, profile=profile)


def test_resolve_data_and_target_passes_date_column_to_loader_of_url(monkeypatch):
    """
    Test that `date_column` reaches the CSV loader also for a URL: the named
    column with an empty cell raises, without the advice to pass
    `date_column`.
    """
    df = df_h2o_text.copy()
    df.loc[100, "date"] = None
    monkeypatch.setattr(pd, "read_csv", lambda *args, **kwargs: df.copy())

    err_msg = re.escape(
        "The dates of column 'date' have 1 empty cell(s), at row position(s) "
        "100 (counting from 0, header excluded): every row needs a date. Fill "
        "in or drop those rows."
    )
    with pytest.raises(InvalidInputError, match=err_msg + "$"):
        _resolve_data_and_target(
            data        = "https://example.com/data.csv",
            target      = "x",
            date_column = "date",
        )


def test_resolve_inputs_with_profile_passes_date_column_when_no_profile(tmp_path):
    """
    Test that, without a profile, `date_column` reaches the CSV loader: a
    column of dates with empty cells before it is left as text without a
    warning.
    """
    df = df_h2o_text.copy()
    df.insert(0, "contract_end", df["date"])
    df.loc[list(range(10)), "contract_end"] = None
    csv_path = tmp_path / "data.csv"
    df.to_csv(csv_path, index=False)

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        data, _, date_column, _ = _resolve_inputs_with_profile(
            csv_path, "x", "date", None, profile=None
        )

    assert date_column == "date"
    assert pd.api.types.is_object_dtype(data["contract_end"])
    assert pd.api.types.is_datetime64_any_dtype(data["date"])


def test_resolve_inputs_with_profile_ValueError_when_date_column_conflicts(tmp_path):
    """
    Test that a `date_column` that does not match the profile raises the
    mismatch error, as the CSV loader checks the date column of the profile
    (here complete), not the one passed.
    """
    clean_path = tmp_path / "clean.csv"
    df_h2o_text.to_csv(clean_path, index=False)
    profile = ForecastingAssistant().profile(data=clean_path, target="x")
    df = df_h2o_text.copy()
    df["period_end"] = df["date"]
    df.loc[100, "period_end"] = None
    csv_path = tmp_path / "data.csv"
    df.to_csv(csv_path, index=False)

    err_msg = re.escape(
        "`date_column` 'period_end' does not match the value recorded in "
        "`profile` ('date'). Pass the value the profile was built with, or "
        "omit it."
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        _resolve_inputs_with_profile(
            csv_path, None, "period_end", None, profile=profile
        )


def test_resolve_inputs_with_profile_DataNotFoundError_before_date_column_conflict(
    tmp_path
):
    """
    Test that a missing CSV is reported before a `date_column` that does not
    match the profile.
    """
    clean_path = tmp_path / "clean.csv"
    df_h2o_text.to_csv(clean_path, index=False)
    profile = ForecastingAssistant().profile(data=clean_path, target="x")

    err_msg = re.escape("CSV file not found: '")
    with pytest.raises(DataNotFoundError, match=err_msg):
        _resolve_inputs_with_profile(
            tmp_path / "missing.csv", None, "other", None, profile=profile
        )
