"""Dump what a client sees of the server: instructions, tools, schemas.

Writes tool_catalog.json and tool_catalog.md next to this script. This is the
only description of the server the explorers were allowed to rely on, with
the SKILL.md.
"""

import json
import sys
import tempfile
from pathlib import Path

import anyio
from mcp import Client

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _client import parameters  # noqa: E402


async def go():
    d = tempfile.mkdtemp(prefix="mcp-audit-allow-")
    async with Client(parameters(allow_dir=d)) as c:
        tools = await c.list_tools()
        tools = tools.tools if hasattr(tools, "tools") else tools
        out = {
            "server_info": c.server_info.model_dump(exclude_none=True) if c.server_info else None,
            "instructions": c.instructions,
            "tools": [t.model_dump(exclude_none=True) for t in tools],
        }
    (HERE / "tool_catalog.json").write_text(json.dumps(out, indent=1, default=str))
    lines = ["# Tool catalog as seen by a client", "", "## Server instructions", "",
             "```", str(out["instructions"]).replace(d, "<ALLOW_DIR>"), "```", ""]
    for t in out["tools"]:
        lines += [f"## {t['name']}", "", t.get("description", ""), "",
                  "Annotations: " + json.dumps(t.get("annotations")), "",
                  "```json", json.dumps(t["input_schema"], indent=1), "```", ""]
    (HERE / "tool_catalog.md").write_text("\n".join(lines))


anyio.run(go)
