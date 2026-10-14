"""Write the small datasets of axis c (notices and cost) to c_notices/data/."""

from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent / "data"


def seasonal(n, period, seed, level=100.0, trend=0.3, noise=1.0):
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    return (
        level
        + trend * t
        + 10 * np.sin(2 * np.pi * t / period)
        + rng.normal(0, noise, n)
    )


def main():
    DATA.mkdir(parents=True, exist_ok=True)

    # Monthly single series, no exogenous, strictly positive.
    n = 120
    dates = pd.date_range("2010-01-01", periods=n, freq="MS")
    pd.DataFrame(
        {"date": dates.strftime("%Y-%m-%d"), "y": seasonal(n, 12, 0).round(3)}
    ).to_csv(DATA / "monthly.csv", index=False)

    # Daily with one exogenous column.
    n = 200
    dates = pd.date_range("2020-01-01", periods=n, freq="D")
    rng = np.random.default_rng(1)
    x = rng.normal(0, 1, n)
    y = seasonal(n, 7, 2) + 3 * x
    pd.DataFrame(
        {"date": dates.strftime("%Y-%m-%d"), "y": y.round(3), "x": x.round(3)}
    ).to_csv(DATA / "daily_exog.csv", index=False)

    # Target with exact zeros (MAPE undefined).
    n = 120
    dates = pd.date_range("2010-01-01", periods=n, freq="MS")
    y = np.clip(seasonal(n, 12, 3, level=5, trend=0.0, noise=3.0), 0, None)
    y[::7] = 0.0
    pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "y": y.round(3)}).to_csv(
        DATA / "zeros.csv", index=False
    )

    # Target with values near zero but no exact zero.
    y = np.abs(seasonal(n, 12, 4, level=20, trend=0.0, noise=1.0))
    y[::9] = 0.001
    pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "y": y.round(4)}).to_csv(
        DATA / "near_zero.csv", index=False
    )

    # Missing dates (rows removed) and missing target values.
    y = seasonal(n, 12, 5)
    df = pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "y": y.round(3)})
    df.loc[[30, 31], "y"] = np.nan
    df = df.drop(index=[60, 61, 62]).reset_index(drop=True)
    df.to_csv(DATA / "gaps.csv", index=False)

    # Only missing target values (no missing dates).
    df = pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "y": y.round(3)})
    df.loc[[40, 41, 90], "y"] = np.nan
    df.to_csv(DATA / "nan_target.csv", index=False)

    # Only missing dates.
    df = pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "y": y.round(3)})
    df = df.drop(index=[50, 51]).reset_index(drop=True)
    df.to_csv(DATA / "missing_dates.csv", index=False)

    # Short series.
    n = 30
    d30 = pd.date_range("2020-01-01", periods=n, freq="MS")
    pd.DataFrame(
        {"date": d30.strftime("%Y-%m-%d"), "y": seasonal(n, 12, 6).round(3)}
    ).to_csv(DATA / "short.csv", index=False)

    # Long multi-series: 30 series, each with missing dates (many notices?).
    rows = []
    d = pd.date_range("2020-01-01", periods=60, freq="MS")
    for k in range(30):
        vals = seasonal(60, 12, 100 + k)
        keep = np.ones(60, bool)
        keep[[10 + (k % 20), 11 + (k % 20)]] = False
        vals[40] = np.nan
        for i in np.where(keep)[0]:
            rows.append((d[i].strftime("%Y-%m-%d"), f"s{k:02d}", round(vals[i], 3)))
    pd.DataFrame(rows, columns=["date", "sid", "y"]).to_csv(
        DATA / "multi_gaps.csv", index=False
    )

    # Long multi-series, clean: 3 series of 120 monthly values.
    rows = []
    d = pd.date_range("2010-01-01", periods=120, freq="MS")
    for k in range(3):
        vals = seasonal(120, 12, 200 + k, level=50 + 10 * k)
        for i in range(120):
            rows.append((d[i].strftime("%Y-%m-%d"), f"s{k}", round(vals[i], 3)))
    pd.DataFrame(rows, columns=["date", "sid", "y"]).to_csv(
        DATA / "multi.csv", index=False
    )


if __name__ == "__main__":
    main()
