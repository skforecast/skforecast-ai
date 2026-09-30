---
name: release-note
description: Add or update the entry for a user-visible change in docs/releases/releases.md under the version in development. Use when a change affects the public API, CLI output, generated scripts or warnings.
---

# Release note

The changelog is read by package users. An entry says what changed for them
and whether it affects them, in one or two sentences. Maintainer detail
(paths under `tools/`, refactors, internal constants, build configuration)
stays in the diff; internal changes get no entry, or one short line when
they have a visible effect.

## Steps

1. Open `docs/releases/releases.md` and find the section marked
   `<small>In development</small>` (the top one).
2. Pick the subsection: `**Added**`, `**Changed**` or `**Fixed**`. Create it
   in that order if it does not exist yet.
3. Pick the badge, exactly as the legend at the top of the file:
   - `<span class="badge text-bg-feature">Feature</span>`: new capability.
   - `<span class="badge text-bg-enhancement">Enhancement</span>`: better
     behavior of something existing.
   - `<span class="badge text-bg-api-change">API Change</span>`: a user must
     change code, or a default changed.
   - `<span class="badge text-bg-danger">Fix</span>`: bug fix.
   - `<span class="badge text-bg-docs">Docs</span>`: documentation.
4. Write the entry as the existing ones: `+ <badge> Text.`, public names in
   backticks, the first mention of a method linked as
   ``[<code>ForecastingAssistant.plan()</code>][assistant]`` using the link
   references defined at the bottom of the file. Add a new reference there
   only if none fits.
5. If an entry for the same feature already exists in this version, extend
   it instead of adding a second one.
6. No en dashes or em dashes. Show the final entry to the user.
