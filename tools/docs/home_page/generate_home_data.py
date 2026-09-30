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

Every number the home page shows is a real skforecast-ai output. The workflow
is the one of `tools/ai/check_ask_context.py` on `bike_sharing` (last 2000 hourly
rows, 36 steps, 80% interval), so the `ask()` answer quoted in the animation,
taken from `tools/ai/ask_context_reports/<release>_bike_sharing.md`, refers to the
same results. The script checks that the metrics still match that answer.

It also writes the data of the animation "Deterministic first, LLM second"
(`docs/animations/deterministic-first.html`), which continues the same
workflow with `refine_plan()` and `ask()`. The LLM suggestion of
`refine_plan()` is recorded once with `--llm`, which calls a real model, and
kept in `ANIMATION_LLM_OUTPUTS`; every other run replays it as an explicit
override, which goes through the same `plan()` call. The answer of `ask()` is
written by hand in the animation.

Finally, it writes the data of the animation "Validate the way you deploy"
(`docs/animations/backtesting-scenario.html`): the folds, predictions and
metrics of `backtest()` with the `create_cv()` strategy of a deployment
scenario (`BACKTEST_SCENARIO`). The scenario and its translation into
parameters are written by hand in the animation; the parameters are passed
explicitly to `create_cv()`, the same path the LLM mode takes.

With the same strategy, it writes the data of the animation "Let measured
performance pick the model" (`docs/animations/compare-candidates.html`): the
leaderboard of `compare()` with the candidates the profile proposes, and the
error of every candidate in every fold.

Run from the repository root:

    python tools/docs/home_page/generate_home_data.py
    python tools/docs/home_page/generate_home_data.py --llm google:gemini-3.5-flash
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from datetime import date
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
# LLM outputs of the animation, written by `--llm` and reviewed by hand.
ANIMATION_LLM_OUTPUTS = Path(__file__).resolve().parent / "deterministic_first_llm.json"

TAIL = 2000
STEPS = 36
# Eight days, so the arc of lag 169 fits before the last training hour.
HISTORY_SHOWN = 192
# MASE quoted in the ask() answer of the animation
# (tools/ai/ask_context_reports/0.3.0_bike_sharing.md, scenario forecast).
QUOTED_MASE = 0.616892
# MASE quoted in the Backtest tab of the ask() section (same report, scenario
# backtest). The backtest uses the plan and the cross-validation of compare(),
# so it is the MASE of the "LightGBM, recursive" row of the leaderboard, which
# is also the winner quoted in the Compare tab.
QUOTED_BACKTEST_MASE = 0.6531

# Questions of the animation "Deterministic first, LLM second".
REFINE_PROMPT = "Rentals follow the daily commute and a weekly cycle."
# The animation shows a first suggestion rejected by the validation of plan():
# the recorded lags plus a monthly lag (30 days), longer than the 33% of the
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


def record_llm_outputs(model: str, data: pd.DataFrame, profile, plan) -> None:
    """
    Call a real LLM and record the suggestion the animation shows.

    Runs `refine_plan()` with `REFINE_PROMPT` and writes the fields the LLM
    suggested in `ANIMATION_LLM_OUTPUTS`. It costs money: review the file
    before committing it.

    Parameters
    ----------
    model : str
        LLM provider string, for example `'google:gemini-3.5-flash'`.
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

    api_key = os.getenv("GOOGLE_API_KEY") if model.startswith("google:") else None
    if model.startswith("google:") and not api_key:
        raise SystemExit("Set GOOGLE_API_KEY to record the LLM outputs.")
    assistant = ForecastingAssistant(llm=model, api_key=api_key)

    refined = assistant.refine_plan(profile, plan, prompt=REFINE_PROMPT)
    if "lags" not in refined.llm_refined_fields:
        raise SystemExit(
            "The LLM did not change the lags (fields applied: "
            f"{refined.llm_refined_fields}), so the animation has nothing to "
            "show. Run again, or adjust REFINE_PROMPT."
        )
    suggested = {
        field: refined.forecaster_kwargs[field] for field in refined.llm_refined_fields
    }

    record = {
        "model": model,
        "date": date.today().isoformat(),
        "refine": {"prompt": REFINE_PROMPT, "suggested": suggested},
    }
    ANIMATION_LLM_OUTPUTS.write_text(
        json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Wrote {ANIMATION_LLM_OUTPUTS.relative_to(REPO_ROOT)}. Review it before committing.")
    print(f"Suggested: {suggested}")


def write_animation_data(
    assistant: ForecastingAssistant,
    data: pd.DataFrame,
    profile,
    plan,
) -> None:
    """
    Write the data of the animation "Deterministic first, LLM second".

    Replays the recorded LLM suggestion as an explicit override of
    `refine_plan()` (the LLM mode merges its suggestion the same way and
    calls the same `plan()`) and forecasts with the refined plan.

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

    if not ANIMATION_LLM_OUTPUTS.exists():
        print(
            f"Skipped {ANIMATION_OUTPUT.relative_to(REPO_ROOT)}: "
            f"{ANIMATION_LLM_OUTPUTS.name} does not exist. Record it once with "
            "--llm <model> (it calls a real LLM)."
        )
        return
    record = json.loads(ANIMATION_LLM_OUTPUTS.read_text(encoding="utf-8"))
    suggested = record["refine"]["suggested"]

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
            "model": record["model"],
            "refine_prompt": record["refine"]["prompt"],
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
    the span of the folds, and the predictions and errors of every candidate.
    With overlapping folds, skforecast scores each hour with its latest
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
        lags = result.plan.forecaster_kwargs.get("lags")
        rows[name] = {
            "forecaster": result.plan.forecaster,
            "estimator": result.plan.estimator,
            "detail": (
                f"{len(lags_list(lags))} lags, rolling windows"
                if lags is not None
                else "pre-trained, no lags"
            ),
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

    payload = {
        "start": str(hours[0]),
        "actual": rounded(series.loc[hours].to_numpy(), 0),
        "order": order,
        "ranked": ranked,
        "rows": rows,
        "metric": metric,
        "gap_pct": round(float((second - first) / second * 100), 1),
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


def main() -> None:
    """
    Run the workflow and write the data files of the home page and of the
    animation "Deterministic first, LLM second".
    """

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument(
        "--llm",
        default=None,
        metavar="MODEL",
        help=(
            "Record the LLM outputs of the animation with this model, e.g. "
            "google:gemini-3.5-flash. Calls a real LLM (it costs money)."
        ),
    )
    args = parser.parse_args()

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
            f"{QUOTED_MASE}. Rerun tools/ai/check_ask_context.py on bike_sharing and "
            "update the answer in docs/overrides/home.html and QUOTED_MASE."
        )

    leaderboard = comparison.results
    winner = leaderboard.loc[leaderboard["name"] == "LightGBM, recursive"].iloc[0]
    backtest_mase = float(winner["mean_absolute_scaled_error"])
    if round(backtest_mase, 4) != QUOTED_BACKTEST_MASE:
        raise SystemExit(
            f"Backtest MASE is {backtest_mase:.4f}, the ask() answer quoted in the "
            f"Backtest tab of the home page says {QUOTED_BACKTEST_MASE}. Rerun "
            "tools/ai/check_ask_context.py on bike_sharing and update the answers of "
            "the ask() section in docs/overrides/home.html and QUOTED_BACKTEST_MASE."
        )

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

    if args.llm:
        record_llm_outputs(args.llm, data, profile, plan)
    write_animation_data(assistant, data, profile, plan)
    write_backtesting_data(assistant, data, profile, plan)
    write_compare_data(assistant, data, profile, plan)


if __name__ == "__main__":
    main()
