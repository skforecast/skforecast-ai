"""Write the small datasets of axis d (limits and security) to data/.

Deterministic (fixed seed). Large or dangerous inputs are generated at run
time by the scripts that need them, never here.
"""

from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent / "data"


def monthly(n: int = 96, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    y = 100 + 0.5 * t + 10 * np.sin(2 * np.pi * t / 12) + rng.normal(0, 1, n)
    dates = pd.date_range("2015-01-01", periods=n, freq="MS")
    return pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "y": y.round(3)})


def monthly_exog(n: int = 96, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    df = monthly(n, seed)
    df["temp"] = (15 + 10 * np.sin(2 * np.pi * np.arange(n) / 12)
                  + rng.normal(0, 1, n)).round(3)
    return df


def future_exog(start: str, steps: int, seed: int = 2) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start, periods=steps, freq="MS")
    temp = 15 + rng.normal(0, 3, steps)
    return pd.DataFrame({"date": dates.strftime("%Y-%m-%d"),
                         "temp": temp.round(3)})


def long_three(n: int = 72, seed: int = 3) -> pd.DataFrame:
    """Three series stacked (long format): date, sid, y, y2."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2015-01-01", periods=n, freq="MS")
    rows = []
    for sid, base in [("a", 10.0), ("b", 50.0), ("c", 90.0)]:
        for d in dates:
            rows.append((d.strftime("%Y-%m-%d"), sid,
                         round(base + rng.normal(), 3), round(rng.normal(), 3)))
    return pd.DataFrame(rows, columns=["date", "sid", "y", "y2"])


def wide_two(n: int = 96, seed: int = 4) -> pd.DataFrame:
    """Two series side by side (wide format) and an integer column x."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2015-01-01", periods=n, freq="MS")
    return pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "y": (100 + rng.normal(0, 5, n)).round(3),
        "y2": (50 + rng.normal(0, 5, n)).round(3),
        "x": rng.integers(0, 3, n),
    })


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    monthly().to_csv(DATA / "monthly.csv", index=False)
    exog = monthly_exog()
    exog.to_csv(DATA / "monthly_exog.csv", index=False)
    future_exog("2023-01-01", 12).to_csv(DATA / "future_exog.csv", index=False)
    long_three().to_csv(DATA / "long.csv", index=False)
    wide_two().to_csv(DATA / "wide.csv", index=False)
    print("written to", DATA)


if __name__ == "__main__":
    main()
