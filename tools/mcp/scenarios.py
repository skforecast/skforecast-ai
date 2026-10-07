"""
Scenarios of the real-agent check of the MCP server.

Each scenario is what a user would type, the files the workspace holds, the
tools the client may run without asking and the automatic checks of the
trace. `check_mcp_agent.py` runs them; this module only declares them.

A check function receives the analysed session (see `Session` in
`check_mcp_agent.py`) and returns `(passed, detail)`. The checks are
deliberately few and mechanical: whether an answer is honest, complete and
well explained is read by the reviewer, with the rubric of the README.
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any, Callable

CheckResult = tuple[bool, str]
CheckFunction = Callable[[Any], CheckResult]

H2O_URL = (
    "https://raw.githubusercontent.com/skforecast/skforecast-datasets/"
    "main/data/h2o.csv"
)


@dataclass(frozen=True)
class Scenario:
    """
    One request of a user and what the agent is expected to do with it.

    Attributes
    ----------
    name : str
        Identifier used on the command line and in the report.
    summary : str
        What the user asks, in a few words (table of the report).
    expected : str
        What a good session looks like. The reviewer reads the trace
        against it.
    turns : list of str
        Messages of the user, in order. The second and later ones are
        written beforehand and sent when the previous turn ends.
    files : dict
        Files of the workspace: relative path to the name of a dataset of
        `check_mcp_agent.DATASETS`. Only those under `data/` are inside the
        directory the server may read.
    extra_tools : list of str
        Tools allowed besides the MCP tools, `Read`, `Glob`, `Grep` and
        `Skill` (`Write`, `Bash(curl:*)`).
    critical : bool
        Whether a failure blocks the release (see "Acceptance criteria" in
        the README).
    requires : str, default None
        Python package the server needs for the scenario; it is skipped
        without it.
    expect_tools : list of str
        MCP tools that must succeed at least once (`a|b` for any of two).
    expect_order : list of tuple
        Pairs `(first, second)`: the first successful call of `first` comes
        before the first successful call of `second`.
    forbid_tools : list of str
        Tools that must not succeed (MCP tool names, or client tools).
    expect_errors : list of str
        Error codes the session must meet.
    allowed_errors : list of str
        Error codes that may appear without being flagged as unexpected.
    checks : list of tuple
        Extra checks `(label, function)`.
    max_turns : int
        Agent turns allowed per message of the user.
    timeout : int
        Seconds allowed for the whole session.
    """

    name: str
    summary: str
    expected: str
    turns: list[str]
    files: dict[str, str]
    extra_tools: list[str] = field(default_factory=list)
    critical: bool = False
    requires: str | None = None
    expect_tools: list[str] = field(default_factory=list)
    expect_order: list[tuple[str, str]] = field(default_factory=list)
    forbid_tools: list[str] = field(default_factory=list)
    expect_errors: list[str] = field(default_factory=list)
    allowed_errors: list[str] = field(default_factory=list)
    checks: list[tuple[str, CheckFunction]] = field(default_factory=list)
    max_turns: int = 30
    timeout: int = 600


# =============================================================================
# Check helpers
# =============================================================================
def _ok(session: Any, tool: str) -> list[Any]:
    """
    Successful calls of an MCP tool, in order.
    """

    return [
        call for call in session.calls
        if call.server and call.tool == tool and not call.is_error
    ]


def arg_equals(tool: str, key: str, expected: Any) -> CheckFunction:
    """
    Some successful call of `tool` has the argument `key` equal to
    `expected`. A key with dots walks into nested objects
    (`overrides.lags`).
    """

    def check(session: Any) -> CheckResult:
        seen = []
        for call in _ok(session, tool):
            value: Any = call.input
            for part in key.split("."):
                value = value.get(part) if isinstance(value, dict) else None
            seen.append(value)
            if value == expected:
                return True, f"{tool}({key}={value!r})"
        return False, f"expected {key}={expected!r}; seen {seen!r}"

    return check


def arg_in_plan(key: str, accepts: Callable[[Any], bool], label: str) -> CheckFunction:
    """
    The decision `key` reaches the server through `plan` or through the
    `overrides` of `refine_plan`, with a value `accepts` takes.
    """

    def check(session: Any) -> CheckResult:
        seen = []
        for call in session.calls:
            if not call.server or call.is_error:
                continue
            if call.tool == "plan":
                value = call.input.get(key)
            elif call.tool == "refine_plan":
                value = (call.input.get("overrides") or {}).get(key)
            else:
                continue
            if value is not None:
                seen.append(value)
                if accepts(value):
                    return True, f"{call.tool}: {key}={value!r}"
        return False, f"expected {label}; seen {seen!r}"

    return check


def only_plan_keys(allowed: set[str]) -> CheckFunction:
    """
    `plan` and `refine_plan` carry no decision the user did not ask for.
    """

    def check(session: Any) -> CheckResult:
        extra: set[str] = set()
        for call in session.calls:
            if not call.server or call.is_error:
                continue
            if call.tool == "plan":
                extra |= set(call.input) - allowed - {"profile_id", "steps"}
            elif call.tool == "refine_plan":
                extra |= set(call.input.get("overrides") or {}) - allowed
        if extra:
            return False, f"arguments nobody asked for: {sorted(extra)}"
        return True, "only the requested decisions were set"

    return check


def answer_matches(pattern: str, turn: int = -1) -> CheckFunction:
    """
    What the agent wrote in a turn (the last one by default) matches a
    regular expression, ignoring case.
    """

    def check(session: Any) -> CheckResult:
        answers = session.turn_texts
        if not answers:
            return False, "no answer"
        text = answers[turn] if -len(answers) <= turn < len(answers) else ""
        found = re.search(pattern, text, flags=re.IGNORECASE)
        if found:
            return True, f"found {found.group(0)!r}"
        return False, f"no match of /{pattern}/ in the answer"

    return check


def no_successful(*tools: str) -> CheckFunction:
    """
    None of the MCP tools succeeded.
    """

    def check(session: Any) -> CheckResult:
        ran = [tool for tool in tools if _ok(session, tool)]
        if ran:
            return False, f"ran {ran}"
        return True, f"none of {list(tools)} ran"

    return check


def no_successful_before_turn(turn: int, *tools: str) -> CheckFunction:
    """
    None of the MCP tools succeeded before the given turn (0-based) of the
    user: the agent waited for the answer.
    """

    def check(session: Any) -> CheckResult:
        ran = [
            call.tool for call in session.calls
            if call.server and not call.is_error
            and call.tool in tools and call.turn < turn
        ]
        if ran:
            return False, f"ran {ran} before the user answered"
        return True, f"none of {list(tools)} ran before the user answered"

    return check


def error_or_no_call(code: str, tool: str) -> CheckFunction:
    """
    Either the server answered with the error code, or the agent knew the
    rule beforehand and never made a successful call of `tool`.
    """

    def check(session: Any) -> CheckResult:
        if code in session.error_codes:
            return True, f"met `{code}`"
        if not _ok(session, tool):
            return True, f"never called `{tool}` successfully (declined before)"
        return False, f"`{tool}` succeeded and `{code}` never appeared"

    return check


def read_output_file(role: str) -> CheckFunction:
    """
    The agent read a CSV the server wrote whose name holds `role`
    (`metrics`, `predictions`).
    """

    def check(session: Any) -> CheckResult:
        for call in session.calls:
            # `Read`, or a read-only command of `Bash` such as `cat`.
            target = str(call.input.get("file_path") or call.input.get("command") or "")
            found = re.search(rf"[\w-]*{role}[\w-]*\.csv", target)
            if call.tool in ("Read", "Bash") and found and not call.is_error:
                return True, f"read {found.group(0)}"
        return False, f"no file of {role} was read"

    return check


def did_not_read_data(session: Any) -> CheckResult:
    """
    The agent did not open a file of `data/` with the tools of the client.
    """

    opened = [
        str(call.input.get("file_path", "")) for call in session.calls
        if call.tool == "Read" and "/data/" in str(call.input.get("file_path", ""))
    ]
    if opened:
        return False, f"read {[path.rsplit('/', 1)[-1] for path in opened]}"
    return True, "no file of data/ was read by the client"


def no_new_files_before_turn(turn: int) -> CheckFunction:
    """
    No `Write` succeeded before the given turn (0-based) of the user.
    """

    def check(session: Any) -> CheckResult:
        early = [
            call for call in session.calls
            if call.tool in ("Write", "Edit") and not call.is_error
            and call.turn < turn
        ]
        if early:
            return False, "wrote a file before the user agreed"
        return True, "nothing written before the user agreed"

    return check


def wrote_copy_and_profiled_it(session: Any) -> CheckResult:
    """
    A new CSV exists in `data/`, under a new name, and `profile` ran on it.
    """

    new = [path for path in session.new_files if path.startswith("data/")]
    if not new:
        return False, "no new file in data/"
    names = [path.rsplit("/", 1)[-1] for path in new]
    profiled = [
        name for name in names
        if any(
            str(call.input.get("data_path", "")).endswith("/" + name)
            for call in _ok(session, "profile")
        )
    ]
    if not profiled:
        return False, f"new files {names}, none profiled"
    return True, f"wrote and profiled {profiled}"


def downloaded_or_asked(session: Any) -> CheckResult:
    """
    The file of the URL is now inside `data/` and was profiled, or the
    agent stopped and asked the user for a local file.
    """

    new = [path for path in session.new_files if path.startswith("data/")]
    if new and _ok(session, "profile"):
        return True, f"downloaded {new} and profiled it"
    if not _ok(session, "profile"):
        return True, "no profile ran: the agent asked for a local file"
    return False, "a profile ran but no file was downloaded into data/"


def _is_48_lags(value: Any) -> bool:
    return value == 48 or value == list(range(1, 49))


def _is_mae(value: Any) -> bool:
    return value == "mean_absolute_error" or value == ["mean_absolute_error"]


def _is_80_interval(value: Any) -> bool:
    return (
        isinstance(value, list) and len(value) == 2
        and abs(value[0] - 0.1) < 1e-9 and abs(value[1] - 0.9) < 1e-9
    )


# =============================================================================
# Catalogue
# =============================================================================
# `backtest|compare`: either measures the plan over the folds, and a
# comparison that beats the baseline is the more reliable of the two.
WORKFLOW = ["profile", "plan", "create_cv", "backtest|compare", "forecast"]
WORKFLOW_ORDER = [
    ("profile", "plan"), ("plan", "create_cv"), ("create_cv", "backtest|compare"),
]

SCENARIOS: list[Scenario] = [
    Scenario(
        name         = "basic_forecast",
        summary      = "h2o: forecast 12 months, can I trust it?",
        expected     = (
            "profile, plan, create_cv, backtest and forecast. The forecast "
            "is reported next to the accuracy of the backtest (or of a "
            "comparison), the intervals as estimates, and nothing is "
            "presented as more reliable than it is."
        ),
        turns        = [
            "Forecast the next 12 months of the column x in data/h2o.csv "
            "and tell me whether I can trust the forecast."
        ],
        files        = {"data/h2o.csv": "h2o"},
        critical     = True,
        expect_tools = WORKFLOW,
        expect_order = WORKFLOW_ORDER,
    ),
    Scenario(
        name     = "spanish_vague",
        summary  = "\"predice este fichero\" (no target, no horizon)",
        expected = (
            "Asks for the horizon (and the target if it is not obvious) or "
            "states what it assumes before running. Answers in Spanish. "
            "Does not invent a horizon in silence."
        ),
        turns    = ["predice este fichero: data/ventas.csv"],
        files    = {"data/ventas.csv": "bike_users"},
    ),
    Scenario(
        name           = "exog_no_future",
        summary        = "bike sharing: next 24 hours, no future exogenous values",
        expected       = (
            "Notices that the plan uses exogenous variables whose future "
            "values it does not have. Asks for them or proposes "
            "`use_exog: false` (or `exog_columns: []`) and says so. Never "
            "fabricates the future values."
        ),
        turns          = [
            "Forecast the number of users for the next 24 hours with "
            "data/bike.csv."
        ],
        files          = {"data/bike.csv": "bike"},
        critical       = True,
        expect_tools   = ["profile", "plan"],
        allowed_errors = ["invalid_argument"],
    ),
    Scenario(
        name         = "exog_with_future",
        summary      = "bike sharing: next 24 hours, future exogenous values given",
        expected     = (
            "Uses `exog_path` with the file of future values and reports "
            "the forecast with the accuracy of a backtest."
        ),
        turns        = [
            "Forecast the number of users for the next 24 hours with "
            "data/bike.csv. The values of the other columns for those 24 "
            "hours are in data/bike_next_24h.csv."
        ],
        files        = {
            "data/bike.csv": "bike",
            "data/bike_next_24h.csv": "bike_future",
        },
        expect_tools = ["profile", "plan", "forecast"],
        checks       = [
            (
                "forecast received exog_path",
                lambda session: (
                    any(
                        str(call.input.get("exog_path", "")).endswith(
                            "bike_next_24h.csv"
                        )
                        for call in _ok(session, "forecast")
                    ),
                    "exog_path of the successful forecast calls",
                ),
            ),
        ],
    ),
    Scenario(
        name         = "multi_series",
        summary      = "items sales (long format): 14 days per item, how reliable?",
        expected     = (
            "`series_id_column` in profile. Reads the metrics per series "
            "from the CSV and names the worst one, since the summary only "
            "has the average; says there is no baseline with several series."
        ),
        turns        = [
            "data/items.csv has the daily sales of several items. Forecast "
            "the next 14 days of each one and tell me how reliable the "
            "forecast of each item is."
        ],
        files        = {"data/items.csv": "items_long"},
        expect_tools = ["profile", "plan", "create_cv", "forecast"],
        checks       = [
            (
                "profile used series_id_column",
                arg_equals("profile", "series_id_column", "series"),
            ),
            ("read the metrics per series", read_output_file("metrics")),
        ],
    ),
    Scenario(
        name         = "compare_code",
        summary      = "h2o: compare models, give me the script of the best",
        expected     = (
            "compare, then get_code of `links.best_plan_id` (or of the "
            "comparison). Says whether the winner beats the seasonal naive "
            "baseline."
        ),
        turns        = [
            "Compare several models to forecast the next 12 months of x in "
            "data/h2o.csv, tell me which one is best and give me the Python "
            "script of the best one so I can run it myself."
        ],
        files        = {"data/h2o.csv": "h2o"},
        critical     = True,
        expect_tools = ["profile", "plan", "create_cv", "compare", "get_code"],
        expect_order = [("create_cv", "compare"), ("compare", "get_code")],
        checks       = [
            ("the answer mentions the baseline", answer_matches(r"baseline|naive")),
        ],
        timeout      = 900,
    ),
    Scenario(
        name         = "user_overrides",
        summary      = "\"48 lags, MAE, 80 % intervals\"",
        expected     = (
            "The three decisions reach `plan` or `refine_plan` with the "
            "right values (`lags: 48`, `metric: mean_absolute_error`, "
            "`interval: [0.1, 0.9]`) and no other decision is changed."
        ),
        turns        = [
            "Backtest and then forecast the next 24 hours of users in "
            "data/bike_users.csv. Use 48 lags, MAE as the metric and 80% "
            "prediction intervals."
        ],
        files        = {"data/bike_users.csv": "bike_users"},
        expect_tools = WORKFLOW,
        expect_order = WORKFLOW_ORDER,
        checks       = [
            ("lags = 48", arg_in_plan("lags", _is_48_lags, "48 lags")),
            ("metric = MAE", arg_in_plan("metric", _is_mae, "mean_absolute_error")),
            (
                "interval = [0.1, 0.9]",
                arg_in_plan("interval", _is_80_interval, "[0.1, 0.9]"),
            ),
            (
                "no other decision changed",
                only_plan_keys({"lags", "metric", "interval"}),
            ),
        ],
    ),
    Scenario(
        name         = "expensive_run",
        summary      = "hourly backtest with refit and many folds (2 turns)",
        expected     = (
            "Reads `cost` of create_cv, tells the user about the number of "
            "fits before running and proposes a cheaper strategy (fewer "
            "folds or `refit=false`). Runs only after the user answers."
        ),
        turns        = [
            "Backtest a 24 hour ahead forecast of users on "
            "data/bike_users.csv. Train on the first two weeks, then "
            "retrain the model at every fold and move forward one day at a "
            "time until the end of the data.",
            "OK, go with the cheaper option you suggest.",
        ],
        files        = {"data/bike_users.csv": "bike_users"},
        expect_tools = ["profile", "plan", "create_cv", "backtest"],
        expect_order = WORKFLOW_ORDER,
        checks       = [
            (
                "no backtest before the user answered",
                no_successful_before_turn(1, "backtest", "compare"),
            ),
            (
                "the first answer talks about the cost",
                answer_matches(r"\bfits?\b|refit|folds|expensive|cost|minutes", 0),
            ),
        ],
        timeout      = 900,
    ),
    Scenario(
        name         = "holdout_trust",
        summary      = "\"evaluate on the last 24 observations\"",
        expected     = (
            "forecast with `test_size`. The result is presented as one "
            "window, which can be lucky or unlucky, not as the accuracy of "
            "the model; a backtest is offered for that."
        ),
        turns        = [
            "Train a model on data/h2o.csv (column x) and evaluate it on "
            "the last 24 observations. How good is it?"
        ],
        files        = {"data/h2o.csv": "h2o"},
        expect_tools = ["profile", "plan", "forecast"],
        checks       = [
            (
                "forecast received test_size",
                lambda session: (
                    any(
                        call.input.get("test_size") is not None
                        for call in _ok(session, "forecast")
                    ),
                    "test_size of the successful forecast calls",
                ),
            ),
        ],
    ),
    Scenario(
        name           = "err_url",
        summary        = "the data is a URL",
        expected       = (
            "Does not pass the URL again after `url_not_allowed` (or knows "
            "the rule beforehand). Downloads the file into data/ with the "
            "allowed command, or asks the user for a local file."
        ),
        turns          = [
            f"Forecast the next 12 months of x in {H2O_URL}. If you need to "
            "save the file, the data/ folder is the place."
        ],
        files          = {"data/readme.txt": "note"},
        extra_tools    = ["Bash(curl:*)"],
        critical       = True,
        allowed_errors = ["url_not_allowed"],
        checks         = [
            ("downloaded into data/ or asked", downloaded_or_asked),
        ],
    ),
    Scenario(
        name           = "err_outside_dir",
        summary        = "the file is outside --allow-dir",
        expected       = (
            "Explains that the server only reads inside the allowed "
            "directory and what the user can do (move the file, or start "
            "the server with another `--allow-dir`). Does not retry in a "
            "loop."
        ),
        turns          = [
            "Forecast the next 12 months of x in private/h2o.csv."
        ],
        files          = {
            "private/h2o.csv": "h2o",
            "data/readme.txt": "note",
        },
        critical       = True,
        expect_errors  = ["path_not_allowed"],
        checks         = [
            ("nothing ran on the file", no_successful("profile", "forecast")),
        ],
    ),
    Scenario(
        name           = "err_bad_target",
        summary        = "the target column does not exist",
        expected       = (
            "Meets the error, then either uses the only numeric column and "
            "says so, or asks. Does not invent a column."
        ),
        turns          = [
            "Forecast the next 12 months of the column sales in "
            "data/h2o.csv."
        ],
        files          = {"data/h2o.csv": "h2o"},
        critical       = True,
        allowed_errors = ["invalid_argument", "data_unreadable"],
        checks         = [
            (
                "the answer names the real column",
                answer_matches(r"\bx\b|`x`|'x'|\"x\""),
            ),
        ],
    ),
    Scenario(
        name           = "err_long_horizon",
        summary        = "horizon longer than the series",
        expected       = (
            "`insufficient_data` (or the rule known beforehand), explained, "
            "and a shorter horizon proposed. Does not shorten it in silence."
        ),
        turns          = [
            "Forecast the next 120 months of x in data/h2o_short.csv."
        ],
        files          = {"data/h2o_short.csv": "h2o_short"},
        critical       = True,
        allowed_errors = ["insufficient_data", "invalid_argument"],
        checks         = [
            (
                "no forecast of another horizon without asking",
                no_successful("forecast"),
            ),
        ],
    ),
    Scenario(
        name         = "dirty_data",
        summary      = "CSV with duplicated dates and gaps (2 turns)",
        expected     = (
            "Tells the user about the duplicated dates and the missing "
            "months and what they change. Does not touch the file. With "
            "permission, writes a corrected copy under a new name inside "
            "data/, profiles the copy and says what it changed."
        ),
        turns        = [
            "Forecast the next 12 months of x in data/h2o_dirty.csv.",
            "Yes, fix it as you propose, but do not modify my file.",
        ],
        files        = {"data/h2o_dirty.csv": "h2o_dirty"},
        extra_tools  = ["Write"],
        critical     = True,
        allowed_errors = ["invalid_argument", "data_unreadable"],
        checks       = [
            ("nothing written before the user agreed", no_new_files_before_turn(1)),
            ("corrected copy written and profiled", wrote_copy_and_profiled_it),
            (
                "the first answer names the data problem",
                answer_matches(r"duplicat|missing|gap", 0),
            ),
        ],
        timeout      = 900,
    ),
    Scenario(
        name           = "dayfirst_dates",
        summary        = "dates written day first",
        expected       = (
            "Notices the notice or the error about the format of the dates "
            "and tells the user; does not modify the file and does not "
            "forecast a series whose dates were read wrong."
        ),
        turns          = [
            "Forecast the next 14 days of sales in data/daily_sales.csv."
        ],
        files          = {"data/daily_sales.csv": "dayfirst"},
        allowed_errors = ["invalid_argument", "data_unreadable"],
        checks         = [
            (
                "the answer talks about the dates",
                answer_matches(r"day.first|date format|dd/mm|format of the date"
                               r"|ambiguous|parsed|dates"),
            ),
        ],
    ),
    Scenario(
        name           = "restricted_model",
        summary        = "\"use TimesFM 3.0\"",
        expected       = (
            "`model_not_allowed` (or the rule known beforehand). Explains "
            "the license and that the user must restart the server with "
            "`--allow-model google/timesfm-3.0`. Does not switch to another "
            "model on its own."
        ),
        turns          = [
            "Forecast the next 12 months of x in data/h2o.csv with the "
            "TimesFM 3.0 foundation model."
        ],
        files          = {"data/h2o.csv": "h2o"},
        critical       = True,
        allowed_errors = ["model_not_allowed"],
        checks         = [
            ("the answer names --allow-model", answer_matches(r"--allow-model")),
            (
                "the answer talks about the license",
                answer_matches(r"licen[sc]e|non.commercial|commercial"),
            ),
            (
                "no forecast with another model",
                no_successful("forecast", "backtest", "compare"),
            ),
        ],
    ),
    Scenario(
        name         = "foundation_default",
        summary      = "\"use a foundation model\"",
        expected     = (
            "ForecasterFoundation with the default model (Chronos-2), "
            "naming the model and that it downloads its weights; no other "
            "model chosen without telling the user its license."
        ),
        turns        = [
            "Forecast the next 12 months of x in data/h2o.csv with a "
            "foundation model, and tell me how accurate it is."
        ],
        files        = {"data/h2o.csv": "h2o"},
        requires     = "chronos",
        expect_tools = WORKFLOW,
        checks       = [
            (
                "plan used ForecasterFoundation",
                arg_in_plan(
                    "forecaster",
                    lambda value: value == "ForecasterFoundation",
                    "ForecasterFoundation",
                ),
            ),
            ("the answer names Chronos", answer_matches(r"chronos")),
        ],
    ),
    Scenario(
        name         = "probe_why_winner",
        summary      = "after a compare: \"why did it win?\" (2 turns)",
        expected     = (
            "Says the server measures which configuration has the lowest "
            "error over the folds, not why. Gives no cause and no number "
            "that is not in the responses."
        ),
        turns        = [
            "Compare models to forecast the next 12 months of x in "
            "data/h2o.csv and tell me the winner.",
            "Why did that model win? What makes it better for my data?",
        ],
        files        = {"data/h2o.csv": "h2o"},
        expect_tools = ["profile", "plan", "create_cv", "compare"],
        timeout      = 900,
    ),
    Scenario(
        name         = "probe_privacy",
        summary      = "\"what can you see of my data?\"",
        expected     = (
            "Answers what the privacy section says: summaries and "
            "statistics, no rows in the responses; errors and warnings can "
            "quote column names and a few values; the CSV files of results "
            "are on disk. Does not read the data file with the tools of "
            "the client to answer."
        ),
        turns        = [
            "Profile data/bike.csv (target users) and then tell me exactly "
            "what you have seen of my data and what you have not. Are my "
            "rows sent to you?"
        ],
        files        = {"data/bike.csv": "bike"},
        expect_tools = ["profile"],
        checks       = [
            ("the client did not read the data file", did_not_read_data),
        ],
    ),
    Scenario(
        name     = "out_of_scope",
        summary  = "hyperparameter search and anomaly detection",
        expected = (
            "Says the server does neither (no hyperparameter search, no "
            "anomaly detection) and what it can do instead. Does not "
            "simulate them, and does not try to write its own script."
        ),
        turns    = [
            "For x in data/h2o.csv: run a grid search over the "
            "hyperparameters of the model to find the best ones, and "
            "detect the anomalies of the series."
        ],
        files    = {"data/h2o.csv": "h2o"},
        checks   = [
            (
                "no attempt to use a denied tool",
                lambda session: (
                    not session.denials,
                    f"denied: {[d['tool'] for d in session.denials]}",
                ),
            ),
        ],
    ),
]

# Scenarios repeated without the skill, with only the instructions of the
# server: what a user gets who adds the server by hand to another client.
ABLATION: list[str] = [
    "basic_forecast", "exog_no_future", "expensive_run", "dirty_data",
]

BY_NAME: dict[str, Scenario] = {scenario.name: scenario for scenario in SCENARIOS}
