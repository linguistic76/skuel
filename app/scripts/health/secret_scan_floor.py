#!/usr/bin/env python3
"""
False-positive floor for the commit-time secret scan, measured over the real corpus.

Runs ``scripts/git-hooks/secret-scan.sh`` against **every tracked text file** as if
each line were newly added, and fails if it reports anything. Nothing in the
repository is a credential, so any finding here is a false positive.

Why a corpus sweep and not more unit tests
------------------------------------------
``tests/unit/scripts/test_secret_scan.py`` has 150+ cases and the scan still shipped
two false-positive regressions that only this sweep caught. Both slipped for the same
reason: every fixture in the file shared a property that dodged the code path under
test.

    a POSIX bracket bug (``[[:space:],}\\]]`` — a backslash is not an escape inside a
    bracket expression, so the value-terminator read as "terminator followed by a
    literal ]") reported ``.env.example``'s commented ``ANTHROPIC_API_KEY`` line.
    Invisible to the unit tests because every interpolation negative in them either
    ended the line (satisfying ``$``) or sat under the length floor, so none of them
    exercised the terminator at all.

Fixtures are written by the same person, at the same moment, with the same idea of
what the input looks like — so they share blind spots by construction. The corpus does
not: it holds env templates, compose interpolations, docs placeholders, lockfile
digests and dict literals that nobody wrote as test data.

This matters more than a cosmetic false positive. A scan that blocks a legitimate
commit gets bypassed with ``SKUEL_ALLOW_SECRETS=1``, and a fence everyone routes
around has stopped being a fence.

Not vacuous
-----------
A sweep that reports "clean" because the scanner is broken is worse than no sweep, so
this plants a synthetic credential and refuses to pass unless the scan catches it.
That is the same fail-closed rule the scan itself follows: a checker with nothing to
check for must never report success.

See: app/scripts/git-hooks/README.md
"""

from __future__ import annotations

import secrets
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent))

from core.utils.terminal_colors import Colors

APP_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = APP_ROOT.parent
SCAN = APP_ROOT / "scripts" / "git-hooks" / "secret-scan.sh"


def _chunked(items: list[str], size: int = 400) -> list[list[str]]:
    """Argument lists in batches, so a growing repo cannot hit ARG_MAX (E2BIG).

    2948 paths fit comfortably today; batching removes the failure mode rather than
    waiting to detect it, which matters for a check whose whole job is not to pass
    when it has not looked.
    """
    return [items[i : i + size] for i in range(0, len(items), size)]


def _fail(message: str) -> None:
    """Abort loudly. Every abort here is a refusal to report a verdict.

    A corpus check that cannot read the corpus has not found "no problems" — it has
    found nothing, and saying so is the only honest outcome.
    """
    print(f"{Colors.RED}{Colors.BOLD}✗ {message}{Colors.RESET}")
    raise SystemExit(1)


def tracked_text_files() -> list[str]:
    """Every tracked file git considers text, repo-root-relative.

    ``grep -Il ''`` is the text/binary discriminator — a binary file would feed the
    scan bytes that mean nothing and can only produce noise.
    """
    listed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split("\0")
    paths = [p for p in listed if p]
    if not paths:
        _fail("git ls-files returned nothing — refusing to report a clean corpus")

    text: list[str] = []
    for batch in _chunked(paths):
        result = subprocess.run(
            ["grep", "-Il", "", *batch],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        # 0 = some file matched, 1 = none did (an all-binary batch). Both are answers.
        # 2 is grep failing, and treating that as "no text files" is how a broken
        # sweep reports success.
        if result.returncode not in (0, 1):
            _fail(
                f"grep failed (exit {result.returncode}) while selecting text files:\n"
                f"  {result.stderr.strip()}"
            )
        text.extend(line for line in result.stdout.splitlines() if line)

    if not text:
        _fail("no tracked text files found — refusing to report a clean corpus")
    return text


def as_added_diff(paths: list[str]) -> str:
    """Every line of every file, prefixed as a diff addition."""
    if not paths:
        _fail("asked to build a diff from no files — refusing to report a clean corpus")

    chunks: list[str] = []
    for batch in _chunked(paths):
        result = subprocess.run(
            ["sed", "s/^/+/", *batch],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            errors="replace",
        )
        if result.returncode != 0:
            _fail(
                f"sed failed (exit {result.returncode}) while building the corpus diff:\n"
                f"  {result.stderr.strip()}"
            )
        chunks.append(result.stdout)

    diff = "".join(chunks)
    # A non-empty file list that produces no lines means the read failed somewhere
    # quiet — an empty diff scans clean, which is the false pass this check exists
    # to make impossible.
    if not diff.strip():
        _fail(f"{len(paths)} files produced an empty diff — the corpus was not read")
    return diff


def run_scan(diff: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCAN), "the tracked corpus"],
        input=diff,
        capture_output=True,
        text=True,
        check=False,
        errors="replace",
    )


def main() -> int:
    if not SCAN.is_file():
        print(f"{Colors.RED}✗ secret-scan.sh not found at {SCAN}{Colors.RESET}")
        return 1

    # Vacuity probe first, on a single line rather than the corpus: if the scanner
    # cannot find a planted credential, its verdict on 2900 files means nothing —
    # and proving it is live costs nothing.
    probe = run_scan(f"+NEO4J_PASSWORD={secrets.token_urlsafe(32)}\n")
    if probe.returncode == 0:
        print(
            f"{Colors.RED}{Colors.BOLD}✗ The scan did not catch a planted credential{Colors.RESET}"
        )
        print(
            f"{Colors.YELLOW}  A sweep that reports clean because the scanner is broken "
            f"is worse than no sweep. Fix the scan before trusting this check.{Colors.RESET}"
        )
        return 1

    paths = tracked_text_files()
    result = run_scan(as_added_diff(paths))
    if result.returncode == 0:
        print(
            f"{Colors.GREEN}✓ Secret-scan floor: {len(paths)} tracked text files, "
            f"no false positives{Colors.RESET}"
        )
        return 0

    print(f"{Colors.RED}{Colors.BOLD}✗ The secret scan fires on tracked content{Colors.RESET}\n")
    for line in result.stderr.splitlines():
        print(f"  {line}")
    print()
    print(
        f"{Colors.YELLOW}Nothing tracked is a credential, so each of these is a false "
        f"positive.{Colors.RESET}"
    )
    print(
        f"{Colors.YELLOW}A scan that blocks a legitimate commit gets bypassed with "
        f"SKUEL_ALLOW_SECRETS=1, and a fence everyone routes around is not a "
        f"fence — fix the pattern, or make the value a recognised placeholder "
        f"(empty, `your-`-prefixed, angle-bracketed, or under 20 characters).{Colors.RESET}"
    )
    print(f"{Colors.YELLOW}See: app/scripts/git-hooks/README.md § The secret scan{Colors.RESET}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
