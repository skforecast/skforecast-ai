"""
Timing of the public API and the MCP server, to find where the time goes.

Subcommands (from the repository root):

    python tools/perf/timing.py api out.json [--sizes small,medium,large]
        Wall time of every public call (median of `--repeats` runs; a call
        slower than `--budget` seconds runs once), and a cProfile run of each
        call that splits its time by package: own code (skforecast_ai),
        skforecast, pandas, numpy, the estimator (sklearn, lightgbm,
        statsmodels, scipy), pydantic, built-in C functions and the rest.
        The split adds up the self time of every function, so it sums to the
        profiled total. The profiled run is one more run of the call, also
        for the calls over the budget. The `.prof` files go to the folder
        `<out>_prof`, to read with `pstats` or `snakeviz`.

    python tools/perf/timing.py mcp out.json [--sizes ...]
        `skforecast-ai mcp` over stdio: the start of the server (spawn to
        the end of `initialize`) and every tool, median of `--repeats`
        sessions (one when `compare` is over the budget). Also an in-process
        cProfile of one session, with the same split by package.

    python tools/perf/timing.py imports out.json
        `python -X importtime` of `import skforecast_ai` and of
        `import skforecast_ai.mcp` (median of `--repeats`), with the slowest
        modules.

    python tools/perf/timing.py memory out.json
        Peak memory of `profile()` on the large data, with tracemalloc.

    python tools/perf/timing.py report out.json [more.json ...]
        Print the tables of one or more outputs as Markdown.

Sizes: small is h2o (204 rows), medium bike_sharing (17520 hourly rows with
exogenous variables), large store_sales (913000 rows in long format, 500
series; synthetic data of the same shape if the download fails, and the
output says so). The output is written after each size, and a call that
raises is recorded with its error, so a failure keeps what already ran.
"""

from __future__ import annotations
import argparse
import cProfile
import importlib.util
import json
import os
import platform
import pstats
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import traceback
import warnings
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _datasets import DEFAULT_DATA_DIR, SIZES, Scenario  # noqa: E402

API_CALLS = [
    "profile", "plan", "refine_plan", "create_cv", "forecast_code",
    "backtest_code", "forecast", "backtest", "compare",
]
MCP_TOOLS = [
    "profile", "plan", "refine_plan", "create_cv", "backtest", "compare",
    "forecast", "get_code", "get_failure", "list_objects", "describe_object",
]
# Label of each package in the split, and the import names it covers.
PACKAGES = {
    "skforecast_ai": ["skforecast_ai"],
    "skforecast": ["skforecast"],
    "pandas": ["pandas"],
    "numpy": ["numpy"],
    "estimator": [
        "sklearn", "lightgbm", "statsmodels", "scipy", "xgboost", "catboost",
    ],
    "pydantic": ["pydantic", "pydantic_core"],
}


def _package_roots() -> list[tuple[str, str]]:
    """
    Install directory of each package of the split, longest first, so a
    package installed inside another one is matched before it.
    """

    roots = []
    for label, names in PACKAGES.items():
        for name in names:
            spec = importlib.util.find_spec(name)
            if spec is None or not spec.submodule_search_locations:
                continue
            for location in spec.submodule_search_locations:
                roots.append((os.path.realpath(location) + os.sep, label))
    return sorted(roots, key=lambda root: -len(root[0]))


_ROOTS = _package_roots()


def _package_of(filename: str) -> str:
    """
    Label of the package a profiled function belongs to, by the directory
    its file is installed in.
    """

    if filename.startswith(("~", "<")):
        # cProfile names C functions `~`: their time is counted apart, since
        # it cannot be told whether numpy, pandas or Python called them.
        return "builtins"
    path = os.path.realpath(filename)
    for root, label in _ROOTS:
        if path.startswith(root):
            return label
    return "other"


def split_by_package(stats: pstats.Stats) -> dict[str, float]:
    """
    Self time of a cProfile run, summed by package.

    Parameters
    ----------
    stats : pstats.Stats
        Statistics of the run.

    Returns
    -------
    split : dict
        Seconds by package label, largest first.
    """

    totals: dict[str, float] = {}
    for (filename, _, _), (_, _, tottime, _, _) in stats.stats.items():
        package = _package_of(filename)
        totals[package] = totals.get(package, 0.0) + tottime
    return dict(sorted(totals.items(), key=lambda item: -item[1]))


def own_functions(stats: pstats.Stats, total: float, limit: int = 15) -> list:
    """
    Functions of skforecast_ai by cumulative time.

    Parameters
    ----------
    stats : pstats.Stats
        Statistics of the run.
    total : float
        Profiled seconds of the call, for the share of each function.
    limit : int, default 15
        Number of functions returned.

    Returns
    -------
    rows : list of dict
        Function (module, line and name), calls, cumulative time, share of
        the call and self time.
    """

    own_root = next(root for root, label in _ROOTS if label == "skforecast_ai")
    rows = []
    for (filename, line, name), (_, ncalls, tottime, cumtime, _) in stats.stats.items():
        if _package_of(filename) != "skforecast_ai":
            continue
        module = os.path.realpath(filename)[len(own_root):]
        rows.append({
            "function": f"{module}:{line}:{name}",
            "calls": ncalls,
            "cumtime": round(cumtime, 4),
            "share": round(cumtime / total, 3) if total else 0.0,
            "tottime": round(tottime, 4),
        })
    rows.sort(key=lambda row: -row["cumtime"])
    return rows[:limit]


def _summary(profiler: cProfile.Profile, limit: int) -> dict:
    """
    Split by package, share of own code and slowest own functions of a run.
    """

    stats = pstats.Stats(profiler)
    split = split_by_package(stats)
    total = sum(split.values())
    return {
        "split": {key: round(value, 4) for key, value in split.items()},
        "own_share": (
            round(split.get("skforecast_ai", 0.0) / total, 3) if total else 0.0
        ),
        "own_functions": own_functions(stats, total, limit),
    }


def _profiled(function: Callable[[], Any], prof_path: Path) -> dict:
    """
    Run a call once under cProfile; save the `.prof` file and summarize it.
    """

    profiler = cProfile.Profile()
    start = time.perf_counter()
    profiler.enable()
    try:
        function()
    finally:
        profiler.disable()
    elapsed = time.perf_counter() - start
    profiler.dump_stats(prof_path)
    return {"profiled_seconds": round(elapsed, 4), **_summary(profiler, 15)}


def _timed(function: Callable[[], Any], repeats: int, budget: float) -> dict:
    """
    Wall time of `repeats` runs of a call (one when the first is over
    `budget` seconds).
    """

    times = []
    for _ in range(repeats):
        start = time.perf_counter()
        function()
        times.append(time.perf_counter() - start)
        if times[0] > budget:
            break
    return {
        "median": round(statistics.median(times), 6),
        "runs": len(times),
        "times": [round(t, 6) for t in times],
    }


def api_calls(scenario: Scenario) -> dict[str, Callable[[], Any]]:
    """
    One closure per public call, each with the inputs built by the earlier
    steps (computed once, outside the timed region).

    Parameters
    ----------
    scenario : Scenario
        Dataset and arguments.

    Returns
    -------
    calls : dict
        Closure of each call of `API_CALLS`, and `forecast_test_size`.
    """

    from skforecast_ai import ForecastingAssistant

    assistant = ForecastingAssistant()
    data = scenario.data
    arguments = scenario.data_arguments
    steps = scenario.steps
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        profile = assistant.profile(data, **arguments)
        plan = assistant.plan(profile=profile, steps=steps)
        cv = assistant.create_cv(profile=profile, plan=plan)
    return {
        "profile": lambda: assistant.profile(data, **arguments),
        "plan": lambda: assistant.plan(profile=profile, steps=steps),
        "refine_plan": lambda: assistant.refine_plan(profile, plan, steps=steps * 2),
        "create_cv": lambda: assistant.create_cv(profile=profile, plan=plan),
        "forecast_code": lambda: assistant.forecast_code(profile=profile, plan=plan),
        "backtest_code": lambda: assistant.backtest_code(
            data, cv=cv, profile=profile, plan=plan
        ),
        "forecast": lambda: assistant.forecast(
            data, profile=profile, plan=plan, exog=scenario.future_exog
        ),
        # Evaluation mode, outside the default list (`--calls`): its checks
        # read the training partition and the test dates.
        "forecast_test_size": lambda: assistant.forecast(
            data, steps=steps, test_size=steps, **arguments
        ),
        "backtest": lambda: assistant.backtest(
            data, cv=cv, profile=profile, plan=plan, show_progress=False
        ),
        "compare": lambda: assistant.compare(
            data, cv=cv, profile=profile, show_progress=False
        ),
    }


def _environment() -> dict:
    """
    Revision (with `-dirty` for uncommitted changes) and versions of the run.
    """

    import pandas as pd
    import skforecast

    import skforecast_ai

    revision = subprocess.run(
        ["git", "describe", "--always", "--dirty"], capture_output=True, text=True
    ).stdout.strip()
    return {
        "revision": revision,
        "python": platform.python_version(),
        "machine": platform.machine(),
        "cpus": os.cpu_count(),
        "skforecast_ai": skforecast_ai.__version__,
        "skforecast": skforecast.__version__,
        "pandas": pd.__version__,
    }


def _prof_dir(output: Path) -> Path:
    """
    Folder of the `.prof` files of an output, next to it.
    """

    directory = output.parent / f"{output.stem}_prof"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _write(output: Path, result: dict) -> None:
    output.write_text(json.dumps(result, indent=1))


def run_api(arguments: argparse.Namespace) -> dict:
    """
    Time and profile every public call on each size; write the output
    after each size.

    Parameters
    ----------
    arguments : argparse.Namespace
        Parsed command line.

    Returns
    -------
    result : dict
        Environment and, by size, the timing of each call.
    """

    output: dict = {"environment": _environment(), "api": {}}
    prof_dir = _prof_dir(arguments.output)
    for size in arguments.sizes:
        scenario = SIZES[size](arguments.data_dir)
        print(f"{size} ({scenario.name}, {scenario.n_rows} rows)", flush=True)
        entry: dict = {"dataset": scenario.name, "rows": scenario.n_rows,
                       "notes": scenario.notes, "calls": {}}
        output["api"][size] = entry
        calls = api_calls(scenario)
        for name in arguments.calls or API_CALLS:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    timing = _timed(calls[name], arguments.repeats, arguments.budget)
                    profiled = (
                        _profiled(calls[name], prof_dir / f"{size}_{name}.prof")
                        if arguments.profile else {}
                    )
            except Exception:  # noqa: BLE001 - recorded, the run goes on
                entry["calls"][name] = {"error": traceback.format_exc(limit=3)}
                print(f"  {name}: failed", flush=True)
                continue
            entry["calls"][name] = {**timing, **profiled}
            print(
                f"  {name}: {timing['median']:.3f} s "
                f"(own {profiled.get('own_share', 0):.0%})",
                flush=True,
            )
        _write(arguments.output, output)
    return output


def _write_csv(scenario: Scenario, directory: Path) -> tuple[dict, str | None]:
    """
    Write the data of a scenario as CSV files for the server.

    Returns
    -------
    profile_arguments : dict
        Arguments of the `profile` tool.
    exog_path : str, None
        Path of the CSV of future exogenous values, if the data has any.
    """

    path = directory / f"{scenario.name}.csv"
    frame = scenario.data
    if scenario.date_column is None:
        frame = frame.reset_index()
    frame.to_csv(path, index=False)
    exog_path = None
    if scenario.future_exog is not None:
        exog_path = str(directory / f"{scenario.name}_exog.csv")
        scenario.future_exog.reset_index().to_csv(exog_path, index=False)
    return {"data_path": str(path), **scenario.data_arguments}, exog_path


async def _session(client, profile_arguments: dict, steps: int, exog_path) -> dict:
    """
    Call every tool once; return the seconds of each. A tool error stops
    the session, except for `get_failure` of a comparison without failures.
    """

    times = {}

    async def call(name: str, arguments: dict) -> dict:
        start = time.perf_counter()
        result = await client.call_tool(name, arguments)
        times[name] = time.perf_counter() - start
        if result.is_error and name != "get_failure":
            raise RuntimeError(f"{name}: {result.content[0].text}")
        return result.structured_content or {}

    profile = await call("profile", profile_arguments)
    plan = await call("plan", {"profile_id": profile["id"], "steps": steps})
    await call(
        "refine_plan", {"plan_id": plan["id"], "overrides": {"steps": steps * 2}}
    )
    cv = await call("create_cv", {"plan_id": plan["id"]})
    await call("backtest", {"cv_id": cv["id"]})
    comparison = await call("compare", {"cv_id": cv["id"]})
    forecast_arguments = {"plan_id": plan["id"]}
    if exog_path:
        forecast_arguments["exog_path"] = exog_path
    await call("forecast", forecast_arguments)
    await call("get_code", {"object_id": plan["id"]})
    await call("get_failure", {"object_id": comparison["id"]})
    await call("list_objects", {})
    await call("describe_object", {"object_id": comparison["id"]})
    return times


def run_mcp(arguments: argparse.Namespace) -> dict:
    """
    Time the server over stdio on each size, and profile one session in
    process; write the output after each size.

    Parameters
    ----------
    arguments : argparse.Namespace
        Parsed command line.

    Returns
    -------
    result : dict
        Environment and, by size, the timing of the start and of each tool.
    """

    import anyio
    from mcp import Client, StdioServerParameters

    output: dict = {"environment": _environment(), "mcp": {}}
    prof_dir = _prof_dir(arguments.output)
    work = Path(tempfile.mkdtemp(prefix="skforecast_ai_mcp_"))
    try:
        for size in arguments.sizes:
            scenario = SIZES[size](arguments.data_dir)
            data_dir = work / size
            data_dir.mkdir()
            profile_arguments, exog_path = _write_csv(scenario, data_dir)
            print(f"{size} ({scenario.name})", flush=True)
            parameters = StdioServerParameters(
                command = sys.executable,
                args    = [
                    "-c", "from skforecast_ai.cli import app; app()", "mcp",
                    "--allow-dir", str(data_dir),
                    "--output-dir", str(data_dir / "out"),
                ],
                env     = dict(os.environ),
                cwd     = str(data_dir),
            )

            async def main():
                start = time.perf_counter()
                async with Client(parameters) as client:
                    started = time.perf_counter() - start
                    times = await _session(
                        client, profile_arguments, scenario.steps, exog_path
                    )
                return {"startup": started, **times}

            entry: dict = {"dataset": scenario.name, "notes": scenario.notes}
            output["mcp"][size] = entry
            runs: list[dict] = []
            try:
                for _ in range(arguments.repeats):
                    runs.append(anyio.run(main))
                    if runs[0]["compare"] > arguments.budget:
                        break
            except Exception:  # noqa: BLE001 - recorded, the run goes on
                entry["error"] = traceback.format_exc(limit=3)
                print("  failed", flush=True)
            entry["runs"] = len(runs)
            entry["tools"] = {}
            for name in ["startup", *MCP_TOOLS] if runs else []:
                values = [run[name] for run in runs]
                entry["tools"][name] = {
                    "median": round(statistics.median(values), 6),
                    "times": [round(v, 6) for v in values],
                }
                print(f"  {name}: {entry['tools'][name]['median']:.3f} s", flush=True)
            if arguments.profile and runs:
                entry["profiled"] = _profile_mcp_in_process(
                    data_dir, profile_arguments, scenario.steps, exog_path,
                    prof_dir / f"mcp_{size}.prof",
                )
            _write(arguments.output, output)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return output


def _profile_mcp_in_process(
    data_dir: Path,
    profile_arguments: dict,
    steps: int,
    exog_path: str | None,
    prof_path: Path,
) -> dict:
    """
    cProfile of one session against a server in this process (in-memory
    client), split by package.
    """

    import anyio
    from mcp import Client

    from skforecast_ai.mcp import create_server

    server = create_server(allow_dir=data_dir, output_dir=data_dir / "out_profiled")

    async def main():
        async with Client(server) as client:
            return await _session(client, profile_arguments, steps, exog_path)

    profiler = cProfile.Profile()
    profiler.enable()
    try:
        anyio.run(main)
    finally:
        profiler.disable()
    profiler.dump_stats(prof_path)
    return _summary(profiler, 25)


def _importtime(module: str) -> tuple[float, list[tuple[str, float]]]:
    """
    Cumulative import time of `module` in a new interpreter, and the 15
    modules with the largest cumulative time.
    """

    result = subprocess.run(
        [sys.executable, "-X", "importtime", "-c", f"import {module}"],
        capture_output=True, text=True, check=True,
    )
    rows = []
    for line in result.stderr.splitlines():
        match = re.match(r"import time:\s+(\d+) \|\s+(\d+) \|\s*(\S+)", line)
        if match:
            rows.append((match.group(3), int(match.group(2)) / 1e6))
    total = next(seconds for name, seconds in reversed(rows) if name == module)
    return total, sorted(rows, key=lambda row: -row[1])[:15]


def run_imports(arguments: argparse.Namespace) -> dict:
    """
    `-X importtime` of the package and of its MCP server.

    Parameters
    ----------
    arguments : argparse.Namespace
        Parsed command line.

    Returns
    -------
    result : dict
        Environment and, by module, the median seconds and slowest imports.
    """

    output: dict = {"environment": _environment(), "imports": {}}
    for module in ("skforecast_ai", "skforecast_ai.mcp"):
        totals = []
        top: list = []
        for _ in range(arguments.repeats):
            total, top = _importtime(module)
            totals.append(total)
        output["imports"][module] = {
            "median": round(statistics.median(totals), 4),
            "times": [round(t, 4) for t in totals],
            "slowest_cumulative": [[name, round(s, 4)] for name, s in top],
        }
        print(f"{module}: {statistics.median(totals):.3f} s", flush=True)
    return output


def run_memory(arguments: argparse.Namespace) -> dict:
    """
    Peak memory that tracemalloc sees during `profile()` of the large data.

    Parameters
    ----------
    arguments : argparse.Namespace
        Parsed command line.

    Returns
    -------
    result : dict
        Environment, size of the data and peak of `profile()`, in MiB.
    """

    import tracemalloc

    from skforecast_ai import ForecastingAssistant

    scenario = SIZES["large"](arguments.data_dir)
    assistant = ForecastingAssistant()
    data_mb = scenario.data.memory_usage(deep=True).sum() / 2**20
    tracemalloc.start()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assistant.profile(scenario.data, **scenario.data_arguments)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    output = {
        "environment": _environment(),
        "memory": {
            "dataset": scenario.name,
            "rows": scenario.n_rows,
            "data_mb": round(float(data_mb), 1),
            "profile_peak_mb": round(peak / 2**20, 1),
            "notes": scenario.notes,
        },
    }
    print(output["memory"], flush=True)
    return output


_API_COLUMNS = [
    "Call", "Median (s)", "Runs", "Own share", "Own (s)", "skforecast",
    "pandas", "numpy", "estimator",
]


def report(paths: list[Path]) -> None:
    """
    Print the tables of timing outputs as Markdown.

    Parameters
    ----------
    paths : list of Path
        Outputs of the `api`, `mcp`, `imports` and `memory` subcommands.

    Returns
    -------
    None
    """

    for path in paths:
        data = json.loads(path.read_text())
        print(f"## {path.name} ({data['environment']['revision']})\n")
        for size, entry in data.get("api", {}).items():
            print(f"### API, {size}: {entry['dataset']} ({entry['rows']} rows)\n")
            print("| " + " | ".join(_API_COLUMNS) + " |")
            print("|" + "---|" * len(_API_COLUMNS))
            for name, call in entry["calls"].items():
                if "error" in call:
                    print(f"| {name} | failed |" + " |" * (len(_API_COLUMNS) - 2))
                    continue
                split = call.get("split", {})
                cells = [
                    name, f"{call['median']:.3f}", str(call["runs"]),
                    f"{call.get('own_share', 0):.0%}",
                    *(
                        f"{split.get(label, 0):.3f}"
                        for label in ("skforecast_ai", "skforecast", "pandas",
                                      "numpy", "estimator")
                    ),
                ]
                print("| " + " | ".join(cells) + " |")
            print()
        for size, entry in data.get("mcp", {}).items():
            print(f"### MCP, {size}: {entry['dataset']} ({entry['runs']} sessions)\n")
            print("| Tool | Median (s) |")
            print("|---|---|")
            for name, tool in entry.get("tools", {}).items():
                print(f"| {name} | {tool['median']:.3f} |")
            if "profiled" in entry:
                print(f"\nOwn share in process: {entry['profiled']['own_share']:.0%}")
            print()
        for module, entry in data.get("imports", {}).items():
            print(f"- `import {module}`: {entry['median']:.3f} s")
        if "memory" in data:
            print(f"- memory: {data['memory']}")


def main() -> int:
    """
    Command line entry point.
    """

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "command", choices=["api", "mcp", "imports", "memory", "report"]
    )
    parser.add_argument("output", type=Path, nargs="+")
    parser.add_argument("--sizes", default="small,medium,large")
    parser.add_argument("--calls", default=None, help="Comma separated API calls.")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument(
        "--budget", type=float, default=60.0,
        help="A call slower than this many seconds runs once.",
    )
    parser.add_argument(
        "--no-profile", dest="profile", action="store_false",
        help="Skip the cProfile runs.",
    )
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    arguments = parser.parse_args()
    if arguments.command == "report":
        report(arguments.output)
        return 0
    arguments.output = arguments.output[0]
    arguments.sizes = arguments.sizes.split(",")
    unknown = set(arguments.sizes) - set(SIZES)
    if unknown:
        parser.error(f"unknown sizes {sorted(unknown)}; available: {list(SIZES)}")
    arguments.calls = arguments.calls.split(",") if arguments.calls else None
    runner = {
        "api": run_api, "mcp": run_mcp, "imports": run_imports, "memory": run_memory,
    }[arguments.command]
    result = runner(arguments)
    _write(arguments.output, result)
    print(f"Written {arguments.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
