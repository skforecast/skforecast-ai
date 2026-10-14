"""Write the small datasets of axis e (skill and tools coherence) to data/.

Deterministic (fixed seeds). Run from the repository root:

    python reports/mcp-blackbox-audit/e_skill_coherence/make_data.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent / "data"


def monthly(n: int, seed: int, level: float = 100.0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    return (
        level
        + 0.5 * t
        + 10 * np.sin(t * 2 * np.pi / 12)
        + rng.normal(0, 1, n)
    ).round(3)


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)

    # One monthly series, 120 rows, no exogenous columns.
    n = 120
    dates = pd.date_range("2015-01-01", periods=n, freq="MS")
    pd.DataFrame(
        {"date": dates.strftime("%Y-%m-%d"), "y": monthly(n, 0)}
    ).to_csv(DATA / "single.csv", index=False)

    # One monthly series with one exogenous column, plus 12 future values.
    rng = np.random.default_rng(1)
    x = rng.normal(0, 1, n + 12).round(3)
    y = monthly(n, 2) + 3 * x[:n]
    pd.DataFrame(
        {"date": dates.strftime("%Y-%m-%d"), "y": y.round(3), "x": x[:n]}
    ).to_csv(DATA / "exog.csv", index=False)
    future = pd.date_range(dates[-1], periods=13, freq="MS")[1:]
    pd.DataFrame(
        {"date": future.strftime("%Y-%m-%d"), "x": x[n:]}
    ).to_csv(DATA / "exog_future.csv", index=False)

    # Three monthly series stacked (long format), 96 rows each.
    m = 96
    d2 = pd.date_range("2016-01-01", periods=m, freq="MS")
    frames = []
    for i, sid in enumerate(["a", "b", "c"]):
        frames.append(
            pd.DataFrame(
                {
                    "date": d2.strftime("%Y-%m-%d"),
                    "series": sid,
                    "y": monthly(m, 10 + i, level=50.0 * (i + 1)),
                }
            )
        )
    pd.concat(frames).to_csv(DATA / "multi_long.csv", index=False)


if __name__ == "__main__":
    main()
