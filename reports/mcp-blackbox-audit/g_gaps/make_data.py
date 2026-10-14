"""Write the small synthetic datasets of the gap round (g_gaps) to data/.

Every file is generated with numpy and pandas from fixed seeds, so running it
again writes the same bytes. The wide multi-series file of the gap on
ForecasterDirectMultiVariate is a_happy_path/data/multi_wide.csv, reused as it
is.
"""

from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent / "data"


def long_series(ids, lengths, seed=5, exog=False):
    """Stacked monthly series ending on 2023-12-01, one block per id."""
    rng = np.random.default_rng(seed)
    rows = []
    end = pd.Timestamp("2023-12-01")
    for k, (sid, n) in enumerate(zip(ids, lengths)):
        dates = pd.date_range(end=end, periods=n, freq="MS")
        temp = 10 + 5 * np.sin(np.arange(n) * 2 * np.pi / 12) + rng.normal(0, 1, n)
        sales = 50 + 20 * k + 3 * temp + rng.normal(0, 2, n)
        for d, s, t in zip(dates, sales, temp):
            rows.append((sid, d.strftime("%Y-%m-%d"), round(s, 3), round(t, 3)))
    df = pd.DataFrame(rows, columns=["store", "date", "sales", "temperature"])
    return df if exog else df.drop(columns="temperature")


def main():
    DATA.mkdir(exist_ok=True)

    # g-02: store ids as the user's system writes them, zero-padded.
    long_series(["001", "002", "010"], [96, 96, 96]).to_csv(
        DATA / "stores_padded_ids.csv", index=False
    )
    # g-02 control: the same values with letters as ids.
    long_series(["S01", "S02", "S10"], [96, 96, 96]).to_csv(
        DATA / "stores_letter_ids.csv", index=False
    )

    # g-03: one store opened 20 months before the end of the data.
    long_series(["S01", "S02", "S10"], [96, 20, 96], exog=False).to_csv(
        DATA / "stores_one_short.csv", index=False
    )

    # g-04: hourly load recorded in UTC, dates written with 'Z'.
    n = 24 * 21
    rng = np.random.default_rng(3)
    idx = pd.date_range("2024-03-20", periods=n, freq="h", tz="UTC")
    load = 50 + 10 * np.sin(np.arange(n) * 2 * np.pi / 24) + rng.normal(0, 1, n)
    pd.DataFrame(
        {"date": idx.strftime("%Y-%m-%dT%H:%M:%SZ"), "load": load.round(3)}
    ).to_csv(DATA / "hourly_utc.csv", index=False)

    # g-05: a monthly series of 20 years, long enough for 10 ForecasterStats
    # folds that take about 20 s on 4 CPUs.
    n = 240
    rng = np.random.default_rng(1)
    y = (
        100
        + np.arange(n) * 0.3
        + 10 * np.sin(np.arange(n) * 2 * np.pi / 12)
        + rng.normal(0, 2, n)
    )
    pd.DataFrame(
        {
            "date": pd.date_range("2000-01-01", periods=n, freq="MS").strftime(
                "%Y-%m-%d"
            ),
            "y": y.round(3),
        }
    ).to_csv(DATA / "monthly_20y.csv", index=False)


if __name__ == "__main__":
    main()
    for path in sorted(DATA.iterdir()):
        print(path.name, path.stat().st_size)
