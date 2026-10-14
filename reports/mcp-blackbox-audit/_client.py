"""Shared stdio client for the black-box audit of `skforecast-ai mcp`.

Starts the server in a process of its own, exactly as
tests/tests_mcp/test_stdio_integration.py does, and offers small helpers.
Usage in a repro script:

    from _client import server, call, run
    async def main(c):
        r = await call(c, "profile", {"data_path": p, "target": "y"})
    run(main, allow_dir=d)
"""

import json
import os
import sys
import tempfile
from pathlib import Path

import anyio
from mcp import Client, StdioServerParameters


def parameters(allow_dir=None, output_dir=None, extra_args=(), env=None, cwd=None):
    args = ["-c", "from skforecast_ai.cli import app; app()", "mcp"]
    if allow_dir is not None:
        args += ["--allow-dir", str(allow_dir)]
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="mcp-audit-out-")
    args += ["--output-dir", str(output_dir)]
    args += list(extra_args)
    return StdioServerParameters(
        command=sys.executable,
        args=args,
        env=dict(os.environ if env is None else env),
        cwd=str(cwd or Path(output_dir).parent),
    )


def unpack(result):
    """Return (is_error, payload) where payload is a dict when JSON, else text."""
    texts = [c.text for c in result.content if getattr(c, "type", "") == "text"]
    text = "\n".join(texts)
    if result.is_error:
        body = text.split(": ", 1)[1] if text.startswith("Error executing tool") else text
        try:
            return True, json.loads(body)
        except Exception:
            return True, text
    sc = getattr(result, "structured_content", None)
    if sc:
        return False, sc
    try:
        return False, json.loads(text)
    except Exception:
        return False, text


async def call(client, tool, arguments, **kw):
    return unpack(await client.call_tool(tool, arguments, **kw))


def run(main, **kw):
    async def _go():
        async with Client(parameters(**kw)) as client:
            return await main(client)

    return anyio.run(_go)


def show(label, obj, limit=3000):
    text = obj if isinstance(obj, str) else json.dumps(obj, indent=1, default=str)
    print(f"=== {label} ===")
    print(text[:limit])
