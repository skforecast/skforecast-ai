# Unit test of the Claude Code plugin and its marketplace

import json
import re
import struct
from pathlib import Path

from skforecast_ai import __version__

ROOT = Path(__file__).resolve().parent.parent
PACKAGE_SKILL = (
    ROOT / "skforecast_ai" / "mcp" / "skills" / "skforecast-ai-forecasting" / "SKILL.md"
)
PLUGIN = ROOT / "plugin"


def _pyproject_version() -> str:
    """
    Return the version of the package written in pyproject.toml.
    """
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    return re.search(r'^version = "([^"]+)"$', text, flags=re.MULTILINE).group(1)


def _json(path: Path) -> dict:
    """
    Return the content of a JSON file.
    """
    return json.loads(path.read_text(encoding="utf-8"))


def test_plugin_skill_is_a_copy_of_the_package_skill():
    """
    Test that the SKILL.md of the plugin is a byte for byte copy of the one
    in the package, which is the source. After changing the package one,
    copy it: `cp skforecast_ai/mcp/skills/skforecast-ai-forecasting/SKILL.md
    plugin/skills/skforecast-ai-forecasting/SKILL.md`.
    """
    copy = PLUGIN / "skills" / "skforecast-ai-forecasting" / "SKILL.md"

    assert copy.read_bytes() == PACKAGE_SKILL.read_bytes()


def test_plugin_versions_match_pyproject():
    """
    Test that `skforecast_ai.__version__`, the versions of plugin.json, of
    the marketplace and of its plugin entry, and the pin of the package in
    .mcp.json are the version of pyproject.toml, so a release never
    installs another server.
    """
    version = _pyproject_version()
    plugin = _json(PLUGIN / ".claude-plugin" / "plugin.json")
    marketplace = _json(ROOT / ".claude-plugin" / "marketplace.json")
    mcp = _json(PLUGIN / ".mcp.json")
    args = mcp["mcpServers"]["skforecast-ai"]["args"]

    assert __version__ == version
    assert plugin["version"] == version
    assert marketplace["metadata"]["version"] == version
    assert [p["version"] for p in marketplace["plugins"]] == [version]
    assert args[0] == f"skforecast-ai-mcp=={version}"


def test_plugin_marketplace_and_server_command():
    """
    Test that the marketplace serves one plugin, named as the package, from
    `./plugin`, and that the server starts with uvx, through the launcher,
    reading the project the agent works in. The command carries no path:
    the plugin directory of Anthropic rejects one written with a variable
    other than `${CLAUDE_PLUGIN_ROOT}`.
    """
    marketplace = _json(ROOT / ".claude-plugin" / "marketplace.json")
    plugin = _json(PLUGIN / ".claude-plugin" / "plugin.json")
    server = _json(PLUGIN / ".mcp.json")["mcpServers"]

    assert marketplace["name"] == "skforecast-ai"
    assert [(p["name"], p["source"]) for p in marketplace["plugins"]] == [
        ("skforecast-ai", "./plugin")
    ]
    assert plugin["name"] == "skforecast-ai"
    assert plugin["license"] == "Apache-2.0"
    assert list(server) == ["skforecast-ai"]
    assert server["skforecast-ai"]["command"] == "uvx"
    assert server["skforecast-ai"]["args"][1:] == ["--allow-project-dir"]


def test_plugin_readme_meets_the_directory_requirements():
    """
    Test that the plugin folder has a README with at least 40 words outside
    code blocks, which the plugin directory of Anthropic requires and shows
    as the description of the listing, and that it shows the command the
    plugin runs.
    """
    readme = (PLUGIN / "README.md").read_text(encoding="utf-8")
    prose = re.sub(r"```.*?```", "", readme, flags=re.DOTALL)

    assert len(prose.split()) >= 40
    assert "uvx skforecast-ai-mcp==<version> --allow-project-dir" in readme


def test_plugin_icon_meets_the_directory_requirements():
    """
    Test that the icon of the plugin is where the plugin directory of
    Anthropic looks for it and is what it accepts: a square PNG of 512 to
    2048 pixels on each side, under 2 MB.
    """
    icon = (PLUGIN / ".claude-plugin" / "icon.png").read_bytes()
    width, height = struct.unpack(">II", icon[16:24])

    assert icon[:8] == b"\x89PNG\r\n\x1a\n"
    assert width == height
    assert 512 <= width <= 2048
    assert len(icon) < 2 * 1024 * 1024
