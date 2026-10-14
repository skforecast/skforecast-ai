"""a-03: the script of a forecast with exogenous variables reads another file.

`forecast(plan_id, exog_path=<allowed dir>/weather_next_12_weeks.csv)` runs,
but `get_code(forecast_id)` returns a script that reads the data by its
absolute path and the future exogenous values from 'exog_future.csv' relative
to the working directory, a file that does not exist. SKILL.md: "`get_code`
returns the Python script that ran ... so the user can reproduce any result
without the server ... Hand the script as it is". Run as it is (in any
directory, even the allowed one), it fails with FileNotFoundError.
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
ALLOW = Path(tempfile.mkdtemp(prefix="a03-allow-"))
shutil.copy(DATA / "exog_hist.csv", ALLOW / "exog_hist.csv")
shutil.copy(DATA / "exog_future.csv", ALLOW / "weather_next_12_weeks.csv")
RESULT = {}


async def main(c):
    _, profile = await call(
        c,
        "profile",
        {"data_path": str(ALLOW / "exog_hist.csv"), "target": "demand"},
    )
    _, plan = await call(c, "plan", {"profile_id": profile["id"], "steps": 12})
    args = {
        "plan_id": plan["id"],
        "exog_path": str(ALLOW / "weather_next_12_weeks.csv"),
    }
    print("INPUT forecast:", json.dumps(args))
    err, fc = await call(c, "forecast", args)
    print("OBSERVED forecast error:", err, "files:", fc.get("files"))
    _, code = await call(c, "get_code", {"object_id": fc["id"]})
    print("OBSERVED get_code keys:", sorted(code))
    lines = [ln for ln in code["code"].splitlines() if "read_csv" in ln]
    print("OBSERVED read_csv lines of the script:")
    for ln in lines:
        print("   ", ln)
    RESULT["code"] = code["code"]


run(main, allow_dir=ALLOW)
script = ALLOW / "forecast_script.py"
script.write_text(RESULT["code"])
proc = subprocess.run(
    [sys.executable, str(script)],
    cwd=ALLOW,
    capture_output=True,
    text=True,
    timeout=300,
)
tail = (proc.stderr.strip().splitlines() or [""])[-1]
print("OBSERVED running the script in the allowed dir: returncode", proc.returncode)
print("   ", tail)
print(
    "EXPECTED: the script reads the file that ran, by its absolute path "
    "(as it does for the data), or get_code says which file to put where."
)
if (
    "read_csv('exog_future.csv')" in RESULT["code"]
    and proc.returncode != 0
    and "FileNotFoundError" in proc.stderr
):
    print("REPRODUCED")
    sys.exit(0)
print("NOT REPRODUCED")
sys.exit(1)
