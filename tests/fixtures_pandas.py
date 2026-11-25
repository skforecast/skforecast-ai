# Fixtures for what the tests quote from pandas and changes with its version

import pandas as pd

# pandas 3 names what pandas 2 does otherwise, and words its errors otherwise.
PANDAS_3 = int(pd.__version__.split(".")[0]) >= 3

# Quarters that start in January, April, July and October: pandas 2 infers
# them as 'QS-OCT' and pandas 3 as 'QS-JAN', two names of the same dates.
QUARTER_START = "QS-JAN" if PANDAS_3 else "QS-OCT"


def at_position(position: int) -> str:
    """
    Return the end of an error of `pandas.to_datetime` about one date:
    pandas 2 says where the date is (', at position 1'), pandas 3 does not.
    """
    return "" if PANDAS_3 else f", at position {position}"
