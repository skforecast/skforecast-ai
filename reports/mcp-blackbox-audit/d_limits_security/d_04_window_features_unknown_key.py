"""d-04: unknown keys inside a `window_features` entry are dropped silently.

The skill says "Arguments are strict: an unknown argument or a wrong type is
an error, never ignored." A typo or an option the agent believes exists
(`min_periods`, `windows_size`) inside an entry of `window_features` is
accepted and ignored: the plan and its script have no trace of it. An
unknown key elsewhere (a candidate config) is rejected.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
WF = [{"stats": ["mean"], "window_size": 3, "min_periods": 2},
      {"stats": ["max"], "window_size": 6, "windows_size": 24}]
OUT = {}


async def main(c):
    _, p = await call(c, "profile",
                      {"data_path": str(DATA / "monthly.csv"), "target": "y"})
    OUT["args"] = {"profile_id": p["id"], "steps": 12, "window_features": WF}
    OUT["plan"] = await call(c, "plan", OUT["args"])
    if not OUT["plan"][0]:
        OUT["code"] = await call(c, "get_code", {"object_id": OUT["plan"][1]["id"]})
    _, pl = await call(c, "plan", {"profile_id": p["id"], "steps": 12})
    _, cv = await call(c, "create_cv", {"plan_id": pl["id"]})
    OUT["strict"] = await call(c, "compare", {"cv_id": cv["id"], "candidates": [
        {"name": "r", "config": {"estimator": "Ridge", "steps": 6}}]})


run(main, allow_dir=DATA)

print("INPUT plan", json.dumps(OUT["args"]))
is_error, plan = OUT["plan"]
if is_error:
    print("OBSERVED error", plan)
    print("NOT REPRODUCED")
    sys.exit(1)
code = OUT["code"][1]["code"]
wf_lines = [ln for ln in code.splitlines()
            if "window" in ln.lower() or "min_periods" in ln][:8]
print("OBSERVED plan ok", plan["id"], "notices:",
      [n["message"][:150] for n in plan["notices"]])
print("OBSERVED script lines:\n  " + "\n  ".join(wf_lines))
print("CONTRAST unknown key in a candidate config ->",
      json.dumps(OUT["strict"][1])[:200])
print("EXPECTED: invalid_argument on window_features naming 'min_periods' and")
print("'windows_size' as unknown keys (only 'stats' and 'window_size' exist).")
silent = "min_periods" not in code and "windows_size" not in code and not any(
    "min_periods" in n["message"] or "windows_size" in n["message"]
    for n in plan["notices"])
if silent:
    print("REPRODUCED")
    sys.exit(0)
print("NOT REPRODUCED")
sys.exit(1)
