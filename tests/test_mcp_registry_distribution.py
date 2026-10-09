# Unit test of the MCP registry entry and the skforecast-ai-mcp launcher

import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = ROOT / "packages" / "skforecast-ai-mcp"
SERVER_NAME = "io.github.skforecast/skforecast-ai"


def _version(pyproject: Path) -> str:
    """
    Return the version of the package written in a pyproject.toml.
    """
    text = pyproject.read_text(encoding="utf-8")

    return re.search(r'^version = "([^"]+)"$', text, flags=re.MULTILINE).group(1)


def _server_json() -> dict:
    """
    Return the entry of the server in the MCP registry.
    """
    return json.loads((ROOT / "server.json").read_text(encoding="utf-8"))


def _launcher_module():
    """
    Return the module of the launcher, loaded from its file: the package is
    not installed in the environment of the tests.
    """
    spec = importlib.util.spec_from_file_location(
        "skforecast_ai_mcp_under_test",
        LAUNCHER / "skforecast_ai_mcp" / "__init__.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


def test_mcp_registry_versions_match_pyproject():
    """
    Test that the version of the launcher, its pin of `skforecast-ai[mcp]`
    and the versions of the registry entry and of its package are the
    version of pyproject.toml, so an entry never starts another server.
    """
    version = _version(ROOT / "pyproject.toml")
    launcher = (LAUNCHER / "pyproject.toml").read_text(encoding="utf-8")
    server = _server_json()
    dependencies = re.search(
        r"^dependencies = \[\n(.*?)^\]", launcher, flags=re.MULTILINE | re.DOTALL
    ).group(1)

    assert _version(LAUNCHER / "pyproject.toml") == version
    assert dependencies.split() == [f'"skforecast-ai[mcp]=={version}",']
    assert server["version"] == version
    assert [p["version"] for p in server["packages"]] == [version]


def test_mcp_registry_entry_names_the_launcher():
    """
    Test that the registry entry has the name the registry verifies, a
    description within its limit of 100 characters and one PyPI package,
    the launcher, started with uvx over stdio and asking for `--allow-dir`.
    """
    server = _server_json()
    launcher = (LAUNCHER / "pyproject.toml").read_text(encoding="utf-8")

    assert server["name"] == SERVER_NAME
    assert 1 <= len(server["description"]) <= 100
    assert server["repository"] == {
        "url": "https://github.com/skforecast/skforecast-ai",
        "source": "github",
    }
    assert len(server["packages"]) == 1
    package = server["packages"][0]
    assert package["registryType"] == "pypi"
    assert package["identifier"] == "skforecast-ai-mcp"
    assert f'name = "{package["identifier"]}"' in launcher
    assert package["runtimeHint"] == "uvx"
    assert package["transport"] == {"type": "stdio"}
    assert [
        (a["type"], a["name"], a["isRequired"]) for a in package["packageArguments"]
    ] == [("named", "--allow-dir", True)]


def test_mcp_registry_ownership_line_is_in_the_launcher_readme():
    """
    Test that the README the launcher publishes to PyPI has the line the
    registry looks for to verify the owner of the package, alone inside an
    HTML comment, with the name of the entry.
    """
    readme = (LAUNCHER / "README.md").read_text(encoding="utf-8")

    assert f"<!-- mcp-name: {SERVER_NAME} -->" in readme.splitlines()
    assert 'readme = "README.md"' in (LAUNCHER / "pyproject.toml").read_text(
        encoding="utf-8"
    )


def test_mcp_registry_launcher_license_is_a_copy():
    """
    Test that the LICENSE of the launcher is a byte for byte copy of the one
    of the repository.
    """
    assert (LAUNCHER / "LICENSE").read_bytes() == (ROOT / "LICENSE").read_bytes()


def test_mcp_registry_launcher_is_not_in_the_skforecast_ai_distribution():
    """
    Test that MANIFEST.in prunes `packages`, so the source distribution of
    skforecast-ai does not carry the launcher.
    """
    manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")

    assert "prune packages" in manifest.splitlines()


def test_mcp_registry_launcher_main_runs_the_mcp_command(monkeypatch):
    """
    Test that `main()` of the launcher calls the CLI of skforecast-ai with
    `mcp` followed by its own arguments, unchanged.
    """
    module = _launcher_module()
    calls = []
    monkeypatch.setattr(
        module, "app", lambda **kwargs: calls.append(kwargs)
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["skforecast-ai-mcp", "--allow-dir", "/data", "--allow-model", "google/x"],
    )

    module.main()

    assert calls == [
        {
            "args"     : ["mcp", "--allow-dir", "/data", "--allow-model", "google/x"],
            "prog_name": "skforecast-ai",
        }
    ]
