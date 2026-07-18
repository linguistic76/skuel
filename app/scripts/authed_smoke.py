#!/usr/bin/env python3
"""Authenticated live smoke test — zero JS/render errors across real authed pages.

The CI smoke test (`./dev smoke`) renders static fixtures with no session and
no live backend, so it cannot see exceptions that only fire on real
authenticated chrome (navbar, htmx fragment loads, Alpine page components).
This script closes that gap locally: it logs in through the real
``/login/submit`` flow, drives headless Chrome via CDP against a running app
instance, and asserts ZERO ``Runtime.exceptionThrown`` events and zero
error-level console events across a representative authed page set.

NOT wired into CI (CI has no Neo4j and no running app). Run it locally against
a live server:

    uv run python scripts/authed_smoke.py                     # defaults to :8001
    uv run python scripts/authed_smoke.py --base-url http://localhost:8001 \
        --pages /profile /home /library/exercises

Credentials: username defaults to ``linguistic76``; the password is read via
``get_credential("TEST_USER_PASSWORD")`` and never printed.

Origin: 2026-07-04 — three JS exception classes were live on every authed page
(skuel.js pathInfo, an Alpine expression SyntaxError, an htmx null
querySelector) and invisible to the static smoke gate.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from websockets.sync.client import ClientConnection, connect

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config.credential_store import get_credential

DEFAULT_PAGES = [
    "/profile",
    "/profile/shared",
    "/today",
    "/library/exercises",
    "/tasks",
    "/goals",
    "/notifications",
    "/gradebook",
]

CHROME_BINARY = "google-chrome-stable"
SETTLE_SECONDS = 3.0  # post-load drain window for htmx fragment loads / Alpine init


@dataclass
class PageResult:
    """JS error events + render-shape problems collected for one navigated page."""

    page: str
    exceptions: list[str] = field(default_factory=list)
    console_errors: list[str] = field(default_factory=list)
    render_errors: list[str] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not self.exceptions and not self.console_errors and not self.render_errors


class CdpSession:
    """Minimal synchronous Chrome DevTools Protocol client over one page target."""

    def __init__(self, ws: ClientConnection) -> None:
        self.ws = ws
        self._next_id = 0
        self.events: list[dict] = []

    def send(self, method: str, params: dict | None = None) -> dict:
        """Send a CDP command and block until its response, buffering events."""
        self._next_id += 1
        msg_id = self._next_id
        self.ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        while True:
            raw = json.loads(self.ws.recv(timeout=30))
            if raw.get("id") == msg_id:
                return raw.get("result", {})
            if "method" in raw:
                self.events.append(raw)

    def drain(self, seconds: float) -> None:
        """Collect events for a fixed window (lets htmx/Alpine settle)."""
        deadline = time.monotonic() + seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            try:
                raw = json.loads(self.ws.recv(timeout=remaining))
            except TimeoutError:
                return
            if "method" in raw:
                self.events.append(raw)

    def take_events(self) -> list[dict]:
        taken, self.events = self.events, []
        return taken


def login(base_url: str, username: str, password: str) -> dict[str, str]:
    """Log in through the real /login/submit flow; return the session cookie jar.

    Uses httpx (cookie jar replays across requests — curl does not).
    """
    with httpx.Client(base_url=base_url, follow_redirects=True) as client:
        login_page = client.get("/login")
        login_page.raise_for_status()
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', login_page.text)
        if not match:
            match = re.search(r'value="([^"]+)"\s+name="csrf_token"', login_page.text)
        if not match:
            raise RuntimeError("csrf_token input not found on /login")
        response = client.post(
            "/login/submit",
            data={"username": username, "password": password, "csrf_token": match.group(1)},
        )
        response.raise_for_status()
        cookies = dict(client.cookies)
        # A FAILED login still leaves csrf_token in the jar (set on GET /login),
        # so a non-empty check would pass unauthenticated. Require the actual
        # session cookie.
        if "skuel_session" not in cookies:
            raise RuntimeError(
                "login did not create a skuel_session cookie — bad credentials or login failed"
            )
        return cookies


def launch_chrome(user_data_dir: str) -> tuple[subprocess.Popen[bytes], int]:
    """Launch headless Chrome; return the process and its DevTools port."""
    proc = subprocess.Popen(
        [
            CHROME_BINARY,
            "--headless=new",
            "--remote-debugging-port=0",
            f"--user-data-dir={user_data_dir}",
            "--no-first-run",
            "--disable-extensions",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    port_file = Path(user_data_dir) / "DevToolsActivePort"
    for _ in range(100):
        if port_file.exists():
            first_line = port_file.read_text().splitlines()[0].strip()
            if first_line:
                return proc, int(first_line)
        time.sleep(0.1)
    proc.kill()
    raise RuntimeError("Chrome did not write DevToolsActivePort within 10s")


def page_ws_url(devtools_port: int) -> str:
    with urllib.request.urlopen(f"http://localhost:{devtools_port}/json/list") as response:
        targets = json.loads(response.read())
    for target in targets:
        if target.get("type") == "page":
            return str(target["webSocketDebuggerUrl"])
    raise RuntimeError("no page target exposed by Chrome DevTools")


def format_exception(params: dict) -> str:
    details = params.get("exceptionDetails", {})
    exc = details.get("exception", {})
    description = exc.get("description") or details.get("text", "unknown exception")
    url = details.get("url", "?")
    line = details.get("lineNumber", "?")
    return f"{url}:{line} — {description.splitlines()[0]}"


def format_console(params: dict) -> str:
    parts = []
    for arg in params.get("args", []):
        value = arg.get("value")
        if value is not None:
            parts.append(str(value))
        elif arg.get("description"):
            parts.append(str(arg["description"]).splitlines()[0])
    return " ".join(parts) or "<no message>"


def check_render_shape(session: CdpSession, result: PageResult) -> None:
    """Flag pages that served 200 without actually rendering a page.

    A handler that returns an un-awaited coroutine (e.g. ``return helper(...)``
    where ``helper`` is async and the ``await`` was dropped) serves a 200
    text/html body of ``<coroutine object ...>`` — zero JS errors, so the
    event-based checks pass. Caught live on /notifications (2026-07-04)."""
    evaluated = session.send(
        "Runtime.evaluate",
        {
            "expression": (
                "JSON.stringify({title: document.title, "
                "snippet: (document.body && document.body.innerText || '').slice(0, 200)})"
            ),
            "returnByValue": True,
        },
    )
    raw = evaluated.get("result", {}).get("value")
    if not raw:
        result.render_errors.append("Runtime.evaluate returned nothing — page state unreadable")
        return
    shape = json.loads(raw)
    if "<coroutine object" in shape["snippet"]:
        result.render_errors.append(f"un-awaited coroutine served as page body: {shape['snippet']}")
    elif not shape["title"]:
        result.render_errors.append("empty <title> — page did not render SKUEL chrome")


def collect_page(session: CdpSession, base_url: str, page: str, verbose: bool) -> PageResult:
    result = PageResult(page=page)
    session.take_events()  # discard leftovers from the previous page
    session.send("Page.navigate", {"url": f"{base_url}{page}"})
    session.drain(SETTLE_SECONDS)
    check_render_shape(session, result)
    for event in session.take_events():
        method = event["method"]
        params = event.get("params", {})
        if method == "Runtime.exceptionThrown":
            detail = format_exception(params)
            result.exceptions.append(detail)
            if verbose:
                print(f"    [exception] {json.dumps(params, indent=2)[:3000]}")
        elif method == "Runtime.consoleAPICalled" and params.get("type") == "error":
            detail = format_console(params)
            result.console_errors.append(detail)
            if verbose:
                print(f"    [console.error] {json.dumps(params, indent=2)[:3000]}")
    return result


def run(base_url: str, username: str, pages: list[str], verbose: bool) -> int:
    password = get_credential("TEST_USER_PASSWORD")
    if not password:
        print("FAIL: TEST_USER_PASSWORD not available via get_credential()")
        return 2

    print(f"Logging in as {username} at {base_url} ...")
    cookies = login(base_url, username, password)
    print(f"Login OK ({len(cookies)} cookie(s) in jar)")

    user_data_dir = tempfile.mkdtemp(prefix="authed_smoke_chrome_")
    proc, devtools_port = launch_chrome(user_data_dir)
    results: list[PageResult] = []
    try:
        with connect(page_ws_url(devtools_port), max_size=32 * 1024 * 1024) as ws:
            session = CdpSession(ws)
            session.send("Network.enable")
            session.send("Runtime.enable")
            session.send("Page.enable")
            for name, value in cookies.items():
                session.send("Network.setCookie", {"name": name, "value": value, "url": base_url})
            for page in pages:
                print(f"  → {page}")
                results.append(collect_page(session, base_url, page, verbose))
    finally:
        proc.kill()
        proc.wait()
        shutil.rmtree(user_data_dir, ignore_errors=True)

    print()
    failed = False
    for result in results:
        status = "OK" if result.is_clean else "FAIL"
        print(
            f"[{status}] {result.page}: {len(result.exceptions)} exception(s), "
            f"{len(result.console_errors)} console error(s), "
            f"{len(result.render_errors)} render error(s)"
        )
        for detail in result.exceptions:
            print(f"    exception: {detail}")
        for detail in result.console_errors:
            print(f"    console.error: {detail}")
        for detail in result.render_errors:
            print(f"    render: {detail}")
        failed = failed or not result.is_clean

    print()
    if failed:
        print("AUTHED SMOKE: FAIL — JS or render errors present on authed pages")
        return 1
    print(f"AUTHED SMOKE: PASS — {len(results)} pages, zero JS or render errors")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://localhost:8001")
    parser.add_argument("--username", default="linguistic76")
    parser.add_argument(
        "--pages",
        nargs="+",
        default=DEFAULT_PAGES,
        help=f"Pages to check (default: {' '.join(DEFAULT_PAGES)})",
    )
    parser.add_argument("--verbose", action="store_true", help="Dump raw CDP event payloads")
    args = parser.parse_args()
    return run(args.base_url, args.username, args.pages, args.verbose)


if __name__ == "__main__":
    sys.exit(main())
