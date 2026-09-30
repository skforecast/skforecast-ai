# Ask the assistant

[Your first forecast](first-forecast.ipynb) ran without an LLM, and every forecast on this page still comes from the same deterministic engine. Connecting a model adds a reasoning layer on top of it, with three jobs:

- **Explain**: `ask()` answers questions about a result, a plan or forecasting in general.
- **Turn your domain knowledge into features**: `refine_plan()` reads a description of your data and proposes lags and window features.
- **Turn a deployment scenario into a backtesting strategy**: `create_cv()` reads how the model will be used and sets up the cross-validation that mimics it.

The LLM never runs the pipeline or changes a number. What it proposes is validated by a Pydantic model before it reaches the plan, and when a proposal is not valid you get the deterministic result and a warning.

The animation follows one series through the whole path: what stays on your machine, what reaches the LLM, how a suggestion of `refine_plan()` is validated before it enters the plan, and how `ask()` explains the result without changing it.

<div class="skf-anim-embed" style="--skf-ratio: 0.5625">
  <iframe src="../animations/deterministic-first.html" title="Animation: deterministic first, LLM second" loading="lazy" allowfullscreen></iframe>
</div>

`ask()` explains whatever you pass as `context`: a forecast, a backtest, a comparison, a plan, or nothing at all for a general question. These are example answers to each kind of question:

<figure class="sk-ask-fig">
--8<-- "ask-window.html"
<figcaption>Example answers on the hourly bike sharing data of the <a href="../index.html">home page</a> animation.</figcaption>
</figure>

---

## Connect a model

Install the LLM extra, make the key of your provider available and pass the model as `provider:model`:

```bash
pip install "skforecast-ai[llm]"
```

=== "OpenAI"

    ```bash
    export OPENAI_API_KEY="sk-..."
    ```

    ```python
    from skforecast_ai import ForecastingAssistant

    assistant = ForecastingAssistant(llm="openai:gpt-5.5")
    ```

=== "Anthropic"

    ```bash
    export ANTHROPIC_API_KEY="sk-ant-..."
    ```

    ```python
    from skforecast_ai import ForecastingAssistant

    assistant = ForecastingAssistant(llm="anthropic:claude-sonnet-5")
    ```

=== "Google"

    ```bash
    export GOOGLE_API_KEY="..."
    ```

    ```python
    from skforecast_ai import ForecastingAssistant

    assistant = ForecastingAssistant(llm="google:gemini-3.8-flash")
    ```

=== "Ollama (local)"

    Nothing leaves your machine: the model runs on a local [Ollama](https://ollama.com) server.

    ```bash
    ollama pull qwen3:8b
    ollama serve
    ```

    ```python
    from skforecast_ai import ForecastingAssistant

    assistant = ForecastingAssistant(llm="ollama:qwen3:8b")
    ```

Amazon Bedrock, Groq and any OpenAI-compatible endpoint are covered in [Configuring the LLM](../user-guides/llm-configuration.md), together with passing the key as `api_key` instead of an environment variable.

Nothing is validated when the assistant is created. `check_llm()` reports how the configuration resolves (provider, credentials, endpoint, installed extras) without calling the model, so a missing key shows up now instead of in the first question. Add `test_call=True` to send a one-line prompt as well.

```python
assistant.check_llm()
```

---

## Ask about your forecast

The code below repeats the evaluation of [Your first forecast](first-forecast.ipynb), keeping the profile and the plan for the next sections, and asks about the result.

```python
import pandas as pd

url = (
    "https://raw.githubusercontent.com/skforecast/skforecast-datasets/"
    "refs/heads/main/data/h2o.csv"
)
data = pd.read_csv(url, sep=",", header=0, names=["y", "date"])

profile = assistant.profile(data=data, target="y", date_column="date")
plan    = assistant.plan(profile=profile, steps=12)
result  = assistant.forecast(data=data, profile=profile, plan=plan, test_size=12)

answer = assistant.ask(
    prompt  = "Is this model good enough? Explain the metrics and the errors.",
    context = result,
)
answer.show_explanation()
```

The other questions of the window above work the same way: pass a backtest or a comparison as `context`, the profile with `plan=plan` to question the plan before running anything, or nothing for a general question. Every answer is grounded in **skills**, curated documents about the skforecast topics the question touches; see [Skills for the LLM](../user-guides/skills.md) to choose them yourself.

!!! warning "What is sent to the model"
    Your dataset never is. The LLM receives a summary of it (frequency, date range, target statistics, missing values, significant lags) and the configuration of the forecaster. A result is the exception: to explain `result`, its predictions and metrics are sent, and a `DataSentToLLMWarning` reminds you of it. Create the assistant with `send_data_to_llm=True` to acknowledge it and silence the warning. [What is sent to the LLM](../user-guides/llm-configuration.md#what-is-sent-to-the-llm) has the full list.

---

## Add your domain knowledge to the plan

You often know things the data alone does not show. `refine_plan()` takes that knowledge in plain words, and the LLM translates it into lags and window features. The deterministic engine then rebuilds the plan with them, so everything else is derived as before.

```python
refined = assistant.refine_plan(
    profile = profile,
    plan    = plan,
    prompt  = (
        "Spending follows a yearly cycle: it peaks in January and drops "
        "sharply in February. The same month of the last two years matters."
    ),
)
refined.llm_refined_fields    # what the LLM changed, for example ['lags']
```

A suggestion is a hypothesis, not an improvement. Evaluate the refined plan on the same test set and keep it only if it is better:

```python
result_refined = assistant.forecast(
                     data      = data,
                     profile   = profile,
                     plan      = refined,
                     test_size = 12,
                 )
pd.concat(
    [result.metrics, result_refined.metrics],
    keys = ["deterministic", "refined"],
)
```

`refined.explanation` records the reasoning of the LLM next to the rules of the engine.

---

## Describe how the model will be deployed

A single test year says little about how the model will behave in production. Backtesting repeats the evaluation over many points in time, and its setup should mimic how the model will be used. Describe that in plain words and `create_cv()` turns it into the parameters of a skforecast `TimeSeriesFold`, validated before the backtest runs:

```python
cv = assistant.create_cv(
    profile = profile,
    plan    = plan,
    prompt  = (
        "Every year we retrain on all the history available and forecast "
        "the next 12 months. Evaluate it over the last four years."
    ),
)
print(cv.explanation)

backtest = assistant.backtest(data=data, cv=cv, profile=profile, plan=plan)
backtest.metrics
```

For this scenario, expect a strategy that refits the model in every fold, moves forward 12 months at a time and starts the first fold four years before the end of the data. Without `prompt`, `create_cv()` picks the strategy by rules, and any parameter can also be set explicitly. The animation shows the same idea on hourly data: how a scenario becomes `TimeSeriesFold` parameters (the horizon always comes from the plan), and how the folds are evaluated.

<div class="skf-anim-embed" style="--skf-ratio: 0.5625">
  <iframe src="../animations/backtesting-scenario.html" title="Animation: validate the way you deploy" loading="lazy" allowfullscreen></iframe>
</div>

---

## Next steps

<div class="grid cards" markdown>

-   **Configuring the LLM**

    ---

    Every provider, credentials, local models, what leaves your machine and what to do when a call fails.

    [:octicons-arrow-right-24: Configuring the LLM](../user-guides/llm-configuration.md)

-   **Step by step**

    ---

    Profile, plan, refine, backtest and compare on an hourly dataset, asking the assistant at each step.

    [:octicons-arrow-right-24: Step by step guide](../user-guides/agentic-forecasting-step-by-step.ipynb)

-   **Skills for the LLM**

    ---

    The skforecast documents that ground every answer, and how to choose them.

    [:octicons-arrow-right-24: Skills for the LLM](../user-guides/skills.md)

-   **Using the CLI**

    ---

    `skforecast-ai ask`, `check-llm` and the rest of the pipeline from the terminal.

    [:octicons-arrow-right-24: Using the CLI](../user-guides/cli-usage.md)

</div>
