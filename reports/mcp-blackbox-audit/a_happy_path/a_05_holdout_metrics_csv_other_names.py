"""a-05: the metrics CSV of `forecast(test_size)` uses other column names.

The metrics CSV of `backtest` (and `compare`) has the skforecast names
(`mean_absolute_scaled_error`, column `levels` for series), the names the
SKILL.md, the schema of `metric` and the MetricReferenceNotice of the same
response use. The metrics CSV of `forecast` with `test_size` has
abbreviations (`MAE`, `MASE`, `MedAE`) and a column `series`, so an agent that
reads `mean_absolute_scaled_error` from `files.metrics` finds no such column.
"""

import json
import sys
from pathlib import Path

import pandas as pd

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
    _, bt = await call(c, "backtest", {"cv_id": cv["id"]})
    args = {"plan_id": plan["id"], "test_size": 12}
    print("INPUT forecast:", json.dumps(args))
    _, fc = await call(c, "forecast", args)
    bt_cols = list(pd.read_csv(bt["files"]["metrics"], index_col=0).columns)
    fc_cols = list(pd.read_csv(fc["files"]["metrics"], index_col=0).columns)
    notice = [n["message"] for n in fc["notices"]
              if n["category"] == "MetricReferenceNotice"]
    print("OBSERVED backtest files.metrics columns:", bt_cols)
    print("OBSERVED forecast(test_size) files.metrics columns:", fc_cols)
    print("OBSERVED forecast MetricReferenceNotice:", notice[:1])
    RESULT["ok"] = (
        "mean_absolute_scaled_error" in bt_cols
        and "mean_absolute_scaled_error" not in fc_cols
        and "MASE" in fc_cols
        and any("mean_absolute_scaled_error" in m for m in notice)
    )


run(main, allow_dir=DATA)
print(
    "EXPECTED: the same column names in every metrics CSV "
    "(`mean_absolute_scaled_error`, ...), the names the notices and the "
    "SKILL.md use."
)
if RESULT.get("ok"):
    print("REPRODUCED")
    sys.exit(0)
print("NOT REPRODUCED")
sys.exit(1)
