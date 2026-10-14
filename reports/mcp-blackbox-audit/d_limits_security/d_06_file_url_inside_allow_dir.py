"""d-06: the URL error tells the agent to download into the allowed directory.

A `file://` URL of a file that is already inside the allowed directory is
`url_not_allowed` with "download the file into the allowed directory and
pass its absolute path" and no hint, although the file is there and its path
is the URL without the scheme. For an http URL the same text tells the agent
to write the file into the allowed directory itself, which the server
instructions forbid ("Never copy, move or rewrite it into that directory
yourself"), while every other path error says to stop and ask the user.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _client import call, run  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
FILE_URL = "file://" + str(DATA / "monthly.csv")
HTTP_URL = "https://example.com/monthly.csv"
OUT = {}


async def main(c):
    for url in (FILE_URL, HTTP_URL):
        OUT[url] = await call(c, "profile", {"data_path": url, "target": "y"})
    OUT["outside"] = await call(
        c, "profile", {"data_path": "/tmp/elsewhere/monthly.csv", "target": "y"})


run(main, allow_dir=DATA)

for url in (FILE_URL, HTTP_URL):
    print("INPUT profile data_path", url)
    print("OBSERVED", json.dumps(OUT[url][1], indent=1))
print("CONTRAST path_not_allowed hint:", OUT["outside"][1]["hint"])
print("EXPECTED: for a file:// URL inside the allowed directory, a hint with")
print("the absolute path to pass; for a remote URL, the same stop and ask the")
print("user advice as path_not_allowed, not 'download the file into the")
print("allowed directory'.")
err, payload = OUT[FILE_URL]
if (err and payload["code"] == "url_not_allowed" and payload["hint"] is None
        and "download the file into the allowed directory" in payload["message"]):
    print("REPRODUCED")
    sys.exit(0)
print("NOT REPRODUCED")
sys.exit(1)
