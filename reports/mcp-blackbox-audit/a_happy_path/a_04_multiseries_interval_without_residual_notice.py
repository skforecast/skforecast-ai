"""a-04: multi-series intervals get no residual notice; points fall outside.

For one series, `create_cv` of a plan with an interval warns when the first
training window leaves fewer than 100 rows of residuals ("the intervals tend
to be too narrow"). The same series, with the same plan, inside a
multi-series dataset gets no notice at all, although the residuals are per
series and several point predictions of the backtest lie outside their own
80 % interval (`pred < lower_bound`). An agent reads the bounds as reliable.
"""

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
RESULT = {}
PLAN = {
    "steps": 12,
    "interval": [0.1, 0.9],
    "estimator": "Ridge",
    "window_features": [{"stats": ["mean"], "window_size": 24}],
}


async def case(c, name, profile_args):
    _, p = await call(
        c, "profile", {"data_path": str(DATA / "multi_wide.csv"), **profile_args}
    )
    _, plan = await call(c, "plan", {"profile_id": p["id"], **PLAN})
    _, cv = await call(c, "create_cv", {"plan_id": plan["id"]})
    _, bt = await call(c, "backtest", {"cv_id": cv["id"]})
    pred = pd.read_csv(bt["files"]["predictions"])
    outside = pred[(pred.pred < pred.lower_bound) | (pred.pred > pred.upper_bound)]
    residual_notice = [
        n["message"][:140] for n in cv["notices"] if "residual" in n["message"]
    ]
    print(f"OBSERVED [{name}] create_cv notices about residuals:", residual_notice)
    print(f"OBSERVED [{name}] rows with pred outside [lower, upper]:",
          len(outside), "of", len(pred))
    print(outside.head(3).to_string())
    RESULT[name] = (bool(residual_notice), len(outside))


async def main(c):
    print("INPUT plan:", json.dumps(PLAN), "then create_cv and backtest")
    await case(c, "one series", {"target": "store_a", "exog_columns": []})
    await case(c, "three series", {"target": ["store_a", "store_b", "store_c"]})


run(main, allow_dir=DATA)
print(
    "EXPECTED: the multi-series strategy carries the same notice as the single "
    "series (fewer than 100 residual rows per series), so the agent reads the "
    "intervals with caution."
)
single, multi = RESULT["one series"], RESULT["three series"]
if single[0] and not multi[0] and multi[1] > 0:
    print("REPRODUCED")
    sys.exit(0)
print("NOT REPRODUCED")
sys.exit(1)
