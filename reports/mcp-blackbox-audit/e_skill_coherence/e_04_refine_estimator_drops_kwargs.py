"""e-04: refine_plan drops omitted `estimator_kwargs` without saying so.

SKILL.md, step 3 (and the schema of `refine_plan`): "An omitted key keeps
the value of the plan".

A plan with `estimator: LGBMRegressor, estimator_kwargs: {n_estimators: 50}`
refined with only `{estimator: RandomForestRegressor}` loses
`n_estimators=50` (a valid argument of RandomForestRegressor too): the new
script builds `RandomForestRegressor(random_state=123)`, there is no notice
and the summary just stops listing `estimator_kwargs` among the choices of
the user. The agent believes the 50 trees were kept.

Run from the repository root:
    python reports/mcp-blackbox-audit/e_skill_coherence/e_04_refine_estimator_drops_kwargs.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
out = {}


def estimator_line(code):
    return [x.strip() for x in code.splitlines() if "estimator  " in x]


async def main(c):
    _, prof = await call(
        c, "profile", {"data_path": str(DATA / "single.csv"), "target": "y"}
    )
    args = {"profile_id": prof["id"], "steps": 12,
            "estimator": "LGBMRegressor",
            "estimator_kwargs": {"n_estimators": 50, "verbose": -1}}
    print("INPUT plan", json.dumps(args))
    _, plan = await call(c, "plan", args)
    _, code = await call(c, "get_code", {"object_id": plan["id"]})
    print("OBSERVED original plan:", estimator_line(code["code"]))
    refine = {"plan_id": plan["id"],
              "overrides": {"estimator": "RandomForestRegressor"}}
    print("INPUT refine_plan", json.dumps(refine))
    _, new = await call(c, "refine_plan", refine)
    _, code = await call(c, "get_code", {"object_id": new["id"]})
    out["line"] = estimator_line(code["code"])
    out["notices"] = new["notices"]
    chosen = [x for x in new["summary"].splitlines()
              if "Chosen by the user" in x]
    print("OBSERVED refined plan:", out["line"])
    print("OBSERVED notices:", out["notices"])
    print("OBSERVED summary:", chosen)


run(main, allow_dir=DATA)

print(
    "EXPECTED: the refined plan keeps n_estimators=50 "
    "(RandomForestRegressor(n_estimators=50, ...)), or a notice says the "
    "estimator_kwargs of the plan were dropped with the change of estimator."
)
kept = any("n_estimators=50" in x for x in out["line"])
if not kept and not out["notices"]:
    print("REPRODUCED")
    sys.exit(0)
print("NOT REPRODUCED")
sys.exit(1)
