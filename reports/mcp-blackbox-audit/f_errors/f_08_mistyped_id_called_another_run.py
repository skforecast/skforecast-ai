"""f-08: an id mistyped in one character is reported as "from another run".

The ids end with a suffix of the run ('plan-2-f5d029'). When an agent
copies an id of this run with one wrong character in the suffix, the
answer states as a fact that the id "comes from another run of the server:
ids do not survive a restart. Create the object again.", so the agent
rebuilds the profile and the plan (and tells the user the server
restarted) instead of fixing the id. The same typo in the counter
('plan-7-...') gets the neutral "No object has the id".
Expected: a neutral message for any id not registered now ("not
registered in this run: mistyped, or from an earlier run"), pointing to
`list_objects` first.
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
    _, plan = await call(c, "plan", {"profile_id": prof["id"], "steps": 12})
    good = plan["id"]
    typo = good[:-1] + ("0" if good[-1] != "0" else "1")
    print("Real id:", good)
    args = {"plan_id": typo}
    print("INPUT create_cv:", json.dumps(args))
    err, out = await call(c, "create_cv", args)
    print("OBSERVED:", json.dumps(out)[:400])
    print(
        "EXPECTED: a message that does not claim a restart, e.g. \"No object "
        "has the id ...: mistyped, or from an earlier run\"."
    )
    return err and "comes from another run" in out.get("message", "")


ok = run(main, allow_dir=DATA)
print("REPRODUCED" if ok else "NOT REPRODUCED")
sys.exit(0 if ok else 1)
