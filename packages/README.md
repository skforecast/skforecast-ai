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

Run them from the root of the repository, on the release branch, once
`release-bump` has updated the versions. `python` is the one of the
development environment, which has `build` and `twine`.

```bash
# 0. skforecast-ai X.Y.Z is on PyPI
curl -s https://pypi.org/pypi/skforecast-ai/json | python3 -c "import sys,json; print(json.load(sys.stdin)['info']['version'])"

# 1. Build the launcher, without the files of the previous version
cd packages/skforecast-ai-mcp
rm -rf dist build skforecast_ai_mcp.egg-info
python -m build
python -m twine check dist/*

# 2. The launcher, to PyPI (user __token__, password the token of the project)
python -m twine upload dist/*

# 3. The entry of the registry, from the root of the repository
cd ../..
mcp-publisher validate
mcp-publisher login github
mcp-publisher publish

# 4. Check
curl -s "https://registry.modelcontextprotocol.io/v0.1/servers?search=skforecast"
uvx skforecast-ai-mcp@X.Y.Z --help
```

Step 1 removes `dist/` because twine uploads every file in it, and the
files of a version already on PyPI make the upload fail. Step 2 run from
the root of the repository would upload `skforecast-ai` instead: check the
directory first.

`mcp-publisher` is installed with `brew install mcp-publisher`. The GitHub
account of the login must be a public member of the `skforecast`
organization: the registry cannot see a private membership and answers 403.

The registry looks for the line `mcp-name: io.github.skforecast/skforecast-ai`
in the README that `skforecast-ai-mcp` publishes to PyPI, so step 3 fails
until step 2 is done. A published version of the entry cannot be changed,
so run `mcp-publisher validate` and read `server.json` once more before
publishing it.
