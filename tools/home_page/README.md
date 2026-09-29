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
│       └── home-data.json             # GENERATED: data of the animation and the leaderboard
├── stylesheets/home.css               # Styles, all scoped to .sk-home
├── javascripts/home.js                # Animation (listed in mkdocs.yml extra_javascript)
└── img/social-card-home.png           # GENERATED: preview image when the page is shared
tools/home_page/
├── README.md                          # This file
├── generate_home_data.py              # Writes docs/overrides/partials/home-data.json
├── make_social_card.mjs               # Writes docs/img/social-card-home.png
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
- Internal links use the `url` filter (`{{ 'quick-start/quick-start.html' | url }}`),
  so every version deployed with mike links to its own pages.
- `home.js` does nothing on pages without `#sk-home`. It subscribes to
  Material's `document$` and destroys the previous instance (animation frame,
  observers, listeners) before starting a new one. It honors
  `prefers-reduced-motion`: the stage shows the last step complete.


## The data

Every number, decision and line of code on the page is a real skforecast-ai
output. `generate_home_data.py` runs the same workflow as
`tools/ask_context_check.py` on `bike_sharing`:

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
`tools/ask_context_reports/0.3.0_bike_sharing.md` (`google:gemini-3.5-flash`).
The script stops if the MASE of the forecast no longer matches the value quoted
in that answer (`QUOTED_MASE`), so the page never shows an explanation of
different results.

Written by hand in `home.html`, review them when the results change: the facts
and the decisions of the side panes, the metric labels, the question and answer
of step 4, and the note under the stage. The code of the steps is in `CODE` in
`home.js`.


## Common tasks

### Regenerate the data

Needed when the profile, the plan, the rendered script or the dataset change.
It needs `lightgbm` and network access for the dataset.

```bash
python tools/home_page/generate_home_data.py
```

If it stops on the MASE check, run `tools/ask_context_check.py --dataset
bike_sharing --scenarios forecast` against a real model (it costs money),
save the reviewed report as described in `tools/ask_context_reports/README.md`,
and update the answer in `home.html`, the report link in the note under the
stage, and `QUOTED_MASE`.

### Update the social preview card

The Open Graph and Twitter tags in the `extrahead` block of `home.html` make
LinkedIn, Slack or X show a preview with `docs/img/social-card-home.png` when
the home page is shared. The image is the headline plus a screenshot of the
animation paused on its last step (the forecast and the `ask()` answer), laid
out by `social_card.html` like the card of skforecast. Regenerate it when the
animation or the headline changes. It needs Node.js 22 or newer and Google
Chrome (set `CHROME_PATH` if Chrome is not in the default macOS location):

```bash
PYTHONPATH=. mkdocs serve                      # in another terminal
node tools/home_page/make_social_card.mjs      # default URL: http://127.0.0.1:8000/
```

The tags use absolute URLs to `https://ai.skforecast.org/stable/`, the alias
mike deploys, because social networks require them. A new image is only
visible once it is deployed.

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
