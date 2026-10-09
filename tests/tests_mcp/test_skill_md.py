# Unit test SKILL.md of the MCP server

import re
import sys
from importlib.resources import files
from pathlib import Path

import pytest

from skforecast_ai._constants import (
    COMPARE_FIT_BUDGET,
    DEFAULT_FOUNDATION_MODEL_ID,
    LONG_TRAINING_FITS,
)
from skforecast_ai._future_exog import _SHOWN
from skforecast_ai.exceptions import ERROR_CODES
from skforecast_ai.mcp import create_server
from skforecast_ai.mcp._errors import (
    MAX_DETAIL_CHARS,
    MAX_HINT_CHARS,
    MAX_MESSAGE_CHARS,
    SERVER_ERROR_CODES,
)
from skforecast_ai.mcp._foundation import permissive_adapters, restricted_adapters
from skforecast_ai.mcp._runtime import (
    HEARTBEAT_SECONDS,
    MAX_NOTICE_CHARS,
    MAX_NOTICES,
)
from skforecast_ai.mcp.server import (
    DEFAULT_MAX_FILE_MB,
    FOUNDATION_KWARGS,
    MAX_SUMMARY_CHARS,
)

from .fixtures_mcp import tool_schemas

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = (
    files("skforecast_ai") / "mcp" / "skills" / "skforecast-ai-forecasting" / "SKILL.md"
)
GUIDE_PATH = REPO_ROOT / "docs" / "user-guides" / "mcp-server.md"


def _flat(text: str) -> str:
    """Return `text` with every run of whitespace as one space."""
    return " ".join(text.split())


def test_skill_md_front_matter_follows_agent_skills():
    """
    Test that SKILL.md opens with the front matter of the Agent Skills
    standard: a `name` equal to its directory (lowercase letters and digits
    joined by single hyphens, at most 64 characters) and a `description` of
    at most 1,024 characters.
    """
    skill = SKILL_PATH.read_text(encoding="utf-8")
    match = re.match(r"---\nname: (.+)\ndescription: (.+)\n---\n", skill)

    assert match is not None
    name, description = match.groups()
    assert name == "skforecast-ai-forecasting"
    assert len(name) <= 64
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name)
    assert 0 < len(description) <= 1024
    # Without it the skill is never loaded for a question about privacy.
    assert "what the server or you can see of the user's data" in description


def test_skill_md_names_every_tool_error_code_and_foundation_kwarg(tmp_path):
    """
    Test that SKILL.md stays in step with the server: it calls every tool
    (written as `` `name( ``) and names every error code the server can
    return (those of the core but the two of the LLM, which the server never
    calls, and those of the server) and every keyword argument a foundation
    model takes through the server (written as `` `name` ``).
    """
    skill = SKILL_PATH.read_text(encoding="utf-8")
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")
    tools = [tool["name"] for tool in tool_schemas(server)]
    codes = [code for code in ERROR_CODES if not code.startswith("llm_")]

    missing_tools = [name for name in tools if f"`{name}(" not in skill]
    missing_names = [
        name
        for name in [*codes, *SERVER_ERROR_CODES, *FOUNDATION_KWARGS]
        if f"`{name}`" not in skill
    ]

    assert len(tools) == 11
    assert missing_tools == []
    assert missing_names == []


@pytest.mark.parametrize(
    "phrase",
    [
        f"cut at {MAX_SUMMARY_CHARS:,} characters",
        f"up to {_SHOWN} values of the data",
        f"a message at {MAX_MESSAGE_CHARS:,} characters",
        f"a hint at {MAX_HINT_CHARS:,}",
        f"each text of `details` at {MAX_DETAIL_CHARS:,}",
        f"each notice at {MAX_NOTICE_CHARS:,}",
        f"at most {MAX_NOTICES}, and `notices_omitted` counts the rest",
        "carries only the type of the exception and an id",
        f"Above {LONG_TRAINING_FITS} estimator fits",
        f"the candidates above {COMPARE_FIT_BUDGET}",
        f"(`--max-file-mb`, {DEFAULT_MAX_FILE_MB} MB by default)",
        f"every {HEARTBEAT_SECONDS:g} seconds while it runs",
    ],
    ids=lambda phrase: phrase,
)
def test_skill_md_states_the_limits_of_the_server(phrase):
    """
    Test that every limit SKILL.md gives the agent is the one the server and
    the core apply: summary size, values quoted in a message, sizes of the
    message, hint, details and notices, what an unexpected error carries,
    the largest file, the period of the heartbeat and the two thresholds
    of the cost of a backtest.
    """
    skill = _flat(SKILL_PATH.read_text(encoding="utf-8"))

    assert phrase in skill


@pytest.mark.parametrize(
    "phrase",
    [
        f"longer than {MAX_SUMMARY_CHARS:,} characters",
        f"quote up to {_SHOWN} values of the data",
        f"cuts an error message at {MAX_MESSAGE_CHARS:,} characters",
        f"its hint at {MAX_HINT_CHARS:,}",
        f"each text of its `details` at {MAX_DETAIL_CHARS}",
        f"at most {MAX_NOTICES} warnings of {MAX_NOTICE_CHARS:,} characters",
        "carries only the type of the exception and an id",
        f"of at most `--max-file-mb` ({DEFAULT_MAX_FILE_MB} MB by default)",
        f"every {HEARTBEAT_SECONDS:g} seconds while it runs",
    ],
    ids=lambda phrase: phrase,
)
def test_skill_md_user_guide_states_the_limits_of_the_server(phrase):
    """
    Test that the user guide of the server gives the same limits as the
    server and the core, as decision 4 of 12.1 asks.
    """
    guide = _flat(GUIDE_PATH.read_text(encoding="utf-8"))

    assert phrase in guide


def test_skill_md_is_shipped_and_shown_in_the_docs():
    """
    Test that SKILL.md is package data, has no en dash or em dash, and is
    included whole at the end of the user guide of the server.
    """
    skill = SKILL_PATH.read_text(encoding="utf-8")
    pyproject = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    package_data = pyproject["tool"]["setuptools"]["package-data"]["skforecast_ai"]
    guide = GUIDE_PATH.read_text(encoding="utf-8")

    assert "mcp/skills/**/*" in package_data
    assert re.search("[\u2013\u2014]", skill) is None
    assert '--8<-- "skforecast-ai-forecasting/SKILL.md"' in guide


def test_skill_md_and_guide_name_the_foundation_models_that_need_allow_model():
    """
    Test that SKILL.md and the user guide name the model ID prefix of every
    foundation model that needs `--allow-model`, as derived from the
    information of skforecast, and that the guide also names those that run
    without it, so neither goes out of date when skforecast adds a model.
    """
    skill = SKILL_PATH.read_text(encoding="utf-8")
    guide = GUIDE_PATH.read_text(encoding="utf-8")
    restricted = [p for info in restricted_adapters() for p in info.model_id_prefixes]
    permissive = [p for info in permissive_adapters() for p in info.model_id_prefixes]

    assert [p for p in restricted if f"`{p}`" not in skill] == []
    assert [p for p in restricted + permissive if f"`{p}`" not in guide] == []


@pytest.mark.parametrize(
    "phrase",
    [
        "There is no baseline with several series",
        "`files.best_metrics`",
        "A `mean_absolute_scaled_error` below 1",
        "the worst series is not in it",
        "Never change their file",
        "Only if they agree, write a corrected copy inside the allowed directory",
        f"Its default model is Chronos-2 (`{DEFAULT_FOUNDATION_MODEL_ID}`)",
        "tell the user which model, its license",
        "A fraction only works when it gives exactly `steps` observations",
        "Without `candidates` it runs the forecasters the profile recommends",
        "`exog` is `exog_path`",
        "no response holds rows of the data or of the predictions",
        "The summaries do carry the metrics and the leaderboard",
    ],
    ids=lambda phrase: phrase,
)
def test_skill_md_covers_what_agents_get_wrong(phrase):
    """
    Test that SKILL.md covers the cases found in the review of phase 4: the
    comparison without baseline, problems of the CSV file, foundation
    models, `test_size` as a fraction, `compare` without candidates, the
    names of the Python API in messages and what `values_included` means.
    """
    skill = _flat(SKILL_PATH.read_text(encoding="utf-8"))

    assert phrase in skill


@pytest.mark.parametrize(
    "phrase",
    [
        "the directory the server may read, which its instructions name",
        "divide the error by that of the one-step naive forecast (repeat the "
        "previous value) on the training data",
        "never report a value below 1 as beating either",
        "Never copy or move a file of the user into that directory yourself",
        "Do not copy or move it yourself: tell the user, who can copy it there "
        "or restart the server with another `--allow-dir`",
        "State a license only as a response gives it: a `ModelLicenseNotice` "
        "or a `ModelDownloadNotice`",
        "`requirements`, the packages to install for it with the versions the "
        "server runs",
        "Hand the script as it is; if you change anything",
        "An error names the first problem it finds",
        "Do not derive one either: no percentage, difference or ratio that a "
        "response does not give",
        "Do not open the data file with your own tools to look at it",
        "When the user named the column to forecast, pass it as `target` at "
        "once",
        "its error lists the columns of the file, so never guess a target to "
        "see them",
        "When the user gives no horizon",
        "stop and do not run it: tell the user the number of fits and the "
        "cheaper strategies",
        "asking to retrain regularly is not that choice",
        "Report what was measured, never why",
        "The server does not search hyperparameters",
        "Do not do any of it another way in the same answer",
        "Never write those values yourself, nor answer with a `test_size` "
        "evaluation instead",
        "nor as the forecast of the future: its dates are already in the data",
    ],
    ids=lambda phrase: phrase[:40],
)
def test_skill_md_states_the_rules_agents_broke_in_the_agent_check(phrase):
    """
    Test that SKILL.md keeps the rules added after the sessions of the MCP
    agent check: where the allowed directory is named, what MASE is scaled
    by, that the agent never copies a file of the user into the allowed
    directory, that a license is quoted from a response, what `get_code`
    says to install and that an error names one problem of a file.
    """
    skill = _flat(SKILL_PATH.read_text(encoding="utf-8"))

    assert phrase in skill
