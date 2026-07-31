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
pip install skforecast-ai==0.2.0
```

Latest (unstable):

```bash
pip install git+https://github.com/skforecast/skforecast-ai@main
```

The following dependencies are installed with the default installation:

+ pydantic>=2.10
+ pandas>=2.1
+ skforecast>=0.23
+ typer>=0.22
+ rich>=13.9
+ tomli>=2.0 (only for Python < 3.11)
+ statsmodels>=0.13, <0.15


## **Optional dependencies**

To install the full version with all optional dependencies:

```bash
pip install skforecast-ai[full]
```

For specific use cases, you can install these dependencies as needed:

### LLM

Enables the LLM-powered forecasting assistant features.

```bash
pip install skforecast-ai[llm]
```

+ pydantic-ai>=2, <3


### Groq

Adds support for Groq models through `pydantic-ai`.

```bash
pip install skforecast-ai[groq]
```

+ pydantic-ai[groq]>=2, <3


### Bedrock

Adds support for Amazon Bedrock models through `pydantic-ai`.

```bash
pip install skforecast-ai[bedrock]
```

+ pydantic-ai[bedrock]>=2, <3
+ boto3>=1.34


### All providers

Installs every supported LLM provider (Groq and Bedrock).

```bash
pip install skforecast-ai[all]
```

+ pydantic-ai[bedrock,groq]>=2, <3
+ boto3>=1.34
