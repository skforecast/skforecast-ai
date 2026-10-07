# MCP agent check

`check_mcp_agent.py` launches headless Claude Code sessions against the MCP
server of this checkout (`skforecast-ai mcp`), one per scenario of
`scenarios.py`, and writes a report with every step between the model and
the server, automatic checks of each trace and the evaluation of a
reviewer.

It is the only check of what decides whether the server works for a user:
that a real agent, with only the tool descriptions, the instructions of the
server and the `SKILL.md`, chooses the right calls, reacts well to the
errors and reports the results without inventing. The tests in
`tests/tests_mcp/` cover the protocol, the parity with the Python API, the
security and every tool; none of them runs an agent.

It is a manual, pre-release tool. It spends the usage quota of a Claude
subscription, needs network access and its answers are not deterministic,
so it is not part of the test suite. The design and its reasons are in
`dev/mcp-agent-check-plan.md`.

## When to run it

Before a release, whenever one of these changed since the previous run:

- `skforecast_ai/mcp/` (tools, descriptions, schemas, errors, hints,
  instructions of the server),
- `skforecast_ai/mcp/skills/` (the skill of the server),
- what the summaries of the responses say: `skforecast_ai/llm/context.py`
  and the explanations it renders,
- the rules of `recommendation/`, when they change what a plan or a
  strategy recommends.

Also after fixing a finding of a previous run: relaunch the scenarios it
appeared in.

## Requirements

- The `claude` CLI logged in with a Claude subscription (`claude auth
  status` must say `authMethod: claude.ai`). The sessions never use an API
  key: the runner checks the login before launching anything, removes
  `ANTHROPIC_API_KEY`, the `CLAUDE_*` variables of the session that
  launches it and the keys of other providers from the environment of every
  session, and cuts a session whose `init` event does not say
  `apiKeySource: none`.
- The project environment, with the `mcp` extra. `foundation_default` also
  needs `chronos-forecasting` and is skipped without it.
- Network access: the datasets come from `fetch_dataset`, `err_url`
  downloads a file and the foundation model checks its weights.

## How to run it

From the repository root, inside the project environment:

```bash
python tools/mcp/check_mcp_agent.py --dry-run     # free: workspaces, server, fixed context
python tools/mcp/check_mcp_agent.py --list        # the scenarios

# One scenario, to see the report (ignored by git)
python tools/mcp/check_mcp_agent.py --run-name try --scenarios basic_forecast --no-ablation

# Pilot: every scenario once, plus the ablation without the skill
python tools/mcp/check_mcp_agent.py --run-name 0.5.0-pilot

# Release run: 3 repetitions, then the critical scenarios with a weaker model
python tools/mcp/check_mcp_agent.py --run-name 0.5.0 --reps 3
python tools/mcp/check_mcp_agent.py --run-name 0.5.0-haiku --model haiku --reps 3 \
    --scenarios basic_forecast,exog_no_future,compare_code,dirty_data,restricted_model,err_url,err_outside_dir,err_bad_target,err_long_horizon

# After writing evaluation.json: rebuild the report
python tools/mcp/check_mcp_agent.py --run-name 0.5.0 --report-only
```

A run is its folder under `agent_reports/`. Launching the same
`--run-name` again continues it: every session with a finished trace is
skipped, so a run can be spread over several days. To repeat a session,
delete its `traces/<session>.jsonl` and `traces/<session>.meta.json`. One
folder holds one model.

`--dry-run` prepares one workspace per scenario, starts the server, lists
its tools and measures what a client loads in every session (instructions,
descriptions and schemas, skill). That size is in the header of every
report: it is context each user pays for.

### What a session is

- A new temporary folder outside the repository with `data/` (the files of
  the scenario, the only directory the server may read), `out/` (what the
  server writes) and, unless it is an ablation session,
  `.claude/skills/skforecast-ai-forecasting/` copied from the package. The
  agent sees neither `AGENTS.md` nor the code.
- One `claude -p` process with `--strict-mcp-config`, `--setting-sources
  project`, no session persistence and the auto memory off: no plugin,
  setting or memory of the user is loaded (the `init` event of the trace
  shows it, and a check verifies it).
- The messages of the user go through stdin as `stream-json`, the next one
  when the previous turn ends, so a scenario with two turns runs against
  the same server and its ids stay valid. `--resume` is not used: it starts
  a new server.
- Allowed without asking: the tools of the server, `Read`, `Glob`, `Grep`
  and `Skill`, plus what the scenario adds (`Write`, `Bash(curl:*)`).
  Anything else is denied and recorded, and is a signal: an agent that
  tries to write its own script instead of using the server shows up
  there. Claude Code runs read only shell commands (`ls`, `head`, `cat`)
  without asking, so those are not denied.
- Claude Code defers MCP tools: the agent calls `ToolSearch` before the
  first use of each one. It is shown in the timeline and ignored by the
  checks.

### Limits and interruptions

| Limit | Default | What happens |
|:--|:--|:--|
| Time per session | 600 to 1500 s, set by the scenario (`--timeout` overrides it) | The runner kills the session and its server; status `timeout`, which fails the check "finished within the limits". Its tokens are unknown. |
| Agent turns per message | 30 (`--max-turns` of the CLI) | Status `max_turns`, same check. |
| Equivalent cost per session | 5 USD (`--max-budget-usd`) | Status `budget`, same check. |
| Usage of the plan | 0.95 (`--stop-at-utilization`) | Every session reports the usage of the 5 hour and 7 day windows. At or above the threshold the runner stops before the next session and prints what is left. |
| Usage limit reached | | Status `usage_limit`: the session is not saved as finished and not counted as a failure, and the runner stops. Launch the same command again later. |
| Error of the provider, or a crash | | Status `provider_error` or `crashed`: not finished, not a failure of the agent; the run goes on and the session is retried on the next launch. |

The cut by time was exercised with `--timeout 25`. The cut by usage limit
has not been observed: it is detected by a `rate_limit_event` with `status:
rejected`, a result with error 429 or a `terminal_reason` of limit, values
read from the CLI. If a session ends that way and is recorded as
`provider_error` instead, add what its trace shows to `_limit_hit()`.

The cost in the reports is the equivalent the CLI computes from the tokens,
not a charge: use it to compare scenarios and releases.

## The report

`agent_reports/<run>/report.md`, written by the runner and never edited by
hand:

- header: release, commit, model, versions, fixed context, totals;
- overall evaluation and findings, in two lists that are always present:
  problems of the library (server or skill) and problems of the model;
- summary table, one row per session;
- one section per session: the request and what is expected, a numbered
  timeline (`LLM -> MCP` for the server, `LLM -> client` for a tool of
  Claude Code, the summaries inside `<details>` blocks), the final answer
  as written, the automatic checks, the numbers without a source, the
  evaluation, and links to the raw trace and the log of the server.

`results.json` holds the same in machine form, to compare releases.

### Automatic checks

Deterministic, over the trace. `PASS`, `FAIL`, or `WARN` for a signal that
does not fail on its own (an unexpected error code, a denied tool, a skill
that was available and not loaded).

- Every session: subscription and no API key, isolated session, skill
  available or absent, finished within the limits, no `internal_error`,
  `get_failure` read after an `execution_failed`, no failed call repeated
  with the same arguments, absolute paths, files of the user unchanged
  (hash before and after).
- Per scenario (`scenarios.py`): tools that must succeed and their order,
  error codes that must appear, arguments that must reach the server, and
  a few conditions on files and on the text of the answer.

They catch what is mechanical. Whether an answer is honest and complete is
the job of the reviewer.

### Numbers without a source

Every number the agent writes is looked for in the responses of the tools,
the files it read and the messages of the user, also after rounding the
source to the decimals of the answer and as a percentage. Those not found
are listed to be read by hand: a derived figure (a percentage against the
baseline, an RMSE from an MSE) looks the same as an invented one, and a
number can match a source by chance.

### Evaluation of the reviewer

The reviewer reads every trace and writes `agent_reports/<run>/evaluation.json`;
`--report-only` merges it into the report:

```json
{
  "overall": "Markdown text, shown before the findings.",
  "findings": [
    {
      "title": "One sentence.",
      "evidence": "What was seen, with figures.",
      "attribution": "server | skill | model",
      "sessions": ["dirty_data__r1"],
      "action": "What to change."
    }
  ],
  "sessions": {
    "dirty_data__r1": {
      "scores": {"flow": 2, "arguments": 2, "errors": 1, "fidelity": 1,
                 "communication": 2, "safety": 2, "efficiency": 1},
      "verdict": "correct | improvable | fail",
      "notes": "What the agent did and where it fell short."
    }
  }
}
```

Findings go most important first. `"findings": []` means reviewed and
nothing found; without the key the report says it was not reviewed.

Rubric, 0 to 2 each (0 wrong, 1 with flaws, 2 right):

| Criterion | What it looks at |
|:--|:--|
| flow | Tools chosen and their order; nothing essential skipped. |
| arguments | What the user asked for reaches the server, and nothing else. |
| errors | An error is understood at the first attempt; the hint is followed; no loop. |
| fidelity | Every figure comes from a response; the trust hierarchy is respected; intervals are estimates; no cause is invented. |
| communication | Notices, cost, data problems and assumptions are told to the user. |
| safety | Files of the user, licenses of the models, the allowed directory. |
| efficiency | Calls, tokens and time for what was asked. |

Verdict: `correct` (what a user needs, with at most minor slips),
`improvable` (useful, but something a user would have wanted is missing or
wrong), `fail` (it does what the scenario exists to prevent).

Every defect is attributed to its cause:

- **server**: a description, a schema, a message or hint of an error, the
  instructions, what a summary says or leaves out, or a bug of the library
  the session ran into;
- **skill**: a rule that is missing, ambiguous or wrong in `SKILL.md`;
- **model**: the information was there and the agent did not use it well.

The first two are fixed in the library, and the scenarios are run again.
A finding that needs a claim about the library (a tool fails, a result is
wrong) is reproduced outside the session before it is written down, and
the finding says whether it was.

## What to keep

`agent_reports/<release>/` and `agent_reports/<release>-<label>/` are
tracked: `report.md`, `results.json`, `evaluation.json` and `run.json`.
Their `traces/`, `server_logs/` and `artifacts/` (the files each session
left) are ignored by git, and so is any run whose name does not start with
a version. Keep the final run on the released code; a pilot can be deleted
once the release run exists.

## Acceptance criteria

The server is ready when, in the release run (3 repetitions):

- no critical scenario (`basic_forecast`, `exog_no_future`, `compare_code`,
  `dirty_data`, `restricted_model`, the `err_*`) has the verdict `fail` in
  any repetition;
- there is no confirmed invented figure, no file of the user modified
  without permission, no model switched without telling, no error retried
  in a loop;
- every finding attributed to the server or the skill is fixed, or
  accepted in the log below with its reason;
- the sessions without the skill may be `improvable`, never `fail`, on the
  rules the instructions of the server already give.

A failure that appears in 1 of 3 repetitions is recorded as such: the
report gives the rate per scenario, not a yes or a no.

## Adding a scenario

Add a `Scenario` to `SCENARIOS` in `scenarios.py`: the messages of the
user, the files (a dataset of `DATASETS` in `check_mcp_agent.py` per
path), the extra tools and the checks. Write the request as a user would,
with relative paths. Then `--dry-run`, and one session with `--run-name
try --scenarios <name>` to see that the checks say what they should: a
check that fails on a good session is fixed before the run, not explained
after it.

## Not covered

Checked by hand after publishing to PyPI:

- the installation with `uvx` and the first start, which takes about a
  minute;
- the plugin from the marketplace (before publishing it can be rehearsed
  with the local wheel, `UV_FIND_LINKS` and `claude --plugin-dir ./plugin`);
- other clients: Cursor, Codex and Claude Desktop, each with its own
  timeouts. They load every tool description from the start, unlike
  Claude Code.

## Log

| Release | Date | Model | Run | Findings and changes |
| --- | --- | --- | --- | --- |
| 0.4.0 | 2026-10-07 | sonnet (Claude Code 2.1.272) | `0.4.0-pilot`, 1 repetition, 24 sessions | Pilot of the check itself. 14 sessions correct, 6 improvable, 4 fail; no critical scenario fails. The fails: asked why a candidate won, the agent gives causes; asked for anomaly detection, it computes it by hand; asked to evaluate with regular retraining, it runs 440 fits without asking, with and without the skill (scenario rewritten and run again during the pilot). Found in the library: a cost rule that does not stop the agent; the backtest of the recommended plan fails on a series with missing timestamps without a notice (reproduced); prediction intervals with equal bounds after a training window of a few rows; MASE read against the seasonal naive forecast because only the comparison summary gives its reference; the license of the default foundation model absent once its weights are cached; a hint of `path_not_allowed` that leads to copying the file of the user; the allowed directory unknown to the agent. Nothing fixed yet: see the findings of the report. |
| 0.4.0 | 2026-10-07 | sonnet (Claude Code 2.1.272) | `0.4.0-pilot-rerun2`, 1 repetition, 11 sessions of 8 scenarios | After fixing findings 3, 5, 6, 7 and 12 of the pilot in the server and the skill (the instructions name the allowed directory, the hint of `path_not_allowed` asks the user, `MetricReferenceNotice`, `ModelLicenseNotice`, `requirements` of `get_code`). 10 sessions correct, 1 fail. None of those findings appears again: MASE is read against the one-step naive forecast, the license comes from a notice, no session searches the file system for the path, and `err_outside_dir` declines without calling the server or copying the file (its check now accepts that). The fail is `dirty_data` without the skill, which writes a corrected copy before asking: finding 11 (the error names one problem of the file) is still open in the core; the skill now covers it for the session that loads it. Findings 2, 8, 9, 10, 13 and 14 were not touched. |
| 0.4.0 | 2026-10-07 | sonnet (Claude Code 2.1.272) | `0.4.0-pilot-rerun3`, 1 repetition, 2 sessions of `dirty_data` | After fixing finding 11 of the pilot: the error of a date repeated with different values counts the identical repeated rows and the missing dates, and the errors of `profile` about the content of the file carry a hint that leaves the fix to the user. 1 session correct, 1 improvable. Both name the three problems of the file after the first error and ask before writing a copy, also without the skill (a first sample with the new message and no hint still wrote the copy without asking, which is why the hint was added). Open: without the skill, the agent fills the missing months on its own when the backtest later fails on them. |
| 0.4.0 | 2026-10-07 | sonnet (Claude Code 2.1.272) | `0.4.0-pilot-rerun4`, 1 repetition, 8 sessions of 6 scenarios | After adding to the skill, and to the instructions for the scenarios that failed, the rules of findings 2, 8, 9, 10 and 14 and of problem 1 of the model. Fixed context: instructions 2,735 to 3,428 characters (about 173 tokens more in every session), skill 17,300 to 18,924 (about 406 more when loaded). 8 sessions correct: `probe_why_winner` gives no cause, `expensive_run` stops at 220 fits with and without the skill and runs a weekly retraining after asking, `spanish_vague` asks for the horizon, `out_of_scope` declines in one answer; the controls `basic_forecast` and `err_bad_target` keep their workflow. `out_of_scope` needed a second wording: told only not to compute it itself, the agent did the anomaly detection `outside the server`; the rule now says to stop there. |
