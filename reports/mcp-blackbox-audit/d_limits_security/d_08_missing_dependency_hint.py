"""d-08: `missing_dependency` of an estimator has no hint, and says pip only.

The schema lists CatBoostRegressor and XGBRegressor among the estimators.
When their package is not installed, the error has `hint: null` and the
message says "(pip install ...)". The skill says: "`missing_dependency`:
Tell the user which package to install; `hint` says how, for pip and for
uvx." A server launched with uvx is not fixed by pip install.
Skipped (NOT REPRODUCED) when both packages are installed.
"""

import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
MISSING = [name for name, mod in (("CatBoostRegressor", "catboost"),
                                  ("XGBRegressor", "xgboost"))
           if importlib.util.find_spec(mod) is None]
OUT = {}


async def main(c):
    _, p = await call(c, "profile",
                      {"data_path": str(DATA / "monthly.csv"), "target": "y"})
    for est in MISSING:
        args = {"profile_id": p["id"], "steps": 12, "estimator": est}
        err, pl = await call(c, "plan", args)
        if err:
            OUT[est] = (args, "plan", pl)
            continue
        OUT[est] = (args, "forecast",
                    (await call(c, "forecast", {"plan_id": pl["id"]}))[1])


if not MISSING:
    print("catboost and xgboost are installed: nothing to check")
    print("NOT REPRODUCED")
    sys.exit(1)
run(main, allow_dir=DATA)

bad = []
for est, (args, tool, payload) in OUT.items():
    print("INPUT plan", json.dumps(args), "then", tool)
    print("OBSERVED", tool, json.dumps(payload, indent=1))
    if (isinstance(payload, dict) and payload.get("code") == "missing_dependency"
            and not payload.get("hint")):
        bad.append(est)
print("EXPECTED: `hint` with the install command for pip and for uvx, as the")
print("skill says (or the error at `plan`, where the estimator is chosen).")
if bad:
    print("REPRODUCED")
    sys.exit(0)
print("NOT REPRODUCED")
sys.exit(1)
