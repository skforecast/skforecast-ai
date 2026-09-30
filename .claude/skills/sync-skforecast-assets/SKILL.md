---
name: sync-skforecast-assets
description: Sync the skills and llms-base.txt from the skforecast repository and update the files maintained by hand when the skill inventory changes.
disable-model-invocation: true
argument-hint: "[branch or tag, default: the script default]"
---

# Sync skforecast assets

`skforecast_ai/skills/` and `skforecast_ai/resources/llms-base.txt` are
denied for Edit and Write; they change only through this script. It needs
network access to GitHub.

1. `git status --short` must show no changes under `skforecast_ai/skills/`
   or `skforecast_ai/resources/`.
2. Run `PY tools/ai/sync_skforecast_assets.py` (add `--branch $ARGUMENTS`
   when an argument was given). `PY` as in `/verify`.
3. Read the report: skills added, removed, renamed or with a new
   description. If there are none, go to step 5.
4. Update the files maintained by hand:
   - `skforecast_ai/llm/skills.py`: `ALL_SKILLS` and the routing tables.
   - Token estimates: `PY tools/ai/measure_skill_tokens.py --update`.
   - The table in `docs/user-guides/skills.md`
     (`tests/test_docs_skills_page.py` checks it against `ALL_SKILLS`).
   - The upstream order test in `tests/tests_llm/test_select_skills.py`.
5. `PY tools/ai/measure_skill_tokens.py --check`, then `/verify`.
6. Skills are part of what `ask()` sends to the model: remind the user that
   a real-model `check_ask_context.py` run is due before the release (see
   `/llm-context-change`).
