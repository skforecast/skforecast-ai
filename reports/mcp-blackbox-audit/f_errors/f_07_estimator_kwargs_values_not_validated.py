"""f-07: `plan` checks the names of `estimator_kwargs` but not their values.

`plan(estimator='Ridge', estimator_kwargs={'alpha': 'abc'})` returns a plan
(an unknown name such as 'foo' is rejected at once with field
`estimator_kwargs`), so the agent reports the plan as valid. The value
fails only when `forecast` or `backtest` fits the estimator:
`execution_failed`, "The generated script failed with
InvalidParameterError", field null, and the reason is in the traceback of
`get_failure`. Same for {'alpha': -1} or RandomForest {'n_estimators': 0}.
Expected: invalid_argument with field `estimator_kwargs` at `plan` time
(scikit-learn validates parameters without data), or at least the
message of the estimator in the error.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
PATH = str(DATA / "monthly.csv")


async def main(c):
    _, prof = await call(c, "profile", {"data_path": PATH, "target": "y"})
    base = {"profile_id": prof["id"], "steps": 12, "estimator": "Ridge"}
    _, bad_key = await call(c, "plan", {**base, "estimator_kwargs": {"foo": 1}})
    print("CONTRAST unknown name:", json.dumps(bad_key)[:200])
    args = {**base, "estimator_kwargs": {"alpha": "abc"}}
    print("INPUT plan:", json.dumps(args))
    perr, plan = await call(c, "plan", args)
    print("OBSERVED plan error:", perr)
    if perr:
        print("   ", json.dumps(plan)[:300])
        return False
    ferr, fc = await call(c, "forecast", {"plan_id": plan["id"]})
    print("OBSERVED forecast:", json.dumps(fc)[:400] if ferr else "success")
    print(
        "EXPECTED: plan fails with invalid_argument, field 'estimator_kwargs': "
        "\"The 'alpha' parameter of Ridge must be a float...\"."
    )
    return ferr and fc.get("code") == "execution_failed" and fc.get("field") is None


ok = run(main, allow_dir=DATA)
print("REPRODUCED" if ok else "NOT REPRODUCED")
sys.exit(0 if ok else 1)
