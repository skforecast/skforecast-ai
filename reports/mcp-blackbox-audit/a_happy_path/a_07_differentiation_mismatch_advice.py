"""a-07: an error advises an argument the tool does not have.

Following SKILL.md step 5 (`backtest(cv_id, plan_id?)`: "`plan_id` backtests
another plan of the same profile on the same folds"), an agent backtests a
plan with `differentiation: 1` on the strategy of the plan without it. The
error says "Create the strategy from this plan with `create_cv()`, or pass
the same `differentiation`", but `create_cv` has no `differentiation`
argument (strict schema), and `hint` is null, so the second way out is a
dead end.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
RESULT = {}


async def main(c):
    tools = {t.name: t for t in (await c.list_tools()).tools}
    cv_props = sorted(tools["create_cv"].input_schema["properties"])
    _, p = await call(
        c, "profile", {"data_path": str(DATA / "monthly.csv"), "target": "sales"}
    )
    _, plan = await call(c, "plan", {"profile_id": p["id"], "steps": 12})
    _, diff = await call(
        c, "plan", {"profile_id": p["id"], "steps": 12, "differentiation": 1}
    )
    _, cv = await call(c, "create_cv", {"plan_id": plan["id"]})
    args = {"cv_id": cv["id"], "plan_id": diff["id"]}
    print("INPUT backtest:", json.dumps(args))
    err, payload = await call(c, "backtest", args)
    print("OBSERVED error:", json.dumps(payload, indent=1))
    print("OBSERVED create_cv arguments:", cv_props)
    err2, payload2 = await call(
        c, "create_cv", {"plan_id": plan["id"], "differentiation": 1}
    )
    print("OBSERVED create_cv with differentiation:", payload2)
    RESULT["ok"] = (
        err
        and "pass the same `differentiation`" in payload.get("message", "")
        and payload.get("hint") is None
        and "differentiation" not in cv_props
    )


run(main, allow_dir=DATA)
print(
    "EXPECTED: advice the agent can follow through the tools, e.g. hint: "
    "'Call create_cv with plan_id=<the plan with differentiation> and backtest "
    "on that strategy.'"
)
if RESULT.get("ok"):
    print("REPRODUCED")
    sys.exit(0)
print("NOT REPRODUCED")
sys.exit(1)
