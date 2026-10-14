"""g-02: long data whose series ids are numbers fails every run with KeyError.

Store ids such as '001', '002', '010' (zero-padded, as most store, SKU or
sensor systems write them) are read as the integers 1, 2 and 10: the
profile names the series '1', '2', '10', so the zeros are lost. profile,
plan and create_cv accept the data without a notice, then `backtest`,
`forecast` and `compare` all fail with `execution_failed` "The generated
script failed with KeyError" (no field, no hint), `get_failure` shows
`KeyError: 1` raised inside skforecast, and the script of `get_code` fails the
same way. The same file with letter ids ('S01', ...) runs. Nothing tells the
agent that the ids are the cause, and the only way out (rewriting the ids)
is a change to the user's data that the agent has no clue to propose.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
R = {}


async def main(c):
    for name in ("stores_padded_ids.csv", "stores_letter_ids.csv"):
        out = R.setdefault(name, {})
        args = {
            "data_path": str(DATA / name),
            "target": "sales",
            "series_id_column": "store",
        }
        print("INPUT profile:", json.dumps(args))
        _, profile = await call(c, "profile", args)
        out["series"] = [
            ln.split("(")[1].split(")")[0]
            for ln in profile["summary"].splitlines()
            if ln.startswith("- Target statistics (")
        ]
        out["profile_notices"] = [n["category"] for n in profile["notices"]]
        _, plan = await call(c, "plan", {"profile_id": profile["id"], "steps": 12})
        _, cv = await call(c, "create_cv", {"plan_id": plan["id"]})
        out["cv_notices"] = [n["category"] for n in cv["notices"]]
        for tool, a in (
            ("backtest", {"cv_id": cv["id"]}),
            ("forecast", {"plan_id": plan["id"]}),
            ("compare", {"cv_id": cv["id"]}),
        ):
            err, res = await call(c, tool, a)
            out[tool] = (res.get("code"), res.get("field"), res.get("hint")) if err else "ok"
            if tool == "backtest" and err:
                out["backtest_message"] = res["message"]
                _, fail = await call(
                    c, "get_failure", {"object_id": res["details"]["failure_id"]}
                )
                text = fail["text"]
                out["failure_head"] = text.split("Failed line")[0].strip()
        _, code = await call(c, "get_code", {"object_id": plan["id"]})
        out["code"] = code["code"]


run(main, allow_dir=DATA)

for name, out in R.items():
    script = Path(tempfile.mkdtemp(prefix="g02-")) / "forecast.py"
    script.write_text(out["code"])
    proc = subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True, timeout=300
    )
    last = (proc.stderr.strip().splitlines() or [""])[-1]
    out["script"] = "ok" if proc.returncode == 0 else last
    print(f"OBSERVED {name}:")
    print("   series named in the profile:", out["series"])
    print("   notices of profile / create_cv:", out["profile_notices"], out["cv_notices"])
    for tool in ("backtest", "forecast", "compare"):
        print(f"   {tool}:", out[tool])
    if "backtest_message" in out:
        print("   backtest message:", out["backtest_message"])
        print("   get_failure:", out["failure_head"].replace("\n", " "))
    print("   get_code(plan) script run standalone:", out["script"])
print(
    "EXPECTED: series ids kept as the text of the file ('001', '002', '010') "
    "and the runs working as with letter ids; at the least, an error that "
    "names the series ids as the cause, with a field and a hint, before "
    "anything runs."
)
pad, letters = R["stores_padded_ids.csv"], R["stores_letter_ids.csv"]
if (
    pad["series"] == ["1", "2", "10"]
    and pad["backtest"][0] == "execution_failed"
    and pad["forecast"][0] == "execution_failed"
    and pad["compare"][0] == "all_candidates_failed"
    and "KeyError" in pad["failure_head"]
    and pad["script"].startswith("KeyError")
    and letters["backtest"] == letters["forecast"] == "ok"
):
    print("REPRODUCED")
    sys.exit(0)
print("NOT REPRODUCED")
sys.exit(1)
