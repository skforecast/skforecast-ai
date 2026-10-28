# Unit test _requirements

from importlib.metadata import version

from skforecast_ai.mcp.server import _requirements

CODE = """\
import os
import pandas as pd
from pathlib import Path
from sklearn.linear_model import Ridge
from skforecast.recursive import ForecasterRecursive
from skforecast.model_selection import TimeSeriesFold
from not_installed_package.sub import thing
"""


def test_requirements_packages_of_the_imports_with_their_versions():
    """
    Test that the requirements of a script are the packages of the modules
    it imports (`sklearn` is `scikit-learn`), once each and sorted, with the
    version installed, leaving out the standard library; a module that no
    installed package provides is named as it is imported.
    """
    requirements = _requirements(CODE, None)

    assert requirements == [
        "not_installed_package",
        f"pandas=={version('pandas')}",
        f"scikit-learn=={version('scikit-learn')}",
        f"skforecast=={version('skforecast')}",
    ]


def test_requirements_backend_of_the_foundation_model():
    """
    Test that the backend package of a foundation model, which the script
    does not import, is the last requirement of a script that loads the
    model, and that a model skforecast does not serve adds none.
    """
    code = (
        "import pandas as pd\n"
        "from skforecast.foundation import FoundationModel, ForecasterFoundation\n"
    )

    chronos = _requirements(code, "autogluon/chronos-2-small")
    unknown = _requirements(code, "unknown/model")

    assert chronos[0] == f"pandas=={version('pandas')}"
    assert [name.split("==")[0] for name in chronos] == [
        "pandas",
        "skforecast",
        "chronos-forecasting",
    ]
    assert [name.split("==")[0] for name in unknown] == ["pandas", "skforecast"]


def test_requirements_no_backend_when_the_script_loads_no_model():
    """
    Test that the script of a cross-validation strategy, which builds the
    folds and loads no model, does not list the backend of the foundation
    model of its plan.
    """
    code = (
        "from skforecast.model_selection import TimeSeriesFold\n"
        "cv = TimeSeriesFold(steps=12, initial_train_size=100)\n"
    )

    requirements = _requirements(code, "autogluon/chronos-2-small")

    assert requirements == [f"skforecast=={version('skforecast')}"]
