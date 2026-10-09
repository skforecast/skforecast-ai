# Unit test build_metric_override_explanation

from skforecast_ai.recommendation import build_metric_override_explanation


def test_build_metric_override_explanation_output_when_one_metric():
    """
    Test the sentence of a single metric chosen by the user.
    """
    explanation = build_metric_override_explanation(["mean_squared_error"])

    assert explanation == "Metric: mean_squared_error, as requested."


def test_build_metric_override_explanation_output_when_several_metrics():
    """
    Test that with several metrics the first one is named as primary and
    the others as also computed, in the order given.
    """
    explanation = build_metric_override_explanation(
        ["median_absolute_error", "mean_absolute_error", "mean_squared_error"]
    )

    assert explanation == (
        "Primary metric: median_absolute_error, as requested; also computed: "
        "mean_absolute_error, mean_squared_error."
    )
