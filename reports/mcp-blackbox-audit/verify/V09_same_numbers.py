"""V09 check: does the plan script (decimal=',') give the same predictions as
the forecast that ran (decimal='.')?"""

import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "b_hard_data" / "data"
OUT = {}


async def main(c):
    _, p = await call(c, "profile", {"data_path": str(DATA / "semi_dot.csv"),
                                     "target": "y", "sep": ";", "decimal": ","})
    _, pl = await call(c, "plan", {"profile_id": p["id"], "steps": 6})
    _, code = await call(c, "get_code", {"object_id": pl["id"]})
    OUT["code"] = code["code"]
    _, fc = await call(c, "forecast", {"plan_id": pl["id"]})
    OUT["pred"] = pd.read_csv(fc["files"]["predictions"], index_col=0)


run(main, allow_dir=DATA)
d = Path(tempfile.mkdtemp())
(d / "plan.py").write_text(OUT["code"] + "\npredictions.to_csv('p.csv')\n")
proc = subprocess.run([sys.executable, "plan.py"], cwd=d, capture_output=True,
                      text=True, timeout=300)
print("plan script returncode", proc.returncode)
plan_pred = pd.read_csv(d / "p.csv", index_col=0)
print(OUT["pred"].head(6))
print(plan_pred.head(6))
same = (abs(OUT["pred"]["pred"].values - plan_pred["pred"].values) < 1e-9).all()
print("SAME PREDICTIONS:", same)
