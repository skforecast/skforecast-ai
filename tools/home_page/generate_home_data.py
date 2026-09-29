################################################################################
#                          generate_home_data                                  #
#                                                                              #
# Writes docs/overrides/partials/home-data.json, the data of the animations   #
# of the documentation home page. See tools/home_page/README.md.               #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

"""
Generate the data of the documentation home page animations.

Every number the home page shows is a real skforecast-ai output. The workflow
is the one of `tools/ask_context_check.py` on `bike_sharing` (last 2000 hourly
rows, 36 steps, 80% interval), so the `ask()` answer quoted in the animation,
taken from `tools/ask_context_reports/<release>_bike_sharing.md`, refers to the
same results. The script checks that the metrics still match that answer.

Run from the repository root:

    python tools/home_page/generate_home_data.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from skforecast_ai import ForecastingAssistant  # noqa: E402

OUTPUT = REPO_ROOT / "docs" / "overrides" / "partials" / "home-data.json"

TAIL = 2000
STEPS = 36
# Eight days, so the arc of lag 169 fits before the last training hour.
HISTORY_SHOWN = 192
# MASE quoted in the ask() answer of the animation
# (tools/ask_context_reports/0.3.0_bike_sharing.md, scenario forecast).
QUOTED_MASE = 0.616892


def load_bike_sharing() -> pd.DataFrame:
    """
    Load the last `TAIL` hourly rows of `bike_sharing`, as ask_context_check.

    Returns
    -------
    data : pandas DataFrame
        Columns `date_time`, `users`, `holiday`, `weather` and `temp`.
    """

    from skforecast.datasets import fetch_dataset

    data = fetch_dataset("bike_sharing", raw=True, verbose=False)
    data = data[["date_time", "users", "holiday", "weather", "temp"]].copy()
    data["date_time"] = pd.to_datetime(data["date_time"])

    return data.tail(TAIL).reset_index(drop=True)


def rounded(values, digits: int = 1) -> list[float]:
    """
    Round a sequence of numbers for the JSON file.

    Parameters
    ----------
    values : iterable of float
        Values to round.
    digits : int, default 1
        Number of decimals.

    Returns
    -------
    values : list of float
        Rounded values.
    """

    return [round(float(v), digits) for v in values]


def main() -> None:
    """
    Run the workflow and write the JSON file of the home page.
    """

    data = load_bike_sharing()
    assistant = ForecastingAssistant()

    profile = assistant.profile(data=data, target="users", date_column="date_time")
    plan = assistant.plan(profile, steps=STEPS, interval=[0.1, 0.9])
    result = assistant.forecast(
        data=data, test_size=STEPS, profile=profile, plan=plan
    )
    cv_result = assistant.create_cv(profile, plan, refit=False)
    candidates = [
        ("LightGBM, recursive", {"forecaster": "ForecasterRecursive"}),
        ("LightGBM, direct", {"forecaster": "ForecasterDirect"}),
        ("Ridge, recursive", {"forecaster": "ForecasterRecursive", "estimator": "Ridge"}),
    ]
    comparison = assistant.compare(
        data=data, cv=cv_result, profile=profile, candidates=candidates,
        show_progress=False,
    )

    metrics = result.metrics.iloc[0]
    mase = float(metrics["MASE"])
    if round(mase, 6) != QUOTED_MASE:
        raise SystemExit(
            f"MASE is {mase:.6f}, the ask() answer quoted on the home page says "
            f"{QUOTED_MASE}. Rerun tools/ask_context_check.py on bike_sharing and "
            "update the answer in docs/overrides/home.html and QUOTED_MASE."
        )

    series = data.set_index("date_time")["users"]
    shown = series.iloc[-(HISTORY_SHOWN + STEPS):]
    predictions = result.predictions
    dp = profile.data_profile
    pacf = profile.series_pacf[0]
    fk = plan.forecaster_kwargs

    leaderboard = comparison.results
    metric_column = "mean_absolute_error"

    payload = {
        "hero": {
            "dates": [d.strftime("%Y-%m-%d %H:%M") for d in shown.index],
            "y": rounded(shown.to_numpy(), 0),
            "train_end": predictions.index[0].strftime("%Y-%m-%d %H:%M"),
            "steps": STEPS,
            "pred": rounded(predictions["pred"]),
            "lo": rounded(predictions["lower_bound"]),
            "hi": rounded(predictions["upper_bound"]),
        },
        "profile": {
            "n_obs": int(dp.n_total_observations),
            "frequency": dp.frequency,
            "start": str(series.index.min()),
            "end": str(series.index.max()),
            "exog": list(dp.exog_columns),
            "categorical_exog": list(dp.categorical_exog),
            "missing": int(sum(dp.missing_target.values())),
            "pacf_lags": [int(v) for v in pacf.lags],
            "pacf_abs": rounded(pacf.pacf_abs, 3),
            "forecaster": profile.forecaster,
            "estimator": profile.estimator,
            "calendar_features": profile.calendar_features,
        },
        "plan": {
            "forecaster": plan.forecaster,
            "estimator": plan.estimator,
            "lags": [int(v) for v in fk["lags"]],
            "window_features": fk.get("window_features"),
            "interval": plan.interval,
            "interval_method": plan.interval_method,
            "metric": plan.metric,
        },
        "metrics": {
            "mae": round(float(metrics["MAE"]), 1),
            "mase": round(mase, 2),
            "mape": round(float(metrics["MAPE"]), 2),
        },
        "code": result.code,
        "compare": {
            "metric": metric_column,
            "cv": cv_result.explanation,
            "explanation": comparison.explanation,
            "rows": [
                {
                    "name": row["name"],
                    "mae": round(float(row[metric_column]), 2),
                    "mase": round(float(row["mean_absolute_scaled_error"]), 2),
                }
                for _, row in leaderboard.iterrows()
            ],
        },
    }

    OUTPUT.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(REPO_ROOT)}")
    print(f"MAE {metrics['MAE']:.4f}, MASE {mase:.6f}")
    print(comparison.explanation)


if __name__ == "__main__":
    main()
