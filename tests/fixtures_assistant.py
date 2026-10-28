# Fixtures for assistant tests

import numpy as np
import pandas as pd


# Seed for reproducibility
_rng = np.random.default_rng(42)

# --- Single series fixture (100 daily observations with exog) ---
_n_obs = 100
_dates = pd.date_range("2023-01-01", periods=_n_obs, freq="D")

df_single = pd.DataFrame(
    {
        "date": _dates,
        "sales": np.arange(_n_obs, dtype=float),
        "promo": np.tile([0.0, 1.0], _n_obs // 2),
    }
)

# --- Single series with a numeric and a categorical exog ---
df_categorical_exog = df_single.assign(
    weekday=df_single["date"].dt.day_name(),
)

# --- Single series with exog named like the calendar features ---
# The daily profile recommends `day_of_week`, `weekend` and `month`; these
# exog columns carry the names the raw calendar columns would take.
df_calendar_named_exog = df_single.assign(
    month=df_single["date"].dt.month,
    weekend=(df_single["date"].dt.dayofweek >= 5).astype(int),
)
df_all_calendar_named_exog = df_calendar_named_exog.assign(
    day_of_week=df_single["date"].dt.dayofweek,
)

# --- Single series without exog (100 daily observations) ---
df_no_exog = pd.DataFrame(
    {
        "date": _dates,
        "sales": np.arange(_n_obs, dtype=float),
    }
)

# --- Single series with hourly frequency (200 observations) ---
_n_obs_hourly = 200
_dates_hourly = pd.date_range("2023-01-01", periods=_n_obs_hourly, freq="h")

df_hourly = pd.DataFrame(
    {
        "date": _dates_hourly,
        "sales": np.arange(_n_obs_hourly, dtype=float),
    }
)

# --- Biweekly series fixture (120 observations every two weeks) ---
df_biweekly = pd.DataFrame(
    {
        "date": pd.date_range("2020-01-05", periods=120, freq="2W-SUN"),
        "sales": np.arange(120, dtype=float),
    }
)

# --- Short series fixture (25 daily observations) ---
_n_obs_short = 25
_dates_short = pd.date_range("2023-01-01", periods=_n_obs_short, freq="D")

df_short = pd.DataFrame(
    {
        "date": _dates_short,
        "sales": np.arange(_n_obs_short, dtype=float) + 10.0,
    }
)

# --- Multi-series long format (2 series, 100 observations each) ---
_n_obs_per_series = 100
_dates_multi = pd.date_range("2023-01-01", periods=_n_obs_per_series, freq="D")

df_multi_long = pd.DataFrame(
    {
        "date": np.tile(_dates_multi, 2),
        "series_id": (
            ["store_a"] * _n_obs_per_series
            + ["store_b"] * _n_obs_per_series
        ),
        "value": np.concatenate([
            np.arange(_n_obs_per_series, dtype=float),
            np.arange(_n_obs_per_series, dtype=float) + 50.0,
        ]),
    }
)

# The long data with one series fewer, or one more, than `df_multi_long`
# (tests of data against a saved profile).
df_multi_long_one_series = df_multi_long[df_multi_long["series_id"] == "store_a"]
df_multi_long_three_series = pd.concat([
    df_multi_long,
    df_multi_long_one_series.assign(series_id="store_c"),
])

# The long data with the second series starting 60 days later (store_b from
# 2023-03-02, 40 observations); both end on 2023-04-10.
df_multi_long_staggered = pd.concat([
    df_multi_long[df_multi_long["series_id"] == "store_a"],
    df_multi_long[df_multi_long["series_id"] == "store_b"].iloc[60:],
])

# Long data whose series ids are numbers written as text, as store or SKU
# codes are: '001' and '1' are two series (one series 1 if read as integers),
# and '10' sorts before '2' as text. Three series of 100 days.
df_multi_long_numeric_ids = pd.DataFrame(
    {
        "date": np.tile(_dates_multi, 3),
        "series_id": np.repeat(["001", "1", "10"], _n_obs_per_series),
        "value": np.concatenate([
            10 + np.sin(np.arange(_n_obs_per_series) / 3),
            20 + 2 * np.cos(np.arange(_n_obs_per_series) / 4),
            30 + np.arange(_n_obs_per_series) % 7,
        ]),
    }
)

# The same data with the series ids as integers (1, 2 and 10), as a
# DataFrame may hold them.
df_multi_long_integer_ids = df_multi_long_numeric_ids.assign(
    series_id=df_multi_long_numeric_ids["series_id"].map({"001": 2, "1": 1, "10": 10})
)

# --- Multi-series wide format (2 series as columns) ---
df_multi_wide = pd.DataFrame(
    {
        "date": _dates,
        "series_a": np.arange(_n_obs, dtype=float),
        "series_b": np.arange(_n_obs, dtype=float) + 50.0,
    }
)

# --- Multi-series wide format, 300 observations pooled over 150 dates ---
# The pooled count reaches the threshold of the estimator rule (250), the
# 150 dates that ForecasterDirectMultiVariate trains on do not.
_n_obs_pooled = 150
_t_pooled = np.arange(_n_obs_pooled, dtype=float)
df_multi_wide_pooled = pd.DataFrame(
    {
        "date": pd.date_range("2023-01-01", periods=_n_obs_pooled, freq="D"),
        "series_a": 50.0 + 0.2 * _t_pooled + 5.0 * np.sin(2 * np.pi * _t_pooled / 7),
        "series_b": 80.0 + 0.1 * _t_pooled + 3.0 * np.cos(2 * np.pi * _t_pooled / 7),
    }
)

# --- Single series away from zero (MAPE is meaningful) ---
df_single_positive = df_single.assign(sales=df_single["sales"] + 1.0)

# --- Targets that cross zero (profits, temperatures, net flows) ---
# MAPE divides by the actual value: the default panel leaves it out. The
# wide frame has one series away from zero and one that crosses it.
_t_single = np.arange(_n_obs, dtype=float)
df_crossing_zero = pd.DataFrame(
    {
        "date": _dates,
        "profit": np.round(10.0 * np.sin(2 * np.pi * _t_single / 12), 2),
    }
)
df_multi_wide_crossing_zero = pd.DataFrame(
    {
        "date": _dates,
        "series_a": np.arange(_n_obs, dtype=float) + 50.0,
        "series_b": np.round(10.0 * np.sin(2 * np.pi * _t_single / 12), 2),
    }
)

# --- Data with missing values in target and exog ---
_target_with_nan = np.arange(_n_obs, dtype=float)
_target_with_nan[10] = np.nan
_target_with_nan[50] = np.nan
_exog_with_nan = _rng.normal(50, 10, _n_obs)
_exog_with_nan[20] = np.nan

df_with_missing = pd.DataFrame(
    {
        "date": _dates,
        "sales": _target_with_nan,
        "promo": _exog_with_nan,
    }
)

# --- Constant target (zero variance) ---
df_constant_target = pd.DataFrame(
    {
        "date": _dates,
        "sales": np.full(_n_obs, 42.0),
    }
)

# --- Single series as a named pandas Series with DatetimeIndex ---
series_single = pd.Series(
    np.arange(_n_obs, dtype=float),
    index=_dates,
    name="sales",
)

# --- Single series as an unnamed pandas Series with DatetimeIndex ---
series_unnamed = pd.Series(
    np.arange(_n_obs, dtype=float),
    index=_dates,
)

# --- Single series without a date column (RangeIndex, no frequency) ---
df_range_index = df_single.drop(columns=["date"]).reset_index(drop=True)

# --- Single series with irregular timestamps (no inferable frequency) ---
# Cumulative random minutes: the datetime index has no frequency.
_irregular_minutes = pd.Timestamp("2023-01-01") + pd.to_timedelta(
    np.cumsum(np.random.default_rng(1).integers(1, 60, 100)), unit="m"
)
df_irregular = pd.DataFrame(
    {"date": _irregular_minutes, "sales": np.arange(100, dtype=float)}
)

# --- Daily series written day first as text, 60 days ending 2021-01-31 ---
# The dates after the 12th ('13/12/2020') settle that they are day first. The
# 7 days to forecast (`df_day_first_exog`, '01/02/2021' to '07/02/2021') read
# both day first and month first, and pandas reads them month first.
df_day_first = pd.DataFrame(
    {
        "date": pd.date_range(end="2021-01-31", periods=60, freq="D").strftime(
            "%d/%m/%Y"
        ),
        "y": np.round(10 + 0.1 * np.arange(60) + 2 * np.sin(np.arange(60) / 3), 3),
        "promo": np.tile([0.0, 1.0], 30),
    }
)
df_day_first_exog = pd.DataFrame(
    {
        "date": [
            "01/02/2021", "02/02/2021", "03/02/2021", "04/02/2021", "05/02/2021",
            "06/02/2021", "07/02/2021",
        ],
        "promo": [0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0],
    }
)

# --- A year of daily sales of a shop closed on Sundays (312 days) ---
# No ten days are in a row: the frequency is 'D', inferred on windows of three
# days, with the 51 Sundays from 2023-01-02 to 2023-12-30 missing.
_dates_no_sundays = pd.date_range("2023-01-02", periods=364, freq="D")
_dates_no_sundays = _dates_no_sundays[_dates_no_sundays.dayofweek != 6]
df_no_sundays = pd.DataFrame(
    {
        "date": _dates_no_sundays,
        "sales": np.round(
            100 + 8 * _dates_no_sundays.dayofweek + 0.05 * np.arange(312)
            + 3 * np.sin(np.arange(312) / 5),
            2,
        ),
    }
)
# The same sales in long format, for two shops closed on Sundays.
df_no_sundays_long = pd.concat(
    [
        df_no_sundays.assign(shop="north"),
        df_no_sundays.assign(shop="south", sales=df_no_sundays["sales"] * 2),
    ],
    ignore_index=True,
)


def patch_agent(monkeypatch, assistant, *, output=None, error=None, capture=None):
    """
    Patch model resolution and the LLM agent factory used by `ask()`.

    Replaces `assistant._resolve_model` and
    `skforecast_ai.llm.agent.create_forecasting_agent` so the LLM path
    runs without network access. The fake agent records the message it
    receives into `capture["message"]` when a dict is provided, allowing
    context assertions to be made after the call returns instead of
    inside `run`, where the broad `except` in `ask()` would swallow them.

    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        The pytest monkeypatch fixture.
    assistant : ForecastingAssistant
        The assistant whose `_resolve_model` is patched.
    output : str, default None
        Value returned as the agent's `output` attribute.
    error : Exception, default None
        If provided, the agent raises this exception instead of returning.
    capture : dict, default None
        If provided, the message passed to `run` is stored under the
        "message" key.
    """
    import skforecast_ai.llm.agent as agent_mod

    def _mock_resolve_model(self_=None):
        return "fake-model-string"

    monkeypatch.setattr(assistant, "_resolve_model", _mock_resolve_model)

    class _FakeResult:
        def __init__(self, out):
            self.output = out

    def _mock_create_agent(*args, **kwargs):
        class _FakeAgent:
            async def run(self, msg, **kw):
                if capture is not None:
                    capture["message"] = msg
                if error is not None:
                    raise error
                return _FakeResult(output)

        return _FakeAgent()

    monkeypatch.setattr(agent_mod, "create_forecasting_agent", _mock_create_agent)


def patch_find_spec(monkeypatch, *, missing=(), installed=()):
    """
    Patch `importlib.util.find_spec`, which the checks of an installed
    estimator use, so a package is missing or installed whatever the
    environment has.

    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        The pytest monkeypatch fixture.
    missing : iterable of str, default ()
        Top-level modules taken as not installed (`'xgboost'`).
    installed : iterable of str, default ()
        Top-level modules taken as installed, without importing them.
    """
    import importlib.machinery
    import importlib.util

    find_spec = importlib.util.find_spec
    missing, installed = frozenset(missing), frozenset(installed)

    def _find_spec(name, *args, **kwargs):
        if name in missing:
            return None
        if name in installed:
            return importlib.machinery.ModuleSpec(name, None)
        return find_spec(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", _find_spec)


def make_comparison_result(assistant, *, with_failure=False):
    """
    Build a lightweight `ComparisonResult` without running backtests.

    Assembles two `BacktestResult` objects with hardcoded metrics so the
    leaderboard, ranking, and failure sections are deterministic and the
    fixture stays fast.

    Parameters
    ----------
    assistant : ForecastingAssistant
        Assistant used to build the shared profile and the candidate plans.
    with_failure : bool, default False
        Whether to include one failed candidate in `failures` and in the
        leaderboard's `'error'` column.

    Returns
    -------
    comparison : ComparisonResult
        Comparison with `'winner'` ranked first and `'runner_up'` second.
    """
    from skforecast_ai.schemas import (
        BacktestResult,
        CandidateFailure,
        ComparisonResult,
    )

    profile = assistant.profile(
        data=df_single, target="sales", date_column="date"
    )
    cv_config = {
        "steps": 5,
        "initial_train_size": 70,
        "refit": False,
        "fixed_train_size": True,
        "gap": 0,
        "n_folds": 6,
    }

    def _backtest(forecaster, estimator, mae, code):
        plan = assistant.plan(profile, steps=5, forecaster=forecaster,
                              estimator=estimator)
        return BacktestResult(
            profile     = profile,
            plan        = plan,
            cv_config   = cv_config,
            metrics     = pd.DataFrame({"MAE": [mae]}),
            predictions = pd.DataFrame({"pred": [1.0, 2.0, 3.0, 4.0, 5.0]}),
            code        = code,
            explanation = f"Backtest of {forecaster}.",
        )

    winner = _backtest(
        "ForecasterRecursive", "Ridge", 1.5, "# winner code"
    )
    runner_up = _backtest(
        "ForecasterDirect", "Ridge", 2.5, "# runner up code"
    )

    rows = [
        {
            "rank": 1,
            "name": "winner",
            "forecaster": "ForecasterRecursive",
            "estimator": "Ridge",
            "MAE": 1.5,
        },
        {
            "rank": 2,
            "name": "runner_up",
            "forecaster": "ForecasterDirect",
            "estimator": "Ridge",
            "MAE": 2.5,
        },
    ]
    failures = {}
    if with_failure:
        failures["broken"] = CandidateFailure(
            error_type     = "ImportError",
            message        = "No module named 'lightgbm'",
            traceback      = "Traceback (most recent call last):\n  SECRET_FRAME",
            generated_code = "# broken code",
        )
        for row in rows:
            row["error"] = None
        rows.append({
            "rank": 3,
            "name": "broken",
            "forecaster": "ForecasterRecursive",
            "estimator": "LGBMRegressor",
            "MAE": float("nan"),
            "error": "ImportError: No module named 'lightgbm'",
        })

    return ComparisonResult(
        profile        = profile,
        cv_config      = cv_config,
        results        = pd.DataFrame(rows),
        candidates     = {"winner": winner, "runner_up": runner_up},
        failures       = failures,
        ranking_metric = "MAE",
        explanation    = "Compared 2 configurations, ranked ascending by MAE.",
    )


def make_comparison_with_stats(assistant, comparison, stats_cv_config):
    """
    Replace the runner-up of a comparison with a ForecasterStats candidate.

    Parameters
    ----------
    assistant : ForecastingAssistant
        Assistant used to build the ForecasterStats plan.
    comparison : ComparisonResult
        Output of `make_comparison_result`.
    stats_cv_config : dict
        Strategy that ran for the ForecasterStats candidate.

    Returns
    -------
    comparison : ComparisonResult
        Copy of `comparison` whose `'runner_up'` is a ForecasterStats
        backtest with `stats_cv_config`.
    """
    stats = comparison.candidates["runner_up"].model_copy(
        update={
            "plan": assistant.plan(
                comparison.profile, steps=5, forecaster="ForecasterStats"
            ),
            "cv_config": stats_cv_config,
        }
    )
    candidates = {**comparison.candidates, "runner_up": stats}
    return comparison.model_copy(update={"candidates": candidates})
