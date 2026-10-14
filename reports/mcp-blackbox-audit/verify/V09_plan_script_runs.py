"""V09 check: with decimal=',' on a ';' file with '.' decimals, what do the
profile and plan notices say, and does the plan script of get_code run?"""

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "b_hard_data" / "data"
OUT = {}


async def main(c):
    err, p = await call(c, "profile", {"data_path": str(DATA / "semi_dot.csv"),
                                       "target": "y", "sep": ";", "decimal": ","})
    print("profile err", err, "notices", [(n["category"], n["message"][:200]) for n in p["notices"]])
    print([ln for ln in p["summary"].splitlines() if "arget" in ln][:6])
    err, pl = await call(c, "plan", {"profile_id": p["id"], "steps": 6})
    print("plan err", err, "notices", [(n["category"], n["message"][:200]) for n in pl["notices"]])
    _, code = await call(c, "get_code", {"object_id": pl["id"]})
    OUT["code"] = code["code"]
    err, fc = await call(c, "forecast", {"plan_id": pl["id"]})
    print("forecast err", err, [ln for ln in fc["summary"].splitlines() if "pred" in ln][:2])


run(main, allow_dir=DATA)
d = Path(tempfile.mkdtemp())
(d / "plan.py").write_text(OUT["code"])
proc = subprocess.run([sys.executable, str(d / "plan.py")], capture_output=True, text=True, timeout=300)
print("plan script returncode", proc.returncode)
print("\n".join(proc.stderr.strip().splitlines()[-3:]))
print([ln for ln in OUT["code"].splitlines() if "numeric" in ln.lower() or "read_csv" in ln])
print("----- plan script head -----")
print("\n".join(OUT["code"].splitlines()[:60]))
print("----- stdout tail -----")
print("\n".join(proc.stdout.strip().splitlines()[-15:]))
