"""c-07: `fixed_train_size` without refit: the schema says error, it warns.

The input schema of `create_cv` says of `fixed_train_size`: "Only with
`refit` true or an integer: with `refit` false or null it is an error, as it
would not run (ForecasterStats aside)". `create_cv(fixed_train_size=true)`
with the default `refit` succeeds and carries an `IgnoredArgumentWarning`
("has no effect"). An agent that relies on the schema expects an error and
does not look for a notice, or avoids a valid call.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
RESULT = {}


async def main(c):
    path = str(DATA / "monthly.csv")
    _, p = await call(c, "profile", {"data_path": path, "target": "y"})
    _, plan = await call(c, "plan", {"profile_id": p["id"], "steps": 6})
    for args in ({"fixed_train_size": True}, {"fixed_train_size": True,
                                              "refit": False}):
        print("INPUT plan(steps=6) -> create_cv(", args, ")")
        is_error, cv = await call(c, "create_cv", {"plan_id": plan["id"], **args})
        if is_error:
            print("OBSERVED error:", cv)
        else:
            print("OBSERVED success, notices:")
            for n in cv["notices"]:
                print(f"  [{n['category']}] {n['message']}")
        RESULT[str(args)] = (not is_error) and any(
            n["category"] == "IgnoredArgumentWarning" for n in cv["notices"]
        )


run(main, allow_dir=DATA)
print(
    "EXPECTED: as the schema says, invalid_argument on field fixed_train_size;"
    " or the schema says it is ignored with an IgnoredArgumentWarning."
)
print("RESULT", RESULT)
if all(RESULT.values()):
    print("REPRODUCED")
    sys.exit(0)
print("NOT REPRODUCED")
sys.exit(1)
