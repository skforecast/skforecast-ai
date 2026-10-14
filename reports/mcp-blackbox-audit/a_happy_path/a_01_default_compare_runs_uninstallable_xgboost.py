"""a-01: a default `compare` on several series always runs XGBRegressor.

The profile of a multi-series dataset proposes XGBRegressor as an alternative
estimator and `compare` without `candidates` runs it, although `xgboost` is
not a dependency of skforecast-ai nor of any of its extras. In a standard
install the candidate always fails and is ranked last, while the foundation
candidate whose backend is missing is left out with a notice instead.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
RESULT = {}


async def main(c):
    args = {
        "data_path": str(DATA / "multi_wide.csv"),
        "target": ["store_a", "store_b", "store_c"],
    }
    print("INPUT profile:", json.dumps(args))
    _, profile = await call(c, "profile", args)
    _, plan = await call(c, "plan", {"profile_id": profile["id"], "steps": 12})
    _, cv = await call(c, "create_cv", {"plan_id": plan["id"]})
    print("INPUT compare:", json.dumps({"cv_id": cv["id"]}))
    _, cmp = await call(c, "compare", {"cv_id": cv["id"]})
    board = pd.read_csv(cmp["files"]["leaderboard"])
    summary = profile["summary"]
    start = summary.find("Alternative estimators")
    print("OBSERVED profile:", summary[start:start + 50])
    print("OBSERVED create_cv cost:", json.dumps(cv["cost"]))
    print("OBSERVED leaderboard:")
    print(board[["rank", "name", "estimator", "error"]].to_string())
    print("OBSERVED notices:", [n["category"] for n in cmp["notices"]])
    for n in cmp["notices"]:
        if n["category"] == "MissingBackendWarning":
            print("  ", n["message"])
    failed = board[board["estimator"].eq("XGBRegressor")]
    RESULT["failed_xgb"] = bool(
        len(failed) and "xgboost" in str(failed["error"].iloc[0])
    )
    RESULT["foundation_left_out"] = any(
        n["category"] == "MissingBackendWarning" for n in cmp["notices"]
    )


run(main, allow_dir=DATA)
print(
    "EXPECTED: candidates whose package is missing are handled alike: the "
    "default candidates leave out an estimator that is not installed (as they "
    "do for ForecasterFoundation, with a notice), or the profile does not "
    "propose it."
)
if importlib.util.find_spec("xgboost") is None and RESULT.get("failed_xgb"):
    print("REPRODUCED")
    sys.exit(0)
print("NOT REPRODUCED")
sys.exit(1)
