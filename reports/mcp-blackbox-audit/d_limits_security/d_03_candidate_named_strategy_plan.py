"""d-03: `compare` accepts a candidate named 'Strategy plan'.

The skill tells the agent that the row 'Strategy plan' is the plan the
strategy was created for, and to report that row as the user's plan. The
baseline names are reserved, but 'Strategy plan' is not: a candidate of the
agent's own (here LGBMRegressor) takes that name, while the real plan of the
strategy (Ridge with lags 3, from refine_plan) is not in the leaderboard.
"""

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
OUT = {}
CANDIDATES = [
    {"name": "Strategy plan",
     "config": {"estimator": "LGBMRegressor",
                "estimator_kwargs": {"n_estimators": 10, "verbose": -1}}},
    {"name": "ridge", "config": {"estimator": "Ridge"}},
]


async def main(c):
    _, p = await call(c, "profile",
                      {"data_path": str(DATA / "monthly.csv"), "target": "y"})
    _, pl = await call(c, "plan", {"profile_id": p["id"], "steps": 12})
    _, rp = await call(c, "refine_plan",
                       {"plan_id": pl["id"], "overrides": {"lags": 3}})
    _, cv = await call(c, "create_cv", {"plan_id": rp["id"]})
    OUT["reserved"] = await call(c, "compare", {"cv_id": cv["id"], "candidates": [
        {"name": "Baseline (seasonal naive)", "config": {"estimator": "Ridge"}}]})
    OUT["args"] = {"cv_id": cv["id"], "candidates": CANDIDATES}
    OUT["compare"] = await call(c, "compare", OUT["args"])


run(main, allow_dir=DATA)

print("INPUT refine_plan overrides {'lags': 3} -> create_cv -> compare",
      json.dumps(OUT["args"]))
is_error, cmp = OUT["compare"]
if is_error:
    print("OBSERVED error", cmp)
    print("NOT REPRODUCED")
    sys.exit(1)
board = pd.read_csv(cmp["files"]["leaderboard"])
print("OBSERVED leaderboard:")
print(board[["rank", "name", "forecaster", "estimator"]].to_string(index=False))
summary = cmp["summary"]
i = summary.find("<deterministic_summary>")
print("OBSERVED summary:", summary[i:i + 700])
print("CONTRAST reserved baseline name ->",
      json.dumps(OUT["reserved"][1])[:220])
print("EXPECTED: invalid_argument, 'Strategy plan' is reserved like the baseline")
print("names, so the row the skill tells the agent to report as the user's plan")
print("is never a candidate of the agent.")
row = board[board["name"] == "Strategy plan"]
if len(row) == 1 and row["estimator"].iloc[0] == "LGBMRegressor":
    print("REPRODUCED")
    sys.exit(0)
print("NOT REPRODUCED")
sys.exit(1)
