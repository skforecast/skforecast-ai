# Seasonality in Lag Selection — Evaluation

Review of how `estimate_seasonality` drives the lag and window-feature selection
in `skforecast_ai/recommendation/autoregressive.py`, with a focus on the best
quality-for-effort improvements. Each item is rated by **impact** (forecast
quality / correctness) and **effort** (implementation + test cost), so the
high-ratio fixes are easy to spot.

---

## 1. Where seasonality is used

`estimate_seasonality(frequency) -> list[int]` (in
[data_profile.py](../../skforecast_ai/profiling/data_profile.py)) maps a pandas
frequency string to one or two integer seasonal periods (e.g. `"h" -> [24, 168]`,
`"D" -> [7, 365]`, `"MS" -> [12]`). It is consumed in three places:

| # | Site | Call | Role |
|---|------|------|------|
| 1 | `compute_series_pacf` | `seasonalities[-1]` | Sets `n_lags_cap`, the PACF horizon (how far PACF can "see") |
| 2 | `select_lags` | `seasonalities[0]`, `[1]` | Seasonal enrichment: force primary/secondary seasonal lags into the final set |
| 3 | `select_window_features` | `seasonalities[0]`, `[1]` | Choose short/long rolling-window sizes |

So seasonality influences **the PACF search horizon, the lag set, and the window
features** — it is central to the whole autoregressive recommendation, not a
side detail.

---

## 2. Findings

### 2.1 Anchored frequencies silently return no seasonality — **BUG**

`estimate_seasonality` matches with `freq_upper == key or freq_upper.endswith(key)`.
But `infer_frequency` (which feeds the real pipeline via `pd.infer_freq`) returns
*anchored* offset aliases for exactly the frequencies that carry seasonality:

| Real series | `infer_frequency` returns | `estimate_seasonality` result | Correct |
|-------------|---------------------------|-------------------------------|---------|
| Weekly | `W-SUN` | `[]` (ends with `SUN`, not `W`) | `[52]` |
| Quarterly | `QS-OCT` / `QE-DEC` | `[]` | `[4]` |
| Yearly | `A-DEC` / `YE-DEC` | `[]` | `[1]` |
| Hourly | `h` → `H` | `[24, 168]` | ok |
| Daily | `D` | `[7, 365]` | ok |
| Monthly | `MS` / `ME` | `[12]` | ok |

The unit test
[test_infer_frequency.py](../../tests/tests_profiling/test_infer_frequency.py)
passes `"W"`, `"QS"`, `"QE"` *directly*, so it never exercises the anchored
strings the pipeline actually produces. The bug is invisible in tests but live in
production: weekly / quarterly / yearly series get **no seasonal lags, no seasonal
windows, and a degraded PACF horizon**.

- **Impact: high** (3 common frequencies lose all seasonal signal).
- **Effort: low** (normalize the alias before lookup + add anchored test cases).
- **Ratio: excellent — do this first.**

Fix sketch: strip the anchor suffix before matching, e.g. take the part before
`-` (`"W-SUN" -> "W"`, `"QS-OCT" -> "QS"`, `"A-DEC" -> "A"`).

### 2.2 `n_lags_cap` floor of 50 is frequency-blind — **quality**

```python
n_lags_cap = max(3 * seasonalities[-1], 50) if seasonalities else 50
```

The constant `50` floor produces nonsensical horizons at the two extremes:

| freq | `seasonalities` | `3 × last` | `n_lags_cap` | calendar span |
|------|-----------------|-----------|--------------|---------------|
| min  | `[60, 1440]`    | 4320      | **4320**     | 3 days, very costly PACF |
| H    | `[24, 168]`     | 504       | 504          | 3 weeks |
| D    | `[7, 365]`      | 1095      | 1095         | 3 years |
| W    | `[52]`          | 156       | 156          | 3 years |
| M    | `[12]`          | 36        | **50** (floor) | ~4 years |
| Q    | `[4]`           | 12        | **50** (floor) | 12 years |
| Y    | `[1]`           | 3         | **50** (floor) | 50 years |

Two problems:
- **Coarse frequencies (M/Q/Y):** the `50` floor forces an absurd horizon (50
  yearly lags = 50 years; 50 quarterly = 12 years). PACF on so many lags relative
  to series length is noisy and wasteful.
- **Fine frequencies (min):** no upper ceiling, so PACF runs up to 4320 lags —
  the most expensive case and the one most needing a cap.

Note `n_lags` is later clamped by `min(n_lags_cap, n // 2 - 1)`, so for *short*
series the cap rarely bites; it only matters for **long** series, which is
exactly where minutely cost explodes and coarse-frequency over-reach happens.

Recommended single-line change — replace the constant floor with a compute
ceiling and let seasonality scale the cap:

```python
n_lags_cap = min(3 * seasonalities[-1], 512) if seasonalities else 50
```

#### Does `512` make sense for every frequency?

The ceiling only *binds* at two frequencies; everywhere else `3 × last` is
already below it:

| freq | `3 × last` | after `min(…, 512)` | ceiling binds? | largest season reached by PACF? |
|------|-----------|---------------------|----------------|----------------------------------|
| min  | 4320 (last=1440) | **512** | yes | **no** — 512 < 1440, PACF cannot see the daily cycle |
| H    | 504  | 504 | no  | yes (weekly 168, ~3×) |
| D    | 1095 | **512** | yes | partial — yearly 365 < 512, reached but only ~1.4× |
| W    | 156  | 156 | no  | yes |
| M    | 36   | 36  | no  | yes |
| Q/Y  | 12 / 3 | 12 / 3 | no | yes |

The key reason `512` is still safe is the **seasonal-enrichment backstop** in
`select_lags`: it force-adds the primary and secondary seasonal lags even when
PACF never flagged them (as long as `season <= n // 3`). So `n_lags_cap` does
**not** need to reach the largest period for the seasonal lag itself to survive —
only the PACF-detected *harmonics* beyond the ceiling are lost.

- **Daily:** `512` clips `1095`, but the yearly lag (365) is below 512 and is
  enriched regardless. Nothing important lost.
- **Minutely:** `512` is below the daily period (1440), so PACF is blind to the
  daily structure — but the hourly cycle (60) is captured 8× over, and the daily
  lag (1440) is re-added by enrichment. Only harmonics of the daily cycle are
  lost, not the daily lag.

So `512` is a defensible compute ceiling (PACF cost grows with `n_lags`, and 4320
is the only genuinely expensive case), and it "works for every frequency"
**because enrichment exists**. If native PACF detection of the daily cycle on
minutely data is later wanted (instead of relying on enrichment), raise the
ceiling to `~1500`; the cost is heavier PACF on long minutely series.

- **Impact: medium** (correctness for coarse freqs + bounded cost for fine freqs).
- **Effort: low** (one line + a couple of parametrized cases).
- **Ratio: very good — pair it with 2.1.**

The `else 50` fallback (unknown / no frequency) is reasonable and can stay. The
ceiling rationale (cost bound + enrichment backstop) should be captured in a code
comment so the number does not look arbitrary.

### 2.3 `estimate_seasonality` ignores frequency multipliers — **bug, lower priority**

Already flagged by a `TODO` in data_profile.py. `"15min"`, `"2H"`, `"30T"` map to
the base alias and return the *base* periods unscaled (`"15min" -> [60, 1440]`),
which is wrong — at 15-minute spacing a day is 96 steps, not 1440. Affects every
downstream site (wrong seasonal lags + wrong windows).

- **Impact: medium** (only when multiplier frequencies are used; common in
  energy / IoT data).
- **Effort: medium** (parse the integer multiplier, divide periods, handle
  rounding and sub-period cases).
- **Ratio: good, but second wave** — fix after 2.1/2.2 since those are cheaper
  and hit more cases.

### 2.4 `else 50` magic number duplicated — **minor**

The literal `50` appears twice on one line and as the `if`/`else` branches. Low
risk, but extracting a named constant (e.g. `DEFAULT_PACF_CAP = 50`,
`MAX_PACF_CAP = 512`) documents intent and keeps the two extremes tunable.

- **Impact: low**. **Effort: trivial**. Do it opportunistically while editing 2.2.

### 2.5 Seasonal handling is otherwise sound — **no change**

Sites 2–3 use seasonality defensively and correctly:
- `select_lags` only appends a seasonal lag when `season <= max_lag_allowed`, so
  it never violates the `max(lags) < n // 3` training-data guard.
- `select_window_features` clamps windows to `n_observations * 0.25` and skips
  short series (`< 60`).

These need no rework; they simply inherit whatever `estimate_seasonality` returns,
so **fixing the source (2.1–2.3) propagates the benefit to all of them for free**.

### 2.6 Secondary seasonal lag enrichment removed — **applied**

`select_lags` previously force-added **both** the primary and secondary seasonal
lags. The secondary lag is harmful enough to drop:

- **Data cost.** `window_size = max(lags)`, and skforecast drops the first
  `window_size` rows when building the training matrix (and needs that many
  history points to predict). A forced yearly lag (365) on daily data costs a
  full year of training rows — **50 % of a 2-year series, 33 % of a 3-year
  series** — for a single noisy seasonal point.
- **Redundancy.** ML forecasters capture annual seasonality far more cheaply via
  calendar exog (`month`, `dayofyear`, `week`), which encode the whole cycle in
  one column.

The primary lag stays force-added (cheap: D=7, H=24, min=60). The secondary lag
is now left to **PACF** (the `n_lags_cap` horizon already reaches it, so a genuine
signal is still detected) and to **calendar features**. A weak/absent annual
signal is correctly dropped instead of forced.

`n_lags_cap` keeps the `3 * seasonalities[-1]` scaling so PACF can still *see* the
secondary period when it is real.

**Open follow-up (TODO in `select_window_features`):** the long rolling window
also defaults to the secondary period (e.g. a 365-day mean) and carries the same
history cost. A long rolling *mean* is a more defensible slow-trend smoother (and
is clamped to `n * 0.25`), so it is left in place pending review.

---

## 3. Prioritized plan (quality / effort)

| Priority | Item | Impact | Effort | Why first |
|----------|------|--------|--------|-----------|
| 1 | 2.1 Anchored-frequency match | High | Low | Restores seasonality for W/Q/Y; pure correctness; cheap |
| 2 | 2.2 `n_lags_cap` ceiling vs. floor | Medium | Low | Removes absurd horizons + bounds minutely cost; one line |
| 3 | 2.4 Named constants | Low | Trivial | Bundle into the 2.2 edit |
| 4 | 2.3 Multiplier scaling | Medium | Medium | Real bug but narrower; more code + tests |

**Best ratio:** ship 1 + 2 (+ 3) together — small, well-tested, and they fix the
two issues that currently degrade real forecasts the most. Defer 4 to a follow-up.

### Test gaps to close alongside the fixes

- Add anchored aliases (`"W-SUN"`, `"QS-OCT"`, `"QE-DEC"`, `"A-DEC"`,
  `"YE-DEC"`) to `test_estimate_seasonality_output` — this is what proves 2.1 and
  guards against regression.
- Add a `compute_series_pacf` test asserting `n_lags_cap` behavior at both
  extremes (minutely ceiling, yearly no-floor) for 2.2.
- Add multiplier cases (`"15min"`, `"2H"`) when 2.3 lands.
