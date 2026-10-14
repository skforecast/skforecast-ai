"""b-07: irregular dates already in ISO 8601 get the hint "write the dates in
ISO 8601 ... so they are not read month-first".

A daily file with ISO dates and 40 random days missing (no regular
frequency). `profile` succeeds with "Frequency: unknown" and "Index
irregularities: none detected"; `plan` fails with an invalid_argument whose
message and hint blame day-first parsing. The SKILL.md tells the agent to
follow `hint`, which asks for something the file already does.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"


async def main(c):
    path = DATA / "random_gaps.csv"
    dates = [line.split(",")[0] for line in path.read_text().splitlines()[1:]]
    all_iso = all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) for d in dates)
    print("Dates of the file are all ISO 8601:", all_iso, dates[:4])
    args = {"data_path": str(path), "target": "y"}
    print("INPUT profile", json.dumps(args))
    _, p = await call(c, "profile", args)
    print(
        "OBSERVED profile:",
        re.findall(r"(Frequency:[^\n]*|Index irregularities:[^\n]*)", p["summary"]),
    )
    print("INPUT plan", json.dumps({"profile_id": p["id"], "steps": 7}))
    err, e = await call(c, "plan", {"profile_id": p["id"], "steps": 7})
    print("OBSERVED:", json.dumps(e, indent=1))
    print(
        "EXPECTED: a message and hint about the irregular spacing (how many "
        "dates are missing for the closest frequency, and that the server "
        "does not fill them in), mentioning day-first dates only when the "
        "dates are not ISO 8601; and the profile reporting the irregularity."
    )
    return (
        all_iso
        and err
        and "ISO 8601" in (e.get("hint") or "")
        and "month-first" in (e.get("hint") or "")
    )


if __name__ == "__main__":
    ok = run(main, allow_dir=DATA)
    print("REPRODUCED" if ok else "NOT REPRODUCED")
    sys.exit(0 if ok else 1)
