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
`report.md` of the run and writes two cuts of it: `full`, the whole session,
and `short`, an abridged one for the README. The full cut keeps the session
as it is, except for two things:

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

The short cut leaves out more, and only leaves out: the calls of the client
are not shown, of the messages of the agent between calls only those of
`SHORT_TEXTS` stay, the calls of `SHORT_GROUP` share one row and one line of
fragments (its footer says so), the other responses use the fragments of
`SHORT_EXCERPTS`, and the paragraphs of the final answer in
`SHORT_ANSWER_OMITS` become a line that counts them.

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
SESSION = "compare_code__r2"
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
        ["forecaster.fit(series=series)",
         "predictions = forecaster.predict(steps=steps)"],
    ],
}

# The short cut. Messages of the agent between calls that it keeps, by the
# text each one starts with.
SHORT_TEXTS = ["Cost is low", "The winner is"]

# Consecutive calls it draws as one row, with the names of the tools and one
# line of fragments: (step number, fragment of the response of that step).
SHORT_GROUP = [
    (3, "Observations: 204"),
    (3, "Frequency: MS"),
    (4, "ForecasterRecursive + Ridge"),
    (5, "6 folds"),
]

# Fragments of its other responses: one line each.
SHORT_EXCERPTS = {
    6: [
        ["'ForecasterFoundation' beats the baseline 'Baseline (seasonal naive)' "
         "(0.0661) by 13.7%."],
    ],
    7: EXCERPTS[7],
}

# Lines of the final answer trimmed: those strictly between the two anchors.
ANSWER_TRIMS = [
    (
        "from skforecast.foundation import FoundationModel, ForecasterFoundation",
        "steps = 12",
        "lines of the script",
    ),
]

# Paragraphs of the final answer left out of the short cut, by the text each
# one starts with: the table, the requirements and the script stay.
SHORT_ANSWER_OMITS = [
    "I compared 5",
    "**Winner: ForecasterFoundation",
    "Note: this is a pre-trained",
    "I adjusted the data path",
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


def grouped_steps() -> list[int]:
    """
    Step numbers of the calls the short cut draws as one row.

    Returns
    -------
    steps : list of int
        The steps of `SHORT_GROUP`, in order and without repeats.

    """

    return sorted({step for step, _ in SHORT_GROUP})


def build_entries(entries: list[dict], short: bool = False) -> list[dict]:
    """
    Entries of the animation, with the declared trims applied and checked.

    Parameters
    ----------
    entries : list of dict
        Output of `parse_session()`.
    short : bool, default False
        If `True`, the entries of the short cut: the request of the user,
        the messages of `SHORT_TEXTS` and the calls to the server, those of
        `SHORT_GROUP` as one entry and the rest with `SHORT_EXCERPTS`.

    Returns
    -------
    shown : list of dict
        One dict per message or call, as the animation reads them. The entry
        of a group holds the names of its tools in `group`.

    """

    excerpts = SHORT_EXCERPTS if short else EXCERPTS
    texts = [entry["text"] for entry in entries if entry["kind"] == "text"]
    for start in SHORT_TEXTS:
        if sum(text.startswith(start) for text in texts) != 1:
            raise SystemExit(f"Message to keep not found once: {start!r}.")
    shown = []
    group = None
    for entry in entries:
        if short and entry["kind"] == "text":
            if not entry["text"].startswith(tuple(SHORT_TEXTS)):
                continue
            if group is not None and len(group["group"]) < len(grouped_steps()):
                raise SystemExit("A message kept falls inside the group of calls.")
        if short and entry.get("side") == "client":
            continue
        if entry["kind"] != "step":
            shown.append({"kind": entry["kind"], "text": neutral(entry["text"])})
            continue
        n, call = entry["n"], entry["call"]
        if short and n in grouped_steps():
            fragments = [fragment for step, fragment in SHORT_GROUP if step == n]
            for fragment in fragments:
                if fragment not in entry["result"]:
                    raise SystemExit(f"Step {n}: {fragment!r} is not in the trace.")
            if group is None:
                group = {"kind": "tool", "n": n, "call": "", "group": [],
                         "trimmed": False, "seconds": 0.0, "excerpts": [[]]}
                shown.append(group)
            elif shown[-1] is not group:
                raise SystemExit(f"Step {n}: the calls of the group are not in a row.")
            group["group"].append(call[: call.index("(")])
            group["call"] = " -> ".join(group["group"])
            group["seconds"] = round(group["seconds"] + entry["seconds"], 1)
            group["excerpts"][0] += fragments
            continue
        trimmed = n in CALL_PREFIXES
        if trimmed:
            if not call.startswith(CALL_PREFIXES[n]):
                raise SystemExit(f"Step {n}: the call does not start with its prefix.")
            call = CALL_PREFIXES[n]
        rows = []
        for fragments in excerpts.get(n, []):
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


def omit_paragraphs(lines: list[str], starts: list[str]) -> list:
    """
    Replace paragraphs of the final answer with a mark that counts them.

    Parameters
    ----------
    lines : list of str
        Lines of the final answer; a paragraph is one line.
    starts : list of str
        Text each paragraph to leave out starts with.

    Returns
    -------
    lines : list
        The lines, with one `{"trim": count, "what": label}` per run of
        omitted paragraphs: those separated only by blank lines share a mark.

    """

    for start in starts:
        if sum(line.startswith(start) for line in lines) != 1:
            raise SystemExit(f"Paragraph to omit not found once: {start!r}.")
    kept = []
    for line in lines:
        if not line.startswith(tuple(starts)):
            kept.append(line)
            continue
        blanks = 0
        while kept and kept[-1 - blanks] == "":
            blanks += 1
        previous = kept[-1 - blanks] if len(kept) > blanks else None
        if isinstance(previous, dict):
            del kept[len(kept) - blanks:]
            previous["trim"] += 1
            previous["what"] = "paragraphs"
        else:
            kept.append({"trim": 1, "what": "paragraph"})
    return kept


def build_answer(answer: str, short: bool = False) -> list:
    """
    Lines of the final answer, with the declared trims.

    Parameters
    ----------
    answer : str
        Output of `parse_session()`.
    short : bool, default False
        If `True`, the paragraphs of `SHORT_ANSWER_OMITS` are left out too.

    Returns
    -------
    lines : list
        Strings, and one `{"trim": count, "what": label}` per trim.

    """

    lines = answer.splitlines()
    if short:
        lines = omit_paragraphs(lines, SHORT_ANSWER_OMITS)
    for first, last, what in ANSWER_TRIMS:
        if lines.count(first) != 1 or lines.count(last) != 1:
            raise SystemExit(f"Anchors of a trim not found once: {first!r}, {last!r}.")
        a, b = lines.index(first), lines.index(last)
        if b - a < 2:
            raise SystemExit(f"Nothing to trim between {first!r} and {last!r}.")
        trim = {"trim": b - a - 1, "what": what}
        lines = lines[: a + 1] + [trim] + lines[b:]
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
        "cuts": {
            cut: {
                "entries": build_entries(entries, short=cut == "short"),
                "answer": build_answer(answer, short=cut == "short"),
            }
            for cut in ("full", "short")
        },
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
    calls = {
        cut: sum(entry["kind"] in ("tool", "client") for entry in data["entries"])
        for cut, data in payload["cuts"].items()
    }
    print(
        f"Wrote {OUTPUT.relative_to(REPO_ROOT)}: {RUN}, {SESSION}, "
        f"{calls['full']} calls ({calls['short']} in the short cut)."
    )


if __name__ == "__main__":
    main()
