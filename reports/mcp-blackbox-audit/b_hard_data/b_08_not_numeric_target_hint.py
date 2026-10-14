"""b-08: the error for a target written with thousands separators or as
percentages points at `target` and gives the hint for missing-value markers.

'10,025.1' (quoted, ',' file) and '12.2%' are numbers written in a format the
server does not read. The error is invalid_argument with `field: 'target'`,
which the SKILL.md table says to fix ("Fix the argument named in field"),
and its hint talks about cells of missing values marked with '-' or '?'.
Neither says that the format of the numbers is the problem nor that this is
a problem of the file to tell the user about.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"


async def main(c):
    results = []
    for name in ("thousands_quoted.csv", "pct_target.csv"):
        args = {"data_path": str(DATA / name), "target": "y"}
        print("INPUT profile", json.dumps(args))
        print("  rows:", (DATA / name).read_text().splitlines()[1:3])
        err, e = await call(c, "profile", args)
        print("  OBSERVED:", json.dumps(e))
        results.append(
            err
            and e["field"] == "target"
            and "missing values" in (e["hint"] or "")
            and "thousand" not in e["message"] + (e["hint"] or "")
        )
    print(
        "EXPECTED: field 'data_path' (the file, not the argument, is the "
        "problem) and a hint that names the format: thousands separators or "
        "'%' signs are not read, tell the user and, only with their "
        "permission, profile a copy written with plain numbers."
    )
    return all(results)


if __name__ == "__main__":
    ok = run(main, allow_dir=DATA)
    print("REPRODUCED" if ok else "NOT REPRODUCED")
    sys.exit(0 if ok else 1)
