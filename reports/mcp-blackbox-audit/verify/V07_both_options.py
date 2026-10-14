"""V07 check: both options of the differentiation mismatch message are
reachable through the tools: create_cv from plan B, or a plan with the same
differentiation as the strategy (refine_plan differentiation null)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "a_happy_path" / "data"


async def main(c):
    _, p = await call(c, "profile", {"data_path": str(DATA / "monthly.csv"), "target": "sales"})
    _, a = await call(c, "plan", {"profile_id": p["id"], "steps": 12})
    _, b = await call(c, "plan", {"profile_id": p["id"], "steps": 12, "differentiation": 1})
    _, cva = await call(c, "create_cv", {"plan_id": a["id"]})
    err, _ = await call(c, "backtest", {"cv_id": cva["id"], "plan_id": b["id"]})
    print("RESULT>> mismatch error:", err)
    _, cvb = await call(c, "create_cv", {"plan_id": b["id"]})
    err1, _ = await call(c, "backtest", {"cv_id": cvb["id"]})
    print("RESULT>> option 1 (create_cv from plan B) error:", err1)
    err2, b2 = await call(c, "refine_plan", {"plan_id": b["id"], "overrides": {"differentiation": None}})
    print("RESULT>> refine_plan error:", err2)
    if not err2:
        err3, _ = await call(c, "backtest", {"cv_id": cva["id"], "plan_id": b2["id"]})
        print("RESULT>> option 2 (same differentiation in the plan) error:", err3)


run(main, allow_dir=DATA)
