"""c-01: create_cv says LGBMRegressor lets backtest run; it cannot.

`nan_target.csv` is a monthly series of 120 values with three missing target
values, one of them (2017-07-01) inside the test folds of the default
strategy. `create_cv` of the recommended plan (Ridge) carries a
`MissingValuesNotice` and a `UserWarning` saying that an estimator that
accepts missing values ('LGBMRegressor', with `refine_plan` and a new
`create_cv`) "lets `backtest` run on every fold". An agent that follows it
gets a clean `create_cv` (no notice at all) and then a `backtest` error:
"skforecast cannot compute the metrics on them, whatever the estimator".
The server already knows at `create_cv` that a test fold holds the missing
value (the backtest names its date before running anything).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
RESULT = {}


async def main(c):
    path = str(DATA / "nan_target.csv")
    print(f"INPUT profile(data_path={path!r}, target='y') -> plan(steps=6)")
    _, p = await call(c, "profile", {"data_path": path, "target": "y"})
    _, plan = await call(c, "plan", {"profile_id": p["id"], "steps": 6})
    _, cv = await call(c, "create_cv", {"plan_id": plan["id"]})
    advice = [n for n in cv["notices"] if "LGBMRegressor" in n["message"]]
    print("OBSERVED create_cv (Ridge) notices that name LGBMRegressor:")
    for n in advice:
        print(f"  [{n['category']}] {n['message']}")

    print("INPUT refine_plan(overrides={'estimator': 'LGBMRegressor'})")
    print("      -> create_cv -> backtest, as the notice says")
    _, lgbm = await call(
        c, "refine_plan",
        {"plan_id": plan["id"], "overrides": {"estimator": "LGBMRegressor"}},
    )
    _, cv2 = await call(c, "create_cv", {"plan_id": lgbm["id"]})
    print("OBSERVED create_cv (LGBMRegressor) notices:",
          [n["category"] for n in cv2["notices"]])
    is_error, bt = await call(c, "backtest", {"cv_id": cv2["id"]})
    print("OBSERVED backtest:", json.dumps(bt, indent=1)[:1500])
    RESULT.update(
        advice=bool(advice),
        cv2_silent=cv2["notices"] == [],
        bt_failed=is_error and "whatever the estimator" in bt.get("message", ""),
    )


run(main, allow_dir=DATA)
print(
    "EXPECTED: create_cv says the missing value 2017-07-01 falls in a test fold"
    " and no estimator avoids it (a later initial_train_size, or ask the user),"
    " instead of promising that LGBMRegressor lets backtest run on every fold;"
    " or create_cv of the LGBMRegressor plan warns before the backtest fails."
)
print("RESULT", RESULT)
if RESULT["advice"] and RESULT["cv2_silent"] and RESULT["bt_failed"]:
    print("REPRODUCED")
    sys.exit(0)
print("NOT REPRODUCED")
sys.exit(1)
