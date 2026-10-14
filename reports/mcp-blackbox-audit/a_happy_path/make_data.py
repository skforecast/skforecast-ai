"""Write the small synthetic datasets of axis a (happy path) to data/.

Deterministic (fixed seeds). Run from the repository root:

    python reports/mcp-blackbox-audit/a_happy_path/make_data.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent / "data"


def monthly(n=120, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    y = 100 + 0.5 * t + 10 * np.sin(2 * np.pi * t / 12) + rng.normal(0, 1, n)
    return pd.DataFrame(
        {
            "date": pd.date_range("2015-01-01", periods=n, freq="MS").strftime(
                "%Y-%m-%d"
            ),
            "sales": y.round(3),
        }
    )


def multiseries(n=96, seed=1):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2016-01-01", periods=n, freq="MS")
    t = np.arange(n)
    wide = pd.DataFrame({"date": dates.strftime("%Y-%m-%d")})
    for i, name in enumerate(["store_a", "store_b", "store_c"]):
        level = 50 * (i + 1)
        wide[name] = (
            level
            + 0.3 * t
            + 8 * np.sin(2 * np.pi * (t + i) / 12)
            + rng.normal(0, 1.5, n)
        ).round(3)
    long = wide.melt(id_vars="date", var_name="store", value_name="sales")
    return wide, long


def with_exog(n=150, h=12, seed=2):
    rng = np.random.default_rng(seed)
    total = n + h
    t = np.arange(total)
    dates = pd.date_range("2020-01-06", periods=total, freq="W-MON")
    temp = 15 + 10 * np.sin(2 * np.pi * t / 52) + rng.normal(0, 1, total)
    promo = (rng.random(total) < 0.2).astype(int)
    y = 200 + 3 * temp + 25 * promo + rng.normal(0, 3, total)
    df = pd.DataFrame(
        {
            "date": dates.strftime("%Y-%m-%d"),
            "demand": y.round(3),
            "temperature": temp.round(3),
            "promo": promo,
        }
    )
    hist = df.iloc[:n].reset_index(drop=True)
    future = df.iloc[n:][["date", "temperature", "promo"]].reset_index(drop=True)
    return hist, future


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    monthly().to_csv(DATA / "monthly.csv", index=False)
    wide, long = multiseries()
    wide.to_csv(DATA / "multi_wide.csv", index=False)
    long.to_csv(DATA / "multi_long.csv", index=False)
    hist, future = with_exog()
    hist.to_csv(DATA / "exog_hist.csv", index=False)
    future.to_csv(DATA / "exog_future.csv", index=False)
    for p in sorted(DATA.iterdir()):
        print(p.name, p.stat().st_size)


if __name__ == "__main__":
    main()
