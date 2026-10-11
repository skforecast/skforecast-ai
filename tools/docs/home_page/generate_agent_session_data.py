################################################################################
#                       generate_agent_session_data                            #
#                                                                              #
# Writes docs/animations/agent-session-data.js, the data of the animation of   #
# a real agent session with the MCP server. See tools/docs/home_page/README.md #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

"""
Generate the data of the animation "A real agent session".

The animation (`docs/animations/agent-session.html`) replays one session of
the MCP agent check (`tools/mcp/check_mcp_agent.py`): the request of the
user, every call of the agent to the server, its messages and its final
answer. Nothing is written by hand. The script reads the session from the
`report.md` of the run and keeps it as it is, except for two things:

- Trims, all declared in this file and all marked in the animation: the
  responses of the server are reduced to the fragments in `EXCERPTS`, joined
  by an ellipsis; two calls of the client are shortened (`CALL_PREFIXES`);
  and the lines of the final answer between the anchors of `ANSWER_TRIMS`
  become one line that says how many were trimmed. The script stops when a
  fragment, a prefix or an anchor is not in the trace, so a trim never
  becomes a rewrite.
- Paths: the workspace of the session, which the report writes as `<ws>`,
  becomes `WORKSPACE`. The script stops if a path of a home directory or a
  user name is left in the output.

It also stops if the report lists numbers without a source for the session:
the animation says that every figure comes from a response of the server.

Run from the repository root (no network, no LLM):

    python tools/docs/home_page/generate_agent_session_data.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
RUN = "0.4.0-final2"
SESSION = "compare_code__r1"
REPORT = REPO_ROOT / "tools" / "mcp" / "agent_reports" / RUN / "report.md"
OUTPUT = REPO_ROOT / "docs" / "animations" / "agent-session-data.js"

# Neutral project directory shown instead of the workspace of the session.
WORKSPACE = "~/project"

# Calls of the client shown up to this prefix, followed by an ellipsis.
CALL_PREFIXES = {
    1: 'Skill(skill="skforecast-ai-forecasting"',
    2: 'ToolSearch(query="select:mcp__skforecast-ai__profile,',
}

# Fragments of each response of the server, by step number: one list per line
# of the animation. Each fragment is looked for, verbatim, in the response,
# its notices and the line of metadata (ids, files, cost) of the report.
EXCERPTS = {
    3: [
        ["Observations: 204", "Frequency: MS", "Date range: 1991-07-01 to 2008-06-01",
         "Missing values: none"],
        ["A single-series ML forecaster (ForecasterRecursive) is recommended."],
    ],
    4: [
        ["Forecaster: ForecasterRecursive", "Estimator: Ridge",
         "Lags: [1, 9, 10, 11, 12, 13, 14]"],
    ],
    5: [
        ["Initial training up to 2003-04-01, trained once (no refit), "
         "12-step horizon, 6 folds.", '"compare_estimator_fits": 19'],
    ],
    6: [
        ["Candidates evaluated: 5", "Winner: ForecasterFoundation"],
        ["Best: 'ForecasterFoundation' (ForecasterFoundation / "
         "autogluon/chronos-2-small) = 0.0570, 8.0% ahead of "
         "'ForecasterRecursive' (0.0620)."],
        ["'ForecasterFoundation' beats the baseline 'Baseline (seasonal naive)' "
         "(0.0661) by 13.7%."],
        ["ModelLicenseNotice", "its license is Apache-2.0"],
    ],
    7: [
        ["Shape: 12 rows x 2 columns",
         "Index range: 2008-07-01 00:00:00 to 2009-06-01 00:00:00"],
    ],
    8: [
        ["from skforecast.model_selection import TimeSeriesFold, "
         "backtesting_foundation", "metrics, predictions = backtesting_foundation("],
    ],
    9: [
        ["forecaster.fit(series=series)",
         "predictions = forecaster.predict(steps=steps)"],
    ],
}

# Lines of the final answer trimmed: those strictly between the two anchors.
ANSWER_TRIMS = [
    (
        "from skforecast.foundation import FoundationModel, ForecasterFoundation",
        "steps = 12",
        "lines of the script",
    ),
]

# Paths of a home directory, or the placeholder of the workspace, left over.
PRIVATE = re.compile(r"/Users/|/home/|[A-Za-z]:\\|<ws>|/private/|/var/folders/")

STEP = re.compile(r"^\*\*(\d+)\.\*\* `LLM -> (MCP|client)` `(.+)` \(([\d.]+) s\)$")


def session_lines(report: str, session: str) -> list[str]:
    """
    Lines of the section of one session in a report of the agent check.

    Parameters
    ----------
    report : str
        Text of `report.md`.
    session : str
        Name of the session, for example `compare_code__r1`.

    Returns
    -------
    lines : list of str
        Lines from its heading to the next session.

    """

    lines = report.splitlines()
    start = lines.index(f"## {session}")
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    return lines[start:end]


def quoted(lines: list[str], i: int) -> tuple[str, int]:
    """
    Text of the quoted block (`> ` lines) that starts at or after line `i`.

    Parameters
    ----------
    lines : list of str
        Lines of the section.
    i : int
        Index where the search starts.

    Returns
    -------
    text : str
        The block without its `> ` markers, lines joined by newlines.
    end : int
        Index of the first line after the block.

    """

    while not lines[i].startswith(">"):
        i += 1
    block = []
    while i < len(lines) and lines[i].startswith(">"):
        block.append(lines[i][2:] if lines[i].startswith("> ") else "")
        i += 1
    return "\n".join(block), i


def parse_session(lines: list[str]) -> tuple[list[dict], str]:
    """
    Timeline and final answer of a session of the report.

    Parameters
    ----------
    lines : list of str
        Lines of the section of the session.

    Returns
    -------
    entries : list of dict
        The messages of the user, the texts of the agent and its calls, in
        order. A call holds its number, side (`MCP` or `client`), call,
        seconds and everything the report shows of its result.
    answer : str
        The final answer, as written.

    """

    entries = []
    i = lines.index("### Timeline")
    answer_at = lines.index("### Final answer")
    while i < answer_at:
        line = lines[i]
        if line.startswith("**User (turn"):
            text, i = quoted(lines, i + 1)
            entries.append({"kind": "user", "text": text})
            continue
        if line == "**LLM (text)**":
            text, i = quoted(lines, i + 1)
            entries.append({"kind": "text", "text": text})
            continue
        match = STEP.match(line)
        if match:
            body = []
            i += 1
            while i < answer_at and not (
                STEP.match(lines[i]) or lines[i].startswith("**")
            ):
                body.append(lines[i])
                i += 1
            entries.append({
                "kind": "step",
                "n": int(match.group(1)),
                "side": match.group(2),
                "call": match.group(3),
                "seconds": float(match.group(4)),
                "result": "\n".join(body),
            })
            continue
        i += 1
    answer, _ = quoted(lines, answer_at + 1)
    return entries, answer


def neutral(text: str) -> str:
    """
    Replace the workspace of the session with `WORKSPACE`.

    Parameters
    ----------
    text : str
        Text of the trace.

    Returns
    -------
    text : str
        The same text with neutral paths.

    """

    return text.replace("<ws>", WORKSPACE)


def build_entries(entries: list[dict]) -> list[dict]:
    """
    Entries of the animation, with the declared trims applied and checked.

    Parameters
    ----------
    entries : list of dict
        Output of `parse_session()`.

    Returns
    -------
    shown : list of dict
        One dict per message or call, as the animation reads them.

    """

    shown = []
    for entry in entries:
        if entry["kind"] != "step":
            shown.append({"kind": entry["kind"], "text": neutral(entry["text"])})
            continue
        n, call = entry["n"], entry["call"]
        trimmed = n in CALL_PREFIXES
        if trimmed:
            if not call.startswith(CALL_PREFIXES[n]):
                raise SystemExit(f"Step {n}: the call does not start with its prefix.")
            call = CALL_PREFIXES[n]
        rows = []
        for fragments in EXCERPTS.get(n, []):
            for fragment in fragments:
                if fragment not in entry["result"]:
                    raise SystemExit(f"Step {n}: {fragment!r} is not in the trace.")
            rows.append([neutral(fragment) for fragment in fragments])
        if entry["side"] == "MCP" and not rows:
            raise SystemExit(f"Step {n}: a call of the server without an excerpt.")
        shown.append({
            "kind": "tool" if entry["side"] == "MCP" else "client",
            "n": n,
            "call": neutral(call),
            "trimmed": trimmed,
            "seconds": entry["seconds"],
            "excerpts": rows,
        })
    return shown


def build_answer(answer: str) -> list:
    """
    Lines of the final answer, with the declared trims.

    Parameters
    ----------
    answer : str
        Output of `parse_session()`.

    Returns
    -------
    lines : list
        Strings, and one `{"trim": count, "what": label}` per trim.

    """

    lines = answer.splitlines()
    for first, last, what in ANSWER_TRIMS:
        if lines.count(first) != 1 or lines.count(last) != 1:
            raise SystemExit(f"Anchors of a trim not found once: {first!r}, {last!r}.")
        a, b = lines.index(first), lines.index(last)
        if b - a < 2:
            raise SystemExit(f"Nothing to trim between {first!r} and {last!r}.")
        lines = lines[: a + 1] + [{"trim": b - a - 1, "what": what}] + lines[b:]
    return [neutral(line) if isinstance(line, str) else line for line in lines]


def strings(value) -> list[str]:
    """
    Every string inside a structure of dicts and lists.

    Parameters
    ----------
    value : object
        A string, a number, or a dict or list of them.

    Returns
    -------
    found : list of str
        The strings, keys included.

    """

    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for k, v in value.items() for s in [k, *strings(v)]]
    if isinstance(value, list):
        return [s for v in value for s in strings(v)]
    return []


def header(report: str) -> dict:
    """
    Model, client and versions of the run, from the header of the report.

    Parameters
    ----------
    report : str
        Text of `report.md`.

    Returns
    -------
    source : dict
        Run, session, date, model, client and release of the package.

    """

    model = re.search(r"^- \*\*Model\*\*: `([^`]+)` \(([^,]+),", report, re.M)
    release = re.search(r"^- \*\*Release\*\*: skforecast-ai ([\d.]+)", report, re.M)
    date = re.search(r"^- \*\*Date\*\*: ([\d-]+)", report, re.M)
    return {
        "run": RUN,
        "session": SESSION,
        "report": REPORT.relative_to(REPO_ROOT).as_posix(),
        "date": date.group(1),
        "model": model.group(1),
        "client": model.group(2),
        "skforecast_ai": release.group(1),
    }


def main() -> None:
    """
    Write `OUTPUT` from the session `SESSION` of the run `RUN`.

    Returns
    -------
    None

    """

    report = REPORT.read_text(encoding="utf-8")
    lines = session_lines(report, SESSION)
    unsourced = lines.index("### Numbers without a source")
    if lines[unsourced + 2] != "None.":
        raise SystemExit(f"{SESSION} has numbers without a source: pick another.")
    entries, answer = parse_session(lines)
    payload = {
        "source": header(report),
        "entries": build_entries(entries),
        "answer": build_answer(answer),
    }
    text = json.dumps(payload, separators=(",", ":"))
    leak = PRIVATE.search("\n".join(strings(payload)))
    if leak:
        raise SystemExit(f"A private path is left in the output: {leak.group(0)!r}.")
    OUTPUT.write_text(
        "// Generated by tools/docs/home_page/generate_agent_session_data.py. "
        "Do not edit.\nwindow.AGENT_SESSION_DATA = " + text + ";\n",
        encoding="utf-8",
    )
    calls = sum(entry["kind"] in ("tool", "client") for entry in payload["entries"])
    print(f"Wrote {OUTPUT.relative_to(REPO_ROOT)}: {RUN}, {SESSION}, {calls} calls.")


if __name__ == "__main__":
    main()
