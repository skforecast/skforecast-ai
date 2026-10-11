# Unit test skforecast_ai.__getattr__ and skforecast_ai.__dir__

import importlib
import re
import subprocess
import sys
from pathlib import Path
import pytest

import skforecast_ai

REPO_ROOT = Path(__file__).resolve().parent.parent

# Every public name of the package and the module that defines it.
PUBLIC_NAMES = {
    "ALL_SKILLS": "skforecast_ai.llm.skills",
    "AllCandidatesFailedError": "skforecast_ai.exceptions",
    "AskResult": "skforecast_ai.schemas",
    "BacktestResult": "skforecast_ai.schemas",
    "CandidateFailedWarning": "skforecast_ai.exceptions",
    "CandidateFailure": "skforecast_ai.schemas",
    "CompareProgress": "skforecast_ai.schemas",
    "ComparisonResult": "skforecast_ai.schemas",
    "CVResult": "skforecast_ai.schemas",
    "DataContentError": "skforecast_ai.exceptions",
    "DataNotFoundError": "skforecast_ai.exceptions",
    "DataProfile": "skforecast_ai.schemas",
    "DataSentToLLMWarning": "skforecast_ai.exceptions",
    "ExplainableResult": "skforecast_ai.schemas",
    "ForecastExecutionError": "skforecast_ai.exceptions",
    "ForecastingProfile": "skforecast_ai.schemas",
    "ForecastingAssistant": "skforecast_ai.assistant",
    "ForecastPlan": "skforecast_ai.schemas",
    "InvalidInputError": "skforecast_ai.exceptions",
    "InvalidInputTypeError": "skforecast_ai.exceptions",
    "LLMCheckResult": "skforecast_ai.schemas",
    "LLMContext": "skforecast_ai.schemas",
    "RenderedScript": "skforecast_ai.schemas",
    "CodeGenerationResult": "skforecast_ai.schemas",
    "LLMCallError": "skforecast_ai.exceptions",
    "LLMRequiredError": "skforecast_ai.exceptions",
    "MissingBackendWarning": "skforecast_ai.exceptions",
    "PlanEditsDiscardedWarning": "skforecast_ai.exceptions",
    "PreprocessingStep": "skforecast_ai.schemas",
    "ForecastResult": "skforecast_ai.schemas",
    "SeriesPacf": "skforecast_ai.schemas",
    "SingleRunResult": "skforecast_ai.schemas",
    "SkforecastAIError": "skforecast_ai.exceptions",
    "UnrecommendedForecasterWarning": "skforecast_ai.exceptions",
}


def test_getattr_all_lists_the_public_names():
    """
    Test that `__all__` lists the public names and the version, as before
    the names were imported on first access.
    """
    assert sorted(skforecast_ai.__all__) == sorted([*PUBLIC_NAMES, "__version__"])


@pytest.mark.parametrize("name", sorted(PUBLIC_NAMES))
def test_getattr_returns_the_object_of_the_module_that_defines_it(name):
    """
    Test that every public name, read as an attribute and with
    `from skforecast_ai import ...`, is the object of the module that
    defines it, not a copy.
    """
    expected = getattr(importlib.import_module(PUBLIC_NAMES[name]), name)
    namespace = {}
    exec(f"from skforecast_ai import {name}", namespace)

    assert getattr(skforecast_ai, name) is expected
    assert namespace[name] is expected


def test_getattr_AttributeError_when_the_name_is_not_public():
    """
    Test that an unknown name raises the `AttributeError` of a module, so
    `hasattr` and `getattr` with a default work.
    """
    err_msg = re.escape("module 'skforecast_ai' has no attribute 'not_a_name'")

    with pytest.raises(AttributeError, match=err_msg):
        skforecast_ai.not_a_name

    assert not hasattr(skforecast_ai, "not_a_name")


def test_getattr_imports_the_names_on_first_access_in_a_new_interpreter():
    """
    Test in a fresh interpreter that `import skforecast_ai` loads neither the
    assistant nor pandas, scikit-learn, scipy or skforecast; that `dir()`
    lists every public name before it is imported; that `__version__` is
    there; and that `from skforecast_ai import ForecastingAssistant` and
    `from skforecast_ai import *` give the classes of their modules.
    """
    code = (
        "import sys\n"
        "import skforecast_ai\n"
        "heavy = {'pandas', 'numpy', 'scipy', 'sklearn', 'skforecast'}\n"
        "print(sorted({n.split('.')[0] for n in sys.modules} & heavy))\n"
        "print('skforecast_ai.assistant' in sys.modules)\n"
        "print(set(skforecast_ai.__all__) <= set(dir(skforecast_ai)))\n"
        "print(skforecast_ai.__version__)\n"
        "from skforecast_ai import ForecastingAssistant\n"
        "import skforecast_ai.assistant\n"
        "print(ForecastingAssistant is skforecast_ai.assistant.ForecastingAssistant)\n"
        "namespace = {}\n"
        "exec('from skforecast_ai import *', namespace)\n"
        "print(sorted(set(skforecast_ai.__all__) - set(namespace)))\n"
    )

    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
    )

    assert proc.returncode == 0, proc.stderr[-2000:]
    assert proc.stdout.splitlines() == [
        "[]",
        "False",
        "True",
        skforecast_ai.__version__,
        "True",
        "[]",
    ]
