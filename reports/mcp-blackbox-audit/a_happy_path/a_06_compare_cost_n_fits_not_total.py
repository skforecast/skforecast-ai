"""a-06: `cost.n_fits` of a `compare` is the plan's, not the total.

SKILL.md: "`compare` runs every candidate on the same folds, so it costs
about the sum of theirs (its response reports the totals)". Its `cost` adds
up `estimator_fits` over the candidates, but `n_fits` ("trainings of the
forecaster") stays the value of the plan of the strategy: two candidates
trained once each report `n_fits: 1`, and the default comparison, whose
summary says ForecasterStats alone is trained 3 times, also reports 1.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
RESULT = {}


async def main(c):
    _, p = await call(
        c, "profile", {"data_path": str(DATA / "monthly.csv"), "target": "sales"}
    )
    _, plan = await call(c, "plan", {"profile_id": p["id"], "steps": 12})
    _, cv = await call(c, "create_cv", {"plan_id": plan["id"]})
    candidates = [
        {"name": "ridge_lags3", "config": {"estimator": "Ridge", "lags": 3}},
        {"name": "ridge_lags6", "config": {"estimator": "Ridge", "lags": 6}},
    ]
    args = {"cv_id": cv["id"], "candidates": candidates, "baseline": False}
    print("INPUT compare:", json.dumps(args))
    _, cmp = await call(c, "compare", args)
    print("OBSERVED create_cv cost:", json.dumps(cv["cost"]))
    print("OBSERVED compare cost:", json.dumps(cmp["cost"]))
    s = cmp["summary"]
    print("OBSERVED compare summary:", s[s.find("Compared"):s.find("Compared") + 80])
    RESULT["ok"] = (
        cmp["cost"]["estimator_fits"] == 2 and cmp["cost"]["n_fits"] == 1
    )


run(main, allow_dir=DATA)
print(
    "EXPECTED: `n_fits` of the compare is the total trainings of its candidates "
    "(2 here), like `estimator_fits`, or the field is documented as the plan's."
)
if RESULT.get("ok"):
    print("REPRODUCED")
    sys.exit(0)
print("NOT REPRODUCED")
sys.exit(1)
