# Unit test build_foundation_explanation
"""Tests for the build_foundation_explanation recommendation function."""

import dataclasses
import pytest
from skforecast.foundation import get_model_info

from skforecast_ai.recommendation import build_foundation_explanation


@pytest.mark.parametrize(
    "n_observations, n_series, expected",
    [
        (
            100,
            1,
            "The model reads up to 8192 observations of the series as context, "
            "so the whole history is used (the series has 100).",
        ),
        (
            10000,
            1,
            "The model reads the last 8192 observations of the series as "
            "context; the series has 10000, so older observations are not used.",
        ),
        (
            10000,
            3,
            "The model reads the last 8192 observations of each series as "
            "context; the longest series has 10000, so older observations are "
            "not used.",
        ),
    ],
    ids=lambda dt: f"n_observations, n_series, expected: {dt}",
)
def test_build_foundation_explanation_output_when_only_context_to_explain(
    n_observations, n_series, expected
):
    """
    Test that, for a model that accepts covariates, has no registered license
    restriction and is not gated, the explanation only states how much of the
    history the model reads as context.
    """
    explanation = build_foundation_explanation(
        foundation_model = get_model_info("autogluon/chronos-2-small"),
        exog_columns     = ["promo"],
        context_length   = 8192,
        n_observations   = n_observations,
        n_series         = n_series,
    )

    assert explanation == expected


def test_build_foundation_explanation_output_when_model_without_covariates():
    """
    Test that the explanation states that the exogenous variables are not
    used by a model without covariate support, and the license restriction
    of its weights.
    """
    explanation = build_foundation_explanation(
        foundation_model = get_model_info("Salesforce/moirai-2.0-R-small"),
        exog_columns     = ["promo", "price"],
        context_length   = 2048,
        n_observations   = 100,
        n_series         = 1,
    )

    assert explanation == (
        "The model reads up to 2048 observations of the series as context, so "
        "the whole history is used (the series has 100). "
        "Exogenous variables ['promo', 'price'] are not used: "
        "'Salesforce/moirai-2.0-R-small' does not support covariates. "
        "The weights of 'Salesforce/moirai-2.0-R-small' are released under "
        "CC-BY-NC-4.0, which restricts commercial use "
        "(https://huggingface.co/Salesforce/moirai-2.0-R-small)."
    )


def test_build_foundation_explanation_output_when_model_is_gated():
    """
    Test that the explanation states that the weights of a gated model need
    an authenticated Hugging Face account, and says nothing about the exog
    of a model that accepts covariates. No adapter of skforecast 0.26 is
    gated, so the information of t0 is marked as gated.
    """
    info = dataclasses.replace(
        get_model_info("theforecastingcompany/t0-alpha"), requires_hf_auth=True
    )
    explanation = build_foundation_explanation(
        foundation_model = info,
        exog_columns     = ["promo"],
        context_length   = 8192,
        n_observations   = 100,
        n_series         = 1,
    )

    assert explanation == (
        "The model reads up to 8192 observations of the series as context, so "
        "the whole history is used (the series has 100). "
        "The weights of 'theforecastingcompany/t0-alpha' are gated on the "
        "Hugging Face Hub: log in with an account that has accepted the model "
        "license before running the script."
    )


def test_build_foundation_explanation_output_when_t0_is_not_gated():
    """
    Test that t0, whose weights skforecast no longer registers as gated and
    whose license does not restrict commercial use, only gets the sentence
    about the context.
    """
    explanation = build_foundation_explanation(
        foundation_model = get_model_info("theforecastingcompany/t0-alpha"),
        exog_columns     = ["promo"],
        context_length   = 8192,
        n_observations   = 100,
        n_series         = 1,
    )

    assert explanation == (
        "The model reads up to 8192 observations of the series as context, so "
        "the whole history is used (the series has 100)."
    )


def test_build_foundation_explanation_output_when_provider_requires_account():
    """
    Test that the explanation of TabPFN states its license, which restricts
    commercial use, and that its provider requires its own account.
    """
    explanation = build_foundation_explanation(
        foundation_model = get_model_info("priorlabs/tabpfn-ts"),
        exog_columns     = ["promo"],
        context_length   = 4096,
        n_observations   = 100,
        n_series         = 1,
    )

    assert explanation == (
        "The model reads up to 4096 observations of the series as context, so "
        "the whole history is used (the series has 100). "
        "The weights of 'priorlabs/tabpfn-ts' are released under "
        "tabpfn-3-5-license-v1.0, which restricts commercial use "
        "(https://huggingface.co/Prior-Labs/tabpfn_3_5/blob/main/LICENSE). "
        "The provider of 'priorlabs/tabpfn-ts' requires its own account and "
        "accepting its license, outside the Hugging Face Hub, before running "
        "the script."
    )
