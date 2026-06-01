#!/usr/bin/env python3
"""
Batch Transcription CLI
========================

Command-line interface for batch audio→text transcription. Transcribes every
audio file in a server-side directory via the admin batch endpoint.

Usage:
    uv run python scripts/batch_transcribe.py --preview                 # list audio files
    uv run python scripts/batch_transcribe.py                           # transcribe to .txt
    uv run python scripts/batch_transcribe.py --cookie "session=..."    # authenticated run

Calls POST /api/journals/batch-transcribe (admin-only, CSRF-protected). The
admin UI for the same operation is at /admin/batch-transcribe. CSRF is handled
transparently — the client obtains a csrf_token and echoes it, so a session
cookie alone is enough.

LLM txt→md processing (the former --process/--process-only/--combined paths)
was retired with ADR-054 — it now lives in UserEntryProcessingService.
"""

import argparse
import json
import sys
from urllib.parse import urlparse

import httpx

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_INPUT_DIR = "data/je_inputs"
DEFAULT_OUTPUT_DIR = "data/je_outputs"


def _seed_cookies(client: httpx.Client, cookie_header: str, host: str) -> None:
    """Load 'k=v; k2=v2' pairs from --cookie into the client's cookie jar."""
    for part in cookie_header.split(";"):
        key, _, value = part.strip().partition("=")
        if key:
            client.cookies.set(key, value, domain=host)


def _ensure_csrf_token(client: httpx.Client) -> str | None:
    """Obtain a csrf_token for double-submit CSRF.

    CSRFMiddleware mints a csrf_token cookie on any response when the request
    lacks one, so a cheap GET yields a usable token — keeping the session-only
    CLI invocation working against the @csrf_protected endpoint.
    """
    token = client.cookies.get("csrf_token")
    if token:
        return token
    try:
        client.get("/")
    except httpx.HTTPError:
        return None
    return client.cookies.get("csrf_token")


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch audio→text transcription")
    parser.add_argument("--preview", action="store_true", help="Preview files without transcribing")
    parser.add_argument("--input-dir", default=DEFAULT_INPUT_DIR, help="Input directory")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Output directory")
    parser.add_argument("--no-skip", action="store_true", help="Re-transcribe existing files")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Server base URL")
    parser.add_argument("--cookie", default=None, help="Auth cookies (name=value; ...)")

    args = parser.parse_args()

    host = urlparse(args.base_url).hostname or "localhost"
    skip_existing = not args.no_skip

    with httpx.Client(base_url=args.base_url, timeout=600.0) as client:
        if args.cookie:
            _seed_cookies(client, args.cookie, host)
        token = _ensure_csrf_token(client)
        if token:
            client.headers["X-CSRF-Token"] = token

        if args.preview:
            _preview(client, args.input_dir, args.output_dir)
        else:
            _transcribe(client, args.input_dir, args.output_dir, skip_existing)


def _preview(client: httpx.Client, input_dir: str, output_dir: str) -> None:
    """Preview files to transcribe."""
    resp = client.post(
        "/api/journals/batch-transcribe",
        json={"input_dir": input_dir, "output_dir": output_dir, "preview_only": True},
    )
    _handle_response(resp, "Preview")

    data = resp.json()
    print(f"\nFiles to transcribe: {data.get('total_files', 0)}")
    print(f"Total size: {data.get('total_size_mb', 0):.2f} MB")

    already = data.get("already_transcribed", [])
    if already:
        print(f"Already transcribed: {len(already)} ({', '.join(already)})")

    files = data.get("files", [])
    if files:
        print("\nAudio files:")
        for f in files:
            marker = " [done]" if f["name"] in already else ""
            print(f"  {f['name']} ({f['size_mb']:.2f} MB){marker}")


def _transcribe(client: httpx.Client, input_dir: str, output_dir: str, skip_existing: bool) -> None:
    """Transcribe audio files to .txt."""
    print(f"Transcribing: {input_dir} → {output_dir}")
    resp = client.post(
        "/api/journals/batch-transcribe",
        json={
            "input_dir": input_dir,
            "output_dir": output_dir,
            "skip_existing": skip_existing,
        },
    )
    _handle_response(resp, "Transcription")
    _print_batch_result(resp.json())


def _handle_response(resp: httpx.Response, operation: str) -> None:
    """Check response status and exit on error."""
    if resp.status_code != 200:
        print(f"{operation} failed (HTTP {resp.status_code}):")
        try:
            print(json.dumps(resp.json(), indent=2))
        except (httpx.DecodingError, ValueError):
            print(resp.text)
        sys.exit(1)


def _print_batch_result(data: dict) -> None:
    """Print batch result summary."""
    print(f"\nTotal: {data.get('total_files', 0)}")
    print(f"Succeeded: {data.get('succeeded', 0)}")
    print(f"Failed: {data.get('failed', 0)}")
    print(f"Skipped: {data.get('skipped', 0)}")

    errors = data.get("errors", [])
    if errors:
        print("\nErrors:")
        for e in errors:
            print(f"  {e['name']}: {e['error']}")

    results = data.get("results", [])
    successes = [r for r in results if r.get("status") == "success"]
    if successes:
        print("\nSuccessful:")
        for r in successes:
            extra = ""
            if "word_count" in r:
                extra = f" ({r['word_count']} words, confidence={r.get('confidence', 0):.2f})"
            print(f"  {r['name']}{extra}")


if __name__ == "__main__":
    main()
