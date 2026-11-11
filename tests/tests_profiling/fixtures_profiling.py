"""Fixtures for profiling tests."""

import numpy as np
import pandas as pd

# --- Single series, daily, 365 observations ---
df_single_daily = pd.DataFrame(
    {"y": np.arange(365, dtype=float)},
    index=pd.date_range("2023-01-01", periods=365, freq="D"),
)

# --- Single series, hourly, 720 observations with exog ---
_hourly_index = pd.date_range("2023-01-01", periods=720, freq="h")
df_single_hourly_exog = pd.DataFrame(
    {
        "sales": np.arange(720, dtype=float),
        "temperature": np.tile(np.linspace(5.0, 35.0, 24), 30),
        "promo_budget": np.arange(720, dtype=float) * 0.5,
        "holiday": (["no"] * 700 + ["yes"] * 20),
    },
    index=_hourly_index,
)

# --- Multi-series, long format, 3 series ---
_multi_dates = pd.date_range("2023-01-01", periods=100, freq="D")
df_multi_long = pd.DataFrame(
    {
        "date": np.tile(_multi_dates, 3),
        "series_id": np.repeat(["A", "B", "C"], 100),
        "value": np.arange(300, dtype=float),
        "exog_1": np.arange(300, dtype=float) * 0.1,
    }
)

# --- Single series with missing values ---
_missing_values = np.arange(100, dtype=float)
_missing_values[10] = np.nan
_missing_values[20] = np.nan
_missing_values[30] = np.nan
_exog_missing = np.arange(100, dtype=float) * 2
_exog_missing[5] = np.nan
_exog_missing[15] = np.nan
df_with_missing = pd.DataFrame(
    {"target": _missing_values, "exog": _exog_missing},
    index=pd.date_range("2023-01-01", periods=100, freq="D"),
)

# --- RangeIndex, no datetime ---
df_range_index = pd.DataFrame(
    {"value": np.arange(100, dtype=float)},
)

# --- Short series, 20 observations ---
df_short = pd.DataFrame(
    {"y": np.arange(20, dtype=float)},
    index=pd.date_range("2023-01-01", periods=20, freq="D"),
)

# --- Duplicate timestamps ---
# The first 5 dates appear twice. In the `*_duplicate_values` frames the
# repeated rows hold other values, which profiling rejects; in the
# `*_identical_duplicates` frames they are copies, which are dropped. One
# copied row has a missing exog value: two NaN count as identical.
_dup_dates = pd.date_range("2023-01-01", periods=50, freq="D")
df_single_duplicate_values = pd.DataFrame(
    {"y": np.arange(55, dtype=float)},
    index=_dup_dates.append(_dup_dates[:5]),
)
_single_no_dup = pd.DataFrame(
    {
        "y": np.arange(50, dtype=float),
        "exog": np.arange(50, dtype=float) * 2,
    },
    index=_dup_dates,
)
_single_no_dup.iloc[2, 1] = np.nan
df_single_identical_duplicates = pd.concat(
    [_single_no_dup, _single_no_dup.iloc[:5]]
)
df_wide_duplicate_values = pd.DataFrame(
    {
        "a": np.arange(55, dtype=float),
        "b": np.arange(55, dtype=float) * 2,
    },
    index=_dup_dates.append(_dup_dates[:5]),
)
_wide_no_dup = df_wide_duplicate_values.iloc[:50]
df_wide_identical_duplicates = pd.concat([_wide_no_dup, _wide_no_dup.iloc[:5]])

# Series B of `df_multi_long` repeats 2023-01-11 (row 110) with another
# value, or as an identical copy.
df_long_duplicate_values_series_b = pd.concat(
    [df_multi_long, df_multi_long.iloc[[110]].assign(value=-1.0)],
    ignore_index=True,
)
df_long_identical_duplicates_series_b = pd.concat(
    [df_multi_long, df_multi_long.iloc[[110]]],
    ignore_index=True,
)
df_multiindex_identical_duplicates_series_b = (
    df_long_identical_duplicates_series_b.set_index(["series_id", "date"])
)

# Wide data whose series 'b' ends 2 dates and 'c' 1 date before the last date
# with a value (2023-01-04); 'c' has a missing value in between.
df_wide_ending_early = pd.DataFrame(
    {
        "a": [1.0, 2.0, 3.0, 4.0],
        "b": [1.0, 2.0, np.nan, np.nan],
        "c": [1.0, np.nan, 3.0, np.nan],
    },
    index=pd.date_range("2023-01-01", periods=4, freq="D"),
)


# --- Dates written with the day and the month as numbers before the year ---
# Closed formulas, so no random seed is involved.

# Daily series of 90 observations from 2020-01-01 written day first
# ('01/01/2020'): the days after the 12th settle the order. The values go
# from 10.0 to 54.5 (mean 32.25).
df_dates_day_first = pd.DataFrame(
    {
        "date": pd.date_range("2020-01-01", periods=90, freq="D").strftime(
            "%d/%m/%Y"
        ),
        "y": 10.0 + 0.5 * np.arange(90),
    }
)

# The same series with ISO dates ('2020-01-01').
df_dates_iso = df_dates_day_first.assign(
    date=pd.date_range("2020-01-01", periods=90, freq="D").strftime("%Y-%m-%d")
)

# The same series with dates written as whole numbers ('20200101').
df_dates_compact = df_dates_day_first.assign(
    date=pd.date_range("2020-01-01", periods=90, freq="D")
    .strftime("%Y%m%d")
    .astype(int)
)

# Monthly series of 60 observations from 2015-01-01 written day first
# ('01/02/2015'), as a Spanish file writes them: no day is after the 12th, so
# every date reads day first and month first, and only the reading day first
# has a regular frequency ('MS'). The values go from 5.0 to 93.5.
df_dates_monthly_ambiguous = pd.DataFrame(
    {
        "date": pd.date_range("2015-01-01", periods=60, freq="MS").strftime(
            "%d/%m/%Y"
        ),
        "y": 5.0 + 1.5 * np.arange(60),
    }
)

# The same series written month first ('02/01/2015'), as a US file writes
# them: only the reading month first has a regular frequency ('MS').
df_dates_monthly_us = df_dates_monthly_ambiguous.assign(
    date=pd.date_range("2015-01-01", periods=60, freq="MS").strftime("%m/%d/%Y")
)

# Three monthly observations from 2020-01-01 written day first ('01/02/2020'):
# both readings have a regular frequency ('MS' day first, 'D' month first),
# so the dates do not tell the order.
df_dates_three_ambiguous = pd.DataFrame(
    {
        "date": ["01/01/2020", "01/02/2020", "01/03/2020"],
        "y": [1.0, 2.0, 4.0],
    }
)

# Daily series of 60 observations from 2020-01-13 written month first
# ('01/13/2020'): the days after the 12th settle the order.
df_dates_month_first = pd.DataFrame(
    {
        "date": pd.date_range("2020-01-13", periods=60, freq="D").strftime(
            "%m/%d/%Y"
        ),
        "y": 5.0 + 1.5 * np.arange(60),
    }
)

# Daily series of 60 observations as a spreadsheet of Germany exports it
# (columns 'datum' and 'umsatz'): dates with points ('15.01.2020') and
# amounts with '.' between thousands and ',' before two decimals
# (`write_german_excel`). The amounts go from 1234.56 to 7149.31 (mean
# 4191.935), the dates from 2020-01-15 and from 2020-01-01.
_german_amounts = np.round(1234.56 + 100.25 * np.arange(60), 2)
df_german_from_15th = pd.DataFrame(
    {
        "datum": pd.date_range("2020-01-15", periods=60, freq="D").strftime(
            "%d.%m.%Y"
        ),
        "umsatz": _german_amounts,
    }
)
df_german_from_1st = df_german_from_15th.assign(
    datum=pd.date_range("2020-01-01", periods=60, freq="D").strftime("%d.%m.%Y")
)

# Monthly series of 60 amounts above 1,000 in the format of a German
# spreadsheet, from 2015-01-01 ('01.02.2015'): no day is after the 12th.
df_german_monthly = pd.DataFrame(
    {
        "datum": pd.date_range("2015-01-01", periods=60, freq="MS").strftime(
            "%d.%m.%Y"
        ),
        "umsatz": np.round(1000.5 + 50.25 * np.arange(60), 2),
    }
)


def write_german_excel(directory, frame: pd.DataFrame, name: str = "de.csv") -> str:
    """
    Write `frame` (columns 'datum' and 'umsatz') to `directory` separated by
    ';', with '.' between the thousands and ',' before the decimals of the
    amounts ('1.234,56'), as a German spreadsheet exports it, and return the
    path. pandas cannot write a thousands separator.
    """

    def written(value: float) -> str:
        return f"{value:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")

    lines = ["datum;umsatz"] + [
        f"{date};{written(value)}"
        for date, value in zip(frame["datum"], frame["umsatz"])
    ]
    path = directory / name
    path.write_text("\n".join(lines) + "\n")

    return str(path)


# Exogenous columns of text, 30 daily rows: 'pct' holds percentages ('0%'),
# 'dash' numbers with a '-' every 10 rows, 'mixed' plain numbers, ' 7 %' with
# spaces, '-' and a blank cell; 'store' and 'code' are true categories
# ('A', 'B' and product codes 'P-001', '007'), 'few' has 3 numbers in 30
# values (below the share of 90 %) and 'x_na' is numeric with 2 missing
# values.
_dirty_n = 30
_dash = [f"{i}.5" for i in range(_dirty_n)]
_dash[::10] = ["-"] * 3
_mixed = [str(i) for i in range(_dirty_n)]
_mixed[1:4] = ["7%", " 7 %", "-"]
_mixed[5] = " "
_x_na = np.arange(_dirty_n, dtype=float)
_x_na[[4, 9]] = np.nan
df_dirty_exog = pd.DataFrame(
    {
        "y": np.arange(_dirty_n, dtype=float) % 7,
        "pct": [f"{i}%" for i in range(_dirty_n)],
        "dash": _dash,
        "mixed": _mixed,
        "store": ["A", "B", "C"] * 10,
        "code": ["P-001", "P-002", "007"] * 10,
        "few": ["1", "2", "3"] + ["low", "high", "mid"] * 9,
        "x_na": _x_na,
    },
    index=pd.date_range("2023-01-01", periods=_dirty_n, freq="D"),
)
