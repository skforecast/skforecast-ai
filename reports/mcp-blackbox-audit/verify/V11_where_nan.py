"""V11 check: where does 'Input contains NaN' come from (fit or predict),
and do the notices of profile name the missing exogenous values?"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "b_hard_data" / "data"


async def main(c):
    _, p = await call(c, "profile", {"data_path": str(DATA / "text_exog.csv"),
                                     "target": "y", "exog_columns": ["x_na"]})
    print("profile notices:", [(n["category"], n["message"][:300]) for n in p["notices"]])
    for args in ({}, {"dropna_from_series": True}, {"estimator": "LGBMRegressor"}):
        _, pl = await call(c, "plan", {"profile_id": p["id"], "steps": 6, **args})
        print(args, "plan notices:", [(n["category"], n["message"][:250]) for n in pl["notices"]])
        _, cv = await call(c, "create_cv", {"plan_id": pl["id"]})
        err, bt = await call(c, "backtest", {"cv_id": cv["id"]})
        if err and bt.get("code") == "execution_failed":
            _, f = await call(c, "get_failure", {"object_id": bt["details"]["failure_id"]})
            lines = [ln for ln in f["text"].splitlines() if "line" in ln and "File" in ln]
            print("FRAMES>>", " | ".join(x.strip() for x in lines[-4:]))
        else:
            print("BT>>", err, bt.get("code") if err else "ok")


run(main, allow_dir=DATA)
