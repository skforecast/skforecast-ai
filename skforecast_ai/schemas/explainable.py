################################################################################
#                            Explainable protocol                              #
#                                                                              #
# Capability shared by every object that ask() can explain                     #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .results import LLMContext


class ExplainableResult:
    """
    Capability shared by every result that can describe itself to an LLM.

    Mirrors `DisplayMixin`, which lets a result describe itself to a
    terminal. Subclasses must implement `_build_llm_context`, returning
    the context block plus the artifacts `ask()` echoes back on its
    `AskResult`.

    Each result decides its own payload, so an aggregate result (for
    example `ComparisonResult`) can send a compact summary instead of the
    concatenated payloads of everything it wraps.
    """

    def _build_llm_context(
        self, *, send_data: bool
    ) -> LLMContext:  # pragma: no cover - overridden by subclasses
        raise NotImplementedError(
            f"{type(self).__name__} must implement _build_llm_context"
        )

    def to_llm_context(self, *, send_data: bool = False) -> LLMContext:
        """
        Build the LLM context for this result.

        Parameters
        ----------
        send_data : bool, default False
            Whether raw data values may be included. When False, only
            aggregate statistics are shown for row-level data. The
            decision belongs to the caller, so the privacy policy stays
            owned by `ForecastingAssistant`.

        Returns
        -------
        context : LLMContext
            Rendered context block plus the artifacts `ask()` echoes back.
        """

        return self._build_llm_context(send_data=send_data)
