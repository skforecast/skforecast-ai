"""V32 minimal: what an agent sees when one candidate has a typo in its estimator.

compare with the default baseline and one candidate {'estimator': 'Ridg'}:
prints the whole deterministic summary, the notices and the leaderboard
rows, to check whether the failure is visible without `get_failure`.
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "f_errors" / "data"
OUT = {}


async def main(c):
    _, p = await call(c, "profile",
                      {"data_path": str(DATA / "monthly.csv"), "target": "y"})
    _, pl = await call(c, "plan", {"profile_id": p["id"], "steps": 12})
    _, cv = await call(c, "create_cv", {"plan_id": pl["id"]})
    is_error, cmp = await call(
        c, "compare",
        {"cv_id": cv["id"],
         "candidates": [{"name": "typo_est", "config": {"estimator": "Ridg"}}]},
    )
    OUT["error"] = is_error
    OUT["cmp"] = cmp


run(main, allow_dir=DATA)
cmp = OUT["cmp"]
summary = cmp["summary"]
start = summary.find("<deterministic_summary>")
print("SUMMARY:", summary[start:start + 1500])
print("NOTICES:", [(n["category"], n["message"][:200]) for n in cmp["notices"]])
with open(cmp["files"]["leaderboard"]) as fh:
    for row in csv.DictReader(fh):
        print("ROW:", {k: v for k, v in row.items() if v})
mentions_failure = "Ridg" in summary or "fail" in summary.lower()
print("summary mentions the failure:", mentions_failure)
