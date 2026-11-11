# Integration test: the notice of an estimator that is not the one of the rules

import anyio
import numpy as np
from mcp import Client

from skforecast_ai.mcp import create_server

from .fixtures_mcp import content_of, df_h2o_csv, write_csv

NOTICE_MESSAGE = (
    "This {run} ran the estimator 'RandomForestRegressor', not the one the "
    "rules recommend for ForecasterRecursive on these data ('Ridge'). It was "
    "passed to `plan`, `refine_plan` or the `candidates` of `compare`, and it "
    "is the estimator that accepts missing values that the advice on the "
    "missing values of the data names. "
    "Say in your answer that the estimator is not the recommended one, which "
    "one the rules recommend and why it was changed."
)


def _notices_of(result, category):
    """
    Return the notices of a tool result with the category `category`.
    """
    return [notice for notice in result["notices"] if notice["category"] == category]


def test_server_estimator_notice_when_plan_refined_to_the_estimator_of_the_missing_values(
    tmp_path,
):
    """
    Test the flow of the server on the last 120 months of h2o with the target
    missing at the position 20 (inside the initial training window, so the
    backtest runs): `create_cv` offers RandomForestRegressor for the missing
    values, `backtest` and `forecast` of the plan of the rules carry no
    EstimatorNotRecommendedNotice, and after `refine_plan` to that estimator
    `backtest`, `forecast` and `forecast` with `test_size` carry exactly one,
    that names both estimators and the missing values.
    """
    data = df_h2o_csv.iloc[-120:].reset_index(drop=True)
    data.loc[20, "x"] = np.nan
    path = write_csv(tmp_path, "monthly.csv", data)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    async def flow():
        async with Client(server) as client:

            async def call(name, args):
                return content_of(await client.call_tool(name, args))

            profile = await call("profile", {"data_path": path, "target": "x"})
            plan = await call("plan", {"profile_id": profile["id"], "steps": 6})
            cv = await call("create_cv", {"plan_id": plan["id"]})
            original = {
                "cv": cv,
                "backtest": await call("backtest", {"cv_id": cv["id"]}),
                "forecast": await call("forecast", {"plan_id": plan["id"]}),
            }
            refined_plan = await call(
                "refine_plan",
                {
                    "plan_id": plan["id"],
                    "overrides": {"estimator": "RandomForestRegressor"},
                },
            )
            refined_cv = await call("create_cv", {"plan_id": refined_plan["id"]})
            refined = {
                "backtest": await call("backtest", {"cv_id": refined_cv["id"]}),
                "forecast": await call("forecast", {"plan_id": refined_plan["id"]}),
                "evaluation": await call(
                    "forecast", {"plan_id": refined_plan["id"], "test_size": 6}
                ),
            }
            return original, refined

    original, refined = anyio.run(flow)

    offered = _notices_of(original["cv"], "MissingValuesNotice")
    assert len(offered) == 1
    assert "'RandomForestRegressor'" in offered[0]["message"]
    for run in ("backtest", "forecast"):
        categories = [notice["category"] for notice in original[run]["notices"]]
        assert "EstimatorNotRecommendedNotice" not in categories

    for key, run in (
        ("backtest", "backtest"), ("forecast", "forecast"), ("evaluation", "forecast")
    ):
        assert _notices_of(refined[key], "EstimatorNotRecommendedNotice") == [
            {
                "source": "plan",
                "category": "EstimatorNotRecommendedNotice",
                "message": NOTICE_MESSAGE.format(run=run),
                "count": 1,
            }
        ]
