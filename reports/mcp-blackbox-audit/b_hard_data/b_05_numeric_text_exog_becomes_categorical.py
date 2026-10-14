"""b-05: numbers written as text in an exogenous column become a categorical
variable silently, and the recommended plan then fails.

Two exogenous columns hold numbers: 'x_pct' written as percentages ('12%')
and 'x_dash' with '-' in a few cells for a missing value. For the target the
same cells give a clear invalid_argument ("values such as ['-'] are not
numbers", with a hint). For an exogenous column `profile` accepts them as
categorical (one level per value), with no notice, and the backtest of the
recommended plan fails with `execution_failed` / "Input contains NaN.".
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"


async def check(c, column):
    args = {
        "data_path": str(DATA / "text_exog.csv"),
        "target": "y",
        "exog_columns": [column],
    }
    print("INPUT profile", json.dumps(args))
    _, p = await call(c, "profile", args)
    categorical = re.findall(r"Categorical exogenous columns:[^\n]*", p["summary"])
    notices = [n["message"] for n in p["notices"]]
    _, pl = await call(c, "plan", {"profile_id": p["id"], "steps": 6})
    _, cv = await call(c, "create_cv", {"plan_id": pl["id"]})
    err, bt = await call(c, "backtest", {"cv_id": cv["id"]})
    failure = None
    if err and bt.get("code") == "execution_failed":
        _, f = await call(c, "get_failure", {"object_id": bt["details"]["failure_id"]})
        failure = re.search(r"\n\n  (.*?)\n", f["text"]).group(1)
    print("  OBSERVED profile:", categorical, "| notices:", notices)
    print("  OBSERVED backtest:", bt.get("code") if err else "ok", "|", failure)
    mentioned = any(column in m and "numer" in m for m in notices)
    return bool(categorical) and failure is not None and not mentioned


async def main(c):
    sample = (DATA / "text_exog.csv").read_text().splitlines()[:3]
    print("First rows of the file:", sample)
    pct = await check(c, "x_pct")
    dash = await check(c, "x_dash")
    args = {"data_path": str(DATA / "text_target_na.csv"), "target": "y"}
    err, tgt = await call(c, "profile", args)
    print("Contrast, '-' in the target:", json.dumps(args), "->", tgt)
    print(
        "EXPECTED: the same treatment as the target, an error or at least a "
        "DataProfileWarning saying the column holds numbers written as text "
        "(values such as '12%', '-') and is taken as categorical; not a "
        "silent categorical column that makes the backtest fail."
    )
    return pct and dash


if __name__ == "__main__":
    ok = run(main, allow_dir=DATA)
    print("REPRODUCED" if ok else "NOT REPRODUCED")
    sys.exit(0 if ok else 1)
