# Unit test ExplainableResult contract skforecast_ai.schemas.results

import re

import numpy as np
import pandas as pd
import pytest

from skforecast_ai import schemas
from skforecast_ai._constants import OLLAMA_MAX_CONTEXT_TOKENS
from skforecast_ai.llm.skills import estimate_context_tokens
from skforecast_ai.schemas import (
    ExplainableResult,
    ForecastingProfile,
    ForecastPlan,
    LLMContext,
)

from tests.fixtures_llm import (
    ROW_LEVEL_MARKER,
    make_backtest_result,
    make_comparison_result,
    make_forecast_result,
    make_single_run_result,
    predictions_single,
    profile_single,
)

# Every concrete `ExplainableResult` needs an entry here. The discovery
# test below fails when a new result type is added without one, so the
# contract covers result types that do not exist yet.
RESULT_BUILDERS = {
    "SingleRunResult": make_single_run_result,
    "ForecastResult":  make_forecast_result,
    "BacktestResult":  make_backtest_result,
    "ComparisonResult": make_comparison_result,
}

# Results that carry row-level predictions and therefore have to honour
# `send_data`. A comparison renders aggregated leaderboard metrics only,
# so the flag has nothing to gate there.
#
# All three use the short prediction frame on purpose: with a frame above
# the truncation threshold an interior value is legitimately absent, which
# would make the privacy assertion pass for the wrong reason.
ROW_LEVEL_BUILDERS = {
    "SingleRunResult": make_single_run_result,
    "ForecastResult":  make_forecast_result,
    "BacktestResult":  lambda: make_backtest_result(
                           predictions=predictions_single
                       ),
}

KNOWN_TAGS = {
    "forecast_context",
    "dataset",
    "profile_decision",
    "forecast_plan",
    "cross_validation",
    "deterministic_summary",
    "evaluation_metrics",
    "predictions",
    "comparison_overview",
    "leaderboard",
    "failed_candidates",
    "winning_candidate",
}


def _walk_tags(text):
    """
    Return the tag names found in `text` and the names left unclosed.

    Parameters
    ----------
    text : str
        Rendered context block.

    Returns
    -------
    seen : set
        Every tag name encountered.
    unbalanced : list
        Names that were opened and never closed, or closed without a
        matching open tag.
    """

    seen = set()
    stack = []
    unbalanced = []
    for closing, name in re.findall(r"<(/?)([a-z_]+)>", text):
        seen.add(name)
        if closing:
            if stack and stack[-1] == name:
                stack.pop()
            else:
                unbalanced.append(name)
        else:
            stack.append(name)

    return seen, unbalanced + stack


# =============================================================================
# Tests: every result type is covered
# =============================================================================
def test_every_explainable_result_is_covered_by_a_builder():
    """
    Test that every concrete `ExplainableResult` exported by the schemas
    package has a fixture builder. Discovering the subclasses by
    introspection instead of listing them means a new result type is
    covered by the whole contract on the day it is added.
    """
    discovered = {
        name for name, obj in vars(schemas).items()
        if isinstance(obj, type)
        and issubclass(obj, ExplainableResult)
        and obj is not ExplainableResult
    }

    assert discovered == set(RESULT_BUILDERS)


# =============================================================================
# Tests: shape of the returned context
# =============================================================================
@pytest.mark.parametrize(
    "name",
    sorted(RESULT_BUILDERS),
    ids=lambda dt: f"result: {dt}"
)
def test_to_llm_context_returns_populated_context(name):
    """
    Test that every result renders a non-empty context block and echoes
    back the artifacts `ask()` reports on its `AskResult`. An empty
    payload would let `ask()` answer from the question alone.
    """
    context = RESULT_BUILDERS[name]().to_llm_context(send_data=True)

    assert isinstance(context, LLMContext)
    assert context.text.strip()
    assert isinstance(context.profile, ForecastingProfile)
    assert isinstance(context.plan, ForecastPlan)
    assert isinstance(context.code, str)


@pytest.mark.parametrize(
    "name",
    sorted(RESULT_BUILDERS),
    ids=lambda dt: f"result: {dt}"
)
@pytest.mark.parametrize(
    "send_data",
    [True, False],
    ids=lambda dt: f"send_data: {dt}"
)
def test_to_llm_context_tags_are_balanced_and_known(name, send_data):
    """
    Test that every result emits a single balanced `<forecast_context>`
    block built only from the documented tag vocabulary. An unknown tag
    would not be described by the static role prompt, leaving the model
    to guess whether its content is authoritative.
    """
    text = RESULT_BUILDERS[name]().to_llm_context(send_data=send_data).text
    seen, unbalanced = _walk_tags(text)

    assert unbalanced == []
    assert seen <= KNOWN_TAGS
    assert text.startswith("<forecast_context>")
    assert text.endswith("</forecast_context>")
    assert text.count("<forecast_context>") == 1


# =============================================================================
# Tests: send_data gates row-level values
# =============================================================================
@pytest.mark.parametrize(
    "name",
    sorted(ROW_LEVEL_BUILDERS),
    ids=lambda dt: f"result: {dt}"
)
def test_to_llm_context_withholds_row_level_values_when_send_data_is_False(name):
    """
    Test that no row-level prediction value reaches the context when
    `send_data` is False. The marker is an interior value of the `pred`
    column, so it is neither the minimum, the maximum, nor the mean, and
    can only appear through a row-level rendering.
    """
    context = ROW_LEVEL_BUILDERS[name]().to_llm_context(send_data=False)

    assert ROW_LEVEL_MARKER not in context.text


@pytest.mark.parametrize(
    "name",
    sorted(ROW_LEVEL_BUILDERS),
    ids=lambda dt: f"result: {dt}"
)
def test_to_llm_context_includes_row_level_values_when_send_data_is_True(name):
    """
    Test that row-level prediction values do reach the context when
    `send_data` is True, so the privacy test above cannot pass because
    the values were never rendered in the first place.
    """
    context = ROW_LEVEL_BUILDERS[name]().to_llm_context(send_data=True)

    assert ROW_LEVEL_MARKER in context.text


def test_to_llm_context_ignores_send_data_for_a_comparison():
    """
    Test that a comparison renders the same context either way. It holds
    aggregated leaderboard metrics only, so the flag has nothing to gate
    and must not change the payload.
    """
    result = make_comparison_result()

    assert (
        result.to_llm_context(send_data=True).text
        == result.to_llm_context(send_data=False).text
    )


# =============================================================================
# Tests: the context stays bounded as the inputs grow
# =============================================================================
def _large_forecast_result():
    """Build a forecast whose predictions are far above the row cap."""
    return make_forecast_result(
        predictions=pd.DataFrame(
            {
                "pred":        np.arange(5000, dtype=float),
                "lower_bound": np.arange(5000, dtype=float) - 10.0,
                "upper_bound": np.arange(5000, dtype=float) + 10.0,
            },
            index=pd.date_range("2023-04-11", periods=5000, freq="D"),
        )
    )


@pytest.mark.parametrize(
    "build_result",
    [
        _large_forecast_result,
        lambda: make_comparison_result(n_candidates=50),
    ],
    ids=["large predictions", "50 candidates"]
)
def test_to_llm_context_stays_bounded_for_large_inputs(build_result):
    """
    Test that neither a long prediction frame nor a wide comparison can
    crowd the prompt out of the context window. The context has to leave
    room for the role prompt, the loaded skills, and the response, so it
    is held to well under half the window.
    """
    context = build_result().to_llm_context(send_data=True)

    assert estimate_context_tokens(context.text) < OLLAMA_MAX_CONTEXT_TOKENS // 2


def test_to_llm_context_does_not_modify_the_result():
    """
    Test that rendering leaves the result untouched. `ask()` may render
    the same result more than once, and a renderer that sorted or
    truncated in place would silently corrupt the object the user holds.
    """
    predictions = predictions_single.copy()
    result = make_forecast_result(predictions=predictions)

    result.to_llm_context(send_data=True)
    result.to_llm_context(send_data=False)

    pd.testing.assert_frame_equal(predictions, predictions_single)
    assert result.profile is profile_single
