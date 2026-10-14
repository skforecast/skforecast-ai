"""f-03: a hold-out whose training part is shorter than the window fails as
`execution_failed`, with no field and no hint.

`plan(steps=90)` on 120 monthly rows is accepted, and
`forecast(test_size=90)` leaves 30 training rows for a window of 36. The
server knows the window size (create_cv warns about this very case before
running), but `forecast` runs the script and answers
"The generated script failed with ValueError", field null. The SKILL.md
table maps "a series too short for the forecaster" to `insufficient_data`.
Expected: `insufficient_data`, field `test_size` (or `steps`), saying the
training part has 30 rows and the forecaster needs more than 36.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
PATH = str(DATA / "monthly.csv")


async def main(c):
    _, prof = await call(c, "profile", {"data_path": PATH, "target": "y"})
    perr, plan = await call(c, "plan", {"profile_id": prof["id"], "steps": 90})
    print("INPUT plan: steps=90 on 120 rows -> error:", perr)
    args = {"plan_id": plan["id"], "test_size": 90}
    print("INPUT forecast:", json.dumps(args))
    err, out = await call(c, "forecast", args)
    print("OBSERVED:", json.dumps(out)[:600] if err else "success")
    if not err:
        return False
    if out.get("code") == "execution_failed":
        fid = out["details"]["failure_id"]
        _, fail = await call(c, "get_failure", {"object_id": fid})
        print("OBSERVED get_failure (start):", fail["text"][:330])
    print(
        "EXPECTED: insufficient_data with field 'test_size' (or 'steps') and "
        "the reason, without a run and without get_failure."
    )
    return out.get("code") == "execution_failed" and out.get("field") is None


ok = run(main, allow_dir=DATA)
print("REPRODUCED" if ok else "NOT REPRODUCED")
sys.exit(0 if ok else 1)
