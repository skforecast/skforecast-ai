################################################################################
#                        generate_mcp_overview_data                            #
#                                                                              #
# Writes docs/animations/mcp-overview-data.js, the data of the animation at    #
# the top of the MCP server guide. See tools/docs/home_page/README.md.         #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

"""
Generate the data of the animation "Your agent asks, skforecast-ai decides".

The animation (`docs/animations/mcp-overview.html`) explains how a coding
agent uses the MCP server: connect, ask, the calls of the deterministic
workflow, the validation against a baseline and the answer with the script.
Its figures are real: this script starts the server of this checkout, opens
an in-memory MCP client against it (as `tests/tests_mcp/` does) and calls the
tools an agent calls for the request of the animation, on the monthly `h2o`
series of skforecast:

    profile -> plan (12 steps) -> create_cv -> compare -> forecast -> get_code

No LLM is involved, so the result is the same on every run. The request of
the user and the answer of the agent are written in the animation, as in the
other animations of the guide; the answer only states figures of this file.

`compare` runs `ForecasterFoundation` with Chronos-2, so the script needs the
`foundation` extra (`chronos-forecasting`) and network access the first time,
to download the dataset and the weights of the model.

Run from the repository root:

    python tools/docs/home_page/generate_mcp_overview_data.py
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

import anyio
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from skforecast_ai import __version__  # noqa: E402

OUTPUT = REPO_ROOT / "docs" / "animations" / "mcp-overview-data.js"
STEPS = 12
# Neutral project directory shown instead of the temporary one of the run.
WORKSPACE = "~/project"


def load_h2o() -> pd.DataFrame:
    """
    The monthly `h2o` dataset of skforecast, as the agent check writes it.

    Returns
    -------
    data : pandas DataFrame
        Columns `fecha` (first day of each month) and `x`.

    """

    from skforecast.datasets import fetch_dataset

    data = fetch_dataset("h2o", raw=True, verbose=False)
    return data[["fecha", "x"]]


async def run_tools(server, data_path: str) -> dict:
    """
    Call the tools of the workflow in order and keep their responses.

    Parameters
    ----------
    server : FastMCP
        Server created by `skforecast_ai.mcp.create_server`.
    data_path : str
        Absolute path of the CSV file inside the allowed directory.

    Returns
    -------
    responses : dict
        Structured content of each call, by tool name.

    """

    from mcp import Client

    async def call(client, name: str, arguments: dict) -> dict:
        result = await client.call_tool(name, arguments)
        if result.is_error:
            raise SystemExit(f"{name} failed: {result.content[0].text}")
        return result.structured_content

    out = {}
    async with Client(server) as client:
        out["profile"] = await call(
            client, "profile", {"data_path": data_path, "target": "x"}
        )
        out["plan"] = await call(
            client, "plan", {"profile_id": out["profile"]["id"], "steps": STEPS}
        )
        out["create_cv"] = await call(
            client, "create_cv", {"plan_id": out["plan"]["id"]}
        )
        out["compare"] = await call(
            client, "compare", {"cv_id": out["create_cv"]["id"]}
        )
        best = out["compare"]["links"]["best_plan_id"]
        out["forecast"] = await call(client, "forecast", {"plan_id": best})
        out["get_code"] = await call(
            client, "get_code", {"object_id": out["forecast"]["id"]}
        )
    return out


def summary_line(summary: str, prefix: str) -> str:
    """
    The line of a summary that starts with `prefix`, without the bullet.

    Parameters
    ----------
    summary : str
        Summary of a response.
    prefix : str
        Start of the line, for example `Observations:`.

    Returns
    -------
    line : str
        The line as the server wrote it.

    """

    for line in summary.splitlines():
        line = line.removeprefix("- ").strip()
        if line.startswith(prefix):
            return line
    raise SystemExit(f"No line starting with {prefix!r} in the summary.")


def leaderboard(directory: Path, files: dict) -> list[dict]:
    """
    Rows of the leaderboard file that `compare` wrote.

    Parameters
    ----------
    directory : Path
        Output directory of the server.
    files : dict
        `files` of the response of `compare`.

    Returns
    -------
    rows : list of dict
        Rank, name, forecaster, estimator and MAE of each row.

    """

    frame = pd.read_csv(directory / Path(files["leaderboard"]).name)
    return [
        {
            "rank": int(row["rank"]),
            "name": row["name"],
            "forecaster": row["forecaster"],
            "estimator": None if pd.isna(row["estimator"]) else row["estimator"],
            "mae": round(float(row["mean_absolute_error"]), 4),
        }
        for _, row in frame.iterrows()
    ]


def main() -> None:
    """
    Run the workflow through the MCP server and write `OUTPUT`.

    Returns
    -------
    None

    """

    from skforecast_ai.mcp import create_server

    data = load_h2o()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "data").mkdir()
        data_path = root / "data" / "h2o.csv"
        data.to_csv(data_path, index=False)
        out_dir = root / "out"
        server = create_server(allow_dir=root, output_dir=out_dir)
        responses = anyio.run(run_tools, server, str(data_path))

        names = ("profile", "plan", "create_cv", "compare", "forecast", "get_code")
        profile, plan, cv, comparison, forecast, code = (responses[k] for k in names)
        rows = leaderboard(out_dir, comparison["files"])
        predictions = pd.read_csv(
            out_dir / Path(forecast["files"]["predictions"]).name
        )
        # "'X' beats the baseline 'B' (v) by p%." with one candidate, or
        # "All 3 configurations beat the baseline 'B' (v). The best, 'X',
        # beats it by p%." (or "2 of 3 ... , by p%.") with several.
        baseline = re.search(
            r"beats? the baseline '([^']+)' \(([\d.]+)\)", comparison["summary"]
        )
        gain = baseline and re.search(
            r"by ([\d.]+)%\.", comparison["summary"][baseline.end():]
        )
        if not gain:
            raise SystemExit("The comparison does not say its winner beats the baseline.")
        script = code["code"].replace(str(root), WORKSPACE)

    payload = {
        "version": __version__,
        "steps": STEPS,
        "data_file": "data/h2o.csv",
        "series": {
            "start": str(pd.Timestamp(data["fecha"].iloc[0]).date()),
            "values": [round(float(v), 4) for v in data["x"]],
        },
        "profile": {
            "id": profile["id"],
            "lines": [
                summary_line(profile["summary"], p)
                for p in ("Observations:", "Frequency:", "Date range:")
            ],
            "forecaster": summary_line(plan["summary"], "Forecaster:"),
        },
        "plan": {
            "id": plan["id"],
            "lines": [
                summary_line(plan["summary"], p) for p in ("Estimator:", "Lags:")
            ],
        },
        "cv": {
            "id": cv["id"],
            "lines": [
                summary_line(cv["summary"], p) for p in ("n_folds:", "refit:")
            ],
            "compare_fits": cv["cost"]["compare_estimator_fits"],
        },
        "compare": {
            "id": comparison["id"],
            "rows": rows,
            "baseline": baseline.group(1),
            "baseline_mae": float(baseline.group(2)),
            "gain_pct": float(gain.group(1)),
            "file": Path(comparison["files"]["leaderboard"]).name,
        },
        "forecast": {
            "id": forecast["id"],
            "lines": [
                summary_line(forecast["summary"], p)
                for p in ("Forecaster:", "Steps:", "Index range:")
            ],
            "file": Path(forecast["files"]["predictions"]).name,
            "start": str(pd.Timestamp(predictions.iloc[0, 0]).date()),
            "values": [round(float(v), 4) for v in predictions["pred"]],
        },
        "script": script.strip().splitlines(),
    }
    # The animation says that no response carries rows of the data.
    if any(r.get("values_included") is not False
           for r in (profile, plan, cv, comparison, forecast)):
        raise SystemExit("A response says that it carries values.")
    if rows[0]["name"] == payload["compare"]["baseline"]:
        raise SystemExit("The baseline wins: the answer of the animation would be wrong.")
    text = json.dumps(payload, separators=(",", ":"))
    for private in (str(root), str(Path.home()), tempfile.gettempdir()):
        if private in text:
            raise SystemExit(f"A private path is left in the output: {private!r}.")
    OUTPUT.write_text(
        "// Generated by tools/docs/home_page/generate_mcp_overview_data.py. "
        "Do not edit.\nwindow.MCP_OVERVIEW_DATA = " + text + ";\n",
        encoding="utf-8",
    )
    best = rows[0]
    print(
        f"Wrote {OUTPUT.relative_to(REPO_ROOT)}: {best['name']} ({best['estimator']}) "
        f"MAE {best['mae']}, {payload['compare']['gain_pct']}% below the baseline."
    )


if __name__ == "__main__":
    main()
