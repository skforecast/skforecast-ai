# AI tools

Scripts that maintain what skforecast-ai sends to the LLM. Run them from the
repository root.

## Assets synced from skforecast

The skills (`skforecast_ai/skills/`) and the base reference
(`skforecast_ai/resources/llms-base.txt`) are copied from the skforecast
repository and never edited here.

| Path | Purpose |
|:-----|:--------|
| `sync_skforecast_assets.py` | Downloads the skills and `llms-base.txt` from a skforecast branch or tag, then rewrites the token estimates in `skforecast_ai/llm/skills.py`. `--check` compares them without writing; `--inventory` prints the local skill table. |
| `measure_skill_tokens.py` | Estimates the tokens of each skill and of `llms-base.txt`. `--update` rewrites the constants in `skforecast_ai/llm/skills.py` (the sync already does it); `--check` and `--report` are used by CI. |

The workflow `.github/workflows/ai-context-check.yml` runs both in `--check`
mode.

## Context built by the `llm` module

| Path | Purpose |
|:-----|:--------|
| `update_golden_contexts.py` | Regenerates the golden LLM contexts in `tests/tests_llm/golden/`. Run it only after an intentional change, and review the diff. |
| `check_ask_context.py` | Sends what `ForecastingAssistant.ask()` builds to a real model and writes a Markdown report. `--dry-run` prints the contexts without calling the LLM. |
| [`ask_context_reports/`](ask_context_reports/) | One reviewed `check_ask_context.py` report per release and dataset. See its README. |
