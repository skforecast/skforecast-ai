"""b-04: missing values in an exogenous column pass every check and then fail
the run with an opaque `execution_failed`.

The file has a numeric exogenous column with 8 empty ('N/A') cells. `profile`
lists it only inside `summary` ("Missing in exog"), with no notice; `plan`
and `create_cv` add none either (for the same problem in the target,
`create_cv` warns that the backtest raises). The recommended plan (Ridge)
fails in `backtest` with `execution_failed` and a `get_failure` saying only
"ValueError: Input contains NaN.", without naming the column. The plan's own
advice ("Use dropna_from_series=True or a NaN-tolerant estimator") is half
wrong: with `dropna_from_series: true` it fails the same way.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"


async def run_backtest(c, profile_id, plan_args):
    _, pl = await call(c, "plan", {"profile_id": profile_id, "steps": 6, **plan_args})
    advice = re.findall(r"\[informational\][^\n]*", pl["summary"])
    _, cv = await call(c, "create_cv", {"plan_id": pl["id"]})
    err, bt = await call(c, "backtest", {"cv_id": cv["id"]})
    failure = None
    if err and bt.get("code") == "execution_failed":
        _, f = await call(c, "get_failure", {"object_id": bt["details"]["failure_id"]})
        failure = re.search(r"\n\n  (.*?)\n", f["text"]).group(1)
    print(f"INPUT plan {json.dumps(plan_args)} -> create_cv -> backtest")
    print("  OBSERVED plan advice:", advice)
    print("  OBSERVED plan notices:", [n["category"] for n in pl["notices"]])
    print("  OBSERVED create_cv notices:", [n["category"] for n in cv["notices"]])
    print("  OBSERVED backtest:", bt.get("code") if err else "ok", "|", failure)
    return failure, pl["notices"] + cv["notices"]


async def main(c):
    args = {
        "data_path": str(DATA / "text_exog.csv"),
        "target": "y",
        "exog_columns": ["x_na"],
    }
    print("INPUT profile", json.dumps(args))
    _, p = await call(c, "profile", args)
    print("OBSERVED profile:", re.findall(r"Missing in exog:[^\n]*", p["summary"]))
    print("OBSERVED profile notices:", [n["message"] for n in p["notices"]])
    f1, n1 = await run_backtest(c, p["id"], {})
    f2, n2 = await run_backtest(c, p["id"], {"dropna_from_series": True})
    print(
        "EXPECTED: a DataProfileWarning for the missing exogenous values at "
        "`profile`, and a notice at `create_cv` (as for a target with missing "
        "values) naming the column and the estimators that accept them; or "
        "an invalid_argument naming 'x_na', as `forecast` does for a missing "
        "value in the file of `exog_path`. Not an execution_failed that "
        "survives the advice of the plan."
    )
    warned = any(
        re.search(r"x_na|exogenous", n["message"])
        and re.search(r"missing", n["message"], re.I)
        for n in p["notices"] + n1 + n2
    )
    return f1 == f2 == "ValueError: Input contains NaN." and not warned


if __name__ == "__main__":
    ok = run(main, allow_dir=DATA)
    print("REPRODUCED" if ok else "NOT REPRODUCED")
    sys.exit(0 if ok else 1)
