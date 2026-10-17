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

# The same series with an exogenous variable, and its values for the three
# months after the last one, dates as text day first. Every date of both is
# the first of a month, so it reads day first and month first.
df_dialect_monthly_exog = df_dialect_monthly.assign(promo=np.tile([0.0, 1.0], 24))
df_dialect_monthly_exog_future = pd.DataFrame(
    {
        "date": ["01/01/2022", "01/02/2022", "01/03/2022"],
        "promo": [0.0, 1.0, 0.0],
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


# Long data of three monthly series of amounts between about 600 and 2,300,
# written by `write_thousands` with '.' between thousands, whose series ids
# are numbers ('001', '1', '10', which read as integers would lose the
# zeros and join '001' and '1').
df_dialect_thousands_long = pd.concat(
    [
        df_dialect_thousands.assign(store="001"),
        df_dialect_thousands.assign(store="1", y=df_dialect_thousands["y"] + 250),
        df_dialect_thousands.assign(store="10", y=df_dialect_thousands["y"] - 270),
    ],
    ignore_index=True,
)


def write_thousands(
    directory,
    frame: pd.DataFrame,
    decimals: bool = True,
    name: str = "thousands.csv",
    series_id_column: str | None = None,
) -> str:
    """
    Write the columns 'date' and 'y' of `frame` to `directory` separated by
    ';', with '.' between thousands and ',' before two decimals
    ('1.020,50'), or as whole numbers ('1.020') when `decimals` is False,
    as a spreadsheet of most of Europe exports them, and return the path.
    pandas cannot write a thousands separator. With `series_id_column`,
    that column of `frame` is written first, as it is.
    """

    def written(value: float) -> str:
        text = f"{value:,.2f}" if decimals else f"{round(value):,}"
        return text.replace(",", " ").replace(".", ",").replace(" ", ".")

    lines = ["date;y"] + [
        f"{date};{written(value)}" for date, value in zip(frame["date"], frame["y"])
    ]
    if series_id_column is not None:
        lines = [f"{series_id_column};{lines[0]}"] + [
            f"{series_id};{line}"
            for series_id, line in zip(frame[series_id_column], lines[1:])
        ]
    path = directory / name
    path.write_text("\n".join(lines) + "\n")

    return str(path)


# The series of `df_dialect` as the "CSV" that Excel saves on Windows with
# Spanish settings: written by `write_cp1252` in cp1252 (not UTF-8), with
# ';' as separator, ',' as decimal mark, dates day first and '\r\n' at the
# end of every line, an 'ñ' in the header ('año') and accents in the
# categories of 'zona'. Days after the 12th say the dates are day first.
df_dialect_cp1252 = pd.DataFrame(
    {
        "fecha": pd.to_datetime(df_dialect["date"]).dt.strftime("%d/%m/%Y"),
        "año": df_dialect["y"],
        "zona": np.where(np.arange(_n_obs) % 2 == 0, "Cádiz", "Peñíscola"),
    }
)

# Future values of 'zona' for the ten days after the last date of
# `df_dialect_cp1252`, written the same way: their days, up to the 11th,
# read in both orders, which the format of the data settles.
df_dialect_cp1252_exog = pd.DataFrame(
    {
        "fecha": pd.to_datetime(df_dialect_exog["date"]).dt.strftime("%d/%m/%Y"),
        "zona": np.where(np.arange(10) % 2 == 0, "Cádiz", "Peñíscola"),
    }
)


def write_cp1252(
    directory,
    frame: pd.DataFrame = df_dialect_cp1252,
    name: str = "excel.csv",
    sep: str = ";",
    decimal: str = ",",
) -> str:
    """
    Write `frame` to `directory` as Excel saves a CSV file on Windows: in
    cp1252, with `sep`, `decimal` and '\r\n' at the end of every line,
    compressed when `name` ends with '.gz'; return the path.
    """

    path = directory / name
    frame.to_csv(
        path,
        index          = False,
        sep            = sep,
        decimal        = decimal,
        encoding       = "cp1252",
        lineterminator = "\r\n",
    )

    return str(path)


# Data and future values as the Excel in Spanish saves them (see
# `write_excel_es`): dates day first, prices with '.' between thousands and
# ',' as decimal mark, and accents in the names and the categories. The ten
# future dates, up to the 11th, read in both orders, which the format of
# the data settles.
_steps = np.arange(_n_obs + 10)
_precio = np.round(870 + 15 * _steps + 40 * np.sin(_steps), 2)
df_dialect_excel = pd.DataFrame(
    {
        "fecha": pd.to_datetime(df_dialect["date"]).dt.strftime("%d/%m/%Y"),
        "año": np.round(1000 + 2.5 * _precio[:_n_obs], 2),
        "precio": _precio[:_n_obs],
        "zona": np.where(np.arange(_n_obs) % 2 == 0, "Cádiz", "Peñíscola"),
    }
)
df_dialect_excel_exog = pd.DataFrame(
    {
        "fecha": pd.to_datetime(df_dialect_exog["date"]).dt.strftime("%d/%m/%Y"),
        "precio": _precio[_n_obs:],
        "zona": np.where(np.arange(10) % 2 == 0, "Cádiz", "Peñíscola"),
    }
)


def write_excel_es(
    directory,
    frame: pd.DataFrame,
    name: str,
    blank_rows: int = 0,
) -> str:
    """
    Write `frame` to `directory` as Excel saves a CSV file on Windows in
    Spanish: in cp1252, with ';', ',' as decimal mark, '.' between
    thousands, '\r\n' at the end of every line and, with `blank_rows`, that
    many rows made only of separators at the end (cells that were
    formatted); return the path.
    """

    def cell(value: object) -> str:
        if isinstance(value, float):
            text = f"{value:,.2f}"
            return text.replace(",", "_").replace(".", ",").replace("_", ".")
        return str(value)

    lines = [";".join(frame.columns)]
    lines += [
        ";".join(cell(value) for value in row)
        for row in frame.itertuples(index=False)
    ]
    lines += [";" * (frame.shape[1] - 1)] * blank_rows
    path = directory / name
    path.write_bytes(("\r\n".join(lines) + "\r\n").encode("cp1252"))

    return str(path)
