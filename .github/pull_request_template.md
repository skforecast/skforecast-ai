## Description

<!-- What does this PR change and why? Link the related issue, for example "Closes #123". -->

## How was this tested?

<!-- Commands you ran, new tests, or screenshots for documentation and UI changes. -->

## Checklist

<!-- Strike through the items that do not apply, for example ~~item~~. -->

- [ ] The PR targets the current release branch (for example `0.4.x`), not `main`.
- [ ] I have read and agree to the [Contributor License Agreement](https://github.com/skforecast/skforecast-ai/blob/main/CONTRIBUTOR_LICENSE_AGREEMENT.md).
- [ ] `ruff check skforecast_ai tests` is clean.
- [ ] Tests are added or updated, and `pytest -n auto` passes locally.
- [ ] Public functions and classes have type hints and NumPy-style docstrings.
- [ ] No en dashes or em dashes in code, docstrings, messages or docs.
- [ ] If generated scripts or LLM contexts changed, the goldens were regenerated on purpose and the diff reviewed.
- [ ] Files synced from skforecast (`skforecast_ai/skills/`, `skforecast_ai/resources/llms-base.txt`) were not edited by hand.
- [ ] User-facing changes are described in [`docs/releases/releases.md`](https://github.com/skforecast/skforecast-ai/blob/main/docs/releases/releases.md).
- [ ] If the documentation changed, `PYTHONPATH=. mkdocs build` runs without new warnings.

<!-- Changes to `llm/prompts.py`, `llm/context.py` or the rendered explanations need an `check_ask_context.py` run against a real model before the release. A maintainer runs it; mention it here if it applies. -->
