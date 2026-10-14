"""Smoke test: profile -> plan -> create_cv -> backtest -> forecast on a monthly series."""
import sys
import tempfile
import time
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _client import call, run, show

d = Path(tempfile.mkdtemp(prefix="allow-"))
n = 120
dates = pd.date_range("2015-01-01", periods=n, freq="MS")
y = 100 + np.arange(n) * 0.5 + 10 * np.sin(np.arange(n) * 2 * np.pi / 12) + np.random.default_rng(0).normal(0, 1, n)
pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "y": y.round(3)}).to_csv(d / "m.csv", index=False)

async def main(c):
    t = time.time()
    _, p = await call(c, "profile", {"data_path": str(d / "m.csv"), "target": "y"})
    show("profile", p, 1500)
    _, pl = await call(c, "plan", {"profile_id": p["id"], "steps": 12})
    _, cv = await call(c, "create_cv", {"plan_id": pl["id"]})
    show("cv", cv, 1500)
    _, bt = await call(c, "backtest", {"cv_id": cv["id"]})
    show("backtest", bt, 2500)
    _, fc = await call(c, "forecast", {"plan_id": pl["id"]})
    show("forecast", fc, 2500)
    print("elapsed", time.time() - t)

run(main, allow_dir=d)
