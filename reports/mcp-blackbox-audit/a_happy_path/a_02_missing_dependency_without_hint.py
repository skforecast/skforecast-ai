"""a-02: `missing_dependency` of an ML estimator has no hint.

SKILL.md: "missing_dependency | Tell the user which package to install;
`hint` says how, for pip and for uvx." For a foundation model the hint does
say it; for XGBRegressor (listed by the schema of `plan`) the error has
`hint: null` and `details: null`, and `plan` and `create_cv` accept the
estimator without a word, so the error only shows at `backtest`/`forecast`.
"""

import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
RESULT = {}


async def main(c):
    _, profile = await call(
        c, "profile", {"data_path": str(DATA / "monthly.csv"), "target": "sales"}
    )
    args = {"profile_id": profile["id"], "steps": 12, "estimator": "XGBRegressor"}
    print("INPUT plan:", json.dumps(args))
    plan_err, plan = await call(c, "plan", args)
    print("OBSERVED plan: error =", plan_err, "notices =", plan.get("notices"))
    _, cv = await call(c, "create_cv", {"plan_id": plan["id"]})
    print("INPUT backtest:", json.dumps({"cv_id": cv["id"]}))
    err, payload = await call(c, "backtest", {"cv_id": cv["id"]})
    print("OBSERVED backtest:", json.dumps(payload, indent=1))
    ferr, fpayload = await call(c, "forecast", {"plan_id": plan["id"]})
    print("OBSERVED forecast:", json.dumps(fpayload))
    RESULT["ok"] = (
        err
        and isinstance(payload, dict)
        and payload.get("code") == "missing_dependency"
        and payload.get("hint") is None
    )


run(main, allow_dir=DATA)
print(
    "EXPECTED: a hint as for a foundation model, e.g. 'Ask the user to install "
    "it where the server runs and to restart the server: `pip install xgboost` "
    "in its Python environment, or `--with xgboost` added to the uvx command', "
    "and details {'package': 'xgboost'} (ideally a notice already at `plan`)."
)
if importlib.util.find_spec("xgboost") is None and RESULT.get("ok"):
    print("REPRODUCED")
    sys.exit(0)
print("NOT REPRODUCED")
sys.exit(1)
