---
name: release-note
description: Adds or updates the entry of a finished user-visible change in docs/releases/releases.md, following the release notes conventions shared with skforecast (short entries, highlights with badges, Added/Changed/Fixed grouped by area, pull request links), or consolidates the section of the version in development before a release. Use when a change affects the public API, CLI output, generated scripts or warnings, when verify or open-pr finds a user-visible change without a release note, or with the argument `consolidate` before publishing a release.
argument-hint: "[short description of the change, PR or issue number | consolidate]"
---

# Write the release note of a finished change

Change to describe: $ARGUMENTS (if empty, infer it from the branch). If it
is `consolidate`, go to
[Consolidate before a release](#consolidate-before-a-release).

The release notes are read by package users on the documentation site, most
of them to decide whether to upgrade and what will change for them. An entry
says what the user sees, in one or two sentences. The technical detail
(cause, implementation, measurements, every edge case) belongs in the pull
request, which the entry links, and the full parameter lists in the user
guide or the API docs. The code is the source of truth: verify every name,
default, argument and message in the source before writing it.

## 1. Scope the change

- Release branch: `X.Y.x` from `__version__` in `skforecast_ai/__init__.py`
  (`0.4.0` -> `0.4.x`).
- Changed files: `git diff --name-only origin/<release-branch>...HEAD` plus
  `git status --short`. Read the diff of the package code and docs, and the
  commit messages for intent.
- Issue or PR numbers: from `$ARGUMENTS`, the commits or `gh pr view` when
  a PR exists. Never invent a number.

No entry (say so and stop) when the change is not visible to a user of the
package:

- Tests, CI, `.claude/`, `dev/`, `tools/`, internal refactors with no
  change in behavior or performance.
- Private classes, functions and attributes (names starting with `_`),
  even if they change the internal design.
- Repository files (`SECURITY.md`, `CITATION.cff`, templates, plugin
  manifests) and the infrastructure of the documentation site.
- A bug in something added in this same cycle: update that entry instead.

Documentation gets an entry only for what a reader would notice: a new user
guide, a new section, a redesigned page.

## 2. Read the target section

Read the section of the version in development
(`## X.Y.Z <small>In development</small> { id="X.Y.Z" }`, created by
`/release-bump`) to find related entries:

- **Same cycle**: if the change modifies something introduced in this same
  section, update that entry instead of adding a new one. Users never saw
  the bug, so it is not a Fixed entry.
- **Same object or same symptom**: if an entry already covers the same
  method, option or kind of problem, extend it and add the pull request to
  its trailer, rather than adding a near-duplicate. Several small fixes of
  one method are one entry.

Never edit the sections of released versions.

## 3. Classify

| Subsection | What goes there |
|:-----------|:----------------|
| **Added** | New public methods, arguments, result fields, CLI commands and options, MCP tools, extras; compatibility with a new version of a dependency |
| **Changed** | Behavior, defaults, rule decisions, generated scripts, renames, removals, deprecations, performance, minimum versions of the dependencies, documentation |
| **Fixed** | Bugs that existed in a released version |

When a subsection has more than about 10 entries, its entries are grouped
by area under a label in italics on its own line (`*Plans and overrides*`,
`*Backtesting and comparison*`, `*Foundation models*`, `*Results and
explanations*`, `*LLM layer*`, `*MCP server*`, `*CLI*`, `*Dependencies*`,
`*Documentation*`...). Use the labels already in the section, add one only
when no label fits, and do not use headings (`###`), which would enter the
table of contents.

Then decide whether the change also deserves:

- A **highlight** in "The main changes in this release are:". Highlights
  are for new features, API changes, notable enhancements and fixes of
  wrong results in a common use. At most 8 to 10 per release: if the list
  is full, either the new one replaces a less important one or it stays
  out.
- A line in the **"Before upgrading"** admonition (see step 6), when the
  results of existing code change without any change in that code (another
  plan, another generated script, other predictions), or when existing
  code stops working.

## 4. Write the entry

Format: a bullet starting with `+ `, one blank line between bullets, placed
in its group next to the entries on the same topic. No badge: badges go
only in the highlights.

**Length: one or two sentences, about 40 words. Three sentences and 80
words is the ceiling**, for a change that needs a workaround or a
migration. If it does not fit, the entry is describing the implementation
or several changes at once.

- **Added**: what is new, where it lives and what it does for the user.
  Name the main options, not every field or attribute.
- **Changed**: the new behavior, the old one when it helps to recognise
  the change, and the consequence for users ("The predictions are the
  same", "The plan for hourly data may differ from previous versions"). If
  the user has to do something, say what to pass, call or install instead.
- **Fixed**: the symptom the user saw and under which conditions (which
  method, forecaster, arguments, data). `Fixed an issue in ... where ...`,
  or the wrong behavior stated directly (`... raised ... when ...`). Add
  the new behavior only when it is not simply "it works now".
- **Deprecations and removals**: name the version and the replacement.
- **Performance**: one or two measured numbers with their scenario. Not
  the full benchmark and not what was optimized internally.

Leave out:

- The cause of a bug and how it was fixed. One short clause is fine when
  it tells the user whether they were affected.
- Lists of every parameter, attribute or field involved: name two or three
  and end with `...`.
- Secondary messages and edge cases. Quote an exception only when it is
  short and a user would search for it; otherwise name its type.
- Internal file paths, private names and names of internal helpers.
- What did not change, except the one sentence that reassures about
  results.

Style:

- Present tense for the current behavior, past tense for the bug.
- No en dashes or em dashes. Use commas, colons, semicolons or
  parentheses.
- Trailers at the end of the entry, in this order: the user guide or API
  page (`See the [CLI guide][cli-guide]`), then the pull request,
  `([#123](https://github.com/skforecast/skforecast-ai/pull/123))`,
  preceded by the issue it closes when there is one (`.../issues/123`),
  several separated by commas.
- **Every entry links its pull request.** It is where the detail left out
  of the entry lives. If the pull request does not exist yet, write the
  entry without it and add the link when it is opened (`/open-pr` does
  it). A change committed directly to the release branch has no link.

## 5. Write the highlight (if warranted)

The highlight is one sentence, two at most, with the same links and
trailers as the entry, preceded by a badge, exactly as the legend at the
top of the file:

```html
<span class="badge text-bg-feature">Feature</span>
<span class="badge text-bg-enhancement">Enhancement</span>
<span class="badge text-bg-api-change">API Change</span>
<span class="badge text-bg-danger">Fix</span>
<span class="badge text-bg-docs">Docs</span>
```

Order the highlights by badge (Feature, Enhancement, API Change, Fix,
Docs) and by importance within each badge. Merge related highlights (all
the new overrides of `plan()`, the MCP server and its plugin) into one.

## 6. "Before upgrading" admonition

After the highlights, only when the release has something to list:

```markdown
!!! warning "Before upgrading"

    Some results change with this version, without any change in your code:

    + `plan()`: ... is chosen instead of ..., because ...
    + ...

    And some code needs to be updated: ... See **Changed**.
```

One line per method or object, saying what changes and, when there is one,
how to keep the previous behavior. It summarises entries that are detailed
in their subsection; it never replaces them.

## 7. Link references

- The first mention of a public method or class in an entry is linked with
  the references defined at the bottom of the file, under
  `<!-- Links to API Reference -->`:
  ``[<code>ForecastingAssistant.plan()</code>][assistant]``. Arguments,
  attributes, values and later mentions: plain backticks.
- Reuse the existing references (`[assistant]`, `[cli]`, `[mcp]`,
  `[results]`, `[cli-guide]`...). Add one only if none fits, pointing to a
  page that exists under `docs/` (paths are relative to `docs/releases/`).
- If the object has no API page, use plain backticks and tell the user
  that the page is missing.

## 8. Check

With the Python command of `/verify` (standard library only):

```bash
python tools/docs/check_release_notes.py
```

It reports, for the version in development only, the undefined references,
the entries over 80 words, the entries without a pull request or issue
link and the entries that still carry a badge. Also confirm that the
layout of the section is intact: two blank lines before `**Added**`,
`**Changed**`, `**Fixed**` and the next `##` heading.

## 9. Report

Show the inserted or updated text, the subsection and group, and whether a
highlight or a "Before upgrading" line was added (and why not, if it was
not). List anything left for the user: a missing API page, a missing pull
request link, detail that was left out and is not in the pull request
description either.

## Consolidate before a release

Entries are added one pull request at a time, so before a release the
section of the version in development is read as a whole, as a user would.
Run it with `/release-note consolidate`, before the date replaces
`In development`.

1. Run the check of step 8 and read the whole section.
2. Remove the entries that do not pass the filter of step 1, and those
   about bugs introduced in this same cycle.
3. Merge the entries about the same object or the same symptom, keeping
   all their pull request links.
4. Shorten every entry over the ceiling, following step 4, and remove the
   badge of any entry that carries one (the format until 0.3.1).
5. Group the subsections with more than about 10 entries by area, and
   order the groups from the most to the least used part of the package.
6. Write or review the highlights (at most 8 to 10, merged and ordered by
   badge) and write or update the "Before upgrading" admonition from the
   entries whose results or code change.
7. Run the check again and report: words and entries before and after, the
   entries removed (so the user can restore one), the entries without link
   and the wording that needs their judgment.

As a reference, a skforecast release with many changes (0.26.0) has about
80 entries and 3,500 words; most releases have 10 to 30 entries.

## Examples

Added:

```markdown
+ New `describe()` method on every result that `ask()` accepts. It returns, without an LLM, a plain-text description of the result, with the predictions summarized instead of listed. See [Results][results].
```

Changed, with what the user has to do:

```markdown
+ [<code>ForecastingAssistant.compare()</code>][assistant] without `candidates` leaves out the alternatives that need more than 500 estimator fits and says so in a warning. Pass them in `candidates` to run them anyway.
```

Fixed:

```markdown
+ Fixed an issue in [<code>ForecastingAssistant.create_cv()</code>][assistant] where a strategy with fewer than 2 folds raised an error without saying how to get a single validation window.
```

Too detailed (every option, limit and internal rule, 200 words), and its
release note:

```markdown
+ New MCP server, so coding agents (Claude Code, Cursor and other MCP clients) can run the deterministic workflow as tools: profile a CSV file, plan, backtest, compare and forecast, each result with the script that produced it and the packages it needs. In Claude Code, install it with its skill as a plugin (...); with other agents, start `skforecast-ai mcp --allow-dir DIR` from the new `mcp` extra (...). Responses never carry rows of your data ... The server only reads CSV files inside `--allow-dir`, of at most `--max-file-mb` ..., and only runs the foundation models whose license ...

+ New MCP server (`skforecast-ai mcp`, extra `mcp`), so coding agents can profile a CSV file, plan, backtest, compare and forecast as tools, each result with the script that produced it. It never returns rows of your data and only reads files inside `--allow-dir`. See [MCP server for coding agents][mcp-guide] ([#35](https://github.com/skforecast/skforecast-ai/pull/35), [#36](https://github.com/skforecast/skforecast-ai/pull/36)).
```

Highlight:

```markdown
+ <span class="badge text-bg-feature">Feature</span> [<code>ForecastingAssistant.compare()</code>][assistant] adds a seasonal naive baseline to the leaderboard and says whether the best configuration beats it. Pass `baseline=False` to leave it out.
```
