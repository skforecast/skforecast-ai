# Tests for plan save/load and pipe composition (Phase 5)

import json
from io import StringIO
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from skforecast_ai.cli import app, _read_json_input
from tests.fixtures_assistant import df_single

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures: mock profile and plan JSON bundle
# ---------------------------------------------------------------------------

MOCK_PROFILE = {
    "data_profile": {
        "data_format": "single",
        "n_series": 1,
        "series_lengths": {"sales": {"start": None, "end": None, "length": 100}},
        "target": "sales",
        "target_dtype": "numeric",
        "target_stats": {"sales": {"min": 0.0, "max": 99.0, "mean": 49.5, "std": 29.0}},
        "missing_target": {},
        "date_column": "date",
        "series_id_column": None,
        "index_type": "datetime",
        "frequency": "D",
        "frequency_is_set": True,
        "index_is_monotonic": True,
        "has_gaps": False,
        "has_duplicate_timestamps": False,
        "start_date": "2023-01-01",
        "exog_columns": ["promo"],
        "categorical_exog": [],
        "missing_exog": {},
        "data_path": "data.csv",
        "warnings": [],
    },
    "task_type": "single_series",
    "forecaster": "ForecasterRecursive",
    "forecaster_candidates": ["ForecasterRecursive", "ForecasterDirect"],
    "estimator": "LGBMRegressor",
    "estimator_candidates": ["LGBMRegressor", "Ridge"],
    "series_pacf": [],
    "window_features": None,
    "explanation": "Single series with daily frequency.",
}

MOCK_PLAN = {
    "task_type": "single_series",
    "forecaster": "ForecasterRecursive",
    "forecaster_kwargs": {"lags": [1, 2, 3, 4, 5, 6, 7]},
    "estimator": "LGBMRegressor",
    "estimator_kwargs": {"n_estimators": 100, "random_state": 123, "verbose": -1},
    "steps": 10,
    "frequency": "D",
    "interval": None,
    "interval_method": None,
    "use_exog": True,
    "end_train": "2023-03-22",
    "preprocessing_steps": [],
    "warnings": [],
    "explanation": "Recursive strategy with LightGBM.",
}

MOCK_BUNDLE = {"profile": MOCK_PROFILE, "plan": MOCK_PLAN}


# ---------------------------------------------------------------------------
# _read_json_input helper tests
# ---------------------------------------------------------------------------


class TestReadJsonInput:
    """Tests for the _read_json_input helper."""

    def test_read_from_file(self, tmp_path):
        """Reads and parses JSON from a file path."""
        f = tmp_path / "data.json"
        f.write_text(json.dumps({"key": "value"}))
        result = _read_json_input(str(f))
        assert result == {"key": "value"}

    def test_read_from_stdin(self):
        """Reads and parses JSON from stdin when source is '-'."""
        with patch("sys.stdin", StringIO('{"key": "stdin_value"}')):
            result = _read_json_input("-")
        assert result == {"key": "stdin_value"}

    def test_file_not_found_raises(self):
        """Raises FileNotFoundError for nonexistent file."""
        with pytest.raises(FileNotFoundError, match="File not found"):
            _read_json_input("/nonexistent/path.json")

    def test_invalid_json_raises(self, tmp_path):
        """Raises ValueError for invalid JSON content."""
        f = tmp_path / "bad.json"
        f.write_text("not json {{{")
        with pytest.raises(ValueError, match="Invalid JSON"):
            _read_json_input(str(f))


# ---------------------------------------------------------------------------
# plan --from-profile tests
# ---------------------------------------------------------------------------


class TestPlanFromProfile:
    """Tests for the plan command with --from-profile."""

    def test_plan_from_profile_file(self, tmp_path):
        """plan --from-profile loads profile and generates plan."""
        profile_file = tmp_path / "profile.json"
        profile_file.write_text(json.dumps(MOCK_PROFILE))

        result = runner.invoke(app, [
            "plan", "--from-profile", str(profile_file),
            "--steps", "10", "--format", "json", "--quiet",
        ])
        assert result.exit_code == 0, result.output
        output = json.loads(result.output)
        assert "profile" in output
        assert "plan" in output
        assert output["plan"]["steps"] == 10

    def test_plan_from_profile_stdin(self):
        """plan --from-profile - reads profile from stdin."""
        result = runner.invoke(
            app,
            ["plan", "--from-profile", "-", "--steps", "10", "--format", "json", "--quiet"],
            input=json.dumps(MOCK_PROFILE),
        )
        assert result.exit_code == 0, result.output
        output = json.loads(result.output)
        assert "plan" in output

    def test_plan_without_data_or_from_profile_errors(self):
        """plan without DATA or --from-profile exits with error."""
        result = runner.invoke(app, ["plan", "--steps", "10", "--quiet"])
        assert result.exit_code == 1
        assert "required" in result.output.lower()

    def test_plan_from_profile_invalid_schema(self):
        """plan --from-profile with wrong schema shows friendly validation error."""
        invalid_profile = json.dumps({"foo": "bar", "unrelated": 123})
        result = runner.invoke(
            app,
            ["plan", "--from-profile", "-", "--steps", "10", "--quiet"],
            input=invalid_profile,
        )
        assert result.exit_code == 1
        assert "validation error" in result.output.lower()
        assert "Tip:" in result.output

    def test_plan_json_output_is_bundle(self, tmp_path):
        """plan --format json outputs a bundle with profile and plan keys."""
        csv_file = tmp_path / "data.csv"
        df_single.to_csv(csv_file, index=False)

        result = runner.invoke(app, [
            "plan", str(csv_file), "--target", "sales",
            "--date-column", "date", "--steps", "10",
            "--format", "json", "--quiet",
        ])
        assert result.exit_code == 0, result.output
        output = json.loads(result.output)
        assert "profile" in output
        assert "plan" in output
        assert output["plan"]["steps"] == 10
        assert output["profile"]["forecaster"] is not None


# ---------------------------------------------------------------------------
# refine-plan tests
# ---------------------------------------------------------------------------


class TestRefinePlan:
    """Tests for the refine-plan command."""

    def test_refine_plan_from_file(self, tmp_path):
        """refine-plan --from-plan loads bundle and refines plan."""
        bundle_file = tmp_path / "bundle.json"
        bundle_file.write_text(json.dumps(MOCK_BUNDLE))

        result = runner.invoke(app, [
            "refine-plan", "--from-plan", str(bundle_file),
            "--steps", "5", "--format", "json", "--quiet",
        ])
        assert result.exit_code == 0, result.output
        output = json.loads(result.output)
        assert "profile" in output
        assert "plan" in output
        assert output["plan"]["steps"] == 5

    def test_refine_plan_from_stdin(self):
        """refine-plan --from-plan - reads bundle from stdin."""
        result = runner.invoke(
            app,
            ["refine-plan", "--from-plan", "-", "--steps", "5", "--format", "json", "--quiet"],
            input=json.dumps(MOCK_BUNDLE),
        )
        assert result.exit_code == 0, result.output
        output = json.loads(result.output)
        assert output["plan"]["steps"] == 5

    def test_refine_plan_override_forecaster(self, tmp_path):
        """refine-plan --forecaster overrides the forecaster field."""
        bundle_file = tmp_path / "bundle.json"
        bundle_file.write_text(json.dumps(MOCK_BUNDLE))

        result = runner.invoke(app, [
            "refine-plan", "--from-plan", str(bundle_file),
            "--forecaster", "ForecasterDirect",
            "--format", "json", "--quiet",
        ])
        assert result.exit_code == 0, result.output
        output = json.loads(result.output)
        assert output["plan"]["forecaster"] == "ForecasterDirect"

    def test_refine_plan_override_estimator_kwargs(self, tmp_path):
        """refine-plan --estimator-kwargs passes JSON overrides."""
        bundle_file = tmp_path / "bundle.json"
        bundle_file.write_text(json.dumps(MOCK_BUNDLE))

        result = runner.invoke(app, [
            "refine-plan", "--from-plan", str(bundle_file),
            "--estimator-kwargs", '{"n_estimators": 500}',
            "--format", "json", "--quiet",
        ])
        assert result.exit_code == 0, result.output
        output = json.loads(result.output)
        assert output["plan"]["estimator_kwargs"]["n_estimators"] == 500

    def test_refine_plan_invalid_json_errors(self):
        """refine-plan with invalid JSON exits with error."""
        result = runner.invoke(
            app,
            ["refine-plan", "--from-plan", "-", "--format", "json", "--quiet"],
            input="not json {{{",
        )
        assert result.exit_code == 1
        assert "invalid json" in result.output.lower() or "error" in result.output.lower()

    def test_refine_plan_invalid_schema_errors(self):
        """refine-plan with wrong schema shows validation error."""
        result = runner.invoke(
            app,
            ["refine-plan", "--from-plan", "-", "--format", "json", "--quiet"],
            input=json.dumps({"profile": {}, "plan": {}}),
        )
        assert result.exit_code == 1
        assert "validation error" in result.output.lower()

    def test_refine_plan_invalid_forecaster_errors(self, tmp_path):
        """refine-plan with invalid forecaster name exits with error."""
        bundle_file = tmp_path / "bundle.json"
        bundle_file.write_text(json.dumps(MOCK_BUNDLE))

        result = runner.invoke(app, [
            "refine-plan", "--from-plan", str(bundle_file),
            "--forecaster", "NonexistentForecaster",
            "--format", "json", "--quiet",
        ])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# forecast-code --from-plan tests
# ---------------------------------------------------------------------------


class TestGenerateCodeFromPlan:
    """Tests for the forecast-code command with --from-plan."""

    def test_render_forecast_code_file(self, tmp_path):
        """forecast-code --from-plan generates code from saved bundle."""
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(MOCK_BUNDLE))

        result = runner.invoke(app, [
            "forecast-code", "--from-plan", str(plan_file), "--quiet",
        ])
        assert result.exit_code == 0, result.output
        # Output should contain Python code (imports, forecaster setup)
        assert "import" in result.output or "ForecasterRecursive" in result.output

    def test_render_forecast_code_stdin(self):
        """forecast-code --from-plan - reads from stdin."""
        result = runner.invoke(
            app,
            ["forecast-code", "--from-plan", "-", "--quiet"],
            input=json.dumps(MOCK_BUNDLE),
        )
        assert result.exit_code == 0, result.output

    def test_render_forecast_code_json_format(self, tmp_path):
        """forecast-code --from-plan --format json outputs CodeGenerationResult."""
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(MOCK_BUNDLE))

        result = runner.invoke(app, [
            "forecast-code", "--from-plan", str(plan_file),
            "--format", "json", "--quiet",
        ])
        assert result.exit_code == 0, result.output
        output = json.loads(result.output)
        assert "code" in output
        assert "plan" in output
        assert "profile" in output

    def test_forecast_code_without_data_or_from_plan_errors(self):
        """forecast-code without DATA or --from-plan exits with error."""
        result = runner.invoke(app, [
            "forecast-code", "--target", "sales", "--steps", "10", "--quiet",
        ])
        assert result.exit_code == 1
        assert "required" in result.output.lower()


# ---------------------------------------------------------------------------
# forecast --from-plan tests
# ---------------------------------------------------------------------------


class TestForecastFromPlan:
    """Tests for the forecast command with --from-plan."""

    def test_forecast_from_plan_file(self, tmp_path):
        """forecast --from-plan executes using saved plan."""
        csv_file = tmp_path / "data.csv"
        df_single.to_csv(csv_file, index=False)

        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(MOCK_BUNDLE))

        result = runner.invoke(app, [
            "forecast", str(csv_file),
            "--from-plan", str(plan_file),
            "--test-size", "0.2",
            "--format", "json", "--quiet",
        ])
        assert result.exit_code == 0, result.output
        output = json.loads(result.output)
        assert "predictions" in output
        assert "metrics" in output

    def test_forecast_from_plan_with_interval_override_produces_intervals(self, tmp_path):
        """
        forecast --from-plan --interval re-derives the plan via refine_plan
        so prediction interval columns are produced, even when the saved
        plan had no interval configured.
        """
        csv_file = tmp_path / "data.csv"
        df_single.to_csv(csv_file, index=False)

        # Generate a real plan bundle; interval is None by default.
        plan_result = runner.invoke(app, [
            "plan", str(csv_file), "--target", "sales",
            "--date-column", "date", "--steps", "5",
            "--format", "json", "--quiet",
        ])
        assert plan_result.exit_code == 0, plan_result.output
        bundle = json.loads(plan_result.output)
        assert bundle["plan"]["interval"] is None

        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(bundle))

        # Forecast from the saved plan with an interval override.
        result = runner.invoke(app, [
            "forecast", str(csv_file),
            "--from-plan", str(plan_file),
            "--interval", "0.1,0.9",
            "--test-size", "0.2",
            "--format", "json", "--quiet",
        ])
        assert result.exit_code == 0, result.output
        output = json.loads(result.output)
        predictions = output["predictions"]
        assert len(predictions) > 0
        assert "lower_bound" in predictions[0]
        assert "upper_bound" in predictions[0]

    def test_forecast_from_plan_with_estimator_override_applies(self, tmp_path):
        """
        forecast --from-plan --estimator re-derives the plan via refine_plan
        so the estimator override is honored instead of being silently
        dropped. The generated code must reference the overriding estimator.
        """
        csv_file = tmp_path / "data.csv"
        df_single.to_csv(csv_file, index=False)

        # Generate a real plan bundle; the default estimator is LGBMRegressor.
        plan_result = runner.invoke(app, [
            "plan", str(csv_file), "--target", "sales",
            "--date-column", "date", "--steps", "5",
            "--format", "json", "--quiet",
        ])
        assert plan_result.exit_code == 0, plan_result.output
        bundle = json.loads(plan_result.output)
        assert bundle["plan"]["estimator"] == "Ridge"

        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(bundle))

        # Forecast from the saved plan, overriding the estimator.
        result = runner.invoke(app, [
            "forecast", str(csv_file),
            "--from-plan", str(plan_file),
            "--estimator", "LGBMRegressor",
            "--test-size", "0.2",
            "--format", "json", "--quiet",
        ])
        assert result.exit_code == 0, result.output
        output = json.loads(result.output)
        assert "LGBMRegressor" in output["code"]
        assert "Ridge" not in output["code"]

    def test_forecast_without_target_or_from_plan_errors(self, tmp_path):
        """forecast without --target/--steps or --from-plan exits with error."""
        csv_file = tmp_path / "data.csv"
        df_single.to_csv(csv_file, index=False)

        result = runner.invoke(app, [
            "forecast", str(csv_file), "--quiet",
        ])
        assert result.exit_code == 1
        assert "required" in result.output.lower()


class TestBacktestFromPlan:
    """Tests for the backtest command with --from-plan."""

    def test_backtest_fold_stride_consistent_across_paths(self, tmp_path):
        """
        backtest treats --fold-stride identically whether or not --from-plan
        is used. Passing --fold-stride equal to steps must produce the same
        number of predictions on both paths (the from-plan branch no longer
        diverges because `steps` is None there).
        """
        csv_file = tmp_path / "data.csv"
        df_single.to_csv(csv_file, index=False)

        # Generate a real plan bundle with steps=5.
        plan_result = runner.invoke(app, [
            "plan", str(csv_file), "--target", "sales",
            "--date-column", "date", "--steps", "5",
            "--format", "json", "--quiet",
        ])
        assert plan_result.exit_code == 0, plan_result.output
        bundle = json.loads(plan_result.output)
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(bundle))

        # Path A: explicit args with --fold-stride equal to steps.
        direct = runner.invoke(app, [
            "backtest", str(csv_file), "--target", "sales",
            "--date-column", "date", "--steps", "5", "--fold-stride", "5",
            "--format", "json", "--quiet",
        ])
        assert direct.exit_code == 0, direct.output

        # Path B: --from-plan with the same --fold-stride.
        from_plan = runner.invoke(app, [
            "backtest", str(csv_file),
            "--from-plan", str(plan_file), "--fold-stride", "5",
            "--format", "json", "--quiet",
        ])
        assert from_plan.exit_code == 0, from_plan.output

        direct_preds = json.loads(direct.output)["predictions"]
        from_plan_preds = json.loads(from_plan.output)["predictions"]
        assert len(direct_preds) == len(from_plan_preds)

    def test_backtest_from_plan_with_estimator_override_applies(self, tmp_path):
        """
        backtest --from-plan --estimator re-derives the plan via refine_plan
        so the estimator override is honored instead of being silently
        dropped. The generated code must reference the overriding estimator.
        """
        csv_file = tmp_path / "data.csv"
        df_single.to_csv(csv_file, index=False)

        plan_result = runner.invoke(app, [
            "plan", str(csv_file), "--target", "sales",
            "--date-column", "date", "--steps", "5",
            "--format", "json", "--quiet",
        ])
        assert plan_result.exit_code == 0, plan_result.output
        bundle = json.loads(plan_result.output)
        assert bundle["plan"]["estimator"] == "Ridge"
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(bundle))

        result = runner.invoke(app, [
            "backtest", str(csv_file),
            "--from-plan", str(plan_file),
            "--estimator", "LGBMRegressor",
            "--format", "json", "--quiet",
        ])
        assert result.exit_code == 0, result.output
        output = json.loads(result.output)
        assert "LGBMRegressor" in output["code"]
        assert "Ridge" not in output["code"]


# ---------------------------------------------------------------------------
# Pipe composition end-to-end test
# ---------------------------------------------------------------------------


class TestPipeComposition:
    """Tests for chaining commands via JSON piping."""

    def test_profile_to_plan_pipe(self, tmp_path):
        """profile --format json output feeds into plan --from-profile."""
        csv_file = tmp_path / "data.csv"
        df_single.to_csv(csv_file, index=False)

        # Step 1: profile
        profile_result = runner.invoke(app, [
            "profile", str(csv_file), "--target", "sales",
            "--date-column", "date", "--format", "json", "--quiet",
        ])
        assert profile_result.exit_code == 0, profile_result.output

        # Step 2: plan from profile (pipe via stdin)
        plan_result = runner.invoke(
            app,
            ["plan", "--from-profile", "-", "--steps", "10", "--format", "json", "--quiet"],
            input=profile_result.output,
        )
        assert plan_result.exit_code == 0, plan_result.output
        plan_output = json.loads(plan_result.output)
        assert "profile" in plan_output
        assert "plan" in plan_output

    def test_plan_to_forecast_code_pipe(self, tmp_path):
        """plan --format json output feeds into forecast-code --from-plan."""
        csv_file = tmp_path / "data.csv"
        df_single.to_csv(csv_file, index=False)

        # Step 1: plan
        plan_result = runner.invoke(app, [
            "plan", str(csv_file), "--target", "sales",
            "--date-column", "date", "--steps", "10",
            "--format", "json", "--quiet",
        ])
        assert plan_result.exit_code == 0, plan_result.output

        # Step 2: forecast-code from plan (pipe via stdin)
        code_result = runner.invoke(
            app,
            ["forecast-code", "--from-plan", "-", "--quiet"],
            input=plan_result.output,
        )
        assert code_result.exit_code == 0, code_result.output
        # Should have Python code output
        assert "import" in code_result.output or "Forecaster" in code_result.output

    def test_full_chain_profile_plan_code(self, tmp_path):
        """Full pipe chain: profile → plan → forecast-code."""
        csv_file = tmp_path / "data.csv"
        df_single.to_csv(csv_file, index=False)

        # profile
        profile_result = runner.invoke(app, [
            "profile", str(csv_file), "--target", "sales",
            "--date-column", "date", "--format", "json", "--quiet",
        ])
        assert profile_result.exit_code == 0

        # plan from profile
        plan_result = runner.invoke(
            app,
            ["plan", "--from-profile", "-", "--steps", "10", "--format", "json", "--quiet"],
            input=profile_result.output,
        )
        assert plan_result.exit_code == 0

        # forecast-code from plan
        code_result = runner.invoke(
            app,
            ["forecast-code", "--from-plan", "-", "--format", "json", "--quiet"],
            input=plan_result.output,
        )
        assert code_result.exit_code == 0
        output = json.loads(code_result.output)
        assert "code" in output
        assert len(output["code"]) > 50

    def test_plan_to_refine_plan_pipe(self, tmp_path):
        """plan --format json output feeds into refine-plan --from-plan."""
        csv_file = tmp_path / "data.csv"
        df_single.to_csv(csv_file, index=False)

        # Step 1: plan
        plan_result = runner.invoke(app, [
            "plan", str(csv_file), "--target", "sales",
            "--date-column", "date", "--steps", "10",
            "--format", "json", "--quiet",
        ])
        assert plan_result.exit_code == 0, plan_result.output

        # Step 2: refine-plan from plan (pipe via stdin)
        refine_result = runner.invoke(
            app,
            ["refine-plan", "--from-plan", "-", "--steps", "5", "--format", "json", "--quiet"],
            input=plan_result.output,
        )
        assert refine_result.exit_code == 0, refine_result.output
        output = json.loads(refine_result.output)
        assert output["plan"]["steps"] == 5
