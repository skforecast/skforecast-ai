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

## A release, step by step

`.github/workflows/publish-pypi.yml` publishes `skforecast-ai` and
`skforecast-ai-mcp` to PyPI with Trusted Publishing (no token), since
0.4.2. The other steps are done by hand, in this order:

1. Run `release-bump` and merge everything into the release branch
   `X.Y.x`, with the release notes of the version closed.
2. Open the pull request `X.Y.x` to `main` and wait for the tests and the
   coverage to pass. Do not merge it yet: the marketplace of this
   repository and the plugin directory serve `main`, and
   `plugin/.mcp.json` pins a version of `skforecast-ai-mcp` that is not on
   PyPI.
3. Create the GitHub release `vX.Y.Z` and publish it. The **Target** is
   the release branch, not `main`, which the form offers by default. The
   workflow starts by itself; approve the two deployments in its run
   (**Review deployments**), first `skforecast-ai` and then
   `skforecast-ai-mcp`.
4. Publish the entry of the MCP registry (see below) and check that the
   command of the plugin starts with the new version.
5. Merge the pull request into `main`.
6. Select **Publish** for the new version in the plugin directory of
   Anthropic (see below).

## The publishing workflow

It builds both packages, runs `twine check --strict`, installs the two
wheels in a clean environment to run them, uploads `skforecast-ai` and
then the launcher, which pins its exact version, and installs the launcher
back from the index. It does not run the test suite: the tests are the
ones of step 2.

| Trigger | Index | GitHub environment |
|:--------|:------|:-------------------|
| A published GitHub release, tag `vX.Y.Z` | PyPI | `pypi` |
| A tag `test-publish-*`, or a manual run | TestPyPI | `testpypi` |

A draft of a release starts nothing; a pre-release does. The build fails,
before any upload, when the tag is not `v` plus the version of
`pyproject.toml`: delete the release and the tag, fix it and create them
again. When an upload fails, **Re-run failed jobs** in the same run
repeats it without a new release.

Setup, done once per index (<https://pypi.org> and <https://test.pypi.org>
are separate accounts): each of the two projects has, in **Settings**,
**Publishing**, a GitHub publisher with owner `skforecast`, repository
`skforecast-ai`, workflow `publish-pypi.yml` and the environment of the
table. Only an Owner of the project can add it, and both projects need it:
with one alone, the other upload answers 403, `OIDC scoped token is not
valid for project`. A project that the index does not have yet takes a
pending publisher, from **Publishing** in the settings of the account. In
GitHub, the environment `pypi` has the two maintainers as required
reviewers (the approval of one is enough) and deploys only from tags
`v*`; `testpypi` has no rules.

A rehearsal on TestPyPI, from any branch that has the workflow (the manual
run needs the workflow on `main`):

```bash
git tag test-publish-X.Y.Z-1
git push origin test-publish-X.Y.Z-1
# afterwards
git push origin --delete test-publish-X.Y.Z-1
git tag -d test-publish-X.Y.Z-1
```

An index never takes the same file twice. A rehearsal skips the files
that TestPyPI already has, so a second one with the same version checks
the build and the login but uploads nothing new.

## The entry of the MCP registry (step 4)

From the root of the repository, on the release branch, once
`skforecast-ai-mcp` X.Y.Z is on PyPI:

```bash
mcp-publisher validate
mcp-publisher login github --token <token with read:org>
mcp-publisher publish

# Check: the new version is the one with "isLatest": true
curl -s "https://registry.modelcontextprotocol.io/v0.1/servers?search=skforecast"

# The command of the plugin starts with the new version
CLAUDE_PROJECT_DIR="$PWD" uvx skforecast-ai-mcp==X.Y.Z --allow-project-dir < /dev/null
```

`mcp-publisher` is installed with `brew install mcp-publisher`. The GitHub
account of the login must be an Owner of the `skforecast` organization: the
registry gives the namespace `io.github.skforecast` only to that role, which
it reads with the token of the login (`GET /user/memberships/orgs`, which
needs the `read:org` scope). The login in the browser
(`mcp-publisher login github`, 1.8.1) gave a token without access to the
organizations, and `publish` answered 403 with only
`io.github.<user>/*` allowed, also with a public membership. What works is
a classic personal access token with the `read:org` scope and nothing else
(<https://github.com/settings/tokens/new>), passed with `--token`. The
registry receives that token to exchange it, so delete it afterwards or
give it an expiration date. To keep it between releases out of any file,
the Keychain of macOS holds it:

```bash
# Once; it asks for the token without showing it
security add-generic-password -a "$USER" -s mcp-publisher-github -w

mcp-publisher login github --token "$(security find-generic-password -a "$USER" -s mcp-publisher-github -w)"
```

The registry looks for the line `mcp-name: io.github.skforecast/skforecast-ai`
in the README that `skforecast-ai-mcp` publishes to PyPI, so `publish`
fails until the launcher is there. A published version of the entry cannot
be changed, so run `mcp-publisher validate` and read `server.json` once
more before publishing it.

## The plugin directory of Anthropic (step 6)

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

So, in every release, once the release branch is merged into `main`:

1. Open the plugin from **Submissions** in the portal, select **Check for
   new commits** and wait for the scan of the new commit.
2. A launcher with a pinned package (`Runs a pinned npx or uvx package`) is
   held for a reviewer of Anthropic, possibly in every version. When the
   version passes, select **Publish**. Until then the listing keeps serving
   the previous version.

Both settings can be changed in the **Settings** tab of the plugin.

## Publishing to PyPI by hand

Only when the workflow cannot be used. It needs a token of each project
and `build` and `twine` in the environment. `skforecast-ai` goes first:
the launcher pins its version.

```bash
# skforecast-ai, from the root of the repository
rm -rf dist build skforecast_ai.egg-info
python -m build
python -m twine check --strict dist/*
python -m twine upload dist/*

# The launcher (user __token__, password the token of the project)
cd packages/skforecast-ai-mcp
rm -rf dist build skforecast_ai_mcp.egg-info
python -m build
python -m twine check --strict dist/*
python -m twine upload dist/*
```

`dist/` is removed first because twine uploads every file in it, and the
files of a version already on PyPI make the upload fail. Each upload takes
the `dist/` of the directory it runs in: check the directory first.
