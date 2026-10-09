"""
pytest plugin that runs the garbage collector after every test, to find a
socket, a file or an event loop left open.

Python warns about an unclosed resource (`ResourceWarning`) when the object
is collected, which happens at an arbitrary later moment: the warning then
fails whichever test is running (warnings are errors in this suite), a
different one each time. Collecting right after the body of every test
makes the warning fail the test that left the resource open, with the line
that created it when `PYTHONTRACEMALLOC` is set.

Usage (from the repository root):

    PYTHONPATH=tools/perf python -X dev -m pytest -p gc_after_test -n auto
    PYTHONPATH=tools/perf python -X dev -m pytest tests/tests_mcp -p gc_after_test

`PYTHONTRACEMALLOC=10` adds where each resource was created, but it slows
the servers the stdio tests start (some of them then time out after 60 s):
use it on the test that failed.
"""

import gc

import pytest


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item):
    """
    Collect the garbage right after the body of every test, inside its own
    call: collected at the teardown, the warning was reported at the setup
    of the next test.
    """
    try:
        return (yield)
    finally:
        gc.collect()
