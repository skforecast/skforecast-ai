"""
Seasonal periods that each rule gives for every frequency pandas infers
(question 5 of section 18 of dev/mcp-preparation.md, unified in phase 7).

- `FREQUENCY_TO_SEASONAL_PERIOD` (`_constants.py`), read through
  `tabulated_seasonal_period`: the table.
- `estimate_seasonality` (`recommendation/autoregressive.py`): the PACF
  horizon of the lags (its last period), the lag always included and the
  window features (its first period).
- `arima_seasonal_period`: the `m` of Auto-ARIMA and the rule that leaves
  ForecasterStats out of the candidates (the table, else the first period
  of `estimate_seasonality` when it is a whole cycle of at least 2 steps).
- `select_baseline_seasonal_period`: the period the baseline repeats (the
  table, else the first period of `estimate_seasonality`).

A row differs when the baseline, or an `m` that exists, is not the first
period of `estimate_seasonality`. A missing `m` (no whole cycle) is not a
difference: Auto-ARIMA then fits a non-seasonal model.

The frequencies are those `pd.infer_freq` returns for regular indexes of
every alias, anchored, alone and multiplied by 2, 3, 4, 5, 6, 7, 10, 12, 14,
15, 20 and 30, plus the aliases pandas 2.1 inferred (`M`, `Q-DEC`, `A-DEC`,
`H`, `T`, `S`), which pandas 2.2 renamed.

Usage (from the repository root):

    python tools/perf/seasonal_periods.py            # rows that differ
    python tools/perf/seasonal_periods.py --all      # every row
"""

from __future__ import annotations
import argparse
import warnings

import pandas as pd

from skforecast_ai.recommendation.autoregressive import (
    arima_seasonal_period,
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
    Period of the table, periods of `estimate_seasonality`, `m` of
    Auto-ARIMA and period of the baseline, for each frequency.
    """

    result = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for frequency in frequencies:
            tabulated = tabulated_seasonal_period(frequency)
            estimated = estimate_seasonality(frequency)
            m = arima_seasonal_period(frequency)
            baseline = select_baseline_seasonal_period(frequency)
            result.append((frequency, tabulated, estimated, m, baseline))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--all", action="store_true", help="Print every row.")
    arguments = parser.parse_args()
    table = rows(inferred_frequencies()) + rows(LEGACY)
    print(
        "| Frequency | Table | `estimate_seasonality` | `m` | Baseline "
        "| Differ |"
    )
    print("|---|---|---|---|---|---|")
    differing = 0
    for frequency, tabulated, estimated, m, baseline in table:
        primary = estimated[0] if estimated else None
        baseline_primary = primary if primary is not None else 1
        differ = baseline != baseline_primary or (m is not None and m != primary)
        differing += differ
        if differ or arguments.all:
            print(
                f"| `{frequency}` | {tabulated} | {estimated} | {m} "
                f"| {baseline} | {'yes' if differ else ''} |"
            )
    print(f"\n{differing} of {len(table)} frequencies differ.")


if __name__ == "__main__":
    main()
