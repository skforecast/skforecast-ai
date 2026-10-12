################################################################################
#                         make_agent_session_video                             #
#                                                                              #
# Exports the animation docs/animations/agent-session.html as a GIF for the    #
# README and an MP4. See tools/docs/home_page/README.md.                       #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

"""
Export the animation "A real agent session" as a GIF and an MP4.

The page is opened in Chromium with Playwright in its export mode
(`?export=1`, see `docs/animations/skf-anim.js`), every frame is rendered
with `window.skfRender(t)` and captured, and ffmpeg encodes the frames. The
GIF is scaled to 800 px wide with a palette of its own; the MP4 keeps the
1280 px of the stage, to share it where a GIF is not welcome.

The animation has two cuts (see `generate_agent_session_data.py`): `full`,
the whole session, which the MCP server guide links to, and `short`, the
abridged one of the README. Each has its GIF: `docs/img/agent-session.gif`
and `docs/img/agent-session-short.gif`.

Needs `pip install playwright` and ffmpeg. Playwright's own Chromium works
(`playwright install chromium`); `--chrome` or `CHROME_PATH` point to
another one.

Run from the repository root, after `generate_agent_session_data.py`:

    python tools/docs/home_page/make_agent_session_video.py
    python tools/docs/home_page/make_agent_session_video.py --cut short
    python tools/docs/home_page/make_agent_session_video.py --theme dark \\
        --gif docs/img/agent-session-dark.gif
"""

from __future__ import annotations

import argparse
import functools
import http.server
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ANIMATIONS = REPO_ROOT / "docs" / "animations"
PAGE = "agent-session.html"
WIDTH, HEIGHT = 1280, 860


def serve(directory: Path) -> http.server.ThreadingHTTPServer:
    """
    Serve `directory` over HTTP on a free local port, in a background thread.

    Parameters
    ----------
    directory : Path
        Directory to serve: the page loads its fonts and scripts from it.

    Returns
    -------
    server : http.server.ThreadingHTTPServer
        The running server; call `shutdown()` when done.

    """

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args) -> None:
            pass

    handler = functools.partial(Quiet, directory=str(directory))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def capture(frames: Path, cut: str, theme: str, fps: int,
            chrome: str | None) -> float:
    """
    Render every frame of the animation to a numbered PNG file.

    Parameters
    ----------
    frames : Path
        Empty directory for the frames.
    cut : str
        `full` or `short`.
    theme : str
        `light` or `dark`.
    fps : int
        Frames per second of the capture.
    chrome : str, default None
        Path of a Chromium executable, or None for the one of Playwright.

    Returns
    -------
    duration : float
        Duration of the animation, in seconds.

    """

    from playwright.sync_api import sync_playwright

    server = serve(ANIMATIONS)
    query = f"export=1&cut={cut}&theme={theme}"
    url = f"http://127.0.0.1:{server.server_port}/{PAGE}?{query}"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=chrome)
            page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
            page.goto(url)
            page.wait_for_function("window.skfReady === true")
            duration = page.evaluate("window.skfDuration")
            for i in range(int(duration*fps) + 1):
                page.evaluate(f"window.skfRender({i/fps})")
                page.screenshot(
                    path = frames / f"{i:05d}.png",
                    clip = {"x": 0, "y": 0, "width": WIDTH, "height": HEIGHT},
                )
            browser.close()
    finally:
        server.shutdown()
    return duration


def encode(frames: Path, fps: int, gif: Path, gif_width: int, gif_fps: int,
           mp4: Path | None) -> None:
    """
    Encode the frames as a GIF and, optionally, an MP4.

    Parameters
    ----------
    frames : Path
        Directory with the numbered PNG frames.
    fps : int
        Frames per second of the capture.
    gif : Path
        Output GIF.
    gif_width : int
        Width of the GIF, in pixels.
    gif_fps : int
        Frames per second of the GIF.
    mp4 : Path, default None
        Output MP4, or None for no MP4.

    Returns
    -------
    None

    """

    source = ["-framerate", str(fps), "-i", str(frames / "%05d.png")]
    graph = (
        f"fps={gif_fps},scale={gif_width}:-1:flags=lanczos,split[a][b];"
        "[a]palettegen=max_colors=128:stats_mode=full[p];"
        "[b][p]paletteuse=dither=none:diff_mode=rectangle"
    )
    run = functools.partial(subprocess.run, check=True)
    run(["ffmpeg", "-y", "-loglevel", "error", *source, "-filter_complex", graph,
         "-loop", "0", str(gif)])
    if mp4 is not None:
        run(["ffmpeg", "-y", "-loglevel", "error", *source, "-c:v", "libx264",
             "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p",
             "-movflags", "+faststart", str(mp4)])


def main() -> None:
    """
    Parse the arguments, capture the frames and encode them.

    Returns
    -------
    None

    """

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--cut", choices=["full", "short"], default="full")
    parser.add_argument("--theme", choices=["light", "dark"], default="light")
    parser.add_argument("--gif", type=Path, default=None,
                        help="Output GIF, by default the one of the cut in docs/img.")
    parser.add_argument("--gif-width", type=int, default=800)
    parser.add_argument("--gif-fps", type=int, default=10)
    parser.add_argument("--mp4", type=Path, default=None,
                        help="Also write an MP4 (keep it out of the repository).")
    parser.add_argument("--fps", type=int, default=30, help="Frames per second of the capture.")
    parser.add_argument("--chrome", default=os.environ.get("CHROME_PATH"))
    args = parser.parse_args()

    if shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg is not installed.")
    if args.gif is None:
        name = "agent-session.gif" if args.cut == "full" else "agent-session-short.gif"
        args.gif = REPO_ROOT / "docs" / "img" / name
    with tempfile.TemporaryDirectory() as tmp:
        duration = capture(Path(tmp), args.cut, args.theme, args.fps, args.chrome)
        encode(Path(tmp), args.fps, args.gif, args.gif_width, args.gif_fps, args.mp4)
    for path in (args.gif, args.mp4):
        if path is not None:
            size = path.stat().st_size/1e6
            print(f"Wrote {path} ({duration:.1f} s, {size:.1f} MB)")


if __name__ == "__main__":
    main()
