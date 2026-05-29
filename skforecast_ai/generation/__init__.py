"""Code generation: produce executable forecasting scripts."""

from .single_series import _template_single_series
from .multi_series import _template_multi_series, _template_multivariate
from .statistical import _template_statistical
from .foundation import _template_foundation

__all__ = [
    "_template_single_series",
    "_template_multi_series",
    "_template_multivariate",
    "_template_statistical",
    "_template_foundation",
]
