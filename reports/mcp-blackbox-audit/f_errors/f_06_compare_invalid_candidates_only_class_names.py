"""f-06: `compare` runs candidates whose configuration `plan` would reject,
and `all_candidates_failed` names only the exception class.

A candidate with a typo (`estimator: 'Ridg'`, an unknown key of
`estimator_kwargs`) is not checked before the run: with `baseline: false`
the answer is `all_candidates_failed` listing "- typo_est: ValueError",
field null, so the agent needs `get_failure` and a traceback to learn what
`plan` says in one line ("'Ridg' is not a supported estimator..."). The
leaderboard of a comparison that succeeds does carry that message, so it
is not withheld for privacy. With the default baseline the same call
succeeds and crowns the baseline.
Expected: invalid_argument with field `candidates[i].config.<key>` before
any run, as `plan` does; failing that, the message of each candidate in
`all_candidates_failed`.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
PATH = str(DATA / "monthly.csv")
CANDIDATES = [
    {"name": "typo_est", "config": {"estimator": "Ridg"}},
    {"name": "typo_kw", "config": {"estimator_kwargs": {"alphaa": 1.0}}},
]


async def main(c):
    _, prof = await call(c, "profile", {"data_path": PATH, "target": "y"})
    _, plan = await call(c, "plan", {"profile_id": prof["id"], "steps": 12})
    _, cv = await call(c, "create_cv", {"plan_id": plan["id"]})
    pargs = {"profile_id": prof["id"], "steps": 12, "estimator": "Ridg"}
    _, perr = await call(c, "plan", pargs)
    print("CONTRAST plan(estimator='Ridg'):", json.dumps(perr)[:260])
    args = {"cv_id": cv["id"], "baseline": False, "candidates": CANDIDATES}
    print("INPUT compare:", json.dumps(args))
    err, out = await call(c, "compare", args)
    print("OBSERVED:", json.dumps(out)[:700] if err else "success")
    args2 = {"cv_id": cv["id"], "candidates": CANDIDATES[:1]}
    err2, out2 = await call(c, "compare", args2)
    if not err2:
        best = [ln for ln in out2["summary"].splitlines() if "Best:" in ln]
        print("OBSERVED with default baseline: success;", best[0][:240])
    print(
        "EXPECTED: invalid_argument, field 'candidates[0].config.estimator', "
        "before any run (or at least each message in all_candidates_failed)."
    )
    return (
        err
        and out.get("code") == "all_candidates_failed"
        and "typo_est: ValueError\n" in out.get("message", "") + "\n"
        and "not a supported estimator" not in out.get("message", "")
    )


ok = run(main, allow_dir=DATA)
print("REPRODUCED" if ok else "NOT REPRODUCED")
sys.exit(0 if ok else 1)
