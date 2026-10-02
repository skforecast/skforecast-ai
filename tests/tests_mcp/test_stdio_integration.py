# Integration test of the MCP server over stdio

import os
import sys
import anyio
import pytest
from mcp import Client, StdioServerParameters

from skforecast_ai import ForecastingAssistant

from .fixtures_mcp import content_of, df_h2o_csv, error_of, write_csv


@pytest.mark.slow
def test_stdio_server_runs_the_planning_workflow(tmp_path):
    """
    Test that `skforecast-ai mcp` serves the tools over stdio in a process of
    its own: profile, plan and create_cv give the results of the Python API,
    an error arrives as the JSON of the error, and the output directory is
    created.
    """
    data = tmp_path / "data"
    data.mkdir()
    path = write_csv(data, "h2o.csv", df_h2o_csv)
    output_dir = tmp_path / "out"
    parameters = StdioServerParameters(
        command = sys.executable,
        args    = [
            "-c", "from skforecast_ai.cli import app; app()", "mcp",
            "--allow-dir", str(data), "--output-dir", str(output_dir),
        ],
        env     = dict(os.environ),
        cwd     = str(tmp_path),
    )

    async def main():
        async with Client(parameters) as client:
            profile = content_of(await client.call_tool(
                "profile", {"data_path": path, "target": "x"}
            ))
            plan = content_of(await client.call_tool(
                "plan", {"profile_id": profile["id"], "steps": 12}
            ))
            cv = content_of(await client.call_tool("create_cv", {"plan_id": plan["id"]}))
            code = content_of(await client.call_tool("get_code", {"object_id": plan["id"]}))
            error = await client.call_tool("plan", {"profile_id": "x", "steps": 12})
            return profile, plan, cv, code, error

    profile, plan, cv, code, error = anyio.run(main)

    assistant = ForecastingAssistant()
    expected_profile = assistant.profile(path, target="x")
    expected_plan = assistant.plan(profile=expected_profile, steps=12)
    expected_cv = assistant.create_cv(profile=expected_profile, plan=expected_plan)
    script = assistant.forecast_code(profile=expected_profile, plan=expected_plan)

    assert profile["summary"] == expected_profile.describe()
    assert plan["summary"] == script.describe()
    assert cv["summary"] == expected_cv.describe()
    assert cv["cost"] == {"n_folds": 6, "n_fits": 1, "estimator_fits": 1}
    assert code["code"] == script.code
    assert error_of(error, "plan")["code"] == "unknown_id"
    assert output_dir.is_dir()
