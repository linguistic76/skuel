#!/usr/bin/env python3
"""
ShellCheck over every tracked shell script (quality check 9).

Single source of truth for shell-script discovery — both `./dev quality`
(scripts/run_quality_checks.py, check 9) and the CI lint job run this script,
so the two gates can never drift on which files are covered.

Discovery: `git ls-files`, keeping paths that either end in `.sh` or open with
a shell shebang (sh/bash/dash/ksh, `env` indirection included) — the repo's
load-bearing shell includes extensionless programs (`dev`, the git hooks,
`scripts/dev/with-secrets`).

Severity gate: --severity=warning. The audit that introduced this check
(PR #976) verified the info-level notes are intentional design or style;
warnings and errors are real lint and fail the check.
"""

import subprocess
import sys
from pathlib import Path

APP_ROOT = Path(__file__).parent.parent

_SHELL_INTERPRETERS = {b"sh", b"bash", b"dash", b"ksh"}


def _has_shell_shebang(file_path: Path) -> bool:
    """True when the file's first line is a shebang naming a POSIX-family shell."""
    try:
        with file_path.open("rb") as handle:
            first_line = handle.readline(200)
    except OSError:
        return False
    if not first_line.startswith(b"#!"):
        return False
    tokens = first_line[2:].split()
    if not tokens:
        return False
    interpreter = tokens[0].rsplit(b"/", 1)[-1]
    if interpreter == b"env" and len(tokens) > 1:
        interpreter = tokens[1]
    return interpreter in _SHELL_INTERPRETERS


def discover_tracked_shell_scripts() -> list[str]:
    """All git-tracked shell scripts under app/, by extension or shebang."""
    tracked = subprocess.run(
        ["git", "ls-files"],
        capture_output=True,
        text=True,
        cwd=APP_ROOT,
        check=True,
    ).stdout.splitlines()
    return [path for path in tracked if path.endswith(".sh") or _has_shell_shebang(APP_ROOT / path)]


def main() -> int:
    scripts = discover_tracked_shell_scripts()
    if not scripts:
        print("No tracked shell scripts to check.")
        return 0
    print(f"ShellCheck (severity=warning) over {len(scripts)} tracked shell scripts:")
    for path in scripts:
        print(f"  {path}")
    result = subprocess.run(["shellcheck", "--severity=warning", *scripts], cwd=APP_ROOT)
    if result.returncode == 0:
        print("✅ ShellCheck clean")
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
