# Unit test _frequencies_differ

from skforecast_ai.profiling.data_profile import _frequencies_differ


def test_frequencies_differ_output():
    """
    Test the message for series of different frequencies, with the series
    ids as text.
    """
    message = _frequencies_differ("D", "a", "W-SUN", 3)

    assert message == (
        "The series do not share one frequency: 'D' (series 'a'), 'W-SUN' "
        "(series '3'). Every series of long-format data must have the same "
        "frequency; forecast the series of each frequency separately."
    )
