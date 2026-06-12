#!/usr/bin/env python3
"""
Vault watcher — Obsidian Headless Sync roadmap Phase 2 (automated trigger).

Watches the content vault for file changes and triggers SKUEL's incremental
ingestion API on the running app. Polling-based (no inotify dependency), with
a quiet-period debounce so Obsidian Sync batch deliveries trigger one ingest,
not one per file. Incremental mode (SHA-256 skip tracking in Neo4j) makes
each trigger cheap even when nothing changed.

Two run shapes:
- Continuous (default): poll every --interval seconds, ingest after --debounce
  seconds of quiet following a detected change. For dev machines and the
  Phase 3 systemd service.
- One-shot (--once): single incremental ingest, then exit. For cron jobs and
  systemd timers — the roadmap's "simpler, slightly less responsive" variant.

The watcher goes through the HTTP API (not direct service composition) so
ingestion always runs on the app's fully-wired UnifiedIngestionService —
embeddings, event bus, UserEntry routing — one path, no divergence.

Auth: the ingestion endpoints are admin-only. Set SKUEL_VAULT_WATCH_USERNAME
and SKUEL_VAULT_WATCH_PASSWORD (an ADMIN account; password resolved via the
credential store with env fallback). Sessions are re-established on expiry.

Usage:
    uv run python scripts/vault_watch.py                 # watch INGESTION_PATH
    uv run python scripts/vault_watch.py --once          # single ingest (cron)
    uv run python scripts/vault_watch.py --path /opt/skuel/vault --mode smart

See: docs/roadmap/obsidian-headless-sync.md (Phase 2)
"""

import argparse
import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

ENV_FILE = Path(__file__).parent.parent / ".env"
load_dotenv(ENV_FILE, override=False)

from core.config.credential_store import get_credential  # noqa: E402

DEFAULT_VAULT = os.getenv("INGESTION_PATH", "/home/mike/0bsidian/0vault")
DEFAULT_BASE_URL = os.getenv("SKUEL_BASE_URL", "http://localhost:8000")
WATCHED_SUFFIXES = (".md", ".yaml", ".yml")

CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"


def scan_signature(vault: Path) -> frozenset[tuple[str, int, int]]:
    """Cheap change signature: (path, mtime_ns, size) for every watched file.

    Catches creates, edits, and deletes (a vanished file drops out of the set).
    Files that disappear mid-scan (Obsidian Sync mid-write) are skipped; the
    next poll picks them up.
    """
    entries: set[tuple[str, int, int]] = set()
    for suffix in WATCHED_SUFFIXES:
        for file_path in vault.rglob(f"*{suffix}"):
            try:
                stat = file_path.stat()
            except OSError:
                continue
            entries.add((str(file_path), stat.st_mtime_ns, stat.st_size))
    return frozenset(entries)


class SkuelSession:
    """Authenticated HTTP session against the running SKUEL app."""

    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.client = httpx.Client(base_url=self.base_url, timeout=600.0)

    def login(self) -> None:
        """GET /login mints the CSRF cookie; POST /login/submit sets the session.

        Success is the 303 redirect — a 200 means the login page came back
        with an error message.
        """
        self.client.get("/login")
        csrf = self.client.cookies.get(CSRF_COOKIE)
        if not csrf:
            raise RuntimeError("No CSRF cookie minted by /login — is the app running?")
        response = self.client.post(
            "/login/submit",
            data={"username": self.username, "password": self.password, "csrf_token": csrf},
        )
        if response.status_code != 303:
            raise RuntimeError(
                f"Login failed for {self.username!r} (HTTP {response.status_code}). "
                "Check SKUEL_VAULT_WATCH_USERNAME / SKUEL_VAULT_WATCH_PASSWORD "
                "and that the account has ADMIN role."
            )

    def ingest_directory(self, vault: Path, mode: str, pattern: str) -> dict:
        """POST /api/ingest/directory, re-authenticating once on session expiry."""
        body = {"directory": str(vault), "pattern": pattern, "ingestion_mode": mode}
        for attempt in (1, 2):
            csrf = self.client.cookies.get(CSRF_COOKIE) or ""
            response = self.client.post(
                "/api/ingest/directory", json=body, headers={CSRF_HEADER: csrf}
            )
            if response.status_code in (401, 403) and attempt == 1:
                print("  Session expired — re-authenticating...")
                self.login()
                continue
            response.raise_for_status()
            return response.json()
        raise RuntimeError("Unreachable")  # loop always returns or raises

    def close(self) -> None:
        self.client.close()


def print_stats(payload: dict) -> None:
    skipped = payload.get("files_skipped")
    summary = (
        f"  ✓ {payload.get('total_files', 0)} files: "
        f"{payload.get('successful', 0)} ok, {payload.get('failed', 0)} failed"
    )
    if skipped is not None:
        summary += f", {skipped} skipped unchanged ({payload.get('skip_efficiency', 0):.0f}%)"
    summary += f" in {payload.get('duration_seconds', 0):.1f}s"
    print(summary)
    for err in (payload.get("errors") or [])[:5]:
        print(f"    ✗ {err}")


def run_ingest(session: SkuelSession, vault: Path, mode: str, pattern: str) -> bool:
    """One ingestion trigger. Returns True on success."""
    try:
        payload = session.ingest_directory(vault, mode, pattern)
    except (httpx.HTTPError, RuntimeError) as exc:
        print(f"  ✗ Ingestion trigger failed: {exc}")
        return False
    print_stats(payload)
    return True


def watch(
    session: SkuelSession,
    vault: Path,
    mode: str,
    pattern: str,
    interval: float,
    debounce: float,
) -> None:
    """Poll for changes; ingest after the vault has been quiet for `debounce` seconds.

    The synced baseline advances only after a SUCCESSFUL ingest — a transient
    trigger failure (app restart, Neo4j blip) leaves the baseline stale, so the
    next poll retries the same changes instead of silently treating them as synced.
    """
    print(f"Watching {vault} (poll {interval:.0f}s, debounce {debounce:.0f}s, mode={mode})")
    print("Initial sync...")
    synced: frozenset[tuple[str, int, int]] | None = None
    if run_ingest(session, vault, mode, pattern):
        synced = scan_signature(vault)

    while True:
        time.sleep(interval)
        current = scan_signature(vault)
        if current == synced:
            continue

        # Change detected (or a previous ingest failed) — wait for a full quiet
        # period (Obsidian Sync may still be delivering a batch), then ingest
        # whatever settled.
        print(f"[{time.strftime('%H:%M:%S')}] Change detected — debouncing...")
        while True:
            time.sleep(debounce)
            settled = scan_signature(vault)
            if settled == current:
                break
            current = settled

        if run_ingest(session, vault, mode, pattern):
            synced = settled


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--path", default=DEFAULT_VAULT, help="Vault directory to watch")
    parser.add_argument("--url", default=DEFAULT_BASE_URL, help="SKUEL app base URL")
    parser.add_argument(
        "--mode",
        default="incremental",
        choices=("incremental", "smart", "full"),
        help="Ingestion mode (default: incremental)",
    )
    parser.add_argument("--pattern", default="*", help="File glob pattern (default: *)")
    parser.add_argument(
        "--interval", type=float, default=10.0, help="Poll interval seconds (default: 10)"
    )
    parser.add_argument(
        "--debounce", type=float, default=5.0, help="Quiet period before ingest (default: 5)"
    )
    parser.add_argument(
        "--once", action="store_true", help="Single incremental ingest, then exit (cron mode)"
    )
    args = parser.parse_args()

    vault = Path(args.path).resolve()
    if not vault.is_dir():
        print(f"✗ Vault directory not found: {vault}")
        return 1

    username = os.getenv("SKUEL_VAULT_WATCH_USERNAME")
    password = get_credential("SKUEL_VAULT_WATCH_PASSWORD", fallback_to_env=True)
    if not username or not password:
        print("✗ Set SKUEL_VAULT_WATCH_USERNAME and SKUEL_VAULT_WATCH_PASSWORD (ADMIN account)")
        return 1

    session = SkuelSession(args.url, username, password)
    try:
        session.login()
        print(f"✓ Authenticated against {args.url} as {username}")
        if args.once:
            return 0 if run_ingest(session, vault, args.mode, args.pattern) else 1
        watch(session, vault, args.mode, args.pattern, args.interval, args.debounce)
        return 0
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0
    except (httpx.HTTPError, RuntimeError) as exc:
        print(f"✗ {exc}")
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
