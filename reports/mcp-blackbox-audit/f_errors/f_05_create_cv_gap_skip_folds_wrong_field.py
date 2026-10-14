"""f-05: `create_cv` errors caused by `gap` or `skip_folds` point elsewhere.

With a 12-step plan on 120 monthly rows and only one argument changed:
- `gap=40`: invalid_argument with field `initial_train_size` (not sent).
- `gap=30`: insufficient_data, field null, and a hint whose remedies are
  `initial_train_size`, `fold_stride` and `steps`, not `gap`.
- `skip_folds=50`: insufficient_data, field null, same hint, not
  `skip_folds` (while `skip_folds=[50]` gets field `skip_folds`).
An agent that acts on `field` and `hint`, as the SKILL.md asks, changes
the wrong argument (a smaller `initial_train_size` cannot help a
`skip_folds` that keeps only fold 0).
Expected: field set to the argument the caller sent that leaves fewer than
two folds (`gap`, `skip_folds`), and a hint that names it.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
PATH = str(DATA / "monthly.csv")


async def main(c):
    _, prof = await call(c, "profile", {"data_path": PATH, "target": "y"})
    _, plan = await call(c, "plan", {"profile_id": prof["id"], "steps": 12})
    res = {}
    for extra in ({"gap": 40}, {"gap": 30}, {"skip_folds": 50}):
        args = {"plan_id": plan["id"], **extra}
        print("INPUT create_cv:", json.dumps(args))
        err, out = await call(c, "create_cv", args)
        name = next(iter(extra))
        res[f"{name}={extra[name]}"] = out if err else {}
        if err:
            print(
                "OBSERVED code/field:", out.get("code"), out.get("field"),
                "| hint names it:", f"`{name}`" in (out.get("hint") or ""),
            )
            print("   hint:", out.get("hint"))
    print(
        "EXPECTED: field 'gap' / 'skip_folds' (the argument sent) and a hint "
        "naming it."
    )
    g40, g30, s50 = res["gap=40"], res["gap=30"], res["skip_folds=50"]
    return (
        g40.get("field") == "initial_train_size"
        and g30.get("field") is None
        and s50.get("field") is None
        and "`skip_folds`" not in (s50.get("hint") or "")
    )


ok = run(main, allow_dir=DATA)
print("REPRODUCED" if ok else "NOT REPRODUCED")
sys.exit(0 if ok else 1)
