# Unit test tool get_failure

from skforecast_ai.mcp import server as server_module

from .fixtures_mcp import (
    COMPARE_CANDIDATES,
    call,
    content_of,
    cv_of,
    error_of,
    h2o_server,
    profile_and_plan,
)


def test_tool_get_failure_unknown_failure_or_wrong_kind(tmp_path):
    """
    Test that a failure id that is not kept is `unknown_id`, and that the id
    of an object that is not a comparison is `invalid_argument`.
    """
    server, path = h2o_server(tmp_path)
    _, plan_id = profile_and_plan(server, path)

    unknown = error_of(
        call(server, "get_failure", {"object_id": "failure-9-abcdef"}), "get_failure"
    )
    wrong = error_of(call(server, "get_failure", {"object_id": plan_id}), "get_failure")

    assert unknown["code"] == "unknown_id"
    assert unknown["message"] == (
        "No failure is kept with the id 'failure-9-abcdef': the server keeps the "
        "last 256, and none from a previous run."
    )
    assert (wrong["code"], wrong["field"]) == ("invalid_argument", "object_id")


def test_tool_get_failure_cut_with_full_text_in_a_file(tmp_path, monkeypatch):
    """
    Test that a failure longer than the limit is cut, with its full text in
    a file of the output directory.
    """
    monkeypatch.setattr(server_module, "MAX_FAILURE_CHARS", 40)
    server, path = h2o_server(tmp_path)
    _, _, cv_id = cv_of(
        server,
        path,
        forecaster="ForecasterRecursive",
        estimator="Ridge",
        estimator_kwargs={"solver": "no-such-solver"},
    )
    failure_id = error_of(call(server, "backtest", {"cv_id": cv_id}), "backtest")[
        "details"
    ]["failure_id"]

    result = content_of(call(server, "get_failure", {"object_id": failure_id}))
    failure_path = tmp_path / "out" / f"{failure_id}-failure.txt"

    assert result["text"] == "Error executing generated forecasting code."[:40]
    assert result["text_truncated"] is True
    assert result["files"] == {"failure": str(failure_path)}
    assert failure_path.read_text(encoding="utf-8").startswith(
        "Error executing generated forecasting code.\n\n  InvalidParameterError:"
    )


def test_tool_get_failure_candidate_with_a_failure_id(tmp_path):
    """
    Test that `candidate` with the id of a failure of one call is
    `invalid_argument` rather than ignored.
    """
    server, path = h2o_server(tmp_path)
    _, _, cv_id = cv_of(
        server,
        path,
        forecaster="ForecasterRecursive",
        estimator="Ridge",
        estimator_kwargs={"solver": "no-such-solver"},
    )
    error = error_of(call(server, "backtest", {"cv_id": cv_id}), "backtest")
    failure_id = error["details"]["failure_id"]

    result = error_of(
        call(server, "get_failure", {"object_id": failure_id, "candidate": "x"}),
        "get_failure",
    )

    assert (result["code"], result["field"]) == ("invalid_argument", "candidate")


def test_tool_get_failure_keeps_the_last_failures(tmp_path):
    """
    Test that only as many failures as objects are kept: an older failure id
    is then `unknown_id`.
    """
    server, path = h2o_server(tmp_path, max_objects=3)
    _, _, cv_id = cv_of(
        server,
        path,
        forecaster="ForecasterRecursive",
        estimator="Ridge",
        estimator_kwargs={"solver": "no-such-solver"},
    )
    ids = [
        error_of(call(server, "backtest", {"cv_id": cv_id}), "backtest")["details"][
            "failure_id"
        ]
        for _ in range(4)
    ]

    first = error_of(call(server, "get_failure", {"object_id": ids[0]}), "get_failure")

    assert first["code"] == "unknown_id"
    assert (
        content_of(call(server, "get_failure", {"object_id": ids[-1]}))["id"] == ids[-1]
    )


def test_tool_get_failure_and_get_code_of_long_candidates(tmp_path, monkeypatch):
    """
    Test that the failure and the script of a candidate longer than the
    limits are cut, with the full text written when the comparison was
    created, in files named by the position of the candidate (in the
    ranking for the scripts, in the order of failure for the failures).
    """
    monkeypatch.setattr(server_module, "MAX_FAILURE_CHARS", 30)
    monkeypatch.setattr(server_module, "MAX_CODE_CHARS", 30)
    server, path = h2o_server(tmp_path)
    _, _, cv_id = cv_of(server, path)
    comparison_id = content_of(
        call(server, "compare", {"cv_id": cv_id, "candidates": COMPARE_CANDIDATES})
    )["id"]

    failure = content_of(
        call(server, "get_failure", {"object_id": comparison_id, "candidate": "bad"})
    )
    code = content_of(
        call(server, "get_code", {"object_id": comparison_id, "candidate": "direct"})
    )
    out = tmp_path / "out"

    assert failure["text"] == "Candidate 'bad' failed: ValueE"
    assert failure["files"] == {"failure": str(out / f"{comparison_id}-failure-0.txt")}
    assert code["code_truncated"] is True
    # 'direct' ranks third, after 'ridge' and the baseline.
    assert code["files"] == {"code": str(out / f"{comparison_id}-candidate-2-code.py")}
    assert (
        (out / f"{comparison_id}-candidate-2-code.py")
        .read_text()
        .startswith(code["code"])
    )
