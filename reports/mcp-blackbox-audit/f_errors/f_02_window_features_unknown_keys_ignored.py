"""f-02: unknown keys inside a `window_features` entry are silently ignored.

SKILL.md: "Arguments are strict: an unknown argument or a wrong type is an
error, never ignored." `plan`, `refine_plan` and the candidates of
`compare` accept {'stats': ['mean'], 'window_size': 3, 'min_periods': 1}
(a real RollingFeatures argument): the summary echoes the key as chosen by
the user, but the script that runs drops it.
Expected: `invalid_argument`, field `window_features`, naming the unknown
key, as for an unknown statistic or a missing `window_size`.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
PATH = str(DATA / "monthly.csv")
WF = [{"stats": ["mean"], "window_size": 3, "min_periods": 1}]


async def main(c):
    _, prof = await call(c, "profile", {"data_path": PATH, "target": "y"})
    args = {"profile_id": prof["id"], "steps": 12, "window_features": WF}
    print("INPUT plan:", json.dumps(args))
    err, plan = await call(c, "plan", args)
    if err:
        print("OBSERVED plan error:", json.dumps(plan))
        return False
    echo = [ln for ln in plan["summary"].splitlines() if "min_periods" in ln]
    print("OBSERVED plan accepted; summary lines:", echo)
    _, code = await call(c, "get_code", {"object_id": plan["id"]})
    script = code["code"] if isinstance(code, dict) and "code" in code else str(code)
    print("OBSERVED 'min_periods' in get_code script:", "min_periods" in script)
    _, base = await call(c, "plan", {"profile_id": prof["id"], "steps": 12})
    rargs = {"plan_id": base["id"], "overrides": {"window_features": WF}}
    rerr, _ = await call(c, "refine_plan", rargs)
    print("OBSERVED refine_plan with the same entry is an error:", rerr)
    bad = [{"stats": ["avg"], "window_size": 3}]
    _, e2 = await call(
        c, "plan", {"profile_id": prof["id"], "steps": 12, "window_features": bad}
    )
    print("CONTRAST unknown statistic:", json.dumps(e2)[:200])
    print(
        "EXPECTED: invalid_argument, field 'window_features', naming the "
        "unknown key 'min_periods'."
    )
    return bool(echo) and "min_periods" not in script and not rerr


ok = run(main, allow_dir=DATA)
print("REPRODUCED" if ok else "NOT REPRODUCED")
sys.exit(0 if ok else 1)
