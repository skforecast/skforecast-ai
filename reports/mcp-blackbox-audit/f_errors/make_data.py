"""Small deterministic datasets for axis f (error quality)."""

from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent / "data"


def main() -> None:
    DATA.mkdir(exist_ok=True)
    rng = np.random.default_rng(0)
    n = 120
    t = np.arange(n)
    dates = pd.date_range("2015-01-01", periods=n, freq="MS")
    y = 100 + 0.5 * t + 10 * np.sin(t * 2 * np.pi / 12) + rng.normal(0, 1, n)
    pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "y": y.round(3)}).to_csv(
        DATA / "monthly.csv", index=False
    )
    # monthly with one exogenous column
    x = rng.normal(0, 1, n).round(3)
    pd.DataFrame(
        {"date": dates.strftime("%Y-%m-%d"), "y": (y + 2 * x).round(3), "x": x}
    ).to_csv(DATA / "monthly_exog.csv", index=False)
    # long multi-series (3 series of 100 daily obs)
    rows = []
    d = pd.date_range("2020-01-01", periods=100, freq="D")
    for s in ["a", "b", "c"]:
        v = 50 + 5 * np.sin(np.arange(100) * 2 * np.pi / 7) + rng.normal(0, 1, 100)
        rows.append(
            pd.DataFrame({"date": d.strftime("%Y-%m-%d"), "id": s, "y": v.round(3)})
        )
    pd.concat(rows).to_csv(DATA / "long.csv", index=False)


if __name__ == "__main__":
    main()
