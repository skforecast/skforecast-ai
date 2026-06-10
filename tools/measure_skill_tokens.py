#!/usr/bin/env python3
"""
Measure token estimates for each skill and the llms-base.txt reference.

Prints a Python dict literal ready to paste into skills.py, and optionally
updates the constants in-place with --update.

Usage
-----
    python tools/measure_skill_tokens.py           # Print estimates
    python tools/measure_skill_tokens.py --update  # Update skills.py in-place
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent.parent / "skforecast_ai"
RESOURCES_DIR = PACKAGE_DIR / "resources"
SKILLS_DIR = PACKAGE_DIR / "skills"
SKILLS_MODULE = PACKAGE_DIR / "llm" / "skills.py"

CHARS_PER_TOKEN = 4


def measure_skill(skill_dir: Path) -> int:
    """Return estimated tokens for a skill (SKILL.md + references/)."""
    total_chars = 0

    skill_file = skill_dir / "SKILL.md"
    if skill_file.exists():
        total_chars += len(skill_file.read_text(encoding="utf-8"))

    references_dir = skill_dir / "references"
    if references_dir.exists() and references_dir.is_dir():
        for ref_file in sorted(references_dir.iterdir()):
            if ref_file.is_file():
                total_chars += len(ref_file.read_text(encoding="utf-8"))

    return total_chars // CHARS_PER_TOKEN


def measure_reference() -> int:
    """Return estimated tokens for llms-base.txt."""
    ref_file = RESOURCES_DIR / "llms-base.txt"
    if not ref_file.exists():
        print(f"WARNING: {ref_file} not found", file=sys.stderr)
        return 0
    return len(ref_file.read_text(encoding="utf-8")) // CHARS_PER_TOKEN


def collect_estimates() -> tuple[dict[str, int], int]:
    """Collect token estimates for all skills and the reference file."""
    skills: dict[str, int] = {}

    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
            skills[skill_dir.name] = measure_skill(skill_dir)

    reference = measure_reference()
    return skills, reference


def format_dict(skills: dict[str, int]) -> str:
    """Format the skills dict as a Python literal for skills.py."""
    lines = ["_SKILL_TOKEN_ESTIMATES: dict[str, int] = {"]
    for name, tokens in skills.items():
        lines.append(f'    "{name}": {tokens},')
    lines.append("}")
    return "\n".join(lines)


def update_skills_file(skills: dict[str, int], reference: int) -> bool:
    """Update _SKILL_TOKEN_ESTIMATES and _REFERENCE_TOKEN_ESTIMATE in skills.py."""
    content = SKILLS_MODULE.read_text(encoding="utf-8")

    # Replace _SKILL_TOKEN_ESTIMATES block
    pattern_skills = re.compile(
        r"(_SKILL_TOKEN_ESTIMATES: dict\[str, int\] = \{).*?(^\})",
        re.DOTALL | re.MULTILINE,
    )
    new_dict_body = "\n".join(
        f'    "{name}": {tokens},' for name, tokens in skills.items()
    )
    replacement_skills = f"\\1\n{new_dict_body}\n\\2"
    new_content, n = pattern_skills.subn(replacement_skills, content)
    if n == 0:
        print("ERROR: Could not find _SKILL_TOKEN_ESTIMATES in skills.py", file=sys.stderr)
        return False

    # Replace _REFERENCE_TOKEN_ESTIMATE value
    pattern_ref = re.compile(r"^(_REFERENCE_TOKEN_ESTIMATE = )\d+", re.MULTILINE)
    new_content, n = pattern_ref.subn(f"\\g<1>{reference}", new_content)
    if n == 0:
        print("ERROR: Could not find _REFERENCE_TOKEN_ESTIMATE in skills.py", file=sys.stderr)
        return False

    SKILLS_MODULE.write_text(new_content, encoding="utf-8")
    return True


def check_skills_file(skills: dict[str, int], reference: int) -> bool:
    """Check whether skills.py constants match the measured values."""
    content = SKILLS_MODULE.read_text(encoding="utf-8")

    stale: list[str] = []

    # Check all skills on disk are present and have correct values
    for name, expected in skills.items():
        pattern = re.compile(rf'"{re.escape(name)}":\s*(\d+)')
        match = pattern.search(content)
        if match is None:
            stale.append(f"  {name}: missing from _SKILL_TOKEN_ESTIMATES")
        elif int(match.group(1)) != expected:
            stale.append(
                f"  {name}: {match.group(1)} -> {expected}"
            )

    # Check for stale entries in the dict that no longer exist on disk
    existing_entries = re.findall(r'"([\w-]+)":\s*\d+', content)
    for entry in existing_entries:
        if entry not in skills:
            stale.append(f"  {entry}: in _SKILL_TOKEN_ESTIMATES but not in skills/")

    pattern_ref = re.compile(r"^_REFERENCE_TOKEN_ESTIMATE = (\d+)", re.MULTILINE)
    match = pattern_ref.search(content)
    if match is None:
        stale.append("  _REFERENCE_TOKEN_ESTIMATE: missing")
    elif int(match.group(1)) != reference:
        stale.append(
            f"  _REFERENCE_TOKEN_ESTIMATE: {match.group(1)} -> {reference}"
        )

    if stale:
        print("ERROR: Token estimates in skills.py are stale:", file=sys.stderr)
        for line in stale:
            print(line, file=sys.stderr)
        print(
            "\nRun 'python3 tools/measure_skill_tokens.py --update' to fix.",
            file=sys.stderr,
        )
        return False

    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure skill token estimates.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--update",
        action="store_true",
        help="Update skills.py constants in-place.",
    )
    group.add_argument(
        "--check",
        action="store_true",
        help="Check that skills.py constants are up-to-date (CI mode).",
    )
    args = parser.parse_args()

    skills, reference = collect_estimates()

    if args.check:
        if check_skills_file(skills, reference):
            print("✓ Token estimates are up-to-date.")
        else:
            sys.exit(1)
    elif args.update:
        if update_skills_file(skills, reference):
            print(f"✓ Updated {SKILLS_MODULE}")
        else:
            sys.exit(1)
    else:
        print(format_dict(skills))
        print(f"\n_REFERENCE_TOKEN_ESTIMATE = {reference}")


if __name__ == "__main__":
    main()
