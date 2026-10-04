# perf

Scripts that check a performance or cleanup change: the parity script shows
that every result stays the same, and the timing script shows where the time
goes. They download the skforecast datasets once into
`~/.cache/skforecast_ai_perf` (change it with `--data-dir`) and read them from
there afterwards.

| Script | Purpose |
|:-------|:--------|
| `parity.py` | Dumps profile, plan, scripts, CV, predictions, metrics and Python warnings of the public calls on eight datasets, and compares two dumps. |
| `timing.py` | Times every public call and every MCP tool (stdio, with the start of the server) on small, medium and large data; splits the time by package with cProfile; `-X importtime`; peak memory of `profile()`. |
| `_datasets.py` | The datasets both scripts use. |
| `results/` | Timing outputs of phase 6 (`baseline_*` before any change, `final_*` after the last one), summarized in section 20 of `dev/mcp-preparation.md`. |

```bash
python tools/perf/parity.py dump before.json        # a few minutes
python tools/perf/parity.py dump after.json
python tools/perf/parity.py compare before.json after.json

python tools/perf/timing.py api api.json --sizes small,medium
python tools/perf/timing.py api api.json --sizes large --calls profile,plan --repeats 5
python tools/perf/timing.py mcp mcp.json --sizes small
python tools/perf/timing.py imports imports.json
python tools/perf/timing.py memory memory.json
python tools/perf/timing.py report api.json mcp.json imports.json memory.json
```

Compare timings only between runs on the same machine, with nothing else
running. The cProfile split adds the self time of every function by
package, read from the directory it is installed in (`skforecast_ai`, `skforecast`, `pandas`,
`numpy`, the estimator, `pydantic`, `builtins` for C functions, `other` for
the rest); profiling slows Python code down, so the share of own code is an
upper bound, and the profiled run is one more run of each call. The `.prof`
files go to the folder `<output>_prof` next to the output, for
`python -m pstats` or `snakeviz`. A parity dump records the revision
(`git describe --dirty`), which `compare` leaves out.
