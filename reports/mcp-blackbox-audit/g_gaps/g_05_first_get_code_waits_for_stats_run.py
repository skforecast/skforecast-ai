"""g-05: the first `get_code` of a session waits for a running ForecasterStats run.

SKILL.md (Progress and cancellation): while a long call runs, "only the read
tools (`get_code`, `get_failure`, `list_objects`, `describe_object`) answer:
the others wait their turn". During a ForecasterStats backtest of 10 folds
(about 20 s on 4 CPUs), `list_objects` and `describe_object` answer at once,
but the first `get_code` of the server process (here on the strategy, an
object that has nothing to do with the run) only answers when the backtest is
about to end. Once one `get_code` has answered before the run, the same call
during the run answers at once (the control below). A client that relies on
the promise, for example to show the user the code while a long backtest or
compare runs, waits as long as the run, with no progress notification for
that call.
"""

import json
import sys
import time
from pathlib import Path

import anyio

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run, unpack  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
R = {}


def scenario(label, warm):
    async def main(c):
        _, profile = await call(
            c, "profile", {"data_path": str(DATA / "monthly_20y.csv"), "target": "y"}
        )
        args = {"profile_id": profile["id"], "steps": 12,
                "forecaster": "ForecasterStats"}
        _, plan = await call(c, "plan", args)
        cv_args = {"plan_id": plan["id"], "initial_train_size": 180, "fold_stride": 6}
        _, cv = await call(c, "create_cv", cv_args)
        if warm:
            await call(c, "get_code", {"object_id": plan["id"]})
        out = R.setdefault(label, {"cost": cv["cost"]})
        t0 = time.monotonic()

        async def backtest():
            res = await c.call_tool("backtest", {"cv_id": cv["id"]})
            out["backtest"] = (round(time.monotonic() - t0, 1), unpack(res)[0])

        async with anyio.create_task_group() as group:
            group.start_soon(backtest)
            await anyio.sleep(2)
            for tool, a in (
                ("list_objects", {}),
                ("describe_object", {"object_id": plan["id"]}),
                ("get_code", {"object_id": cv["id"]}),
            ):
                t = time.monotonic()
                err, _ = await call(c, tool, a)
                out[tool] = (round(time.monotonic() - t, 1), err)
        print(f"INPUT {label}: plan {json.dumps(args)}, create_cv "
              f"{json.dumps(cv_args)}, backtest, then 2 s later list_objects, "
              f"describe_object(plan), get_code(cv)")

    return main


run(scenario("first get_code during the run", warm=False), allow_dir=DATA)
run(scenario("control: one get_code before the run", warm=True), allow_dir=DATA)

for label, out in R.items():
    print(f"OBSERVED {label}: cost {out['cost']}")
    for tool in ("list_objects", "describe_object", "get_code"):
        secs, err = out[tool]
        print(f"   {tool}: answered after {secs} s (error {err})")
    print(f"   backtest ended {out['backtest'][0]} s after it started")
print(
    "EXPECTED: get_code answers within a couple of seconds during the run, "
    "like list_objects and describe_object, as SKILL.md promises."
)
first = R["first get_code during the run"]
warm = R["control: one get_code before the run"]
if (
    first["get_code"][0] > 10
    and first["list_objects"][0] < 2
    and first["describe_object"][0] < 2
    and warm["get_code"][0] < 3
    and warm["backtest"][0] > 10
):
    print("REPRODUCED")
    sys.exit(0)
print("NOT REPRODUCED")
sys.exit(1)
