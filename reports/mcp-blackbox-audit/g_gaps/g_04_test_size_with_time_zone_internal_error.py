"""g-04: `forecast(test_size=...)` with a time zone in the date is an internal_error.

Hourly load recorded in UTC, with dates written '2024-03-20T00:00:00Z'.
SKILL.md: "pass ... the ISO 8601 date the test set starts at". Passing it as
the data writes it ('2024-04-09T00:00:00Z', or '+00:00') returns
`internal_error` "Unexpected TypeError" whose hint says "do not retry with
the same inputs", so the agent stops and reports a server bug. The server log
holds "Cannot compare tz-naive and tz-aware timestamps". The same date
without the zone works, and `create_cv(initial_train_size=...)` accepts a date
written with the same zone. On data without time zone the date with a zone is
also an internal_error in `forecast`, while `create_cv` answers it with a
clear invalid_argument ("has a time zone (UTC), but the index has none").
"""

import json
import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
ALLOW = Path(tempfile.mkdtemp(prefix="g04-allow-"))
utc = pd.read_csv(DATA / "hourly_utc.csv")
(ALLOW / "hourly_utc.csv").write_text((DATA / "hourly_utc.csv").read_text())
naive = utc.assign(
    date=pd.to_datetime(utc["date"]).dt.strftime("%Y-%m-%d %H:%M:%S")
)
naive.to_csv(ALLOW / "hourly_naive.csv", index=False)
R = []


async def main(c):
    for name in ("hourly_utc.csv", "hourly_naive.csv"):
        _, profile = await call(
            c, "profile", {"data_path": str(ALLOW / name), "target": "load"}
        )
        _, plan = await call(
            c, "plan", {"profile_id": profile["id"], "steps": 24, "estimator": "Ridge"}
        )
        for zone in ("T00:00:00Z", "T00:00:00+00:00", ""):
            args = {"plan_id": plan["id"], "test_size": "2024-04-09" + zone}
            err, fc = await call(c, "forecast", args)
            got = (fc["code"], fc["hint"], fc["details"]) if err else "ok"
            R.append((name, "forecast", zone, json.dumps(args), got))
            args = {"plan_id": plan["id"], "initial_train_size": "2024-04-03" + zone}
            err, cv = await call(c, "create_cv", args)
            got = (cv["code"], cv["message"][:110]) if err else "ok"
            R.append((name, "create_cv", zone, json.dumps(args), got))


run(main, allow_dir=ALLOW)

for name, tool, zone, args, got in R:
    print(f"INPUT {name} {tool}: {args}")
    print(f"OBSERVED {got}")
print(
    "EXPECTED: `forecast` reads a test_size date with a time zone as "
    "`create_cv` reads it (or answers invalid_argument on field test_size "
    "saying to drop the zone), never internal_error with 'do not retry'."
)
got = {(n, t, z): g for n, t, z, a, g in R}
zoned = ("T00:00:00Z", "T00:00:00+00:00")
internal = all(
    got[(n, "forecast", z)] != "ok"
    and got[(n, "forecast", z)][0] == "internal_error"
    and got[(n, "forecast", z)][2]["error_type"] == "TypeError"
    for n in ("hourly_utc.csv", "hourly_naive.csv")
    for z in zoned
)
if (
    internal
    and got[("hourly_utc.csv", "forecast", "")] == "ok"
    and got[("hourly_naive.csv", "forecast", "")] == "ok"
    and all(got[("hourly_utc.csv", "create_cv", z)] == "ok" for z in zoned)
    and got[("hourly_naive.csv", "create_cv", "T00:00:00Z")][0] == "invalid_argument"
):
    print("REPRODUCED")
    sys.exit(0)
print("NOT REPRODUCED")
sys.exit(1)
