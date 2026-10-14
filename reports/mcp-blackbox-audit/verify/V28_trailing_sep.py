"""V28 minimal: a trailing separator only on the data rows vs on every line.

Builds two copies of a 120 row monthly series:
- rows_only.csv: header 'date,y', every data row ends with ','.
- all_lines.csv: header 'date,y,' and every data row ends with ','
  (the usual form of an export that writes a trailing separator).
Prints the code of `profile` for each.
"""

import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

ALLOW = Path(tempfile.mkdtemp(prefix="v28-"))
dates = pd.date_range("2015-01-01", periods=120, freq="MS").strftime("%Y-%m-%d")
values = np.round(100 + np.arange(120) * 0.5, 3)
body = [f"{d},{v}," for d, v in zip(dates, values)]
(ALLOW / "rows_only.csv").write_text("date,y\n" + "\n".join(body) + "\n")
(ALLOW / "all_lines.csv").write_text("date,y,\n" + "\n".join(body) + "\n")
OUT = {}


async def main(c):
    for name in ("rows_only.csv", "all_lines.csv"):
        is_error, payload = await call(
            c, "profile", {"data_path": str(ALLOW / name), "target": "y"}
        )
        if is_error:
            OUT[name] = ("error", payload.get("code"), payload.get("message"))
        else:
            lines = [ln for ln in payload["summary"].splitlines()
                     if ln.startswith(("- Frequency", "- Exogenous", "- Missing"))]
            OUT[name] = ("ok", lines, [n["category"] for n in payload["notices"]])


run(main, allow_dir=ALLOW)
for name, obs in OUT.items():
    print(name, "->", obs)
rows_only = OUT["rows_only.csv"]
if rows_only[0] == "error" and rows_only[1] != "data_unreadable":
    print("REPRODUCED")
    sys.exit(0)
print("NOT REPRODUCED")
sys.exit(1)
