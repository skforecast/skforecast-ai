"""g-05 check: while the first get_code computes its requirements during a
ForecasterStats backtest, does list_objects (sent 1 s after get_code) also wait?
If so, get_code blocks the event loop of the server, not only itself."""
import sys
import time
from pathlib import Path

import anyio

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "g_gaps" / "data"
T = {}


async def main(c):
    _, p = await call(c, "profile", {"data_path": str(DATA / "monthly_20y.csv"), "target": "y"})
    _, plan = await call(c, "plan", {"profile_id": p["id"], "steps": 12, "forecaster": "ForecasterStats"})
    _, cv = await call(c, "create_cv", {"plan_id": plan["id"], "initial_train_size": 180, "fold_stride": 6})
    t0 = time.monotonic()

    async def timed(name, tool, args, delay):
        await anyio.sleep(delay)
        t = time.monotonic()
        await call(c, tool, args)
        T[name] = (round(t - t0, 1), round(time.monotonic() - t0, 1))

    async with anyio.create_task_group() as g:
        g.start_soon(timed, "backtest", "backtest", {"cv_id": cv["id"]}, 0)
        g.start_soon(timed, "get_code", "get_code", {"object_id": cv["id"]}, 2)
        g.start_soon(timed, "list_objects", "list_objects", {}, 3)


run(main, allow_dir=DATA)
for k, (s, e) in T.items():
    print(f"{k}: sent at {s} s, answered at {e} s")
