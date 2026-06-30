#!/usr/bin/env python3
"""Headless render smoke test — catch client-side render hangs before users do.

Why this exists
---------------
A self-triggering ``MutationObserver`` in ``static/js/skuel.js`` once drove an
infinite loop (``createIcons()`` mutated the DOM, which re-fired the observer),
pegging the main thread on every page. Because ``skuel.js`` is render-blocking,
the page body never rendered and the browser/laptop froze. Nothing caught it —
unit tests mock the DOM, and the failure is purely client-side.

This test renders pages that load the full global JS bundle (``skuel.js`` +
Alpine + HTMX), serves them with the committed static assets, and loads each in
headless Chrome with a bounded budget. Two failure classes are caught:

1. **Render hangs** — a page that never reaches idle (infinite loop, runaway
   synchronous work) blows the wall-clock timeout. We fail loudly instead of
   shipping a page that freezes.
2. **JS console errors** — uncaught ``ReferenceError``/``TypeError`` and Alpine
   expression errors (e.g. ``<component> is not defined``). These do *not* hang
   the page, so the hang detector misses them. ``--enable-logging=stderr`` lets
   us scan Chrome's console output and fail on the registration/timing class
   that shipped silently in #468 (Alpine ``Alpine.data()`` components registered
   in ``DOMContentLoaded`` instead of ``alpine:init``).

The ``js_smoke`` fixture exists for (2): it mounts one representative ``x-data``
per ``skuel.js`` registry block so a registration regression surfaces as an
"is not defined" console error. Network side effects (``fetch``/``WebSocket``)
are stubbed in-page so component ``init()`` runs harmlessly — this is a
*registration* check, not a data-fetch check.

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
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fasthtml.common import FT

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


# JS error signatures that mean a script failed (not a handled app-level error
# like "Failed to load ...: HTTP 404", which is normal in a server-less fixture).
# Scoped tightly so component init() noise (fetch/WS failures) does NOT false-fail.
# "Uncaught (in promise)" catches async throws — Chrome puts "(in promise)"
# between "Uncaught" and the error type, so the plain "Uncaught TypeError" marker
# would miss them.
_JS_ERROR_MARKERS = (
    "Alpine Expression Error",
    "is not defined",
    "Uncaught ReferenceError",
    "Uncaught TypeError",
    "Uncaught SyntaxError",
    "Uncaught (in promise)",
)

# Every Alpine.data() component in skuel.js, with minimal valid constructor args.
# Mounting all of them (not just the block that broke in #468) means a wrong
# lifecycle hook (DOMContentLoaded vs alpine:init) for ANY component surfaces as
# "<component> is not defined" on init. Kept in sync with the registry by
# _assert_registry_in_sync() — adding a component to skuel.js without adding it
# here fails the smoke test.
_REGISTRY_COMPONENTS = (
    "searchFilters",
    "calendarPage",
    "collapsible(true)",
    "collapsibleSidebar('k', false)",
    "chartVis('/x.json', 'bar')",
    "timelineVis('/x.json')",
    "toastManager",
    "entityPicker",
    "formValidator",
    "hierarchyTree({entityType: 'goal'})",
    "bulkInsightManager",
    "relationshipGraph('uid', 'tasks', 1)",
    "domainFilter",
    "insightDetailModal('i1')",
    "intelligenceCache",
    "profileFocusHandler('f1')",
    "insightFiltersDebounced({})",
    "ingestionProgress('op1')",
    "offlineIndicator",
    "exploreSearch('tag')",
    "exploreGraph('mode', 'uid', 'tasks')",
    "revisionForm",
    "batchTranscribe",
    "userFolderTranscribe",
    "submit('dest', false, false)",
)

# Run before Alpine starts: neutralise component init() network side effects so
# the fixture is hermetic and quiet. We assert registration, not data fetching.
_FIXTURE_STUB_JS = (
    "window.fetch = function () { return new Promise(function () {}); };"
    "window.WebSocket = function () { return { close: function () {}, send: function () {} }; };"
)


def _assert_registry_in_sync() -> str | None:
    """Fail if skuel.js registers a component not mounted by the js_smoke fixture.

    Counts ``Alpine.data('name'`` registrations in skuel.js and compares the set
    of names to the fixture's. Keeps the fixture honest: a new component added to
    skuel.js must be added here, or it would silently escape the timing check.
    Returns an error message, or None if in sync.
    """
    import re

    js = (STATIC_DIR / "js" / "skuel.js").read_text(encoding="utf-8")
    registered = set(re.findall(r"Alpine\.data\(\s*'([^']+)'", js))
    # The fixture expression is "name" or "name(args)"; take the leading identifier.
    mounted = {m.group(0) for expr in _REGISTRY_COMPONENTS if (m := re.match(r"\w+", expr))}
    missing = registered - mounted
    extra = mounted - registered
    if missing or extra:
        parts = []
        if missing:
            parts.append(f"not mounted by fixture: {', '.join(sorted(missing))}")
        if extra:
            parts.append(f"in fixture but not in skuel.js: {', '.join(sorted(extra))}")
        return "js_smoke fixture out of sync with skuel.js registry — " + "; ".join(parts)
    return None


def _render_js_smoke_fixture() -> "FT":
    """Build a hermetic page that mounts every skuel.js registry component.

    Uses the real ``build_head()`` bundle so the registration timing matches
    production exactly (Alpine ``defer`` + ``queueMicrotask`` start).
    """
    from fasthtml.common import Body, Div, Html, Script, Span

    from ui.components.icon import Icon
    from ui.layouts.base_page import build_head

    component_divs = [Div(Span("x"), **{"x-data": expr}) for expr in _REGISTRY_COMPONENTS]
    return Html(
        build_head("JS Component Smoke"),
        Body(
            # First child: stubs run during parse, before Alpine's post-defer start.
            Script(_FIXTURE_STUB_JS),
            # "SKUEL" satisfies the brand-marker check; Icon satisfies the <svg> check.
            Div("SKUEL", Icon("check"), *component_divs),
        ),
    )


def render_pages() -> dict[str, str]:
    """Render the pages that load the full global JS bundle.

    - ``login``: THE canary — a complete document whose <head> pulls in skuel.js
      + Alpine + HTMX, exactly the bundle that once froze.
    - ``js_smoke``: mounts one x-data per skuel.js registry block to catch Alpine
      component registration/timing regressions (#468).
    """
    from fasthtml.common import to_xml

    from ui.system import render_login_landing_page

    renderers: dict[str, Callable[[], Any]] = {
        "login": render_login_landing_page,
        "js_smoke": _render_js_smoke_fixture,
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


def _scan_console_errors(stderr: str) -> list[str]:
    """Return JS-error console lines (uncaught exceptions, Alpine expression errors).

    Scoped to ``_JS_ERROR_MARKERS`` so Chrome internals and handled app errors
    (e.g. "Failed to load ...: HTTP 404") do not register as failures.
    """
    hits: list[str] = []
    for line in stderr.splitlines():
        if "CONSOLE" not in line:
            continue
        if any(marker in line for marker in _JS_ERROR_MARKERS):
            # Trim Chrome's "[pid:pid:ts:INFO:CONSOLE:n]" prefix for a readable message.
            hits.append(line.split("CONSOLE:", 1)[-1].split("]", 1)[-1].strip())
    return hits


def check_page(chrome: str, url: str, profile_dir: Path) -> tuple[bool, str]:
    """Load a page in headless Chrome; True iff it reaches idle with content and no JS errors."""
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
        # Surface page console output on stderr so we can detect JS errors that
        # don't hang the page (Alpine "is not defined", uncaught exceptions).
        "--enable-logging=stderr",
        "--v=0",
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
        return (
            False,
            "no <svg> in DOM — server-rendered inline icons (ui/components/icon.py) absent",
        )
    js_errors = _scan_console_errors(result.stderr or "")
    if js_errors:
        shown = "; ".join(js_errors[:3])
        return False, f"JS console error(s): {shown}"
    return True, f"idle OK · {icon_count} icon(s) rendered · {len(dom):,} bytes"


def main() -> int:
    print("▶ render smoke test (headless Chrome)")
    try:
        chrome = find_chrome()
    except RuntimeError as exc:
        print(f"✗ {exc}")
        return 1
    print(f"  chrome: {chrome}")

    drift = _assert_registry_in_sync()
    if drift:
        print(f"  ✗ {drift}")
        return 1

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
