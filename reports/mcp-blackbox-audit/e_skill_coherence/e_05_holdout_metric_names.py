"""e-05: forecast with `test_size` names its metrics MAE/MASE and its rows 'series'.

SKILL.md (Inputs): "Metrics are the names of skforecast:
`mean_absolute_error`, `mean_squared_error`, `mean_absolute_scaled_error`
...", and the rules of trust tell the agent to read
`mean_absolute_scaled_error` per series in the CSV of metrics.

`backtest` (files.metrics) and `compare` (files.best_metrics, leaderboard)
use those names and a `levels` column. `forecast` with `test_size` writes
files.metrics with the columns `series, MAE, MSE, MASE, MAPE` and its
summary uses the same abbreviations, while its own MetricReferenceNotice
speaks of `mean_absolute_scaled_error`. An agent that looks the metric up
by the name it passed in `plan(metric=...)` does not find it.

Run from the repository root:
    python reports/mcp-blackbox-audit/e_skill_coherence/e_05_holdout_metric_names.py
"""

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
out = {}


def header(path):
    with open(path) as fh:
        return next(csv.reader(fh))


async def main(c):
    _, prof = await call(
        c, "profile",
        {"data_path": str(DATA / "multi_long.csv"), "target": "y",
         "series_id_column": "series"},
    )
    metric = ["mean_absolute_scaled_error", "mean_absolute_error"]
    args = {"profile_id": prof["id"], "steps": 6, "metric": metric,
            "estimator": "Ridge"}
    print("INPUT plan", json.dumps(args))
    _, plan = await call(c, "plan", args)
    _, cv = await call(c, "create_cv", {"plan_id": plan["id"]})
    _, bt = await call(c, "backtest", {"cv_id": cv["id"]})
    out["backtest"] = header(bt["files"]["metrics"])
    fargs = {"plan_id": plan["id"], "test_size": 6}
    print("INPUT forecast", json.dumps(fargs))
    _, fc = await call(c, "forecast", fargs)
    out["forecast"] = header(fc["files"]["metrics"])
    s = fc["summary"]
    out["summary"] = s[s.index("<evaluation_metrics>"):
                       s.index("</evaluation_metrics>")]
    out["notice"] = [n["message"][:80] for n in fc["notices"]
                     if n["category"] == "MetricReferenceNotice"]


run(main, allow_dir=DATA)

print("OBSERVED backtest files.metrics header:", out["backtest"])
print("OBSERVED forecast(test_size) files.metrics header:", out["forecast"])
print("OBSERVED forecast summary:", out["summary"])
print("OBSERVED forecast MetricReferenceNotice:", out["notice"])
print(
    "EXPECTED: the forecast metrics use the skforecast names given in "
    "`metric` (mean_absolute_scaled_error, ...) and the same id column as the "
    "backtest ('levels')."
)
if ("mean_absolute_scaled_error" in out["backtest"]
        and "mean_absolute_scaled_error" not in out["forecast"]
        and "MASE" in out["forecast"]):
    print("REPRODUCED")
    sys.exit(0)
print("NOT REPRODUCED")
sys.exit(1)
