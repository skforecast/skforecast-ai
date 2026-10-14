"""c-02: create_cv accepts `skip_folds` for ForecasterStats; backtest fails.

For a ForecasterStats plan, `create_cv(skip_folds=2)` succeeds without any
notice and reports the reduced cost (`n_folds: 3`, `n_fits: 3`), so an agent
that takes "fewer folds" literally believes it found a cheaper strategy.
`backtest` then fails with an opaque `execution_failed` whose traceback
(`get_failure`) says "`skip_folds` is not allowed for ForecasterStats".
The server knows it: its own LongTrainingWarning for ForecasterStats says
"`skip_folds` is not allowed for it", and for the documented cases (a
direct forecaster with `gap`, a first window too short) `create_cv` carries
a notice and `backtest` returns a clear error. A `compare` without
candidates on such a strategy also runs ForecasterStats, which fails and is
ranked last, although its cost was counted in `compare_estimator_fits`.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
RESULT = {}


async def main(c):
    path = str(DATA / "monthly.csv")
    _, p = await call(c, "profile", {"data_path": path, "target": "y"})
    _, plan = await call(
        c, "plan",
        {"profile_id": p["id"], "steps": 6, "forecaster": "ForecasterStats"},
    )
    args = {"plan_id": plan["id"], "initial_train_size": 84, "skip_folds": 2}
    print("INPUT plan(steps=6, forecaster='ForecasterStats') ->",
          "create_cv(initial_train_size=84, skip_folds=2) -> backtest")
    cv_err, cv = await call(c, "create_cv", args)
    print("OBSERVED create_cv error:", cv_err, "cost:", cv.get("cost"),
          "notices:", [n["category"] for n in cv.get("notices", [])])
    bt_err, bt = await call(c, "backtest", {"cv_id": cv["id"]})
    print("OBSERVED backtest:", bt)
    text = ""
    if bt_err and isinstance(bt, dict) and (bt.get("details") or {}).get(
        "failure_id"
    ):
        _, failure = await call(
            c, "get_failure", {"object_id": bt["details"]["failure_id"]}
        )
        text = failure["text"].splitlines()[2].strip()
        print("OBSERVED get_failure:", text)

    _, rplan = await call(c, "plan", {"profile_id": p["id"], "steps": 6})
    _, rcv = await call(
        c, "create_cv",
        {"plan_id": rplan["id"], "initial_train_size": 84, "skip_folds": 2},
    )
    print("INPUT plan(steps=6) -> create_cv(initial_train_size=84, skip_folds=2)",
          "-> compare()")
    print("OBSERVED create_cv cost:", rcv["cost"],
          "notices:", [n["category"] for n in rcv["notices"]])
    _, cmp = await call(c, "compare", {"cv_id": rcv["id"]})
    board = pd.read_csv(cmp["files"]["leaderboard"])
    stats_row = board[board["name"] == "ForecasterStats"]
    print("OBSERVED compare leaderboard rows (name, error):")
    for _, row in board.iterrows():
        print("  ", row["name"], "|", row.get("error"))
    RESULT.update(
        cv_accepted=not cv_err and cv["notices"] == [],
        bt_opaque=bt_err and bt.get("code") == "execution_failed",
        skip_folds_cause="skip_folds" in text and "not allowed" in text,
        compare_stats_failed=bool(len(stats_row))
        and "skip_folds" in str(stats_row["error"].iloc[0]),
    )


run(main, allow_dir=DATA)
print(
    "EXPECTED: create_cv rejects skip_folds for a ForecasterStats plan"
    " (invalid_argument, field skip_folds), or at least carries a notice that"
    " backtest of this plan will fail, as it does for gap with a direct"
    " forecaster; compare without candidates leaves ForecasterStats out (or"
    " says why) instead of counting it and failing it."
)
print("RESULT", RESULT)
if RESULT["cv_accepted"] and RESULT["bt_opaque"] and RESULT["skip_folds_cause"]:
    print("REPRODUCED")
    sys.exit(0)
print("NOT REPRODUCED")
sys.exit(1)
