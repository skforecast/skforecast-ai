"""d-07: `fixed_train_size` without `refit` is described as an error; it is not.

The input schema of `create_cv` says of `fixed_train_size`: "Only with
`refit` true or an integer: with `refit` false or null it is an error, as it
would not run". The server accepts it, with a notice that it has no effect,
and the backtest of that strategy runs.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
OUT = {}


async def main(c):
    tools = await c.list_tools()
    tool = next(t for t in tools.tools if t.name == "create_cv")
    schema = tool.input_schema if hasattr(tool, "input_schema") else tool.inputSchema
    OUT["desc"] = schema["properties"]["fixed_train_size"]["description"]
    _, p = await call(c, "profile",
                      {"data_path": str(DATA / "monthly.csv"), "target": "y"})
    _, pl = await call(c, "plan", {"profile_id": p["id"], "steps": 12})
    OUT["args"] = {"plan_id": pl["id"], "fixed_train_size": True, "refit": False}
    OUT["cv"] = await call(c, "create_cv", OUT["args"])
    if not OUT["cv"][0]:
        OUT["bt"] = await call(c, "backtest", {"cv_id": OUT["cv"][1]["id"]})


run(main, allow_dir=DATA)

print("SCHEMA fixed_train_size:", OUT["desc"])
print("INPUT create_cv", json.dumps(OUT["args"]))
err, cv = OUT["cv"]
print("OBSERVED create_cv", "error" if err else "ok",
      json.dumps(cv)[:200] if err else [n["message"][:200] for n in cv["notices"]])
if not err:
    bt_err, bt = OUT["bt"]
    print("OBSERVED backtest", "error" if bt_err else "ok " + bt["id"])
print("EXPECTED: what the schema says (an error), or a schema that says it is")
print("accepted with a notice and has no effect.")
if "it is an error" in OUT["desc"] and not err and not OUT["bt"][0]:
    print("REPRODUCED")
    sys.exit(0)
print("NOT REPRODUCED")
sys.exit(1)
