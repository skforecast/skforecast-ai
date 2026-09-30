# Documentation home page

The home page of the documentation (https://ai.skforecast.org/) is not a
Markdown page. It is a custom Material for MkDocs template with its own styles,
scripts and a data file, built like the home page of the skforecast
documentation so that both sites read as one family. This folder holds the
scripts that generate the data and the preview image, and this README explains
how the pieces fit together, why the page says what it says, and how to update
it.


## File map

```
docs/
├── README.md                          # Front matter only: `template: home.html`
├── overrides/
│   ├── home.html                      # The page: every section and all its text
│   └── partials/
│       ├── home-data.json             # GENERATED: data of the animation and the leaderboard
│       ├── ask-window.html            # Answers of ask() in tabs, also used by the Ask the assistant page
│       └── team.html                  # Team cards, also used by docs/more (--8<-- "team.html")
├── stylesheets/home.css               # Styles, all scoped to .sk-home
├── stylesheets/extra.css              # Site-wide styles, including the ask() window (.sk-ask)
├── javascripts/home.js                # Animation (listed in mkdocs.yml extra_javascript)
├── javascripts/ask-window.js          # Tabs and syntax highlight of the ask() window, on any page
├── animations/
│   ├── deterministic-first.html       # Animation of the user guide, embedded with an iframe
│   ├── deterministic-first-data.js    # GENERATED: its data
│   ├── backtesting-scenario.html      # Animation of the Backtesting section of the guide
│   ├── backtesting-scenario-data.js   # GENERATED: its data
│   ├── compare-candidates.html        # Animation of the comparison section of the guide
│   └── compare-candidates-data.js     # GENERATED: its data
└── img/
    ├── social-card-home.png           # GENERATED: preview image when the page is shared
    └── skforecast-ai-forecast-ask.png # GENERATED: image for the GitHub README
tools/docs/home_page/
├── README.md                          # This file
├── generate_home_data.py              # Writes home-data.json and the data of the animations
├── deterministic_first_llm.json       # LLM suggestion of the animation, recorded with --llm
├── make_social_card.mjs               # Writes the two images of docs/img/ above
└── social_card.html                   # Layout of the social preview card
```


## What the page sells, and why this animation

skforecast already sells the models. What skforecast-ai adds is the path from
raw data to a validated forecast, and the trust in that path. The page is built
around three messages, in this order:

1. **One call, from data to forecast.** Profiling, model choice, features,
   validation: done for you.
2. **Decisions you can audit.** Every choice comes from a rule, the same data
   always gives the same result, and you get the script that ran. This is
   the differentiator against AutoML black boxes and against LLM agents that
   write code ad hoc.
3. **An LLM that explains, never decides.** Optional, grounded in the
   skforecast skills, validated before it touches execution, and your
   dataset never leaves your machine.

The headline, "The forecasting assistant that shows its work", carries the
second message, which is the one no alternative can claim.

The animation is the assistant's own pipeline (profile, plan, run, ask) rather
than a chat or a terminal. A chat would suggest that the LLM makes the
decisions, the opposite of how the package works. A terminal is authentic but
does not show what each step decides. The pipeline shows the decisions on the
chart itself (the lags found by the profile, the rolling windows of the plan,
the forecast against the held-out hours) and keeps the LLM for last, marked as
optional. Orange marks the deterministic engine and violet the LLM layer,
across the whole page.


## How the page is built

- `docs/README.md` is the home page in `nav`. Its front matter selects the
  template (`template: home.html`). Its body is ignored, so the home page does
  not appear in the site search.
- `docs/overrides/home.html` extends `main.html` (so the header, tabs, search,
  version selector and footer are the standard ones) and overrides three
  blocks:
  - `extrahead`: loads Poppins (headings) from Google Fonts and
    `stylesheets/home.css`, only on the home page.
  - `site_nav`: empty, so there are no sidebars.
  - `container`: the whole page, inside `<div class="sk-home" id="sk-home">`.
    The content of `partials/home-data.json` goes, HTML-escaped, in the
    `data-home` attribute of that div. It is not in a
    `<script type="application/json">` because instant navigation re-runs the
    scripts of the page without their `type` attribute.
- `exclude_docs` in `mkdocs.yml` keeps the templates out of the site. Material
  still copies the non-template files of `custom_dir` as theme assets, so
  `home-data.json` is also published at `partials/home-data.json`, as in
  skforecast. It is small and harmless.
- Internal links use the `url` filter (`{{ 'quick-start/how-to-install.html' | url }}`),
  so every version deployed with mike links to its own pages.
- `home.js` does nothing on pages without `#sk-home`. It subscribes to
  Material's `document$` and destroys the previous instance (animation frame,
  observers, listeners) before starting a new one. It honors
  `prefers-reduced-motion`: the stage shows the last step complete.
- The window of the "Ask why, at any step" section is
  `partials/ask-window.html`, shared with the Ask the assistant page of the
  Quick start (included there with `--8<-- "ask-window.html"`). Its styles are
  in `extra.css` (`.sk-ask`) and its tabs in `ask-window.js`, which also
  provides the syntax highlighter home.js uses, so it is listed before
  `home.js` in `extra_javascript`. Each page writes its own caption.


## The data

Every number, decision and line of code on the page is a real skforecast-ai
output. `generate_home_data.py` runs the same workflow as
`tools/ai/check_ask_context.py` on `bike_sharing`:

| Item | Value |
|:-----|:------|
| Dataset | `bike_sharing`, the last 2,000 hours, target `users`, exogenous `holiday`, `weather`, `temp` |
| Assistant | `ForecastingAssistant()`, no LLM |
| Plan | `plan(profile, steps=36, interval=[0.1, 0.9])` |
| Forecast | `forecast(data, test_size=36, ...)`: evaluated on the last 36 hours |
| Comparison | `compare()` of LightGBM recursive, LightGBM direct and Ridge recursive, with `create_cv(profile, plan, refit=False)` |
| Chart | The last 8 days before the forecast (3 on phones) and the 36 held-out hours |

The answer in step 4 is not generated at build time: it is an excerpt, quoted
word for word, of the `forecast` scenario of
`tools/ai/ask_context_reports/0.3.0_bike_sharing.md` (`google:gemini-3.5-flash`).
The five tabs of the "Ask why, at any step" section quote, in the same way,
the opening of the grounded answer of the `forecast`, `backtest`, `compare`,
`plan` and `qa` scenarios of that report. They are ordered from the most
common use of `ask()` to the least, as the quick start, the user guides and
the CLI use it: a forecast result first, then backtests and comparisons, the
plan and a question without context. The `profile` and `code` scenarios are
left out: the plan tab already carries the profile, and the CLI explains a
plan through its script. The Compare tab shows the candidates as the evaluation script names
them (`recursive_default`, `direct`), because its answer quotes those names.
The script stops if the MASE of the forecast or of the backtest no longer
matches the value quoted in those answers (`QUOTED_MASE`,
`QUOTED_BACKTEST_MASE`; the backtest is the `LightGBM, recursive` row of the
leaderboard, the winner of the Compare tab), so the page never shows an
explanation of different results.

### The animation "Deterministic first, LLM second"

`docs/animations/deterministic-first.html` is embedded in the introduction of
the Agentic forecasting user guide and in Ask the assistant (quick start). The
section of the same name on the home page, the "Under the hood" section of Your
first forecast, the step-by-step guide and "What is sent to the LLM" (Configuring
the LLM) link to it. It is built with the animation engine of the skforecast
docs (`skf-anim.js`, `skf-anim.css`, copied from skforecast with a `brandUrl`
option), and it continues the workflow above: `refine_plan()` with the prompt
`REFINE_PROMPT`, `forecast()` with the refined plan on the same 36 held-out
hours, and `ask()` about that forecast.

The suggestion of `refine_plan()` (lags, and window features when the LLM
changes them) is recorded once with `--llm` in `deterministic_first_llm.json`.
Every run replays it as an explicit override of `refine_plan()` (the LLM mode
merges its suggestion the same way and calls the same `plan()`), so the refined
plan, its forecast and its metrics are real and need no LLM call. The first
suggestion of the animation, which the validation of `plan()` rejects, is the
recorded lags plus a monthly lag (`REJECTED_EXTRA_LAG`): the suggestion is
illustrative, the rejection message is the real one.

The question and the answer of `ask()` are written by hand in the animation
(`ASK_PROMPT` and `ANSWER`): the step shows what kind of answer to expect, and a
short answer written for the stage reads better than an excerpt of a real one.
Its MAE and MASE come from the data; its last sentence describes this forecast
(the large errors are the peaks of the second day, which it underestimates), so
review it when the data changes.

### The animation "Validate the way you deploy"

`docs/animations/backtesting-scenario.html` is embedded in the Backtesting
section of the Agentic forecasting user guide and in the `create_cv()` section
of Ask the assistant. The step-by-step guide links to it from its `create_cv()`
with a prompt section, and the `create_cv()` card of the home page as well. It shows what the LLM mode
of `create_cv()` does with a deployment scenario ("Every day at noon we
forecast the next 36 hours, and we retrain once a week"): the phrases become
`TimeSeriesFold` parameters (except the horizon, `steps`, which the LLM does not
decide: it comes from the plan, and the animation marks it so), and `backtest()`
evaluates the model fold by fold. At the end, the card of the `TimeSeriesFold`
shows the `backtesting_forecaster()` call of `result.code` instead.

The scenario and the phrase that maps to each parameter are written by hand in
the animation. The data is real: `write_backtesting_data()` passes the
parameters of `BACKTEST_SCENARIO` explicitly to `create_cv()`, the same path the
LLM mode takes, with the initial training ending at the first 11:00 on or after
the deterministic default (so every forecast starts at noon), and runs
`backtest()` with the deterministic plan. It writes the series around the
folds, every fold and whether the model is trained in it, the predictions of
each fold, the metrics, the `TimeSeriesFold` snippet of the script and the
deterministic strategy the animation compares with.

### The animation "Let measured performance pick the model"

`docs/animations/compare-candidates.html` is embedded in the "Comparing
forecaster configurations" section of the Agentic forecasting user guide; the
`compare()` section of the home page and the step-by-step guide link to it. It runs `compare()`
without candidates, so the profile proposes them (ForecasterRecursive,
ForecasterDirect and ForecasterFoundation with Chronos-2), with the strategy of
the backtesting animation, and shows one window moving over the three
candidates at once while each one draws its forecast against the actual
series, the leaderboard as a plain sort, the winner reused in `forecast()`, and
`ask()` explaining the ranking. The question and the answer of `ask()` are
written in the animation (`ASK_PROMPT`, `ANSWER`), with figures from the data;
the answer only uses what `ask()` sends for a comparison (the leaderboard, the
shared profile and strategy, and the winning plan, never per-fold results).

`write_compare_data()` writes the leaderboard, the series over the span of the
folds and, for every candidate, the predictions that are scored and the error
of every fold (for the running MAE). With overlapping folds, skforecast scores
each hour with its latest forecast, so those are the predictions written and
the hours each fold's error uses; the script checks that those errors average
to the MAE of the leaderboard, and that every candidate is scored on the same
hours. Its numbers differ from the comparison of the home
page, which uses other candidates and another strategy. It needs Chronos-2
(`chronos-forecasting`, with `torch`), downloads its checkpoint the first time
and adds about a minute to the script; its results are deterministic.

Written by hand in `home.html`, review them when the results change: the facts
and the decisions of the side panes, the metric labels, the question and answer
of step 4 and the note under the stage; and in `partials/ask-window.html`, the
questions and answers of the ask() section. The code of the steps is in `CODE`
in `home.js`.


## Common tasks

### Regenerate the data

Needed when the profile, the plan, the rendered script or the dataset change.
It needs `lightgbm`, `chronos-forecasting` (for the comparison animation) and
network access for the dataset and the Chronos-2 checkpoint.

```bash
python tools/docs/home_page/generate_home_data.py
```

If it stops on the MASE check, run `tools/ai/check_ask_context.py --dataset
bike_sharing` against a real model (it costs money),
save the reviewed report as described in `tools/ai/ask_context_reports/README.md`,
and update the answers (step 4 in `home.html`, the ask() section in
`partials/ask-window.html`), the report links (the note under the stage, and
the caption of the ask() section in `home.html` and in
`docs/quick-start/ask-the-assistant.md`),
`QUOTED_MASE` and `QUOTED_BACKTEST_MASE`.

### Record the LLM outputs of the animation

Needed only to change the suggestion the animation replays, for example after
changing `REFINE_PROMPT`. It calls a real LLM (it costs money), so review the
file before committing it: the suggested lags must make sense for the prompt.

```bash
python tools/docs/home_page/generate_home_data.py --llm google:gemini-3.5-flash
```

It needs `GOOGLE_API_KEY` for `google:` models (other providers read their
usual environment variables). If the LLM does not change the lags, the script
stops: run it again or adjust `REFINE_PROMPT`.

### Update the social preview card and the README image

The Open Graph and Twitter tags in the `extrahead` block of `home.html` make
LinkedIn, Slack or X show a preview with `docs/img/social-card-home.png` when
the home page is shared. The image is the headline plus a screenshot of the
animation paused on its last step (the forecast and the `ask()` answer), laid
out by `social_card.html` like the card of skforecast. The same screenshot,
without the headline, is saved as `docs/img/skforecast-ai-forecast-ask.png`,
the image for the GitHub README (reference it with an absolute URL, so PyPI can
show it too). Regenerate both when the animation or the headline changes. It needs Node.js 22 or newer and Google
Chrome (set `CHROME_PATH` if Chrome is not in the default macOS location):

```bash
PYTHONPATH=. mkdocs serve                           # in another terminal
node tools/docs/home_page/make_social_card.mjs      # default URL: http://127.0.0.1:8000/
```

The tags use absolute URLs to `https://ai.skforecast.org/stable/`, the alias
mike deploys, because social networks require them. A new image is only
visible once it is deployed.

The `privacy` plugin (see `mkdocs.yml`) downloads Google Fonts and other
third-party assets at build time and serves them from the site, so the build
needs network access; the downloads are cached in `.cache/`.

### Change a text, a link or a section

Edit `docs/overrides/home.html` and check it with `mkdocs serve`. Link internal
pages with the `url` filter and their `.html` path (the site uses
`use_directory_urls: false`). No en dashes or em dashes, as everywhere else.


## Verification

```bash
PYTHONPATH=. mkdocs serve
```

Check the home page:

- in light and dark mode, using the palette toggle in the header;
- clicking each step, with the animation playing and paused;
- after navigating to another page and back (instant navigation): the
  animation restarts and the browser console shows no errors from `home.js`;
- at phone width (about 400 px): no horizontal scroll of the page;
- with reduced motion enabled in the operating system.

Check the tabs of the ask() window on the Ask the assistant page as well, in
both schemes.
