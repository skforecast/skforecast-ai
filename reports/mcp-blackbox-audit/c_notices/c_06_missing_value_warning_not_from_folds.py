"""c-06: the missing-value warnings of create_cv do not match the backtest.

For a Ridge plan on a target with gaps, `create_cv` always gives the same
two notices: `MissingValuesNotice` (an estimator that accepts missing
values "lets `backtest` run on every fold") and a `UserWarning`
("`backtest()` of this plan raises when a test fold is predicted from one,
naming its dates"). What the backtest does differs from both:

Case A, `missing_dates.csv` (two missing months, both early in the first
training window): the backtest with Ridge runs on every fold, without
error. The notices pushed the agent to switch estimator or to stop and ask
the user for nothing.

Case B, `gaps.csv` (missing months and missing values inside the first
training window): the backtest fails with an opaque `execution_failed`;
`get_failure` says "All samples have been removed due to NaNs. Set
`forecaster.dropna_from_series = False`", a failure in training, not the
announced error that names the dates, and the advice it carries is
rejected by `refine_plan` (`dropna_from_series=False` with Ridge).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
RESULT = {}


async def strategy(c, name):
    _, p = await call(c, "profile", {"data_path": str(DATA / name), "target": "y"})
    _, plan = await call(c, "plan", {"profile_id": p["id"], "steps": 6})
    _, cv = await call(c, "create_cv", {"plan_id": plan["id"]})
    print(f"INPUT profile({name}) -> plan(steps=6) -> create_cv -> backtest")
    print("OBSERVED create_cv notices:")
    for n in cv["notices"]:
        print(f"  [{n['category']}] {n['message'][:240]}")
    warned = any(
        "raises when a test fold" in n["message"] for n in cv["notices"]
    )
    is_error, bt = await call(c, "backtest", {"cv_id": cv["id"]})
    return plan, warned, is_error, bt


async def main(c):
    _, warned_a, err_a, bt_a = await strategy(c, "missing_dates.csv")
    print("OBSERVED backtest (case A):",
          bt_a if err_a else f"ran, cost {bt_a['cost']}")

    plan_b, warned_b, err_b, bt_b = await strategy(c, "gaps.csv")
    print("OBSERVED backtest (case B):", bt_b)
    cause = ""
    if err_b and (bt_b.get("details") or {}).get("failure_id"):
        _, failure = await call(
            c, "get_failure", {"object_id": bt_b["details"]["failure_id"]}
        )
        cause = failure["text"].splitlines()[2].strip()
        print("OBSERVED get_failure (case B):", cause)
    ref_err, ref = await call(
        c, "refine_plan",
        {"plan_id": plan_b["id"], "overrides": {"dropna_from_series": False}},
    )
    print("OBSERVED refine_plan(dropna_from_series=False):", ref)
    RESULT.update(
        a_false_alarm=warned_a and not err_a,
        b_other_failure=warned_b and err_b
        and bt_b.get("code") == "execution_failed"
        and "All samples have been removed" in cause,
        b_advice_rejected=ref_err,
    )


run(main, allow_dir=DATA)
print(
    "EXPECTED: create_cv checks the folds it built (it knows the dates of the"
    " missing values and the window of the forecaster): no warning in case A;"
    " in case B, a notice (or an insufficient_data error at backtest) saying"
    " that no training row of the first window is complete, with the remedy"
    " (an estimator that accepts missing values, or a later"
    " initial_train_size)."
)
print("RESULT", RESULT)
if RESULT["a_false_alarm"] and RESULT["b_other_failure"]:
    print("REPRODUCED")
    sys.exit(0)
print("NOT REPRODUCED")
sys.exit(1)
