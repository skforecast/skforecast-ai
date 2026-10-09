# Unit test _undeclared_distributions

from importlib.metadata import PackagePath

from skforecast_ai.mcp import server as server_module
from skforecast_ai.mcp.server import _distributions, _undeclared_distributions


class _Distribution:
    """
    An installed distribution with the name, the `top_level.txt` and the
    files given.
    """

    def __init__(self, name, top_level, files):
        self.metadata = {"Name": name}
        self._top_level = top_level
        self.files = None if files is None else [PackagePath(file) for file in files]

    def read_text(self, filename):
        return self._top_level if filename == "top_level.txt" else None


_INSTALLED = [
    _Distribution(
        "scikit-learn", None,
        [
            "sklearn/__init__.py",
            "sklearn/linear_model/_base.py",
            "scikit_learn-1.7.2.dist-info/METADATA",
            "../../bin/tool",
        ],
    ),
    _Distribution("six", None, ["six.py", "six-1.17.0.dist-info/RECORD"]),
    _Distribution("skforecast", "skforecast\n", ["skforecast/__init__.py"]),
    _Distribution("no-files", None, None),
]


def test_undeclared_distributions_output_modules_read_from_the_files(monkeypatch):
    """
    Test that the modules of a distribution without `top_level.txt` are read
    from its files (a package directory, a single module), leaving out its
    metadata directory and the paths outside the package, and that a
    distribution that declares its modules or lists no files is left out.
    """
    monkeypatch.setattr(
        server_module.metadata, "distributions", lambda: iter(_INSTALLED)
    )

    result = _undeclared_distributions()

    assert result == {"sklearn": ["scikit-learn"], "six": ["six"]}


def test_distributions_output_adds_the_undeclared_ones_on_python_3_10(monkeypatch):
    """
    Test that on Python 3.10, whose `packages_distributions` reads only
    `top_level.txt`, the modules read from the files are added (`sklearn`
    was returned as the package to install), without replacing a declared
    one.
    """
    monkeypatch.setattr(
        server_module.metadata, "distributions", lambda: iter(_INSTALLED)
    )
    monkeypatch.setattr(
        server_module.metadata, "packages_distributions",
        lambda: {"skforecast": ["skforecast"], "six": ["declared-six"]},
    )
    monkeypatch.setattr(server_module.sys, "version_info", (3, 10, 20))
    _distributions.cache_clear()
    try:
        result = _distributions()
    finally:
        _distributions.cache_clear()

    assert result == {
        "skforecast": ["skforecast"],
        "six": ["declared-six"],
        "sklearn": ["scikit-learn"],
    }
