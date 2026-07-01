# Unit test cli skforecast_ai

import ast
import json

import pytest
import typer
from typer.testing import CliRunner

from skforecast_ai.cli import app, _parse_lags
from skforecast_ai.assistant import ForecastingAssistant

from .fixtures_assistant import df_single, df_multi_long, df_multi_wide

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
             "--steps", "10", "--estimator-kwargs", '{"n_estimators": 200}',
             "--format", "json", "--quiet"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["plan"]["estimator_kwargs"]["n_estimators"] == 200

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
             "--steps", "10", "--estimator-kwargs", '{"n_estimators": 300}',
             "--quiet"],
        )
        assert result.exit_code == 0
        assert "n_estimators" in result.output


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
             "--steps", "5", "--quiet"],
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
             "--steps", "5", "--format", "json", "--quiet"],
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
             "--steps", "5", "--output-predictions", str(preds_path), "--quiet"],
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
             "--steps", "5", "--output-code", str(code_path), "--quiet"],
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
             "--steps", "5", "--interval", "0.1,0.9", "--format", "json", "--quiet"],
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
             "--steps", "5", "--estimator", "RandomForestRegressor",
             "--estimator-kwargs", '{"n_estimators": 150, "random_state": 123}',
             "--format", "json", "--quiet"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["plan"]["estimator_kwargs"]["n_estimators"] == 150

    def test_forecast_with_exog_future(self, tmp_path):
        """
        Forecast --exog-future loads the CSV with its date column as a
        DatetimeIndex and produces predictions over the horizon.
        """
        csv_path = _write_csv(tmp_path, df_single)
        mask = (df_single["date"] >= "2023-03-22") & (df_single["date"] <= "2023-03-26")
        exog_future = df_single.loc[mask, ["date", "promo"]]
        exog_path = _write_csv(tmp_path, exog_future, name="future_exog.csv")
        result = runner.invoke(
            app,
            ["forecast", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "5", "--exog-future", exog_path,
             "--format", "json", "--quiet"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data["predictions"]) == 5



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