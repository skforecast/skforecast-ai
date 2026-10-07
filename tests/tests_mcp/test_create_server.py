# Unit test create_server

import json
import os
import re
import tempfile
from typing import get_args
import pytest

from skforecast_ai import __version__
from skforecast_ai._constants import FORECASTER_TASK_TYPES, LONG_TRAINING_FITS
from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.mcp import create_server
from skforecast_ai.mcp.models import (
    ESTIMATOR_KWARGS_DESCRIPTION,
    CandidateArgs,
    ForecasterName,
    RefinePlanArgs,
)
from skforecast_ai.mcp.server import FOUNDATION_KWARGS
from skforecast_ai.schemas.plans import CANDIDATE_CONFIG_KEYS, REFINE_PLAN_OVERRIDE_KEYS

from .fixtures_mcp import (
    GOLDEN_SCHEMAS,
    call,
    error_of,
    h2o_server,
    profile_and_plan,
    run_session,
    tool_schemas,
)


def test_create_server_tool_schemas_match_golden(tmp_path):
    """
    Test that the tools, their descriptions, annotations and input and output
    schemas are those of the golden file, so a change of the SDK of MCP or of
    pydantic that changes what agents see is noticed. Every input schema
    rejects unknown arguments. Regenerate the golden with
    `write_golden_schemas` of `fixtures_mcp` only after a deliberate change.
    """
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    schemas = tool_schemas(server)
    golden = json.loads(GOLDEN_SCHEMAS.read_text(encoding="utf-8"))

    assert [tool["name"] for tool in schemas] == [
        "profile",
        "plan",
        "refine_plan",
        "create_cv",
        "backtest",
        "compare",
        "forecast",
        "get_code",
        "get_failure",
        "list_objects",
        "describe_object",
    ]
    assert all(
        tool["input_schema"]["additionalProperties"] is False for tool in schemas
    )
    assert schemas == golden


def test_create_server_name_version_and_instructions(tmp_path):
    """
    Test that the server presents itself as skforecast-ai with the version
    of the package and instructions on the workflow.
    """
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    async def steps(client):
        return client.server_info, client.instructions

    info, instructions = run_session(server, steps)

    assert (info.name, info.version) == ("skforecast-ai", __version__)
    assert instructions.startswith(
        "Deterministic time series forecasting with skforecast."
    )


def test_create_server_instructions_name_the_allowed_dir(tmp_path):
    """
    Test that the instructions of the server name the directory it reads,
    as configured, so an agent given a relative path can build the absolute
    one without searching the file system.
    """
    allowed = tmp_path / "data"
    allowed.mkdir()
    server = create_server(allow_dir=allowed, output_dir=tmp_path / "out")

    async def steps(client):
        return client.instructions

    instructions = " ".join(run_session(server, steps).split())

    assert (
        f"The server reads CSV files only inside '{allowed}' (subdirectories "
        f"included). Tools take absolute paths: a file the user names by a "
        f"relative path or by its name is looked for there, so build the path "
        f"from that directory instead of searching the file system."
    ) in instructions
    assert "{allowed_dir}" not in instructions


def test_create_server_output_dir_created_or_temporary(tmp_path, monkeypatch):
    """
    Test that the output directory is created when it does not exist, that
    without one the server writes to a new temporary directory, and that one
    that cannot be created raises `InvalidInputError`.
    """
    output_dir = tmp_path / "a" / "b"
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp_dir))
    (tmp_path / "file").write_text("")

    create_server(allow_dir=tmp_path, output_dir=output_dir)
    create_server(allow_dir=tmp_path)

    assert output_dir.is_dir()
    assert [name.startswith("skforecast-ai-mcp-") for name in os.listdir(temp_dir)] == [
        True
    ]
    err_msg = re.escape(
        f"The output directory {str(tmp_path / 'file' / 'out')!r} cannot be created"
    )
    with pytest.raises(InvalidInputError, match=err_msg) as excinfo:
        create_server(allow_dir=tmp_path, output_dir=tmp_path / "file" / "out")
    assert excinfo.value.field == "output_dir"


def test_create_server_InvalidInputError_when_output_dir_not_writable(
    tmp_path, monkeypatch
):
    """
    Test that an output directory the server cannot write stops it when it
    is created, instead of failing at the end of every run, and that the
    check leaves no file behind.
    """
    from skforecast_ai.mcp import server as server_module

    output_dir = tmp_path / "out"
    create_server(allow_dir=tmp_path, output_dir=output_dir)

    def read_only(*args, **kwargs):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(server_module.tempfile, "NamedTemporaryFile", read_only)
    err_msg = re.escape(
        f"The output directory {str(output_dir)!r} cannot be written: "
        f"Permission denied."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as excinfo:
        create_server(allow_dir=tmp_path, output_dir=output_dir)

    assert excinfo.value.field == "output_dir"
    assert os.listdir(output_dir) == []


@pytest.mark.parametrize(
    "arguments, message",
    [
        ({"max_objects": 0}, "`max_objects` must be an integer of at least 1, got 0."),
        (
            {"max_memory_mb": True},
            "`max_memory_mb` must be an integer of at least 1, got True.",
        ),
        (
            {"max_objects": 2.5},
            "`max_objects` must be an integer of at least 1, got 2.5.",
        ),
        (
            {"max_file_mb": -1},
            "`max_file_mb` must be an integer of at least 0 (0 for no limit), "
            "got -1.",
        ),
    ],
    ids=lambda dt: f"{dt}",
)
def test_create_server_InvalidInputError_when_limits_invalid(
    tmp_path, arguments, message
):
    """
    Test that the limits of the store must be integers of at least 1, and
    the size of a file an integer of at least 0.
    """
    with pytest.raises(InvalidInputError, match=re.escape(message)):
        create_server(allow_dir=tmp_path, output_dir=tmp_path, **arguments)


def test_create_server_unknown_tool(tmp_path):
    """
    Test that calling a tool the server does not have is an error.
    """
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    result = call(server, "ask", {"question": "Why?"})

    assert result.is_error
    assert result.content[0].text == "Unknown tool: ask"


def test_create_server_argument_models_match_the_core():
    """
    Test that the keys of `refine_plan.overrides` and of a candidate are
    those of the core, that the forecasters of the schema are those the
    core knows, and that the description of `estimator_kwargs` names every
    argument a foundation model takes through the server.
    """
    assert set(RefinePlanArgs.__annotations__) == REFINE_PLAN_OVERRIDE_KEYS
    assert set(CandidateArgs.__annotations__) == CANDIDATE_CONFIG_KEYS
    assert set(get_args(ForecasterName)) == set(FORECASTER_TASK_TYPES)
    assert [k for k in FOUNDATION_KWARGS if k not in ESTIMATOR_KWARGS_DESCRIPTION] == []


def test_create_server_schemas_describe_arguments_for_the_agent(tmp_path):
    """
    Test what the schemas tell the agent: `refine_plan.overrides` and the
    candidates describe each key without the text of a Python docstring,
    `forecaster` lists its valid values, `steps` is at least 1, `interval`
    has two elements, the arguments of `create_cv` give their defaults,
    `skip_folds` lists folds from 1, and `get_failure` is read-only.
    """
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")
    schemas = {tool["name"]: tool for tool in tool_schemas(server)}
    refine = schemas["refine_plan"]["input_schema"]
    compare = schemas["compare"]["input_schema"]
    plan = schemas["plan"]["input_schema"]["properties"]
    create_cv = schemas["create_cv"]["input_schema"]["properties"]

    for schema in (refine, compare):
        text = json.dumps(schema)
        assert "Attributes" not in text
        assert "ForecastingAssistant" not in text
        assert "RefinePlanOverrides" not in text and "CandidateConfig" not in text
        for model in schema["$defs"].values():
            assert all("description" in p for p in model["properties"].values())
    overrides = refine["$defs"]["RefinePlanArgs"]["properties"]
    assert overrides["forecaster"]["enum"] == list(get_args(ForecasterName))
    assert overrides["steps"]["minimum"] == 1
    assert plan["steps"]["minimum"] == 1
    assert plan["interval"]["anyOf"][0]["minItems"] == 2
    assert plan["interval"]["anyOf"][0]["maxItems"] == 2
    assert all(
        "Null for" in create_cv[name]["description"]
        for name in (
            "initial_train_size", "fold_stride", "refit", "fixed_train_size",
            "gap", "skip_folds", "allow_incomplete_fold",
        )
    )
    assert create_cv["skip_folds"]["anyOf"][1]["items"]["minimum"] == 1
    assert "numbered from 0" in create_cv["skip_folds"]["description"]
    assert schemas["get_failure"]["annotations"]["readOnlyHint"] is True


def test_create_server_skip_folds_zero_is_invalid_argument(tmp_path):
    """
    Test that skipping fold 0, which skforecast rejects, is an
    `invalid_argument` of the schema instead of an `internal_error`.
    """
    server, path = h2o_server(tmp_path)
    _, plan_id = profile_and_plan(server, path)

    error = error_of(
        call(server, "create_cv", {"plan_id": plan_id, "skip_folds": [0, 2]}),
        "create_cv",
    )

    assert (error["code"], error["field"]) == ("invalid_argument", "skip_folds")


def test_create_server_instructions_carry_the_rules_that_fail_most(tmp_path):
    """
    Test that the instructions of the server, which reach the agent without
    the skill, carry the scale of trust (with the case without baseline),
    the reference of MASE, the cost threshold, the notices, the interval of
    `compare`, the rules on the data and the files of the user and the ones
    on foundation models and their license.
    """
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    async def steps(client):
        return client.instructions

    instructions = " ".join(run_session(server, steps).split())

    for phrase in (
        "Without a baseline",
        "`mean_absolute_scaled_error`",
        f"Before a run above {LONG_TRAINING_FITS} estimator fits",
        "Read `notices` before reporting",
        "`compare` without `interval` uses the interval of the plan",
        "Never modify the user's data",
        "only with their permission write a corrected copy",
        "Foundation models other than the default",
        "Below 1 it beats the one-step naive forecast (repeat the previous "
        "value) on the training data, which is not a seasonal naive forecast "
        "nor the baseline of `compare`",
        "Never copy a file of the user into that directory yourself",
        "State the license of a model only as a notice or an error gives it",
        "nor derive one: no percentage, ratio or difference that a response "
        "does not give",
        "stop: tell the user the number of fits and the cheaper strategies",
        "run the expensive one only if they choose it",
        "Report what was measured, never why",
        "The server does not search hyperparameters (it compares the "
        "candidates you list), detect anomalies or select features",
        "Say so and stop there: do not do them another way",
    ):
        assert phrase in instructions, phrase
