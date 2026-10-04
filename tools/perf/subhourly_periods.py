"""
Seasonal period of data sampled every 5 to 30 minutes: the hour, as
`estimate_seasonality` puts first, or the day, as
`FREQUENCY_TO_SEASONAL_PERIOD` says (point 1b of phase 7 in
dev/mcp-preparation.md).

For each dataset and two horizons (one hour and one day), the script
backtests with the same strategy (the last 14 days, trained once):

- `lags`: the lags and window features `profile()` and `plan()` choose with
  the hour first (`estimate_seasonality`, as today) and with the day alone
  (the period of the table);
- `baseline`: `ForecasterEquivalentDate` repeating the day (as today) and
  repeating the hour;
- `arima`: Auto-ARIMA (`ForecasterStats`) with `m` the day and `m` the hour,
  on its own shorter strategy: the last 14 days of training data and the
  last 2 days as test, refitted in every fold (skforecast does it for ARIMA
  whatever `refit` says), so only with the horizon of one day (48 refits
  for the horizon of one hour did not end in 15 minutes). A backtest that takes more than `ARIMA_TIMEOUT`
  seconds is stopped and reported as such.

It reports MASE and MAE (mean over the folds, as `backtest()` gives them),
the time of the backtest and the number of predictors (lags plus window
features). The real datasets come from `skforecast.datasets` (cached by
`_datasets._fetch`); two synthetic sets cover 5 and 10 minutes, which no
skforecast dataset has.

Usage (from the repository root):

    python tools/perf/subhourly_periods.py results.json
    python tools/perf/subhourly_periods.py results.json --parts lags,baseline
    python tools/perf/subhourly_periods.py results.json --parts arima --datasets vic,ett_m2
    python tools/perf/subhourly_periods.py report results.json
"""

from __future__ import annotations
import argparse
import json
import multiprocessing
import sys
import time
import warnings
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _datasets import DEFAULT_DATA_DIR, _fetch  # noqa: E402

METRICS = ["mean_absolute_scaled_error", "mean_absolute_error"]
DAYS = 60
TEST_DAYS = 14
ARIMA_TRAIN_DAYS = 14
ARIMA_TEST_DAYS = 2
ARIMA_TIMEOUT = 600


def _synthetic(frequency: str, per_day: int, hourly: bool) -> pd.DataFrame:
    """
    `DAYS` days of a series with a daily cycle, plus an hourly one when
    `hourly`, a slow trend and seeded noise.
    """

    rng = np.random.default_rng(per_day)
    n_rows = DAYS * per_day
    index = pd.date_range("2024-01-01", periods=n_rows, freq=frequency)
    steps = np.arange(n_rows)
    values = (
        100 + 0.001 * steps
        + 10 * np.sin(2 * np.pi * steps / per_day)
        + rng.normal(0, 1, n_rows)
    )
    if hourly:
        values += 4 * np.sin(2 * np.pi * steps / (per_day // 24))
    return pd.DataFrame({"y": values}, index=index.rename("date"))


def _last_days(frame: pd.DataFrame, column: str, per_day: int) -> pd.DataFrame:
    """
    The last `DAYS` days of one column, on its regular grid.
    """
    return frame[[column]].iloc[-DAYS * per_day:].rename(columns={column: "y"})


def datasets(data_dir: Path) -> dict[str, tuple[Callable[[], pd.DataFrame], int]]:
    """
    Builders of the datasets, with the number of steps per day.
    """
    return {
        "vic_electricity (30min, Demand)": (
            lambda: _last_days(_fetch("vic_electricity", data_dir), "Demand", 48), 48
        ),
        "ett_m1 (15min, OT)": (
            lambda: _last_days(_fetch("ett_m1", data_dir), "OT", 96), 96
        ),
        "ett_m2 (15min, OT)": (
            lambda: _last_days(_fetch("ett_m2", data_dir), "OT", 96), 96
        ),
        "ett_m1 (15min, HUFL)": (
            lambda: _last_days(_fetch("ett_m1", data_dir), "HUFL", 96), 96
        ),
        "synthetic (5min, day and hour)": (lambda: _synthetic("5min", 288, True), 288),
        "synthetic (10min, day only)": (lambda: _synthetic("10min", 144, False), 144),
    }


@contextmanager
def _day_first():
    """
    Make the lags and the window features read the day alone, the period of
    `FREQUENCY_TO_SEASONAL_PERIOD`, instead of `estimate_seasonality`.
    """

    from skforecast_ai.recommendation import autoregressive

    original = autoregressive.estimate_seasonality

    def day_alone(frequency):
        period = autoregressive.tabulated_seasonal_period(frequency)
        return [period] if period else original(frequency)

    autoregressive.estimate_seasonality = day_alone
    try:
        yield
    finally:
        autoregressive.estimate_seasonality = original


@contextmanager
def _baseline_period(period: int):
    """
    Make the baseline repeat `period` steps.
    """

    from skforecast_ai.recommendation import baseline

    original = baseline.select_baseline_seasonal_period
    baseline.select_baseline_seasonal_period = lambda frequency: period
    try:
        yield
    finally:
        baseline.select_baseline_seasonal_period = original


@contextmanager
def _nothing():
    yield


def _n_predictors(plan) -> int:
    """
    Lags plus window features (one per statistic and window) of a plan.
    """

    kwargs = plan.forecaster_kwargs
    lags = kwargs.get("lags") or []
    n_lags = lags if isinstance(lags, int) else len(lags)
    windows = kwargs.get("window_features") or []
    return n_lags + sum(len(w["stats"]) for w in windows)


def _run(data, steps, n_test, context, plan_arguments) -> dict:
    """
    Profile, plan and backtest under `context`, with a fresh assistant.
    """

    from skforecast.model_selection import TimeSeriesFold

    from skforecast_ai import ForecastingAssistant

    with context, warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assistant = ForecastingAssistant()
        profile = assistant.profile(data, target="y")
        plan = assistant.plan(
            profile=profile, steps=steps, metric=METRICS, **plan_arguments
        )
        cv = TimeSeriesFold(
            steps=steps, initial_train_size=len(data) - n_test, refit=False
        )
        start = time.perf_counter()
        result = assistant.backtest(
            data, cv=cv, profile=profile, plan=plan, show_progress=False
        )
        elapsed = time.perf_counter() - start
    metrics = result.metrics.iloc[0]
    return {
        "mase": float(metrics["mean_absolute_scaled_error"]),
        "mae": float(metrics["mean_absolute_error"]),
        "seconds": round(elapsed, 2),
        "n_predictors": _n_predictors(plan),
        "lags": plan.forecaster_kwargs.get("lags"),
        "window_features": plan.forecaster_kwargs.get("window_features"),
        "offset": plan.forecaster_kwargs.get("offset"),
        "n_folds": int(result.cv_config["n_folds"]),
    }


def _run_safely(data, steps, n_test, context, plan_arguments) -> dict:
    """
    `_run`, with an error as the result.
    """
    try:
        return _run(data, steps, n_test, context, plan_arguments)
    except Exception as exc:  # noqa: BLE001 - the error is the result
        return {"error": f"{type(exc).__name__}: {exc}"[:300]}


def _child(queue, data, steps, n_test, plan_arguments) -> None:
    queue.put(_run_safely(data, steps, n_test, _nothing(), plan_arguments))


def _run_with_timeout(data, steps, n_test, plan_arguments) -> dict:
    """
    `_run` in a child process, stopped after `ARIMA_TIMEOUT` seconds (the
    Auto-ARIMA search catches the exceptions of its models, so a signal
    would not stop it).
    """

    queue = multiprocessing.get_context("fork").Queue()
    process = multiprocessing.get_context("fork").Process(
        target=_child, args=(queue, data, steps, n_test, plan_arguments)
    )
    process.start()
    process.join(ARIMA_TIMEOUT)
    if process.is_alive():
        process.terminate()
        process.join()
        return {"error": f"stopped after {ARIMA_TIMEOUT} s"}
    return queue.get()


def measure(data_dir: Path, parts: list[str], only: str | None = None) -> dict:
    """
    Every backtest of the selected parts, by dataset and horizon, on the
    datasets whose name contains one of the comma separated texts of
    `only` (all when None).
    """

    results: dict = {}
    for name, (build, per_day) in datasets(data_dir).items():
        if only and not any(text in name for text in only.split(",")):
            continue
        data = build()
        hour = per_day // 24
        results[name] = {"n_rows": len(data)}
        print(name, len(data), flush=True)
        for horizon, steps in (("hour", hour), ("day", per_day)):
            n_test = TEST_DAYS * per_day
            runs = {}
            if "lags" in parts:
                runs["lags_hour_first"] = (data, n_test, _nothing(), {})
                runs["lags_day_alone"] = (data, n_test, _day_first(), {})
            if "baseline" in parts:
                baseline = {"forecaster": "ForecasterEquivalentDate"}
                runs["baseline_day"] = (data, n_test, _baseline_period(per_day), baseline)
                runs["baseline_hour"] = (data, n_test, _baseline_period(hour), baseline)
            if "arima" in parts and horizon == "day":
                short = data.iloc[-(ARIMA_TRAIN_DAYS + ARIMA_TEST_DAYS) * per_day:]
                n_short = ARIMA_TEST_DAYS * per_day
                for label, m in (("day", per_day), ("hour", hour)):
                    runs[f"arima_m_{label}"] = (
                        short, n_short, _nothing(),
                        {"forecaster": "ForecasterStats", "estimator_kwargs": {"m": m}},
                    )
            for label, (frame, n, context, arguments) in runs.items():
                if label.startswith("arima"):
                    outcome = _run_with_timeout(frame, steps, n, arguments)
                else:
                    outcome = _run_safely(frame, steps, n, context, arguments)
                results[name][f"{horizon}/{label}"] = outcome
                print(f"  {horizon}/{label}: {outcome}", flush=True)
    return results


def report(results: dict) -> None:
    """
    Print the results as Markdown tables.
    """

    print(
        "| Dataset | Horizon | Option | MASE | MAE | Seconds | Predictors |\n"
        "|---|---|---|---|---|---|---|"
    )
    for name, runs in results.items():
        for key, outcome in runs.items():
            if key == "n_rows":
                continue
            horizon, label = key.split("/")
            if "error" in outcome:
                print(f"| {name} | {horizon} | {label} | error: {outcome['error'][:80]} | | | |")
                continue
            predictors = outcome["n_predictors"] if label.startswith("lags") else ""
            print(
                f"| {name} | {horizon} | {label} | {outcome['mase']:.4f} "
                f"| {outcome['mae']:.4f} | {outcome['seconds']:.2f} | {predictors} |"
            )


def main() -> int:
    """
    Command line entry point.
    """
    if len(sys.argv) >= 2 and sys.argv[1] == "report":
        report(json.loads(Path(sys.argv[2]).read_text()))
        return 0
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("output", type=Path)
    parser.add_argument("--parts", default="lags,baseline,arima")
    parser.add_argument(
        "--datasets", default=None, help="Comma separated parts of names."
    )
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    arguments = parser.parse_args()
    results = measure(
        arguments.data_dir, arguments.parts.split(","), arguments.datasets
    )
    arguments.output.write_text(json.dumps(results, indent=1))
    report(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
