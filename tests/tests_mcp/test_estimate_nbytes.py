# Unit test estimate_nbytes

import pandas as pd

from skforecast_ai.mcp._store import estimate_nbytes


def test_estimate_nbytes_counts_frames_and_shared_objects_once():
    """
    Test that a DataFrame counts its deep memory and that an object reached
    twice is counted once.
    """
    frame = pd.DataFrame({"a": [1.0, 2.0, 3.0]})
    frame_bytes = int(frame.memory_usage(deep=True).sum())

    assert estimate_nbytes(frame) == frame_bytes
    assert estimate_nbytes([frame, frame]) - estimate_nbytes([frame]) == 8
