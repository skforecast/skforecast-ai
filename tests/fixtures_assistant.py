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

# --- Single series without exog (100 daily observations) ---
df_no_exog = pd.DataFrame(
    {
        "date": _dates,
        "sales": np.arange(_n_obs, dtype=float),
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

# --- Multi-series wide format (2 series as columns) ---
df_multi_wide = pd.DataFrame(
    {
        "date": _dates,
        "series_a": np.arange(_n_obs, dtype=float),
        "series_b": np.arange(_n_obs, dtype=float) + 50.0,
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
