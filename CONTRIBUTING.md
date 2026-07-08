# Contributing to skforecast-ai

## How to Contribute

**skforecast-ai** is a community-driven open-source project that relies on contributions from people like you. Every contribution, no matter how big or small, can make a significant impact on the project. Even if you've never contributed to an open-source project before, don't worry! Your help will be appreciated and welcomed with gratitude.

### Ways to Contribute

Primarily, **skforecast-ai** development focuses on improving the deterministic recommendation engine, adding new *Skills* (business rules) for the LLM, or improving the code generation pipelines. However, there are many other ways to contribute:

- Submit a bug report or feature request on [GitHub Issues](https://github.com/skforecast/skforecast-ai/issues).
- Write or improve [unit and integration tests](https://docs.pytest.org/en/latest/).
- Improve the internal heuristics or `SKILL.md` documents.
- Answer questions on our issues or discussions.
- Write a blog post, tweet, or share our project with others.

### Before You Start

To make sure we are aligned, please **open an issue** with a brief description of your proposed contribution. Once you are ready to proceed, you must read and agree to the [**Contributor License Agreement**](./CONTRIBUTOR_LICENSE_AGREEMENT.md).

We are excited to have you involved in this project!

## Testing

To run the test suite, first install the test dependencies:

```bash
$ pip install -e ".[test]"
```

All unit tests can be run at once as follows from the root of the project:

```bash
$ pytest tests/
```

During normal development, it is recommended to run only the desired tests from the test file being written:

```bash
$ pytest tests/test_specific_module.py
```

This will go a long way to ensure that the new code does not affect existing library functionality.

## Documentation and Code Standards

### Typing and Formatting
- **Type Hints:** All new functions and methods must include exhaustive type hints (using Python 3.10+ syntax, e.g., `|` instead of `Union`).
- **Formatting:** We use `ruff` to ensure consistent code styling. Make sure to format your code before submitting a PR.
- **Docstrings:** Docstring documentation must be included in every class and function. `skforecast-ai` follows the numpydoc format. The location of the docstring should be just below the class or function definition.

Example function docstring:

```python
def select_forecaster_and_candidates(
    profile: DataProfile
) -> tuple[str, list[str]]:
    """
    Select the preferred forecaster and ordered compatible candidates.

    Parameters
    ----------
    profile : DataProfile
        Profiled dataset metadata.

    Returns
    -------
    preferred : str
        Name of the recommended forecaster class.
    candidates : list of str
        Ordered list of compatible skforecast forecaster class names.
        The first item matches `preferred`.
    """
```