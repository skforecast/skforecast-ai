"""
Test session setup shared by every test module.
"""

import os
import time


def pytest_configure(config):
    """
    Run the suite in UTC, as CI and the cloud sessions do. pandas reads a
    time zone name such as 'CET' as the local zone when it matches the
    machine's (with a FutureWarning), so the profiling tests on zone names
    gave other results on a machine set to Central European Time.
    """
    os.environ["TZ"] = "UTC"
    if hasattr(time, "tzset"):
        time.tzset()
    # Typer forces a color terminal when `GITHUB_ACTIONS` is set, so the
    # usage errors of the CLI came with escape codes in CI only and the
    # tests that read their text failed there. Read when typer is imported,
    # and inherited by the subprocesses that run the CLI.
    os.environ["_TYPER_FORCE_DISABLE_TERMINAL"] = "1"
