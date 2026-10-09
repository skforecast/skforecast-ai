"""
Launcher of the MCP server of skforecast-ai.

The MCP registry names a package, not one of its extras, so this package
exists to depend on `skforecast-ai[mcp]` and to run `skforecast-ai mcp`.
"""

import sys

from skforecast_ai.cli import app


def main() -> None:
    """
    Start the MCP server of skforecast-ai, as `skforecast-ai mcp` does.

    It has no options of its own: every argument goes to `skforecast-ai mcp`.

    Returns
    -------
    None
    """
    app(args=["mcp", *sys.argv[1:]], prog_name="skforecast-ai")
