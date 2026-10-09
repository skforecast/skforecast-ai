################################################################################
#                          generate_home_data                                  #
#                                                                              #
# Writes docs/overrides/partials/home-data.json, the data of the animations   #
# of the documentation home page, and the data of the animations of the user   #
# guide in docs/animations/. See tools/docs/home_page/README.md.               #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

"""
Generate the data of the documentation home page animations.

Every number the home page shows is a real skforecast-ai output, from the
workflow of `tools/ai/check_ask_context.py` on `bike_sharing` (last 2000
hourly rows, 36 steps, 80% interval). The `ask()` answers of the page are
examples written by hand, not recorded from a model; the script checks that
the numbers they quote (`QUOTED`) still match the results, so a change in the
data stops it instead of leaving an answer about other results.

It also writes the data of the animation "Deterministic first, LLM second"
(`docs/animations/deterministic-first.html`), which continues the same
workflow with `refine_plan()` and `ask()`. The suggestion of `refine_plan()`
(`REFINE_SUGGESTION`) and the answer of `ask()` are examples written by hand;
the suggestion is applied as an explicit override, which goes through the same
`plan()` call as the LLM mode, so the refined plan and its metrics are real.
No LLM is called.

Finally, it writes the data of the animation "Validate the way you deploy"
(`docs/animations/backtesting-scenario.html`): the folds, predictions and
metrics of `backtest()` with the `create_cv()` strategy of a deployment
scenario (`BACKTEST_SCENARIO`). The scenario and its translation into
parameters are written by hand in the animation; the parameters are passed
explicitly to `create_cv()`, the same path the LLM mode takes.

With the same strategy, it writes the data of the animation "Let measured
performance pick the model" (`docs/animations/compare-candidates.html`): the
leaderboard of `compare()` with the candidates the profile proposes and the
seasonal naive baseline it adds, and the error of every row in every fold.

Run from the repository root:

    python tools/docs/home_page/generate_home_data.py
"""

from __future__ import annotations

import json
import re
import sys
import warnings
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from skforecast_ai import ForecastingAssistant  # noqa: E402
from skforecast_ai._constants import MAX_FEATURE_FRACTION  # noqa: E402

OUTPUT = REPO_ROOT / "docs" / "overrides" / "partials" / "home-data.json"
ANIMATION_OUTPUT = REPO_ROOT / "docs" / "animations" / "deterministic-first-data.js"
BACKTEST_OUTPUT = REPO_ROOT / "docs" / "animations" / "backtesting-scenario-data.js"
COMPARE_OUTPUT = REPO_ROOT / "docs" / "animations" / "compare-candidates-data.js"

TAIL = 2000
STEPS = 36
# Eight days, so the arc of lag 169 fits before the last training hour.
HISTORY_SHOWN = 192
# Numbers quoted, rounded as written, by the example ask() answers: step 4 of
# the animation in docs/overrides/home.html and the tabs of
# docs/overrides/partials/ask-window.html. The backtest uses the plan and the
# cross-validation of compare(), so it is the "LightGBM, recursive" row of the
# leaderboard, the winner of the Compare tab.
QUOTED = {
    "forecast MAE": 45.8,
    "forecast MASE": 0.62,
    "backtest MAE": 49.5,
    "backtest MASE": 0.65,
    "backtest folds": 17,
    "runner-up MAE": 53.1,
    "gap to the runner-up (%)": 6.7,
    "gap to the baseline (%)": 22.4,
    "lags": 28,
}
# Lags named by the Plan tab.
QUOTED_LAGS = {1, 2, 3, 23, 24, 25, 167, 169}

# Prompt of refine_plan() in the animation "Deterministic first, LLM second",
# and the suggestion the animation shows for it. The suggestion is an example
# written by hand, not recorded from a model: the last 24 hours and the same
# hour a week earlier, with daily and weekly rolling statistics.
REFINE_PROMPT = "Rentals follow the daily commute and a weekly cycle."
REFINE_SUGGESTION = {
    "lags": [*range(1, 25), 168],
    "window_features": [
        {"stats": ["mean", "std"], "window_size": 24},
        {"stats": ["mean", "std"], "window_size": 168},
    ],
}
# The animation shows a first suggestion rejected by the validation of plan():
# the lags of REFINE_SUGGESTION plus a monthly lag (30 days), longer than the 33% of the
# series that plan() accepts. The suggestion is illustrative; the rejection
# message is the real one.
REJECTED_EXTRA_LAG = 720
# Scenario of the animation "Validate the way you deploy": "Every day at noon we
# forecast the next 36 hours, and we retrain once a week." A forecast every 24
# hours, retraining every 7 folds, and forecasts made at noon: the initial
# training ends at the first 11:00 on or after the deterministic default.
BACKTEST_SCENARIO = {"fold_stride": 24, "refit": 7, "fixed_train_size": False, "gap": 0}
BACKTEST_ORIGIN_HOUR = 12
# Hours shown before the first forecast of the backtest.
BACKTEST_CONTEXT = 72
METRIC_LABELS = {
    "mean_absolute_error": "MAE",
    "mean_squared_error": "MSE",
    "mean_absolute_scaled_error": "MASE",
    "root_mean_squared_scaled_error": "RMSSE",
}


def load_bike_sharing() -> pd.DataFrame:
    """
    Load the last `TAIL` hourly rows of `bike_sharing`, as check_ask_context.

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


def window_features_label(window_features: list[dict] | None) -> str:
    """
    Describe window features in one short line, grouped by statistic.

    Parameters
    ----------
    window_features : list of dict, None
        Window features of a plan, one dict with `'stats'` and
        `'window_size'` per window size.

    Returns
    -------
    label : str
        For example `'mean 3, 24, 168; std 3'`, or `'none'`.
    """

    if not window_features:
        return "none"
    sizes: dict[str, list[int]] = {}
    for feature in window_features:
        for stat in feature["stats"]:
            sizes.setdefault(stat, []).append(int(feature["window_size"]))

    return "; ".join(
        f"{stat} {', '.join(str(v) for v in values)}" for stat, values in sizes.items()
    )


def lags_list(lags: int | list[int]) -> list[int]:
    """
    Expand a lags value of a plan into the list of lags it means.

    Parameters
    ----------
    lags : int, list of int
        An int `n` means the consecutive lags `1..n`.

    Returns
    -------
    lags : list of int
        Sorted lags.
    """

    if isinstance(lags, int):
        return list(range(1, lags + 1))

    return sorted(int(v) for v in lags)


def write_animation_data(
    assistant: ForecastingAssistant,
    data: pd.DataFrame,
    profile,
    plan,
) -> None:
    """
    Write the data of the animation "Deterministic first, LLM second".

    Applies `REFINE_SUGGESTION` as an explicit override of `refine_plan()`
    (the LLM mode merges its suggestion the same way and calls the same
    `plan()`) and forecasts with the refined plan.

    Parameters
    ----------
    assistant : ForecastingAssistant
        Assistant without LLM.
    data : pandas DataFrame
        Data returned by `load_bike_sharing()`.
    profile : ForecastingProfile
        Profile of `data`.
    plan : ForecastPlan
        Deterministic plan of `data`.

    Returns
    -------
    None
    """

    suggested = REFINE_SUGGESTION

    refined = assistant.refine_plan(profile, plan, **suggested)
    result = assistant.forecast(
        data=data, test_size=STEPS, profile=profile, plan=refined
    )
    metrics = result.metrics.iloc[0]
    mase = float(metrics["MASE"])

    lags = lags_list(refined.forecaster_kwargs["lags"])
    rejected = lags + [REJECTED_EXTRA_LAG]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            assistant.refine_plan(profile, plan, lags=rejected)
    except ValueError as exc:
        rejection = str(exc)
    else:
        raise SystemExit(
            f"lags={rejected} passed the validation of plan(); raise "
            "REJECTED_EXTRA_LAG so the animation shows a rejection."
        )

    dp = profile.data_profile
    n_obs = int(dp.span_index_length)
    series = data.set_index("date_time")["users"]
    train = series.iloc[:-STEPS]
    predictions = result.predictions
    fk = plan.forecaster_kwargs
    refined_windows = refined.forecaster_kwargs.get("window_features")

    payload = {
        "history": rounded(train.iloc[-168:].to_numpy(), 0),
        "actual": rounded(series.iloc[-STEPS:].to_numpy(), 0),
        "pred": rounded(predictions["pred"]),
        "lo": rounded(predictions["lower_bound"]),
        "hi": rounded(predictions["upper_bound"]),
        "metrics": {
            "mae": round(float(metrics["MAE"]), 1),
            "mase": round(mase, 2),
        },
        "profile": [
            ["frequency", dp.frequency],
            ["observations", f"{int(dp.n_total_observations):,}"],
            ["exogenous", str(len(dp.exog_columns))],
            ["missing values", str(int(sum(dp.missing_target.values())))],
            ["PACF lags", ", ".join(str(int(v)) for v in profile.series_pacf[0].lags[:4])],
        ],
        "plan": [
            ["forecaster", plan.forecaster],
            ["estimator", plan.estimator],
            ["lags", f"{len(lags_list(fk['lags']))}, from PACF"],
            ["windows", window_features_label(fk.get("window_features"))],
            ["metric", METRIC_LABELS.get(plan.metric, plan.metric)],
        ],
        "refined": {
            "fields": list(suggested),
            "lags": lags,
            "windows": window_features_label(refined_windows),
        },
        "rejected": {
            "lags": rejected,
            "span": REJECTED_EXTRA_LAG,
            "max": int(n_obs * MAX_FEATURE_FRACTION),
            "n_obs": n_obs,
            "message": rejection,
        },
        "llm": {
            "refine_prompt": REFINE_PROMPT,
        },
    }
    if f"maximum of {payload['rejected']['max']} " not in rejection:
        raise SystemExit(
            f"The rejection message changed ({rejection!r}); update the "
            "maximum in write_animation_data()."
        )

    ANIMATION_OUTPUT.write_text(
        "// Generated by tools/docs/home_page/generate_home_data.py. Do not edit.\n"
        "window.DETERMINISTIC_FIRST_DATA = "
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
    )
    print(f"Wrote {ANIMATION_OUTPUT.relative_to(REPO_ROOT)}")
    print(f"Refined: lags {lags}, MAE {metrics['MAE']:.4f}, MASE {mase:.6f}")


def scenario_cv(assistant: ForecastingAssistant, profile, plan) -> tuple:
    """
    Build the deterministic strategy and the strategy of `BACKTEST_SCENARIO`.

    Parameters
    ----------
    assistant : ForecastingAssistant
        Assistant without LLM.
    profile : ForecastingProfile
        Profile of the data.
    plan : ForecastPlan
        Deterministic plan of the data.

    Returns
    -------
    deterministic : CVResult
        Strategy of `create_cv()` without prompt or overrides.
    scenario : CVResult
        Strategy of the scenario: forecasts every day at noon, retrained
        every 7 folds, with the initial training ending at the first 11:00
        on or after the deterministic default.
    """

    deterministic = assistant.create_cv(profile, plan)
    default_end = pd.Timestamp(deterministic.cv_config["initial_train_size"])
    train_end = default_end.normalize() + pd.Timedelta(hours=BACKTEST_ORIGIN_HOUR - 1)
    if train_end < default_end:
        train_end += pd.Timedelta(days=1)
    scenario = assistant.create_cv(
        profile, plan, initial_train_size=str(train_end), **BACKTEST_SCENARIO
    )

    return deterministic, scenario


def write_backtesting_data(
    assistant: ForecastingAssistant,
    data: pd.DataFrame,
    profile,
    plan,
) -> None:
    """
    Write the data of the animation "Validate the way you deploy".

    Builds the strategy of `BACKTEST_SCENARIO` with `create_cv()`, runs
    `backtest()` with it and writes the series around the folds, every fold
    (with whether the model is trained in it), the predictions of each fold,
    the metrics, and the `TimeSeriesFold` and `backtesting_forecaster()`
    snippets of the script. It also
    records the deterministic strategy, which the animation compares with.

    Parameters
    ----------
    assistant : ForecastingAssistant
        Assistant without LLM.
    data : pandas DataFrame
        Data returned by `load_bike_sharing()`.
    profile : ForecastingProfile
        Profile of `data`.
    plan : ForecastPlan
        Deterministic plan of `data`.

    Returns
    -------
    None
    """

    deterministic, scenario = scenario_cv(assistant, profile, plan)
    result = assistant.backtest(
        data=data, cv=scenario, profile=profile, plan=plan, show_progress=False
    )

    series = data.set_index("date_time")["users"].asfreq(profile.data_profile.frequency)
    with warnings.catch_warnings():
        # split() warns that it cannot compute the last window of a splitter
        # without window_size; the animation does not use it.
        warnings.simplefilter("ignore")
        folds = scenario.cv.split(X=series, as_pandas=True)
    start = int(folds["test_start"].iloc[0]) - BACKTEST_CONTEXT
    predictions = result.predictions
    metrics = result.metrics.iloc[0]
    code = scenario.code
    snippet = code[code.index("cv = TimeSeriesFold("):].split("\n")
    snippet = snippet[: snippet.index(")") + 1]
    script = result.code
    call = script[script.index("metrics, predictions = backtesting_forecaster("):].split("\n")
    call = call[: call.index(")") + 1]

    payload = {
        "start": str(series.index[start]),
        "start_pos": start,
        "n_obs": len(series),
        "y": rounded(series.iloc[start:].to_numpy(), 0),
        "folds": [
            [int(row.train_end), int(row.test_start), int(row.test_end), bool(row.fit_forecaster)]
            for row in folds.itertuples()
        ],
        "pred": [
            rounded(predictions.loc[predictions["fold"] == k, "pred"])
            for k in range(len(folds))
        ],
        "metrics": {
            "mae": round(float(metrics["mean_absolute_error"]), 1),
            "mase": round(float(metrics["mean_absolute_scaled_error"]), 2),
        },
        "cv": {k: v for k, v in scenario.cv_config.items() if v is not None},
        "snippet": snippet,
        "call": call,
        "deterministic": {
            "n_folds": deterministic.cv_config["n_folds"],
            "fold_stride": deterministic.cv_config["fold_stride"],
            "refit": deterministic.cv_config["refit"],
        },
    }

    BACKTEST_OUTPUT.write_text(
        "// Generated by tools/docs/home_page/generate_home_data.py. Do not edit.\n"
        "window.BACKTESTING_SCENARIO_DATA = "
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
    )
    print(f"Wrote {BACKTEST_OUTPUT.relative_to(REPO_ROOT)}")
    print(f"Scenario: {scenario.explanation} MAE {metrics['mean_absolute_error']:.4f}")


def baseline_detail(offset: int) -> str:
    """
    Describe the values the hourly seasonal naive baseline repeats.

    Parameters
    ----------
    offset : int
        `offset` of the `ForecasterEquivalentDate` baseline, in hours.

    Returns
    -------
    detail : str
        Short description shown under the baseline in the animation.
    """

    if offset == 1:
        return "repeats the last hour"
    if offset == 24:
        return "same hour, one day earlier"
    if offset == 168:
        return "same hour, one week earlier"
    return f"repeats the value {offset} hours earlier"


def write_compare_data(
    assistant: ForecastingAssistant,
    data: pd.DataFrame,
    profile,
    plan,
) -> None:
    """
    Write the data of the animation "Let measured performance pick the model".

    Runs `compare()` with the candidates the profile proposes and the strategy
    of the backtesting animation, and writes the leaderboard, the series over
    the span of the folds, and the predictions and errors of every candidate,
    the seasonal naive baseline that `compare()` adds included. With
    overlapping folds, skforecast scores each hour with its latest
    forecast, so those are the predictions written, and the error of a fold
    uses the hours where its forecast is the latest one; the mean over all
    those hours is the metric of the leaderboard, which the script checks.

    Parameters
    ----------
    assistant : ForecastingAssistant
        Assistant without LLM.
    data : pandas DataFrame
        Data returned by `load_bike_sharing()`.
    profile : ForecastingProfile
        Profile of `data`.
    plan : ForecastPlan
        Deterministic plan of `data`.

    Returns
    -------
    None
    """

    _, scenario = scenario_cv(assistant, profile, plan)
    comparison = assistant.compare(
        data=data, cv=scenario, profile=profile, show_progress=False
    )
    metric = comparison.ranking_metric
    board = comparison.results.set_index("name")
    series = data.set_index("date_time")["users"]

    rows = {}
    hours = None
    for name, result in comparison.candidates.items():
        predictions = result.predictions
        scored = predictions.loc[~predictions.index.duplicated(keep="last")]
        if hours is None:
            hours = scored.index
        elif not scored.index.equals(hours):
            raise SystemExit(f"{name} was scored on other hours than the rest.")
        errors = (scored["pred"] - series.loc[scored.index]).abs()
        by_fold = errors.groupby(scored["fold"])
        mae = float(errors.mean())
        if abs(mae - float(board.loc[name, metric])) > 1e-6:
            raise SystemExit(
                f"The errors of {name} per fold give an MAE of {mae:.6f}, the "
                f"leaderboard says {board.loc[name, metric]:.6f}: the scoring "
                "rule of overlapping folds changed."
            )
        kwargs = result.plan.forecaster_kwargs
        if name == comparison.baseline_name:
            detail = baseline_detail(kwargs["offset"])
        elif kwargs.get("lags") is not None:
            detail = f"{len(lags_list(kwargs['lags']))} lags, rolling windows"
        else:
            detail = "pre-trained, no lags"
        rows[name] = {
            "forecaster": result.plan.forecaster,
            # The baseline has no estimator: its lane shows the forecaster.
            "estimator": result.plan.estimator or result.plan.forecaster,
            "detail": detail,
            "rank": int(board.loc[name, "rank"]),
            "mae": round(mae, 1),
            "mase": round(float(board.loc[name, "mean_absolute_scaled_error"]), 2),
            "pred": rounded(scored["pred"].to_numpy()),
            "fold_mae": rounded(by_fold.mean().to_numpy()),
            "fold_n": [int(v) for v in by_fold.size().to_numpy()],
        }
    ranked = list(board.index)
    order = [name for name in profile.forecaster_candidates if name in rows]
    order += [name for name in ranked if name not in order]
    first, second = board[metric].iloc[0], board[metric].iloc[1]
    if comparison.baseline_name is None:
        raise SystemExit("compare() added no baseline: the animation shows one.")
    reference = board.loc[comparison.baseline_name, metric]

    payload = {
        "start": str(hours[0]),
        "actual": rounded(series.loc[hours].to_numpy(), 0),
        "order": order,
        "ranked": ranked,
        "rows": rows,
        "metric": metric,
        "gap_pct": round(float((second - first) / second * 100), 1),
        "baseline": comparison.baseline_name,
        # Improvement of the winner over the baseline, as the explanation of
        # compare() computes it.
        "baseline_gap_pct": round(float((reference - first) / reference * 100), 1),
        "cv": {
            k: scenario.cv_config[k]
            for k in ("n_folds", "steps", "initial_train_size", "fold_stride", "refit")
        },
    }
    COMPARE_OUTPUT.write_text(
        "// Generated by tools/docs/home_page/generate_home_data.py. Do not edit.\n"
        "window.COMPARE_CANDIDATES_DATA = "
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
    )
    print(f"Wrote {COMPARE_OUTPUT.relative_to(REPO_ROOT)}")
    print(comparison.explanation)


def check_quoted_numbers(result, cv_result, comparison, plan) -> None:
    """
    Stop when a number quoted by the example ask() answers no longer matches.

    The answers are written by hand, so nothing regenerates them: when the
    results change, the answers and `QUOTED` are edited together. No LLM is
    involved.

    Parameters
    ----------
    result : ForecastResult
        Forecast evaluated on the held-out hours.
    cv_result : CVResult
        Cross-validation strategy of the comparison.
    comparison : ComparisonResult
        Comparison of the home page.
    plan : ForecastPlan
        Deterministic plan of the data.

    Returns
    -------
    None
    """

    board = comparison.results.set_index("name")
    winner = board.loc["LightGBM, recursive"]
    explanation = comparison.explanation
    gaps = {
        "gap to the runner-up (%)": r"([\d.]+)% ahead of",
        "gap to the baseline (%)": r"beats the baseline .* by ([\d.]+)%",
    }
    actual = {
        "forecast MAE": round(float(result.metrics.iloc[0]["MAE"]), 1),
        "forecast MASE": round(float(result.metrics.iloc[0]["MASE"]), 2),
        "backtest MAE": round(float(winner["mean_absolute_error"]), 1),
        "backtest MASE": round(float(winner["mean_absolute_scaled_error"]), 2),
        "backtest folds": int(cv_result.cv_config["n_folds"]),
        "runner-up MAE": round(float(board.loc["LightGBM, direct", "mean_absolute_error"]), 1),
        "lags": len(plan.forecaster_kwargs["lags"]),
    }
    for key, pattern in gaps.items():
        found = re.search(pattern, explanation)
        actual[key] = float(found.group(1)) if found else None

    changed = [
        f"{key}: quoted {QUOTED[key]}, now {actual[key]}"
        for key in QUOTED
        if actual[key] != QUOTED[key]
    ]
    missing = QUOTED_LAGS - set(plan.forecaster_kwargs["lags"])
    if missing:
        changed.append(f"lags named by the Plan tab no longer in the plan: {sorted(missing)}")
    if changed:
        raise SystemExit(
            "The example ask() answers quote numbers that changed:\n  "
            + "\n  ".join(changed)
            + "\nEdit the answers (step 4 in docs/overrides/home.html, the tabs "
            "of docs/overrides/partials/ask-window.html) and QUOTED or QUOTED_LAGS."
        )


def main() -> None:
    """
    Run the workflow and write the data files of the home page and of the
    animation "Deterministic first, LLM second".
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
    check_quoted_numbers(result, cv_result, comparison, plan)
    leaderboard = comparison.results

    series = data.set_index("date_time")["users"]
    shown = series.iloc[-(HISTORY_SHOWN + STEPS):]
    predictions = result.predictions
    dp = profile.data_profile
    pacf = profile.series_pacf[0]
    fk = plan.forecaster_kwargs

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
            "baseline": comparison.baseline_name,
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

    write_animation_data(assistant, data, profile, plan)
    write_backtesting_data(assistant, data, profile, plan)
    write_compare_data(assistant, data, profile, plan)


if __name__ == "__main__":
    main()
