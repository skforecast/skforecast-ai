# skforecast-ai-mcp

<!-- mcp-name: io.github.skforecast/skforecast-ai -->

The MCP server of [skforecast-ai](https://github.com/skforecast/skforecast-ai): deterministic time series forecasting as tools for coding agents (Claude Code, Cursor, VS Code, Codex, Claude Desktop and other MCP clients).

The agent brings the language model and calls skforecast-ai as tools: profile a CSV file, plan a forecaster, backtest it, compare candidates and forecast. Every decision comes from rule-based code, every result comes with the script that produced it, and responses never carry rows of your data.

## Usage

The server runs over stdio and needs one directory, `--allow-dir`: it only reads CSV files inside it. With [uv](https://docs.astral.sh/uv/):

```bash
uvx skforecast-ai-mcp --allow-dir /absolute/path/to/project
```

As the entry of an MCP client:

```json
{
  "mcpServers": {
    "skforecast-ai": {
      "command": "uvx",
      "args": ["skforecast-ai-mcp", "--allow-dir", "/absolute/path/to/project"]
    }
  }
}
```

The setup of each client, the tools, every option and what the server does with your data are in [MCP server for coding agents](https://ai.skforecast.org/stable/user-guides/mcp-server.html).

## What this package is

A launcher with no logic of its own. It installs `skforecast-ai[mcp]` at the same version and runs `skforecast-ai mcp` with the arguments it receives, so these two commands start the same server:

```bash
uvx skforecast-ai-mcp --allow-dir /absolute/path/to/project
uvx --from "skforecast-ai[mcp]" skforecast-ai mcp --allow-dir /absolute/path/to/project
```

It exists because the [MCP registry](https://registry.modelcontextprotocol.io) names a package, not one of its extras.

## License

Apache-2.0, as skforecast-ai.
