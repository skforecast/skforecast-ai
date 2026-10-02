# Unit test build_notices

import logging
import warnings
from skforecast.exceptions import LongTrainingWarning, MissingValuesWarning

from skforecast_ai.exceptions import CandidateFailedWarning, UnrecommendedForecasterWarning
from skforecast_ai.mcp._runtime import build_notices
from skforecast_ai.mcp.models import ToolNotice


def _records(*pairs):
    """
    Emit the warnings `(category, text)` and return their records.
    """
    with warnings.catch_warnings(record=True) as records:
        warnings.simplefilter("always")
        for category, text in pairs:
            warnings.warn(text, category)

    return records


def test_build_notices_output_deduplicated_with_sources():
    """
    Test that warnings are deduplicated by category and text with a count,
    that a text of `plan.warnings` has source 'plan', a text of the profiling
    'data' and any other the default source, and that the suggestion of
    skforecast on how to silence a warning is removed.
    """
    records = _records(
        (UnrecommendedForecasterWarning, "Not recommended."),
        (UserWarning, "Dates skipped."),
        (MissingValuesWarning, "Missing values."),
        (MissingValuesWarning, "Missing values."),
        (UserWarning, "Not recommended."),
    )

    notices, omitted = build_notices(
        records,
        plan_warnings = ["Not recommended."],
        data_warnings = ["Dates skipped."],
    )

    assert notices == [
        ToolNotice(source="plan", category="UnrecommendedForecasterWarning",
                   message="Not recommended.", count=1),
        ToolNotice(source="data", category="UserWarning",
                   message="Dates skipped.", count=1),
        ToolNotice(source="runtime", category="MissingValuesWarning",
                   message="Missing values.", count=2),
        ToolNotice(source="plan", category="UserWarning",
                   message="Not recommended.", count=1),
    ]
    assert omitted == 0


def test_build_notices_leaves_out_candidate_failures_and_logs_deprecations(caplog):
    """
    Test that `CandidateFailedWarning` is left out (the failures are in the
    result) and that deprecation warnings go to the log of the server.
    """
    records = _records(
        (CandidateFailedWarning, "Candidate 'a' failed."),
        (DeprecationWarning, "Old API."),
        (PendingDeprecationWarning, "Soon old."),
        (LongTrainingWarning, "Long."),
    )

    with caplog.at_level(logging.INFO, logger="skforecast_ai.mcp"):
        notices, omitted = build_notices(records)

    assert notices == [
        ToolNotice(source="runtime", category="LongTrainingWarning",
                   message="Long.", count=1),
    ]
    assert omitted == 0
    assert [r.getMessage() for r in caplog.records] == [
        "DeprecationWarning: Old API.", "PendingDeprecationWarning: Soon old.",
    ]


def test_build_notices_limits_count_and_length():
    """
    Test that at most 20 distinct warnings are kept, with the number left
    out, and that a message is cut to 1,000 characters.
    """
    records = _records(
        *[(UserWarning, f"Warning {i}.") for i in range(25)],
        (UserWarning, "x" * 1_003),
    )

    notices, omitted = build_notices(records, default_source="data")

    assert [notice.message for notice in notices] == [f"Warning {i}." for i in range(20)]
    assert all(notice.source == "data" for notice in notices)
    assert omitted == 6

    notices, _ = build_notices(_records((UserWarning, "x" * 1_003)))
    assert notices[0].message == "x" * 1_000 + " ... (3 more characters)"


def test_build_notices_removes_skforecast_suppress_suggestion():
    """
    Test that the line skforecast appends to its warnings on how to silence
    them is removed.
    """
    records = _records((MissingValuesWarning, "NaN found."))

    notices, _ = build_notices(records)

    assert str(records[0].message) == (
        "NaN found.\nYou can suppress this warning using: "
        "warnings.simplefilter('ignore', category=MissingValuesWarning)"
    )
    assert notices[0].message == "NaN found."
