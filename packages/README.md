# Packages

Packages published to PyPI from this repository besides `skforecast-ai`
itself. They are not part of the `skforecast-ai` distribution
(`MANIFEST.in` prunes this folder).

| Path | Purpose |
|:-----|:--------|
| [`skforecast-ai-mcp/`](skforecast-ai-mcp/) | Launcher of the MCP server: depends on `skforecast-ai[mcp]` at the same version and runs `skforecast-ai mcp`. It is the package that `server.json`, the entry of the server in the [MCP registry](https://registry.modelcontextprotocol.io), names: the registry accepts a package, not one of its extras. |

## Versions

`skforecast-ai-mcp`, its pin of `skforecast-ai[mcp]` and the two versions of
`server.json` follow `pyproject.toml`
(`tests/test_mcp_registry_distribution.py`). The `release-bump` skill
updates them.

## Publishing, after `skforecast-ai` is on PyPI

The launcher pins the version of `skforecast-ai`, so that one goes first.

```bash
# 1. The launcher, to PyPI
cd packages/skforecast-ai-mcp
python -m build
python -m twine upload dist/*

# 2. The entry of the registry, from the root of the repository
cd ../..
mcp-publisher validate
mcp-publisher login github
mcp-publisher publish

# 3. Check
curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=skforecast"
```

`mcp-publisher` is installed with `brew install mcp-publisher`. The GitHub
account of the login must be a public member of the `skforecast`
organization: the registry cannot see a private membership and answers 403.

The registry looks for the line `mcp-name: io.github.skforecast/skforecast-ai`
in the README that `skforecast-ai-mcp` publishes to PyPI, so step 2 fails
until step 1 is done. A published version of the entry cannot be changed,
so run `mcp-publisher validate` and read `server.json` once more before
publishing it.
