"""
Start of the MCP server: time to the answers of the handshake
(`initialize`), `tools/list` and the first tool, with and without compiled
bytecode.

Subcommands (from the repository root):

    python tools/perf/mcp_startup.py run out.json [--command launcher]
        Starts the server as the plugin does (the launcher `skforecast-ai-mcp`
        with `--allow-project-dir`, over stdio) and times, from the spawn of
        the process, the answer to `initialize`, to `tools/list` and to a
        first `profile` of a small generated CSV, sent as soon as
        `tools/list` is answered. Median of `--repeats` starts for each
        `--bytecode` mode: `cold` sets `PYTHONPYCACHEPREFIX` to a new empty
        directory in every start, so every module is compiled again; `warm`
        sets it to a directory filled by one start that is not counted.
        `--command cli` starts `python -m skforecast_ai.cli mcp` instead.
        Both import skforecast-ai from the checkout `--source` (by default
        this one) through `PYTHONPATH`, so an older revision exported with
        `git archive` gives the times before a change.
        `--call-delay` waits that many seconds between `tools/list` and the
        tool, as a client does while the model writes its first call.
        `--handshake discover` opens with `server/discover` and the version
        of 2026-07-28 in every request instead of `initialize`, as Claude
        Code 2.1.296 does with this server; the column `Handshake` names
        which one was timed.

    python tools/perf/mcp_startup.py run out.json --command uvx [--source .]
        Builds the wheels of the checkout `--source` and of its launcher once
        (not timed), then starts `uvx --from <launcher wheel> --with
        <skforecast-ai wheel>[mcp] skforecast-ai-mcp --allow-project-dir`.
        `cold` gives every start a new empty `UV_CACHE_DIR`: uv downloads and
        installs the dependencies from PyPI and Python compiles every module
        (uv does not compile bytecode by default), the first start of a user.
        `warm` reuses one cache filled by a start that is not counted.

    python tools/perf/mcp_startup.py importtime out.json [--command ...]
        One start with `PYTHONPROFILEIMPORTTIME=1` (the `-X importtime` of
        every process, also through the launcher and uvx) per bytecode mode.
        The lines of the standard error are split by the answer they came
        before: until the handshake, until `tools/list`, until the first
        tool, and after it. Each phase gives its seconds of import (sum of
        the self times; the imports of a background thread are counted in
        the phase they ran in), split by top level package, and its slowest
        modules.

    python tools/perf/mcp_startup.py report out.json [more.json ...]
        Print the tables of one or more outputs as Markdown.

The times include the start of the interpreter. Compare them only between
runs on the same machine, with nothing else running.
"""

from __future__ import annotations
import argparse
import json
import math
import os
import platform
import queue
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from datetime import date
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
PROTOCOL_VERSION = "2025-06-18"
MODERN_VERSION = "2026-07-28"
STEPS = ("handshake", "tools_list", "first_tool")
PHASES = ("handshake", "tools_list", "first_tool", "after")


def write_csv(directory: Path, rows: int = 60) -> Path:
    """
    Write a monthly series of `rows` months with a trend and a yearly
    season, with the standard library only.
    """

    path = directory / "series.csv"
    lines = ["date,y"]
    for i in range(rows):
        month = date(2015 + i // 12, i % 12 + 1, 1)
        value = 100 + 0.5 * i + 10 * math.sin(2 * math.pi * i / 12)
        lines.append(f"{month.isoformat()},{value:.4f}")
    path.write_text("\n".join(lines) + "\n")
    return path


def build_wheels(source: Path, directory: Path) -> tuple[Path, Path]:
    """
    Build the wheel of skforecast-ai and of its launcher from `source`.
    """

    for project in (source, source / "packages" / "skforecast-ai-mcp"):
        subprocess.run(
            ["uv", "build", "--wheel", "--out-dir", str(directory), str(project)],
            check=True, capture_output=True,
        )
    core = next(directory.glob("skforecast_ai-*.whl"))
    launcher = next(directory.glob("skforecast_ai_mcp-*.whl"))
    return core, launcher


def server_command(arguments: argparse.Namespace, wheels, output: Path) -> list[str]:
    """
    Command line of the server for `--command`.
    """

    options = ["--allow-project-dir", "--output-dir", str(output)]
    if arguments.command == "launcher":
        # What the console script `skforecast-ai-mcp` runs.
        code = "import sys; from skforecast_ai_mcp import main; sys.exit(main())"
        return [sys.executable, "-c", code, *options]
    if arguments.command == "cli":
        return [sys.executable, "-m", "skforecast_ai.cli", "mcp", *options]
    core, launcher = wheels
    return [
        "uvx", "--from", str(launcher), "--with", f"{core}[mcp]",
        "skforecast-ai-mcp", *options,
    ]


def server_environment(
    arguments: argparse.Namespace, data_dir: Path, bytecode: Path | None
) -> dict[str, str]:
    """
    Environment of the server: the project directory of the plugin and the
    directory of the bytecode (`PYTHONPYCACHEPREFIX`, or `UV_CACHE_DIR` with
    uvx, which installs into its cache).
    """

    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(data_dir)
    env.pop("PYTHONPROFILEIMPORTTIME", None)
    if arguments.command in ("launcher", "cli"):
        # The checkout of `--source` first, before the installed package.
        source = arguments.source.resolve()
        paths = [str(source)]
        if arguments.command == "launcher":
            paths.insert(0, str(source / "packages" / "skforecast-ai-mcp"))
        env["PYTHONPATH"] = os.pathsep.join(
            filter(None, [*paths, env.get("PYTHONPATH")])
        )
    if arguments.command == "uvx":
        env["UV_CACHE_DIR"] = str(bytecode)
        env.pop("PYTHONPYCACHEPREFIX", None)
    elif bytecode is not None:
        env["PYTHONPYCACHEPREFIX"] = str(bytecode)
    return env


class Session:
    """
    A server over stdio and a minimal JSON-RPC client of it, with the time
    of every answer counted from the spawn of the process.
    """

    def __init__(self, command: list[str], env: dict[str, str], cwd: Path) -> None:
        self.start = time.perf_counter()
        self.process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=env, cwd=cwd, text=True, bufsize=1,
        )
        self.messages: queue.Queue = queue.Queue()
        self.stderr: list[tuple[float, str]] = []
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()
        self.next_id = 0
        # Sent in every request with the protocol of 2026-07-28.
        self.meta: dict | None = None

    def _read_stdout(self) -> None:
        for line in self.process.stdout:
            self.messages.put((time.perf_counter(), json.loads(line)))
        self.messages.put((time.perf_counter(), None))

    def _read_stderr(self) -> None:
        for line in self.process.stderr:
            self.stderr.append((time.perf_counter(), line.rstrip("\n")))

    def send(self, method: str, params: dict | None = None, notify: bool = False):
        message = {"jsonrpc": "2.0", "method": method}
        if self.meta is not None:
            params = {**(params or {}), "_meta": self.meta}
        if params is not None:
            message["params"] = params
        if not notify:
            self.next_id += 1
            message["id"] = self.next_id
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()
        return message.get("id")

    def request(self, method: str, params: dict | None, timeout: float) -> tuple:
        """
        Send a request and wait for its answer; return the seconds since the
        spawn and the result. Notifications of the server are skipped.
        """

        sent = time.perf_counter()
        request_id = self.send(method, params)
        deadline = sent + timeout
        while True:
            try:
                received, message = self.messages.get(
                    timeout=max(0.0, deadline - time.perf_counter())
                )
            except queue.Empty:
                raise TimeoutError(f"{method}: no answer in {timeout} s") from None
            if message is None:
                tail = "\n".join(line for _, line in self.stderr[-20:])
                raise RuntimeError(f"{method}: the server exited.\n{tail}")
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise RuntimeError(f"{method}: {message['error']}")
            return received - self.start, received - sent, message["result"]

    def close(self) -> None:
        self.process.stdin.close()
        try:
            self.process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()


def one_start(
    arguments: argparse.Namespace,
    wheels,
    work: Path,
    csv_path: Path,
    bytecode: Path | None,
    importtime: bool = False,
) -> dict:
    """
    Start the server once, ask the handshake (`initialize`, or
    `server/discover` with `--handshake discover`), `tools/list` and
    `profile`, and return the seconds of each answer since the spawn.
    """

    output = Path(tempfile.mkdtemp(prefix="out_", dir=work))
    env = server_environment(arguments, csv_path.parent, bytecode)
    if importtime:
        env["PYTHONPROFILEIMPORTTIME"] = "1"
    session = Session(
        server_command(arguments, wheels, output), env, csv_path.parent
    )
    result: dict = {}
    try:
        client = {"name": "mcp_startup", "version": "1"}
        if arguments.handshake == "discover":
            # As Claude Code 2.1.296 does: no `initialize` and no
            # `notifications/initialized`, the version in every request.
            session.meta = {
                "io.modelcontextprotocol/protocolVersion": MODERN_VERSION,
                "io.modelcontextprotocol/clientInfo": client,
                "io.modelcontextprotocol/clientCapabilities": {},
            }
            result["handshake"], _, answer = session.request(
                "server/discover", None, arguments.timeout
            )
        else:
            result["handshake"], _, answer = session.request(
                "initialize",
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": client,
                },
                arguments.timeout,
            )
            session.send("notifications/initialized", notify=True)
        result["server"] = answer.get("serverInfo", {})
        result["tools_list"], _, answer = session.request(
            "tools/list", {}, arguments.timeout
        )
        result["tools"] = len(answer["tools"])
        if arguments.call_delay:
            time.sleep(arguments.call_delay)
        result["first_tool"], result["first_tool_call"], answer = session.request(
            "tools/call",
            {
                "name": "profile",
                "arguments": {"data_path": str(csv_path), "target": "y"},
            },
            arguments.timeout,
        )
        if answer.get("isError"):
            raise RuntimeError(f"profile: {answer['content'][0]['text']}")
        marks = {name: session.start + result[name] for name in STEPS}
    finally:
        session.close()
        shutil.rmtree(output, ignore_errors=True)
    if importtime:
        result["imports"] = split_importtime(session.stderr, marks)
    return result


IMPORT_LINE = re.compile(r"import time:\s+(\d+) \|\s+(\d+) \|( *)(\S+)")


def split_importtime(lines: list[tuple[float, str]], marks: dict) -> dict:
    """
    Split the `-X importtime` lines of a start by the answer they came
    before, and sum the self time of each phase by top level package.
    """

    phases = {name: {"seconds": 0.0, "modules": 0, "packages": {}, "slowest": []}
              for name in PHASES}
    for when, line in lines:
        match = IMPORT_LINE.match(line)
        if not match:
            continue
        phase = next(
            (name for name in STEPS if when <= marks[name]), "after"
        )
        self_s = int(match.group(1)) / 1e6
        cumulative = int(match.group(2)) / 1e6
        module = match.group(4)
        package = module.split(".")[0]
        entry = phases[phase]
        entry["seconds"] += self_s
        entry["modules"] += 1
        entry["packages"][package] = entry["packages"].get(package, 0.0) + self_s
        entry["slowest"].append((module, cumulative))
    for entry in phases.values():
        entry["seconds"] = round(entry["seconds"], 4)
        entry["packages"] = {
            name: round(seconds, 4)
            for name, seconds in sorted(entry["packages"].items(), key=lambda i: -i[1])
        }
        entry["slowest"] = [
            [name, round(seconds, 4)]
            for name, seconds in sorted(entry["slowest"], key=lambda i: -i[1])[:12]
        ]
    return phases


def environment() -> dict:
    """
    Revision (with `-dirty` for uncommitted changes) and versions of the run.
    """

    revision = subprocess.run(
        ["git", "describe", "--always", "--dirty"],
        capture_output=True, text=True, cwd=REPOSITORY,
    ).stdout.strip()
    return {
        "revision": revision,
        "python": platform.python_version(),
        "system": platform.system(),
        "machine": platform.machine(),
        "cpus": os.cpu_count(),
    }


def run(arguments: argparse.Namespace, importtime: bool = False) -> dict:
    """
    Time `--repeats` starts per bytecode mode (one with `importtime`).
    """

    output = {
        "environment": environment(),
        "command": arguments.command,
        "handshake": arguments.handshake,
        "call_delay": arguments.call_delay,
        "modes": {},
    }
    work = Path(tempfile.mkdtemp(prefix="mcp_startup_"))
    try:
        csv_path = write_csv(Path(tempfile.mkdtemp(prefix="data_", dir=work)))
        wheels = None
        if arguments.command == "uvx":
            wheels = build_wheels(arguments.source.resolve(), work / "wheels")
        for mode in arguments.bytecode:
            warm = Path(tempfile.mkdtemp(prefix="warm_", dir=work))
            if mode == "warm":
                one_start(arguments, wheels, work, csv_path, warm)
            starts = []
            for i in range(1 if importtime else arguments.repeats):
                bytecode = (
                    warm if mode == "warm"
                    else Path(tempfile.mkdtemp(prefix="cold_", dir=work))
                )
                starts.append(
                    one_start(arguments, wheels, work, csv_path, bytecode, importtime)
                )
                if mode == "cold":
                    shutil.rmtree(bytecode, ignore_errors=True)
                print(
                    f"{mode} {i + 1}: "
                    + ", ".join(f"{s} {starts[-1][s]:.2f} s" for s in STEPS),
                    flush=True,
                )
            entry = {
                "server": starts[0]["server"],
                "tools": starts[0]["tools"],
                "starts": len(starts),
            }
            for step in (*STEPS, "first_tool_call"):
                values = [start[step] for start in starts]
                entry[step] = {
                    "median": round(statistics.median(values), 3),
                    "times": [round(value, 3) for value in values],
                }
            if importtime:
                entry["imports"] = starts[0]["imports"]
            output["modes"][mode] = entry
            shutil.rmtree(warm, ignore_errors=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return output


def report(paths: list[Path]) -> None:
    """
    Print the tables of the outputs as Markdown.
    """

    print("| Output | Command | Bytecode | Handshake | Answer | `tools/list` "
          "| First tool | Its call | Starts |")
    print("| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |")
    for path in paths:
        data = json.loads(path.read_text())
        for mode, entry in data["modes"].items():
            cells = [f"{entry[step]['median']:.2f} s"
                     for step in (*STEPS, "first_tool_call")]
            handshake = data.get("handshake", "initialize")
            print(f"| {path.name} | {data['command']} | {mode} | {handshake} | "
                  + " | ".join(cells) + f" | {entry['starts']} |")
    for path in paths:
        data = json.loads(path.read_text())
        for mode, entry in data["modes"].items():
            if "imports" not in entry:
                continue
            print(f"\n{path.name}, {mode}: seconds of import by phase\n")
            print("| Phase | Seconds | Modules | By package |")
            print("| --- | ---: | ---: | --- |")
            for phase, values in entry["imports"].items():
                packages = ", ".join(
                    f"{name} {seconds:.2f}"
                    for name, seconds in list(values["packages"].items())[:8]
                )
                print(f"| {phase} | {values['seconds']:.2f} | "
                      f"{values['modules']} | {packages} |")


def main() -> int:
    """
    Command line entry point.
    """

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("subcommand", choices=["run", "importtime", "report"])
    parser.add_argument("output", type=Path, nargs="+")
    parser.add_argument(
        "--command", choices=["launcher", "cli", "uvx"], default="launcher"
    )
    parser.add_argument("--bytecode", default="warm,cold")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument(
        "--handshake", choices=["initialize", "discover"], default="initialize"
    )
    parser.add_argument("--call-delay", type=float, default=0.0)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--source", type=Path, default=REPOSITORY)
    arguments = parser.parse_args()
    if arguments.subcommand == "report":
        report(arguments.output)
        return 0
    arguments.output = arguments.output[0]
    arguments.bytecode = arguments.bytecode.split(",")
    if set(arguments.bytecode) - {"warm", "cold"}:
        parser.error("--bytecode takes warm, cold or both")
    result = run(arguments, importtime=arguments.subcommand == "importtime")
    arguments.output.write_text(json.dumps(result, indent=1))
    print(f"Written {arguments.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
