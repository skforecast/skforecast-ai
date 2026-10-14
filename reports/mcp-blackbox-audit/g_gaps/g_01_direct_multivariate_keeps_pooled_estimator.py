"""g-01: ForecasterDirectMultiVariate keeps the estimator chosen for the pooled data.

On wide data (three monthly series of 96 dates side by side) the profile
recommends LGBMRegressor "for a dataset of this size (288 observations)",
the 288 being the three series pooled. `plan(forecaster=
'ForecasterDirectMultiVariate')` keeps that estimator and that reason, but this
forecaster trains on one row per date (96 dates, 67 in the first training
window), and the same series alone gets Ridge ("the dataset is small (96
observations < 250)"). The default backtest then measures a model that
learned nothing: its predictions are the same in every fold (a constant per
step), with MASE 3.59, while Ridge on the same folds gets 0.49. No notice
says so, and the summary reads as a plain result of the plan the server
recommended for the forecaster the user chose.
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "a_happy_path" / "data"
ALLOW = Path(tempfile.mkdtemp(prefix="g01-allow-"))
shutil.copy(DATA / "multi_wide.csv", ALLOW / "stores.csv")
pd.read_csv(DATA / "multi_wide.csv")[["date", "store_a"]].to_csv(
    ALLOW / "store_a.csv", index=False
)
R = {}


def estimator_line(summary):
    return next(ln for ln in summary.splitlines() if "Estimator:" in ln and "." in ln)


async def main(c):
    _, single = await call(
        c, "profile", {"data_path": str(ALLOW / "store_a.csv"), "target": "store_a"}
    )
    R["single"] = estimator_line(single["summary"])
    args = {
        "data_path": str(ALLOW / "stores.csv"),
        "target": ["store_a", "store_b", "store_c"],
    }
    print("INPUT profile:", json.dumps(args))
    _, profile = await call(c, "profile", args)
    args = {
        "profile_id": profile["id"],
        "steps": 12,
        "forecaster": "ForecasterDirectMultiVariate",
    }
    print("INPUT plan:", json.dumps(args))
    _, plan = await call(c, "plan", args)
    R["plan_estimator"] = next(
        ln for ln in plan["summary"].splitlines() if ln.startswith("- Estimator:")
    )
    R["plan_reason"] = estimator_line(plan["summary"])
    R["plan_notices"] = [n["category"] for n in plan["notices"]]
    _, cv = await call(c, "create_cv", {"plan_id": plan["id"]})
    print("INPUT create_cv:", json.dumps({"plan_id": plan["id"]}))
    _, bt = await call(c, "backtest", {"cv_id": cv["id"]})
    print("INPUT backtest:", json.dumps({"cv_id": cv["id"]}))
    R["bt_notices"] = [n["category"] for n in bt["notices"]]
    R["metrics"] = pd.read_csv(bt["files"]["metrics"], index_col=0)
    R["pred"] = pd.read_csv(bt["files"]["predictions"], index_col=0)
    cands = [
        {"name": "dmv_plan_estimator", "config": {
            "forecaster": "ForecasterDirectMultiVariate"}},
        {"name": "dmv_ridge", "config": {
            "forecaster": "ForecasterDirectMultiVariate", "estimator": "Ridge"}},
    ]
    print("INPUT compare:", json.dumps({"cv_id": cv["id"], "candidates": cands}))
    _, cmp = await call(c, "compare", {"cv_id": cv["id"], "candidates": cands})
    R["board"] = pd.read_csv(cmp["files"]["leaderboard"], index_col=0)


run(main, allow_dir=ALLOW)

pred = R["pred"]
per_fold = [
    tuple(g["pred"].round(6).tolist()[:5]) for _, g in pred.groupby("fold")
]
same_every_fold = len(set(per_fold)) == 1
mase = float(R["metrics"]["mean_absolute_scaled_error"].iloc[0])
board = R["board"].set_index("name")["mean_absolute_scaled_error"]
single = R["single"]
print("OBSERVED single series alone:", single[single.find("Data:"):][:170])
print("OBSERVED plan:", R["plan_estimator"])
print("OBSERVED plan reason:", R["plan_reason"][:330])
print("OBSERVED plan notices:", R["plan_notices"], "backtest notices:", R["bt_notices"])
print("OBSERVED backtest MASE:", round(mase, 4))
print("OBSERVED first 4 predictions per fold:")
for fold, g in pred.groupby("fold"):
    print("   fold", fold, g["pred"].round(3).tolist()[:4])
print("OBSERVED first 5 predictions identical in every fold (the last fold has 5):",
      same_every_fold)
print("OBSERVED compare MASE on the same folds:", board.round(4).to_dict())
print(
    "EXPECTED: an estimator chosen for the rows the forecaster trains on (one "
    "per date, so Ridge as for the series alone), or at least a notice that "
    "LGBMRegressor on 67 training dates learns no split; not a 288-observation "
    "reason and a backtest whose predictions repeat in every fold."
)
if (
    "LGBMRegressor" in R["plan_estimator"]
    and "288 observations" in R["plan_reason"]
    and "Ridge" in R["single"]
    and same_every_fold
    and board["dmv_ridge"] < board["dmv_plan_estimator"] / 3
):
    print("REPRODUCED")
    sys.exit(0)
print("NOT REPRODUCED")
sys.exit(1)
