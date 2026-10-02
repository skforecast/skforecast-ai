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
