"""e-07: `fixed_train_size` with `refit` false is a warning, not the documented error.

Schema of `create_cv`, `fixed_train_size`: "Only with `refit` true or an
integer: with `refit` false or null it is an error, as it would not run
(ForecasterStats aside)."

The server creates the strategy and adds an IgnoredArgumentWarning notice
("has no effect"); the summary still lists `fixed_train_size: True`. The
behaviour is reasonable, but the description tells the agent it cannot
happen, so an agent that wants to check a strategy before running it may
avoid a valid combination or not expect the notice.

Run from the repository root:
    python reports/mcp-blackbox-audit/e_skill_coherence/e_07_fixed_train_size_without_refit.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
out = {}


async def main(c):
    _, prof = await call(
        c, "profile", {"data_path": str(DATA / "single.csv"), "target": "y"}
    )
    _, plan = await call(c, "plan", {"profile_id": prof["id"], "steps": 12})
    descr = [t for t in (await c.list_tools()).tools if t.name == "create_cv"]
    out["doc"] = descr[0].input_schema["properties"]["fixed_train_size"][
        "description"]
    for refit in (None, False):
        args = {"plan_id": plan["id"], "fixed_train_size": True}
        if refit is not None:
            args["refit"] = refit
        print("INPUT create_cv", json.dumps(args))
        is_error, cv = await call(c, "create_cv", args)
        got = cv if is_error else {"id": cv["id"], "notices": cv["notices"]}
        out[str(refit)] = (is_error, got)
        print("OBSERVED", json.dumps(got)[:600])


run(main, allow_dir=DATA)

print("DOCUMENTED:", out["doc"])
print("EXPECTED: an error (as documented), or a description that says it "
      "is accepted with an IgnoredArgumentWarning notice.")
if not out["None"][0] and not out["False"][0] and "is an error" in out["doc"]:
    print("REPRODUCED")
    sys.exit(0)
print("NOT REPRODUCED")
sys.exit(1)
