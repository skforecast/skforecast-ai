# Integration test: the MCP server gives the results of the Python API

import subprocess
import sys
import textwrap

import anyio
import numpy as np
import pandas as pd
import pytest
from mcp import Client

from skforecast_ai import ForecastingAssistant
from skforecast_ai.mcp import create_server

from ..fixtures_datasets import df_items_sales_long, df_items_sales_wide
from .fixtures_mcp import content_of, csv_of, df_h2o_csv, text_of, write_csv

CANDIDATES = [
    {"name": "ridge", "config": {"estimator": "Ridge"}},
    {"name": "lgbm", "config": {"estimator": "LGBMRegressor", "lags": 7}},
]


def _run_as_file(code: str, workdir) -> pd.DataFrame:
    """
    Run a script in a fresh interpreter from `workdir` and return its
    `predictions`.
    """
    script = workdir / "script.py"
    script.write_text(code)
    export = workdir / "exported.csv"
    wrapper = workdir / "run.py"
    wrapper.write_text(
        textwrap.dedent(f"""
        import runpy
        import pandas as pd
        namespace = runpy.run_path({str(script)!r})
        pd.DataFrame(namespace["predictions"]).to_csv({str(export)!r})
    """)
    )
    proc = subprocess.run(
        [sys.executable, str(wrapper)],
        cwd=workdir,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert proc.returncode == 0, proc.stderr[-3000:]

    return pd.read_csv(export, index_col=0)


@pytest.mark.slow
@pytest.mark.parametrize(
    "frame, arguments, steps",
    [
        (df_h2o_csv, {"target": "x"}, 12),
        (df_items_sales_long, {"target": "value", "series_id_column": "series"}, 7),
        (
            df_items_sales_wide.reset_index(),
            {"target": ["item_1", "item_2", "item_3"]},
            7,
        ),
    ],
    ids=["h2o", "items_sales long", "items_sales wide"],
)
def test_server_workflow_matches_python_api_and_scripts(
    tmp_path, frame, arguments, steps
):
    """
    Test that profile -> plan -> create_cv -> backtest -> compare -> forecast
    through the server gives the predictions and metrics of the Python API,
    and that the scripts of `get_code` reproduce them run as files.
    """
    path = write_csv(tmp_path, "data.csv", frame)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    async def flow():
        async with Client(server) as client:

            async def call(name, args):
                return content_of(await client.call_tool(name, args))

            profile = await call("profile", {"data_path": path, **arguments})
            plan = await call("plan", {"profile_id": profile["id"], "steps": steps})
            cv = await call("create_cv", {"plan_id": plan["id"]})
            backtest = await call("backtest", {"cv_id": cv["id"]})
            comparison = await call(
                "compare", {"cv_id": cv["id"], "candidates": CANDIDATES}
            )
            forecast = await call(
                "forecast", {"plan_id": comparison["links"]["best_plan_id"]}
            )
            evaluation = await call(
                "forecast", {"plan_id": plan["id"], "test_size": steps}
            )
            codes = {
                key: (await call("get_code", {"object_id": obj["id"]}))["code"]
                for key, obj in (
                    ("backtest", backtest),
                    ("forecast", forecast),
                    ("evaluation", evaluation),
                )
            }
            return backtest, comparison, forecast, evaluation, codes

    backtest, comparison, forecast, evaluation, codes = anyio.run(flow)

    assistant = ForecastingAssistant()
    profile = assistant.profile(path, **arguments)
    plan = assistant.plan(profile=profile, steps=steps)
    cv = assistant.create_cv(profile=profile, plan=plan)
    expected_backtest = assistant.backtest(
        data=path, cv=cv, profile=profile, plan=plan, show_progress=False
    )
    expected_comparison = assistant.compare(
        data=path,
        cv=cv,
        profile=profile,
        show_progress=False,
        candidates=[(c["name"], dict(c["config"])) for c in CANDIDATES],
    )
    expected_forecast = assistant.forecast(
        data=path, profile=profile, plan=expected_comparison.best_candidate.plan
    )
    expected_evaluation = assistant.forecast(
        data=path, profile=profile, plan=plan, test_size=steps
    )

    assert (
        text_of(backtest["files"]["predictions"])
        == csv_of(expected_backtest.predictions)
    )
    assert text_of(backtest["files"]["metrics"]) == csv_of(expected_backtest.metrics)
    assert (
        text_of(comparison["files"]["leaderboard"])
        == csv_of(expected_comparison.results)
    )
    assert (
        text_of(forecast["files"]["predictions"])
        == csv_of(expected_forecast.predictions)
    )
    assert (
        text_of(evaluation["files"]["metrics"]) == csv_of(expected_evaluation.metrics)
    )
    for key, expected in (
        ("backtest", expected_backtest),
        ("forecast", expected_forecast),
        ("evaluation", expected_evaluation),
    ):
        standalone = _run_as_file(codes[key], tmp_path)
        assert len(standalone) == len(expected.predictions)
        np.testing.assert_allclose(
            standalone["pred"].to_numpy(),
            expected.predictions["pred"].to_numpy(),
            rtol=1e-6,
        )
