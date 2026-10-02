---
name: release-note
description: Add or update the entry for a user-visible change in docs/releases/releases.md under the version in development. Use when a change affects the public API, CLI output, generated scripts or warnings.
---

# Release note

The changelog is read by package users and compares one release with the
previous one. An entry says what changed for them, whether it affects them
and, if they must act, what to do. Maintainer detail (paths under `tools/`,
refactors, internal constants, build configuration) stays in the diff;
internal changes get no entry, or one short line when they have a visible
effect.

## Shape of an entry

- The first sentence says what changed and stands on its own: a reader who
  stops there knows whether the entry concerns them.
- An `API Change` entry adds who is affected and the migration: what to
  pass, call or install instead to keep the previous behavior. Only this
  part may make the entry longer.
- A `Fix` entry describes the symptom the user saw (what raised, returned
  a wrong value or failed, and when), not the internal cause.
- Anything beyond that (full parameter lists, edge cases, rationale)
  belongs in the user guide or the API docs: link to them instead of
  copying them into the entry.

## Steps

1. Open `docs/releases/releases.md` and find the section marked
   `<small>In development</small>` (the top one).
2. Check whether the change touches something added or changed in this
   same version. The previous release never had it, so there is nothing to
   announce separately: correct or extend the existing entry instead of
   adding a `Fix` or a second entry. This also holds for a fix to a feature
   that is not released yet.
3. Pick the subsection: `**Added**`, `**Changed**` or `**Fixed**`. Create it
   in that order if it does not exist yet.
4. Pick the badge, exactly as the legend at the top of the file:
   - `<span class="badge text-bg-feature">Feature</span>`: new capability.
   - `<span class="badge text-bg-enhancement">Enhancement</span>`: better
     behavior of something existing.
   - `<span class="badge text-bg-api-change">API Change</span>`: a user must
     change code, or a default changed.
   - `<span class="badge text-bg-danger">Fix</span>`: bug fix.
   - `<span class="badge text-bg-docs">Docs</span>`: documentation.
5. Place it by impact: `API Change` entries go first in `**Changed**`,
   above the other badges, so whoever upgrades sees them before anything
   else; within a subsection, more visible changes go before minor ones.
   An upgrade summary at the top of the version is written once, when the
   release is prepared and the author asks for it, not per entry.
6. Write the entry as the existing ones: `+ <badge> Text.`, public names in
   backticks, the first mention of a method linked as
   ``[<code>ForecastingAssistant.plan()</code>][assistant]`` using the link
   references defined at the bottom of the file. Add a new reference there
   only if none fits.
7. Optionally end the entry with the pull request or issue, once its
   number is known:
   `([#123](https://github.com/skforecast/skforecast-ai/pull/123))`. The
   link carries the detail, so the entry can stay short. Never invent a
   number.
8. No en dashes or em dashes. Show the final entry to the user.
