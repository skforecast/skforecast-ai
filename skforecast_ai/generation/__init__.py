"""Code generation: produce executable forecasting scripts."""

from .code_templates import _TEMPLATE_DISPATCH, generate_template

__all__ = [
    "_TEMPLATE_DISPATCH",
    "generate_template",
]
