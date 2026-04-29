"""skforecast-ai: AI-powered forecasting assistant built on skforecast."""

__version__ = "0.1.0"

from .schemas import DataProfile, ForecastPlan
from .recommendation import recommend_plan
from .generation import generate_code

__all__ = [
    "DataProfile",
    "ForecastPlan",
    "generate_code",
    "recommend_plan",
    "__version__",
]
