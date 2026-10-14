"""Write the small datasets of axis b (hard data) to b_hard_data/data/.

Deterministic (fixed seeds); every file is well under 200 KB. Run from the
repository root: python reports/mcp-blackbox-audit/b_hard_data/make_data.py
"""

import gzip
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent / "data"


def monthly(n=72, seed=0, start="2015-01-01"):
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start, periods=n, freq="MS")
    t = np.arange(n)
    y = 1000 + 5 * t + 200 * np.sin(2 * np.pi * t / 12) + rng.normal(0, 20, n)
    return dates, y.round(2)


def daily(n=120, seed=1, start="2020-01-01", freq="D"):
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start, periods=n, freq=freq)
    t = np.arange(n)
    y = 50 + 10 * np.sin(2 * np.pi * t / 7) + rng.normal(0, 2, n)
    return dates, y.round(3)


def write_text(name, text, encoding="utf-8"):
    (DATA / name).write_text(text, encoding=encoding)


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    dates, y = monthly()
    iso = dates.strftime("%Y-%m-%d")
    base = pd.DataFrame({"date": iso, "y": y})

    # Formats and compression
    base.to_csv(DATA / "base.csv", index=False)
    base.to_csv(DATA / "base.tsv", index=False, sep="\t")
    with gzip.open(DATA / "base.csv.gz", "wt") as f:
        base.to_csv(f, index=False)
    with gzip.open(DATA / "base.tsv.gz", "wt") as f:
        base.to_csv(f, index=False, sep="\t")

    # European: ';' separator and ',' decimal mark
    base.to_csv(DATA / "semi_comma.csv", index=False, sep=";", decimal=",")

    # Thousands separators
    big = (y * 10).round(1)
    lines = ["date,y"] + [f'{d},"{v:,.1f}"' for d, v in zip(iso, big)]
    write_text("thousands_quoted.csv", "\n".join(lines) + "\n")
    eu = [f"{v:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
          for v in big]
    lines = ["date;y"] + [f"{d};{v}" for d, v in zip(iso, eu)]
    write_text("thousands_eu.csv", "\n".join(lines) + "\n")
    # Integers with '.' as thousands separator only (no decimal part)
    ints = (y * 10).round().astype(int)
    eu_int = [f"{v:,d}".replace(",", ".") for v in ints]
    lines = ["date;y"] + [f"{d};{v}" for d, v in zip(iso, eu_int)]
    write_text("thousands_dot_int.csv", "\n".join(lines) + "\n")
    # Integers with ',' as thousands separator, quoted, in a ';' file
    lines = ["date;y"] + [f'{d};"{v:,d}"' for d, v in zip(iso, ints)]
    write_text("thousands_comma_int_semi.csv", "\n".join(lines) + "\n")

    # Thousands separators on part of the values only: amounts below 1000
    # have none, so the same column mixes '987' and '1.234' (or '1,234').
    amounts = [870, 945, 987, 1020, 1234, 1499, 2050, 1800, 1100, 990, 960, 1010]
    amounts = amounts * 5
    mdates = pd.date_range("2015-01-01", periods=len(amounts), freq="MS")
    mdates = mdates.strftime("%Y-%m-%d")
    dot = [f"{v:,d}".replace(",", ".") for v in amounts]
    lines = ["date;y"] + [f"{d};{v}" for d, v in zip(mdates, dot)]
    write_text("thousands_dot_mixed.csv", "\n".join(lines) + "\n")
    lines = ["date;y"] + [f'{d};"{v:,d}"' for d, v in zip(mdates, amounts)]
    write_text("thousands_comma_mixed_semi.csv", "\n".join(lines) + "\n")

    # ';' separator with '.' decimals (no ',' anywhere in the numbers)
    base.to_csv(DATA / "semi_dot.csv", index=False, sep=";")

    # Gaps and missing values
    gaps = base.drop(index=[10, 11, 30]).reset_index(drop=True)
    gaps.to_csv(DATA / "gaps.csv", index=False)
    nan = base.copy()
    nan.loc[[5, 20, 21], "y"] = np.nan
    nan.to_csv(DATA / "nan_target.csv", index=False)

    # Irregular dates
    bd, yb = daily(n=120, freq="B")
    pd.DataFrame({"date": bd.strftime("%Y-%m-%d"), "y": yb}).to_csv(
        DATA / "business_days.csv", index=False
    )
    dd, yd = daily(n=150)
    keep = np.sort(np.random.default_rng(3).choice(150, 110, replace=False))
    pd.DataFrame({"date": dd[keep].strftime("%Y-%m-%d"), "y": yd[keep]}).to_csv(
        DATA / "random_gaps.csv", index=False
    )
    mixed = base.copy()
    mixed.loc[36:, "date"] = dates[36:].strftime("%d/%m/%Y")
    mixed.to_csv(DATA / "mixed_formats.csv", index=False)
    # Day first, daily: 13/01/2020 shows it is day first
    pd.DataFrame({"date": dd[:90].strftime("%d/%m/%Y"), "y": yd[:90]}).to_csv(
        DATA / "dayfirst_daily.csv", index=False
    )
    # Day first, monthly on day 1: every value is ambiguous (01/02/2015)
    pd.DataFrame({"date": dates.strftime("%d/%m/%Y"), "y": y}).to_csv(
        DATA / "dayfirst_monthly.csv", index=False
    )

    # Duplicated dates
    dup_same = pd.concat([base, base.iloc[[10, 20]]]).sort_index(kind="stable")
    dup_same.to_csv(DATA / "dup_identical.csv", index=False)
    dup_diff = dup_same.copy()
    dup_diff.iloc[11, 1] = dup_diff.iloc[11, 1] + 50
    dup_diff.to_csv(DATA / "dup_different.csv", index=False)

    # Very short series
    for n in (5, 10, 20):
        base.iloc[:n].to_csv(DATA / f"short_{n}.csv", index=False)

    # Text columns that look numeric (exogenous and target)
    ex = base.copy()
    ex["x_str"] = [str(i % 30) for i in range(len(ex))]
    ex["x_na"] = [("N/A" if i % 9 == 0 else str(i)) for i in range(len(ex))]
    ex["x_dash"] = [("-" if i % 11 == 0 else f"{i}.5") for i in range(len(ex))]
    ex["x_sci"] = [f"{i}e3" for i in range(len(ex))]
    ex["x_pct"] = [f"{i % 100}%" for i in range(len(ex))]
    ex.to_csv(DATA / "text_exog.csv", index=False)
    tgt = base.copy()
    tgt["y"] = tgt["y"].astype(object)
    tgt.loc[[7, 40], "y"] = "N/A"
    tgt.loc[[15], "y"] = "-"
    tgt.to_csv(DATA / "text_target_na.csv", index=False)
    pct = base.copy()
    pct["y"] = [f"{v / 100:.1f}%" for v in y]
    pct.to_csv(DATA / "pct_target.csv", index=False)

    # Numeric looking date columns
    pd.DataFrame({"date": dd[:90].strftime("%Y%m%d").astype(int), "y": yd[:90]}).to_csv(
        DATA / "date_yyyymmdd.csv", index=False
    )
    unix = (dd[:90].astype("int64") // 10**9).astype(int)
    pd.DataFrame({"date": unix, "y": yd[:90]}).to_csv(
        DATA / "date_unix.csv", index=False
    )

    # BOM and trailing empty lines
    write_text("bom.csv", base.to_csv(index=False), encoding="utf-8-sig")
    write_text("trailing_blank.csv", base.to_csv(index=False) + "\n\n\n")
    write_text("trailing_commas.csv", base.to_csv(index=False) + ",\n,\n")

    # Column names with spaces and accents
    acc = base.rename(columns={"date": "fecha de venta", "y": "Ventas (€) año"})
    acc["temperatura media"] = np.round(np.linspace(10, 20, len(acc)), 2)
    acc.to_csv(DATA / "accents.csv", index=False)

    # Constant target and target with zeros and negatives
    const = base.copy()
    const["y"] = 5.0
    const.to_csv(DATA / "constant.csv", index=False)
    neg = base.copy()
    neg["y"] = (np.sin(np.arange(len(neg)) * 2 * np.pi / 12) * 10).round(0)
    neg.to_csv(DATA / "neg_zero.csv", index=False)
    t = np.arange(len(base))
    sales = np.where(t % 7 == 0, 0, (50 + 20 * np.sin(2 * np.pi * t / 12)).round(0))
    pd.DataFrame({"date": iso, "y": sales}).to_csv(
        DATA / "sales_zeros.csv", index=False
    )

    print("written to", DATA)


if __name__ == "__main__":
    main()
