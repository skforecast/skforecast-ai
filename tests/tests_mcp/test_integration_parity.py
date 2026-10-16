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

from ..fixtures_assistant import df_no_sundays
from ..fixtures_datasets import df_items_sales_long, df_items_sales_wide
from .fixtures_mcp import (
    content_of,
    csv_of,
    df_h2o_csv,
    error_of,
    text_of,
    write_csv,
)

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


@pytest.mark.slow
def test_server_workflow_when_daily_data_closed_on_sundays(tmp_path):
    """
    Test the flow of the server on a year of daily sales of a shop closed on
    Sundays, which had no frequency before (the cause of finding V14 of the
    MCP audit): `profile` infers 'D' and warns about the 51 Sundays missing,
    which a forecast predicts too and a business closed on them can fill
    with 0 after asking the user; `plan` and `forecast` run; `backtest` says
    that the Sundays asfreq() restores fall in its test folds, with the same
    advice; and the script of `get_code` run as a file gives the predictions
    of `forecast`.
    """
    path = write_csv(tmp_path, "shop.csv", df_no_sundays)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    async def flow():
        async with Client(server) as client:
            profile = content_of(
                await client.call_tool(
                    "profile", {"data_path": path, "target": "sales"}
                )
            )
            plan = content_of(
                await client.call_tool(
                    "plan", {"profile_id": profile["id"], "steps": 14}
                )
            )
            cv = content_of(
                await client.call_tool("create_cv", {"plan_id": plan["id"]})
            )
            backtest = error_of(
                await client.call_tool("backtest", {"cv_id": cv["id"]}), "backtest"
            )
            forecast = content_of(
                await client.call_tool("forecast", {"plan_id": plan["id"]})
            )
            code = content_of(
                await client.call_tool("get_code", {"object_id": forecast["id"]})
            )["code"]
            return profile, backtest, forecast, code

    profile, backtest, forecast, code = anyio.run(flow)

    missing = (
        "Missing timestamps: 51 timestamps of frequency 'D' are missing from "
        "the date range, all of them on Sundays, when the data never has a "
        "date. asfreq() inserts them as rows with missing values, and a "
        "forecast predicts Sundays too. If the business is closed on Sundays, "
        "they can be filled with 0 in the data, after asking the user."
    )
    assert "- Frequency: D\n" in profile["summary"]
    assert "- Index irregularities: gaps in the index\n" in profile["summary"]
    assert profile["notices"] == [
        {
            "source": "data",
            "category": "DataProfileWarning",
            "message": missing,
            "count": 1,
        }
    ]
    assert backtest["code"] == "invalid_argument"
    assert backtest["message"] == (
        "The target has 15 missing value(s) in the test folds (2023-09-17 "
        "00:00:00, 2023-09-24 00:00:00, 2023-10-01 00:00:00, 2023-10-08 "
        "00:00:00, 2023-10-15 00:00:00 and 10 more), counting the missing "
        "timestamps that asfreq() restores: all of them on Sundays, when the "
        "target never has a value. skforecast cannot compute the metrics on "
        "them, whatever the estimator. If the business is closed on Sundays, "
        "fill them with 0 in the data, after asking the user; otherwise, "
        "impute the target, or evaluate on dates without missing values."
    )
    assert [notice["category"] for notice in forecast["notices"]] == [
        "UserWarning", "MissingValuesWarning", "MissingValuesWarning",
        "MissingValuesWarning",
    ]
    predictions = pd.read_csv(forecast["files"]["predictions"], index_col=0)
    assert list(predictions.index[:2]) == ["2023-12-31", "2024-01-01"]
    assert "data = data.asfreq('D')\n" in code
    standalone = _run_as_file(code, tmp_path)
    assert len(standalone) == len(predictions) == 14
    np.testing.assert_allclose(
        standalone["pred"].to_numpy(), predictions["pred"].to_numpy(), rtol=1e-6
    )
