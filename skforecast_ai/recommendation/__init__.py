"""Recommendation engine: deterministic rule-based forecasting plans."""

from .forecaster_selection import recommend_plan, select_forecaster_type

__all__ = ["recommend_plan", "select_forecaster_type"]
