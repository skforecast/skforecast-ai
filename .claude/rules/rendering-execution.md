---
paths:
  - "skforecast_ai/rendering/**"
  - "skforecast_ai/execution/**"
  - "tests/tests_rendering/**"
  - "tests/tests_execution/**"
---

# Rendering and execution

- The code you see is the code that ran: `forecast()` and `backtest()`
  execute the script that `forecast_code()` and `backtest_code()` return,
  minus the CSV loading preamble. Never compute something in `execution/`
  that the rendered script does not show.
- Rendering lives in `rendering/` (one module per forecaster family) and only
  turns a plan into source code; execution lives in `execution/`.
- Any change here is checked three ways: byte for byte expected scripts in
  `tests/tests_rendering/`, the scripts executed as real files in
  `tests/test_integration_standalone_script.py`, and
  `tests/test_integration_determinism.py` (same input, same script and
  predictions).
- A change to a generated script is user visible: add a release note with
  `/release-note`.
