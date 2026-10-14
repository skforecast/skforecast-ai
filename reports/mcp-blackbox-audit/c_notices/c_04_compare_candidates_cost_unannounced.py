"""c-04: a compare of 78 estimator fits runs with no cost warning at all.

SKILL.md: "Above 50 estimator fits ... a run gets a `LongTrainingWarning`
notice" and "Before an expensive run (a `backtest` or a `compare` above
those thresholds), stop". With `candidates`, no tool reports the cost of a
`compare` before it runs (`create_cv` only estimates the one without
candidates: 48 here, below the threshold, so no CostNotice). The compare
then runs 78 estimator fits (its own `cost.estimator_fits`) and its
response has no LongTrainingWarning nor CostNotice: the agent is never told
it crossed the threshold, before or after. (A single candidate above 50
fits does get the LongTrainingWarning of skforecast: the threshold is
applied per candidate, while the SKILL.md adds up the inference windows
over the candidates of a compare.)
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
RESULT = {}
CANDIDATES = [
    {"name": "direct_a", "config": {"forecaster": "ForecasterDirect", "lags": 3}},
    {"name": "direct_b", "config": {"forecaster": "ForecasterDirect", "lags": 6}},
    {"name": "rec", "config": {}},
]
COST = ("CostNotice", "CompareCostNotice", "LongTrainingWarning")


async def main(c):
    path = str(DATA / "monthly.csv")
    _, p = await call(c, "profile", {"data_path": path, "target": "y"})
    _, plan = await call(c, "plan", {"profile_id": p["id"], "steps": 6})
    _, cv = await call(
        c, "create_cv",
        {"plan_id": plan["id"], "initial_train_size": 84, "refit": True},
    )
    print("INPUT plan(steps=6) -> create_cv(initial_train_size=84, refit=true)")
    print("OBSERVED create_cv cost:", cv["cost"],
          "notices:", [n["category"] for n in cv["notices"]])
    print("INPUT compare(candidates=", json.dumps(CANDIDATES), ")")
    _, cmp = await call(c, "compare", {"cv_id": cv["id"], "candidates": CANDIDATES})
    print("OBSERVED compare cost:", cmp["cost"])
    print("OBSERVED compare notices:", [n["category"] for n in cmp["notices"]])
    RESULT.update(
        no_pre_warning=not any(n["category"] in COST for n in cv["notices"]),
        above=cmp["cost"]["estimator_fits"] > 50,
        no_post_warning=not any(n["category"] in COST for n in cmp["notices"]),
    )


run(main, allow_dir=DATA)
print(
    "EXPECTED: a compare whose estimator_fits (78) is above 50 carries a"
    " LongTrainingWarning, as a backtest of 51 fits does; better, a way to know"
    " the cost of a list of candidates before running it (a dry run, or the"
    " check done before the first candidate starts)."
)
print("RESULT", RESULT)
if all(RESULT.values()):
    print("REPRODUCED")
    sys.exit(0)
print("NOT REPRODUCED")
sys.exit(1)
