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
mcp-publisher login github --token <token with read:org>
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
account of the login must be an Owner of the `skforecast` organization: the
registry gives the namespace `io.github.skforecast` only to that role, which
it reads with the token of the login (`GET /user/memberships/orgs`, which
needs the `read:org` scope). The login in the browser
(`mcp-publisher login github`, 1.8.1) gave a token without access to the
organizations, and `publish` answered 403 with only
`io.github.<user>/*` allowed, also with a public membership. What works is
a classic personal access token with the `read:org` scope and nothing else
(<https://github.com/settings/tokens/new>), passed with `--token` and
deleted afterwards: the registry receives that token to exchange it.

The registry looks for the line `mcp-name: io.github.skforecast/skforecast-ai`
in the README that `skforecast-ai-mcp` publishes to PyPI, so step 3 fails
until step 2 is done. A published version of the entry cannot be changed,
so run `mcp-publisher validate` and read `server.json` once more before
publishing it.

## The plugin directory of Anthropic, after the steps above

The plugin (`plugin/`) is listed in the plugin directory of Anthropic,
submitted on 2026-10-09 from <https://claude.ai/directory/manage>. The
directory follows `main` and does not need a new submission for a release,
but two settings chosen at the submission leave a step by hand:

- **Auto-publish is off.** A version that passes the checks is not live
  until someone selects **Publish** on the page of the plugin. It is the
  gate of the release: the checks of the directory do not look at PyPI, so
  they pass a `plugin/.mcp.json` that pins a version of `skforecast-ai-mcp`
  that does not exist yet, and that plugin would not start.
- **Scheduled check only**, no GitHub webhook. The directory looks at
  `main` about every 6 hours; **Check for new commits** on the page of the
  plugin does it at once.

So, in every release, once `skforecast-ai` and `skforecast-ai-mcp` are on
PyPI:

```bash
# 5. The command of the plugin starts with the new version
CLAUDE_PROJECT_DIR="$PWD" uvx skforecast-ai-mcp==X.Y.Z --allow-project-dir < /dev/null

# 6. Merge the release branch into main (never before step 2: the
#    marketplace of this repository and the directory serve main)
```

7. Open the plugin from **Submissions** in the portal, select **Check for
   new commits** and wait for the scan of the new commit.
8. A launcher with a pinned package (`Runs a pinned npx or uvx package`) is
   held for a reviewer of Anthropic, possibly in every version. When the
   version passes, select **Publish**. Until then the listing keeps serving
   the previous version.

Both settings can be changed in the **Settings** tab of the plugin.
