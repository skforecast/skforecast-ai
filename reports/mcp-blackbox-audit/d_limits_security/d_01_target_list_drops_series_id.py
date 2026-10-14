"""d-01: `target` as a list plus `series_id_column`: the id column is dropped.

With long (stacked) data, `profile(target=["y"], series_id_column="sid")`
ignores `series_id_column`, reads the file as wide data and answers that the
user's file has repeated dates, with a hint telling the agent it is a
problem of the user's file. With `target="y"` the same file profiles as 3
series. On wide data, the same combination is accepted and the id column
vanishes without any notice.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
LONG = str(DATA / "long.csv")
WIDE = str(DATA / "wide.csv")
OUT = {}


async def main(c):
    for key, args in [
        ("long_str", {"data_path": LONG, "target": "y", "series_id_column": "sid"}),
        ("long_list", {"data_path": LONG, "target": ["y"], "series_id_column": "sid"}),
        ("wide_list", {"data_path": WIDE, "target": ["y", "y2"],
                       "series_id_column": "x"}),
    ]:
        is_error, payload = await call(c, "profile", args)
        OUT[key] = (args, is_error, payload)


run(main, allow_dir=DATA)

for key, (args, is_error, payload) in OUT.items():
    print("INPUT profile", json.dumps(args))
    if is_error:
        print("OBSERVED error", json.dumps(payload, indent=1)[:1200])
    else:
        lines = [ln for ln in payload["summary"].splitlines()
                 if ln.startswith(("- Series:", "- Target:", "- Exogenous"))]
        print("OBSERVED ok", payload["id"], lines,
              "notices:", [n["message"][:200] for n in payload["notices"]])
    print()

print("EXPECTED: target=['y'] with series_id_column='sid' profiles the 3 stacked")
print("series like target='y' does, or is rejected as a contradictory argument")
print("naming `target`/`series_id_column`; never reported as a problem of the")
print("user's file. On wide data, the dropped column is at least named.")

_, err_str, ok_str = OUT["long_str"]
_, err_list, payload = OUT["long_list"]
_, err_wide, wide = OUT["wide_list"]
blames_file = (
    err_list
    and isinstance(payload, dict)
    and payload.get("field") == "data_path"
    and "problem of the file of the user" in (payload.get("hint") or "")
)
wide_silent = (
    not err_wide
    and "x" not in json.dumps(wide.get("notices", []))
    and "Exogenous columns: none" in wide["summary"]
)
print("long target='y' ok:", not err_str, "| long target=['y'] blames file:",
      blames_file, "| wide drops 'x' silently:", wide_silent)
if not err_str and blames_file:
    print("REPRODUCED")
    sys.exit(0)
print("NOT REPRODUCED")
sys.exit(1)
