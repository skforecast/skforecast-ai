################################################################################
#                           check_release_notes                                #
#                                                                              #
# Checks the section of the version in development of the release notes.      #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

"""
Report the state of the version in development in `docs/releases/releases.md`.

Usage, from the repository root (standard library only):

    python tools/docs/check_release_notes.py

It prints the link references used but not defined, the size of the section,
the entries over the length ceiling, the entries without a pull request or
issue link and the entries that still carry a badge. The exit code is 1 only
for undefined references, which break the documentation build; the rest is
for the author to judge. Released versions are out of scope.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

RELEASES = Path(__file__).resolve().parents[2] / "docs" / "releases" / "releases.md"
MAX_WORDS = 80
SUBSECTION = re.compile(r"^\*\*(Added|Changed|Fixed)\*\*\s*$", flags=re.M)


def count_words(entry: str) -> int:
    """
    Count the words a reader sees: HTML tags and link targets are left out.

    Parameters
    ----------
    entry : str
        Line of one entry, starting with `+ `.

    Returns
    -------
    n_words : int
        Number of words of the rendered entry.
    """

    text = re.sub(r"<[^>]+>", " ", entry)
    text = re.sub(r"\]\([^)]*\)", "]", text)
    text = re.sub(r"\]\[[^\]]*\]", "]", text)

    return len(text.lstrip("+ ").split())


def main() -> int:
    """
    Print the report of the section in development.

    Returns
    -------
    exit_code : int
        1 when a link reference is used but not defined, 0 otherwise.
    """

    text = RELEASES.read_text(encoding="utf-8")
    match = re.search(r"^## .*In development.*?(?=^## )", text, flags=re.M | re.S)
    if match is None:
        print("No section marked 'In development' in", RELEASES.name)
        return 0
    dev = match.group(0)

    first = SUBSECTION.search(dev)
    head = dev[: first.start()] if first else dev
    body = dev[first.start():] if first else ""
    highlights = re.findall(r"^\+ .*", head, flags=re.M)
    entries = re.findall(r"^\+ .*", body, flags=re.M)

    used = set(re.findall(r"\]\[([^\]\s]+)\]", dev))
    defined = set(re.findall(r"^\[([^\]]+)\]:", text, flags=re.M))
    undefined = sorted(used - defined)
    too_long = [e for e in highlights + entries if count_words(e) > MAX_WORDS]
    no_link = [e for e in entries if "/pull/" not in e and "/issues/" not in e]
    with_badge = [e for e in entries if 'class="badge' in e]

    print("Undefined references:", ", ".join(undefined) or "none")
    print(
        f"Words: {len(dev.split())} | entries: {len(entries)} | "
        f"highlights: {len(highlights)}"
    )
    print(f"Entries over {MAX_WORDS} words: {len(too_long)}")
    for entry in too_long:
        print(f"  {count_words(entry)} words: {entry[:90]}")
    print(f"Entries without a pull request or issue link: {len(no_link)}")
    print(f"Entries with a badge (badges go only in the highlights): {len(with_badge)}")

    return 1 if undefined else 0


if __name__ == "__main__":
    sys.exit(main())
