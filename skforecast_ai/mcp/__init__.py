"""
MCP server of skforecast-ai: the deterministic workflow as tools for agents.

Needs the `mcp` extra (`pip install "skforecast-ai[mcp]"`). Importing
`skforecast_ai` never imports this subpackage, so the core works without it.
Run it with the `skforecast-ai mcp` command, or build it with
`create_server()`.
"""

from .models import (
    CodeResult,
    FailureResult,
    ObjectInfo,
    ObjectList,
    ToolNotice,
    ToolResult,
)
from .server import create_server, run_server

__all__ = [
    "CodeResult",
    "FailureResult",
    "ObjectInfo",
    "ObjectList",
    "ToolNotice",
    "ToolResult",
    "create_server",
    "run_server",
]
