#!/usr/bin/env python3
"""
Sync AI assets (llms-base.txt and skills/) from the skforecast core repo.

Downloads from a configurable branch/tag and places files into:
  - skforecast_ai/resources/llms-base.txt
  - skforecast_ai/skills/<skill-name>/SKILL.md  (full refresh)

Usage
-----
    # Sync all assets from the default branch
    python tools/sync_skforecast_assets.py

    # Sync from a specific branch or tag
    python tools/sync_skforecast_assets.py --branch 0.23.x

    # CI check: verify local copies match the remote version
    python tools/sync_skforecast_assets.py --check

    # CI check against a specific branch
    python tools/sync_skforecast_assets.py --check --branch v0.22.0
"""

from __future__ import annotations

import argparse
import hashlib
import io
import re
import shutil
import sys
import tarfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DEFAULT_BRANCH = "auto"

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
DEST_LLMS = REPO_ROOT / "skforecast_ai" / "resources" / "llms-base.txt"
DEST_SKILLS = REPO_ROOT / "skforecast_ai" / "skills"

# Paths inside the skforecast tarball (relative to archive root)
TARBALL_LLMS_PATH = "tools/ai/llms-base.txt"
TARBALL_SKILLS_PREFIX = "skills/"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _resolve_branch(branch: str) -> str:
    """
    Resolve branch name. If 'auto', derive from pyproject.toml.

    Parses the skforecast dependency spec (e.g. 'skforecast>=0.22,<0.23')
    and returns the branch pattern '{major}.{minor}.x' (e.g. '0.22.x').
    """
    if branch != "auto":
        return branch

    if not PYPROJECT_PATH.exists():
        sys.exit(
            "Error: --branch auto requires pyproject.toml at repo root.\n"
            f"Expected: {PYPROJECT_PATH}"
        )

    content = PYPROJECT_PATH.read_text()
    # Match: "skforecast>=0.22" or "skforecast>=0.22,<0.23"
    match = re.search(r'"skforecast>=([\d.]+)', content)
    if not match:
        sys.exit(
            "Error: could not find skforecast version pin in pyproject.toml.\n"
            "Expected a dependency like: \"skforecast>=0.22,<0.23\""
        )

    version = match.group(1)  # e.g. "0.22"
    resolved = f"{version}.x"
    print(f"Resolved --branch auto -> {resolved} (from pyproject.toml)")
    return resolved


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _archive_url(branch: str) -> str:
    return f"https://github.com/skforecast/skforecast/archive/{branch}.tar.gz"


def _download(url: str, branch: str) -> bytes:
    """Download *url* and return its content as bytes."""
    req = Request(url, headers={"User-Agent": "skforecast-ai-sync/1.0"})
    try:
        with urlopen(req, timeout=60) as resp:  # noqa: S310
            return resp.read()
    except HTTPError as exc:
        sys.exit(
            f"Error: HTTP {exc.code} when fetching {url}\n"
            f"Hint: does branch/tag '{branch}' exist in the skforecast repo?"
        )
    except URLError as exc:
        sys.exit(f"Error: could not reach {url} — {exc.reason}")


def _extract_from_tarball(
    data: bytes,
) -> tuple[bytes | None, dict[str, bytes]]:
    """
    Extract llms-base.txt and skills from tarball bytes.

    Returns
    -------
    llms_data : bytes or None
    skills : dict mapping relative paths (e.g. "skill-name/SKILL.md",
             "skill-name/references/file.md") -> file content bytes
    """
    llms_data = None
    skills: dict[str, bytes] = {}

    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        for member in tf.getmembers():
            if not member.isfile():
                continue
            # Strip the top-level archive directory (e.g. "skforecast-master/")
            parts = member.name.split("/", 1)
            if len(parts) < 2:
                continue
            rel_path = parts[1]

            if rel_path == TARBALL_LLMS_PATH:
                f = tf.extractfile(member)
                if f:
                    llms_data = f.read()

            elif rel_path.startswith(TARBALL_SKILLS_PREFIX):
                f = tf.extractfile(member)
                if f:
                    # e.g. "skills/complete-api-reference/references/method-signatures.md"
                    skill_rel = rel_path[len(TARBALL_SKILLS_PREFIX):]
                    skills[skill_rel] = f.read()

    return llms_data, skills


def _dir_hash(directory: Path) -> str:
    """Compute combined hash of all files in directory (sorted, deterministic)."""
    h = hashlib.sha256()
    if not directory.exists():
        return h.hexdigest()
    for file_path in sorted(directory.rglob("*")):
        if file_path.is_file():
            h.update(str(file_path.relative_to(directory)).encode())
            h.update(file_path.read_bytes())
    return h.hexdigest()


def _skills_hash_from_dict(skills: dict[str, bytes]) -> str:
    """Compute combined hash from extracted skills dict."""
    h = hashlib.sha256()
    for key in sorted(skills.keys()):
        h.update(key.encode())
        h.update(skills[key])
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def sync(branch: str) -> None:
    """Download and write llms-base.txt and skills/ from the tarball."""
    url = _archive_url(branch)
    print(f"Downloading skforecast archive (branch: {branch}) ...")
    data = _download(url, branch)

    llms_data, skills = _extract_from_tarball(data)

    # --- llms-base.txt ---
    if llms_data is None:
        print("Warning: llms-base.txt not found in archive.")
    else:
        DEST_LLMS.parent.mkdir(parents=True, exist_ok=True)
        DEST_LLMS.write_bytes(llms_data)
        print(
            f"  llms-base.txt -> {DEST_LLMS.relative_to(REPO_ROOT)}"
            f"  ({len(llms_data):,} bytes)"
        )

    # --- skills/ (full refresh) ---
    if not skills:
        print("Warning: no skills found in archive under skills/")
    else:
        if DEST_SKILLS.exists():
            shutil.rmtree(DEST_SKILLS)
        DEST_SKILLS.mkdir(parents=True, exist_ok=True)

        for rel_path, content in sorted(skills.items()):
            dest = DEST_SKILLS / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(content)

        skill_names = sorted({p.split("/")[0] for p in skills})
        print(f"  skills/ -> {DEST_SKILLS.relative_to(REPO_ROOT)}/")
        print(f"    {len(skill_names)} skills: {', '.join(skill_names)}")

    print("Sync complete.")


def check(branch: str) -> None:
    """Verify local assets match the pinned remote version."""
    url = _archive_url(branch)
    print(f"Fetching skforecast archive (branch: {branch}) for check ...")
    data = _download(url, branch)

    llms_data, skills = _extract_from_tarball(data)
    failed = False

    # --- llms-base.txt ---
    if llms_data is not None:
        if not DEST_LLMS.exists():
            print(
                f"FAIL: {DEST_LLMS.relative_to(REPO_ROOT)} does not exist."
            )
            failed = True
        else:
            remote_hash = _sha256(llms_data)
            local_hash = _sha256(DEST_LLMS.read_bytes())
            if remote_hash != local_hash:
                print(
                    f"FAIL: llms-base.txt differs.\n"
                    f"  local  sha256: {local_hash}\n"
                    f"  remote sha256: {remote_hash}"
                )
                failed = True
            else:
                print("  llms-base.txt: OK")

    # --- skills/ ---
    if skills:
        remote_hash = _skills_hash_from_dict(skills)
        local_hash = _dir_hash(DEST_SKILLS)
        if remote_hash != local_hash:
            print(
                f"FAIL: skills/ directory differs.\n"
                f"  local  hash: {local_hash}\n"
                f"  remote hash: {remote_hash}"
            )
            failed = True
        else:
            print(f"  skills/: OK ({len(skills)} files)")

    if failed:
        sys.exit(
            "\nCheck failed. Run "
            f"`python tools/sync_skforecast_assets.py --branch {branch}` to update."
        )

    print("\nAll checks passed.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync AI assets from the skforecast core repository."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify local copies match the pinned remote version (for CI).",
    )
    parser.add_argument(
        "--branch",
        default=DEFAULT_BRANCH,
        help=(
            "Branch or tag to sync from. Use 'auto' (default) to derive "
            "from pyproject.toml skforecast version pin (e.g. >=0.22 -> 0.22.x)."
        ),
    )
    args = parser.parse_args()

    branch = _resolve_branch(args.branch)

    if args.check:
        check(branch)
    else:
        sync(branch)


if __name__ == "__main__":
    main()
