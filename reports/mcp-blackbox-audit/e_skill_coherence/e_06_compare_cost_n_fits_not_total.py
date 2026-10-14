"""e-06: `cost.n_fits` of compare is the plan's, not the total of the candidates.

SKILL.md (Cost): "`compare` runs every candidate on the same folds, so it
costs about the sum of theirs (its response reports the totals)".

In the `cost` of a comparison, `estimator_fits` is the total over the
candidates but `n_fits` (trainings of the forecaster) stays at the value of
the plan of the strategy: with `refit=True` over 3 folds, three candidates
(ForecasterRecursive, ForecasterDirect, ForecasterStats) train 3 times each,
yet `n_fits` is 3. The same object mixes a total and a per-plan number with
nothing to tell them apart. (tests/tests_mcp/test_tool_compare.py pins
`n_fits: 1` for a two-candidate comparison, so the behaviour is tested; the
skill and the field do not say it.)

Run from the repository root:
    python reports/mcp-blackbox-audit/e_skill_coherence/e_06_compare_cost_n_fits_not_total.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
out = {}


async def main(c):
    _, prof = await call(
        c, "profile", {"data_path": str(DATA / "single.csv"), "target": "y"}
    )
    _, plan = await call(c, "plan", {"profile_id": prof["id"], "steps": 12})
    _, cv = await call(c, "create_cv", {"plan_id": plan["id"], "refit": True})
    out["cv_cost"] = cv["cost"]
    candidates = [
        {"name": "recursive", "config": {"estimator": "Ridge"}},
        {"name": "direct", "config": {"forecaster": "ForecasterDirect",
                                      "estimator": "Ridge"}},
        {"name": "stats", "config": {"forecaster": "ForecasterStats"}},
    ]
    args = {"cv_id": cv["id"], "candidates": candidates, "baseline": False}
    print("INPUT create_cv", json.dumps({"plan_id": "<plan>", "refit": True}))
    print("INPUT compare", json.dumps(args))
    _, cmp = await call(c, "compare", args)
    out["cmp_cost"] = cmp["cost"]


run(main, allow_dir=DATA)

print("OBSERVED create_cv cost:", out["cv_cost"])
print("OBSERVED compare cost:", out["cmp_cost"])
folds = out["cmp_cost"]["n_folds"]
expected_fits = 3 * folds
print(
    f"EXPECTED: compare n_fits = {expected_fits} (3 candidates x {folds} "
    "folds, as estimator_fits is a total), or a field that says it is the "
    "plan's count."
)
if out["cmp_cost"]["n_fits"] == out["cv_cost"]["n_fits"] < expected_fits:
    print("REPRODUCED")
    sys.exit(0)
print("NOT REPRODUCED")
sys.exit(1)
