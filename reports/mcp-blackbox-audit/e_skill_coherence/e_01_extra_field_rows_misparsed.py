"""e-01: rows with one field more than the header are not `data_unreadable`.

SKILL.md, table of errors: `data_unreadable` is "The file is not a CSV the
server can read (empty, binary, not UTF-8, or rows with more fields than the
header)". That holds when the extra field is in a middle row, but not when
every data row ends with a separator (a common export) or when only the
first data row has an extra field: pandas then takes the first column as
the index and every column shifts one place to the left.

- trailing separator in every row: `insufficient_data`, "Target column 'y'
  has no values", which tells the agent the user's column is empty;
- extra field in the first data row only: `profile` succeeds, with the
  dates as an exogenous column, no datetime index and 119 of 120 targets
  missing.

Run from the repository root:
    python reports/mcp-blackbox-audit/e_skill_coherence/e_01_extra_field_rows_misparsed.py
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
ALLOW = Path(tempfile.mkdtemp(prefix="e01-"))
lines = (DATA / "single.csv").read_text().splitlines()
trailing = ALLOW / "trailing_separator.csv"
trailing.write_text(lines[0] + "\n" + "\n".join(x + "," for x in lines[1:]) + "\n")
first_row = ALLOW / "extra_field_first_row.csv"
first_row.write_text(
    lines[0] + "\n" + lines[1] + ",9\n" + "\n".join(lines[2:]) + "\n"
)
middle_row = ALLOW / "extra_field_middle_row.csv"
middle = list(lines)
middle[50] = middle[50] + ",9"
middle_row.write_text("\n".join(middle) + "\n")

observed = {}


async def main(c):
    for path in (trailing, first_row, middle_row):
        args = {"data_path": str(path), "target": "y"}
        print("INPUT profile", json.dumps(args))
        print("  first lines:", path.read_text().splitlines()[:3])
        is_error, payload = await call(c, "profile", args)
        if is_error:
            observed[path.name] = ("error", payload.get("code"), payload["message"])
        else:
            summary = payload["summary"]
            start = summary.index("<dataset>")
            observed[path.name] = ("ok", None, summary[start:start + 600])
        print("OBSERVED", observed[path.name])
        print()


run(main, allow_dir=ALLOW)

print(
    "EXPECTED: the three files fail with code 'data_unreadable' (rows with "
    "more fields than the header), as the middle row case does."
)
trail = observed["trailing_separator.csv"]
first = observed["extra_field_first_row.csv"]
symptom = (
    trail[0] == "ok" or trail[1] != "data_unreadable"
    or first[0] == "ok" or first[1] != "data_unreadable"
)
if symptom:
    print("REPRODUCED")
    sys.exit(0)
print("NOT REPRODUCED")
sys.exit(1)
