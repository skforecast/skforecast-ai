# Unit test _coverage_notices

import warnings
from skforecast.exceptions import LongTrainingWarning

from skforecast_ai.exceptions import IntervalCoverageWarning
from skforecast_ai.mcp.models import ToolNotice
from skforecast_ai.mcp.server import _coverage_notices


_ADVICE = (
    " The same holds for a `forecast` of the same plan with this interval: "
    "give the user the coverage measured here (by series when there are "
    "several) and say that the uncertainty is larger than its bounds show."
)


def _records(*pairs):
    """
    Emit the warnings `(category, text)` and return their records.
    """
    with warnings.catch_warnings(record=True) as records:
        warnings.simplefilter("always")
        for category, text in pairs:
            warnings.warn(text, category)

    return records


def test_coverage_notices_output_replaces_the_warning_with_one_notice():
    """
    Test that the `IntervalCoverageWarning` of a call becomes one
    `IntervalCoverageNotice` (source 'runtime') with its text and what to
    say in a forecast of the plan, deduplicated, and that the other warnings
    are kept in order.
    """
    records = _records(
        (LongTrainingWarning, "Long training."),
        (IntervalCoverageWarning, "Covers 50 %."),
        (IntervalCoverageWarning, "Covers 50 %."),
        (UserWarning, "Other."),
    )

    kept, notices = _coverage_notices(records)

    assert kept == [records[0], records[3]]
    assert notices == [
        ToolNotice(
            source   = "runtime",
            category = "IntervalCoverageNotice",
            message  = f"Covers 50 %.{_ADVICE}",
            count    = 1,
        )
    ]


def test_coverage_notices_output_empty_without_the_warning():
    """
    Test that a call without `IntervalCoverageWarning` keeps every warning
    and has no `IntervalCoverageNotice`.
    """
    records = _records((UserWarning, "Other."))

    kept, notices = _coverage_notices(records)

    assert kept == records
    assert notices == []
