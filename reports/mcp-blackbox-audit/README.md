# Black-box audit of `skforecast-ai mcp`: reproduction scripts

Scripts and datasets behind `reports/mcp-blackbox-audit.md`. Every script
starts the real server over stdio in a process of its own (the pattern of
`tests/tests_mcp/test_stdio_integration.py`), acting as an MCP client. No
network, no API keys: the datasets are synthetic (pandas and numpy, fixed
seeds).

## Layout

- `_client.py`: shared stdio client (`run`, `call`, `show`, `parameters`).
- `dump_catalog.py`: writes `tool_catalog.json` and `tool_catalog.md`, what a
  client sees of the server (instructions, tool descriptions, input
  schemas). With `skforecast_ai/mcp/skills/skforecast-ai-forecasting/SKILL.md`
  it is the only description of the server the explorers relied on.
- `smoke.py`: profile, plan, create_cv, backtest and forecast on a monthly
  series.
- One directory per axis (`a_happy_path/`, `b_hard_data/`, `c_notices/`,
  `d_limits_security/`, `e_skill_coherence/`, `f_errors/`, and the later
  rounds), with `make_data.py` (writes the small datasets to `data/`), the
  datasets and one `<axis>_<NN>_<slug>.py` per finding.

## Running a script

From the root of the repository, with the package installed
(`pip install -e ".[test,llm]"`):

```bash
python reports/mcp-blackbox-audit/<axis>/<script>.py
```

A reproduction script prints the input it sent, the output it got and the
output expected, ends with a line `REPRODUCED` (exit code 0) when the
finding holds, or `NOT REPRODUCED` (exit code 1) when it does not. Large
inputs (big files, `.gz` that expand) are generated at run time in a
temporary directory and never committed.
