"""f-01: `profile` accepts a target list with the same column twice.

The duplicated column is profiled as two series, the plan recommends a
multi-series forecaster, and `forecast` then runs with a pandas warning
("DataFrame columns are not unique, some columns will be omitted").
Expected: `invalid_argument` with `field: target`, as `plan` does for a
repeated lag, metric or calendar feature.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
PATH = str(DATA / "monthly.csv")


async def main(c):
    args = {"data_path": PATH, "target": ["y", "y"]}
    print("INPUT profile:", json.dumps(args))
    err, prof = await call(c, "profile", args)
    if err:
        print("OBSERVED profile error:", json.dumps(prof))
        return False
    lines = [
        ln for ln in prof["summary"].splitlines()
        if ln.startswith(("- Series:", "- Target:", "- Observations"))
    ]
    print("OBSERVED profile summary:", lines)
    err, plan = await call(c, "plan", {"profile_id": prof["id"], "steps": 12})
    err, fc = await call(c, "forecast", {"plan_id": plan["id"]})
    notices = [n["message"] for n in fc.get("notices", [])] if not err else fc
    print("OBSERVED forecast error" if err else "OBSERVED forecast notices:", notices)
    if not err and "predictions" in fc.get("files", {}):
        with open(fc["files"]["predictions"]) as fh:
            head = [next(fh).rstrip() for _ in range(3)]
        print("OBSERVED files.predictions head:", head)
    print(
        "EXPECTED: profile fails with invalid_argument, field 'target', "
        "saying the column 'y' is repeated."
    )
    two_series = any(ln.strip() == "- Series: 2" for ln in lines)
    return two_series


ok = run(main, allow_dir=DATA)
print("REPRODUCED" if ok else "NOT REPRODUCED")
sys.exit(0 if ok else 1)
