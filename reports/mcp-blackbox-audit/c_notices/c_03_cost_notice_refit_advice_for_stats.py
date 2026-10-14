"""c-03: CostNotice offers `refit` remedies that cannot cut a Stats cost.

A ForecasterStats plan backtested over 51 folds costs 51 estimator fits.
The `CostNotice` of `create_cv`, the one that tells the agent to stop and
"tell the user those numbers and the cheaper strategies", lists "an integer
`refit`, fewer folds, `refit=false`" even when `refit` is already false.
The `LongTrainingWarning` of the same response says the opposite
("skforecast refits it in every fold whatever `refit` says"), and so does
the SKILL.md ("`refit=false` ... no help for ForecasterStats"). Following
the CostNotice, `create_cv(refit=false)` or `refit=5` still costs 51 fits.
The CostNotice of a ForecasterFoundation plan above 2000 inference windows
(50 series x 41 folds, generated at run time) gives the same `refit` list,
while its LongTrainingWarning only offers fewer folds or fewer series.
"""

import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
RESULT = {}
ALLOW = Path(tempfile.mkdtemp(prefix="c03-allow-"))
shutil.copy(DATA / "monthly.csv", ALLOW / "monthly.csv")


def write_m50():
    rng = np.random.default_rng(0)
    dates = pd.date_range("2020-01-01", periods=60, freq="MS")
    rows = []
    for k in range(50):
        v = 100 + 10 * np.sin(np.arange(60) * 2 * np.pi / 12) + rng.normal(0, 1, 60)
        rows += [(d.strftime("%Y-%m-%d"), f"s{k:02d}", round(x, 3)) for d, x in
                 zip(dates, v)]
    pd.DataFrame(rows, columns=["date", "sid", "y"]).to_csv(
        ALLOW / "m50.csv", index=False
    )


def by_category(notices, category):
    return next((n["message"] for n in notices if n["category"] == category), "")


async def main(c):
    path = str(ALLOW / "monthly.csv")
    _, p = await call(c, "profile", {"data_path": path, "target": "y"})
    _, plan = await call(
        c, "plan",
        {"profile_id": p["id"], "steps": 1, "forecaster": "ForecasterStats"},
    )
    base = {"plan_id": plan["id"], "initial_train_size": 69, "fold_stride": 1}
    print("INPUT plan(steps=1, forecaster='ForecasterStats') ->",
          "create_cv(initial_train_size=69, fold_stride=1)")
    _, cv = await call(c, "create_cv", base)
    cost_notice = by_category(cv["notices"], "CostNotice")
    long_training = by_category(cv["notices"], "LongTrainingWarning")
    print("OBSERVED cost:", cv["cost"])
    print("OBSERVED CostNotice:", cost_notice)
    print("OBSERVED LongTrainingWarning:", long_training)
    fits = {}
    for refit in (False, 5):
        _, alt = await call(c, "create_cv", {**base, "refit": refit})
        fits[refit] = alt["cost"]["estimator_fits"]
        print(f"OBSERVED create_cv(refit={refit!r}) estimator_fits:", fits[refit],
              "CostNotice still there:",
              bool(by_category(alt["notices"], "CostNotice")))
    write_m50()
    _, p50 = await call(
        c, "profile",
        {"data_path": str(ALLOW / "m50.csv"), "target": "y",
         "series_id_column": "sid"},
    )
    _, fplan = await call(
        c, "plan",
        {"profile_id": p50["id"], "steps": 1, "forecaster": "ForecasterFoundation"},
    )
    print("INPUT 50 series x 60 months: plan(steps=1,",
          "forecaster='ForecasterFoundation') ->",
          "create_cv(initial_train_size=19, fold_stride=1)")
    _, fcv = await call(
        c, "create_cv",
        {"plan_id": fplan["id"], "initial_train_size": 19, "fold_stride": 1},
    )
    f_cost = by_category(fcv["notices"], "CostNotice")
    print("OBSERVED cost:", fcv["cost"])
    print("OBSERVED CostNotice:", f_cost)
    print("OBSERVED LongTrainingWarning:",
          by_category(fcv["notices"], "LongTrainingWarning"))
    RESULT["foundation_refit_offered"] = "`refit=false`" in f_cost
    RESULT.update(
        refit_offered="`refit=false`" in cost_notice
        and "an integer `refit`" in cost_notice,
        contradicted="whatever `refit` says" in long_training,
        no_effect=fits[False] == fits[5] == cv["cost"]["estimator_fits"] > 50,
    )


run(main, allow_dir=ALLOW)
print(
    "EXPECTED: for a ForecasterStats plan (and a foundation plan) the CostNotice"
    " offers only remedies that lower its cost (fewer folds: a later"
    " initial_train_size or a larger fold_stride), as its LongTrainingWarning"
    " and the SKILL.md do; at least it does not offer `refit=false` when refit"
    " is already false."
)
print("RESULT", RESULT)
if all(RESULT.values()):
    print("REPRODUCED")
    sys.exit(0)
print("NOT REPRODUCED")
sys.exit(1)
