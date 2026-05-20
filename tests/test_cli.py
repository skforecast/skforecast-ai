# Unit test cli skforecast_ai

import ast
import json

from typer.testing import CliRunner

from skforecast_ai.cli import app

from .fixtures_assistant import df_single, df_multi_long, df_multi_wide

runner = CliRunner()


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
             "--date-column", "date", "--series-id", "series_id",
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
        assert "forecaster" in data
        assert "steps" in data
        assert data["steps"] == 10

    def test_plan_with_interval(self, tmp_path):
        """
        Plan with --interval includes interval in the output.
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["plan", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "10", "--interval", "10,90", "--format", "json", "--quiet"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["interval"] == [10, 90]
        assert data["interval_method"] is not None

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
        assert data["steps"] == 10


# ---------------------------------------------------------------------------
# generate-code command
# ---------------------------------------------------------------------------


class TestGenerateCode:
    """Tests for the `generate-code` CLI command."""

    def test_generate_code_basic(self, tmp_path):
        """
        Generate-code command prints Python code to stdout.
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["generate-code", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "10", "--quiet"],
        )
        assert result.exit_code == 0
        assert "import" in result.output
        assert "skforecast" in result.output

    def test_generate_code_json_format(self, tmp_path):
        """
        Generate-code --format json outputs valid JSON with code key.
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["generate-code", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "10", "--format", "json", "--quiet"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "code" in data
        assert "profile" in data
        assert "plan" in data

    def test_generate_code_output_to_file(self, tmp_path):
        """
        Generate-code --output writes a valid Python file.
        """
        csv_path = _write_csv(tmp_path, df_single)
        out_path = tmp_path / "script.py"
        result = runner.invoke(
            app,
            ["generate-code", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "10", "--output", str(out_path), "--quiet"],
        )
        assert result.exit_code == 0
        assert out_path.exists()
        code = out_path.read_text()
        ast.parse(code)

    def test_generate_code_syntax_valid(self, tmp_path):
        """
        Generated code is syntactically valid Python.
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["generate-code", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "10", "--format", "json", "--quiet"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        ast.parse(data["code"])

    def test_generate_code_with_interval(self, tmp_path):
        """
        Generate-code with --interval produces code with prediction intervals.
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["generate-code", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "10", "--interval", "10,90", "--format", "json", "--quiet"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "predict_interval" in data["code"] or "interval" in data["code"]

    def test_generate_code_missing_file(self):
        """
        Generate-code with non-existent file shows helpful error.
        """
        result = runner.invoke(
            app,
            ["generate-code", "nonexistent.csv", "--target", "y", "--steps", "10"],
        )
        assert result.exit_code == 1


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
        Forecast with --interval includes intervals in JSON output.
        """
        csv_path = _write_csv(tmp_path, df_single)
        result = runner.invoke(
            app,
            ["forecast", csv_path, "--target", "sales", "--date-column", "date",
             "--steps", "5", "--interval", "10,90", "--format", "json", "--quiet"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["intervals"] is not None
        assert len(data["intervals"]) == 5

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
            def run_sync(self, msg, **kw):
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