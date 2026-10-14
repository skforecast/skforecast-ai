"""b-06: a date column written as yyyymmdd integers becomes an exogenous
variable, and naming it as `date_column` is rejected.

A daily file whose column 'date' holds 20200101, 20200102, ... (a very
common export format). Without `date_column`, `profile` takes 'date' as an
exogenous regressor and the data as having no dates; `plan` then asks the
agent (FutureExogNotice) for the future values of 'date'. With
`date_column: 'date'`, `profile` says the values "could not be parsed as
timestamps", although they are unambiguous.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"


async def main(c):
    path = str(DATA / "date_yyyymmdd.csv")
    print("First rows of the file:", (DATA / "date_yyyymmdd.csv").read_text().split()[:3])
    args = {"data_path": path, "target": "y"}
    print("INPUT profile", json.dumps(args))
    _, p = await call(c, "profile", args)
    exog = re.search(r"Exogenous columns:[^\n]*", p["summary"]).group(0)
    freq = re.search(r"Frequency:[^\n]*", p["summary"]).group(0)
    print("OBSERVED profile:", exog, "|", freq)
    _, pl = await call(c, "plan", {"profile_id": p["id"], "steps": 7})
    future = [n["message"] for n in pl["notices"] if n["category"] == "FutureExogNotice"]
    print("OBSERVED plan FutureExogNotice:", future)
    args = {"data_path": path, "target": "y", "date_column": "date"}
    print("INPUT profile", json.dumps(args))
    err, e = await call(c, "profile", args)
    print("OBSERVED:", e)
    print(
        "EXPECTED: 'date' read as dates with format '%Y%m%d' (daily "
        "frequency), or at least a notice that 'date' looks like compact "
        "dates and is used as an exogenous variable, and an error for "
        "`date_column` that says the format is not supported instead of "
        "'could not be parsed as timestamps'."
    )
    return (
        exog.endswith("date")
        and "unknown" in freq
        and any("'date'" in m for m in future)
        and err
        and "could not be parsed" in e["message"]
    )


if __name__ == "__main__":
    ok = run(main, allow_dir=DATA)
    print("REPRODUCED" if ok else "NOT REPRODUCED")
    sys.exit(0 if ok else 1)
