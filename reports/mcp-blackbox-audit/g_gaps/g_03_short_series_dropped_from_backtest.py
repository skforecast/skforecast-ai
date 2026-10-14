"""g-03: a series too short for the plan vanishes from the backtest without a word.

Long data with three stores, one of them ('S02') opened 20 months before the
end of the data. The profile and the plan only say "Short series: only 20
observations", without naming the series. The default backtest runs: its
metrics file has an empty row for S02, the summary gives "Results (average
across series)" over the two other stores, and no notice says that S02 was
never forecast. `forecast` of the same plan then fails with
`insufficient_data` ('S02': 20 values, 24 needed). An agent following
SKILL.md reports the backtest accuracy of the plan across the series, and
cannot name the worst series as the skill asks, since that one has no
values.
"""

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
R = {}


async def main(c):
    args = {
        "data_path": str(DATA / "stores_one_short.csv"),
        "target": "sales",
        "series_id_column": "store",
    }
    print("INPUT profile:", json.dumps(args))
    _, profile = await call(c, "profile", args)
    R["profile_notices"] = [n["message"] for n in profile["notices"]]
    args = {"profile_id": profile["id"], "steps": 12}
    print("INPUT plan:", json.dumps(args))
    _, plan = await call(c, "plan", args)
    print("INPUT create_cv:", json.dumps({"plan_id": plan["id"]}))
    _, cv = await call(c, "create_cv", {"plan_id": plan["id"]})
    R["cv_notices"] = [n["message"] for n in cv["notices"]]
    print("INPUT backtest:", json.dumps({"cv_id": cv["id"]}))
    _, bt = await call(c, "backtest", {"cv_id": cv["id"]})
    R["bt_notices"] = [(n["category"], n["message"]) for n in bt["notices"]]
    summary = bt["summary"]
    i = summary.find("Results (")
    R["bt_results"] = summary[i:summary.find(". Initial training size", i)]
    R["metrics"] = pd.read_csv(bt["files"]["metrics"], index_col=0)
    R["pred_levels"] = sorted(
        pd.read_csv(bt["files"]["predictions"], index_col=0)["level"].unique()
    )
    print("INPUT forecast:", json.dumps({"plan_id": plan["id"]}))
    err, fc = await call(c, "forecast", {"plan_id": plan["id"]})
    R["forecast"] = (fc["code"], fc["message"]) if err else "ok"


run(main, allow_dir=DATA)

m = R["metrics"].set_index("levels")
print("OBSERVED profile notices:", R["profile_notices"])
print("OBSERVED create_cv notices:", R["cv_notices"])
print("OBSERVED backtest notices:", [cat for cat, _ in R["bt_notices"]])
print("OBSERVED backtest summary:", R["bt_results"])
print("OBSERVED metrics file:")
print(m[["mean_absolute_error", "mean_absolute_scaled_error"]].to_string())
print("OBSERVED series in the predictions file:", R["pred_levels"])
print("OBSERVED forecast of the same plan:", R["forecast"])
print(
    "EXPECTED: the profile or plan names the short series; create_cv or the "
    "backtest says that S02 is not forecast in any fold (and that forecast "
    "of this plan fails for it), instead of an average 'across series' that "
    "silently leaves it out."
)
names_s02 = any("S02" in t for t in R["profile_notices"] + R["cv_notices"])
bt_names_s02 = any("S02" in msg for _, msg in R["bt_notices"])
if (
    not names_s02
    and not bt_names_s02
    and m.loc["S02"].isna().all()
    and "S02" not in R["pred_levels"]
    and "average across series" in R["bt_results"]
    and R["forecast"] != "ok"
    and R["forecast"][0] == "insufficient_data"
    and "S02" in R["forecast"][1]
):
    print("REPRODUCED")
    sys.exit(0)
print("NOT REPRODUCED")
sys.exit(1)
