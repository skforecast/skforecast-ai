---
paths:
  - "tests/**"
---

# Tests

Before writing or changing a test, read
`.github/instructions/testing.instructions.md` (shared with skforecast; its
examples use skforecast forecasters but the structure, naming, fixtures and
assertion rules apply here unchanged) and the "Testing" section of
`AGENTS.md`.

Specific to skforecast-ai:

- Fixtures live in `tests/fixtures_<module>.py` as module-level variables;
  reuse them before creating new data.
- LLM calls are always mocked with `patch_agent` from
  `tests/fixtures_assistant.py`. Never reach a real provider.
- Generated scripts are compared byte for byte in `tests/tests_rendering/`;
  a rendering change updates those expected strings on purpose, never by
  loosening the assertion.
- LLM context goldens in `tests/tests_llm/golden/` are regenerated with
  `python tools/ai/update_golden_contexts.py` only when the change is
  intentional; review the diff (see `/llm-context-change`).
- Warnings are errors. Wrap expected warnings in `pytest.warns`; a third
  party warning gets a targeted `ignore` in `pyproject.toml` with its reason.
- Run the file you touched first, then the full suite through `/verify`.
