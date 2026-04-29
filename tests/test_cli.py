# Unit test cli skforecast_ai

import json

from typer.testing import CliRunner

from skforecast_ai.cli import app

runner = CliRunner()

CSV_CONTENT = (
    "date,sales,promo\n"
    "2020-01-01,100,1\n"
    "2020-01-02,110,0\n"
    "2020-01-03,105,1\n"
    "2020-01-04,120,0\n"
    "2020-01-05,115,1\n"
    "2020-01-06,130,0\n"
    "2020-01-07,125,1\n"
    "2020-01-08,140,0\n"
    "2020-01-09,135,1\n"
    "2020-01-10,150,0\n"
    "2020-01-11,145,1\n"
    "2020-01-12,160,0\n"
    "2020-01-13,155,1\n"
    "2020-01-14,170,0\n"
    "2020-01-15,165,1\n"
    "2020-01-16,180,0\n"
    "2020-01-17,175,1\n"
    "2020-01-18,190,0\n"
    "2020-01-19,185,1\n"
    "2020-01-20,200,0\n"
    "2020-01-21,195,1\n"
    "2020-01-22,210,0\n"
    "2020-01-23,205,1\n"
    "2020-01-24,220,0\n"
    "2020-01-25,215,1\n"
    "2020-01-26,230,0\n"
    "2020-01-27,225,1\n"
    "2020-01-28,240,0\n"
    "2020-01-29,235,1\n"
    "2020-01-30,250,0\n"
    "2020-01-31,245,1\n"
    "2020-02-01,260,0\n"
    "2020-02-02,255,1\n"
    "2020-02-03,270,0\n"
    "2020-02-04,265,1\n"
    "2020-02-05,280,0\n"
    "2020-02-06,275,1\n"
    "2020-02-07,290,0\n"
    "2020-02-08,285,1\n"
    "2020-02-09,300,0\n"
    "2020-02-10,295,1\n"
    "2020-02-11,310,0\n"
    "2020-02-12,305,1\n"
    "2020-02-13,320,0\n"
    "2020-02-14,315,1\n"
    "2020-02-15,330,0\n"
    "2020-02-16,325,1\n"
    "2020-02-17,340,0\n"
    "2020-02-18,335,1\n"
    "2020-02-19,350,0\n"
)


def _write_csv(tmp_path):
    """Write sample CSV to a temporary file and return its path."""
    csv_file = tmp_path / "sample.csv"
    csv_file.write_text(CSV_CONTENT)
    return csv_file


def test_inspect_output_when_valid_csv(tmp_path):
    """
    Test that the inspect command with --json produces valid JSON output
    matching the DataProfile schema and exits with code 0.
    """
    csv_file = _write_csv(tmp_path)
    result = runner.invoke(
        app, ["inspect", str(csv_file), "--target", "sales", "--json"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    profile = json.loads(result.stdout)
    assert profile["target"] == "sales"
    assert profile["n_observations"] == 50
    assert profile["n_series"] == 1
    assert profile["index_type"] == "datetime"


def test_inspect_error_when_missing_target(tmp_path):
    """
    Test that the inspect command fails with a clear error when the --target
    option is not provided.
    """
    csv_file = _write_csv(tmp_path)
    result = runner.invoke(app, ["inspect", str(csv_file)])
    assert result.exit_code != 0


def test_recommend_output_when_valid_csv(tmp_path):
    """
    Test that the recommend command with --json produces valid JSON output
    matching the ForecastPlan schema with the correct horizon.
    """
    csv_file = _write_csv(tmp_path)
    result = runner.invoke(
        app,
        ["recommend", str(csv_file), "--target", "sales", "--horizon", "5", "--json"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    plan = json.loads(result.stdout)
    assert plan["horizon"] == 5
    assert plan["forecaster"]
    assert plan["metric"]
    assert plan["task_type"] == "single_series"


def test_generate_code_output_when_stdout(tmp_path):
    """
    Test that the generate-code command prints Python code containing
    import statements to stdout.
    """
    csv_file = _write_csv(tmp_path)
    result = runner.invoke(
        app,
        [
            "generate-code",
            str(csv_file),
            "--target", "sales",
            "--horizon", "5",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "import" in result.stdout
    assert "skforecast" in result.stdout


def test_generate_code_output_when_file(tmp_path):
    """
    Test that the generate-code command with --output writes a Python file
    containing valid import statements.
    """
    csv_file = _write_csv(tmp_path)
    output_file = tmp_path / "forecast_script.py"
    result = runner.invoke(
        app,
        [
            "generate-code",
            str(csv_file),
            "--target", "sales",
            "--horizon", "5",
            "--output", str(output_file),
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert output_file.exists()
    code = output_file.read_text()
    assert "import" in code
    assert "skforecast" in code


def test_inspect_error_when_nonexistent_file():
    """
    Test that the inspect command exits with code 1 and prints an error
    message when the CSV file does not exist.
    """
    result = runner.invoke(
        app,
        ["inspect", "nonexistent_file.csv", "--target", "sales", "--json"],
    )
    assert result.exit_code == 1
    assert "not found" in result.stdout.lower() or "error" in result.stdout.lower()


def test_generate_code_output_when_json_flag(tmp_path):
    """
    Test that the generate-code command with --json returns a JSON object
    containing both the plan and the generated code.
    """
    csv_file = _write_csv(tmp_path)
    result = runner.invoke(
        app,
        [
            "generate-code",
            str(csv_file),
            "--target", "sales",
            "--horizon", "5",
            "--json",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    output = json.loads(result.stdout)
    assert "plan" in output
    assert "code" in output
    assert "import" in output["code"]
    assert output["plan"]["horizon"] == 5
