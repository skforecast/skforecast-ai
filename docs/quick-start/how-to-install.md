# Installation

**skforecast-ai** needs Python 3.10 or newer and is available on PyPI. The core package runs the whole forecasting pipeline offline, with no API key; the LLM reasoning layer and the foundation model backend are optional extras.

![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue) [![PyPI](https://img.shields.io/pypi/v/skforecast-ai)](https://pypi.org/project/skforecast-ai)

## Install

=== "Core"

    Profiling, planning, forecasting, backtesting, comparison and the CLI. No LLM, no network access at run time.

    ```bash
    pip install skforecast-ai
    ```

=== "With the LLM layer"

    Adds `ask()` and the LLM-guided variants of `refine_plan()` and `create_cv()`. Enough for OpenAI, Anthropic, Google, Groq, Ollama and any OpenAI-compatible endpoint.

    ```bash
    pip install "skforecast-ai[llm]"
    ```

=== "Amazon Bedrock"

    The LLM layer plus the AWS client that Bedrock needs.

    ```bash
    pip install "skforecast-ai[bedrock]"
    ```

=== "Foundation models"

    Adds the backend of Chronos-2, the default model of `ForecasterFoundation`, so it can run in `forecast()`, `backtest()` and `compare()`. Scripts that use it can be generated without it.

    ```bash
    pip install "skforecast-ai[foundation]"
    ```

To install a specific version, pin it (`pip install skforecast-ai==0.4.1`). The development version, which may be unstable, installs from GitHub:

```bash
pip install git+https://github.com/skforecast/skforecast-ai@main
```

To work on the code, see the [Contribution Guide](https://github.com/skforecast/skforecast-ai/blob/main/CONTRIBUTING.md).

## Check the installation

The snippet below downloads a small monthly dataset, evaluates a model on its last 12 months and prints the metrics. It runs in deterministic mode, so it needs no LLM and no configuration.

```python
from skforecast.datasets import load_demo_dataset
from skforecast_ai import ForecastingAssistant

data = load_demo_dataset(verbose=False)
assistant = ForecastingAssistant()
result = assistant.forecast(data=data, target="y", steps=12, test_size=12)
print(result.metrics)
```

If the installation works, it prints one row of metrics:

```
  series       MAE       MSE      MASE      MAPE
0      y  0.078442  0.008933  0.802828  0.088608
```

The command line interface is installed with the package:

```bash
skforecast-ai --version
```

### Check the LLM configuration

With the LLM extra installed, `check-llm` reports how the provider, the model and the credentials resolve, without calling the model. It exits with an error when something is missing, for example the API key:

```bash
export OPENAI_API_KEY="sk-..."
skforecast-ai check-llm --llm openai:gpt-5.5
```

The same check is available in Python as `assistant.check_llm()`. [Configuring the LLM](../user-guides/llm-configuration.md) covers every provider and its credentials.

## Optional dependencies

| Extra | Adds | Use it for |
|:------|:-----|:-----------|
| `llm` | [pydantic-ai](https://ai.pydantic.dev/), the only LLM abstraction the package uses | OpenAI, Anthropic, Google, Groq, Ollama and OpenAI-compatible endpoints |
| `bedrock` | pydantic-ai with its Bedrock support, and `boto3` | Amazon Bedrock |
| `mcp` | [mcp](https://pypi.org/project/mcp/), the Model Context Protocol SDK | The [MCP server for coding agents](../user-guides/mcp-server.md) |
| `all` | Every provider-specific dependency and the `mcp` extra (`full` is an alias) | Several providers in the same environment |
| `foundation` | `chronos-forecasting`, the backend of Chronos-2 | Running `ForecasterFoundation` with its default model |

The core dependencies (skforecast, pandas, pydantic, statsmodels, typer and rich) are listed with their versions on [PyPI](https://pypi.org/project/skforecast-ai/).

Without the `foundation` extra, `compare()` leaves `ForecasterFoundation` out of the automatic candidates with a `MissingBackendWarning`. Other foundation models (TimesFM, Moirai, TabICL, ...) need their own backend; skforecast names the package to install when it is missing.

!!! note "Groq"
    The `groq` extra (`pip install "skforecast-ai[groq]"`) is kept for backwards compatibility. Groq support is already included in the `llm` extra.

## Next steps

<div class="grid cards" markdown>

-   **Your first forecast**

    ---

    From raw data to a validated forecast and the script that produced it, with no LLM.

    [:octicons-arrow-right-24: Your first forecast](first-forecast.ipynb)

-   **Ask the assistant**

    ---

    Connect an LLM to explain results, add domain knowledge to the plan and describe the deployment.

    [:octicons-arrow-right-24: Ask the assistant](ask-the-assistant.md)

</div>
