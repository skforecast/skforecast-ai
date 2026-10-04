"""
Parity dump of the public API, to check that a change keeps every result.

For each dataset of `_datasets.parity_scenarios()` the script calls, with
the default arguments:

- `profile()` and `plan()`;
- `forecast_code()` and `create_cv()`, then `backtest_code()` with that CV;
- `forecast()` in prediction mode (with the future exogenous values when the
  data has exogenous columns) and in evaluation mode (`test_size=steps`,
  from the data alone);
- `backtest()` with the CV and `compare()` by default.

It writes every result as JSON (`model_dump(mode='json')`, plus the dtypes
of the frames) with the Python warnings of each call. Tracebacks of failed
`compare()` candidates are left out, because their line numbers change with
any edit of the package.

Usage (from the repository root):

    python tools/perf/parity.py dump baseline.json
    python tools/perf/parity.py dump after.json --scenarios h2o_csv,h2o_dataframe
    python tools/perf/parity.py compare baseline.json after.json

`compare` lists every difference (scenario, call and JSON path) and exits
with 1 when there is any.
"""

from __future__ import annotations
import argparse
import json
import math
import subprocess
import sys
import time
import warnings
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _datasets import DEFAULT_DATA_DIR, Scenario, parity_scenarios  # noqa: E402


def _frame_dtypes(result: Any) -> dict:
    """
    Dtypes of the frames a result holds, which the JSON dump loses.
    """

    import pandas as pd

    dtypes = {}
    for name in ("predictions", "metrics", "results"):
        frame = getattr(result, name, None)
        if isinstance(frame, pd.DataFrame):
            dtypes[name] = {str(k): str(v) for k, v in frame.dtypes.items()}
            dtypes[f"{name}.index"] = str(frame.index.dtype)
    return dtypes


def _dump_result(result: Any) -> Any:
    """
    JSON form of a result, without the tracebacks of failed candidates.
    """

    dumped = result.model_dump(mode="json")
    for failure in (dumped.get("failures") or {}).values():
        failure.pop("traceback", None)
    dumped["_dtypes"] = _frame_dtypes(result)
    return dumped


def _call(record: dict, name: str, function, *args, **kwargs) -> Any:
    """
    Run one call, recording its result (or error) and its warnings.
    """

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        start = time.perf_counter()
        try:
            result = function(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - the error is the result
            result = None
            record[name] = {"error": f"{type(exc).__name__}: {exc}"}
        else:
            record[name] = {"result": _dump_result(result)}
        elapsed = time.perf_counter() - start
    record[name]["warnings"] = [
        [w.category.__name__, str(w.message)] for w in caught
    ]
    print(f"  {name}: {elapsed:.2f} s", flush=True)
    return result


def dump_scenario(scenario: Scenario) -> dict:
    """
    Run every call of the parity set on one dataset.
    """

    from skforecast_ai import ForecastingAssistant

    assistant = ForecastingAssistant()
    record: dict = {}
    data = scenario.data
    arguments = scenario.data_arguments
    steps = scenario.steps

    profile = _call(record, "profile", assistant.profile, data, **arguments)
    if profile is None:
        return record
    plan = _call(record, "plan", assistant.plan, profile=profile, steps=steps)
    if plan is None:
        return record
    _call(
        record, "forecast_code", assistant.forecast_code,
        profile=profile, plan=plan,
    )
    cv = _call(record, "create_cv", assistant.create_cv, profile=profile, plan=plan)
    if cv is not None:
        _call(
            record, "backtest_code", assistant.backtest_code,
            data, cv=cv, profile=profile, plan=plan,
        )
    _call(
        record, "forecast", assistant.forecast,
        data, profile=profile, plan=plan, exog=scenario.future_exog,
    )
    _call(
        record, "forecast_test_size", assistant.forecast,
        data, steps=steps, test_size=steps, **arguments,
    )
    if cv is not None:
        _call(
            record, "backtest", assistant.backtest,
            data, cv=cv, profile=profile, plan=plan, show_progress=False,
        )
        _call(
            record, "compare", assistant.compare,
            data, cv=cv, profile=profile, show_progress=False,
        )
    return record


def dump(output: Path, names: list[str] | None, data_dir: Path) -> None:
    """
    Write the parity dump of the selected scenarios to `output`.

    Parameters
    ----------
    output : Path
        JSON file to write.
    names : list of str, None
        Scenarios to run; None runs them all. An unknown name stops the
        script, so a typo does not give an empty dump that compares equal.
    data_dir : Path
        Cache directory of the datasets.

    Returns
    -------
    None
    """

    import pandas as pd
    import skforecast

    import skforecast_ai

    scenarios = parity_scenarios(data_dir)
    unknown = set(names or []) - {scenario.name for scenario in scenarios}
    if unknown:
        raise SystemExit(
            f"Unknown scenarios {sorted(unknown)}; available: "
            f"{[scenario.name for scenario in scenarios]}"
        )
    revision = subprocess.run(
        ["git", "describe", "--always", "--dirty"], capture_output=True, text=True
    ).stdout.strip()
    records = {
        "_versions": {
            "revision": revision,
            "skforecast_ai": skforecast_ai.__version__,
            "skforecast": skforecast.__version__,
            "pandas": pd.__version__,
        }
    }
    for scenario in scenarios:
        if names and scenario.name not in names:
            continue
        print(scenario.name, flush=True)
        records[scenario.name] = dump_scenario(scenario)
    output.write_text(json.dumps(records, indent=1, sort_keys=True))
    print(f"Written {output}")


def _short(value: Any, limit: int = 200) -> str:
    """
    JSON text of a value, cut to `limit` characters.
    """
    text = json.dumps(value, sort_keys=True)
    return text if len(text) <= limit else text[:limit] + "..."


def _differences(old: Any, new: Any, path: str) -> list[str]:
    """
    Every difference between two JSON values, with the path where it is.
    """

    if isinstance(old, dict) and isinstance(new, dict):
        lines = []
        for key in sorted(set(old) | set(new)):
            child = f"{path}.{key}" if path else str(key)
            if key not in old:
                lines.append(f"{child}: only in the second dump: {_short(new[key])}")
            elif key not in new:
                lines.append(f"{child}: only in the first dump: {_short(old[key])}")
            else:
                lines.extend(_differences(old[key], new[key], child))
        return lines
    if isinstance(old, list) and isinstance(new, list):
        if len(old) != len(new):
            return [f"{path}: length {len(old)} != {len(new)}"] + [
                line
                for i, (a, b) in enumerate(zip(old, new))
                for line in _differences(a, b, f"{path}[{i}]")
            ][:20]
        return [
            line
            for i, (a, b) in enumerate(zip(old, new))
            for line in _differences(a, b, f"{path}[{i}]")
        ]
    if isinstance(old, float) and isinstance(new, float):
        # NaN (a metric of a failed candidate) is equal to NaN here.
        if old == new or (math.isnan(old) and math.isnan(new)):
            return []
        return [f"{path}: {_short(old)} != {_short(new)}"]
    if old != new or type(old) is not type(new):
        return [f"{path}: {_short(old)} != {_short(new)}"]
    return []


def compare(first: Path, second: Path) -> int:
    """
    Print the differences between two dumps.

    The revision in `_versions` is left out: the dumps of two revisions
    are compared.

    Parameters
    ----------
    first, second : Path
        Dumps written by `dump`.

    Returns
    -------
    exit_code : int
        0 without differences, 1 otherwise.
    """

    old = json.loads(first.read_text())
    new = json.loads(second.read_text())
    for dumped in (old, new):
        dumped.get("_versions", {}).pop("revision", None)
    lines = _differences(old, new, "")
    for line in lines:
        print(line)
    scenarios = [name for name in old if not name.startswith("_")]
    if lines:
        print(f"{len(lines)} differences")
        return 1
    print(f"No differences ({len(scenarios)} scenarios: {', '.join(scenarios)})")
    return 0


def main() -> int:
    """
    Command line entry point.
    """
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    dump_parser = commands.add_parser("dump", help="Write a parity dump.")
    dump_parser.add_argument("output", type=Path)
    dump_parser.add_argument(
        "--scenarios", default=None, help="Comma separated names (default all)."
    )
    dump_parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    compare_parser = commands.add_parser("compare", help="Compare two dumps.")
    compare_parser.add_argument("first", type=Path)
    compare_parser.add_argument("second", type=Path)
    arguments = parser.parse_args()
    if arguments.command == "dump":
        names = arguments.scenarios.split(",") if arguments.scenarios else None
        dump(arguments.output, names, arguments.data_dir)
        return 0
    return compare(arguments.first, arguments.second)


if __name__ == "__main__":
    sys.exit(main())
