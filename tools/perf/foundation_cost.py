"""
Time of a backtest of a foundation model by number of inference windows
(series times folds), to set the threshold of its `LongTrainingWarning`
(point 2 of phase 7 in dev/mcp-preparation.md).

A foundation model is never trained: its cost is the load of the weights,
once per backtest, and one inference per series and fold. The script runs
`ForecastingAssistant.backtest()` with `ForecasterFoundation` on daily
series of `store_sales` (horizon 7, the default model unless `--model`),
for several numbers of series and folds, and fits `seconds = fixed +
per_window * windows` by least squares. It needs the backend of the model
(`chronos-forecasting` for Chronos-2) and downloads its weights the first
time.

Usage (from the repository root):

    python tools/perf/foundation_cost.py results.json
    python tools/perf/foundation_cost.py results.json --model amazon/chronos-2
    python tools/perf/foundation_cost.py results.json --grid 1x1,500x10
"""

from __future__ import annotations
import argparse
import json
import platform
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _datasets import DEFAULT_DATA_DIR, _fetch  # noqa: E402

STEPS = 7
# Series x folds: one window, then growing numbers of windows.
DEFAULT_GRID = "1x1,1x10,1x50,10x10,50x10,100x10,100x50,500x10"


def _long_sales(data_dir: Path, n_series: int) -> pd.DataFrame:
    """
    The first `n_series` series of store_sales in long format.
    """

    sales = _fetch("store_sales", data_dir).reset_index()
    series = "s" + sales["store"].astype(str) + "_i" + sales["item"].astype(str)
    keep = series.isin(series.drop_duplicates().iloc[:n_series])
    return pd.DataFrame({
        "date": sales.loc[keep, "date"],
        "series": series[keep],
        "sales": sales.loc[keep, "sales"].astype(float),
    }).reset_index(drop=True)


def _backtest(data: pd.DataFrame, n_folds: int, model: str | None) -> dict:
    """
    Backtest of the last `n_folds` folds of `STEPS` days, with a fresh
    assistant (the weights are loaded again).
    """

    from skforecast.model_selection import TimeSeriesFold

    from skforecast_ai import ForecastingAssistant

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assistant = ForecastingAssistant()
        arguments = {"target": "sales", "date_column": "date"}
        if data["series"].nunique() > 1:
            arguments["series_id_column"] = "series"
        else:
            data = data.drop(columns="series")
        profile = assistant.profile(data, **arguments)
        plan = assistant.plan(
            profile    = profile,
            steps      = STEPS,
            forecaster = "ForecasterFoundation",
            estimator  = model,
        )
        n_dates = profile.data_profile.span_index_length
        cv = TimeSeriesFold(
            steps=STEPS, initial_train_size=n_dates - n_folds * STEPS
        )
        start = time.perf_counter()
        result = assistant.backtest(
            data, cv=cv, profile=profile, plan=plan, show_progress=False
        )
        seconds = time.perf_counter() - start
    return {
        "model": plan.estimator,
        "n_series": int(profile.data_profile.n_series),
        "n_folds": int(result.cv_config["n_folds"]),
        "seconds": round(seconds, 2),
    }


def main() -> int:
    """
    Command line entry point.
    """
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("output", type=Path)
    parser.add_argument("--model", default=None, help="Default: the plan's model.")
    parser.add_argument("--grid", default=DEFAULT_GRID, help="Series x folds.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    arguments = parser.parse_args()

    import torch

    runs = []
    for cell in arguments.grid.split(","):
        n_series, n_folds = (int(v) for v in cell.split("x"))
        run = _backtest(_long_sales(arguments.data_dir, n_series), n_folds, arguments.model)
        run["windows"] = run["n_series"] * run["n_folds"]
        runs.append(run)
        print(run, flush=True)

    windows = np.array([run["windows"] for run in runs], dtype=float)
    seconds = np.array([run["seconds"] for run in runs])
    per_window, fixed = np.polyfit(windows, seconds, 1)
    summary = {
        "machine": {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "torch": torch.__version__,
            "threads": torch.get_num_threads(),
            "cuda": torch.cuda.is_available(),
        },
        "runs": runs,
        "fixed_seconds": round(float(fixed), 2),
        "seconds_per_window": round(float(per_window), 5),
        "windows_per_minute": int((60 - fixed) / per_window) if per_window > 0 else None,
    }
    arguments.output.write_text(json.dumps(summary, indent=1))
    print(json.dumps({k: v for k, v in summary.items() if k != "runs"}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
