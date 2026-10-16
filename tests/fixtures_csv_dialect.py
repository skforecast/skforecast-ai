# Fixtures for the tests of the CSV dialects (separator, decimal mark and
# thousands separator)

import numpy as np
import pandas as pd

# Daily series of 60 observations with ISO dates and decimals, written by the
# tests with `to_csv(sep=';', decimal=',', index=False)` and the like. The
# values are a closed formula, so no random seed is involved.
_n_obs = 60
df_dialect = pd.DataFrame(
    {
        "date": pd.date_range("2023-01-01", periods=_n_obs, freq="D").strftime(
            "%Y-%m-%d"
        ),
        "y": np.round(
            10 + 0.1 * np.arange(_n_obs) + 2 * np.sin(np.arange(_n_obs) / 3), 3
        ),
    }
)

# Future values of an exogenous variable for the series of `df_dialect`
# (columns 'date' and 'temp'), ten days after its last date.
df_dialect_exog = pd.DataFrame(
    {
        "date": pd.date_range("2023-03-02", periods=10, freq="D").strftime(
            "%Y-%m-%d"
        ),
        "temp": [1.5, 2.25, 3.5, 4.75, 5.5, 6.25, 7.5, 8.75, 9.5, 10.25],
    }
)

# Monthly series of the reproduction: dates written day first, one decimal
# mark apart from the thousandths.
df_dialect_monthly = pd.DataFrame(
    {
        "date": pd.date_range("2018-01-01", periods=48, freq="MS").strftime(
            "%d/%m/%Y"
        ),
        "y": np.round(np.linspace(1, 3, 48) + np.sin(np.arange(48)), 3),
    }
)


# How each dialect is written to disk by the tests: name, file name, and the
# arguments of `DataFrame.to_csv`.
DIALECT_FILES = {
    "semicolon_comma": ("eu.csv", {"sep": ";", "decimal": ","}),
    "semicolon_dot": ("semi.csv", {"sep": ";", "decimal": "."}),
    "tab_dot": ("tab.csv", {"sep": "\t", "decimal": "."}),
    "tab_comma": ("tab_comma.csv", {"sep": "\t", "decimal": ","}),
    "tsv": ("data.tsv", {"sep": "\t", "decimal": "."}),
    "gz_comma_dot": ("data.csv.gz", {"sep": ","}),
    "gz_semicolon_comma": ("eu.csv.gz", {"sep": ";", "decimal": ","}),
}


def write_dialect(directory, frame: pd.DataFrame, name: str) -> str:
    """
    Write `frame` to `directory` as the dialect `name` of `DIALECT_FILES`
    and return the path.
    """

    file_name, arguments = DIALECT_FILES[name]
    path = directory / file_name
    frame.to_csv(path, index=False, **arguments)

    return str(path)


# Monthly series of 48 amounts between 870 and about 2,050, the shape of the
# reproduction of '.' read as a decimal mark: written by `write_thousands`
# with '.' between thousands, the amounts below 1,000 have none.
df_dialect_thousands = pd.DataFrame(
    {
        "date": pd.date_range("2018-01-01", periods=48, freq="MS").strftime(
            "%Y-%m-%d"
        ),
        "y": np.round(870 + 25 * np.arange(48) + 30 * np.sin(np.arange(48)), 2),
    }
)


def write_thousands(
    directory,
    frame: pd.DataFrame,
    decimals: bool = True,
    name: str = "thousands.csv",
) -> str:
    """
    Write the columns 'date' and 'y' of `frame` to `directory` separated by
    ';', with '.' between thousands and ',' before two decimals
    ('1.020,50'), or as whole numbers ('1.020') when `decimals` is False,
    as a spreadsheet of most of Europe exports them, and return the path.
    pandas cannot write a thousands separator.
    """

    def written(value: float) -> str:
        text = f"{value:,.2f}" if decimals else f"{round(value):,}"
        return text.replace(",", " ").replace(".", ",").replace(" ", ".")

    lines = ["date;y"] + [
        f"{date};{written(value)}" for date, value in zip(frame["date"], frame["y"])
    ]
    path = directory / name
    path.write_text("\n".join(lines) + "\n")

    return str(path)
