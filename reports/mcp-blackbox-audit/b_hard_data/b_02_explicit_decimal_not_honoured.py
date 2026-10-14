"""b-02: an explicit `decimal` is accepted with a non-numeric target and then
dropped by the runs.

A ';' file written with '.' decimals is profiled with `decimal: ','` (what an
agent passes when the user says the file is a European export). `profile`
does not reject the target that this reading leaves as text (it does reject
it with `decimal: '.'` on a ',' file), the plan's script reads with
`decimal=','`, and `backtest` / `forecast` silently read the file again with
`decimal='.'`: the code of the plan is not the code that ran, and the change
shows only as a line inside `summary`, not in `notices`.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"


def read_csv_line(code):
    return re.search(r"read_csv\([^\n]*", code).group(0)


async def main(c):
    args = {
        "data_path": str(DATA / "semi_dot.csv"),
        "target": "y",
        "sep": ";",
        "decimal": ",",
    }
    print("INPUT profile", json.dumps(args))
    err, p = await call(c, "profile", args)
    if err:
        print("OBSERVED profile error (expected behaviour):", p)
        return False
    has_stats = "Target statistics" in p["summary"]
    print("OBSERVED profile: no error; 'Target statistics' in summary:", has_stats)
    _, pl = await call(c, "plan", {"profile_id": p["id"], "steps": 6})
    print("OBSERVED plan steps:", re.findall(r"\[in generated code\][^\n]*", pl["summary"]))
    _, plan_code = await call(c, "get_code", {"object_id": pl["id"]})
    err, fc = await call(c, "forecast", {"plan_id": pl["id"]})
    if err:
        print("OBSERVED forecast error:", fc)
        return False
    _, fc_code = await call(c, "get_code", {"object_id": fc["id"]})
    plan_line = read_csv_line(plan_code["code"])
    fc_line = read_csv_line(fc_code["code"])
    print("OBSERVED get_code(plan):    ", plan_line)
    print("OBSERVED get_code(forecast):", fc_line)
    print("OBSERVED forecast summary:", re.findall(r"Data warning:[^\n]*", fc["summary"]))
    print("OBSERVED forecast notices:", [n["category"] for n in fc["notices"]])
    print(
        "EXPECTED: profile rejects the target as not numeric with "
        "decimal=',' (as it does for decimal='.' on a ',' file), or the runs "
        "keep the decimal the agent passed; never a different reading than "
        "the plan's script without a notice."
    )
    return (
        not has_stats
        and "decimal=','" in plan_line
        and "decimal='.'" in fc_line
        and not any("differ" in n["message"] for n in fc["notices"])
    )


if __name__ == "__main__":
    ok = run(main, allow_dir=DATA)
    print("REPRODUCED" if ok else "NOT REPRODUCED")
    sys.exit(0 if ok else 1)
