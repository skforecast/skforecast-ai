"""
Datasets shared by the parity and timing scripts.

The skforecast datasets are downloaded once with `fetch_dataset` and kept as
pickles in a cache directory of the user (`~/.cache/skforecast_ai_perf` by
default), so every later run reads the same values. The synthetic sets are
built from a seeded generator.
"""

from __future__ import annotations
import os
import pickle
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

# A directory of the user, not the shared temporary one: the cache is read
# with pickle, which must only load files this user wrote.
DEFAULT_DATA_DIR = Path.home() / ".cache" / "skforecast_ai_perf"


@dataclass
class Scenario:
    """
    One dataset and the arguments every call of the assistant receives.

    Attributes
    ----------
    name : str
        Name of the dataset in the outputs.
    data : pandas DataFrame, str
        What `profile()` and the execution methods receive: a frame, or the
        path of a CSV.
    steps : int
        Forecast horizon.
    target : str, list of str
        Target column, or columns of wide data.
    date_column : str, default None
        Date column, when the dates are not the index.
    series_id_column : str, default None
        Series id column of long data.
    future_exog : pandas DataFrame, default None
        Future exogenous values given to `forecast()` in prediction mode.
    notes : list of str
        What the outputs should say about the data (synthetic data).
    """

    name: str
    data: pd.DataFrame | str
    steps: int
    target: str | list[str]
    date_column: str | None = None
    series_id_column: str | None = None
    future_exog: pd.DataFrame | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def data_arguments(self) -> dict:
        """
        Keyword arguments of `profile()` that name the columns.
        """
        arguments = {"target": self.target}
        if self.date_column is not None:
            arguments["date_column"] = self.date_column
        if self.series_id_column is not None:
            arguments["series_id_column"] = self.series_id_column
        return arguments

    @property
    def n_rows(self) -> int:
        """
        Number of rows of the data.
        """
        if isinstance(self.data, str):
            with open(self.data) as file:
                return sum(1 for _ in file) - 1
        return len(self.data)


def _fetch(name: str, data_dir: Path) -> pd.DataFrame:
    """
    Read a skforecast dataset from the cache, downloading it the first time.
    The pickle is written to a temporary file and renamed, so an interrupted
    run leaves no truncated cache.
    """

    path = data_dir / f"{name}.pkl"
    if path.exists():
        with open(path, "rb") as file:
            return pickle.load(file)
    from skforecast.datasets import fetch_dataset

    frame = fetch_dataset(name=name, verbose=False)
    data_dir.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=data_dir, suffix=".tmp")
    with os.fdopen(handle, "wb") as file:
        pickle.dump(frame, file)
    os.replace(temporary, path)
    return frame


def _synthetic_store_sales() -> pd.DataFrame:
    """
    Data with the shape of `store_sales`: 10 stores and 50 items with daily
    sales from 2013-01-01 to 2017-12-31 (913000 rows), date as index.
    """

    rng = np.random.default_rng(123)
    dates = pd.date_range("2013-01-01", "2017-12-31", freq="D")
    frames = []
    for store in range(1, 11):
        for item in range(1, 51):
            level = rng.uniform(10, 60)
            weekly = 1 + 0.2 * np.sin(2 * np.pi * dates.dayofweek / 7)
            sales = rng.poisson(level * weekly)
            frames.append(
                pd.DataFrame(
                    {"store": store, "item": item, "sales": sales}, index=dates
                )
            )
    frame = pd.concat(frames)
    frame.index.name = "date"
    return frame


def _madrid_hourly() -> pd.DataFrame:
    """
    Hourly series in Europe/Madrid from 2023-03-01 to 2023-04-14, across the
    spring change of time (no 02:00 on 2023-03-26).
    """

    rng = np.random.default_rng(7)
    index = pd.date_range(
        "2023-03-01 00:00", "2023-04-14 23:00", freq="h", tz="Europe/Madrid"
    )
    hour = index.hour.to_numpy()
    values = (
        50 + 10 * np.sin(2 * np.pi * hour / 24)
        + np.arange(len(index)) * 0.01
        + rng.normal(0, 1, len(index))
    )
    return pd.DataFrame({"date": index, "load": values})


def _bike_sharing(data_dir: Path) -> pd.DataFrame:
    """
    bike_sharing with the target `users` and six exogenous columns, on its
    hourly grid (17544 rows).
    """

    bike = _fetch("bike_sharing", data_dir)
    columns = ["users", "holiday", "workingday", "weather", "temp", "hum", "windspeed"]
    return bike[columns].asfreq("h")


def _small(data_dir: Path) -> Scenario:
    h2o = _fetch("h2o", data_dir)
    return Scenario(name="h2o", data=h2o.rename_axis("fecha"), steps=12, target="x")


def _medium(data_dir: Path) -> Scenario:
    bike = _bike_sharing(data_dir)
    # The last day is the future: 17520 rows of history.
    return Scenario(
        name        = "bike_sharing",
        data        = bike.iloc[:-24],
        steps       = 24,
        target      = "users",
        future_exog = bike.drop(columns="users").iloc[-24:],
    )


def _large(data_dir: Path) -> Scenario:
    notes = []
    try:
        sales = _fetch("store_sales", data_dir)
    except Exception as exc:  # noqa: BLE001 - any download failure
        sales = _synthetic_store_sales()
        notes.append(f"store_sales download failed ({exc!r}): synthetic data")
    sales = sales.reset_index()
    sales = pd.DataFrame({
        "date": sales["date"],
        "series": (
            "s" + sales["store"].astype(str) + "_i" + sales["item"].astype(str)
        ),
        "sales": sales["sales"].astype(float),
    })
    return Scenario(
        name             = "store_sales",
        data             = sales,
        steps            = 7,
        target           = "sales",
        date_column      = "date",
        series_id_column = "series",
        notes            = notes,
    )


# The three sizes of the timing script, built only when asked for: small is
# h2o (204 rows), medium bike_sharing (17520 hourly rows with exogenous
# variables) and large store_sales (913000 rows in long format, 500 series).
SIZES: dict[str, Callable[[Path], Scenario]] = {
    "small": _small,
    "medium": _medium,
    "large": _large,
}


def parity_scenarios(data_dir: Path = DEFAULT_DATA_DIR) -> list[Scenario]:
    """
    The datasets of the parity script. The CSV is written to `data_dir`,
    whose path appears in the profile and the scripts, so two runs to be
    compared use the same directory.

    Parameters
    ----------
    data_dir : Path, default DEFAULT_DATA_DIR
        Cache directory of the datasets and of the CSV.

    Returns
    -------
    scenarios : list of Scenario
        Eight datasets, in the order they run.
    """

    data_dir.mkdir(parents=True, exist_ok=True)
    scenarios = []

    h2o = _fetch("h2o", data_dir).rename_axis("fecha")
    csv_path = data_dir / "h2o.csv"
    h2o.to_csv(csv_path)
    scenarios.append(Scenario("h2o_csv", str(csv_path), 12, "x"))
    scenarios.append(Scenario("h2o_dataframe", h2o, 12, "x"))

    h2o_exog = _fetch("h2o_exog", data_dir).rename_axis("fecha").asfreq("MS")
    scenarios.append(Scenario(
        "h2o_exog",
        h2o_exog.iloc[:-12],
        12,
        "y",
        future_exog=h2o_exog[["exog_1", "exog_2"]].iloc[-12:],
    ))

    # The last 120 days keep compare() within a few seconds.
    bike = _bike_sharing(data_dir).iloc[-24 * 120:]
    scenarios.append(Scenario(
        "bike_sharing_future_exog",
        bike.iloc[:-24],
        24,
        "users",
        future_exog=bike.drop(columns="users").iloc[-24:],
    ))

    items = _fetch("items_sales", data_dir).rename_axis("date")
    scenarios.append(
        Scenario("items_sales_wide", items, 7, ["item_1", "item_2", "item_3"])
    )
    long = (
        items.reset_index()
        .melt(id_vars="date", var_name="series", value_name="sales")
    )
    scenarios.append(Scenario(
        "items_sales_long", long, 7, "sales",
        date_column="date", series_id_column="series",
    ))

    starts = {"item_1": "2012-01-01", "item_2": "2012-03-01", "item_3": "2012-06-15"}
    staggered = long[long["date"] >= long["series"].map(starts)]
    scenarios.append(Scenario(
        "long_staggered_starts", staggered.reset_index(drop=True), 7, "sales",
        date_column="date", series_id_column="series",
    ))

    scenarios.append(Scenario(
        "hourly_madrid_dst", _madrid_hourly(), 24, "load", date_column="date",
    ))
    return scenarios
