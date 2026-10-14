"""b-03: MAPE of 1e13 or more reported on targets with zeros, without notice.

Case A: a target that takes negative values and zeros (min < 0) gets
`mean_absolute_percentage_error` in its default panel (a target whose
minimum is exactly 0 does not), and the backtest reports it as about 3.3e13.
Case B: a plan that asks for MAPE on a target with zeros gets no notice at
`plan`, and the backtest reports about 6.8e15. In both, the only notice is
`MetricUnitNotice`, which tells the agent to multiply the value by 100.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"


async def backtest(c, name, plan_args):
    _, p = await call(c, "profile", {"data_path": str(DATA / name), "target": "y"})
    stats = re.search(r"Target statistics:[^\n]*", p["summary"]).group(0)
    args = {"profile_id": p["id"], "steps": 6, **plan_args}
    print(f"INPUT {name}: profile -> plan {json.dumps(plan_args)} -> create_cv")
    _, pl = await call(c, "plan", args)
    _, cv = await call(c, "create_cv", {"plan_id": pl["id"]})
    _, bt = await call(c, "backtest", {"cv_id": cv["id"]})
    results = re.search(r"Results: [^\n]*?\. ", bt["summary"]).group(0)
    mape = float(
        re.search(r"mean_absolute_percentage_error: (\d+(?:\.\d+)?)", results).group(1)
    )
    full = pl["notices"] + bt["notices"]
    notices = [(n["category"], n["message"][:120]) for n in full]
    print(f"OBSERVED {name}: {stats}")
    print(f"OBSERVED {name}: {results}")
    print(f"OBSERVED {name}: plan+backtest notices {notices}")
    zero_notice = any(re.search(r"zero", n["message"], re.I) for n in full)
    return mape, zero_notice


async def main(c):
    mape_a, notice_a = await backtest(c, "neg_zero.csv", {})
    mape_b, notice_b = await backtest(
        c, "sales_zeros.csv", {"metric": "mean_absolute_percentage_error"}
    )
    print(
        "EXPECTED: MAPE left out of the default panel whenever the target has "
        "zeros (also when it has negative values), and a notice at `plan` "
        "when the agent asks for MAPE on a target with zeros, saying the "
        "value is not meaningful; never a bare 3e13 next to a notice that "
        "says to multiply it by 100."
    )
    return mape_a > 1e6 and mape_b > 1e6 and not notice_a and not notice_b


if __name__ == "__main__":
    ok = run(main, allow_dir=DATA)
    print("REPRODUCED" if ok else "NOT REPRODUCED")
    sys.exit(0 if ok else 1)
