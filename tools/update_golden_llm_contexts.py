#!/usr/bin/env python3
"""
Regenerate the golden LLM context files under `tests/tests_llm/golden/`.

REQUIRED TOOLING. This is not a throwaway development aid: the golden
files are regenerated every time a change legitimately alters the payload
sent to the LLM, so this script is the only supported way to update them.
Do not delete it.

Why the goldens exist
---------------------
The rendered context string is the entire contract between the
deterministic code and the LLM. It is assembled from a dozen section
renderers plus the profiler's and planner's own wording, so a change
anywhere in that chain silently changes what the model is told. A
substring assertion cannot catch a section that stops being rendered; a
full-text comparison can.

Workflow
--------
1. Change a section renderer, a profiler message, or a plan explanation.
2. `tests/tests_llm/test_golden_context.py` fails and prints the exact
   diff of the prompt.
3. If the change was intended, run this script and review the resulting
   diff to the `.txt` files in the pull request.
4. If it was not intended, an accidental prompt regression was caught.

There is deliberately no `--check` mode, unlike the other scripts in this
directory. The test suite already is the check, and a second
implementation of it would be one more thing to keep in sync.

Usage
-----
    python tools/update_golden_llm_contexts.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tests.fixtures_llm import GOLDEN_SCENARIOS  # noqa: E402

GOLDEN_DIR = REPO_ROOT / "tests" / "tests_llm" / "golden"


def main() -> None:
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)

    for scenario, build_result in GOLDEN_SCENARIOS.items():
        context = build_result().to_llm_context(send_data=True)
        path = GOLDEN_DIR / f"{scenario}.txt"
        path.write_text(context.text + "\n", encoding="utf-8")
        print(f"  {path.relative_to(REPO_ROOT)}  ({len(context.text):,} chars)")

    print(f"\nWrote {len(GOLDEN_SCENARIOS)} golden files.")
    print("Review the diff before committing: it is the prompt diff.")


if __name__ == "__main__":
    main()
