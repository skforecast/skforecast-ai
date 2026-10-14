"""g-03 check: full plan, create_cv and backtest summaries for the short series."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "g_gaps" / "data"


async def main(c):
    _, p = await call(c, "profile", {"data_path": str(DATA / "stores_one_short.csv"),
                                     "target": "sales", "series_id_column": "store"})
    print("PROFILE SUMMARY\n", p["summary"])
    _, plan = await call(c, "plan", {"profile_id": p["id"], "steps": 12})
    print("PLAN SUMMARY\n", plan["summary"])
    print("PLAN NOTICES", plan["notices"])
    _, cv = await call(c, "create_cv", {"plan_id": plan["id"]})
    print("CV SUMMARY\n", cv["summary"])
    _, bt = await call(c, "backtest", {"cv_id": cv["id"]})
    print("BT SUMMARY\n", bt["summary"])
    print("BT NOTICES", bt["notices"])


run(main, allow_dir=DATA)
