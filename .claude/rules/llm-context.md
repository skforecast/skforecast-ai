---
paths:
  - "skforecast_ai/llm/**"
  - "tests/tests_llm/**"
  - "skforecast_ai/recommendation/explanation.py"
  - "skforecast_ai/execution/backtesting_runner.py"
  - "skforecast_ai/execution/comparison.py"
---

# LLM layer

- The LLM explains, it never decides. Anything it returns is validated by a
  Pydantic model before it reaches execution, and every path that can fall
  back to a deterministic result must do so with a warning, not silently.
- Datasets never reach the LLM: contexts carry summary statistics only.
  Values owned by a result (predictions, metrics) are the exception, and
  `ask()` warns with `DataSentToLLMWarning` when `send_data_to_llm=False`.
- pydantic-ai is imported inside functions only;
  `tests/test_import_without_llm_extra.py` fails otherwise.
- A change to `llm/context.py`, `llm/prompts.py` or the rendered
  explanations changes the goldens and needs a real-model run before the
  release. Follow `/llm-context-change`; the real run costs money and is
  launched by the user (a hook blocks it without `--dry-run`).
- A new `ExplainableResult` needs a builder in `tests/fixtures_llm.py`.
