# Unit test cli skforecast_ai

import ast
import io
import json
import re
import warnings

import numpy as np
import pandas as pd
import pytest
import typer
from typer.testing import CliRunner
from skforecast.exceptions.exceptions import rich_warning_handler

from skforecast_ai.cli import (
    app,
    _parse_decisions,
    _parse_exog_columns,
    _parse_initial_train_size,
    _parse_lags,
    _report_error,
    _showwarning_to_stderr,
)
from skforecast_ai.exceptions import ForecastExecutionError
from skforecast_ai.assistant import ForecastingAssistant

from .fixtures_assistant import (
    df_categorical_exog,
    df_multi_long,
    df_multi_wide,
    df_single,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# _parse_lags helper
# ---------------------------------------------------------------------------


class TestParseLags:
    """Tests for the `_parse_lags` CLI helper."""

    def test_parse_lags_output_when_none(self):
        assert _parse_lags(None) is None

    def test_parse_lags_output_when_single_int(self):
        assert _parse_lags("7") == 7

    def test_parse_lags_output_when_list(self):
        assert _parse_lags("1,2,3") == [1, 2, 3]

    def test_parse_lags_BadParameter_when_not_int(self):
        with pytest.raises(typer.BadParameter):
            _parse_lags("1,x,3")

    def test_parse_lags_BadParameter_when_non_positive(self):
        with pytest.raises(typer.BadParameter, match="positive integers"):
            _parse_lags("0,1,2")

    def test_parse_lags_BadParameter_when_duplicates(self):
        with pytest.raises(typer.BadParameter, match="must not contain duplicates"):
            _parse_lags("1,2,2")

    def test_parse_lags_output_when_auto(self):
        assert _parse_lags("auto") is None
        assert _parse_lags(" AUTO ") is None


class TestParseInitialTrainSize:
    """Tests for the `_parse_initial_train_size` CLI helper."""

    def test_parse_initial_train_size_output_when_none(self):
        assert _parse_initial_train_size(None) is None

    def test_parse_initial_train_size_output_when_int(self):
        assert _parse_initial_train_size("70") == 70
        assert _parse_initial_train_size(" 70 ") == 70

    def test_parse_initial_train_size_output_when_date(self):
        assert _parse_initial_train_size("2023-03-01") == "2023-03-01"


def _write_csv(tmp_path, df, name="data.csv"):
    """Write a DataFrame to a CSV file in tmp_path and return the path."""
    path = tmp_path / name
    df.to_csv(path, index=False)
    return str(path)


# ---------------------------------------------------------------------------
# profile command
# ---------------------------------------------------------------------------


class TestProfile:
    """Tests for the `profile` CLI command."""

    def test_profile_basic(self, tmp_path):
        """
        Profile command prints table output with forecaster recommendation.
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["profile", csv_path, "--target", "sales", "--date-column", "date", "--quiet"],
        )
        assert result.exit_code == 0
        assert "ForecasterRecursive" in result.output

    def test_profile_json_format(self, tmp_path):
        """
        Profile --format json outputs valid JSON with expected keys.
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["profile", csv_path, "--target", "sales", "--date-column", "date",
             "--format", "json", "--quiet"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "forecaster" in data
        assert "data_profile" in data
        assert "estimator" in data

    def test_profile_missing_file(self):
        """
        Profile with non-existent file shows helpful error.
        """
        result = runner.invoke(
            app,
            ["profile", "nonexistent.csv", "--target", "y"],
        )
        assert result.exit_code == 1
        assert "not found" in result.output.lower() or "error" in result.output.lower()

    def test_profile_invalid_target(self, tmp_path):
        """
        Profile with a column that does not exist raises an error.
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["profile", csv_path, "--target", "nonexistent_col", "--date-column", "date"],
        )
        assert result.exit_code == 1

    def test_profile_multi_series_wide(self, tmp_path):
        """
        Profile with comma-separated targets for wide-format multi-series.
        """
        csv_path = _write_csv(tmp_path, df_multi_wide)
        result = runner.invoke(
            app,
            ["profile", csv_path, "--target", "series_a,series_b",
             "--date-column", "date", "--format", "json", "--quiet"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data_profile"]["n_series"] == 2

    def test_profile_multi_series_long(self, tmp_path):
        """
        Profile with series-id for long-format multi-series.
        """
        csv_path = _write_csv(tmp_path, df_multi_long)
        result = runner.invoke(
            app,
            ["profile", csv_path, "--target", "value",
             "--date-column", "date", "--series-id-column", "series_id",
             "--format", "json", "--quiet"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data_profile"]["n_series"] == 2

    def test_profile_output_to_file(self, tmp_path):
        """
        Profile --output writes JSON to file.
        """
        csv_path = _write_csv(tmp_path, df_single)
        out_path = tmp_path / "profile.json"
        result = runner.invoke(
            app,
            ["profile", csv_path, "--target", "sales", "--date-column", "date",
             "--format", "json", "--output", str(out_path), "--quiet"],
        )
        assert result.exit_code == 0
        assert out_path.exists()
        data = json.loads(out_path.read_text())
        assert "forecaster" in data


# ---------------------------------------------------------------------------
# plan command
# ---------------------------------------------------------------------------


class TestPlan:
    """Tests for the `plan` CLI command."""

    def test_plan_basic(self, tmp_path):
        """
        Plan command prints table output with plan details.
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["plan", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "10", "--quiet"],
        )
        assert result.exit_code == 0
        assert "Forecast Plan" in result.output

    def test_plan_json_format(self, tmp_path):
        """
        Plan --format json outputs valid JSON parseable as ForecastPlan.
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["plan", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "10", "--format", "json", "--quiet"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "profile" in data
        assert "plan" in data
        assert "forecaster" in data["plan"]
        assert data["plan"]["steps"] == 10

    def test_plan_with_interval(self, tmp_path):
        """
        Plan with --interval includes interval in the output.
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["plan", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "10", "--interval", "0.1,0.9", "--format", "json", "--quiet"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["plan"]["interval"] == [0.1, 0.9]
        assert data["plan"]["interval_method"] is not None

    def test_plan_invalid_interval(self, tmp_path):
        """
        Plan with a non-numeric --interval reports the expected format
        instead of a raw conversion error.
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["plan", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "10", "--interval", "low,high"],
        )
        assert result.exit_code != 0
        assert "Interval must be two comma-separated quantiles" in result.output

    def test_plan_missing_steps(self, tmp_path):
        """
        Plan without --steps shows error.
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["plan", csv_path, "--target", "sales", "--date-column", "date"],
        )
        assert result.exit_code != 0

    def test_plan_output_to_file(self, tmp_path):
        """
        Plan --output writes JSON to file.
        """
        csv_path = _write_csv(tmp_path, df_single)
        out_path = tmp_path / "plan.json"
        result = runner.invoke(
            app,
            ["plan", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "10", "--format", "json", "--output", str(out_path), "--quiet"],
        )
        assert result.exit_code == 0
        assert out_path.exists()
        data = json.loads(out_path.read_text())
        assert data["plan"]["steps"] == 10

    def test_plan_with_estimator_kwargs(self, tmp_path):
        """
        Plan with --estimator-kwargs includes hyperparameters in plan output.
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["plan", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "10", "--estimator-kwargs", '{"alpha": 2.0}',
             "--format", "json", "--quiet"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["plan"]["estimator_kwargs"]["alpha"] == 2.0

    def test_plan_json_includes_plan_warnings(self, tmp_path):
        """
        Plan --format json carries the warnings of plan() in
        `plan.warnings`, with the text of the warning emitted.
        """
        csv_path = _write_csv(tmp_path, df_single)
        with pytest.warns(UserWarning, match="not a named parameter"):
            result = runner.invoke(
                app,
                ["plan", csv_path, "--target", "sales", "--date-column", "date",
                 "--steps", "10", "--estimator", "LGBMRegressor",
                 "--estimator-kwargs", '{"n_estimatorz": 10}',
                 "--format", "json", "--quiet"],
            )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["plan"]["warnings"] == [
            "'n_estimatorz' is not a named parameter of LGBMRegressor. It is "
            "passed to the library as an extra parameter, which ignores it "
            "without an error if it does not exist. Did you mean "
            "'n_estimators'?"
        ]

    def test_plan_table_without_plan_warnings_panel(self, tmp_path):
        """
        Plan table output leaves out the "Plan Warnings" panel of the
        display, since the CLI already prints each warning.
        """
        csv_path = _write_csv(tmp_path, df_single)
        with pytest.warns(UserWarning, match="not a named parameter"):
            result = runner.invoke(
                app,
                ["plan", csv_path, "--target", "sales", "--date-column", "date",
                 "--steps", "10", "--estimator", "LGBMRegressor",
                 "--estimator-kwargs", '{"n_estimatorz": 10}', "--quiet"],
            )
        assert result.exit_code == 0
        assert "Forecast Plan" in result.output
        assert "Plan Warnings" not in result.output

    def test_plan_estimator_kwargs_invalid_json(self, tmp_path):
        """
        Plan with invalid JSON in --estimator-kwargs shows error.
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["plan", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "10", "--estimator-kwargs", "not-json", "--quiet"],
        )
        assert result.exit_code != 0
        assert "Invalid JSON" in result.output

    def test_plan_estimator_kwargs_not_dict(self, tmp_path):
        """
        Plan with non-dict JSON in --estimator-kwargs shows error.
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["plan", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "10", "--estimator-kwargs", "[1, 2, 3]", "--quiet"],
        )
        assert result.exit_code != 0
        assert "JSON object" in result.output


# ---------------------------------------------------------------------------
# forecast-code command
# ---------------------------------------------------------------------------


class TestGenerateCode:
    """Tests for the `forecast-code` CLI command."""

    def test_forecast_code_basic(self, tmp_path):
        """
        forecast-code command prints Python code to stdout.
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["forecast-code", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "10", "--quiet"],
        )
        assert result.exit_code == 0
        assert "import" in result.output
        assert "skforecast" in result.output

    def test_forecast_code_json_format(self, tmp_path):
        """
        forecast-code --format json outputs valid JSON with code key.
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["forecast-code", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "10", "--format", "json", "--quiet"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "code" in data
        assert "profile" in data
        assert "plan" in data

    def test_forecast_code_output_to_file(self, tmp_path):
        """
        forecast-code --output writes a valid Python file.
        """
        csv_path = _write_csv(tmp_path, df_single)
        out_path = tmp_path / "script.py"
        result = runner.invoke(
            app,
            ["forecast-code", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "10", "--output", str(out_path), "--quiet"],
        )
        assert result.exit_code == 0
        assert out_path.exists()
        code = out_path.read_text()
        ast.parse(code)

    def test_forecast_code_syntax_valid(self, tmp_path):
        """
        Generated code is syntactically valid Python.
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["forecast-code", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "10", "--format", "json", "--quiet"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        ast.parse(data["code"])

    def test_forecast_code_with_interval(self, tmp_path):
        """
        forecast-code with --interval produces code with prediction intervals.
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["forecast-code", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "10", "--interval", "0.1,0.9", "--format", "json", "--quiet"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "predict_interval" in data["code"] or "interval" in data["code"]

    def test_forecast_code_missing_file(self):
        """
        forecast-code with non-existent file shows helpful error.
        """
        result = runner.invoke(
            app,
            ["forecast-code", "nonexistent.csv", "--target", "y", "--steps", "10"],
        )
        assert result.exit_code == 1

    def test_forecast_code_with_estimator_kwargs(self, tmp_path):
        """
        forecast-code with --estimator-kwargs passes hyperparameters through.
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["forecast-code", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "10", "--estimator-kwargs", '{"alpha": 3.0}',
             "--quiet"],
        )
        assert result.exit_code == 0
        assert "alpha=3.0" in result.output

    @pytest.mark.parametrize("command", ["forecast-code", "backtest-code"])
    def test_code_from_plan_loads_data_argument(self, tmp_path, command):
        """
        forecast-code and backtest-code with --from-plan write into the script
        the DATA argument, the file to run it on, not the file of the bundle:
        forecast-code ignored DATA and wrote the bundle's path, unlike
        backtest-code and the Python API.
        """
        first = _write_csv(tmp_path, df_single, name="first.csv")
        second = _write_csv(tmp_path, df_single, name="second.csv")
        plan_result = runner.invoke(
            app,
            ["plan", first, "--target", "sales", "--date-column", "date",
             "--steps", "5", "--format", "json", "--quiet"],
        )
        assert plan_result.exit_code == 0, plan_result.output
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(plan_result.output)
        output = tmp_path / "script.py"

        result = runner.invoke(
            app,
            [command, second, "--from-plan", str(plan_file),
             "--output", str(output), "--quiet"],
        )

        assert result.exit_code == 0, result.output
        code = output.read_text()
        assert f"pd.read_csv({second!r}" in code
        assert "first.csv" not in code


# ---------------------------------------------------------------------------
# forecast command
# ---------------------------------------------------------------------------


class TestForecast:
    """Tests for the `forecast` CLI command."""

    def test_forecast_basic(self, tmp_path):
        """
        Forecast command prints metrics table with MAE, MSE, MASE.
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["forecast", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "5", "--test-size", "5", "--quiet"],
        )
        assert result.exit_code == 0
        assert "MAE" in result.output
        assert "MSE" in result.output

    def test_forecast_json_format(self, tmp_path):
        """
        Forecast --format json outputs valid JSON with metrics and predictions.
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["forecast", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "5", "--test-size", "5", "--format", "json", "--quiet"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "metrics" in data
        assert "predictions" in data
        assert "code" in data
        assert len(data["predictions"]) == 5

    def test_forecast_output_predictions(self, tmp_path):
        """
        Forecast --output-predictions writes a CSV file with predictions.
        """
        csv_path = _write_csv(tmp_path, df_single)
        preds_path = tmp_path / "preds.csv"
        result = runner.invoke(
            app,
            ["forecast", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "5", "--test-size", "5", "--output-predictions", str(preds_path), "--quiet"],
        )
        assert result.exit_code == 0
        assert preds_path.exists()
        import pandas as pd
        preds_df = pd.read_csv(preds_path)
        assert len(preds_df) == 5

    def test_forecast_output_code(self, tmp_path):
        """
        Forecast --output-code writes a valid Python file.
        """
        csv_path = _write_csv(tmp_path, df_single)
        code_path = tmp_path / "script.py"
        result = runner.invoke(
            app,
            ["forecast", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "5", "--test-size", "5", "--output-code", str(code_path), "--quiet"],
        )
        assert result.exit_code == 0
        assert code_path.exists()
        ast.parse(code_path.read_text())

    def test_forecast_with_interval(self, tmp_path):
        """
        Forecast with --interval includes interval columns in the
        predictions of the JSON output.
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["forecast", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "5", "--test-size", "5", "--interval", "0.1,0.9", "--format", "json", "--quiet"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data["predictions"]) == 5
        assert "lower_bound" in data["predictions"][0]
        assert "upper_bound" in data["predictions"][0]

    def test_forecast_missing_file(self):
        """
        Forecast with non-existent file shows helpful error.
        """
        result = runner.invoke(
            app,
            ["forecast", "nonexistent.csv", "--target", "y", "--steps", "5"],
        )
        assert result.exit_code == 1

    def test_forecast_missing_steps(self, tmp_path):
        """
        Forecast without --steps shows error.
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["forecast", csv_path, "--target", "sales", "--date-column", "date"],
        )
        assert result.exit_code != 0

    def test_forecast_with_estimator_kwargs(self, tmp_path):
        """
        Forecast with --estimator-kwargs passes hyperparameters through.
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["forecast", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "5", "--test-size", "5", "--estimator", "RandomForestRegressor",
             "--estimator-kwargs", '{"n_estimators": 150, "random_state": 123}',
             "--format", "json", "--quiet"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["plan"]["estimator_kwargs"]["n_estimators"] == 150

    def test_forecast_with_test_size(self, tmp_path):
        """
        Forecast --test-size runs in evaluation mode: the data is split and
        metrics (MAE, MSE, MASE) are reported over the test set.
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["forecast", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "5", "--test-size", "5", "--format", "json", "--quiet"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["plan"]["end_train"] is not None
        assert len(data["metrics"]) == 1
        assert "MAE" in data["metrics"][0]
        assert len(data["predictions"]) == 5

    def test_forecast_with_exog(self, tmp_path):
        """
        Forecast --exog forecasts the future (prediction mode): the model is
        trained on all data and predicts the horizon using the supplied
        future exogenous values.
        """
        csv_path = _write_csv(tmp_path, df_single)
        future_dates = pd.date_range("2023-04-11", periods=5, freq="D")
        exog_future = pd.DataFrame(
            {"date": future_dates, "promo": [0.0, 1.0, 0.0, 1.0, 0.0]}
        )
        exog_path = _write_csv(tmp_path, exog_future, name="future_exog.csv")
        result = runner.invoke(
            app,
            ["forecast", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "5", "--exog", exog_path,
             "--format", "json", "--quiet"],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["plan"]["end_train"] is None
        assert len(data["predictions"]) == 5

    def test_forecast_exog_consistent_direct_and_from_plan(self, tmp_path):
        """
        --exog produces identical predictions on the direct path and the
        --from-plan path. Frequency enforcement now happens in the execution
        layer, so both invocations sit the future exog on the same regular
        grid regardless of how the workflow was started.
        """
        csv_path = _write_csv(tmp_path, df_single)
        future_dates = pd.date_range("2023-04-11", periods=5, freq="D")
        exog_future = pd.DataFrame(
            {"date": future_dates, "promo": [0.0, 1.0, 0.0, 1.0, 0.0]}
        )
        exog_path = _write_csv(tmp_path, exog_future, name="future_exog.csv")

        # Direct path.
        direct = runner.invoke(
            app,
            ["forecast", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "5", "--exog", exog_path,
             "--format", "json", "--quiet"],
        )
        assert direct.exit_code == 0, direct.output

        # Build a real plan bundle, then run the --from-plan path.
        plan_result = runner.invoke(
            app,
            ["plan", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "5", "--format", "json", "--quiet"],
        )
        assert plan_result.exit_code == 0, plan_result.output
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(json.loads(plan_result.output)))

        from_plan = runner.invoke(
            app,
            ["forecast", csv_path, "--from-plan", str(plan_file),
             "--exog", exog_path, "--format", "json", "--quiet"],
        )
        assert from_plan.exit_code == 0, from_plan.output

        direct_preds = json.loads(direct.output)["predictions"]
        from_plan_preds = json.loads(from_plan.output)["predictions"]
        assert [p["pred"] for p in direct_preds] == [
            p["pred"] for p in from_plan_preds
        ]

    def test_forecast_exog_dates_not_in_first_column(self, tmp_path):
        """
        --exog reads the dates of a CSV whose first column holds a horizon
        counter: the dates are found as the data loader finds them, and the
        first column is left out, as `index_col=0` took it as the index in
        0.3.1.
        """
        csv_path = _write_csv(tmp_path, df_single)
        future_dates = pd.date_range("2023-04-11", periods=5, freq="D")
        exog_future = pd.DataFrame(
            {"h": range(1, 6), "date": future_dates,
             "promo": [0.0, 1.0, 0.0, 1.0, 0.0]}
        )
        exog_path = _write_csv(tmp_path, exog_future, name="future_exog.csv")
        result = runner.invoke(
            app,
            ["forecast", csv_path, "--target", "sales", "--steps", "5",
             "--exog", exog_path, "--format", "json", "--quiet"],
        )
        assert result.exit_code == 0, result.output
        assert len(json.loads(result.output)["predictions"]) == 5

    def test_forecast_exog_error_when_date_column_missing_from_exog(self, tmp_path):
        """
        --date-column names a column the exog CSV does not have: the error
        names it and lists the columns of the file (it printed only the raw
        KeyError before).
        """
        csv_path = _write_csv(tmp_path, df_single)
        exog_future = pd.DataFrame(
            {"day": pd.date_range("2023-04-11", periods=5), "promo": 0.0}
        )
        exog_path = _write_csv(tmp_path, exog_future, name="future_exog.csv")
        result = runner.invoke(
            app,
            ["forecast", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "5", "--exog", exog_path, "--quiet"],
        )
        assert result.exit_code == 1
        assert (
            "has no column 'date'; its columns are ['day', 'promo']."
            in " ".join(result.output.split())
        )

    def test_forecast_exog_error_when_future_dates_have_gap(self, tmp_path):
        """
        --exog with a date missing from the horizon raises before running,
        with the missing date, instead of forecasting with a missing value.
        """
        csv_path = _write_csv(tmp_path, df_single)
        future_dates = pd.date_range("2023-04-11", periods=6, freq="D").delete(2)
        exog_future = pd.DataFrame(
            {"date": future_dates, "promo": [0.0, 1.0, 0.0, 1.0, 0.0]}
        )
        exog_path = _write_csv(tmp_path, exog_future, name="future_exog.csv")
        result = runner.invoke(
            app,
            ["forecast", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "5", "--exog", exog_path, "--quiet"],
        )
        assert result.exit_code == 1
        assert "`exog` has no row for 1 of the 5 dates to forecast, such as " \
            "2023-04-13." in " ".join(result.output.split())

    def test_forecast_error_when_data_has_final_rows_without_target(self, tmp_path):
        """
        A CSV with future rows appended to carry the exogenous variables (an
        empty target) raises, naming those rows, before --exog is checked: it
        said that the exog started before the first date to forecast.
        """
        future = pd.DataFrame({
            "date": pd.date_range("2023-04-11", periods=5, freq="D"),
            "sales": np.nan,
            "promo": [0.0, 1.0, 0.0, 1.0, 0.0],
        })
        csv_path = _write_csv(tmp_path, pd.concat([df_single, future]))
        exog_path = _write_csv(
            tmp_path, future[["date", "promo"]], name="future_exog.csv"
        )
        result = runner.invoke(
            app,
            ["forecast", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "5", "--exog", exog_path, "--quiet"],
        )
        assert result.exit_code == 1
        assert (
            "The data has no target value after 2023-04-10: drop its last 5 "
            "row(s) (2023-04-11 to 2023-04-15)" in " ".join(result.output.split())
        )



# ---------------------------------------------------------------------------
# ask command
# ---------------------------------------------------------------------------


def _mock_ask_agent(monkeypatch, response_text="This is a test response."):
    """Patch the LLM agent to return a fixed response without API calls."""
    import skforecast_ai.llm.agent as agent_mod

    class _FakeResult:
        output = response_text

    def _mock_create_agent(*args, **kwargs):
        class _FakeAgent:
            async def run(self, msg, **kw):
                return _FakeResult()
        return _FakeAgent()

    monkeypatch.setattr(agent_mod, "create_forecasting_agent", _mock_create_agent)


class TestAsk:
    """Tests for the `ask` CLI command."""

    def test_ask_no_llm_configured_error(self, monkeypatch):
        """
        Ask without LLM configured shows helpful error message.
        """
        monkeypatch.delenv("SKFORECAST_AI_LLM", raising=False)
        monkeypatch.delenv("SKFORECAST_AI_BASE_URL", raising=False)
        result = runner.invoke(
            app,
            ["ask", "What is skforecast?"],
        )
        assert result.exit_code == 1
        assert "no llm configured" in result.output.lower()

    def test_ask_qa_mode_basic(self, monkeypatch):
        """
        Ask in Q&A mode (no data) prints the LLM explanation.
        """
        monkeypatch.delenv("SKFORECAST_AI_LLM", raising=False)
        _mock_ask_agent(monkeypatch, "Skforecast is a Python library.")
        result = runner.invoke(
            app,
            ["ask", "What is skforecast?", "--llm", "openai:fake-model", "--quiet"],
        )
        assert result.exit_code == 0
        assert "Skforecast" in result.output

    def test_ask_with_data(self, tmp_path, monkeypatch):
        """
        Ask with --data triggers profiling and returns explanation.
        """
        monkeypatch.delenv("SKFORECAST_AI_LLM", raising=False)
        _mock_ask_agent(monkeypatch, "The data shows a daily trend.")
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["ask", "What is the best approach?", "--llm", "openai:fake-model",
             "--data", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "10", "--quiet"],
        )
        assert result.exit_code == 0
        assert "daily trend" in result.output.lower()

    def test_ask_json_format(self, monkeypatch):
        """
        Ask --format json outputs valid JSON with explanation key.
        """
        monkeypatch.delenv("SKFORECAST_AI_LLM", raising=False)
        _mock_ask_agent(monkeypatch, "Use ForecasterRecursive for this task.")
        result = runner.invoke(
            app,
            ["ask", "How to forecast?", "--llm", "openai:fake-model",
             "--format", "json", "--quiet"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "explanation" in data
        assert "ForecasterRecursive" in data["explanation"]

    def test_ask_with_data_without_steps(self, tmp_path, monkeypatch):
        """
        Ask with --data and no --steps explains the profile alone.
        """
        monkeypatch.delenv("SKFORECAST_AI_LLM", raising=False)
        _mock_ask_agent(monkeypatch, "A recursive forecaster fits this data.")
        csv_path = _write_csv(tmp_path, df_single)

        result = runner.invoke(
            app,
            ["ask", "Why this forecaster?", "--llm", "openai:fake-model",
             "--data", csv_path, "--target", "sales", "--date-column", "date",
             "--format", "json", "--quiet"],
        )

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["profile"]["forecaster"]
        assert data["plan"] is None

    def test_ask_from_profile(self, tmp_path, monkeypatch):
        """
        Ask --from-profile explains a saved profile without any data.
        """
        monkeypatch.delenv("SKFORECAST_AI_LLM", raising=False)
        _mock_ask_agent(monkeypatch, "Explained from the saved profile.")
        profile = ForecastingAssistant().profile(
            data=df_single, target="sales", date_column="date"
        )
        profile_file = tmp_path / "profile.json"
        profile_file.write_text(json.dumps(profile.model_dump(mode="json")))

        result = runner.invoke(
            app,
            ["ask", "Why this forecaster?", "--llm", "openai:fake-model",
             "--from-profile", str(profile_file), "--format", "json", "--quiet"],
        )

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["profile"]["forecaster"] == profile.forecaster
        assert "saved profile" in data["explanation"]

    def test_ask_llm_failure_exits_with_error(self, monkeypatch):
        """
        A failed LLM call prints an LLM error and exits with code 1
        instead of printing the failure as if it were an answer.
        """
        import skforecast_ai.llm.agent as agent_mod

        monkeypatch.delenv("SKFORECAST_AI_LLM", raising=False)

        def _mock_create_agent(*args, **kwargs):
            class _FailingAgent:
                async def run(self, msg, **kw):
                    raise RuntimeError("Error code: 401 - invalid api key")
            return _FailingAgent()

        monkeypatch.setattr(agent_mod, "create_forecasting_agent", _mock_create_agent)

        result = runner.invoke(
            app,
            ["ask", "What is skforecast?", "--llm", "openai:fake-model", "--quiet"],
        )

        assert result.exit_code == 1
        assert "LLM Error" in result.output
        assert "401" in result.output

    def test_ask_missing_target_with_data(self, tmp_path, monkeypatch):
        """
        Ask with --data but without --target shows error.
        """
        monkeypatch.delenv("SKFORECAST_AI_LLM", raising=False)
        _mock_ask_agent(monkeypatch)
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["ask", "Explain this data", "--llm", "openai:fake-model",
             "--data", csv_path, "--steps", "10", "--quiet"],
        )
        assert result.exit_code == 1

    def test_ask_send_data_from_env_var(self, monkeypatch):
        """
        SKFORECAST_AI_SEND_DATA_TO_LLM env var enables send_data when flag
        is not provided.
        """
        monkeypatch.delenv("SKFORECAST_AI_LLM", raising=False)
        monkeypatch.setenv("SKFORECAST_AI_SEND_DATA_TO_LLM", "true")
        _mock_ask_agent(monkeypatch, "Response with data.")

        captured = {}
        original_init = ForecastingAssistant.__init__

        def _capture_init(self, **kwargs):
            captured.update(kwargs)
            original_init(self, **kwargs)

        monkeypatch.setattr(ForecastingAssistant, "__init__", _capture_init)

        result = runner.invoke(
            app,
            ["ask", "test", "--llm", "openai:fake-model", "--quiet"],
        )
        assert result.exit_code == 0
        assert captured["send_data_to_llm"] is True

    def test_ask_no_send_data_flag_overrides_env_var(self, monkeypatch):
        """
        --no-send-data-to-llm flag overrides env var set to true.
        """
        monkeypatch.delenv("SKFORECAST_AI_LLM", raising=False)
        monkeypatch.setenv("SKFORECAST_AI_SEND_DATA_TO_LLM", "true")
        _mock_ask_agent(monkeypatch, "Response.")

        captured = {}
        original_init = ForecastingAssistant.__init__

        def _capture_init(self, **kwargs):
            captured.update(kwargs)
            original_init(self, **kwargs)

        monkeypatch.setattr(ForecastingAssistant, "__init__", _capture_init)

        result = runner.invoke(
            app,
            ["ask", "test", "--llm", "openai:fake-model",
             "--no-send-data-to-llm", "--quiet"],
        )
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# backtest command
# ---------------------------------------------------------------------------


class TestBacktestCodeCVOptions:
    """Tests for the CV options forwarded by `backtest-code`."""

    def _generate(self, tmp_path, *extra):
        csv_path = _write_csv(tmp_path, df_single)
        out = tmp_path / "script.py"
        result = runner.invoke(
            app,
            ["backtest-code", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "5", "--output", str(out), "--quiet", *extra],
        )
        assert result.exit_code == 0, result.output
        return out.read_text()

    def test_backtest_code_exit_code_1_when_direct_forecaster_with_gap(
        self, tmp_path
    ):
        """
        A direct forecaster with --gap exits with code 1 and the message of
        backtest_code(): the script would fail. The warning of create_cv()
        about the same problem is not shown (warnings are errors here).
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["backtest-code", csv_path, "--target", "sales", "--date-column",
             "date", "--steps", "5", "--forecaster", "ForecasterDirect",
             "--gap", "2", "--quiet"],
        )

        assert result.exit_code == 1
        assert (
            "ForecasterDirect is trained to predict 5 steps, and with `gap=2` "
            "each fold needs steps + gap = 7 steps ahead"
        ) in " ".join(result.output.split())

    def test_backtest_exit_code_1_when_direct_forecaster_with_gap(self, tmp_path):
        """
        `backtest` with a direct forecaster and --gap exits with code 1 and
        the message of backtest(), without the warning of create_cv().
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["backtest", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "5", "--forecaster", "ForecasterDirect", "--gap", "2",
             "--quiet"],
        )

        assert result.exit_code == 1
        assert (
            "ForecasterDirect is trained to predict 5 steps, and with `gap=2` "
            "each fold needs steps + gap = 7 steps ahead"
        ) in " ".join(result.output.split())

    def test_backtest_exit_code_1_when_first_window_shorter_than_forecaster(
        self, tmp_path
    ):
        """
        `backtest` with a horizon that leaves the first training window
        shorter than the window of the forecaster exits with code 1 and the
        message of backtest(), without the warning of create_cv().
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["backtest", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "5", "--lags", "30", "--initial-train-size", "30",
             "--quiet"],
        )

        assert result.exit_code == 1
        assert (
            "The first training window of the strategy has 30 observations, "
            "and ForecasterRecursive needs at least 31 (more than its window "
            "size, 30)"
        ) in " ".join(result.output.split())

    def test_backtest_code_warns_when_first_window_shorter_than_forecaster(
        self, tmp_path
    ):
        """
        `backtest-code` writes the script with the warning of backtest_code()
        that a backtest of it fails (the one of create_cv() is not repeated).
        """
        csv_path = _write_csv(tmp_path, df_single)
        with pytest.warns(UserWarning, match="The first training window"):
            result = runner.invoke(
                app,
                ["backtest-code", csv_path, "--target", "sales", "--date-column",
                 "date", "--steps", "5", "--lags", "30",
                 "--initial-train-size", "30", "--quiet"],
            )

        assert result.exit_code == 0, result.output

    def test_backtest_code_forwards_no_refit(self, tmp_path):
        """
        --no-refit reaches create_cv() and the generated script disables
        refitting; it used to be dropped for matching the CLI default.
        """
        code = self._generate(tmp_path, "--no-refit")
        assert re.search(r"refit\s+= False,", code)

    def test_backtest_code_forwards_fixed_train_size(self, tmp_path):
        """
        --fixed-train-size reaches create_cv() and the generated script uses
        a rolling training window; it used to be dropped for matching the
        CLI default. It is passed with --refit because the training window
        only matters, and is only written, when the model is refitted.
        """
        code = self._generate(tmp_path, "--refit", "--fixed-train-size")
        assert re.search(r"fixed_train_size\s+= True,", code)

    def test_backtest_code_defaults_leave_cv_to_assistant(self, tmp_path):
        """
        Without CV flags the deterministic defaults apply: the model is
        trained once, so the training window is not written.
        """
        code = self._generate(tmp_path)
        assert re.search(r"refit\s+= False,", code)
        assert "fixed_train_size" not in code

    def test_backtest_code_accepts_date_initial_train_size(self, tmp_path):
        """
        --initial-train-size accepts an ISO date, rendered as a quoted
        string in the generated TimeSeriesFold.
        """
        code = self._generate(tmp_path, "--initial-train-size", "2023-03-01")
        assert re.search(r"initial_train_size\s+= '2023-03-01',", code)

    def test_backtest_code_error_when_initial_train_size_date_unparseable(
        self, tmp_path
    ):
        """
        An unparseable --initial-train-size date exits with the create_cv()
        error message instead of a traceback.
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["backtest-code", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "5", "--initial-train-size", "not-a-date", "--quiet"],
        )
        assert result.exit_code == 1
        assert "could not be parsed" in result.output


class TestRefinePlanAuto:
    """Tests for `--lags auto` / `--window-features auto` in `refine-plan`."""

    def test_refine_plan_lags_auto_resets_to_deterministic_selection(self, tmp_path):
        """
        A plan saved with explicit lags is refined with --lags auto and gets
        the deterministic PACF-based lags back, the same ones a plan without
        --lags produces.
        """
        csv_path = _write_csv(tmp_path, df_single)
        base = ["plan", csv_path, "--target", "sales", "--date-column", "date",
                "--steps", "5", "--format", "json", "--quiet"]

        deterministic = runner.invoke(app, base)
        assert deterministic.exit_code == 0, deterministic.output
        deterministic_lags = json.loads(deterministic.output)["plan"]["forecaster_kwargs"]["lags"]

        explicit = runner.invoke(app, [*base, "--lags", "1,2,3"])
        assert explicit.exit_code == 0, explicit.output
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(explicit.output)
        assert json.loads(explicit.output)["plan"]["forecaster_kwargs"]["lags"] == [1, 2, 3]

        refined = runner.invoke(
            app,
            ["refine-plan", "--from-plan", str(plan_file), "--lags", "auto",
             "--format", "json", "--quiet"],
        )
        assert refined.exit_code == 0, refined.output
        refined_lags = json.loads(refined.output)["plan"]["forecaster_kwargs"]["lags"]
        assert refined_lags == deterministic_lags
        assert refined_lags != [1, 2, 3]

    def test_refine_plan_lags_duplicates_rejected(self, tmp_path):
        """
        refine-plan --lags with duplicated values fails at option parsing
        with the shared validation message.
        """
        csv_path = _write_csv(tmp_path, df_single)
        plan_result = runner.invoke(
            app,
            ["plan", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "5", "--format", "json", "--quiet"],
        )
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(plan_result.output)

        result = runner.invoke(
            app,
            ["refine-plan", "--from-plan", str(plan_file), "--lags", "1,2,2",
             "--format", "json", "--quiet"],
        )
        assert result.exit_code != 0
        assert "must not contain duplicates" in result.output


class TestBacktest:
    """Tests for the `backtest` CLI command."""

    def test_backtest_basic(self, tmp_path):
        """
        Backtest command prints metrics table and CV configuration.
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["backtest", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "5", "--quiet"],
        )
        assert result.exit_code == 0
        assert "Backtest Metrics" in result.output
        assert "Cross-Validation Configuration" in result.output

    def test_backtest_json_format(self, tmp_path):
        """
        Backtest --format json outputs valid JSON with expected keys.
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["backtest", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "5", "--format", "json", "--quiet"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "metrics" in data
        assert "predictions" in data
        assert "cv_config" in data
        assert "code" in data
        assert "explanation" in data

    def test_backtest_interval_produces_interval_columns(self, tmp_path):
        """
        Backtest --interval produces prediction interval columns
        (lower_bound/upper_bound) in the JSON predictions output.
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["backtest", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "5", "--interval", "0.1,0.9", "--format", "json", "--quiet"],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        predictions = data["predictions"]
        assert len(predictions) > 0
        assert "lower_bound" in predictions[0]
        assert "upper_bound" in predictions[0]

    def test_backtest_output_predictions(self, tmp_path):
        """
        Backtest --output-predictions writes a CSV file with predictions.
        """
        csv_path = _write_csv(tmp_path, df_single)
        preds_path = tmp_path / "preds.csv"
        result = runner.invoke(
            app,
            ["backtest", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "5", "--output-predictions", str(preds_path), "--quiet"],
        )
        assert result.exit_code == 0
        assert preds_path.exists()
        import pandas as pd
        preds_df = pd.read_csv(preds_path)
        assert len(preds_df) > 0

    def test_backtest_output_code(self, tmp_path):
        """
        Backtest --output-code writes a valid Python file.
        """
        csv_path = _write_csv(tmp_path, df_single)
        code_path = tmp_path / "script.py"
        result = runner.invoke(
            app,
            ["backtest", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "5", "--output-code", str(code_path), "--quiet"],
        )
        assert result.exit_code == 0
        assert code_path.exists()
        ast.parse(code_path.read_text())

    def test_backtest_missing_target_and_steps(self):
        """
        Backtest without --target and --steps shows error.
        """
        result = runner.invoke(
            app,
            ["backtest", "some.csv"],
        )
        assert result.exit_code == 1

    def test_backtest_multi_series_table(self, tmp_path):
        """
        Backtest on wide multi-series renders the metrics table from the
        skforecast `levels` column without a formatting error.
        """
        csv_path = _write_csv(tmp_path, df_multi_wide)
        result = runner.invoke(
            app,
            ["backtest", csv_path, "--target", "series_a,series_b",
             "--date-column", "date", "--steps", "5", "--quiet"],
        )
        assert result.exit_code == 0
        assert "Backtest Metrics" in result.output
        assert "series_a" in result.output
        assert "series_b" in result.output


# ---------------------------------------------------------------------------
# _parse_candidates helper
# ---------------------------------------------------------------------------


class TestParseCandidates:
    """Tests for the `_parse_candidates` CLI helper."""

    def test_parse_candidates_output_when_none(self):
        from skforecast_ai.cli import _parse_candidates

        assert _parse_candidates(None) is None

    def test_parse_candidates_output_when_array_of_pairs(self):
        from skforecast_ai.cli import _parse_candidates

        parsed = _parse_candidates(
            '[["rec", {"forecaster": "ForecasterRecursive"}]]'
        )
        assert parsed == [("rec", {"forecaster": "ForecasterRecursive"})]

    def test_parse_candidates_output_when_object_mapping(self):
        from skforecast_ai.cli import _parse_candidates

        parsed = _parse_candidates(
            '{"rec": {"forecaster": "ForecasterRecursive"}}'
        )
        assert parsed == [("rec", {"forecaster": "ForecasterRecursive"})]

    def test_parse_candidates_BadParameter_when_invalid_json(self):
        from skforecast_ai.cli import _parse_candidates

        with pytest.raises(typer.BadParameter):
            _parse_candidates("{not json}")

    def test_parse_candidates_BadParameter_when_entry_not_pair(self):
        from skforecast_ai.cli import _parse_candidates

        with pytest.raises(typer.BadParameter, match="name, config"):
            _parse_candidates('[["only_one"]]')


# ---------------------------------------------------------------------------
# compare command
# ---------------------------------------------------------------------------


class TestCompare:
    """Tests for the `compare` CLI command."""

    _candidates = (
        '[["rec", {"forecaster": "ForecasterRecursive"}], '
        '["dir", {"forecaster": "ForecasterDirect", "estimator": "Ridge", '
        '"lags": [1, 2, 3]}]]'
    )

    def test_compare_basic(self, tmp_path):
        """
        Compare command prints the leaderboard and CV configuration.
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["compare", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "5", "--initial-train-size", "70",
             "--candidates", self._candidates, "--quiet"],
        )
        assert result.exit_code == 0, result.output
        assert "Comparison Results" in result.output
        assert "Cross-Validation Configuration" in result.output

    def test_compare_adds_baseline_by_default(self, tmp_path):
        """
        Compare adds the seasonal naive baseline row unless --no-baseline is
        passed.
        """
        csv_path = _write_csv(tmp_path, df_single)
        args = ["compare", csv_path, "--target", "sales", "--date-column", "date",
                "--steps", "5", "--initial-train-size", "70",
                "--candidates", self._candidates, "--format", "json", "--quiet"]

        result = runner.invoke(app, args)
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["baseline_name"] == "Baseline (seasonal naive)"
        assert [row["name"] for row in data["results"]] == [
            "rec", "dir", "Baseline (seasonal naive)"
        ]

        result = runner.invoke(app, [*args, "--no-baseline"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["baseline_name"] is None
        assert [row["name"] for row in data["results"]] == ["rec", "dir"]

    def test_compare_json_format(self, tmp_path):
        """
        Compare --format json outputs valid JSON with expected keys.
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["compare", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "5", "--initial-train-size", "70",
             "--candidates", self._candidates, "--no-baseline",
             "--format", "json", "--quiet"],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "results" in data
        assert "cv_config" in data
        assert "ranking_metric" in data
        assert "candidates" in data
        assert "best_name" in data
        assert "failures" in data
        assert "explanation" in data
        assert len(data["results"]) == 2
        assert data["best_name"] in data["candidates"]

    def test_compare_output_code_writes_winning_script(self, tmp_path):
        """
        Compare --output-code writes the winning configuration's script.
        """
        csv_path = _write_csv(tmp_path, df_single)
        code_path = tmp_path / "best.py"
        result = runner.invoke(
            app,
            ["compare", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "5", "--initial-train-size", "70",
             "--candidates", self._candidates,
             "--output-code", str(code_path), "--quiet"],
        )
        assert result.exit_code == 0, result.output
        assert code_path.exists()
        ast.parse(code_path.read_text())

    def test_compare_output_code_keeps_json_stdout_parseable(self, tmp_path):
        """
        Compare --output-code with --format json writes the confirmation
        message to stderr, so stdout is the JSON document alone and can be
        piped to another command.
        """
        csv_path = _write_csv(tmp_path, df_single)
        code_path = tmp_path / "best.py"
        result = runner.invoke(
            app,
            ["compare", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "5", "--initial-train-size", "70",
             "--candidates", self._candidates,
             "--output-code", str(code_path), "--format", "json", "--quiet"],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert payload["best_name"] in payload["candidates"]
        assert "Code written to" in result.stderr
        assert "Code written to" not in result.stdout

    def test_compare_missing_steps(self, tmp_path):
        """
        Compare without --steps shows an error.
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["compare", csv_path, "--target", "sales", "--date-column", "date"],
        )
        assert result.exit_code == 1

    def test_compare_metric_override(self, tmp_path):
        """
        Compare --metric restricts the ranking to the requested metric.
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["compare", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "5", "--initial-train-size", "70",
             "--candidates", self._candidates,
             "--metric", "mean_absolute_scaled_error",
             "--format", "json", "--quiet"],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["ranking_metric"] == "mean_absolute_scaled_error"


# ---------------------------------------------------------------------------
# Warnings go to stderr
# ---------------------------------------------------------------------------


class TestWarningsToStderr:
    """Tests for the warning handler that the CLI sends to stderr."""

    def test_backtest_json_stdout_parseable_when_skforecast_warning(self, tmp_path):
        """
        A skforecast warning (rich panel printed on stdout by skforecast's own
        handler) goes to stderr with its format, so the JSON document on
        stdout stays parseable.
        """
        csv_path = _write_csv(tmp_path, df_single)
        with warnings.catch_warnings():
            warnings.simplefilter("always")
            warnings.showwarning = rich_warning_handler
            result = runner.invoke(
                app,
                ["backtest", csv_path, "--target", "sales", "--date-column", "date",
                 "--steps", "1", "--initial-train-size", "40", "--refit",
                 "--format", "json", "--quiet"],
            )
            handler_after = warnings.showwarning
        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert "metrics" in payload
        assert "LongTrainingWarning" in result.stderr
        assert "LongTrainingWarning" not in result.stdout
        assert handler_after is rich_warning_handler

    def test_showwarning_to_stderr_keeps_explicit_file(self, capsys):
        """
        A warning shown on an explicit file is written there, not to stderr.
        """
        def file_handler(message, category, filename, lineno, file=None, line=None):
            print(f"shown: {message}", file=file)

        buffer = io.StringIO()
        handler = _showwarning_to_stderr(file_handler)
        handler(UserWarning("to the file"), UserWarning, "f.py", 1, file=buffer)
        captured = capsys.readouterr()
        assert "to the file" in buffer.getvalue()
        assert captured.out == ""
        assert captured.err == ""

    def test_showwarning_to_stderr_sends_stdout_to_stderr(self, capsys):
        """
        A handler that prints on stdout writes to stderr once wrapped.
        """
        def printing_handler(message, category, filename, lineno, file=None, line=None):
            print(f"shown: {message}")

        handler = _showwarning_to_stderr(printing_handler)
        handler(UserWarning("panel"), UserWarning, "f.py", 1)
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == "shown: panel\n"

    def test_main_keeps_handler_when_already_wrapped(self):
        """
        A handler already wrapped (a command invoked from another one) is
        neither wrapped again nor replaced when the command ends.
        """
        wrapped = _showwarning_to_stderr(rich_warning_handler)
        with warnings.catch_warnings():
            warnings.showwarning = wrapped
            result = runner.invoke(app, ["config", "path"])
            assert warnings.showwarning is wrapped
        assert result.exit_code == 0, result.output

    def test_main_leaves_handler_for_mcp(self, monkeypatch):
        """
        The `mcp` command keeps the handler it finds: the server records
        warnings itself in a worker thread.
        """
        seen = {}

        def fake_run_server(**kwargs):
            seen["handler"] = warnings.showwarning

        monkeypatch.setattr("skforecast_ai.mcp.server.run_server", fake_run_server)
        with warnings.catch_warnings():
            warnings.showwarning = rich_warning_handler
            result = runner.invoke(app, ["mcp", "--allow-dir", "/tmp"])
        assert result.exit_code == 0, result.output
        assert seen["handler"] is rich_warning_handler


# ---------------------------------------------------------------------------
# Error contract
# ---------------------------------------------------------------------------


def _write_plan_bundle(tmp_path, csv_path, steps=5):
    """Write the JSON bundle of `plan` for df_single and return its path."""
    result = runner.invoke(
        app,
        ["plan", csv_path, "--target", "sales", "--date-column", "date",
         "--steps", str(steps), "--format", "json", "--quiet"],
    )
    assert result.exit_code == 0, result.output
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(result.stdout)
    return str(plan_file)


class TestErrorContract:
    """Tests for how the CLI reports errors."""

    def test_error_on_stderr_with_brackets_kept(self, tmp_path):
        """
        An error goes to stderr, with text in brackets kept: rich markup
        used to eat `[lower, upper]`.
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["plan", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "5", "--interval", "0.9,0.1", "--quiet"],
        )
        assert result.exit_code == 1
        assert result.stdout == ""
        assert "Error: `interval` must be `[lower, upper]` with 0 < lower" in result.stderr

    def test_error_json_object_on_stderr_when_format_json(self, tmp_path):
        """
        With --format json an error is a JSON object `{"error": {...}}` with
        the fields of `ErrorInfo`, on stderr; stdout stays empty.
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["plan", csv_path, "--target", "missing", "--date-column", "date",
             "--steps", "5", "--format", "json", "--quiet"],
        )
        assert result.exit_code == 1
        assert result.stdout == ""
        payload = json.loads(result.stderr)
        assert list(payload) == ["error"]
        assert set(payload["error"]) == {"code", "message", "field", "hint"}
        assert payload["error"]["code"] == "invalid_argument"
        assert payload["error"]["field"] == "target"

    def test_error_json_when_required_option_missing(self, tmp_path):
        """
        A missing required option is reported like any other error: code 1
        and, with --format json, the JSON object naming the option.
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["plan", csv_path, "--target", "sales", "--date-column", "date",
             "--format", "json", "--quiet"],
        )
        assert result.exit_code == 1
        assert json.loads(result.stderr) == {
            "error": {
                "code": "invalid_argument",
                "message": "--steps is required.",
                "field": "steps",
                "hint": None,
            }
        }

    def test_error_json_when_no_llm(self, monkeypatch):
        """
        Without an LLM, the JSON error carries the CLI message that says how
        to configure one.
        """
        monkeypatch.delenv("SKFORECAST_AI_LLM", raising=False)
        monkeypatch.setattr("skforecast_ai.cli.get_config_value", lambda key: None)
        result = runner.invoke(app, ["ask", "Why?", "--format", "json"])
        assert result.exit_code == 1
        payload = json.loads(result.stderr)["error"]
        assert payload["code"] == "llm_required"
        assert payload["message"] == (
            "No LLM configured. Set the SKFORECAST_AI_LLM environment variable "
            "or use the --llm flag."
        )

    def test_error_json_when_bundle_does_not_validate(self, tmp_path):
        """
        A bundle that does not validate is `invalid_argument` with the tip of
        the text output as `hint`.
        """
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps({"profile": {}, "plan": {}}))
        result = runner.invoke(
            app, ["forecast-code", "--from-plan", str(plan_file), "--format", "json"]
        )
        assert result.exit_code == 1
        payload = json.loads(result.stderr)["error"]
        assert payload["code"] == "invalid_argument"
        assert payload["hint"] == (
            "Use --format json with the source command to produce valid input."
        )

    def test_error_json_when_csv_is_empty(self, tmp_path):
        """
        `profile` of an empty CSV with --format json reports the code
        'data_unreadable', the field 'data' and the hint on stderr.
        """
        csv_path = tmp_path / "empty.csv"
        csv_path.write_bytes(b"")
        result = runner.invoke(
            app,
            ["profile", str(csv_path), "--target", "sales", "--format", "json",
             "--quiet"],
        )
        assert result.exit_code == 1
        assert result.stdout == ""
        assert json.loads(result.stderr) == {
            "error": {
                "code": "data_unreadable",
                "message": (
                    f"The CSV file '{csv_path}' could not be read: No columns "
                    f"to parse from file"
                ),
                "field": "data",
                "hint": (
                    "Pass a comma-separated text file in UTF-8 with a header "
                    "row, and the same number of fields in every row."
                ),
            }
        }

    def test_error_text_shows_tip_when_csv_is_empty(self, tmp_path):
        """
        In text mode the hint of the error is shown after "Tip: " on stderr.
        """
        csv_path = tmp_path / "empty.csv"
        csv_path.write_bytes(b"")
        result = runner.invoke(
            app, ["profile", str(csv_path), "--target", "sales", "--quiet"]
        )
        assert result.exit_code == 1
        assert result.stdout == ""
        assert (
            "Tip: Pass a comma-separated text file in UTF-8 with a header "
            "row, and the same number of fields in every row."
        ) in " ".join(result.stderr.split())

    def test_report_error_execution_tip(self, capsys):
        """
        A failed script points to the `*-code` commands: `--output-code` is
        only written when the command succeeds.
        """
        error = ForecastExecutionError(
            original_error      = ValueError("boom"),
            generated_code      = "x = 1",
            execution_traceback = "Traceback",
        )
        _report_error(error, json_errors=False)
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "Execution Error:" in captured.err
        assert (
            "Tip: Run forecast-code or backtest-code with the same options to "
            "get the script that failed."
        ) in " ".join(captured.err.split())

        _report_error(error, json_errors=True)
        payload = json.loads(capsys.readouterr().err)["error"]
        assert payload["code"] == "execution_failed"
        assert payload["hint"].startswith("Run forecast-code or backtest-code")

    @pytest.mark.parametrize(
        "command, value",
        [("forecast", "code"), ("forecast-code", "table"), ("ask", "code"),
         ("plan", "xml")],
    )
    def test_format_invalid_value_exit_2(self, command, value):
        """
        `--format` only accepts the values of the command: any other is a
        usage error (exit code 2) instead of the default output.
        """
        result = runner.invoke(app, [command, "data.csv", "--format", value])
        assert result.exit_code == 2
        assert "Invalid value for '--format'" in result.output

    @pytest.mark.parametrize(
        "command", ["forecast", "forecast-code", "backtest", "backtest-code"],
    )
    def test_steps_different_from_plan_raises(self, tmp_path, command):
        """
        `--steps` with `--from-plan` must match the steps of the plan, as in
        Python: it was ignored and the plan's horizon used.
        """
        csv_path = _write_csv(tmp_path, df_single)
        plan_file = _write_plan_bundle(tmp_path, csv_path, steps=5)
        result = runner.invoke(
            app,
            [command, csv_path, "--from-plan", plan_file, "--steps", "3",
             "--format", "json", "--quiet"],
        )
        assert result.exit_code == 1
        assert json.loads(result.stderr) == {
            "error": {
                "code": "invalid_argument",
                "message": (
                    "--steps (3) does not match the steps of the plan in "
                    "--from-plan (5). Omit --steps to use the plan's horizon, "
                    "or change it with `refine-plan --steps`."
                ),
                "field": "steps",
                "hint": None,
            }
        }

    @pytest.mark.parametrize("command", ["forecast", "backtest"])
    def test_data_of_another_structure_than_plan_raises(self, tmp_path, command):
        """
        Data passed with `--from-plan` whose structure differs from the
        profile of the bundle (an exogenous column is missing) exit with
        code 1 and say how they differ.
        """
        csv_path = _write_csv(tmp_path, df_single)
        plan_file = _write_plan_bundle(tmp_path, csv_path, steps=5)
        new_csv = _write_csv(
            tmp_path, df_single.drop(columns="promo"), name="new.csv"
        )
        result = runner.invoke(
            app,
            [command, new_csv, "--from-plan", plan_file, "--format", "json",
             "--quiet"],
        )
        assert result.exit_code == 1
        assert json.loads(result.stderr) == {
            "error": {
                "code": "invalid_argument",
                "message": (
                    "The data do not have the structure of the profile passed "
                    "(exog_columns: ['promo'] != []): profile these data and "
                    "build the plan from that profile."
                ),
                "field": "profile",
                "hint": (
                    "Profile these data again and build the plan from that "
                    "profile."
                ),
            }
        }

    def test_steps_different_from_plan_raises_ask(self, tmp_path):
        """
        `ask --from-plan` rejects a different `--steps` before calling the LLM.
        """
        csv_path = _write_csv(tmp_path, df_single)
        plan_file = _write_plan_bundle(tmp_path, csv_path, steps=5)
        result = runner.invoke(
            app,
            ["ask", "Why?", "--from-plan", plan_file, "--steps", "3",
             "--llm", "test", "--format", "json"],
        )
        assert result.exit_code == 1
        assert json.loads(result.stderr)["error"]["field"] == "steps"

    def test_steps_equal_to_plan_runs(self, tmp_path):
        """
        `--steps` equal to the steps of the plan is accepted.
        """
        csv_path = _write_csv(tmp_path, df_single)
        plan_file = _write_plan_bundle(tmp_path, csv_path, steps=5)
        result = runner.invoke(
            app,
            ["forecast-code", csv_path, "--from-plan", plan_file, "--steps", "5",
             "--quiet"],
        )
        assert result.exit_code == 0, result.output

    @pytest.mark.parametrize(
        "bundle, missing",
        [({"plan": {}}, "'profile'"), ([1], "'profile' or 'plan'")],
        ids=["no_profile", "not_an_object"],
    )
    def test_error_json_when_bundle_has_no_profile(self, tmp_path, bundle, missing):
        """
        A `--from-plan` input without a profile or a plan, or that is not a
        JSON object, is an invalid argument naming what is missing, not an
        internal `KeyError` or `TypeError`.
        """
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(bundle))
        result = runner.invoke(
            app, ["forecast-code", "--from-plan", str(plan_file), "--format", "json"]
        )
        assert result.exit_code == 1
        assert json.loads(result.stderr) == {
            "error": {
                "code": "invalid_argument",
                "message": (
                    f"The --from-plan input has no {missing}: pass the file "
                    f"written by `plan` or `refine-plan` with --format json."
                ),
                "field": "from_plan",
                "hint": None,
            }
        }

    def test_error_json_when_option_value_rejected(self, tmp_path):
        """
        A value that an option parser rejects keeps exit code 2 and, with
        --format json, is the JSON object too; without it, the usage error
        of the parser.
        """
        csv_path = _write_csv(tmp_path, df_single)
        args = ["forecast-code", csv_path, "--target", "sales", "--steps", "3",
                "--interval", "0.1"]
        result = runner.invoke(app, [*args, "--format", "json"])
        assert result.exit_code == 2
        assert json.loads(result.stderr) == {
            "error": {
                "code": "invalid_argument",
                "message": "Interval must be two comma-separated quantiles, e.g. '0.1,0.9'.",
                "field": None,
                "hint": None,
            }
        }

        result = runner.invoke(app, args)
        assert result.exit_code == 2
        assert "Invalid value" in result.stderr


# ---------------------------------------------------------------------------
# Decisions added in 0.4.0: --metric, --use-exog, --differentiation,
# --calendar-features, --target-transformer, --dropna-from-series
# ---------------------------------------------------------------------------


class TestDecisionOptions:
    """Tests for the options of the overrides added in 0.4.0."""

    def test_parse_decisions_reads_each_option(self):
        """
        Each option given becomes a keyword argument of plan(): 'auto' is
        None, 'none' an empty calendar list, comma-separated metrics a list
        and 'true'/'false' bools.
        """
        assert _parse_decisions() == {}
        assert _parse_decisions(
            metric="mean_squared_error,mean_absolute_error",
            use_exog="False",
            differentiation="1",
            calendar_features="month, day_of_week",
            target_transformer="none",
            dropna_from_series="true",
        ) == {
            "metric": ["mean_squared_error", "mean_absolute_error"],
            "use_exog": False,
            "differentiation": 1,
            "calendar_features": ["month", "day_of_week"],
            "target_transformer": "none",
            "dropna_from_series": True,
        }
        assert _parse_decisions(
            metric="auto", use_exog="auto", differentiation="auto",
            calendar_features="auto", target_transformer="auto",
            dropna_from_series="auto",
        ) == dict.fromkeys(
            ["metric", "use_exog", "differentiation", "calendar_features",
             "target_transformer", "dropna_from_series"]
        )
        assert _parse_decisions(metric="mean_squared_error") == {
            "metric": "mean_squared_error"
        }
        assert _parse_decisions(calendar_features="none") == {"calendar_features": []}

    @pytest.mark.parametrize(
        "option, value, message",
        [
            ("--use-exog", "yes", "--use-exog takes 'true', 'false' or 'auto'"),
            (
                "--dropna-from-series", "1",
                "--dropna-from-series takes 'true', 'false' or 'auto'",
            ),
            ("--differentiation", "one", "--differentiation takes an integer"),
        ],
    )
    def test_plan_exit_code_2_when_decision_option_invalid(
        self, tmp_path, option, value, message
    ):
        """
        A value the option cannot read exits with the usage error of click,
        which names the values it takes.
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["plan", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "5", option, value, "--quiet"],
        )

        assert result.exit_code == 2
        assert message in " ".join(result.output.split())

    def test_plan_and_refine_plan_with_decision_options(self, tmp_path):
        """
        plan applies the options, as plan() does, and refine-plan keeps them
        when omitted and resets one with 'auto'.
        """
        csv_path = _write_csv(tmp_path, df_single)
        planned = runner.invoke(
            app,
            ["plan", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "5", "--estimator", "Ridge",
             "--metric", "mean_squared_error", "--use-exog", "false",
             "--differentiation", "1", "--calendar-features", "none",
             "--target-transformer", "none", "--dropna-from-series", "true",
             "--format", "json", "--quiet"],
        )
        assert planned.exit_code == 0, planned.output
        plan = json.loads(planned.output)["plan"]
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(planned.output)
        refined = runner.invoke(
            app,
            ["refine-plan", "--from-plan", str(plan_file), "--steps", "6",
             "--use-exog", "auto", "--format", "json", "--quiet"],
        )
        assert refined.exit_code == 0, refined.output
        refined_plan = json.loads(refined.output)["plan"]

        kwargs = plan["forecaster_kwargs"]
        assert kwargs["differentiation"] == 1
        assert kwargs["calendar_features"] is None
        assert kwargs["dropna_from_series"] is True
        assert "transformer_y" not in kwargs
        assert "transformer_exog" not in kwargs
        assert plan["metrics_to_compute"] == ["mean_squared_error"]
        assert plan["use_exog"] is False
        assert plan["overridden_fields"] == [
            "estimator", "metric", "use_exog", "differentiation",
            "calendar_features", "target_transformer", "dropna_from_series",
        ]
        assert refined_plan["use_exog"] is True
        assert refined_plan["forecaster_kwargs"]["differentiation"] == 1
        assert "use_exog" not in refined_plan["overridden_fields"]

    def test_forecast_and_backtest_with_lags_and_decision_options(self, tmp_path):
        """
        forecast and backtest take --lags, --window-features and the new
        options, and run the plan they describe: forecast without --exog
        when --use-exog false.
        """
        csv_path = _write_csv(tmp_path, df_single)
        common = [csv_path, "--target", "sales", "--date-column", "date",
                  "--steps", "5", "--lags", "1,2,3", "--use-exog", "false",
                  "--metric", "mean_squared_error", "--format", "json", "--quiet"]

        forecast = runner.invoke(app, ["forecast", *common])
        backtest = runner.invoke(
            app, ["backtest", *common, "--initial-train-size", "60"]
        )

        assert forecast.exit_code == 0, forecast.output
        assert backtest.exit_code == 0, backtest.output
        forecast_plan = json.loads(forecast.output)["plan"]
        backtest_result = json.loads(backtest.output)
        assert forecast_plan["forecaster_kwargs"]["lags"] == [1, 2, 3]
        assert forecast_plan["use_exog"] is False
        assert backtest_result["plan"]["metrics_to_compute"] == ["mean_squared_error"]

    def test_forecast_code_and_backtest_code_from_plan_with_decision_options(
        self, tmp_path
    ):
        """
        With --from-plan, the options are applied on top of the saved plan
        through refine_plan, as the other overrides are.
        """
        csv_path = _write_csv(tmp_path, df_single)
        planned = runner.invoke(
            app,
            ["plan", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "5", "--format", "json", "--quiet"],
        )
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(planned.output)

        code = runner.invoke(
            app,
            ["forecast-code", "--from-plan", str(plan_file),
             "--differentiation", "1", "--quiet"],
        )
        backtest_code = runner.invoke(
            app,
            ["backtest-code", "--from-plan", str(plan_file),
             "--differentiation", "1", "--quiet"],
        )

        assert code.exit_code == 0, code.output
        assert backtest_code.exit_code == 0, backtest_code.output
        assert re.search(r"differentiation\s+=\s+1,", code.output)
        assert len(re.findall(r"differentiation\s+=\s+1,", backtest_code.output)) == 2


    def test_forecast_and_backtest_from_plan_apply_decision_options(self, tmp_path):
        """
        forecast and backtest with --from-plan apply the options on top of
        the saved plan, and 'auto' resets a choice of the saved plan.
        """
        csv_path = _write_csv(tmp_path, df_single)
        planned = runner.invoke(
            app,
            ["plan", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "5", "--lags", "1,2,3", "--differentiation", "1",
             "--format", "json", "--quiet"],
        )
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(planned.output)

        forecast = runner.invoke(
            app,
            ["forecast", csv_path, "--from-plan", str(plan_file),
             "--use-exog", "false", "--differentiation", "auto",
             "--format", "json", "--quiet"],
        )
        backtest = runner.invoke(
            app,
            ["backtest", csv_path, "--from-plan", str(plan_file),
             "--lags", "auto", "--metric", "mean_squared_error",
             "--initial-train-size", "60", "--format", "json", "--quiet"],
        )

        assert forecast.exit_code == 0, forecast.output
        assert backtest.exit_code == 0, backtest.output
        forecast_plan = json.loads(forecast.output)["plan"]
        backtest_plan = json.loads(backtest.output)["plan"]
        assert forecast_plan["use_exog"] is False
        assert "differentiation" not in forecast_plan["forecaster_kwargs"]
        assert forecast_plan["forecaster_kwargs"]["lags"] == [1, 2, 3]
        assert backtest_plan["forecaster_kwargs"]["lags"] != [1, 2, 3]
        assert backtest_plan["forecaster_kwargs"]["differentiation"] == 1
        assert backtest_plan["metrics_to_compute"] == ["mean_squared_error"]


# ---------------------------------------------------------------------------
# --exog-columns (profile and plan)
# ---------------------------------------------------------------------------


class TestExogColumnsOption:
    """Tests for the `--exog-columns` option of `profile` and `plan`."""

    def test_parse_exog_columns_output(self):
        """
        'auto' (or the option left out) is None, 'none' an empty list and
        comma-separated names a list.
        """
        assert _parse_exog_columns(None) is None
        assert _parse_exog_columns(" Auto ") is None
        assert _parse_exog_columns("NONE") == []
        assert _parse_exog_columns("promo, weekday") == ["promo", "weekday"]

    @pytest.mark.parametrize(
        "command", [["profile"], ["plan", "--steps", "5"]], ids=["profile", "plan"]
    )
    def test_profile_and_plan_output_when_exog_columns(self, tmp_path, command):
        """
        profile and plan pass --exog-columns to profile(): the profile keeps
        the columns named and lists the others in `unused_columns`.
        """
        csv_path = _write_csv(tmp_path, df_categorical_exog)
        result = runner.invoke(
            app,
            [*command[:1], csv_path, *command[1:], "--target", "sales",
             "--date-column", "date", "--exog-columns", "promo",
             "--format", "json", "--quiet"],
        )

        assert result.exit_code == 0, result.output
        output = json.loads(result.output)
        data_profile = (output.get("profile") or output)["data_profile"]
        assert data_profile["exog_columns"] == ["promo"]
        assert data_profile["unused_columns"] == ["weekday"]

    def test_profile_exit_code_1_when_exog_columns_not_in_data(self, tmp_path):
        """
        A column of --exog-columns that is not in the data is reported with
        the message of profile().
        """
        csv_path = _write_csv(tmp_path, df_categorical_exog)
        result = runner.invoke(
            app,
            ["profile", csv_path, "--target", "sales", "--date-column", "date",
             "--exog-columns", "price", "--quiet"],
        )

        assert result.exit_code == 1
        assert "`exog_columns` names columns that are not in the data: " in (
            " ".join(result.output.split())
        )

    def test_plan_exit_code_1_when_exog_columns_with_from_profile(self, tmp_path):
        """
        --exog-columns with --from-profile is an error: the profile loaded
        already chose its columns.
        """
        csv_path = _write_csv(tmp_path, df_categorical_exog)
        profiled = runner.invoke(
            app,
            ["profile", csv_path, "--target", "sales", "--date-column", "date",
             "--format", "json", "--quiet"],
        )
        profile_file = tmp_path / "profile.json"
        profile_file.write_text(profiled.output)

        result = runner.invoke(
            app,
            ["plan", "--from-profile", str(profile_file), "--steps", "5",
             "--exog-columns", "promo", "--quiet"],
        )

        assert result.exit_code == 1
        assert (
            "--exog-columns applies when the data is profiled, not with "
            "--from-profile: run `skforecast-ai profile` with --exog-columns "
            "instead."
        ) in " ".join(result.output.split())
