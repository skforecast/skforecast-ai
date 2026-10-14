"""d-02: a target list that repeats a column is accepted as two series.

`profile(target=["y", "y"])` succeeds: the summary says 2 series and the
recommendation switches to ForecasterRecursiveMultiSeries, while the
backtest and the forecast only hold one level, 'y'. `exog_columns` with a
repeated name is rejected ("names a column more than once").
"""

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
WIDE = str(DATA / "wide.csv")
OUT = {}


async def main(c):
    args = {"data_path": WIDE, "target": ["y", "y"], "exog_columns": []}
    OUT["args"] = args
    OUT["profile"] = await call(c, "profile", args)
    OUT["exog_dup"] = await call(
        c, "profile", {"data_path": WIDE, "target": "y", "exog_columns": ["x", "x"]}
    )
    is_error, p = OUT["profile"]
    if is_error:
        return
    _, pl = await call(c, "plan", {"profile_id": p["id"], "steps": 12})
    OUT["plan"] = pl
    _, fc = await call(c, "forecast", {"plan_id": pl["id"]})
    OUT["forecast"] = fc


run(main, allow_dir=DATA)

print("INPUT profile", json.dumps(OUT["args"]))
is_error, p = OUT["profile"]
if is_error:
    print("OBSERVED error", p)
    print("NOT REPRODUCED")
    sys.exit(1)
lines = [ln for ln in p["summary"].splitlines()
         if ln.startswith(("- Series:", "- Target:", "- Observations"))]
print("OBSERVED profile ok:", lines)
decision = [ln for ln in p["summary"].splitlines() if "is recommended" in ln]
print("OBSERVED decision:", decision[0][:160] if decision else None)
levels = sorted(pd.read_csv(OUT["forecast"]["files"]["predictions"])["level"].unique())
print("OBSERVED forecast levels:", levels)
print("CONTRAST exog_columns ['x','x'] ->", json.dumps(OUT["exog_dup"][1])[:200])
print("EXPECTED: invalid_argument on `target` (a column named more than once),")
print("as for exog_columns; at least not a profile of 2 series for 1 column.")
if "- Series: 2" in lines and levels == ["y"]:
    print("REPRODUCED")
    sys.exit(0)
print("NOT REPRODUCED")
sys.exit(1)
