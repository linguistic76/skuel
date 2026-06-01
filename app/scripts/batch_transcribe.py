#!/usr/bin/env python3
"""
Batch Transcription CLI
========================

Command-line interface for batch audio transcription and LLM processing.

Usage:
    uv run python scripts/batch_transcribe.py --preview                              # list files
    uv run python scripts/batch_transcribe.py                                        # transcribe only
    uv run python scripts/batch_transcribe.py --process --mode activity_tracking     # transcribe + process
    uv run python scripts/batch_transcribe.py --process-only --input-dir data/je_outputs  # process existing .txt

Calls the batch API endpoints on localhost:8000.
"""

import argparse
import json
import sys

import httpx

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_INPUT_DIR = "data/je_inputs"
DEFAULT_OUTPUT_DIR = "data/je_outputs"


def _extract_cookie_value(cookie_header: str, name: str) -> str | None:
    """Pull a single cookie value out of a 'k=v; k2=v2' Cookie header string."""
    for part in cookie_header.split(";"):
        key, _, value = part.strip().partition("=")
        if key == name:
            return value or None
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch transcription and LLM processing")
    parser.add_argument("--preview", action="store_true", help="Preview files without transcribing")
    parser.add_argument("--process", action="store_true", help="Transcribe + process (combined)")
    parser.add_argument(
        "--process-only", action="store_true", help="Process existing .txt files only"
    )
    parser.add_argument("--input-dir", default=DEFAULT_INPUT_DIR, help="Input directory")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Output directory")
    parser.add_argument(
        "--mode",
        default=None,
        help="Enrichment mode: activity_tracking|idea_articulation|critical_thinking",
    )
    parser.add_argument("--model", default="gpt-4o-mini", help="LLM model (default: gpt-4o-mini)")
    parser.add_argument("--custom-instructions", default=None, help="Custom instruction text")
    parser.add_argument("--no-skip", action="store_true", help="Re-process existing files")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Server base URL")
    parser.add_argument(
        "--cookie",
        default=None,
        help="Auth cookies (name=value; ...). Include csrf_token=... for CSRF-protected endpoints.",
    )

    args = parser.parse_args()

    headers: dict[str, str] = {}
    if args.cookie:
        headers["Cookie"] = args.cookie
        # Double-submit CSRF: echo the csrf_token cookie as the X-CSRF-Token
        # header so CSRF-protected endpoints (e.g. /api/journals/batch-transcribe)
        # accept this programmatic caller. Pass a --cookie value that includes
        # csrf_token=... copied from an authenticated browser session. Interim
        # until bearer-token auth lands — docs/roadmap/programmatic-client-auth-csrf.md.
        csrf = _extract_cookie_value(args.cookie, "csrf_token")
        if csrf:
            headers["X-CSRF-Token"] = csrf

    skip_existing = not args.no_skip

    with httpx.Client(base_url=args.base_url, headers=headers, timeout=600.0) as client:
        if args.preview:
            _preview(client, args.input_dir, args.output_dir)
        elif args.process_only:
            _process_only(client, args)
        elif args.process:
            _combined(client, args, skip_existing)
        else:
            _transcribe_only(client, args.input_dir, args.output_dir, skip_existing)


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


def _transcribe_only(
    client: httpx.Client, input_dir: str, output_dir: str, skip_existing: bool
) -> None:
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


def _process_only(client: httpx.Client, args: argparse.Namespace) -> None:
    """Process existing .txt files through LLM."""
    print(f"Processing: {args.input_dir} (mode={args.mode or 'default'}, model={args.model})")
    resp = client.post(
        "/api/journals/batch-process",
        json={
            "input_dir": args.input_dir,
            "output_dir": args.output_dir,
            "enrichment_mode": args.mode,
            "custom_instructions": args.custom_instructions,
            "model": args.model,
            "skip_existing": not args.no_skip,
        },
    )
    _handle_response(resp, "Processing")
    _print_batch_result(resp.json())


def _combined(client: httpx.Client, args: argparse.Namespace, skip_existing: bool) -> None:
    """Combined transcription + processing."""
    print(
        f"Combined pipeline: {args.input_dir} → {args.output_dir} "
        f"(mode={args.mode or 'default'}, model={args.model})"
    )
    resp = client.post(
        "/api/journals/batch-process",
        json={
            "combined": True,
            "audio_dir": args.input_dir,
            "output_dir": args.output_dir,
            "enrichment_mode": args.mode,
            "custom_instructions": args.custom_instructions,
            "model": args.model,
            "skip_existing": skip_existing,
        },
    )
    _handle_response(resp, "Combined pipeline")

    data = resp.json()
    tier1 = data.get("transcription", {})
    tier2 = data.get("processing", {})
    print("\n--- Tier 1: Transcription ---")
    print(
        f"  Total: {tier1.get('total', 0)}, Succeeded: {tier1.get('succeeded', 0)}, "
        f"Failed: {tier1.get('failed', 0)}, Skipped: {tier1.get('skipped', 0)}"
    )
    print("\n--- Tier 2: Processing ---")
    print(
        f"  Total: {tier2.get('total', 0)}, Succeeded: {tier2.get('succeeded', 0)}, "
        f"Failed: {tier2.get('failed', 0)}, Skipped: {tier2.get('skipped', 0)}"
    )


def _handle_response(resp: httpx.Response, operation: str) -> None:
    """Check response status and exit on error."""
    if resp.status_code != 200:
        print(f"{operation} failed (HTTP {resp.status_code}):")
        try:
            print(json.dumps(resp.json(), indent=2))
        except Exception:
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
            elif "output_chars" in r:
                extra = f" ({r['output_chars']} chars)"
            print(f"  {r['name']}{extra}")


if __name__ == "__main__":
    main()
