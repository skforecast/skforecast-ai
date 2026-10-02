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
        self, *, send_data: bool, for_describe: bool = False
    ) -> LLMContext:  # pragma: no cover - overridden by subclasses
        raise NotImplementedError(
            f"{type(self).__name__} must implement _build_llm_context"
        )

    def describe(self) -> str:
        """
        Describe the result in plain text.

        The text is the one `ask()` sends to the LLM about this result when
        `send_data_to_llm=False`, without the sentences that only tell the
        LLM how to answer. It is deterministic and needs no LLM, so it can
        be shown to a user or passed to an agent as it is. A plan is
        described through the script rendered from it:
        `assistant.forecast_code(profile=profile, plan=plan).describe()`.

        Returns
        -------
        description : str
            Sections wrapped in XML-style tags (`<dataset>`,
            `<forecast_plan>`, ...), the same ones `ask()` sends.

        Notes
        -----
        It never includes values row by row: predictions are summarized
        by their shape, columns, minimum, maximum, mean and standard
        deviation, and metrics are included as computed. Two limitations,
        shared with the context of `ask()`:

        - The summary of the predictions is computed over all their rows:
        with several series it pools them, and the `fold` column of a
        backtest is summarized like the other numeric columns.
        - For a result of `backtest_code()`, the `<script>` section
        describes the script as the one of the plan in prediction mode
        (it trains on all the data and computes no metrics), although the
        script backtests the plan.
        """

        return self._build_llm_context(send_data=False, for_describe=True).text

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
