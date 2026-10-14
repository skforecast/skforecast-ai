"""b-01: thousands separators read silently as decimal marks.

A ';' file (the Excel export of Spanish, German or French locales) writes
amounts of 1000 or more with '.' as thousands separator ('1.020', '1.234')
and smaller ones without it ('870', '987'). `profile` detects the decimal
mark as '.', reads '1.020' as 1.02, and the whole workflow runs on a target
that jumps between hundreds and units, with no notice and no error.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
FILE = DATA / "thousands_dot_mixed.csv"


async def main(c):
    args = {"data_path": str(FILE), "target": "y"}
    print("INPUT profile", json.dumps(args))
    print("First rows of the file:", FILE.read_text().splitlines()[:7])
    err, p = await call(c, "profile", args)
    if err:
        print("OBSERVED error", p)
        return False
    stats = re.search(r"Target statistics:[^\n]*", p["summary"]).group(0)
    print("OBSERVED profile:", stats)
    print("OBSERVED profile notices:", [n["message"] for n in p["notices"]])
    _, pl = await call(c, "plan", {"profile_id": p["id"], "steps": 6})
    err, fc = await call(c, "forecast", {"plan_id": pl["id"]})
    preds = re.search(r"pred: [^\n]*", fc["summary"]).group(0) if not err else fc
    print("OBSERVED forecast:", preds)
    print("OBSERVED forecast notices:", [n["category"] for n in fc["notices"]])
    print(
        "EXPECTED: the file holds amounts between 870 and 2050; profile "
        "either reads '1.020' as 1020 or stops with data_unreadable (the "
        "decimal mark cannot be told), as it does for '1,841' in a tab file. "
        "At least a notice should say that the column mixes magnitudes."
    )
    minimum = float(re.search(r"min ([-\d.e]+)", stats).group(1))
    mentions = any(
        re.search(r"thousand|decimal", n["message"], re.I) for n in p["notices"]
    )
    return minimum < 2 and not mentions


if __name__ == "__main__":
    ok = run(main, allow_dir=DATA)
    print("REPRODUCED" if ok else "NOT REPRODUCED")
    sys.exit(0 if ok else 1)
