"""V13 check: the notices of profile and plan for a yyyymmdd integer date
column, and what the plan does without a datetime index."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "b_hard_data" / "data"


async def main(c):
    _, p = await call(c, "profile", {"data_path": str(DATA / "date_yyyymmdd.csv"),
                                     "target": "y"})
    for n in p["notices"]:
        print("PROFILE NOTICE>>", n["category"], "|", n["message"][:600])
    err, pl = await call(c, "plan", {"profile_id": p["id"], "steps": 7})
    print("PLAN>> err", err)
    for n in (pl.get("notices") or []):
        print("PLAN NOTICE>>", n["category"], "|", n["message"][:300])
    if err:
        print("PLAN ERR>>", pl)


run(main, allow_dir=DATA)
