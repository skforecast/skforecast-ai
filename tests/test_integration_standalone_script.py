# Integration test: the standalone script reproduces the executed workflow

import subprocess
import sys
import textwrap

import numpy as np
import pandas as pd

from skforecast.model_selection import TimeSeriesFold

from skforecast_ai import ForecastingAssistant

from tests.fixtures_assistant import df_multi_long, df_multi_wide, df_no_exog, df_single


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
