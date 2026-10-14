"""d-05: `cost` ignores the size of the estimator; one run wedges the server.

A plan with `estimator_kwargs={"n_estimators": 10**8}` gets no notice, and
`create_cv` reports 1 estimator fit, far below the 50 of the cost rule, so
an agent that follows the skill runs the backtest. The run cannot be
interrupted: after the client cancels it, every non read tool (`profile`
here) stays blocked until the fit ends (hours). Only killing the server
frees it.
"""

import json
import sys
import time
from pathlib import Path

import anyio

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
KW = {"n_estimators": 10**8, "n_jobs": 1}
WAIT = 20
OUT = {}


async def main(c):
    _, p = await call(c, "profile",
                      {"data_path": str(DATA / "monthly.csv"), "target": "y"})
    _, pl = await call(c, "plan", {"profile_id": p["id"], "steps": 12,
                                   "estimator": "RandomForestRegressor",
                                   "estimator_kwargs": KW})
    OUT["plan_notices"] = [n["message"][:200] for n in pl["notices"]]
    _, cv = await call(c, "create_cv", {"plan_id": pl["id"]})
    OUT["cost"] = cv["cost"]
    OUT["cv_notices"] = [n["message"][:200] for n in cv["notices"]]

    async def backtest():
        with anyio.move_on_after(3) as scope:
            await c.call_tool("backtest", {"cv_id": cv["id"]})
        OUT["cancelled"] = scope.cancelled_caught

    async def later():
        await anyio.sleep(4)
        t = time.time()
        with anyio.move_on_after(WAIT) as scope:
            await call(c, "profile",
                       {"data_path": str(DATA / "monthly.csv"), "target": "y"})
        OUT["profile_blocked"] = scope.cancelled_caught
        OUT["profile_wait"] = round(time.time() - t, 1)

    async with anyio.create_task_group() as tg:
        tg.start_soon(backtest)
        tg.start_soon(later)


run(main, allow_dir=DATA)

print("INPUT plan estimator RandomForestRegressor, estimator_kwargs",
      json.dumps(KW), "-> create_cv {} -> backtest (cancelled after 3 s)",
      "-> profile")
print("OBSERVED plan notices:", OUT["plan_notices"])
print("OBSERVED create_cv cost:", OUT["cost"], "notices:", OUT["cv_notices"])
print("OBSERVED backtest cancelled by the client:", OUT["cancelled"])
print(f"OBSERVED profile still blocked after {OUT['profile_wait']} s:",
      OUT["profile_blocked"])
print("EXPECTED: a notice (plan or create_cv) that the estimator size makes the")
print("run expensive, or a cap on it, so the cost rule of the skill can stop")
print("the agent; or a cancellation that frees the server.")
cheap = OUT["cost"]["estimator_fits"] <= 50 and not OUT["cv_notices"]
if cheap and not OUT["plan_notices"] and OUT["profile_blocked"]:
    print("REPRODUCED")
    sys.exit(0)
print("NOT REPRODUCED")
sys.exit(1)
