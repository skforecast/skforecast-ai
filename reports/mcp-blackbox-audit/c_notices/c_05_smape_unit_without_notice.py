"""c-05: sMAPE is a percentage, MAPE a fraction; only MAPE gets a notice.

A plan with `metric: ["mean_absolute_percentage_error",
"symmetric_mean_absolute_percentage_error"]` on a smooth monthly series
gets, in the same backtest, MAPE 0.0113 and sMAPE 1.1364: about 100 times
apart, because skforecast returns sMAPE already multiplied by 100. The
only unit notice is `MetricUnitNotice` for MAPE ("a fraction, not a
percentage ... Multiply it by 100"). Nothing tells the agent the unit of
sMAPE, so the natural reading by analogy (both "percentage errors", one
told to be a fraction) reports sMAPE as 113.6 %, or reports both with
units 100 times apart without knowing it.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
RESULT = {}
METRICS = [
    "mean_absolute_percentage_error",
    "symmetric_mean_absolute_percentage_error",
]


async def main(c):
    path = str(DATA / "monthly.csv")
    _, p = await call(c, "profile", {"data_path": path, "target": "y"})
    _, plan = await call(
        c, "plan", {"profile_id": p["id"], "steps": 12, "metric": METRICS}
    )
    _, cv = await call(c, "create_cv", {"plan_id": plan["id"]})
    _, bt = await call(c, "backtest", {"cv_id": cv["id"]})
    print(f"INPUT plan(steps=12, metric={METRICS}) -> create_cv -> backtest")
    metrics = pd.read_csv(bt["files"]["metrics"], index_col=0)
    print("OBSERVED files.metrics:")
    print(metrics.to_string())
    print("OBSERVED notices:")
    for n in bt["notices"]:
        print(f"  [{n['category']}] {n['message']}")
    mape = float(metrics[METRICS[0]].iloc[0])
    smape = float(metrics[METRICS[1]].iloc[0])
    smape_named = any(
        "symmetric_mean_absolute_percentage_error" in n["message"]
        for n in bt["notices"]
    )
    RESULT.update(
        scale_gap=smape / mape > 50,
        mape_notice=any(n["category"] == "MetricUnitNotice" for n in bt["notices"]),
        smape_silent=not smape_named,
    )


run(main, allow_dir=DATA)
print(
    "EXPECTED: a unit notice for symmetric_mean_absolute_percentage_error too"
    " (it is already a percentage, from 0 to 200: write 1.14 as 1.14 %), or"
    " the same unit for both metrics; the metric schema could say it as well."
)
print("RESULT", RESULT)
if all(RESULT.values()):
    print("REPRODUCED")
    sys.exit(0)
print("NOT REPRODUCED")
sys.exit(1)
