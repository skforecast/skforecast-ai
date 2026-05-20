#!/usr/bin/env python3
"""
Download the pinned version of llms-base.txt from the skforecast core repo
and save it to skforecast_ai/resources/llms-base.txt.

Usage
-----
    # Download (or update) the resource
    python tools/sync_skforecast_assets.py

    # CI check: verify the local copy matches the pinned remote version
    python tools/sync_skforecast_assets.py --check
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SKFORECAST_BRANCH = "master"
SKFORECAST_RAW_URL = (
    "https://raw.githubusercontent.com/skforecast/skforecast/"
    f"{SKFORECAST_BRANCH}/tools/ai/llms-base.txt"
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEST_PATH = REPO_ROOT / "skforecast_ai" / "resources" / "llms-base.txt"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _download(url: str) -> bytes:
    """Download *url* and return its content as bytes."""
    req = Request(url, headers={"User-Agent": "skforecast-ai-sync/1.0"})
    try:
        with urlopen(req, timeout=30) as resp:  # noqa: S310
            return resp.read()
    except HTTPError as exc:
        sys.exit(
            f"Error: HTTP {exc.code} when fetching {url}\n"
            f"Hint: does branch '{SKFORECAST_BRANCH}' exist in the skforecast repo?"
        )
    except URLError as exc:
        sys.exit(f"Error: could not reach {url} — {exc.reason}")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def sync() -> None:
    """Download llms-base.txt and write it to *DEST_PATH*."""
    print(f"Downloading llms-base.txt (skforecast branch: {SKFORECAST_BRANCH}) ...")
    data = _download(SKFORECAST_RAW_URL)

    DEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEST_PATH.write_bytes(data)

    print(f"Saved to {DEST_PATH.relative_to(REPO_ROOT)}  ({len(data):,} bytes)")


def check() -> None:
    """Verify the local copy matches the pinned remote version."""
    if not DEST_PATH.exists():
        sys.exit(
            f"Check failed: {DEST_PATH.relative_to(REPO_ROOT)} does not exist.\n"
            f"Run `python tools/sync_skforecast_assets.py` first."
        )

    print(f"Fetching remote llms-base.txt (skforecast branch: {SKFORECAST_BRANCH}) ...")
    remote_data = _download(SKFORECAST_RAW_URL)
    local_data = DEST_PATH.read_bytes()

    remote_hash = _sha256(remote_data)
    local_hash = _sha256(local_data)

    if remote_hash != local_hash:
        sys.exit(
            f"Check failed: local and remote llms-base.txt differ.\n"
            f"  local  sha256: {local_hash}\n"
            f"  remote sha256: {remote_hash}\n"
            f"Run `python tools/sync_skforecast_assets.py` to update."
        )

    print("Check passed: local copy matches the pinned remote version.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync llms-base.txt from the skforecast core repository."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify the local copy matches the pinned remote version (for CI).",
    )
    args = parser.parse_args()

    if args.check:
        check()
    else:
        sync()


if __name__ == "__main__":
    main()
