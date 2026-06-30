#!/usr/bin/env python3
"""Headless render smoke test — catch client-side render hangs before users do.

Why this exists
---------------
A self-triggering ``MutationObserver`` in ``static/js/skuel.js`` once drove an
infinite loop (``createIcons()`` mutated the DOM, which re-fired the observer),
pegging the main thread on every page. Because ``skuel.js`` is render-blocking,
the page body never rendered and the browser/laptop froze. Nothing caught it —
unit tests mock the DOM, and the failure is purely client-side.

This test renders the unauthenticated pages that load the full global JS bundle
(``skuel.js`` + Alpine + lucide + HTMX), serves them with the committed static
assets, and loads each in headless Chrome with a bounded budget. A page that
never reaches idle (infinite loop, runaway synchronous work) makes Chrome exceed
the wall-clock timeout — we fail loudly instead of shipping a page that freezes.

Deliberately NO server / NO Neo4j: the pages are pure FastHTML renders, so we
render them directly and serve the HTML statically. That keeps the check fast and
free of flaky infrastructure while still exercising the real browser JS path.

Run: ``uv run python scripts/smoke_test.py``  (or ``./dev smoke``)
"""

from __future__ import annotations

import functools
import http.server
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

APP_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = APP_ROOT / "static"

# A healthy page reaches idle in ~1-2s. virtual-time-budget nudges Chrome to
# settle quickly; the wall-clock timeout is the real hang detector — a main-thread
# infinite loop blocks virtual time too, so only a hard kill catches it.
PAGE_LOAD_BUDGET_MS = 10_000
WALL_TIMEOUT_S = 30

CHROME_CANDIDATES = (
    "google-chrome-stable",
    "google-chrome",
    "chromium",
    "chromium-browser",
)


def find_chrome() -> str:
    """Locate a Chrome/Chromium binary (CHROME_BIN env wins)."""
    env_bin = os.environ.get("CHROME_BIN")
    if env_bin and shutil.which(env_bin):
        return env_bin
    for candidate in CHROME_CANDIDATES:
        path = shutil.which(candidate)
        if path:
            return path
    raise RuntimeError(
        "No Chrome/Chromium found. Install google-chrome-stable or chromium, "
        "or set CHROME_BIN. (GitHub ubuntu-latest ships google-chrome-stable.)"
    )


def render_pages() -> dict[str, str]:
    """Render the unauthenticated pages that load the full global JS bundle.

    The login landing page is THE canary: it is a complete document whose <head>
    pulls in skuel.js + Alpine + lucide + HTMX — exactly the bundle that froze.
    """
    from fasthtml.common import to_xml

    from ui.system import render_login_landing_page

    renderers: dict[str, Callable[[], Any]] = {
        "login": render_login_landing_page,
    }

    pages: dict[str, str] = {}
    for name, render in renderers.items():
        html = to_xml(render())
        if not html.lstrip()[:15].lower().startswith("<!doctype"):
            html = "<!doctype html>\n" + html
        pages[name] = html
    return pages


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args: Any) -> None:  # noqa: D102 - silence per-request noise
        pass


def serve(root: Path, port: int) -> http.server.ThreadingHTTPServer:
    handler = functools.partial(_QuietHandler, directory=str(root))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def check_page(chrome: str, url: str, profile_dir: Path) -> tuple[bool, str]:
    """Load a page in headless Chrome; True iff it reaches idle with content."""
    cmd = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={profile_dir}",
        f"--virtual-time-budget={PAGE_LOAD_BUDGET_MS}",
        "--run-all-compositor-stages-before-draw",
        "--dump-dom",
        url,
    ]
    try:
        result = subprocess.run(  # noqa: S603 - args are fixed/local
            cmd, capture_output=True, text=True, timeout=WALL_TIMEOUT_S
        )
    except subprocess.TimeoutExpired:
        return False, (
            f"HANG — page never reached idle within {WALL_TIMEOUT_S}s "
            "(infinite JS loop or runaway synchronous work)"
        )

    dom = result.stdout or ""
    if result.returncode != 0:
        return False, f"chrome exited {result.returncode}: {result.stderr.strip()[-300:]}"
    if "SKUEL" not in dom:
        return False, "DOM missing expected content (brand marker 'SKUEL' absent)"
    icon_count = dom.count("<svg")
    if icon_count == 0:
        return False, "no <svg> in DOM — lucide.createIcons() never completed (icons unrendered)"
    return True, f"idle OK · {icon_count} icon(s) rendered · {len(dom):,} bytes"


def main() -> int:
    print("▶ render smoke test (headless Chrome)")
    try:
        chrome = find_chrome()
    except RuntimeError as exc:
        print(f"✗ {exc}")
        return 1
    print(f"  chrome: {chrome}")

    pages = render_pages()
    port = _free_port()

    with tempfile.TemporaryDirectory(prefix="skuel-smoke-") as tmp:
        root = Path(tmp)
        # Absolute /static/* references in the HTML resolve against the server
        # root via this symlink to the committed static assets.
        os.symlink(STATIC_DIR, root / "static")
        for name, html in pages.items():
            (root / f"{name}.html").write_text(html, encoding="utf-8")

        server = serve(root, port)
        profiles = root / "_profiles"
        profiles.mkdir()
        failures = 0
        try:
            for name in pages:
                url = f"http://127.0.0.1:{port}/{name}.html"
                ok, detail = check_page(chrome, url, profiles / name)
                marker = "✓" if ok else "✗"
                print(f"  {marker} {name}: {detail}")
                if not ok:
                    failures += 1
        finally:
            server.shutdown()

    if failures:
        print(f"✗ smoke test FAILED — {failures} page(s) did not load cleanly")
        return 1
    print("✓ smoke test passed — all pages reached idle")
    return 0


if __name__ == "__main__":
    sys.exit(main())
