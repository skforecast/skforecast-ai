# Unit test docs/user-guides/skills.md inventory

import re
from pathlib import Path

from skforecast_ai.llm.skills import ALL_SKILLS, _TASK_TYPE_SKILLS

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_GUIDE = REPO_ROOT / "docs" / "user-guides" / "skills.md"

_BACKTICKED = re.compile(r"`([^`]+)`")


def _section(text: str, heading: str) -> str:
    """
    Return the body of the `## heading` section of a Markdown document.

    Parameters
    ----------
    text : str
        Full Markdown document.
    heading : str
        Section title without the `## ` prefix.

    Returns
    -------
    body : str
        Text between the heading and the next `## ` heading.
    """
    start = text.index(f"## {heading}\n")
    match = re.search(r"^## ", text[start + 1:], flags=re.M)
    end = len(text) if match is None else start + 1 + match.start()

    return text[start:end]


def _table_rows(body: str, first_header_cell: str) -> list[list[str]]:
    """
    Return the body rows of the Markdown table whose header starts with a cell.

    Parameters
    ----------
    body : str
        Markdown text containing the table.
    first_header_cell : str
        Exact content of the first header cell, used to locate the table.

    Returns
    -------
    rows : list of list of str
        One list of stripped cell contents per body row, in document order.
    """
    lines = body.splitlines()
    header = next(
        i for i, line in enumerate(lines)
        if line.startswith(f"| {first_header_cell} |")
    )
    rows: list[list[str]] = []
    for line in lines[header + 2:]:
        if not line.startswith("|"):
            break
        rows.append([cell.strip() for cell in line.strip("|").split("|")])

    return rows


def test_skills_guide_table_lists_all_skills_in_inventory_order():
    """
    Test that the "Available skills" table of the skills user guide lists
    exactly the names in `ALL_SKILLS`, in the same order. The skills are
    synced from skforecast and the guide is written by hand, so this is
    what catches a sync that adds or removes a skill without the guide
    being updated. `python tools/sync_skforecast_assets.py --inventory`
    prints the current table.
    """
    text = SKILLS_GUIDE.read_text(encoding="utf-8")
    rows = _table_rows(_section(text, "Available skills"), "Skill")
    documented = [_BACKTICKED.match(row[0]).group(1) for row in rows]

    assert documented == ALL_SKILLS, (
        "docs/user-guides/skills.md does not match ALL_SKILLS. Missing: "
        f"{sorted(set(ALL_SKILLS) - set(documented))}. Extra: "
        f"{sorted(set(documented) - set(ALL_SKILLS))}. Regenerate the rows "
        "with `python tools/sync_skforecast_assets.py --inventory`."
    )


def test_skills_guide_base_skills_table_matches_task_type_routing():
    """
    Test that the "Base skills" table of the skills user guide reproduces
    the `_TASK_TYPE_SKILLS` routing table: every task type is documented
    and the skills listed for it are the ones the router selects.
    """
    text = SKILLS_GUIDE.read_text(encoding="utf-8")
    rows = _table_rows(
        _section(text, "Automatic selection"), "`profile.task_type`"
    )
    documented: dict[str | None, list[str]] = {}
    for task_types, skills in rows:
        keys = _BACKTICKED.findall(task_types) or [None]
        for key in keys:
            documented[key] = _BACKTICKED.findall(skills)

    assert documented == _TASK_TYPE_SKILLS
