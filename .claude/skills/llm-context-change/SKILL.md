---
name: llm-context-change
description: Checklist after changing what the LLM receives (skforecast_ai/llm/context.py, llm/prompts.py, the rendered explanations in recommendation/explanation.py, execution/backtesting_runner.py or execution/comparison.py). Regenerates and reviews the golden contexts and prepares the real-model check that the user launches.
---

# LLM context change

1. Run the golden test to see what changed:
   `PY -m pytest tests/tests_llm/test_golden_context.py -q`
   (`PY` as in `/verify`).
2. If the difference is intended, regenerate:
   `PY tools/ai/update_golden_contexts.py`
3. Review `git diff tests/tests_llm/golden/` and summarize it for the user:
   what the model now sees that it did not, and what it no longer sees.
   Check that no raw dataset values leaked into a context (privacy by
   default); only summary statistics and values owned by a result are
   allowed.
4. Build the contexts without calling a model:
   `PY tools/ai/check_ask_context.py --dry-run`
   and skim the report for truncation or empty sections.
5. Check the token budget tests: `PY -m pytest tests/tests_llm -q`.
6. Tell the user that this change needs a real-model run of
   `tools/ai/check_ask_context.py` before the release. It costs money, so
   the user launches it (a hook blocks it without `--dry-run`); the reviewed
   report is kept as described in `tools/ai/ask_context_reports/README.md`.
7. If the answers of `ask()` change in a way a user notices, add a release
   note with `/release-note`.
