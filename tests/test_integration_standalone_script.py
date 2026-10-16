# Integration test: the standalone script reproduces the executed workflow

import re
import subprocess
import sys
import textwrap

import numpy as np
import pandas as pd
import pytest

from skforecast.exceptions import MissingValuesWarning
from skforecast.model_selection import TimeSeriesFold

from skforecast_ai import ForecastingAssistant
from skforecast_ai._utils import load_exog

from tests.fixtures_assistant import (
    df_multi_long,
    df_multi_long_integer_ids,
    df_multi_long_numeric_ids,
    df_multi_long_staggered,
    df_multi_wide,
    df_no_exog,
    df_single,
)
from tests.fixtures_csv_dialect import (
    df_dialect,
    df_dialect_cp1252,
    df_dialect_cp1252_exog,
    df_dialect_thousands,
    df_dialect_thousands_long,
    write_cp1252,
    write_dialect,
    write_thousands,
)
from tests.fixtures_datasets import df_h2o, df_items_sales_long
from tests.fixtures_future_exog import data_long, exog_long


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

    # The series names are text, as the script names them ('001').
    predictions = pd.read_csv(export_path, index_col=0, dtype={"level": str})
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


def _write_german(path, frame: pd.DataFrame) -> None:
    """
    Write a frame of 'date' and 'y' as the German Excel writes a CSV file:
    ';' between fields, dates such as '15.01.2020' and numbers such as
    '1.234,56'.
    """
    lines = ["date;y"]
    for date, value in zip(frame["date"], frame["y"]):
        number = f"{value:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")
        lines.append(f"{date.strftime('%d.%m.%Y')};{number}")
    path.write_text("\n".join(lines) + "\n")


# Daily series of 60 days from 2020-01-01 with values above 1,000, and the
# same series monthly from 2015-01-01: their CSV files are written below
# with the dates in each format.
_daily = pd.DataFrame(
    {
        "date": pd.date_range("2020-01-01", periods=60, freq="D"),
        "y": np.round(1000 + 7.25 * np.arange(60) + 40 * np.sin(np.arange(60)), 2),
    }
)
_monthly = pd.DataFrame(
    {
        "date": pd.date_range("2015-01-01", periods=48, freq="MS"),
        "y": np.round(1000 + 5 * np.arange(48) + 90 * np.sin(np.arange(48)), 2),
    }
)


@pytest.mark.parametrize(
    "frame, write, profile_kwargs, date_format, line",
    [
        (
            _daily,
            lambda path, frame: frame.assign(
                date=frame["date"].dt.strftime("%d/%m/%Y")
            ).to_csv(path, index=False),
            {},
            "%d/%m/%Y",
            "data = pd.read_csv({path!r})\n",
        ),
        (
            _monthly,
            lambda path, frame: frame.assign(
                date=frame["date"].dt.strftime("%d/%m/%Y")
            ).to_csv(path, index=False),
            {"dayfirst": True},
            "%d/%m/%Y",
            "data = pd.read_csv({path!r})\n",
        ),
        (
            _monthly,
            lambda path, frame: frame.assign(
                date=frame["date"].dt.strftime("%d/%m/%Y")
            ).to_csv(path, index=False),
            {},
            "%d/%m/%Y",
            "data = pd.read_csv({path!r})\n",
        ),
        (
            _monthly,
            lambda path, frame: frame.assign(
                date=frame["date"].dt.strftime("%m/%d/%Y")
            ).to_csv(path, index=False),
            {},
            "%m/%d/%Y",
            "data = pd.read_csv({path!r})\n",
        ),
        (
            _daily,
            lambda path, frame: frame.assign(
                date=frame["date"].dt.strftime("%Y%m%d").astype(int)
            ).to_csv(path, index=False),
            {},
            "%Y%m%d",
            "data = pd.read_csv({path!r})\n",
        ),
        (
            _daily,
            _write_german,
            {},
            "%d.%m.%Y",
            "data = pd.read_csv({path!r}, sep=';', decimal=',', thousands='.', "
            "dtype={{'date': str}})\n",
        ),
    ],
    ids=[
        "day first daily",
        "day first monthly with dayfirst",
        "day first monthly told from regularity",
        "us monthly told from regularity",
        "whole numbers yyyymmdd",
        "German Excel with thousands",
    ],
)
def test_standalone_script_matches_forecast_when_csv_dates_need_a_format(
    tmp_path, frame, write, profile_kwargs, date_format, line
):
    """
    Test that a CSV file whose dates the generated script reads with a
    format (day first after a first date that reads month first, monthly
    dates that read both ways with `dayfirst` or in the only order in which
    they are regular, day first or month first as a US file writes them,
    whole numbers such as 20200131, and the German Excel with '15.01.2020'
    and '1.234,56') is read with that format by forecast() and by the
    script run as a file, with the predictions of the same data written in
    ISO 8601 by `to_csv()`.
    """
    csv_path = tmp_path / "data.csv"
    write(csv_path, frame)
    iso_path = tmp_path / "iso.csv"
    frame.to_csv(iso_path, index=False)
    assistant = ForecastingAssistant()

    profile = assistant.profile(data=csv_path, target="y", **profile_kwargs)
    executed = assistant.forecast(data=csv_path, steps=6, profile=profile)
    expected = assistant.forecast(data=iso_path, target="y", steps=6)

    assert profile.data_profile.date_format == date_format
    assert profile.data_profile.frequency == expected.profile.data_profile.frequency
    assert line.format(path=str(csv_path)) in executed.code
    assert (
        f"data['date'] = pd.to_datetime(data['date'], format={date_format!r})\n"
        in executed.code
    )
    pd.testing.assert_frame_equal(executed.predictions, expected.predictions)
    _assert_same_predictions(_run_standalone(executed.code, tmp_path), executed.predictions)


def test_standalone_script_matches_forecast_when_long_format_future_exog_day_first(
    tmp_path,
):
    """
    Test that long-format data and future exogenous values written day
    first, whose horizon reads both ways ('01/04/2012' to '07/04/2012'), are
    read in the order of the data by load_exog() and by the script run as a
    file with that file as `exog_future.csv`, with the predictions of the
    same files written in ISO 8601.
    """
    data = df_items_sales_long[df_items_sales_long["date"] <= "2012-03-31"].copy()
    data["promo"] = (data["date"].dt.day % 5 == 0).astype(float)
    future_dates = pd.date_range("2012-04-01", periods=7, freq="D")
    exog = pd.DataFrame(
        {
            "series": np.repeat(["item_1", "item_2", "item_3"], 7),
            "date": np.tile(future_dates, 3),
            "promo": np.tile([0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0], 3),
        }
    )
    csv_path = tmp_path / "items.csv"
    data.assign(date=data["date"].dt.strftime("%d/%m/%Y")).to_csv(
        csv_path, index=False
    )
    exog.assign(date=exog["date"].dt.strftime("%d/%m/%Y")).to_csv(
        tmp_path / "exog_future.csv", index=False
    )
    iso_path = tmp_path / "items_iso.csv"
    data.to_csv(iso_path, index=False)
    assistant = ForecastingAssistant()
    kwargs = {
        "target": "value", "date_column": "date", "series_id_column": "series",
    }

    profile = assistant.profile(data=csv_path, **kwargs)
    future = load_exog(
        tmp_path / "exog_future.csv",
        date_column      = "date",
        series_id_column = "series",
        date_format      = profile.data_profile.date_format,
    )
    executed = assistant.forecast(
        data=csv_path, steps=7, profile=profile, estimator="Ridge", exog=future
    )
    expected = assistant.forecast(
        data=iso_path, steps=7, estimator="Ridge", exog=exog, **kwargs
    )

    assert profile.data_profile.date_format == "%d/%m/%Y"
    assert (
        "exog_future['date'] = pd.to_datetime(exog_future['date'], "
        "format='%d/%m/%Y')\n" in executed.code
    )
    pd.testing.assert_frame_equal(executed.predictions, expected.predictions)
    standalone = _run_standalone(executed.code, tmp_path)
    assert list(standalone["level"]) == list(executed.predictions["level"])
    _assert_same_predictions(standalone, executed.predictions)


@pytest.mark.parametrize(
    "exog_written, exog_format_arg",
    [("%Y-%m-%d", ""), ("%d/%m/%Y", ", format='%d/%m/%Y'")],
    ids=["exog in iso by to_csv", "exog day first"],
)
def test_standalone_script_matches_forecast_when_day_first_data_and_future_exog(
    tmp_path, exog_written, exog_format_arg
):
    """
    Test that the future exogenous values of data written day first are read
    with their own format, by load_exog() and by the script run as a file
    with that file as `exog_future.csv`: in ISO 8601, as `to_csv()` of a
    frame indexed by its dates writes them (no format), or day first like
    the data, whose seven dates read both ways and take the order of the
    data. The predictions are the same, those of the data written in ISO
    8601.
    """
    data = _daily.assign(promo=(np.arange(60) % 7 == 5).astype(float))
    future = pd.DataFrame(
        {"promo": [0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0]},
        index=pd.DatetimeIndex(
            pd.date_range("2020-03-01", periods=7, freq="D"), name="date"
        ),
    )
    csv_path = tmp_path / "data.csv"
    data.assign(date=data["date"].dt.strftime("%d/%m/%Y")).to_csv(
        csv_path, index=False
    )
    future.set_axis(future.index.strftime(exog_written)).rename_axis(
        "date"
    ).to_csv(tmp_path / "exog_future.csv")
    iso_path = tmp_path / "iso.csv"
    data.to_csv(iso_path, index=False)
    assistant = ForecastingAssistant()

    profile = assistant.profile(data=csv_path, target="y", date_column="date")
    exog = load_exog(
        tmp_path / "exog_future.csv",
        date_column = "date",
        date_format = profile.data_profile.date_format,
    )
    executed = assistant.forecast(
        data=csv_path, steps=7, profile=profile, estimator="Ridge", exog=exog
    )
    expected = assistant.forecast(
        data=iso_path, target="y", date_column="date", steps=7,
        estimator="Ridge", exog=future,
    )

    assert profile.data_profile.date_format == "%d/%m/%Y"
    assert (
        f"exog_future['date'] = pd.to_datetime(exog_future['date']"
        f"{exog_format_arg})\n" in executed.code
    )
    pd.testing.assert_frame_equal(executed.predictions, expected.predictions)
    _assert_same_predictions(
        _run_standalone(executed.code, tmp_path), executed.predictions
    )


def test_standalone_script_matches_forecast_when_csv_long_series_has_gaps(tmp_path):
    """
    Test that a long-format CSV whose second series has missing dates is
    profiled with gaps (only the first series was checked before) and that
    the script run as a file yields the same predictions as forecast().
    """
    csv_path = tmp_path / "items.csv"
    df_items_sales_long.drop(index=range(130, 150)).to_csv(csv_path, index=False)
    assistant = ForecastingAssistant()
    kwargs = {
        "data": csv_path, "target": "value", "date_column": "date",
        "series_id_column": "series", "steps": 7,
    }

    code = assistant.forecast_code(**kwargs).code
    # skforecast warns when the missing dates become NaN, and again when the
    # NaN rows are dropped from the training matrices.
    with pytest.warns(MissingValuesWarning) as record:
        executed = assistant.forecast(**kwargs)

    assert "Series 'item_2' is incomplete" in {
        str(warning.message).split(".")[0] for warning in record
    }
    assert executed.profile.data_profile.has_gaps is True
    standalone = _run_standalone(code, tmp_path)
    np.testing.assert_allclose(
        standalone["pred"].to_numpy(), executed.predictions["pred"].to_numpy(),
        rtol=1e-6,
    )


def test_standalone_script_matches_forecast_when_csv_last_window_has_missing_value(
    tmp_path,
):
    """
    Test that a CSV of h2o with an empty target cell that lag 13 reads
    (2007-06-01) gives, with LightGBM, the warning of the last window and
    the predictions of the script run as a file: the check does not change
    what runs.
    """
    data = df_h2o.copy()
    data.iloc[-13, 0] = np.nan
    csv_path = tmp_path / "h2o.csv"
    data.to_csv(csv_path)
    assistant = ForecastingAssistant()
    kwargs = {"data": csv_path, "target": "x", "steps": 3, "estimator": "LGBMRegressor"}

    # skforecast warns about the missing value when the lags are selected.
    with pytest.warns(MissingValuesWarning):
        code = assistant.forecast_code(**kwargs).code
    with pytest.warns(MissingValuesWarning):
        with pytest.warns(
            UserWarning, match=re.escape("reads missing values of the target")
        ):
            executed = assistant.forecast(**kwargs)

    np.testing.assert_allclose(
        executed.predictions["pred"].to_numpy(),
        [0.970301079342671, 0.9582311356017825, 1.0445571101106315],
        rtol=1e-6,
    )
    _assert_same_predictions(_run_standalone(code, tmp_path), executed.predictions)


def test_standalone_script_of_forecast_and_backtest_loads_csv_path_that_ran(
    tmp_path,
):
    """
    Test that the scripts returned by forecast() and backtest() themselves
    (not only by forecast_code() and backtest_code()) load the CSV path
    they ran on and, run as files from another directory, give the same
    predictions.
    """
    csv_path = tmp_path / "sales.csv"
    df_single.to_csv(csv_path, index=False)
    workdir = tmp_path / "elsewhere"
    workdir.mkdir()
    assistant = ForecastingAssistant()
    kwargs = dict(data=csv_path, target="sales", date_column="date")

    forecast = assistant.forecast(**kwargs, steps=5, test_size=5)
    backtest = assistant.backtest(
        **kwargs, cv=TimeSeriesFold(steps=5, initial_train_size=60),
        show_progress=False,
    )

    _assert_same_predictions(_run_standalone(forecast.code, workdir), forecast.predictions)
    np.testing.assert_allclose(
        _run_standalone(backtest.code, workdir)["pred"].to_numpy(),
        backtest.predictions["pred"].to_numpy(),
        rtol=1e-6,
    )


def test_standalone_script_matches_forecast_when_csv_has_no_dates(tmp_path):
    """
    Test that a CSV without dates (a row index) is read by the script as
    forecast() reads it: its first column stays a data column instead of
    becoming the index, and the predictions match.
    """
    csv_path = tmp_path / "h2o.csv"
    df_h2o.reset_index(drop=True).to_csv(csv_path, index=False)
    assistant = ForecastingAssistant()

    executed = assistant.forecast(data=csv_path, target="x", steps=6)

    assert f"data = pd.read_csv({str(csv_path)!r})\n" in executed.code
    standalone = _run_standalone(executed.code, tmp_path)
    np.testing.assert_allclose(
        standalone["pred"].to_numpy(), executed.predictions["pred"].to_numpy(),
        rtol=1e-6,
    )


def test_standalone_script_matches_forecast_when_long_format_future_exog(tmp_path):
    """
    Test that, with long-format data and exogenous variables, the script
    run as a file parses the dates of `exog_future.csv` and gives the
    predictions of forecast() with the same future values (before, the
    dates stayed text and the predictions used missing exogenous values).
    """
    data = df_items_sales_long.copy()
    day = data["date"].dt.day
    data["promo"] = ((day + data["series"].str[-1].astype(int)) % 5 == 0).astype(float)
    last_dates = sorted(data["date"].unique())[-7:]
    history = data[~data["date"].isin(last_dates)]
    exog_future = data[data["date"].isin(last_dates)][["date", "series", "promo"]]
    csv_path = tmp_path / "items.csv"
    history.to_csv(csv_path, index=False)
    exog_future.to_csv(tmp_path / "exog_future.csv", index=False)
    assistant = ForecastingAssistant()

    executed = assistant.forecast(
        data=csv_path, target="value", date_column="date",
        series_id_column="series", steps=7, exog=exog_future,
    )

    assert executed.plan.use_exog is True
    assert "exog_future['date'] = pd.to_datetime(exog_future['date'])" in executed.code
    standalone = _run_standalone(executed.code, tmp_path)
    assert list(standalone["level"]) == list(executed.predictions["level"])
    np.testing.assert_allclose(
        standalone["pred"].to_numpy(), executed.predictions["pred"].to_numpy(),
        rtol=1e-6,
    )


def test_standalone_script_matches_forecast_when_long_format_multiindex(tmp_path):
    """
    Test that the script of long-format data passed in memory indexed by a
    (series, date) MultiIndex, with the future exogenous variables indexed
    the same way, runs as a file on the frames saved with `to_csv()` and
    gives the predictions of forecast(): `to_csv()` writes the levels as
    columns, which is how forecast() runs the data. Before, forecast() failed
    because the executed script did not find the date column.
    """
    data = data_long.set_index(["series", "date"])
    exog = exog_long.set_index(["series", "date"])
    executed = ForecastingAssistant().forecast(
        data=data, target="value", steps=7, estimator="Ridge", exog=exog
    )
    data.to_csv(tmp_path / "data.csv")
    exog.to_csv(tmp_path / "exog_future.csv")

    assert executed.plan.use_exog is True
    standalone = _run_standalone(executed.code, tmp_path)
    assert list(standalone["level"]) == list(executed.predictions["level"])
    np.testing.assert_allclose(
        standalone["pred"].to_numpy(), executed.predictions["pred"].to_numpy(),
        rtol=1e-6,
    )


_N_RANGE = 120
_y_range = 10.0 + np.sin(np.arange(_N_RANGE) / 4)


@pytest.mark.parametrize(
    "data, target, kwargs",
    [
        (pd.DataFrame({"y": _y_range}), "y", {}),
        (
            pd.DataFrame({"y": _y_range}, index=pd.RangeIndex(50, 50 + _N_RANGE)),
            "y", {},
        ),
        (pd.DataFrame({"a": _y_range, "b": 2 * _y_range}), ["a", "b"], {}),
        (
            pd.DataFrame({"a": _y_range, "b": 2 * _y_range}), ["a", "b"],
            {"forecaster": "ForecasterDirectMultiVariate"},
        ),
        (
            pd.DataFrame({"y": _y_range, "x": np.cos(np.arange(_N_RANGE))}), "y",
            {"exog": pd.DataFrame(
                {"x": np.cos(np.arange(_N_RANGE, _N_RANGE + 5))},
                index=pd.RangeIndex(_N_RANGE, _N_RANGE + 5),
            )},
        ),
    ],
    ids=["single", "offset_index", "multi_series", "multivariate", "future_exog"],
)
def test_standalone_script_matches_forecast_when_in_memory_data_has_no_dates(
    tmp_path, data, target, kwargs
):
    """
    Test that the script of data passed in memory without dates (a
    RangeIndex), saved with `to_csv()`, runs as a file and gives the
    predictions and positions of forecast(): the row index read back from
    the CSV is turned into the RangeIndex skforecast requires, for the data
    and for `exog_future.csv`. Before, every one of these scripts failed
    with an unsupported index type.
    """
    executed = ForecastingAssistant().forecast(
        data=data, target=target, steps=5, **kwargs
    )
    data.to_csv(tmp_path / "data.csv")
    if "exog" in kwargs:
        kwargs["exog"].to_csv(tmp_path / "exog_future.csv")

    assert "data.index = pd.RangeIndex(data.index[0], data.index[0] + len(data))" in (
        executed.code
    )
    standalone = _run_standalone(executed.code, tmp_path)
    np.testing.assert_allclose(
        standalone["pred"].to_numpy(), executed.predictions["pred"].to_numpy(),
        rtol=1e-6,
    )
    # `_run_standalone` parses the index as dates; integers come back as
    # nanoseconds from the epoch.
    assert list(standalone.index.asi8) == list(executed.predictions.index)


def test_standalone_scripts_match_forecast_and_backtest_when_metric_override(
    tmp_path,
):
    """
    Test that, with metrics chosen through `metric`, the scripts of
    forecast_code() (evaluation mode) and backtest_code() run as files and
    give the predictions of forecast() and backtest(), whose metrics are
    the ones chosen.
    """
    csv_path = tmp_path / "sales.csv"
    df_single.to_csv(csv_path, index=False)
    assistant = ForecastingAssistant()
    metric = ["mean_squared_error", "median_absolute_error"]
    cv = TimeSeriesFold(steps=5, initial_train_size=60, refit=False)
    inputs = {"data": csv_path, "target": "sales", "date_column": "date"}

    forecast_code = assistant.forecast_code(
        **inputs, steps=5, test_size=5, metric=metric
    ).code
    forecast = assistant.forecast(**inputs, steps=5, test_size=5, metric=metric)
    backtest_code = assistant.backtest_code(**inputs, cv=cv, metric=metric).code
    backtest = assistant.backtest(**inputs, cv=cv, metric=metric, show_progress=False)

    assert forecast_code == forecast.code
    assert backtest_code == backtest.code
    assert list(forecast.metrics.columns) == ["series", "MSE", "MedAE"]
    assert list(backtest.metrics.columns) == metric
    _assert_same_predictions(_run_standalone(forecast_code, tmp_path), forecast.predictions)
    np.testing.assert_allclose(
        _run_standalone(backtest_code, tmp_path)["pred"].to_numpy(),
        backtest.predictions["pred"].to_numpy(),
        rtol=1e-6,
    )


@pytest.mark.parametrize(
    "frame, target, forecaster",
    [
        (df_single, "sales", "ForecasterRecursive"),
        (
            df_multi_wide.assign(promo=np.arange(len(df_multi_wide)) % 7),
            ["series_a", "series_b"],
            "ForecasterDirectMultiVariate",
        ),
    ],
    ids=["single series", "multivariate"],
)
def test_standalone_scripts_match_forecast_and_backtest_when_exog_not_used(
    tmp_path, frame, target, forecaster
):
    """
    Test that, with `use_exog=False` on data with exogenous columns, the
    scripts of forecast_code() (evaluation mode) and backtest_code() run as
    files and give the predictions of forecast() and backtest(); the
    multivariate script fits only the target series.
    """
    csv_path = tmp_path / "data.csv"
    frame.to_csv(csv_path, index=False)
    assistant = ForecastingAssistant()
    cv = TimeSeriesFold(steps=5, initial_train_size=60, refit=False)
    inputs = {
        "data": csv_path, "target": target, "date_column": "date",
        "forecaster": forecaster, "use_exog": False,
    }

    forecast = assistant.forecast(**inputs, steps=5, test_size=5)
    backtest = assistant.backtest(**inputs, cv=cv, show_progress=False)

    assert forecast.code == assistant.forecast_code(**inputs, steps=5, test_size=5).code
    assert backtest.code == assistant.backtest_code(**inputs, cv=cv).code
    assert "promo" not in forecast.code.split("# Create forecaster")[1]
    _assert_same_predictions(_run_standalone(forecast.code, tmp_path), forecast.predictions)
    np.testing.assert_allclose(
        _run_standalone(backtest.code, tmp_path)["pred"].to_numpy(),
        backtest.predictions["pred"].to_numpy(),
        rtol=1e-6,
    )


def test_standalone_scripts_match_forecast_and_backtest_when_differentiation(
    tmp_path,
):
    """
    Test that, with `differentiation=1`, the scripts of forecast_code()
    and backtest_code() (with the strategy of create_cv(), which carries
    the order) run as files and give the predictions of forecast() and
    backtest().
    """
    csv_path = tmp_path / "h2o.csv"
    df_h2o.reset_index().to_csv(csv_path, index=False)
    assistant = ForecastingAssistant()
    profile = assistant.profile(csv_path, target="x")
    plan = assistant.plan(profile, steps=12, differentiation=1)
    cv = assistant.create_cv(profile, plan)

    forecast = assistant.forecast(csv_path, profile=profile, plan=plan)
    backtest = assistant.backtest(
        csv_path, cv=cv, profile=profile, show_progress=False
    )

    assert forecast.code == assistant.forecast_code(profile=profile, plan=plan).code
    assert backtest.code == assistant.backtest_code(
        csv_path, cv=cv, profile=profile
    ).code
    assert "    differentiation    = 1,\n" in backtest.code
    _assert_same_predictions(_run_standalone(forecast.code, tmp_path), forecast.predictions)
    np.testing.assert_allclose(
        _run_standalone(backtest.code, tmp_path)["pred"].to_numpy(),
        backtest.predictions["pred"].to_numpy(),
        rtol=1e-6,
    )


@pytest.mark.parametrize(
    "frame, target",
    [
        (df_single, "sales"),
        (df_multi_wide, ["series_a", "series_b"]),
    ],
    ids=["single series", "multi-series wide"],
)
def test_standalone_scripts_match_forecast_and_backtest_when_feature_overrides(
    tmp_path, frame, target
):
    """
    Test that, with `calendar_features`, `target_transformer` and
    `dropna_from_series` chosen, the scripts of forecast_code() (evaluation
    mode) and backtest_code() run as files and give the predictions of
    forecast() and backtest().
    """
    csv_path = tmp_path / "data.csv"
    frame.to_csv(csv_path, index=False)
    assistant = ForecastingAssistant()
    cv = TimeSeriesFold(steps=5, initial_train_size=60, refit=False)
    inputs = {
        "data": csv_path, "target": target, "date_column": "date",
        "estimator": "Ridge", "calendar_features": ["month", "day_of_week"],
        "target_transformer": "none", "dropna_from_series": True,
    }

    forecast = assistant.forecast(**inputs, steps=5, test_size=5)
    backtest = assistant.backtest(**inputs, cv=cv, show_progress=False)

    assert forecast.code == assistant.forecast_code(**inputs, steps=5, test_size=5).code
    assert backtest.code == assistant.backtest_code(**inputs, cv=cv).code
    assert "transformer_" not in forecast.code.replace("transformer_exog", "")
    standalone = _run_standalone(forecast.code, tmp_path)
    np.testing.assert_allclose(
        standalone["pred"].to_numpy(), forecast.predictions["pred"].to_numpy(),
        rtol=1e-6,
    )
    np.testing.assert_allclose(
        _run_standalone(backtest.code, tmp_path)["pred"].to_numpy(),
        backtest.predictions["pred"].to_numpy(),
        rtol=1e-6,
    )


@pytest.mark.parametrize(
    "frame, target, exog_columns, forecaster",
    [
        (
            df_single.assign(noise=np.arange(len(df_single)) % 3),
            "sales",
            ["promo"],
            "ForecasterRecursive",
        ),
        (
            df_multi_wide.assign(promo=np.arange(len(df_multi_wide)) % 7),
            ["series_a", "series_b"],
            [],
            "ForecasterDirectMultiVariate",
        ),
    ],
    ids=["single series", "multivariate"],
)
def test_standalone_scripts_match_forecast_and_backtest_when_exog_columns(
    tmp_path, frame, target, exog_columns, forecaster
):
    """
    Test that, with a profile built with `exog_columns`, the scripts of
    forecast_code() (evaluation mode) and backtest_code() run as files on
    the whole CSV and give the predictions of forecast() and backtest(),
    which are those of the data without the columns left out.
    """
    csv_path = tmp_path / "data.csv"
    frame.to_csv(csv_path, index=False)
    assistant = ForecastingAssistant()
    cv = TimeSeriesFold(steps=5, initial_train_size=60, refit=False)
    profile = assistant.profile(
        data         = csv_path,
        target       = target,
        date_column  = "date",
        exog_columns = exog_columns,
    )
    plan = assistant.plan(profile=profile, steps=5, forecaster=forecaster)
    unused = profile.data_profile.unused_columns
    reference = assistant.profile(
        data        = frame.drop(columns=unused),
        target      = target,
        date_column = "date",
    )
    reference_plan = assistant.plan(profile=reference, steps=5, forecaster=forecaster)

    forecast = assistant.forecast(
        data      = csv_path,
        profile   = profile,
        plan      = plan,
        test_size = 5,
    )
    backtest = assistant.backtest(
        data          = csv_path,
        profile       = profile,
        plan          = plan,
        cv            = cv,
        show_progress = False,
    )
    expected = assistant.forecast(
        data      = frame.drop(columns=unused),
        profile   = reference,
        plan      = reference_plan,
        test_size = 5,
    )
    forecast_code = assistant.forecast_code(
        data      = csv_path,
        profile   = profile,
        plan      = plan,
        test_size = 5,
    )
    backtest_code = assistant.backtest_code(
        data    = csv_path,
        profile = profile,
        plan    = plan,
        cv      = cv,
    )

    assert unused != []
    assert forecast.code == forecast_code.code
    assert backtest.code == backtest_code.code
    pd.testing.assert_frame_equal(forecast.predictions, expected.predictions)
    _assert_same_predictions(
        _run_standalone(forecast.code, tmp_path), forecast.predictions
    )
    np.testing.assert_allclose(
        _run_standalone(backtest.code, tmp_path)["pred"].to_numpy(),
        backtest.predictions["pred"].to_numpy(),
        rtol=1e-6,
    )


def test_standalone_backtesting_script_matches_backtest_when_csv_dates_in_utc(
    tmp_path,
):
    """
    Test that the backtesting script of a CSV whose dates are in UTC, with
    the default strategy of create_cv() (a date without time zone, which
    the script gets as its number of observations), runs as a file and
    gives the predictions of backtest().
    """
    csv_path = tmp_path / "utc.csv"
    df_h2o.set_axis(df_h2o.index.tz_localize("UTC")).rename_axis(
        "date"
    ).reset_index().to_csv(csv_path, index=False)
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=csv_path, target="x")
    plan = assistant.plan(profile, steps=12)
    cv = assistant.create_cv(profile, plan)

    backtest = assistant.backtest(
        data          = csv_path,
        cv            = cv,
        profile       = profile,
        plan          = plan,
        show_progress = False,
    )

    np.testing.assert_allclose(
        _run_standalone(backtest.code, tmp_path)["pred"].to_numpy(),
        backtest.predictions["pred"].to_numpy(),
        rtol=1e-6,
    )


def test_standalone_script_matches_forecast_when_long_series_start_on_different_dates(
    tmp_path,
):
    """
    Test that the evaluation script of long data whose series start on
    different dates, with `test_size`, runs as a file and gives the
    predictions of forecast(), with the training set ending inside the data.
    """
    csv_path = tmp_path / "staggered.csv"
    df_multi_long_staggered.to_csv(csv_path, index=False)
    assistant = ForecastingAssistant()
    inputs = {
        "data": csv_path, "target": "value", "date_column": "date",
        "series_id_column": "series_id",
    }

    forecast = assistant.forecast(**inputs, steps=5, test_size=5)
    standalone = _run_standalone(forecast.code, tmp_path)

    assert forecast.plan.end_train == "2023-04-05"
    np.testing.assert_allclose(
        standalone["pred"].to_numpy(),
        forecast.predictions["pred"].to_numpy(),
        rtol=1e-6,
    )


@pytest.mark.parametrize(
    "name, fragment",
    [
        ("semicolon_comma", "sep=';', decimal=','"),
        ("tab_dot", "sep='\\t', decimal='.'"),
        ("gz_semicolon_comma", "sep=';', decimal=','"),
    ],
)
def test_standalone_script_matches_forecast_when_csv_has_another_dialect(
    tmp_path, name, fragment
):
    """
    Test that the script of a CSV with ';' and a decimal comma, tabulators,
    or gzip, run as a real file, reads it with its dialect and yields the
    same predictions as forecast().
    """
    csv_path = write_dialect(tmp_path, df_dialect, name)
    assistant = ForecastingAssistant()

    code = assistant.forecast_code(data=csv_path, target="y", steps=5).code
    executed = assistant.forecast(data=csv_path, target="y", steps=5)

    assert fragment in code
    _assert_same_predictions(_run_standalone(code, tmp_path), executed.predictions)


def test_standalone_backtesting_script_matches_backtest_when_csv_has_another_dialect(
    tmp_path,
):
    """
    Test that the backtesting script of a CSV with ';' and a decimal comma,
    run as a real file, yields the same predictions as backtest().
    """
    csv_path = write_dialect(tmp_path, df_dialect, "semicolon_comma")
    cv = TimeSeriesFold(steps=5, initial_train_size=40, verbose=False)
    assistant = ForecastingAssistant()

    result = assistant.backtest(
        data=csv_path, cv=cv, target="y", estimator="Ridge", show_progress=False
    )

    assert "sep=';', decimal=','" in result.code
    _assert_same_predictions(
        _run_standalone(result.code, tmp_path), result.predictions
    )


def test_forecast_gives_equal_predictions_when_same_data_in_semicolon_and_comma_csv(
    tmp_path,
):
    """
    Test that forecast() on a ';' file with a decimal comma and on the same
    data written with commas gives equal predictions.
    """
    semicolon_path = write_dialect(tmp_path, df_dialect, "semicolon_comma")
    comma_path = tmp_path / "us.csv"
    df_dialect.to_csv(comma_path, index=False)
    assistant = ForecastingAssistant()

    result = assistant.forecast(data=semicolon_path, target="y", steps=5)
    expected = assistant.forecast(data=comma_path, target="y", steps=5)

    pd.testing.assert_frame_equal(result.predictions, expected.predictions)


@pytest.mark.parametrize(
    "decimals",
    [True, False],
    ids=["thousands and decimal comma", "whole numbers with and without separator"],
)
def test_standalone_script_matches_forecast_when_csv_separates_thousands(
    tmp_path, decimals
):
    """
    Test that the script of a ';' file with '.' between thousands ('1.020,50'
    or '870' next to '1.020'), run as a real file, reads it with
    `thousands='.'` and yields the same predictions as forecast(), which
    are those of the same amounts written with ',' and '.'.
    """
    csv_path = write_thousands(tmp_path, df_dialect_thousands, decimals=decimals)
    comma_path = tmp_path / "us.csv"
    df_dialect_thousands.assign(
        y=df_dialect_thousands["y"] if decimals else df_dialect_thousands["y"].round()
    ).to_csv(comma_path, index=False)
    assistant = ForecastingAssistant()

    code = assistant.forecast_code(data=csv_path, target="y", steps=5).code
    executed = assistant.forecast(data=csv_path, target="y", steps=5)
    expected = assistant.forecast(data=str(comma_path), target="y", steps=5)

    assert (
        f"data = pd.read_csv({csv_path!r}, sep=';', decimal=',', thousands='.', "
        f"dtype={{'date': str}})\n"
        in code
    )
    _assert_same_predictions(_run_standalone(code, tmp_path), executed.predictions)
    pd.testing.assert_frame_equal(executed.predictions, expected.predictions)


@pytest.mark.parametrize(
    "data, levels",
    [
        ("csv", ["001", "1", "10"]),
        (df_multi_long_numeric_ids, ["001", "1", "10"]),
        (df_multi_long_integer_ids, ["1", "10", "2"]),
    ],
    ids=["csv path", "dataframe with text ids", "dataframe with integer ids"],
)
def test_standalone_script_matches_forecast_when_series_ids_are_numbers(
    tmp_path, data, levels
):
    """
    Test that the script of long-format data whose series ids are numbers
    ('001', '1', '10'), run as a file, reads them as text, turns them into
    text again before the reshape (data passed in memory does not run the
    loading) and gives the predictions of forecast(), with the series named
    as in the file: '001' keeps its zeros and is not the series '1'. Before,
    every run failed inside skforecast with `KeyError: 1` (skforecast issue
    #1357).
    """
    if isinstance(data, str):
        data = tmp_path / "series.csv"
        df_multi_long_numeric_ids.to_csv(data, index=False)
        path = str(data)
    else:
        data.to_csv(tmp_path / "data.csv", index=False)
        path = "data.csv"
    assistant = ForecastingAssistant()
    kwargs = dict(
        data=data, target="value", date_column="date",
        series_id_column="series_id", steps=5, test_size=5,
    )

    code = assistant.forecast_code(**kwargs).code
    executed = assistant.forecast(**kwargs)

    assert code == executed.code
    assert f"data = pd.read_csv({path!r}, dtype={{'series_id': str}})\n" in code
    assert (
        "data['series_id'] = data['series_id'].map(str, na_action='ignore')\n"
        in code
    )
    assert sorted(executed.predictions["level"].unique()) == levels
    assert sorted(executed.metrics["series"]) == levels
    standalone = _run_standalone(code, tmp_path)
    assert list(standalone["level"]) == list(executed.predictions["level"])
    np.testing.assert_allclose(
        standalone["pred"].to_numpy(), executed.predictions["pred"].to_numpy(),
        rtol=1e-6,
    )


def test_standalone_backtesting_script_matches_backtest_when_series_ids_are_numbers(
    tmp_path,
):
    """
    Test that the backtesting script of long-format data whose series ids are
    numbers ('001', '1', '10'), run as a file, gives the backtest
    predictions of backtest(), with the series named as in the file.
    """
    csv_path = tmp_path / "series.csv"
    df_multi_long_numeric_ids.to_csv(csv_path, index=False)
    assistant = ForecastingAssistant()
    cv = TimeSeriesFold(steps=5, initial_train_size=80, refit=False)
    kwargs = dict(
        data=csv_path, target="value", date_column="date",
        series_id_column="series_id", cv=cv,
    )

    code = assistant.backtest_code(**kwargs).code
    executed = assistant.backtest(**kwargs, show_progress=False)

    assert sorted(executed.predictions["level"].unique()) == ["001", "1", "10"]
    standalone = _run_standalone(code, tmp_path)
    assert list(standalone["level"]) == list(executed.predictions["level"])
    np.testing.assert_allclose(
        standalone["pred"].to_numpy(), executed.predictions["pred"].to_numpy(),
        rtol=1e-6,
    )


def test_standalone_script_matches_forecast_when_series_ids_and_thousands(tmp_path):
    """
    Test that the script of a ';' file of long-format data with '.' between
    thousands ('1.020,50') and series ids that are numbers ('001', '1',
    '10'), run as a file, reads the ids as text after the dialect, so the
    thousands separator does not touch them, and yields the predictions of
    forecast(), which are those of the same data written with ',' and '.'.
    """
    csv_path = write_thousands(
        tmp_path, df_dialect_thousands_long, series_id_column="store"
    )
    comma_path = tmp_path / "us.csv"
    df_dialect_thousands_long[["store", "date", "y"]].to_csv(comma_path, index=False)
    assistant = ForecastingAssistant()
    kwargs = dict(target="y", series_id_column="store", steps=6, test_size=6)

    executed = assistant.forecast(data=csv_path, **kwargs)
    expected = assistant.forecast(data=str(comma_path), **kwargs)

    assert (
        f"data = pd.read_csv({csv_path!r}, sep=';', decimal=',', thousands='.', "
        f"dtype={{'store': str, 'date': str}})\n"
    ) in executed.code
    assert sorted(executed.predictions["level"].unique()) == ["001", "1", "10"]
    _assert_same_predictions(_run_standalone(executed.code, tmp_path), executed.predictions)
    pd.testing.assert_frame_equal(executed.predictions, expected.predictions)


@pytest.mark.parametrize("name", ["ventas.csv", "ventas.csv.gz"], ids=["plain", "gzip"])
def test_standalone_script_matches_forecast_when_csv_and_future_exog_are_cp1252(
    tmp_path, name
):
    """
    Test that the CSV that Excel saves on Windows in Spanish (cp1252, ';',
    ',' as decimal mark, dates day first, 'año' as target and accents in the
    categories of 'zona') and future values saved by Excel in cp1252 with
    ',' are read as cp1252 by the library and by the script run as a file
    with that file as `exog_future.csv`, also with the data compressed: the
    script names `encoding='cp1252'` in both reads, and the predictions are
    those of the same files written in UTF-8.
    """
    csv_path = write_cp1252(tmp_path, name=name)
    write_cp1252(
        tmp_path, df_dialect_cp1252_exog, name="exog_future.csv", sep=",", decimal="."
    )
    utf8_path = tmp_path / "utf8.csv"
    df_dialect_cp1252.to_csv(utf8_path, index=False, sep=";", decimal=",")
    assistant = ForecastingAssistant()

    profile = assistant.profile(data=csv_path, target="año")
    with pytest.warns(UserWarning, match="it was read as cp1252"):
        exog = load_exog(
            tmp_path / "exog_future.csv",
            date_column = "fecha",
            date_format = profile.data_profile.date_format,
        )
    executed = assistant.forecast(
        data=csv_path, steps=10, profile=profile, estimator="Ridge", exog=exog
    )
    # The same future values as a frame not read from a file.
    future = exog.copy()
    future.attrs = {}
    expected = assistant.forecast(
        data=utf8_path, target="año", steps=10, estimator="Ridge", exog=future
    )

    assert profile.data_profile.csv_encoding == "cp1252"
    assert (
        f"data = pd.read_csv({csv_path!r}, sep=';', decimal=',', "
        f"encoding='cp1252')\n" in executed.code
    )
    assert (
        "exog_future = pd.read_csv('exog_future.csv', encoding='cp1252')\n"
        in executed.code
    )
    assert "encoding='cp1252'" not in expected.code
    pd.testing.assert_frame_equal(executed.predictions, expected.predictions)
    _assert_same_predictions(
        _run_standalone(executed.code, tmp_path), executed.predictions
    )
