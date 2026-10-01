# Integration test: the standalone script reproduces the executed workflow

import subprocess
import sys
import textwrap

import numpy as np
import pandas as pd
import pytest

from skforecast.model_selection import TimeSeriesFold

from skforecast_ai import ForecastingAssistant

from tests.fixtures_assistant import df_multi_long, df_multi_wide, df_no_exog, df_single
from tests.fixtures_datasets import df_h2o, df_items_sales_long


def _run_standalone(script: str, workdir) -> pd.DataFrame:
    """
    Run a generated script in a fresh interpreter and collect `predictions`.

    The script is executed exactly as a user would run it (its own
    process, working directory `workdir`, data loaded from CSV), which is
    the guarantee the library makes: the code returned is the code that
    ran. A tiny wrapper exports the `predictions` variable to CSV.

    Parameters
    ----------
    script : str
        Full standalone script (`result.code`).
    workdir : Path
        Directory holding the CSV files the script reads.

    Returns
    -------
    predictions : pandas DataFrame
        Predictions produced by the script, index parsed back to datetime.
    """

    script_path = workdir / "script.py"
    script_path.write_text(script)
    export_path = workdir / "predictions.csv"
    wrapper = workdir / "run.py"
    wrapper.write_text(textwrap.dedent(f"""
        import runpy
        import pandas as pd
        namespace = runpy.run_path({str(script_path)!r})
        pd.DataFrame(namespace["predictions"]).to_csv({str(export_path)!r})
    """))

    proc = subprocess.run(
        [sys.executable, str(wrapper)],
        cwd=workdir, capture_output=True, text=True, timeout=600,
    )
    assert proc.returncode == 0, proc.stderr[-3000:]

    predictions = pd.read_csv(export_path, index_col=0)
    predictions.index = pd.to_datetime(predictions.index)
    return predictions


def _assert_same_predictions(standalone: pd.DataFrame, executed: pd.DataFrame) -> None:
    """Compare the point forecasts of the standalone run with the executed run."""
    assert len(standalone) == len(executed)
    np.testing.assert_allclose(
        standalone["pred"].to_numpy(), executed["pred"].to_numpy(), rtol=1e-6
    )
    assert list(standalone.index) == list(executed.index)


def test_standalone_script_matches_forecast_when_evaluation_mode_with_exog(tmp_path):
    """
    Test that the script produced by forecast_code() for an evaluation
    run with exogenous variables loads the CSV from the recorded path and
    yields the same predictions as forecast().
    """
    csv_path = tmp_path / "sales.csv"
    df_single.to_csv(csv_path, index=False)
    assistant = ForecastingAssistant()

    code = assistant.forecast_code(
        data=csv_path, target="sales", date_column="date", steps=5, test_size=5
    ).code
    executed = assistant.forecast(
        data=csv_path, target="sales", date_column="date", steps=5, test_size=5
    )

    # The script embeds the path as a Python literal, so compare its repr
    # (backslashes are escaped on Windows).
    assert repr(str(csv_path)) in code
    _assert_same_predictions(_run_standalone(code, tmp_path), executed.predictions)


def test_standalone_script_matches_forecast_when_prediction_mode(tmp_path):
    """
    Test that the prediction-mode script (no test split, forecast the
    future) yields the same predictions as forecast().
    """
    csv_path = tmp_path / "sales.csv"
    df_no_exog.to_csv(csv_path, index=False)
    assistant = ForecastingAssistant()

    code = assistant.forecast_code(
        data=csv_path, target="sales", date_column="date", steps=5
    ).code
    executed = assistant.forecast(
        data=csv_path, target="sales", date_column="date", steps=5
    )

    _assert_same_predictions(_run_standalone(code, tmp_path), executed.predictions)


def test_standalone_script_loads_future_exog_when_prediction_mode_with_exog(tmp_path):
    """
    Test that the prediction-mode script with exogenous variables reads
    `exog_future.csv` from the working directory and yields the same
    predictions as forecast() given the same future values.
    """
    csv_path = tmp_path / "sales.csv"
    df_single.to_csv(csv_path, index=False)
    last_date = pd.to_datetime(df_single["date"]).max()
    exog_future = pd.DataFrame(
        {"promo": [0, 1, 0, 1, 0]},
        index=pd.date_range(last_date + pd.Timedelta(1, unit="D"), periods=5, freq="D"),
    )
    exog_future.rename_axis("date").reset_index().to_csv(
        tmp_path / "exog_future.csv", index=False
    )
    assistant = ForecastingAssistant()

    code = assistant.forecast_code(
        data=csv_path, target="sales", date_column="date", steps=5
    ).code
    executed = assistant.forecast(
        data=csv_path, target="sales", date_column="date", steps=5,
        exog=exog_future,
    )

    assert "exog_future.csv" in code
    _assert_same_predictions(_run_standalone(code, tmp_path), executed.predictions)


def test_standalone_script_matches_forecast_when_multi_series_long(tmp_path):
    """
    Test that the long-format multi-series script (reshape to dict,
    ForecasterRecursiveMultiSeries) yields the same predictions as
    forecast().
    """
    csv_path = tmp_path / "series.csv"
    df_multi_long.to_csv(csv_path, index=False)
    assistant = ForecastingAssistant()
    kwargs = dict(
        data=csv_path, target="value", date_column="date",
        series_id_column="series_id", steps=5, test_size=5,
    )

    code = assistant.forecast_code(**kwargs).code
    executed = assistant.forecast(**kwargs)

    standalone = _run_standalone(code, tmp_path)
    assert len(standalone) == len(executed.predictions)
    np.testing.assert_allclose(
        standalone["pred"].to_numpy(), executed.predictions["pred"].to_numpy(),
        rtol=1e-6,
    )


@pytest.mark.parametrize(
    "data, kwargs",
    [
        (
            pd.concat([df_no_exog, df_no_exog.iloc[[10]]], ignore_index=True),
            {"target": "sales", "date_column": "date"},
        ),
        (
            pd.concat([df_multi_long, df_multi_long.iloc[[-10]]], ignore_index=True),
            {"target": "value", "date_column": "date", "series_id_column": "series_id"},
        ),
        (
            pd.concat(
                [df_multi_long, df_multi_long.iloc[[-10]]], ignore_index=True
            ).rename(columns={"series_id": "store's id", "date": 'day "local"'}),
            {
                "target": "value",
                "date_column": 'day "local"',
                "series_id_column": "store's id",
            },
        ),
    ],
    ids=["single", "long", "long, quotes in column names"],
)
def test_standalone_script_matches_forecast_when_duplicate_rows_are_identical(
    tmp_path, data, kwargs
):
    """
    Test that data with a timestamp repeated in an identical row produces a
    script that drops the copy and runs (for long format it deduplicates on
    the series identifier and date columns, without asfreq on its
    RangeIndex), with the same predictions as forecast(). Column names with
    single and double quotes are written as string literals.
    """
    csv_path = tmp_path / "data.csv"
    data.to_csv(csv_path, index=False)
    assistant = ForecastingAssistant()
    kwargs = dict(data=csv_path, steps=5, test_size=5, **kwargs)

    code = assistant.forecast_code(**kwargs).code
    executed = assistant.forecast(**kwargs)

    standalone = _run_standalone(code, tmp_path)
    assert len(standalone) == len(executed.predictions)
    np.testing.assert_allclose(
        standalone["pred"].to_numpy(), executed.predictions["pred"].to_numpy(),
        rtol=1e-6,
    )


def test_standalone_script_matches_forecast_when_multi_series_wide(tmp_path):
    """
    Test that the wide-format multi-series script (one column per series)
    yields the same predictions as forecast().
    """
    csv_path = tmp_path / "series.csv"
    df_multi_wide.to_csv(csv_path, index=False)
    assistant = ForecastingAssistant()
    kwargs = dict(
        data=csv_path, target=["series_a", "series_b"], date_column="date",
        steps=5, test_size=5,
    )

    code = assistant.forecast_code(**kwargs).code
    executed = assistant.forecast(**kwargs)

    standalone = _run_standalone(code, tmp_path)
    assert len(standalone) == len(executed.predictions)
    np.testing.assert_allclose(
        standalone["pred"].to_numpy(), executed.predictions["pred"].to_numpy(),
        rtol=1e-6,
    )


def test_standalone_script_matches_forecast_when_statistical(tmp_path):
    """
    Test that the ForecasterStats (Auto-ARIMA) script yields the same
    predictions as forecast().
    """
    csv_path = tmp_path / "sales.csv"
    df_no_exog.to_csv(csv_path, index=False)
    assistant = ForecastingAssistant()
    kwargs = dict(
        data=csv_path, target="sales", date_column="date", steps=5,
        test_size=5, forecaster="ForecasterStats",
    )

    code = assistant.forecast_code(**kwargs).code
    executed = assistant.forecast(**kwargs)

    _assert_same_predictions(_run_standalone(code, tmp_path), executed.predictions)


def test_standalone_script_matches_forecast_when_baseline(tmp_path):
    """
    Test that the ForecasterEquivalentDate (baseline) script, with conformal
    intervals and exogenous columns in the data that it must ignore, yields
    the same predictions as forecast().
    """
    csv_path = tmp_path / "sales.csv"
    df_single.to_csv(csv_path, index=False)
    assistant = ForecastingAssistant()
    kwargs = dict(
        data=csv_path, target="sales", date_column="date", steps=5,
        test_size=5, forecaster="ForecasterEquivalentDate", interval=[0.1, 0.9],
    )

    code = assistant.forecast_code(**kwargs).code
    executed = assistant.forecast(**kwargs)

    _assert_same_predictions(_run_standalone(code, tmp_path), executed.predictions)


def test_standalone_backtesting_script_matches_backtest(tmp_path):
    """
    Test that the script produced by backtest_code() loads the CSV from
    the recorded path and yields the same backtest predictions as
    backtest().
    """
    csv_path = tmp_path / "sales.csv"
    df_single.to_csv(csv_path, index=False)
    assistant = ForecastingAssistant()
    cv = TimeSeriesFold(steps=5, initial_train_size=60, refit=False)

    code = assistant.backtest_code(
        data=csv_path, target="sales", date_column="date", cv=cv
    ).code
    executed = assistant.backtest(
        data=csv_path, target="sales", date_column="date", cv=cv,
        show_progress=False,
    )

    # The script embeds the path as a Python literal, so compare its repr
    # (backslashes are escaped on Windows).
    assert repr(str(csv_path)) in code
    standalone = _run_standalone(code, tmp_path)
    np.testing.assert_allclose(
        standalone["pred"].to_numpy(), executed.predictions["pred"].to_numpy(),
        rtol=1e-6,
    )


@pytest.mark.parametrize(
    "order", ["descending", "shuffled"], ids=lambda dt: f"order: {dt}"
)
def test_standalone_script_matches_forecast_when_csv_rows_not_in_date_order(
    tmp_path, order
):
    """
    Test that a CSV whose rows are not in date order (h2o descending or
    shuffled) gets the plan and the predictions of the sorted data, and
    that the script run as a file yields the same predictions as
    forecast(). Before, descending rows gave the lags [1] and a script that
    failed inside skforecast, and shuffled rows other lags and predictions.
    """
    data = df_h2o.iloc[::-1] if order == "descending" else df_h2o.sample(
        frac=1, random_state=1
    )
    csv_path = tmp_path / "h2o.csv"
    data.to_csv(csv_path)
    assistant = ForecastingAssistant()

    code = assistant.forecast_code(data=csv_path, target="x", steps=12).code
    executed = assistant.forecast(data=csv_path, target="x", steps=12)
    expected = assistant.forecast(data=df_h2o, target="x", steps=12)

    assert executed.plan.forecaster_kwargs["lags"] == [1, 9, 10, 11, 12, 13, 14]
    assert str(executed.predictions.index[0]) == "2008-07-01 00:00:00"
    np.testing.assert_allclose(
        executed.predictions["pred"].to_numpy()[:3],
        [0.97755777, 1.07009966, 1.0921686],
        rtol=1e-6,
    )
    assert executed.plan == expected.plan
    pd.testing.assert_frame_equal(executed.predictions, expected.predictions)
    _assert_same_predictions(_run_standalone(code, tmp_path), executed.predictions)


def test_standalone_script_matches_forecast_when_csv_dates_are_day_first(tmp_path):
    """
    Test that a CSV in date order with day-first text dates (items_sales
    item_1 from 13/01/2012) is read as the script reads it, with the format
    guessed from the first date: no rows are taken for out of order, the
    start date is the first date of the file, and the script run as a file
    yields the same predictions as forecast(). Each date used to be parsed
    on its own, so '01/02/2012' was read as 2 January.
    """
    data = df_items_sales_long[df_items_sales_long["series"] == "item_1"]
    data = data[data["date"] >= "2012-01-13"].drop(columns="series")
    data = data.assign(date=data["date"].dt.strftime("%d/%m/%Y"))
    csv_path = tmp_path / "item_1.csv"
    data.to_csv(csv_path, index=False)
    assistant = ForecastingAssistant()
    kwargs = {
        "data": csv_path, "target": "value", "date_column": "date",
        "steps": 7, "estimator": "Ridge",
    }

    profile = assistant.profile(data=csv_path, target="value", date_column="date")
    code = assistant.forecast_code(**kwargs).code
    executed = assistant.forecast(**kwargs)

    assert profile.data_profile.start_date == "2012-01-13"
    assert profile.data_profile.frequency == "D"
    assert profile.data_profile.index_is_monotonic is True
    assert profile.data_profile.warnings == []
    assert str(executed.predictions.index[0]) == "2012-04-30 00:00:00"
    _assert_same_predictions(_run_standalone(code, tmp_path), executed.predictions)
