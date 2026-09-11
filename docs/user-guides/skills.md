# Skills: how the LLM is briefed

When you call `ask()`, the LLM does not answer from its own memory of skforecast. Every call includes a set of **skills**: curated documents about a specific forecasting topic (how to choose a forecaster, how to configure backtesting, how prediction intervals work, the exact API of `RollingFeatures`, and so on). They keep the answers grounded in the current skforecast API instead of an older version the model may have seen during training.

Skills are plain Markdown files bundled with the package under `skforecast_ai/skills/`. They are synced from the skforecast repository, so they describe the same version of skforecast the generated scripts run on. The returned `AskResult` records the skills that were sent (`answer.skills`), so an answer is always traceable to the documents it was built from.

!!! note "Skills only apply to `ask()`"
    `refine_plan()` and `create_cv()` use fixed, dedicated skills (feature engineering and lag selection for the first, backtesting configuration for the second). The selection described here is for `ask()`, which is the free-form entry point.

---

## Where the skills come from

The skills are the ones skforecast publishes in its own repository, copied verbatim by `tools/sync_skforecast_assets.py` from the skforecast branch that `pyproject.toml` pins. They are never edited in skforecast-ai, so a skill always describes the skforecast version the generated scripts run on. The upstream [Workflow skills](https://skforecast.org/latest/quick-start/ai-assisted-forecasting.html#workflow-skills) table is the canonical list.

Each skill follows the open [Agent Skills](https://agentskills.io/specification) standard: a directory named after the skill with a `SKILL.md` file whose YAML front matter declares `name` and `description`, a Markdown body with the instructions, and an optional `references/` folder with longer material (API signatures, worked examples). Because the format is standard, any agent that supports it (GitHub Copilot, Claude Code and others) can load the same skills directly from the skforecast repository.

!!! note "How `ask()` departs from the standard"
    In the Agent Skills model the agent reads every `description` and decides on its own which skill to activate, loading the body only when needed. `ask()` does not leave that choice to the model: the skills are selected deterministically from the context and the question (see below), and each selected skill is sent whole, `SKILL.md` and `references/` included, trimmed as a block to the token budget. The trade-off is reproducibility: the documentation the model saw is a function of the inputs and is recorded in `answer.skills`.

---

## Available skills

`skforecast_ai.ALL_SKILLS` lists the valid names, in priority order (the most foundational first). The table below follows the same order and is checked against the package by the test suite, so it cannot drift from the skills actually shipped:

```python
from skforecast_ai import ALL_SKILLS

print(ALL_SKILLS)
```

| Skill | Covers |
|---|---|
| `choosing-a-forecaster` | Decision matrix mapping data characteristics and requirements to a skforecast forecaster class. |
| `autocorrelation-and-lag-selection` | ACF and PACF analysis with `skforecast.stats`, ranking lags by partial autocorrelation, feeding them to `lags`. |
| `feature-engineering` | Calendar features, holiday distances, rolling statistics with `RollingFeatures`, differencing, categorical exogenous variables. |
| `forecasting-single-series` | `ForecasterRecursive` and `ForecasterDirect`: data preparation, training, prediction, backtesting, intervals. |
| `forecasting-multiple-series` | Global models with `ForecasterRecursiveMultiSeries` and `ForecasterDirectMultiVariate`: data formats, encoding, per-series transformers. |
| `foundation-forecasting` | Zero-shot forecasting with pre-trained foundation models (Chronos, TimesFM, Moirai, TabPFN-TS and others) through `ForecasterFoundation`. |
| `baseline-forecasting` | Seasonal-naive and equivalent-date baselines with `ForecasterEquivalentDate`, and how to benchmark a model against them. |
| `metric-selection` | Which metric fits the forecaster type, the prediction output and multi-series aggregation; configuring `metric` in backtesting and search. |
| `backtesting-configuration` | Mapping a deployment scenario (retraining frequency, horizon, data budget) to `TimeSeriesFold` parameters. |
| `hyperparameter-optimization` | Grid, random and Bayesian (Optuna) search for single and multi-series forecasters, search spaces, cross-validation. |
| `feature-selection` | Selecting lags, window features and exogenous variables with `RFECV` and `SelectFromModel`. |
| `prediction-intervals` | Bootstrapping, conformal prediction and statistical intervals; residual management and calibration. |
| `statistical-models` | ARIMA, SARIMAX, ETS and ARAR through `ForecasterStats`, Auto-ARIMA, backtesting statistical models. |
| `deep-learning-forecasting` | RNN, LSTM and GRU models with `ForecasterRnn` and `create_and_compile_model`. |
| `drift-detection` | Monitoring in production with `RangeDriftDetector` and `PopulationDriftDetector`. |
| `troubleshooting-common-errors` | Common skforecast errors and the mistakes LLM-generated code tends to make: deprecated imports, wrong names, data formats. |
| `complete-api-reference` | Full constructor and method signatures of every skforecast forecaster, backtesting and search function, cross-validation class and preprocessing helper. |

---

## Automatic selection

When `skills` is not passed, `ask()` selects them in three steps.

**1. Base skills from the context.** If `context` carries a profile (a `ForecastingProfile` or any result), its `task_type` picks the foundational skills. Without a context, the general `choosing-a-forecaster` skill is used alone.

| `profile.task_type` | Base skills |
|---|---|
| `single_series` | `choosing-a-forecaster`, `forecasting-single-series` |
| `multi_series`, `multivariate` | `choosing-a-forecaster`, `forecasting-multiple-series` |
| `statistical` | `statistical-models` |
| `foundation` | `foundation-forecasting` |
| no context | `choosing-a-forecaster` |

**2. Keyword augmentation from the question.** The prompt is scanned for topic keywords and the matching skills are added:

| Keywords in the prompt (examples) | Skill added |
|---|---|
| interval, quantile, conformal, bootstrap, uncertainty | `prediction-intervals` |
| backtest, cross-validation, fold, refit, gap, evaluate | `backtesting-configuration` |
| hyperparameter, tuning, optuna, grid search, bayesian | `hyperparameter-optimization` |
| lag, autocorrelation, acf, pacf | `autocorrelation-and-lag-selection` |
| rolling feature, window feature, calendar, holiday, differentiation | `feature-engineering` |
| feature selection, rfecv, feature importance | `feature-selection` |
| metric, mae, mape, rmse, mase, pinball, coverage | `metric-selection` |
| lstm, gru, rnn, keras, neural | `deep-learning-forecasting` |
| chronos, timesfm, moirai, foundation, zero-shot | `foundation-forecasting` |
| arima, sarimax, ets, arar, statistical | `statistical-models` |
| drift, monitor, production, distribution shift | `drift-detection` |
| baseline, naive, benchmark, equivalent date | `baseline-forecasting` |
| api, signature, kwargs, "parameters of", "default value" | `complete-api-reference` |
| traceback, debug, exception, fails, TypeError, ValueError | `troubleshooting-common-errors` |

**3. Conflict resolution and budget.** Some skills suppress others whose guidance would be misleading next to them: `foundation-forecasting` removes the lag, feature and interval skills (a foundation model needs none of them), `deep-learning-forecasting` removes the single and multi-series workflow skills, and `statistical-models` removes them together with feature engineering and selection. The remaining skills are sorted by the `ALL_SKILLS` priority and trimmed to a token budget: a fixed ceiling for hosted providers, and for local `ollama:` models also the space left in the context window after the role prompt, the rendered context and the room reserved for the answer. Trimming drops the last (least foundational) skills first.

The final list is stored in the result:

```python
answer = assistant.ask(
    prompt  = "Which metric should I use to compare the intervals?",
    context = result,
)
answer.skills
# ['choosing-a-forecaster', 'forecasting-single-series',
#  'metric-selection', 'prediction-intervals']
```

!!! tip "Logging the selection"
    The selection and any trimming are logged by the `skforecast_ai.llm.skills` logger at `INFO` (trimming) and `DEBUG` (base, augmented and final lists).

---

## Choosing the skills yourself

Pass `skills` to bypass the automatic selection. The list is sent as is, in the order given and without budget trimming, so keep it short for local models:

```python
answer = assistant.ask(
    prompt = "How do I tune the number of lags and the window sizes together?",
    skills = ["hyperparameter-optimization", "feature-engineering"],
)
```

A name that is not in `ALL_SKILLS` is skipped with a warning in the log; it does not raise. Pass `include_reference=True` to append the full skforecast API reference to the prompt on top of the skills. It is large, so use it for questions about exact signatures and defaults.

The CLI exposes the same option as a comma-separated list:

```bash
skforecast-ai ask "How to set up prediction intervals?" \
  --skills "prediction-intervals,hyperparameter-optimization"
```

---

## See also

- [Agentic forecasting](agentic-forecasting.ipynb): `ask()` on a forecast, a backtest and a comparison in the fast path.
- [Agentic forecasting step by step](agentic-forecasting-step-by-step.ipynb): `ask()` at every stage, from the profile to the comparison, plus a free-form question with no context.
- [Using the CLI](cli-usage.md): the `ask` command and its `--skills` option.
- [Workflow skills in skforecast](https://skforecast.org/latest/quick-start/ai-assisted-forecasting.html#workflow-skills): the upstream list the skills are synced from.
- [Agent Skills specification](https://agentskills.io/specification): the format of a `SKILL.md` file.
