# Installation Guide

This guide will help you install `skforecast-ai`, an AI-powered forecasting assistant built on top of [skforecast](https://skforecast.org). The default installation of `skforecast-ai` includes only the essential dependencies required for basic functionality. Additional optional dependencies can be installed for extended features such as LLM-based assistance.

![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue) [![PyPI](https://img.shields.io/pypi/v/skforecast-ai)](https://pypi.org/project/skforecast-ai)


## **Basic installation**

**Skforecast-ai** requires Python 3.10 or higher. It is available on PyPI and can be installed using `pip`.

To install the basic version of `skforecast-ai` with its core dependencies, run:

```bash
pip install skforecast-ai
```

Specific version:

```bash
pip install skforecast-ai==0.3.1
```

Latest (unstable):

```bash
pip install git+https://github.com/skforecast/skforecast-ai@main
```

The following dependencies are installed with the default installation:

+ pydantic>=2.10
+ pandas>=2.1
+ skforecast>=0.25
+ typer>=0.22
+ rich>=13.9
+ tomli>=2.0 (only for Python < 3.11)
+ typing-extensions>=4.12 (only for Python < 3.12)
+ statsmodels>=0.13, <0.15


## **Optional dependencies**

The core installation runs the whole deterministic pipeline offline. The extras below only add the LLM reasoning layer (`ask()`, and the LLM-guided variants of `refine_plan()` and `create_cv()`).

### LLM

Installs [pydantic-ai](https://ai.pydantic.dev/), the only LLM abstraction used by `skforecast-ai`. This is enough for most providers: OpenAI, Anthropic, Google, Groq, Ollama, and any OpenAI-compatible endpoint reached through `base_url`.

```bash
pip install "skforecast-ai[llm]"
```

+ pydantic-ai>=2, <3

Credentials are read from the provider's environment variable (for example `OPENAI_API_KEY` or `GOOGLE_API_KEY`) or passed explicitly with `api_key`. See [Configuring the LLM](../user-guides/llm-configuration.md) for the provider strings, the credentials of each provider and local models.

### Bedrock

Amazon Bedrock needs `boto3` on top of the LLM extra, so it has its own extra:

```bash
pip install "skforecast-ai[bedrock]"
```

+ pydantic-ai[bedrock]>=2, <3
+ boto3>=1.34

### All providers

Installs the LLM extra plus every provider-specific dependency (currently Bedrock). `full` is an alias of `all`.

```bash
pip install "skforecast-ai[all]"
```

+ pydantic-ai[bedrock,groq]>=2, <3
+ boto3>=1.34

!!! note "Groq"
    The `groq` extra (`pip install "skforecast-ai[groq]"`) is kept for backwards compatibility. Groq support is already included in the `llm` extra.
