"""e-02: with `candidates`, compare silently leaves out the refined plan.

SKILL.md, step 6: "When the strategy was created for another plan (one from
`refine_plan`, say), that plan runs too, with its own decisions, in the row
`Strategy plan`. The summary names the row of the plan of the strategy:
report that row as the user's plan."

With an explicit `candidates` list the plan of the strategy does not run,
nothing says so (no notice), and the summary names no row: it only says
"The strategy was created for the plan (ForecasterRecursive + Ridge)",
which is also the label of a candidate that runs the profile's
recommendation (other lags). The name 'Strategy plan' is not reserved
either: a candidate called that way is accepted and ranked, so the row the
skill tells the agent to report as the user's plan can be any configuration.

Run from the repository root:
    python reports/mcp-blackbox-audit/e_skill_coherence/e_02_compare_candidates_drop_strategy_plan.py
"""

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
out = {}


def rows(path):
    with open(path) as fh:
        return list(csv.DictReader(fh))


async def main(c):
    _, prof = await call(
        c, "profile", {"data_path": str(DATA / "single.csv"), "target": "y"}
    )
    _, plan = await call(c, "plan", {"profile_id": prof["id"], "steps": 12})
    refine = {"plan_id": plan["id"], "overrides": {"lags": 2}}
    _, refined = await call(c, "refine_plan", refine)
    _, cv = await call(c, "create_cv", {"plan_id": refined["id"]})
    _, bt = await call(c, "backtest", {"cv_id": cv["id"]})
    out["user_plan_metrics"] = rows(bt["files"]["metrics"])

    candidates = [
        {"name": "ridge", "config": {"estimator": "Ridge"}},
        {"name": "Strategy plan", "config": {"estimator": "RandomForestRegressor"}},
    ]
    print("INPUT refine_plan", json.dumps(refine))
    print("INPUT compare", json.dumps({"cv_id": "<cv of the refined plan>",
                                       "candidates": candidates}))
    is_error, cmp = await call(c, "compare", {"cv_id": cv["id"],
                                              "candidates": candidates})
    out["error"] = is_error
    out["summary"] = cmp["summary"]
    out["notices"] = [n["category"] for n in cmp["notices"]]
    out["leaderboard"] = rows(cmp["files"]["leaderboard"])


run(main, allow_dir=DATA)

summary = out["summary"]
start = summary.index("<deterministic_summary>")
end = summary.index("</deterministic_summary>")
print("OBSERVED deterministic summary:", summary[start + 23:end].strip())
print("OBSERVED notices:", out["notices"])
print("OBSERVED leaderboard:")
for r in out["leaderboard"]:
    print("  ", r["rank"], r["name"], r["forecaster"], r["estimator"],
          r["mean_absolute_error"])
user_mae = float(out["user_plan_metrics"][0]["mean_absolute_error"])
print("OBSERVED backtest of the refined plan on the same cv: MAE", user_mae)
print(
    "EXPECTED: the refined plan (lags=2) runs in a row the summary names, or "
    "the summary/notices say it was not compared; a candidate cannot take the "
    "name 'Strategy plan'."
)

maes = [float(r["mean_absolute_error"]) for r in out["leaderboard"]
        if r["mean_absolute_error"]]
user_plan_ran = any(abs(m - user_mae) < 1e-9 for m in maes)
names_a_row = "plan of row" in summary
fake_row = any(r["name"] == "Strategy plan" and r["estimator"] != "Ridge"
               for r in out["leaderboard"])
if not out["error"] and not user_plan_ran and not names_a_row:
    print("REPRODUCED (refined plan not compared, no row named"
          + (", and 'Strategy plan' taken by another configuration)"
             if fake_row else ")"))
    sys.exit(0)
print("NOT REPRODUCED")
sys.exit(1)
