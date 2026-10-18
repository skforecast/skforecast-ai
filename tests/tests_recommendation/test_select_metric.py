# Unit test select_metric
"""Tests for the select_metric recommendation function."""


from skforecast_ai.recommendation.metric_selection import select_metric
from skforecast_ai.schemas import DataProfile


# --- Fixtures ---

profile_single_no_zeros = DataProfile(
    n_series       = 1,
    series_lengths = {"y": 365},
    target         = "y",
    index_type     = "datetime",
    frequency      = "D",
    target_stats   = {"y": {"min": 5.2, "max": 100.0, "mean": 50.0, "std": 10.0}},
)

profile_single_with_zeros = DataProfile(
    n_series       = 1,
    series_lengths = {"y": 365},
    target         = "y",
    index_type     = "datetime",
    frequency      = "D",
    target_stats   = {"y": {"min": 0.0, "max": 100.0, "mean": 50.0, "std": 10.0}},
)

profile_single_near_zero = DataProfile(
    n_series       = 1,
    series_lengths = {"y": 365},
    target         = "y",
    index_type     = "datetime",
    frequency      = "D",
    target_stats   = {"y": {"min": 0.005, "max": 100.0, "mean": 50.0, "std": 10.0}},
)

profile_multi_series = DataProfile(
    n_series       = 3,
    series_lengths = {"value": 300},
    target         = "value",
    index_type     = "datetime",
    frequency      = "D",
    target_stats   = {
        "series_1": {"min": 10.0, "max": 200.0, "mean": 100.0, "std": 30.0},
        "series_2": {"min": 5.0, "max": 50.0, "mean": 25.0, "std": 8.0},
        "series_3": {"min": 1.0, "max": 500.0, "mean": 200.0, "std": 80.0},
    },
)

profile_single_crossing_zero = DataProfile(
    n_series       = 1,
    series_lengths = {"y": 365},
    target         = "y",
    index_type     = "datetime",
    frequency      = "D",
    target_stats   = {"y": {"min": -10.0, "max": 10.0, "mean": 0.0, "std": 7.3}},
)

profile_single_negative = DataProfile(
    n_series       = 1,
    series_lengths = {"y": 365},
    target         = "y",
    index_type     = "datetime",
    frequency      = "D",
    target_stats   = {"y": {"min": -80.0, "max": -2.5, "mean": -40.0, "std": 9.0}},
)

profile_multi_series_crossing_zero = DataProfile(
    n_series       = 2,
    series_lengths = {"series_1": 300, "series_2": 300},
    target         = "value",
    index_type     = "datetime",
    frequency      = "D",
    target_stats   = {
        "series_1": {"min": 10.0, "max": 200.0, "mean": 100.0, "std": 30.0},
        "series_2": {"min": -5.0, "max": 50.0, "mean": 25.0, "std": 8.0},
    },
)

profile_multi_series_with_zeros = DataProfile(
    n_series       = 2,
    series_lengths = {"value": 300},
    target         = "value",
    index_type     = "datetime",
    frequency      = "D",
    target_stats   = {
        "series_1": {"min": 0.0, "max": 200.0, "mean": 100.0, "std": 30.0},
        "series_2": {"min": 5.0, "max": 50.0, "mean": 25.0, "std": 8.0},
    },
)

profile_no_stats = DataProfile(
    n_series       = 1,
    series_lengths = {"y": 100},
    target         = "y",
    index_type     = "datetime",
    frequency      = "D",
    target_stats   = {},
)


# --- Tests for select_metric ---

class TestSelectMetricSingleSeries:
    """Tests for single-series metric selection."""

    def test_general_single_series_returns_mae(self):
        """
        Test that a general single-series task returns MAE as primary metric.
        """
        metric, explanation, metrics = select_metric(profile_single_no_zeros)
        assert metric == "mean_absolute_error"
        assert "MAE" in explanation
        assert "mean_absolute_error" in metrics

    def test_single_series_with_zeros_excludes_mape(self):
        """
        Test that when target has zeros, MAPE is excluded from metrics_to_compute.
        """
        metric, _, metrics = select_metric(profile_single_with_zeros)
        assert metric == "mean_absolute_error"
        assert "mean_absolute_percentage_error" not in metrics

    def test_single_series_near_zero_excludes_mape(self):
        """
        Test that near-zero values (abs(min) <= 0.01) exclude MAPE.
        """
        _, _, metrics = select_metric(profile_single_near_zero)
        assert "mean_absolute_percentage_error" not in metrics

    def test_single_series_crossing_zero_excludes_mape(self):
        """
        Test that a target that crosses zero (negative minimum, positive
        maximum) excludes MAPE, which the minimum alone did not see.
        """
        metric, _, metrics = select_metric(profile_single_crossing_zero)
        assert metric == "mean_absolute_error"
        assert metrics == [
            "mean_absolute_error",
            "mean_squared_error",
            "mean_absolute_scaled_error",
        ]

    def test_single_series_negative_includes_mape(self):
        """
        Test that a target with only negative values, away from zero, keeps
        MAPE: no actual value is near zero.
        """
        _, _, metrics = select_metric(profile_single_negative)
        assert "mean_absolute_percentage_error" in metrics

    def test_single_series_no_zeros_includes_mape(self):
        """
        Test that a positive target away from zero keeps the whole default
        panel, MAPE included.
        """
        _, _, metrics = select_metric(profile_single_no_zeros)
        assert metrics == [
            "mean_absolute_error",
            "mean_squared_error",
            "mean_absolute_scaled_error",
            "mean_absolute_percentage_error",
        ]

    def test_single_series_always_includes_core_metrics(self):
        """
        Test that MAE, MSE, and MASE are always included for regression tasks.
        """
        _, _, metrics = select_metric(profile_single_no_zeros)
        assert "mean_absolute_error" in metrics
        assert "mean_squared_error" in metrics
        assert "mean_absolute_scaled_error" in metrics


class TestSelectMetricMultiSeries:
    """Tests for multi-series metric selection."""

    def test_multi_series_returns_mase(self):
        """
        Test that multi-series tasks return MASE as primary metric.
        """
        metric, explanation, metrics = select_metric(profile_multi_series)
        assert metric == "mean_absolute_scaled_error"
        assert "scale-independent" in explanation

    def test_multi_series_with_zeros_excludes_mape(self):
        """
        Test that multi-series with zeros excludes MAPE.
        """
        _, _, metrics = select_metric(profile_multi_series_with_zeros)
        assert "mean_absolute_percentage_error" not in metrics

    def test_multi_series_one_crossing_zero_excludes_mape(self):
        """
        Test that one series crossing zero excludes MAPE for the whole panel,
        even when the other series are positive.
        """
        metric, _, metrics = select_metric(profile_multi_series_crossing_zero)
        assert metric == "mean_absolute_scaled_error"
        assert metrics == [
            "mean_absolute_error",
            "mean_squared_error",
            "mean_absolute_scaled_error",
        ]

    def test_multi_series_no_zeros_includes_mape(self):
        """
        Test that multi-series without zeros includes MAPE.
        """
        _, _, metrics = select_metric(profile_multi_series)
        assert "mean_absolute_percentage_error" in metrics


class TestSelectMetricNoStats:
    """Tests when target_stats is empty."""

    def test_empty_target_stats_no_mape_exclusion(self):
        """
        Test that empty target_stats does not trigger zero detection
        (defaults to no zeros detected, MAPE included).
        """
        _, _, metrics = select_metric(profile_no_stats)
        assert "mean_absolute_percentage_error" in metrics
