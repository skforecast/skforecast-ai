"""
Seasonal period that each of the two tables gives for every frequency pandas
infers, to decide whether they can be unified (question 5 of section 18 of
dev/mcp-preparation.md).

- `FREQUENCY_TO_SEASONAL_PERIOD` (`_constants.py`), read through
  `tabulated_seasonal_period`: the `m` of Auto-ARIMA, the rule that leaves
  ForecasterStats out of the candidates, and the period the baseline
  repeats.
- `estimate_seasonality` (`recommendation/autoregressive.py`): the PACF
  horizon of the lags (its last period), the window features (its first
  period), and the baseline when the table has no entry.

The frequencies are those `pd.infer_freq` returns for regular indexes of
every alias, anchored, alone and multiplied by 2, 3, 4, 5, 6, 7, 10, 12, 14,
15, 20 and 30, plus the aliases pandas 2.1 inferred (`M`, `Q-DEC`, `A-DEC`, `H`, `T`, `S`), which pandas 2.2 renamed.

Usage (from the repository root):

    python tools/perf/seasonal_periods.py            # rows that differ
    python tools/perf/seasonal_periods.py --all      # every row
"""

from __future__ import annotations
import argparse
import warnings

import pandas as pd

from skforecast_ai.recommendation.autoregressive import (
    estimate_seasonality,
    tabulated_seasonal_period,
)
from skforecast_ai.recommendation.baseline import select_baseline_seasonal_period

BASES = [
    "s", "min", "h", "D", "B", "W-SUN", "W-MON", "W-WED", "MS", "ME", "SMS",
    "SME", "BMS", "BME", "QS-JAN", "QS-OCT", "QE-DEC", "QE-MAR", "BQS-JAN",
    "BQE-DEC", "YS-JAN", "YS-JUL", "YE-DEC", "YE-JUN", "BYS-JAN", "BYE-DEC",
]
MULTIPLIERS = [1, 2, 3, 4, 5, 6, 7, 10, 12, 14, 15, 20, 30]
LEGACY = [
    "M", "2M", "Q-DEC", "Q-OCT", "QS-OCT", "A-DEC", "AS-JAN", "Y-DEC", "H", "2H",
    "3H", "T", "5T", "10T", "15T", "30T", "S", "BM", "BQ-DEC", "BA-DEC",
]


def inferred_frequencies() -> list[str]:
    """
    Frequencies `pd.infer_freq` returns for the aliases and multipliers.
    """

    found = set()
    for base in BASES:
        for multiplier in MULTIPLIERS:
            alias = f"{multiplier}{base}" if multiplier > 1 else base
            try:
                index = pd.date_range("2023-01-02", periods=40, freq=alias)
            except ValueError:
                continue
            frequency = pd.infer_freq(index)
            if frequency is not None:
                found.add(frequency)
    return sorted(found, key=lambda f: (f.lstrip("0123456789"), len(f), f))


def rows(frequencies: list[str]) -> list[tuple]:
    """
    Period of the table, periods of `estimate_seasonality` and period of
    the baseline, for each frequency.
    """

    result = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for frequency in frequencies:
            tabulated = tabulated_seasonal_period(frequency)
            estimated = estimate_seasonality(frequency)
            baseline = select_baseline_seasonal_period(frequency)
            result.append((frequency, tabulated, estimated, baseline))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--all", action="store_true", help="Print every row.")
    arguments = parser.parse_args()
    table = rows(inferred_frequencies()) + rows(LEGACY)
    print(
        "| Frequency | Table (`m`, baseline) | `estimate_seasonality` "
        "| Baseline | Differ |"
    )
    print("|---|---|---|---|---|")
    differing = 0
    for frequency, tabulated, estimated, baseline in table:
        primary = estimated[0] if estimated else None
        differ = tabulated != primary
        differing += differ
        if differ or arguments.all:
            print(
                f"| `{frequency}` | {tabulated} | {estimated} | {baseline} "
                f"| {'yes' if differ else ''} |"
            )
    print(f"\n{differing} of {len(table)} frequencies differ.")


if __name__ == "__main__":
    main()
