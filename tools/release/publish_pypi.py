"""Checks of `.github/workflows/publish-pypi.yml`.

Each subcommand is one step of the workflow and fails with a message that
GitHub shows as an error annotation:

- `version`: reads the version of `skforecast-ai` and `skforecast-ai-mcp`,
  checks that they agree and are canonical, and, for a rehearsal, rewrites
  them as `X.Y.Z.devN` so that TestPyPI never holds the names of a release.
  It also gives the Python versions of the smoke tests.
- `release`: the GitHub release matches the version (tag, pre-release flag)
  and its commit is on the release branch `X.Y.x`. It only reads the files
  and git, so the release steps run it locally before creating the release
  (`packages/README.md`), with the same code as the workflow:

      python tools/release/publish_pypi.py release --tag vX.Y.Z \
          --prerelease false --sha <commit>
- `contents`: the files that each distribution must and must not hold.
- `absent`: the version is not on the index yet, checked before the
  approval of the deployment.
- `uploaded`: the index serves exactly the files built in this run, compared
  by their SHA256.

It needs `packaging` besides the standard library and runs from the root of
the repository.
"""

from __future__ import annotations

import argparse
import email.message
import email.parser
import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile
import time
import tomllib
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version

ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = ROOT / "pyproject.toml"
INIT = ROOT / "skforecast_ai" / "__init__.py"
LAUNCHER = ROOT / "packages" / "skforecast-ai-mcp"
LAUNCHER_PYPROJECT = LAUNCHER / "pyproject.toml"
PROJECTS = ("skforecast-ai", "skforecast-ai-mcp")
MCP_NAME = "mcp-name: io.github.skforecast/skforecast-ai"
# The sdist of skforecast-ai leaves these out (`MANIFEST.in`).
PRUNED = ("dev/", "packages/", "tools/mcp/agent_reports/")
USER_AGENT = "skforecast-ai-publish-check"


class CheckError(Exception):
    """A check of the workflow failed."""


def _output(**values: str) -> None:
    """Write step outputs to `GITHUB_OUTPUT`, or print them locally."""
    lines = [f"{key}={value}" for key, value in values.items()]
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))


def _replace_once(path: Path, pattern: str, replacement: str) -> None:
    """Replace the single match of `pattern` in `path`."""
    text = path.read_text(encoding="utf-8")
    new, count = re.subn(pattern, replacement, text, flags=re.MULTILINE)
    if count != 1:
        raise CheckError(
            f"{path.relative_to(ROOT)}: expected one match of {pattern!r}, "
            f"found {count}"
        )
    path.write_text(new, encoding="utf-8")


def _lowest_python(requires_python: str, main: str) -> str:
    """Lowest minor version of Python 3 that `requires_python` accepts."""
    spec = SpecifierSet(requires_python)
    main_minor = Version(main).release[1]
    for minor in range(8, main_minor + 1):
        if f"3.{minor}" in spec:
            return f"3.{minor}"
    raise CheckError(f"requires-python {requires_python!r} excludes Python {main}")


def _read_version() -> tuple[str, dict, dict]:
    """Read and check the version of both projects.

    Returns the version and the `[project]` tables of `skforecast-ai` and
    `skforecast-ai-mcp`.
    """
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    launcher = tomllib.loads(LAUNCHER_PYPROJECT.read_text(encoding="utf-8"))[
        "project"
    ]
    version = project["version"]
    match = re.search(
        r'^__version__ = "([^"]+)"$', INIT.read_text(encoding="utf-8"), re.MULTILINE
    )
    found = {
        "pyproject.toml": version,
        "skforecast_ai/__init__.py": match.group(1) if match else None,
        "packages/skforecast-ai-mcp/pyproject.toml": launcher["version"],
    }
    if len(set(found.values())) != 1:
        raise CheckError(f"the versions do not agree: {found}")

    try:
        parsed = Version(version)
    except InvalidVersion as exc:
        raise CheckError(f"{version!r} is not a valid version") from exc
    if str(parsed) != version:
        raise CheckError(
            f"the version {version!r} is not canonical: write {str(parsed)!r}"
        )
    if parsed.local is not None:
        raise CheckError(f"the version {version!r} has a local label")

    pin = f"skforecast-ai[mcp]=={version}"
    if launcher["dependencies"] != [pin]:
        raise CheckError(
            f"skforecast-ai-mcp depends on {launcher['dependencies']}, "
            f"expected [{pin!r}]"
        )
    if project["requires-python"] != launcher["requires-python"]:
        raise CheckError(
            f"requires-python differs: {project['requires-python']!r} and "
            f"{launcher['requires-python']!r}"
        )
    return version, project, launcher


def cmd_version(args: argparse.Namespace) -> None:
    """Check the versions and, for a rehearsal, turn them into `.devN`."""
    version, project, _ = _read_version()
    pin = f"skforecast-ai[mcp]=={version}"
    if args.rehearsal:
        # The canonical form writes the dev segment last, as `.devN`.
        rehearsal = f"{version.split('.dev')[0]}.dev{args.rehearsal}"
        Version(rehearsal)
        _replace_once(PYPROJECT, r'^version = "[^"]+"$', f'version = "{rehearsal}"')
        _replace_once(
            INIT, r'^__version__ = "[^"]+"$', f'__version__ = "{rehearsal}"'
        )
        _replace_once(
            LAUNCHER_PYPROJECT, r'^version = "[^"]+"$', f'version = "{rehearsal}"'
        )
        _replace_once(
            LAUNCHER_PYPROJECT,
            re.escape(f'"{pin}"'),
            f'"skforecast-ai[mcp]=={rehearsal}"',
        )
        print(f"Rehearsal of {version} as {rehearsal}")
        version = rehearsal

    lowest = _lowest_python(project["requires-python"], args.main_python)
    pythons = sorted({lowest, args.main_python}, key=Version)
    _output(version=version, pythons=json.dumps(pythons))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(
                f"skforecast-ai and skforecast-ai-mcp **{version}** to "
                f"**{args.target}**, smoke tests on Python "
                f"{' and '.join(pythons)}\n"
            )


def _git(*args: str) -> subprocess.CompletedProcess:
    """Run git in the repository."""
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True
    )


def cmd_release(args: argparse.Namespace) -> None:
    """Check a GitHub release against the files of its commit.

    The workflow runs it once the release is published, and the release
    steps run it locally before creating the release, in a checkout of the
    same commit. It reads the version from the files, never from the build,
    and git for the branch: run `git fetch origin X.Y.x` first.
    """
    head = _git("rev-parse", "HEAD").stdout.strip()
    sha = _git("rev-parse", "--verify", "--quiet", f"{args.sha}^{{commit}}")
    if sha.returncode != 0:
        raise CheckError(f"{args.sha} is not a commit of this repository")
    if sha.stdout.strip() != head:
        raise CheckError(
            f"the checkout is {head}, not {args.sha}: the version is read from "
            f"the files, so check out the commit of the release first"
        )
    version_files = [
        str(path.relative_to(ROOT)) for path in (PYPROJECT, INIT, LAUNCHER_PYPROJECT)
    ]
    changed = _git("diff", "--name-only", "HEAD", "--", *version_files).stdout.split()
    if changed:
        raise CheckError(f"uncommitted changes in {', '.join(changed)}")

    text, _, _ = _read_version()
    version = Version(text)
    if version.is_devrelease:
        raise CheckError(f"{text} is a development version, not a release")
    if args.tag != f"v{text}":
        raise CheckError(f"the tag is {args.tag} and the version is {text}")

    prerelease = args.prerelease == "true"
    if prerelease != version.is_prerelease:
        if version.is_prerelease:
            reason = "is a pre-release, so the GitHub release must be one too"
        else:
            reason = "is not a pre-release, so the GitHub release cannot be one"
        raise CheckError(f"{text} {reason}")

    branch = f"{version.major}.{version.minor}.x"
    result = _git("merge-base", "--is-ancestor", head, f"origin/{branch}")
    if result.returncode == 1:
        raise CheckError(f"the commit {args.sha} is not on the branch {branch}")
    if result.returncode != 0:
        raise CheckError(
            f"cannot check the branch {branch} (git fetch origin {branch}?): "
            f"{result.stderr.strip()}"
        )
    print(f"{args.tag}: version {text}, pre-release {prerelease}, commit on {branch}")


def _tracked(prefix: str) -> set[str]:
    """Files that git tracks under `prefix`, relative to the root."""
    out = subprocess.run(
        ["git", "ls-files", "-z", prefix],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    return {name for name in out.split("\0") if name}


def _distribution_files(directory: Path, stem: str, version: str) -> tuple[Path, Path]:
    """The wheel and the sdist of one project, and nothing else."""
    wheel = directory / f"{stem}-{version}-py3-none-any.whl"
    sdist = directory / f"{stem}-{version}.tar.gz"
    found = sorted(path.name for path in directory.iterdir())
    if found != sorted([wheel.name, sdist.name]):
        raise CheckError(
            f"{directory}: expected {wheel.name} and {sdist.name}, found {found}"
        )
    return wheel, sdist


def _check_wheel(
    wheel: Path,
    stem: str,
    version: str,
    expected: set[str],
    requires_python: str,
    console_script: str,
) -> email.message.Message:
    """Check the files and the metadata of a wheel; return the metadata."""
    dist_info = f"{stem}-{version}.dist-info/"
    with zipfile.ZipFile(wheel) as zf:
        names = set(zf.namelist())
        metadata = email.parser.Parser().parsestr(
            zf.read(dist_info + "METADATA").decode("utf-8")
        )
        entry_points = zf.read(dist_info + "entry_points.txt").decode("utf-8")
    files = {name for name in names if not name.startswith(dist_info)}
    problems = []
    if files - expected:
        problems.append(f"unexpected files {sorted(files - expected)}")
    if expected - files:
        problems.append(f"missing files {sorted(expected - files)}")
    if metadata["Version"] != version:
        problems.append(f"metadata version {metadata['Version']}")
    if metadata["Requires-Python"] != requires_python:
        problems.append(f"Requires-Python {metadata['Requires-Python']}")
    if f"{dist_info}licenses/LICENSE" not in names:
        problems.append("no LICENSE")
    if console_script not in entry_points.splitlines():
        problems.append(f"no console script {console_script!r}")
    if problems:
        raise CheckError(f"{wheel.name}: " + "; ".join(problems))
    return metadata


def _check_sdist(sdist: Path, top: str, required: set[str]) -> None:
    """Check that an sdist holds `required` and nothing pruned or compiled."""
    with tarfile.open(sdist) as tf:
        names = {
            name.removeprefix(top) for name in tf.getnames() if name.startswith(top)
        }
    problems = []
    if required - names:
        problems.append(f"missing files {sorted(required - names)}")
    unwanted = sorted(
        name
        for name in names
        if name.startswith(PRUNED) or "__pycache__" in name or name.endswith(".pyc")
    )
    if unwanted:
        problems.append(f"unexpected files {unwanted[:10]}")
    if problems:
        raise CheckError(f"{sdist.name}: " + "; ".join(problems))


def cmd_contents(args: argparse.Namespace) -> None:
    """Check the contents of the four distributions."""
    version = args.version
    dist = Path(args.dist)
    requires_python = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))[
        "project"
    ]["requires-python"]

    package = _tracked("skforecast_ai")
    if not any(name.startswith("skforecast_ai/skills/") for name in package):
        raise CheckError("git tracks no skill under skforecast_ai/skills/")
    wheel, sdist = _distribution_files(dist / "skforecast-ai", "skforecast_ai", version)
    _check_wheel(
        wheel,
        "skforecast_ai",
        version,
        package,
        requires_python,
        "skforecast-ai = skforecast_ai.cli:app",
    )
    _check_sdist(
        sdist,
        f"skforecast_ai-{version}/",
        package | {"pyproject.toml", "LICENSE", "README.md", "PKG-INFO"},
    )

    prefix = "packages/skforecast-ai-mcp/"
    launcher = {name.removeprefix(prefix) for name in _tracked(prefix)}
    code = {name for name in launcher if name.startswith("skforecast_ai_mcp/")}
    wheel, sdist = _distribution_files(
        dist / "skforecast-ai-mcp", "skforecast_ai_mcp", version
    )
    metadata = _check_wheel(
        wheel,
        "skforecast_ai_mcp",
        version,
        code,
        requires_python,
        "skforecast-ai-mcp = skforecast_ai_mcp:main",
    )
    requires = metadata.get_all("Requires-Dist") or []
    if requires != [f"skforecast-ai[mcp]=={version}"]:
        raise CheckError(f"{wheel.name}: Requires-Dist {requires}")
    if MCP_NAME not in metadata.get_payload():
        raise CheckError(
            f"{wheel.name}: the description lacks {MCP_NAME!r}, which the MCP "
            f"registry looks for"
        )
    _check_sdist(
        sdist,
        f"skforecast_ai_mcp-{version}/",
        code | {"pyproject.toml", "LICENSE", "README.md", "PKG-INFO"},
    )
    print(f"The contents of the four distributions of {version} are as expected")


def _release_files(index: str, project: str, version: str) -> dict[str, str] | None:
    """Files of a version on an index, by name, with their SHA256.

    Returns None when the index does not have the version.
    """
    url = f"{index.rstrip('/')}/pypi/{project}/{version}/json"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    return {item["filename"]: item["digests"]["sha256"] for item in data["urls"]}


def cmd_absent(args: argparse.Namespace) -> None:
    """Fail when the index already has the version of either project."""
    present = [
        project
        for project in PROJECTS
        if _release_files(args.index, project, args.version) is not None
    ]
    if present:
        raise CheckError(
            f"{args.index} already has {args.version} of {', '.join(present)}"
        )
    print(f"{args.index} does not have {args.version} yet")


def cmd_uploaded(args: argparse.Namespace) -> None:
    """Wait until the index lists the built files and compare their hashes."""
    dist = Path(args.dist)
    deadline = time.monotonic() + args.wait
    for project in PROJECTS:
        built = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((dist / project).iterdir())
        }
        while True:
            listed = _release_files(args.index, project, args.version) or {}
            for name, digest in listed.items():
                if name in built and built[name] != digest:
                    raise CheckError(
                        f"{name} on {args.index} is not the file built in this run"
                    )
            if listed.keys() == built.keys():
                break
            if time.monotonic() > deadline:
                raise CheckError(
                    f"{args.index} lists {sorted(listed)} for {project} "
                    f"{args.version}, expected {sorted(built)}"
                )
            time.sleep(15)
        print(f"{project} {args.version}: {len(built)} files, same SHA256")


def main(argv: list[str] | None = None) -> int:
    """Run one subcommand; return the exit code."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("version")
    p.add_argument("--main-python", required=True)
    p.add_argument("--target", default="the index", help="for the summary")
    p.add_argument("--rehearsal",help="N of the .devN version of a rehearsal")
    p.set_defaults(func=cmd_version)

    p = sub.add_parser("release")
    p.add_argument("--tag", required=True)
    p.add_argument("--prerelease", required=True, choices=["true", "false"])
    p.add_argument("--sha", required=True)
    p.set_defaults(func=cmd_release)

    p = sub.add_parser("contents")
    p.add_argument("--version", required=True)
    p.add_argument("--dist", required=True)
    p.set_defaults(func=cmd_contents)

    p = sub.add_parser("absent")
    p.add_argument("--version", required=True)
    p.add_argument("--index", required=True)
    p.set_defaults(func=cmd_absent)

    p = sub.add_parser("uploaded")
    p.add_argument("--version", required=True)
    p.add_argument("--index", required=True)
    p.add_argument("--dist", required=True)
    p.add_argument("--wait", type=int, default=300, help="seconds")
    p.set_defaults(func=cmd_uploaded)

    args = parser.parse_args(argv)
    try:
        args.func(args)
    except CheckError as exc:
        print(f"::error::{exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
