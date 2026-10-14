"""e-03: `missing_dependency` of an estimator package has no hint and a bad field.

SKILL.md, table of errors: "`missing_dependency` | Tell the user which
package to install; `hint` says how, for pip and for uvx."

For a foundation model the error has that hint and `field: plan_id`. For a
machine learning estimator whose package is not installed (XGBRegressor or
CatBoostRegressor here) `plan` accepts it without a notice, and `forecast`
then fails with `hint: null`, a message that only says `pip install ...`
(wrong for a server started with uvx) and `field: "estimator"`, which is
not an argument of `forecast` (its arguments are plan_id, test_size and
exog_path).

Run from the repository root:
    python reports/mcp-blackbox-audit/e_skill_coherence/e_03_missing_dependency_ml_estimator.py
"""

import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
missing = [
    name for name, module in (("XGBRegressor", "xgboost"),
                              ("CatBoostRegressor", "catboost"))
    if importlib.util.find_spec(module) is None
]
if not missing:
    print("xgboost and catboost are installed: cannot reproduce here.")
    print("NOT REPRODUCED")
    sys.exit(1)
estimator = missing[0]
out = {}


async def main(c):
    _, prof = await call(
        c, "profile", {"data_path": str(DATA / "single.csv"), "target": "y"}
    )
    args = {"profile_id": prof["id"], "steps": 12, "estimator": estimator}
    print("INPUT plan", json.dumps(args))
    is_error, plan = await call(c, "plan", args)
    out["plan_error"] = is_error
    out["plan_notices"] = [] if is_error else plan["notices"]
    print("OBSERVED plan: error =", is_error, "notices =", out["plan_notices"])
    print("INPUT forecast", json.dumps({"plan_id": plan["id"]}))
    is_error, err = await call(c, "forecast", {"plan_id": plan["id"]})
    out["forecast"] = (is_error, err)
    print("OBSERVED forecast:", json.dumps(err))


run(main, allow_dir=DATA)

print(
    "EXPECTED: code 'missing_dependency' with a `hint` that says how to "
    "install the package for pip and for uvx, and `field` naming an argument "
    "of `forecast` ('plan_id', as for a foundation model); ideally a notice "
    "on `plan` that the estimator cannot run where the server runs."
)
is_error, err = out["forecast"]
if (is_error and isinstance(err, dict) and err.get("code") == "missing_dependency"
        and (err.get("hint") is None or err.get("field") == "estimator")):
    print("REPRODUCED")
    sys.exit(0)
print("NOT REPRODUCED")
sys.exit(1)
