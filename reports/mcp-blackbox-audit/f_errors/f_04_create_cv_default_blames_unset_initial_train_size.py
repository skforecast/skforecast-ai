"""f-04: `create_cv` with only `plan_id` blames an argument the agent never set.

For a plan with `steps=90` on 120 monthly rows (accepted by `plan`, whose
limit is the length of the series), `create_cv(plan_id)` answers
`invalid_argument`, field `initial_train_size`, "If `initial_train_size` is
a date, it must be within the index range". The agent passed no
`initial_train_size`: the SKILL.md says "Fix the argument named in
`field`", which it cannot do. With `steps=80` the same situation (no room
for two folds) gets `insufficient_data` and a precise hint (use `forecast`
with `test_size`, or fewer `steps`).
Expected: the `steps=80` answer for `steps=90` too (insufficient_data,
field `steps` or null, the hold-out hint), never a field the caller did not
send.
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
    out = {}
    for steps in (80, 90):
        _, plan = await call(c, "plan", {"profile_id": prof["id"], "steps": steps})
        args = {"plan_id": plan["id"]}
        print(f"INPUT create_cv (plan with steps={steps}):", json.dumps(args))
        err, res = await call(c, "create_cv", args)
        out[steps] = res if err else {}
        print(f"OBSERVED steps={steps}:", json.dumps(res)[:520] if err else "ok")
    print(
        "EXPECTED steps=90: the same insufficient_data answer as steps=80, "
        "without field 'initial_train_size' (not sent)."
    )
    r90 = out[90]
    return (
        r90.get("code") == "invalid_argument"
        and r90.get("field") == "initial_train_size"
        and out[80].get("code") == "insufficient_data"
    )


ok = run(main, allow_dir=DATA)
print("REPRODUCED" if ok else "NOT REPRODUCED")
sys.exit(0 if ok else 1)
