"""
Check the MCP server with a real agent.

Launches headless Claude Code sessions against the local server, one per
scenario of `scenarios.py`, each in a clean folder outside the repository
with only the server and (optionally) its skill. It keeps the raw trace of
every session and writes a report with the steps between the model and the
server, the automatic checks, the numbers of the answers that are in no
response, and the evaluation of the reviewer.

It is a manual, pre-release tool: it spends the usage quota of the Claude
subscription the CLI is logged in with (never an API key), needs network
access and its answers are not deterministic. See `README.md`.

Usage (from the repository root, inside the project environment)::

    python tools/mcp/check_mcp_agent.py --dry-run
    python tools/mcp/check_mcp_agent.py --list
    python tools/mcp/check_mcp_agent.py --run-name pilot --scenarios basic_forecast
    python tools/mcp/check_mcp_agent.py --run-name 0.4.0 --reps 3
    python tools/mcp/check_mcp_agent.py --run-name 0.4.0 --report-only

Launching the same `--run-name` again resumes it: every scenario and
repetition that already has a finished trace is skipped.
"""

from __future__ import annotations
import argparse
import dataclasses
import datetime as dt
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import queue
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scenarios import ABLATION, BY_NAME, SCENARIOS, Scenario  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
REPORTS_DIR = Path(__file__).resolve().parent / "agent_reports"
SKILL_NAME = "skforecast-ai-forecasting"
SKILL_DIR = REPO_ROOT / "skforecast_ai" / "mcp" / "skills" / SKILL_NAME
SERVER_NAME = "skforecast-ai"
TOOL_PREFIX = f"mcp__{SERVER_NAME}__"
BASE_TOOLS = [f"{TOOL_PREFIX}*", "Read", "Glob", "Grep", "Skill"]
# Tools of the client that hand the work to a subagent, removed from every
# session: its calls are not in the trace, it wrote files the session was
# not allowed to, and launched in the background it ends the turn with a
# promise instead of an answer.
SUBAGENT_TOOLS = ["Agent", "Task", "Workflow"]
# Tools of the client whose arguments and results the report shows. Any
# other one (a tool that reaches other sessions of the machine, the web or
# the account of whoever runs the check) is named in the timeline with its
# argument names only: what it returns is not about the server and can hold
# data of the person who launched the run.
SHOWN_CLIENT_TOOLS = ("Read", "Glob", "Grep", "Bash", "Write", "Skill", "ToolSearch")

# Variables that would make a nested session pay through an API key or
# another provider, or tie it to the session that launched the runner.
ENV_PREFIXES = (
    "ANTHROPIC_", "CLAUDE_", "CLAUDECODE", "OPENAI_", "GOOGLE_", "GEMINI_",
    "AWS_", "AZURE_", "MISTRAL_", "GROQ_", "VERTEX", "BEDROCK",
)
ENV_NAMES = ("AI_AGENT",)

FINISHED = ("completed", "timeout", "max_turns", "budget")
LIMIT_TEXT = re.compile(
    r"hit your (usage )?limit|usage limit|limit reached|rate.?limit", re.IGNORECASE
)
LIMIT_REASONS = (
    "rate_limit", "rate_limited", "usage_limit", "usage_limited", "blocking_limit",
)
RUBRIC = [
    "flow", "arguments", "errors", "fidelity", "communication", "safety",
    "efficiency",
]


# =============================================================================
# Datasets
# =============================================================================
_FRAMES: dict[str, Any] = {}


def _fetch(name: str) -> Any:
    """
    A skforecast dataset, downloaded once per run.
    """

    if name not in _FRAMES:
        from skforecast.datasets import fetch_dataset

        _FRAMES[name] = fetch_dataset(name, raw=True, verbose=False)
    return _FRAMES[name].copy()


def _h2o() -> Any:
    return _fetch("h2o")[["fecha", "x"]]


def _h2o_dirty() -> Any:
    """
    The last 120 months of h2o with three months removed, one row repeated
    as it is and one date repeated with another value.
    """

    import pandas as pd

    data = _h2o().tail(120).reset_index(drop=True)
    conflicting = data.iloc[[90]].assign(x=lambda frame: (frame["x"] * 1.1).round(6))
    data = pd.concat(
        [data.iloc[:51], data.iloc[[50]], data.iloc[51:91], conflicting, data.iloc[91:]]
    )
    return data.drop(index=[30, 31, 75]).reset_index(drop=True)


def _bike(with_future: bool = False) -> Any:
    """
    90 days of hourly bike sharing users with three exogenous columns. The
    24 hours that follow are the file of future exogenous values.
    """

    data = _fetch("bike_sharing")
    data = data[["date_time", "users", "holiday", "weather", "temp"]]
    data = data.tail(24 * 90 + 24).reset_index(drop=True)
    if with_future:
        return data.tail(24).drop(columns="users")
    return data.iloc[:-24]


def _items_long() -> Any:
    data = _fetch("items_sales").tail(400)
    return data.melt(id_vars="date", var_name="series", value_name="value")


def _dayfirst() -> Any:
    """
    200 days of synthetic sales whose dates are written day first
    (`13/01/2024`), with a weekly pattern.
    """

    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(123)
    index = pd.date_range("2024-01-01", periods=200, freq="D")
    sales = 100 + 20 * (index.dayofweek >= 5) + rng.normal(0, 5, len(index))
    return pd.DataFrame(
        {"date": index.strftime("%d/%m/%Y"), "sales": sales.round(2)}
    )


DATASETS: dict[str, Any] = {
    "h2o": _h2o,
    "h2o_short": lambda: _h2o().tail(60),
    "h2o_dirty": _h2o_dirty,
    "bike": _bike,
    "bike_future": lambda: _bike(with_future=True),
    "bike_users": lambda: _bike()[["date_time", "users"]],
    # Two years of hours: a backtest that retrains at every fold takes
    # minutes, so the cost rule has something real to warn about.
    "bike_two_years": lambda: _fetch("bike_sharing")[["date_time", "users"]],
    "items_long": _items_long,
    "dayfirst": _dayfirst,
    "note": lambda: "Put the CSV files to forecast in this folder.\n",
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hashes(root: Path, skip: tuple[str, ...] = ("out", ".claude")) -> dict[str, str]:
    """
    Hash of every file of the workspace the user owns (not what the server
    writes, nor the configuration of the client).
    """

    return {
        str(path.relative_to(root)): _sha(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
        and path.relative_to(root).parts[0] not in skip
        and path.name not in ("mcp.json", "server.log")
    }


# =============================================================================
# Workspace and session
# =============================================================================
def clean_environment() -> dict[str, str]:
    """
    Environment of a nested session: no API key of any provider and nothing
    of the session that launched the runner, so the CLI can only use the
    subscription it is logged in with.
    """

    env = {
        key: value for key, value in os.environ.items()
        if not key.startswith(ENV_PREFIXES) and key not in ENV_NAMES
    }
    env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"
    return env


def check_subscription() -> dict[str, Any]:
    """
    Stop unless the CLI is logged in with a Claude subscription.
    """

    done = subprocess.run(
        ["claude", "auth", "status"], env=clean_environment(),
        capture_output=True, text=True, timeout=60,
    )
    try:
        status = json.loads(done.stdout)
    except ValueError:
        sys.exit(f"`claude auth status` gave no JSON:\n{done.stdout}{done.stderr}")
    if not status.get("loggedIn") or status.get("authMethod") != "claude.ai":
        sys.exit(
            "The CLI is not logged in with a Claude subscription "
            f"(authMethod={status.get('authMethod')!r}). Nothing was launched."
        )
    return status


def prepare_workspace(scenario: Scenario, with_skill: bool) -> Path:
    """
    A clean folder outside the repository with the files of the scenario,
    the output directory of the server, the MCP configuration and, when
    asked, the skill. The agent sees neither `AGENTS.md` nor the code.
    """

    root = Path(os.path.realpath(tempfile.mkdtemp(prefix="skfai_mcp_")))
    (root / "data").mkdir()
    (root / "out").mkdir()
    for relative, dataset in scenario.files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        content = DATASETS[dataset]()
        if isinstance(content, str):
            path.write_text(content, encoding="utf-8")
        else:
            content.to_csv(path, index=False)
    if with_skill:
        shutil.copytree(SKILL_DIR, root / ".claude" / "skills" / SKILL_NAME)
    (root / "mcp.json").write_text(
        json.dumps(server_config(root), indent=2), encoding="utf-8"
    )
    return root


def server_config(root: Path) -> dict[str, Any]:
    """
    MCP configuration of the client: the server of this checkout, reading
    `data/` and writing to `out/`, with its stderr kept in `server.log`.
    """

    command = (
        f"exec {shlex.quote(sys.executable)} -m skforecast_ai mcp "
        f"--allow-dir {shlex.quote(str(root / 'data'))} "
        f"--output-dir {shlex.quote(str(root / 'out'))} "
        f"2>>{shlex.quote(str(root / 'server.log'))}"
    )
    return {
        "mcpServers": {
            SERVER_NAME: {
                "command": "/bin/sh",
                "args": ["-c", command],
                "env": {"PYTHONPATH": str(REPO_ROOT)},
            }
        }
    }


def session_command(
    scenario: Scenario, model: str, max_budget: float | None
) -> list[str]:
    """
    Command of one session. The messages of the user go through stdin as
    `stream-json`, so every turn runs in the same process and against the
    same server: its ids stay valid, as in an interactive session.
    """

    command = [
        "claude", "-p",
        "--input-format", "stream-json",
        "--output-format", "stream-json", "--verbose",
        "--mcp-config", "mcp.json", "--strict-mcp-config",
        "--setting-sources", "project",
        "--permission-mode", "default",
        "--permission-prompts", "none",
        "--no-session-persistence",
        "--model", model,
        "--max-turns", str(scenario.max_turns),
        "--allowedTools", *BASE_TOOLS, *scenario.extra_tools,
        # A subagent runs outside the trace, with permissions of its own.
        "--disallowedTools", *SUBAGENT_TOOLS,
    ]
    if max_budget:
        command += ["--max-budget-usd", str(max_budget)]
    return command


def _kill(process: subprocess.Popen) -> None:
    """
    End the session and the server it started (same process group).
    """

    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=10)
            return
        except subprocess.TimeoutExpired:
            continue


def _limit_hit(event: dict[str, Any]) -> bool:
    """
    Whether an event says the usage limit of the subscription was reached.
    """

    if event.get("type") == "rate_limit_event":
        return (event.get("rate_limit_info") or {}).get("status") == "rejected"
    if event.get("type") == "result" and event.get("is_error"):
        if event.get("api_error_status") == 429:
            return True
        if event.get("terminal_reason") in LIMIT_REASONS:
            return True
        texts = [str(event.get("result") or ""), *map(str, event.get("errors") or [])]
        return any(LIMIT_TEXT.search(text) for text in texts)
    return False


def run_session(
    scenario: Scenario,
    root: Path,
    trace_path: Path,
    model: str,
    max_budget: float | None,
) -> dict[str, Any]:
    """
    Run one session and write its raw trace, one event per line, with the
    lines the runner adds (`"type": "runner"`) for each message of the user.

    Returns
    -------
    outcome : dict
        `status` (`completed`, `timeout`, `max_turns`, `budget`,
        `usage_limit`, `provider_error`, `auth_error`, `crashed`), the wall
        time, the seconds at which each line arrived and the last rate
        limit information.
    """

    command = session_command(scenario, model, max_budget)
    stderr_path = trace_path.with_name(
        trace_path.name.removesuffix(".partial.jsonl") + ".stderr"
    )
    start = time.monotonic()
    deadline = start + scenario.timeout
    lines: queue.Queue = queue.Queue()
    seconds: list[float] = []
    status = "completed"
    rate_limit: dict[str, Any] | None = None

    with open(stderr_path, "w") as stderr, open(trace_path, "w") as trace:
        process = subprocess.Popen(
            command, cwd=root, env=clean_environment(), text=True,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr,
            start_new_session=True,
        )

        def pump() -> None:
            for line in process.stdout:
                lines.put(line)
            lines.put(None)

        threading.Thread(target=pump, daemon=True).start()

        def record(line: str) -> None:
            trace.write(line if line.endswith("\n") else line + "\n")
            trace.flush()
            seconds.append(round(time.monotonic() - start, 2))

        def wait_for_result() -> str:
            nonlocal rate_limit
            assistant_messages = 0
            while True:
                try:
                    line = lines.get(timeout=max(0.1, deadline - time.monotonic()))
                except queue.Empty:
                    return "timeout"
                if line is None:
                    return "crashed"
                record(line)
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                kind = event.get("type")
                if kind == "system" and event.get("subtype") == "init":
                    if event.get("apiKeySource") not in (None, "none"):
                        return "auth_error"
                if kind == "rate_limit_event":
                    rate_limit = event.get("rate_limit_info")
                if _limit_hit(event):
                    return "usage_limit"
                if kind == "assistant":
                    # Backstop of `--max-turns`, should the CLI not stop.
                    assistant_messages += 1
                    if assistant_messages > 4 * scenario.max_turns:
                        return "max_turns"
                if kind == "result":
                    if event.get("subtype") == "error_max_turns":
                        return "max_turns"
                    if event.get("subtype") == "error_max_budget_usd":
                        return "budget"
                    if event.get("is_error"):
                        return "provider_error"
                    return "completed"
                if time.monotonic() > deadline:
                    return "timeout"

        try:
            for index, text in enumerate(scenario.turns):
                record(json.dumps({
                    "type": "runner", "subtype": "user_turn", "turn": index,
                    "text": text,
                }))
                message = {
                    "type": "user",
                    "message": {"role": "user", "content": text},
                }
                try:
                    process.stdin.write(json.dumps(message) + "\n")
                    process.stdin.flush()
                except BrokenPipeError:
                    status = "crashed"
                    break
                status = wait_for_result()
                if status != "completed":
                    break
            try:
                process.stdin.close()
            except BrokenPipeError:
                pass
            if status == "completed":
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    pass
        finally:
            _kill(process)

    return {
        "status": status,
        "wall_seconds": round(time.monotonic() - start, 1),
        "event_seconds": seconds,
        "rate_limit": rate_limit,
        "command": command,
    }


# =============================================================================
# Trace analysis
# =============================================================================
@dataclass
class Call:
    """
    One tool call of the agent with its result.
    """

    index: int
    turn: int
    tool: str
    server: bool
    input: dict[str, Any]
    id: str
    text: str = ""
    is_error: bool = False
    denied: bool = False
    code: str | None = None
    error: dict[str, Any] | None = None
    response: dict[str, Any] | None = None
    seconds: float | None = None
    started: float | None = None


@dataclass
class Session:
    """
    One analysed session: what the report and the checks read.
    """

    key: str
    scenario: Scenario
    with_skill: bool
    rep: int
    meta: dict[str, Any]
    init: dict[str, Any] = field(default_factory=dict)
    steps: list[tuple[str, Any]] = field(default_factory=list)
    calls: list[Call] = field(default_factory=list)
    answers: list[str] = field(default_factory=list)
    turn_texts: list[str] = field(default_factory=list)
    results: list[dict[str, Any]] = field(default_factory=list)
    denials: list[dict[str, Any]] = field(default_factory=list)
    checks: list[dict[str, str]] = field(default_factory=list)
    unsourced: list[dict[str, str]] = field(default_factory=list)
    artifacts: str = ""

    @property
    def status(self) -> str:
        return self.meta["status"]

    @property
    def root(self) -> str:
        return self.meta["workspace"]

    @property
    def error_codes(self) -> list[str]:
        return [call.code for call in self.calls if call.code]

    @property
    def new_files(self) -> list[str]:
        before = self.meta["files_before"]
        return [path for path in self.meta["files_after"] if path not in before]

    @property
    def changed_files(self) -> list[str]:
        after = self.meta["files_after"]
        return [
            path for path, digest in self.meta["files_before"].items()
            if after.get(path) != digest
        ]

    @property
    def server_calls(self) -> list[Call]:
        return [call for call in self.calls if call.server]

    @property
    def usage(self) -> dict[str, Any]:
        """
        Tokens and equivalent cost of the session (the last result event
        carries the totals), agent turns and time inside the CLI.
        """

        totals = {
            "input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0,
            "cache_creation_tokens": 0, "cost_usd": 0.0,
        }
        if self.results:
            last = self.results[-1]
            totals["cost_usd"] = round(last.get("total_cost_usd") or 0.0, 4)
            for usage in (last.get("modelUsage") or {}).values():
                totals["input_tokens"] += usage.get("inputTokens", 0)
                totals["output_tokens"] += usage.get("outputTokens", 0)
                totals["cache_read_tokens"] += usage.get("cacheReadInputTokens", 0)
                totals["cache_creation_tokens"] += usage.get(
                    "cacheCreationInputTokens", 0
                )
        totals["agent_turns"] = sum(r.get("num_turns") or 0 for r in self.results)
        totals["wall_seconds"] = self.meta["wall_seconds"]
        return totals


def _block_text(content: Any) -> str:
    """
    Text of the content of a tool result (a string or a list of blocks).
    """

    if isinstance(content, str):
        return content
    parts = []
    for block in content or []:
        if isinstance(block, dict):
            if block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif block.get("type") == "tool_reference":
                parts.append(f"tool_reference: {block.get('tool_name')}")
            else:
                parts.append(json.dumps(block))
        else:
            parts.append(str(block))
    return "\n".join(parts)


def parse_trace(key: str, scenario: Scenario, meta: dict[str, Any], path: Path) -> Session:
    """
    Read a raw trace into a `Session`.
    """

    session = Session(
        key=key, scenario=scenario, with_skill=meta["with_skill"],
        rep=meta["rep"], meta=meta,
    )
    by_id: dict[str, Call] = {}
    times = meta.get("event_seconds") or []
    turn = -1
    turn_texts: list[str] = []

    # One event per "\n", as `record` wrote them: `splitlines` would also cut
    # an event at a line separator inside its text (U+2028, U+0085), which
    # JSON does not escape, and shift every later event against its time.
    for number, line in enumerate(path.read_text(encoding="utf-8").split("\n")):
        try:
            event = json.loads(line)
        except ValueError:
            continue
        at = times[number] if number < len(times) else None
        kind = event.get("type")
        if kind == "runner" and event.get("subtype") == "user_turn":
            turn = event["turn"]
            turn_texts = []
            session.steps.append(("user", event["text"]))
        elif kind == "system" and event.get("subtype") == "init":
            if not session.init:
                session.init = event
        elif kind == "system" and event.get("subtype") == "permission_denied":
            call = by_id.get(event.get("tool_use_id", ""))
            if call is not None:
                call.denied = True
        elif kind == "assistant":
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "text" and block.get("text", "").strip():
                    session.steps.append(("text", block["text"]))
                    turn_texts.append(block["text"])
                elif block.get("type") == "tool_use":
                    name = block["name"]
                    call = Call(
                        index  = len(session.calls) + 1,
                        turn   = turn,
                        tool   = name.removeprefix(TOOL_PREFIX),
                        server = name.startswith(TOOL_PREFIX),
                        input  = block.get("input") or {},
                        id     = block["id"],
                        started = at,
                    )
                    session.calls.append(call)
                    by_id[call.id] = call
                    session.steps.append(("call", call))
        elif kind == "user":
            content = event.get("message", {}).get("content", [])
            for block in content if isinstance(content, list) else []:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                call = by_id.get(block.get("tool_use_id", ""))
                if call is None:
                    continue
                call.text = _block_text(block.get("content"))
                call.is_error = bool(block.get("is_error"))
                if at is not None and call.started is not None:
                    call.seconds = round(at - call.started, 1)
                _read_result(call)
        elif kind == "result":
            session.results.append(event)
            # Everything the agent wrote in the turn: the user reads it all,
            # and the last message alone can be only its closing part.
            session.turn_texts.append("\n\n".join(turn_texts))
            answer = event.get("result")
            session.answers.append(
                answer if isinstance(answer, str) and answer.strip()
                else "\n\n".join(turn_texts[-1:])
            )
            for denial in event.get("permission_denials") or []:
                session.denials.append({
                    "tool": denial.get("tool_name"),
                    "input": denial.get("tool_input"),
                })
    return session


def _read_result(call: Call) -> None:
    """
    Decode the result of a server call: the response object, or the error
    `{code, message, field, hint, details}`.
    """

    if not call.server:
        return
    text = call.text
    if call.is_error:
        start = text.find("{")
        if start >= 0:
            try:
                call.error = json.loads(text[start:])
                call.code = call.error.get("code")
            except ValueError:
                pass
        if call.code is None and not call.denied:
            call.code = "unparsed_error"
        return
    try:
        decoded = json.loads(text)
    except ValueError:
        return
    if isinstance(decoded, dict):
        call.response = decoded


# =============================================================================
# Checks
# =============================================================================
# Commands of a shell that write the file they name last, a redirection
# into a file, and what a script uses to write one.
_COPY_COMMAND = re.compile(r"(?:^|[\s;&|(])(cp|mv|tee|rsync|install|ln)\s+([^;&|\n]+)")
_REDIRECTION = re.compile(r"(?<![0-9&])>{1,2}\s*[\"']?([^\s\"';&|)]+)")
# Calls of a script that write a file, and the position of the argument
# that names it; and a text given to a variable, which often holds it.
_SCRIPT_WRITE = (
    (re.compile(r"\.to_csv\("), 0),
    (re.compile(r"\bopen\((?=[^\n]*,\s*(?:mode\s*=\s*)?[\"'][wax])"), 0),
    (re.compile(r"\bshutil\.(?:copy\w*|move)\("), 1),
    (re.compile(r"\bPath\((?=[^\n]*\)\.write_(?:text|bytes)\()"), 0),
)
_ASSIGNED_TEXT = re.compile(r"^\s*(\w+)\s*=\s*[rfb]*[\"']([^\"'\n]+)[\"']\s*$", re.M)
_QUOTED = re.compile(r"[\"']([^\"'\n]+)[\"']")


def _call_arguments(text: str, start: int) -> list[str]:
    """
    Arguments of the call whose opening parenthesis ends at `start`, split
    at the commas outside any bracket or text.
    """

    arguments, depth, quote, current = [], 0, "", ""
    for char in text[start:]:
        if quote:
            quote = "" if char == quote else quote
        elif char in "\"'":
            quote = char
        elif char in "([{":
            depth += 1
        elif char in ")]}":
            if depth == 0:
                break
            depth -= 1
        elif char == "," and depth == 0:
            arguments.append(current.strip())
            current = ""
            continue
        current += char
    return [*arguments, current.strip()]


def _script_targets(command: str) -> list[str]:
    """
    Files that the script in a command writes: the text of the argument
    that names each one, or the text given to the variable passed there.
    A file named another way (computed, read from an argument) is not found.
    """

    assigned = dict(_ASSIGNED_TEXT.findall(command))
    targets = []
    for pattern, position in _SCRIPT_WRITE:
        for found in pattern.finditer(command):
            arguments = _call_arguments(command, found.end())
            if position >= len(arguments):
                continue
            argument = arguments[position]
            quoted = _QUOTED.findall(argument)
            if quoted:
                targets.append(quoted[-1])
            elif argument in assigned:
                targets.append(assigned[argument])
    return targets


def _write_target(call: Call, root: str) -> str | None:
    """
    What a call of the client would have written among the data of the
    user: a file inside `data/`, or a CSV file anywhere (future exogenous
    values written next to the workspace). None for a call that reads, or
    that writes something else (a script, a chart). A script counts by the
    file it writes, as `cp` and `Write` do, not by the files it names: one
    that reads the data and prints, or draws a chart, wrote none of it.
    """

    def of_user(path: str) -> bool:
        path = path.strip("\"'")
        relative = path.removeprefix(root).lstrip("/")
        return relative.startswith("data/") or path.lower().endswith(".csv")

    if call.tool in ("Write", "Edit"):
        path = str(call.input.get("file_path", ""))
        return path.replace(root, "<ws>") if of_user(path) else None
    if call.tool != "Bash":
        return None
    command = str(call.input.get("command", ""))
    for found in _COPY_COMMAND.finditer(command):
        arguments = [a for a in found.group(2).split() if not a.startswith("-")]
        if found.group(1) == "tee":
            targets = arguments
        else:
            targets = arguments[-1:]
        for target in targets:
            if of_user(target):
                return f"{found.group(1)} to {target.replace(root, '<ws>')}"
    for found in _REDIRECTION.finditer(command):
        if of_user(found.group(1)):
            return f"> {found.group(1).replace(root, '<ws>')}"
    if any(of_user(target) for target in _script_targets(command)):
        return "a script that writes a file of data"
    return None


def _unmeasured_forecast(session: Session) -> str | None:
    """
    Whether the last forecast of the future (without `test_size`) ran a
    plan that the session did not measure, while it measured another: the
    agent backtests one plan, builds a second one and forecasts with it.

    Returns
    -------
    detail : str, None
        None when the session has no forecast of the future or measured no
        plan (nothing to compare); `''` when the plan of the forecast was
        measured, by a backtest or as the winner of a comparison; else the
        plan of the forecast and the plans measured.
    """

    cv_plans: dict[str, str] = {}
    measured: list[str] = []
    forecast_plan = None
    for call in session.server_calls:
        if call.is_error or not call.response:
            continue
        links = call.response.get("links") or {}
        if call.tool == "create_cv":
            cv_plans[call.response.get("id", "")] = links.get("plan_id", "")
        elif call.tool == "backtest":
            measured.append(
                call.input.get("plan_id") or links.get("plan_id")
                or cv_plans.get(call.input.get("cv_id", ""), "")
            )
        elif call.tool == "compare":
            measured.append(links.get("best_plan_id", ""))
        elif call.tool == "forecast" and call.input.get("test_size") is None:
            forecast_plan = call.input.get("plan_id")
    if forecast_plan is None or not measured:
        return None
    if forecast_plan in measured:
        return ""
    return f"forecast ran {forecast_plan}; measured: {sorted(set(measured))}"


def run_checks(session: Session) -> None:
    """
    Automatic, deterministic checks of a session. Each one is `pass`,
    `fail` or `warn` (a signal to read, which does not fail on its own).
    """

    scenario = session.scenario
    checks: list[dict[str, str]] = []

    def add(name: str, passed: bool, detail: str = "", soft: bool = False) -> None:
        status = "pass" if passed else ("warn" if soft else "fail")
        checks.append({"name": name, "status": status, "detail": detail})

    init = session.init
    add(
        "subscription, no API key",
        init.get("apiKeySource") == "none",
        f"apiKeySource={init.get('apiKeySource')!r}",
    )
    servers = [(s.get("name"), s.get("status")) for s in init.get("mcp_servers", [])]
    plugins = [
        p.get("name") for p in init.get("plugins", []) if p.get("path") != "builtin"
    ]
    add(
        "isolated session",
        servers == [(SERVER_NAME, "connected")] and not plugins,
        f"servers={servers}, plugins={plugins}",
    )
    listed = SKILL_NAME in (init.get("skills") or [])
    if session.with_skill:
        add("skill available", listed, f"listed in init: {listed}")
        loaded = any(
            call.tool == "Skill" and call.input.get("skill") == SKILL_NAME
            for call in session.calls
        )
        add("skill loaded by the agent", loaded, "Skill call" if loaded else "never",
            soft=True)
    else:
        add("skill absent (ablation)", not listed, f"listed in init: {listed}")

    add(
        "finished within the limits",
        session.status == "completed",
        f"status={session.status}, {session.meta['wall_seconds']} s of "
        f"{session.meta.get('timeout', scenario.timeout)} s",
    )

    delegated = [
        call for call in session.calls
        if call.tool in SUBAGENT_TOOLS and not call.denied and not call.is_error
    ]
    add(
        "no work handed to a subagent", not delegated,
        "; ".join(
            f"{call.tool} (call {call.index}, turn {call.turn + 1})"
            for call in delegated
        ),
    )
    # A turn has an answer when the agent wrote text in it and was not
    # waiting for a subagent launched in the background.
    sent = len(scenario.turns)
    unanswered = [
        f"turn {turn + 1}: no text"
        for turn in range(sent)
        if turn >= len(session.turn_texts) or not session.turn_texts[turn].strip()
    ] + [
        f"turn {call.turn + 1}: ended waiting for a subagent (call {call.index})"
        for call in delegated if "Async agent launched" in call.text
    ]
    if session.status == "completed":
        add("every turn ends with an answer", not unanswered, "; ".join(unanswered))

    unmeasured = _unmeasured_forecast(session)
    if unmeasured is not None:
        # Mechanical half of the finding: whether the answer gives the
        # accuracy of the other plan as its own is read by the reviewer.
        add(
            "the plan of the forecast was measured", not unmeasured, unmeasured,
            soft=True,
        )

    succeeded = [call.tool for call in session.server_calls if not call.is_error]
    def first_of(names: str) -> int | None:
        # `backtest|compare`: any of the tools.
        found = [succeeded.index(n) for n in names.split("|") if n in succeeded]
        return min(found) if found else None

    for tool in scenario.expect_tools:
        add(f"called `{tool}`", first_of(tool) is not None)
    for first, second in scenario.expect_order:
        before, after = first_of(first), first_of(second)
        if before is not None and after is not None:
            add(f"`{first}` before `{second}`", before < after)
    done = succeeded + [
        call.tool for call in session.calls if not call.server and not call.is_error
    ]
    for tool in scenario.forbid_tools:
        add(f"did not run `{tool}`", tool not in done)

    codes = session.error_codes
    for code in scenario.expect_errors:
        add(f"met `{code}`", code in codes)
    known = set(scenario.expect_errors) | set(scenario.allowed_errors)
    unexpected = [code for code in codes if code not in known]
    add("no internal_error", "internal_error" not in codes)
    failures = [
        call for call in session.server_calls
        if call.code in ("execution_failed", "all_candidates_failed")
    ]
    if failures:
        # The error carries a `failure_id`; the traceback says why it failed.
        unread = [
            f"{call.tool} (call {call.index})" for call in failures
            if not any(
                later.tool == "get_failure" and later.index > call.index
                for later in session.server_calls
            )
        ]
        add(
            "`get_failure` read after a failed execution", not unread,
            f"not read after: {unread}" if unread else "",
        )
    add(
        "no unexpected error", not unexpected,
        f"unexpected: {unexpected}" if unexpected else f"errors: {codes}",
        soft=True,
    )

    failed: dict[str, int] = {}
    for call in session.calls:
        if call.is_error and not call.denied:
            signature = call.tool + json.dumps(call.input, sort_keys=True)
            failed[signature] = failed.get(signature, 0) + 1
    repeated = [signature for signature, count in failed.items() if count > 1]
    add(
        "no failed call repeated with the same arguments", not repeated,
        "; ".join(text[:120] for text in repeated),
    )

    relative = [
        f"{call.tool}({key}={call.input[key]!r})"
        for call in session.server_calls
        for key in ("data_path", "exog_path")
        if isinstance(call.input.get(key), str)
        and not call.input[key].startswith(("/", "http://", "https://"))
    ]
    add("absolute paths", not relative, "; ".join(relative), soft=True)

    add(
        "files of the user unchanged", not session.changed_files,
        f"changed: {session.changed_files}" if session.changed_files else "",
    )
    add(
        "no tool denied by the client", not session.denials,
        "; ".join(
            f"{d['tool']}({json.dumps(d['input'])[:100]})"
            if d["tool"] in SHOWN_CLIENT_TOOLS else f"{d['tool']}(...)"
            for d in session.denials
        ),
        soft=True,
    )

    # A denied write is still an attempt: another client would have let it
    # through, so it fails the session unless the user had agreed to it.
    agreed = scenario.writes_agreed_from
    attempts = [
        f"{call.tool} (call {call.index}): {target}"
        for call in session.calls
        if call.denied and (agreed is None or call.turn < agreed)
        for target in [_write_target(call, session.root)]
        if target
    ]
    add(
        "no denied attempt to write data of the user", not attempts,
        "; ".join(attempts)[:400],
    )

    for label, function in scenario.checks:
        try:
            passed, detail = function(session)
        except Exception as exc:  # noqa: BLE001 - a broken check is reported
            passed, detail = False, f"the check raised {type(exc).__name__}: {exc}"
        add(label, bool(passed), detail)

    session.checks = checks


def auto_status(session: Session) -> str:
    statuses = {check["status"] for check in session.checks}
    return "fail" if "fail" in statuses else "warn" if "warn" in statuses else "pass"


# =============================================================================
# Numbers with a source
# =============================================================================
NUMBER = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?%?")
NOISE = re.compile(
    r"\b[a-z_]+-\d+-[0-9a-f]{6}\b"          # ids of the server
    r"|\b\d{4}-\d{2}(?:-\d{2})?(?:[T ]\d{2}:\d{2}(?::\d{2})?)?\b"   # dates
    r"|\b\d{1,2}:\d{2}(?::\d{2})?\b"        # hours
    r"|\b\d{1,2}/\d{1,2}/\d{2,4}\b"         # dates with slashes
    r"|(?m:^\s*\d+[.)]\s)"                  # list numbering
    r"|\S*/\S+\.\w+"                        # paths
    r"|\b[A-Za-z]+[-_]?\d+(?:\.\d+)*\b"     # names with digits (Chronos-2)
)


def _numbers(text: str) -> list[tuple[str, float, int, bool]]:
    """
    Numbers of a text: `(literal, value, decimals, percent)`.
    """

    found = []
    for match in NUMBER.finditer(text):
        literal = match.group(0)
        percent = literal.endswith("%")
        digits = literal.rstrip("%").replace(",", "")
        try:
            value = float(digits)
        except ValueError:
            continue
        mantissa = digits.lower().split("e")[0]
        decimals = len(mantissa.split(".")[1]) if "." in mantissa else 0
        found.append((literal, value, decimals, percent))
    return found


def find_unsourced(session: Session) -> None:
    """
    Numbers of the text the agent wrote that are in no tool result, in no
    file it read and in no message of the user, also after rounding the
    source to the decimals of the answer (and as a percentage). They are
    listed to be read by hand: a rounding rule this function does not know
    looks the same as an invented number.
    """

    root = session.root
    sources = " ".join(
        [text for kind, text in session.steps if kind == "user"]
        + [call.text for call in session.calls]
        + [json.dumps(call.input) for call in session.calls]
    ).replace(root, "")
    # The sources keep their dates and names, so a year or a part of a
    # date the agent quotes has an origin; signs are ignored (`1.2-1.5`).
    # A comma is read both as a thousands separator and as the separator
    # of a CSV row.
    source_values = {
        abs(value)
        for text in (sources, sources.replace(",", " "))
        for _, value, _, _ in _numbers(text)
    }

    def sourced(value: float, decimals: int, percent: bool) -> bool:
        value = abs(value)
        if decimals == 0 and value <= 10 and not percent:
            return True
        scales = (1.0, 100.0) if percent else (1.0,)
        for source in source_values:
            for scale in scales:
                if round(source * scale, decimals) == round(value, decimals):
                    return True
        return False

    seen: set[str] = set()
    unsourced = []
    for kind, text in session.steps:
        if kind != "text":
            continue
        cleaned = NOISE.sub(" ", text.replace(root, ""))
        for match in NUMBER.finditer(cleaned):
            literal = match.group(0)
            if literal in seen:
                continue
            parsed = _numbers(literal)
            if not parsed:
                continue
            _, value, decimals, percent = parsed[0]
            seen.add(literal)
            if not sourced(value, decimals, percent):
                start, end = max(0, match.start() - 50), match.end() + 40
                context = " ".join(cleaned[start:end].split())
                unsourced.append({"number": literal, "context": context})
    session.unsourced = unsourced


# =============================================================================
# Fixed context (dry run)
# =============================================================================
def measure_context() -> dict[str, Any]:
    """
    Start the server, list its tools and measure what a client loads: the
    instructions, the description and schema of every tool, and the skill.
    Costs nothing: no agent is launched.
    """

    import anyio
    from mcp import Client, StdioServerParameters

    root = Path(os.path.realpath(tempfile.mkdtemp(prefix="skfai_mcp_dry_")))
    (root / "data").mkdir()
    (root / "out").mkdir()
    parameters = StdioServerParameters(
        command = sys.executable,
        args    = [
            "-m", "skforecast_ai", "mcp",
            "--allow-dir", str(root / "data"), "--output-dir", str(root / "out"),
        ],
        env     = {**clean_environment(), "PYTHONPATH": str(REPO_ROOT)},
        cwd     = str(root),
    )

    async def main() -> dict[str, Any]:
        async with Client(parameters) as client:
            listed = await client.list_tools()
            tools = {}
            for tool in listed.tools:
                schema = getattr(tool, "input_schema", None) or getattr(
                    tool, "inputSchema", {}
                )
                tools[tool.name] = {
                    "description_chars": len(tool.description or ""),
                    "schema_chars": len(json.dumps(schema)),
                }
            return {"instructions_chars": len(client.instructions or ""), "tools": tools}

    try:
        measured = anyio.run(main)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    front = skill.split("---")[1] if skill.startswith("---") else ""
    tools_chars = sum(
        sizes["description_chars"] + sizes["schema_chars"]
        for sizes in measured["tools"].values()
    )
    names_chars = sum(len(TOOL_PREFIX + name) for name in measured["tools"])
    measured.update({
        "n_tools": len(measured["tools"]),
        "tools_chars": tools_chars,
        "skill_chars": len(skill),
        "skill_frontmatter_chars": len(front),
        # What a session holds before the first call.
        "always_deferred_chars": (
            measured["instructions_chars"] + names_chars + len(front)
        ),
        "always_full_chars": measured["instructions_chars"] + tools_chars,
    })
    return measured


def render_context(context: dict[str, Any]) -> list[str]:
    """
    Table of the fixed context. Tokens are estimated as characters / 4.
    """

    def row(label: str, chars: int) -> str:
        return f"| {label} | {chars:,} | {round(chars / 4):,} |"

    lines = [
        "| What the client loads | Characters | Tokens (about) |",
        "|:--|--:|--:|",
        row("Server instructions", context["instructions_chars"]),
        row(
            f"Descriptions and schemas of the {context['n_tools']} tools",
            context["tools_chars"],
        ),
        row("`SKILL.md`, when the agent loads it", context["skill_chars"]),
        row(
            "Every session, client that defers tools (Claude Code): "
            "instructions, tool names, skill description",
            context["always_deferred_chars"],
        ),
        row(
            "Every session, client that loads every tool: instructions, "
            "descriptions and schemas",
            context["always_full_chars"],
        ),
    ]
    return lines


# =============================================================================
# Report
# =============================================================================
def _short(value: Any, root: str, limit: int = 160) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    text = text.replace(root, "<ws>")
    if not isinstance(value, str):
        return text if len(text) <= limit else text[: limit - 3] + "..."
    text = json.dumps(text, ensure_ascii=False)
    return text if len(text) <= limit else text[: limit - 4] + '..."'


def _shown(call: Call) -> bool:
    """
    Whether the report shows the arguments and the result of a call: the
    tools of the server and the client tools of `SHOWN_CLIENT_TOOLS`.
    """

    return call.server or call.tool in SHOWN_CLIENT_TOOLS


def _signature(call: Call, root: str) -> str:
    if not _shown(call):
        return f"{call.tool}({', '.join(call.input)}) [values not shown]"
    arguments = ", ".join(
        f"{key}={_short(value, root)}" for key, value in call.input.items()
    )
    return f"{call.tool}({arguments})"


def _details(summary: str, body: str, root: str, limit: int = 8000) -> list[str]:
    body = body.replace(root, "<ws>")
    if len(body) > limit:
        body = body[:limit] + f"\n[... {len(body) - limit:,} more characters in the trace]"
    fence = "````"
    return [
        f"<details><summary>{summary}</summary>", "",
        f"{fence}text", body, fence, "", "</details>", "",
    ]


def _shared_prefix(first: str, second: str) -> int:
    """
    Length of the common start of two texts, cut at the end of a line.
    """

    length = 0
    for a, b in zip(first, second):
        if a != b:
            break
        length += 1
    return first.rfind("\n", 0, length) + 1 if length < len(second) else length


def _quote(text: str, root: str) -> list[str]:
    return [f"> {line}" if line else ">" for line in text.replace(root, "<ws>").splitlines()]


def _notice_text(notice: Any) -> str:
    if not isinstance(notice, dict):
        return str(notice)
    label = notice.get("category") or notice.get("type") or "notice"
    source = notice.get("source")
    message = notice.get("message") or notice.get("text") or json.dumps(notice)
    head = f"{label} ({source})" if source else label
    return f"{head}: {' '.join(str(message).split())}"


def render_timeline(session: Session) -> list[str]:
    """
    Numbered conversation: the messages of the user, the text of the agent,
    every call (`LLM -> MCP` to the server, `LLM -> client` to a tool of
    Claude Code) and what came back.
    """

    root = session.root
    lines: list[str] = []
    number = 0
    user_turn = 0
    previous = ""
    for kind, item in session.steps:
        if kind == "user":
            user_turn += 1
            lines += [f"**User (turn {user_turn})**", "", *_quote(item, root), ""]
            continue
        if kind == "text":
            if item in session.answers:
                turn = session.answers.index(item) + 1
                lines += [f"**LLM (answer of turn {turn}, under \"Final answer\")**", ""]
            else:
                lines += ["**LLM (text)**", "", *_quote(item, root), ""]
            continue
        call: Call = item
        number += 1
        target = "MCP" if call.server else "client"
        took = f" ({call.seconds} s)" if call.seconds is not None else ""
        lines += [f"**{number}.** `LLM -> {target}` `{_signature(call, root)}`{took}", ""]
        back = f"`{target} -> LLM`"
        if call.denied:
            lines += [f"{back} **DENIED** by the permissions of the client", ""]
        elif not _shown(call):
            flag = " **ERROR**" if call.is_error else ""
            lines += [
                f"{back}{flag} result not shown ({len(call.text):,} characters): "
                "not a tool of the server nor one the report shows", "",
            ]
        elif call.server and call.is_error:
            error = call.error or {}
            lines.append(
                f"{back} **ERROR** `{call.code}`"
                + (f", field `{error.get('field')}`" if error.get("field") else "")
                + f": {' '.join(str(error.get('message', call.text)).split())}"
                .replace(root, "<ws>")
            )
            if error.get("hint"):
                hint = " ".join(str(error["hint"]).split()).replace(root, "<ws>")
                lines.append(f"  hint: {hint}")
            lines.append("")
        elif call.server and call.response is not None:
            response = call.response
            notices = response.get("notices") or []
            parts = []
            if response.get("id"):
                parts.append(f"id `{response['id']}`")
            parts.append(f"{len(notices)} notices")
            if response.get("files"):
                parts.append("files: " + ", ".join(f"`{k}`" for k in response["files"]))
            if response.get("cost"):
                parts.append(f"cost `{json.dumps(response['cost'])}`")
            if (response.get("links") or {}).get("best_plan_id"):
                parts.append(f"best_plan_id `{response['links']['best_plan_id']}`")
            lines += [f"{back} " + ", ".join(parts), ""]
            for notice in notices:
                lines.append(f"- {_notice_text(notice)[:400]}".replace(root, "<ws>"))
            if notices:
                lines.append("")
            body = str(response.get("summary") or response.get("code") or call.text)
            name = "summary" if response.get("summary") else "response"
            title = f"{name} ({len(body):,} characters)"
            shared = _shared_prefix(previous, body)
            previous = body
            if shared > 400:
                title += f", the first {shared:,} repeat the previous response"
                body = f"[... {shared:,} characters as above]\n" + body[shared:]
            lines += _details(title, body, root)
        else:
            flag = " **ERROR**" if call.is_error else ""
            first = " ".join(call.text.split())[:160].replace(root, "<ws>")
            if len(call.text) <= 200:
                lines += [f"{back}{flag} {first}", ""]
            else:
                lines += [f"{back}{flag} {len(call.text):,} characters", ""]
                lines += _details("result", call.text, root, limit=4000)
    return lines


def _usage_cells(usage: dict[str, Any]) -> tuple[str, str, str]:
    if not usage["agent_turns"] and not usage["cost_usd"]:
        # A session cut by the runner never sends its totals.
        return "unknown (cut)", "unknown", f"{usage['wall_seconds']:.0f}"
    tokens = (
        f"{usage['input_tokens'] + usage['cache_creation_tokens']:,} in, "
        f"{usage['cache_read_tokens']:,} cached, {usage['output_tokens']:,} out"
    )
    return tokens, f"{usage['cost_usd']:.2f}", f"{usage['wall_seconds']:.0f}"


def render_session(session: Session, evaluation: dict[str, Any], run_dir: Path) -> list[str]:
    scenario = session.scenario
    root = session.root
    usage = session.usage
    tokens, cost, seconds = _usage_cells(usage)
    lines = [f"## {session.key}", ""]
    lines += [
        f"- **Asks**: {scenario.summary}",
        f"- **Expected**: {scenario.expected}",
        f"- **Setup**: files {', '.join(f'`{p}`' for p in scenario.files)}; "
        f"skill {'yes' if session.with_skill else 'no'}; allowed tools "
        f"{', '.join(f'`{t}`' for t in BASE_TOOLS + scenario.extra_tools)}; "
        f"critical: {'yes' if scenario.critical else 'no'}",
        f"- **Session**: status `{session.status}`, {usage['agent_turns']} agent "
        f"turns, {len(session.server_calls)} server calls "
        f"({len(session.error_codes)} errors), {len(session.calls)} calls in "
        f"all, {tokens} tokens, {cost} USD equivalent, {seconds} s",
        "",
        "### Timeline", "",
        *render_timeline(session),
        "### Final answer", "",
    ]
    for index, answer in enumerate(session.answers, start=1):
        if len(session.answers) > 1:
            lines += [f"**Turn {index}**", ""]
        lines += [*_quote(answer, root), ""]
    if not session.answers:
        lines += ["(none)", ""]

    lines += ["### Automatic checks", "", "| Check | Result | Detail |", "|:--|:--|:--|"]
    for check in session.checks:
        detail = check["detail"].replace("|", "\\|").replace(root, "<ws>")
        lines.append(f"| {check['name']} | {check['status'].upper()} | {detail} |")
    lines.append("")
    if session.new_files or session.changed_files:
        lines += [
            f"New files: {session.new_files or 'none'}. Changed files: "
            f"{session.changed_files or 'none'}.", "",
        ]

    lines += ["### Numbers without a source", ""]
    if session.unsourced:
        lines += [
            "In the text of the agent and in no response, file read or "
            "message of the user (to read by hand: a rounding or an "
            "invention):", "",
        ]
        lines += [
            f"- `{item['number']}`: ...{item['context']}..." for item in session.unsourced
        ]
    else:
        lines.append("None.")
    lines.append("")

    review = (evaluation.get("sessions") or {}).get(session.key)
    lines += ["### Evaluation", ""]
    if review:
        scores = review.get("scores") or {}
        lines += [
            "| " + " | ".join(RUBRIC) + " | verdict |",
            "|" + ":-:|" * (len(RUBRIC) + 1),
            "| " + " | ".join(str(scores.get(name, "")) for name in RUBRIC)
            + f" | **{review.get('verdict', '')}** |",
            "", review.get("notes", ""), "",
        ]
    else:
        lines += ["Not reviewed yet.", ""]

    trace = Path("traces") / f"{session.key}.jsonl"
    log = Path("server_logs") / f"{session.key}.log"
    lines += [f"Raw trace: [`{trace}`]({trace}). Server log: [`{log}`]({log}).", ""]
    return lines


def render_report(
    run: dict[str, Any], sessions: list[Session], evaluation: dict[str, Any],
    pending: list[str], run_dir: Path,
) -> str:
    context = run["context"]
    total_cost = sum(session.usage["cost_usd"] for session in sessions)
    total_seconds = sum(session.usage["wall_seconds"] for session in sessions)
    lines = [
        f"# MCP agent check: {run['name']}", "",
        f"- **Release**: skforecast-ai {run['versions']['skforecast_ai']}, "
        f"commit `{run['commit']}`",
        f"- **Date**: {run['started']}",
        f"- **Model**: `{run['model']}` (Claude Code "
        f"{run['versions'].get('claude_code', '?')}, subscription, no API key)",
        f"- **Versions**: mcp {run['versions']['mcp']}, skforecast "
        f"{run['versions']['skforecast']}, Python {run['versions']['python']}",
        f"- **Sessions**: {len(sessions)} finished, {len(pending)} pending; "
        f"{total_cost:.2f} USD equivalent (not a charge), "
        f"{total_seconds / 60:.1f} minutes",
        "",
        "Fixed context:", "", *render_context(context), "",
    ]
    if pending:
        lines += ["Pending sessions: " + ", ".join(f"`{key}`" for key in pending), ""]

    if evaluation.get("overall"):
        lines += ["## Overall evaluation", "", evaluation["overall"], ""]

    lines += ["## Findings", ""]
    findings = evaluation.get("findings")
    if findings is None:
        lines += ["Not reviewed yet.", ""]
    else:
        reviewed = len(evaluation.get("sessions") or {})
        lines += [
            f"Written by the reviewer after reading {reviewed} of the "
            f"{len(sessions)} sessions, most important first. Both lists are "
            "always present: an empty one says nothing was found.", "",
        ]
        groups = [
            (
                "Problems of the library (server or skill)",
                "to fix in skforecast-ai, then rerun the sessions",
                ("server", "skill"),
            ),
            (
                "Problems of the model",
                "the library gave the right information and the agent did "
                "not use it well",
                ("model",),
            ),
        ]
        for title, meaning, causes in groups:
            rows = [f for f in findings if f["attribution"] in causes]
            lines += [f"### {title}", "", f"{len(rows)} found ({meaning}).", ""]
            if not rows:
                continue
            lines += [
                "| # | Finding | Cause | Sessions | Proposed action |",
                "|--:|:--|:--|:--|:--|",
            ]
            for number, finding in enumerate(rows, start=1):
                lines.append(
                    f"| {number} | **{finding['title']}** "
                    f"{finding.get('evidence', '')} "
                    f"| {finding['attribution']} "
                    f"| {', '.join(finding.get('sessions', []))} "
                    f"| {finding.get('action', '')} |"
                )
            lines.append("")

    lines += [
        "## Summary", "",
        "| Session | Verdict | Checks | Calls (server) | Errors | Tokens "
        "| USD eq. | Seconds |",
        "|:--|:--|:--|--:|:--|:--|--:|--:|",
    ]
    for session in sessions:
        review = (evaluation.get("sessions") or {}).get(session.key) or {}
        fails = [c["name"] for c in session.checks if c["status"] == "fail"]
        warns = [c["name"] for c in session.checks if c["status"] == "warn"]
        checks = auto_status(session).upper()
        if fails:
            checks += f" ({len(fails)} fail)"
        elif warns:
            checks += f" ({len(warns)})"
        tokens, cost, seconds = _usage_cells(session.usage)
        anchor = re.sub(r"[^a-z0-9_-]", "", session.key.lower())
        lines.append(
            f"| [{session.key}](#{anchor}) | {review.get('verdict', 'to review')} "
            f"| {checks} | {len(session.calls)} ({len(session.server_calls)}) "
            f"| {', '.join(session.error_codes) or 'none'} | {tokens} | {cost} "
            f"| {seconds} |"
        )
    lines.append("")

    rates = _pass_rates(sessions, evaluation)
    if any(total > 1 for _, total in rates.values()):
        lines += ["Pass rate per scenario (verdict other than fail):", ""]
        lines += [f"- `{name}`: {good}/{total}" for name, (good, total) in rates.items()]
        lines.append("")

    for session in sessions:
        lines += render_session(session, evaluation, run_dir)
    return "\n".join(lines).rstrip() + "\n"


def _pass_rates(
    sessions: list[Session], evaluation: dict[str, Any]
) -> dict[str, tuple[int, int]]:
    """
    Sessions that did not fail, per scenario and variant: by the verdict of
    the reviewer when there is one, else by the automatic checks.
    """

    rates: dict[str, tuple[int, int]] = {}
    for session in sessions:
        name = session.key.rsplit("__r", 1)[0]
        review = (evaluation.get("sessions") or {}).get(session.key) or {}
        failed = (
            review["verdict"] == "fail" if review.get("verdict")
            else auto_status(session) == "fail"
        )
        good, total = rates.get(name, (0, 0))
        rates[name] = (good + (not failed), total + 1)
    return rates


def results_json(
    run: dict[str, Any], sessions: list[Session], evaluation: dict[str, Any],
    pending: list[str],
) -> dict[str, Any]:
    output = {
        "run": {key: value for key, value in run.items() if key != "plan"},
        "pending": pending,
        "pass_rates": {
            name: {"passed": good, "total": total}
            for name, (good, total) in _pass_rates(sessions, evaluation).items()
        },
        "sessions": {},
    }
    for session in sessions:
        review = (evaluation.get("sessions") or {}).get(session.key) or {}
        output["sessions"][session.key] = {
            "scenario": session.scenario.name,
            "skill": session.with_skill,
            "rep": session.rep,
            "critical": session.scenario.critical,
            "status": session.status,
            "checks": session.checks,
            "auto": auto_status(session),
            "verdict": review.get("verdict"),
            "scores": review.get("scores"),
            "tools": [call.tool for call in session.calls],
            "n_calls": len(session.calls),
            "n_server_calls": len(session.server_calls),
            "error_codes": session.error_codes,
            "denials": [denial["tool"] for denial in session.denials],
            "unsourced_numbers": [item["number"] for item in session.unsourced],
            "usage": session.usage,
        }
    return output


# =============================================================================
# Run
# =============================================================================
def _session_key(name: str, with_skill: bool, rep: int) -> str:
    return f"{name}{'' if with_skill else '__noskill'}__r{rep}"


def build_plan(arguments: argparse.Namespace) -> list[tuple[str, bool, int]]:
    """
    Sessions of the run: every scenario with the skill, plus the ablation
    scenarios without it, each repeated `--reps` times.
    """

    names = arguments.scenarios or [scenario.name for scenario in SCENARIOS]
    unknown = [name for name in names if name not in BY_NAME]
    if unknown:
        sys.exit(f"Unknown scenarios: {unknown}. See --list.")
    plan = []
    for rep in range(1, arguments.reps + 1):
        if not arguments.only_ablation:
            plan += [(name, True, rep) for name in names]
        if not arguments.no_ablation:
            plan += [(name, False, rep) for name in names if name in ABLATION]
    return plan


def _versions() -> dict[str, str]:
    import skforecast
    import skforecast_ai

    return {
        "skforecast_ai": skforecast_ai.__version__,
        "skforecast": skforecast.__version__,
        "mcp": importlib.metadata.version("mcp"),
        "python": sys.version.split()[0],
    }


def _commit() -> str:
    described = subprocess.run(
        ["git", "describe", "--always", "--dirty"], cwd=REPO_ROOT,
        capture_output=True, text=True,
    )
    return described.stdout.strip() or "unknown"


def load_sessions(run_dir: Path) -> list[Session]:
    """
    Every finished session of a run, analysed, in the order of the catalogue.
    """

    sessions = []
    for meta_path in sorted((run_dir / "traces").glob("*.meta.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        trace = meta_path.with_name(f"{meta['key']}.jsonl")
        if meta["status"] not in FINISHED or not trace.exists():
            continue
        if meta["scenario"] not in BY_NAME:
            continue
        session = parse_trace(meta["key"], BY_NAME[meta["scenario"]], meta, trace)
        # The files the session left, for the checks that read them.
        session.artifacts = str(run_dir / "artifacts" / meta["key"])
        run_checks(session)
        find_unsourced(session)
        sessions.append(session)
    order = {scenario.name: index for index, scenario in enumerate(SCENARIOS)}
    sessions.sort(key=lambda s: (order[s.scenario.name], not s.with_skill, s.rep))
    return sessions


def write_report(run_dir: Path, pending: list[str]) -> None:
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    evaluation_path = run_dir / "evaluation.json"
    evaluation = (
        json.loads(evaluation_path.read_text(encoding="utf-8"))
        if evaluation_path.exists() else {}
    )
    sessions = load_sessions(run_dir)
    for session in sessions:
        version = session.init.get("claude_code_version")
        if version:
            run["versions"]["claude_code"] = version
    (run_dir / "report.md").write_text(
        render_report(run, sessions, evaluation, pending, run_dir), encoding="utf-8"
    )
    (run_dir / "results.json").write_text(
        json.dumps(results_json(run, sessions, evaluation, pending), indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"[report] {run_dir / 'report.md'} ({len(sessions)} sessions)")


def _utilization(rate_limit: dict[str, Any] | None) -> float:
    windows = (rate_limit or {}).get("unifiedWindows") or {}
    return max(
        [window.get("utilization") or 0.0 for window in windows.values()] or [0.0]
    )


def _pending_keys(run_dir: Path, plan: list[tuple[str, bool, int]]) -> list[str]:
    pending = []
    for name, with_skill, rep in plan:
        key = _session_key(name, with_skill, rep)
        meta_path = run_dir / "traces" / f"{key}.meta.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta["status"] in FINISHED:
                continue
        requires = BY_NAME[name].requires
        if requires and importlib.util.find_spec(requires) is None:
            continue
        pending.append(key)
    return pending


def run(arguments: argparse.Namespace) -> None:
    run_dir = REPORTS_DIR / arguments.run_name
    plan = build_plan(arguments)

    if arguments.report_only:
        write_report(run_dir, _pending_keys(run_dir, plan))
        return

    status = check_subscription()
    print(
        f"[auth] {status.get('authMethod')}, plan {status.get('subscriptionType')}: "
        "sessions use the subscription; API keys are removed from their environment"
    )
    for folder in ("traces", "server_logs", "artifacts"):
        (run_dir / folder).mkdir(parents=True, exist_ok=True)

    run_path = run_dir / "run.json"
    if run_path.exists():
        run_info = json.loads(run_path.read_text(encoding="utf-8"))
        if run_info["model"] != arguments.model:
            sys.exit(
                f"Run {arguments.run_name!r} was started with model "
                f"{run_info['model']!r}; use another --run-name for "
                f"{arguments.model!r}."
            )
    else:
        print("[context] measuring the fixed context (no agent)")
        run_info = {
            "name": arguments.run_name,
            "started": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "model": arguments.model,
            "commit": _commit(),
            "versions": _versions(),
            "context": measure_context(),
        }
        run_path.write_text(json.dumps(run_info, indent=2) + "\n", encoding="utf-8")

    stopped = None
    for name, with_skill, rep in plan:
        scenario = BY_NAME[name]
        if arguments.timeout:
            scenario = dataclasses.replace(scenario, timeout=arguments.timeout)
        key = _session_key(name, with_skill, rep)
        meta_path = run_dir / "traces" / f"{key}.meta.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta["status"] in FINISHED:
                print(f"[skip] {key}: already finished ({meta['status']})")
                continue
        if scenario.requires and importlib.util.find_spec(scenario.requires) is None:
            print(f"[skip] {key}: needs the package {scenario.requires!r}")
            continue

        print(f"[run ] {key} ...", flush=True)
        root = prepare_workspace(scenario, with_skill)
        files_before = _hashes(root)
        trace_path = run_dir / "traces" / f"{key}.jsonl"
        partial = run_dir / "traces" / f"{key}.partial.jsonl"
        try:
            outcome = run_session(
                scenario, root, partial, arguments.model, arguments.max_budget_usd
            )
            files_after = _hashes(root)
            meta = {
                "key": key, "scenario": name, "with_skill": with_skill, "rep": rep,
                "model": arguments.model, "workspace": str(root),
                "turns": scenario.turns, "timeout": scenario.timeout,
                "files_before": files_before,
                "files_after": files_after, **outcome,
            }
            log = root / "server.log"
            if log.exists():
                shutil.copy(log, run_dir / "server_logs" / f"{key}.log")
            artifacts = run_dir / "artifacts" / key
            shutil.rmtree(artifacts, ignore_errors=True)
            for relative in files_after:
                if files_before.get(relative) != files_after[relative]:
                    target = artifacts / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy(root / relative, target)
            if (root / "out").exists():
                shutil.copytree(root / "out", artifacts / "out", dirs_exist_ok=True)
        finally:
            if not arguments.keep_workspaces:
                shutil.rmtree(root, ignore_errors=True)

        meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        if outcome["status"] in FINISHED:
            partial.replace(trace_path)
        used = _utilization(outcome["rate_limit"])
        print(
            f"       {outcome['status']} in {outcome['wall_seconds']} s; "
            f"usage of the plan: {used:.0%}",
            flush=True,
        )

        if outcome["status"] == "auth_error":
            stopped = "a session did not use the subscription (apiKeySource)"
        elif outcome["status"] == "usage_limit":
            stopped = "the usage limit of the subscription was reached"
        elif used >= arguments.stop_at_utilization:
            stopped = (
                f"the usage of the plan is at {used:.0%} "
                f"(--stop-at-utilization {arguments.stop_at_utilization})"
            )
        elif outcome["status"] in ("provider_error", "crashed"):
            print(
                f"       not counted as a failure of the agent; see "
                f"{partial.name} and {key}.stderr"
            )
        if stopped:
            break

    pending = _pending_keys(run_dir, plan)
    write_report(run_dir, pending)
    if stopped:
        print(f"[stop] {stopped}.")
    if pending:
        print(f"[left] {len(pending)} sessions: {', '.join(pending)}")
        print(
            "       Launch the same command again to continue: finished "
            "sessions are skipped."
        )


def dry_run() -> None:
    """
    Prepare one workspace per scenario, start the server, list its tools
    and measure the fixed context. No agent runs.
    """

    for scenario in SCENARIOS:
        root = prepare_workspace(scenario, with_skill=True)
        files = sorted(_hashes(root))
        shutil.rmtree(root, ignore_errors=True)
        print(f"[workspace] {scenario.name}: {files}, {len(scenario.turns)} turn(s)")
    context = measure_context()
    print(f"[server] {context['n_tools']} tools: {', '.join(context['tools'])}")
    print("\n".join(render_context(context)))
    print(json.dumps(context["tools"], indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="Prepare, start the server and measure; no agent, no cost.")
    parser.add_argument("--list", action="store_true", help="List the scenarios.")
    parser.add_argument("--run-name", default=None,
                        help="Folder of the run under agent_reports/ (a release such "
                             "as 0.4.0 is versioned; other names are ignored by git). "
                             "Default: run_<date>_<time>.")
    parser.add_argument("--scenarios", type=lambda text: text.split(","), default=None,
                        help="Comma-separated subset of scenarios.")
    parser.add_argument("--reps", type=int, default=1,
                        help="Repetitions per scenario (1 for a pilot, 3 for a release).")
    parser.add_argument("--model", default="sonnet",
                        help="Model alias or id of Claude Code.")
    parser.add_argument("--no-ablation", action="store_true",
                        help="Skip the sessions without the skill.")
    parser.add_argument("--only-ablation", action="store_true",
                        help="Run only the sessions without the skill.")
    parser.add_argument("--max-budget-usd", type=float, default=5.0,
                        help="Equivalent cost at which a session is cut (0 for none).")
    parser.add_argument("--timeout", type=int, default=None,
                        help="Seconds allowed per session, instead of the limit of "
                             "each scenario (to test the cut, or on a slow machine).")
    parser.add_argument("--stop-at-utilization", type=float, default=0.95,
                        help="Stop before the next session when a usage window of "
                             "the plan is at or above this fraction.")
    parser.add_argument("--keep-workspaces", action="store_true",
                        help="Do not delete the temporary folder of each session.")
    parser.add_argument("--report-only", action="store_true",
                        help="Rebuild report.md and results.json of --run-name.")
    arguments = parser.parse_args()

    if arguments.list:
        for scenario in SCENARIOS:
            flags = [
                "critical" if scenario.critical else "",
                "ablation" if scenario.name in ABLATION else "",
                f"{len(scenario.turns)} turns" if len(scenario.turns) > 1 else "",
            ]
            print(f"{scenario.name:20} {scenario.summary}  "
                  f"[{', '.join(flag for flag in flags if flag)}]")
        return
    if arguments.dry_run:
        dry_run()
        return
    if arguments.report_only and not arguments.run_name:
        sys.exit("--report-only needs --run-name.")
    if not arguments.run_name:
        arguments.run_name = f"run_{dt.datetime.now():%Y%m%d_%H%M%S}"
    run(arguments)


if __name__ == "__main__":
    main()
