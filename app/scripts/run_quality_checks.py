#!/usr/bin/env python3
"""
Code Quality Checks Runner
===========================

Runs all code quality checks in sequence:
1. Ruff formatting check
2. Ruff linting
3. SKUEL linting (consolidated architecture + patterns)
4. Cypher query validation
5. Route security audit (5b: raw headers audit)
6. Skills validation (6b: content-boundary guard)
7. Dead-code gate
8. Dependency CVE audit (osv-scanner: uv.lock + package-lock.json, all severities)
9. ShellCheck on tracked shell scripts (--severity=warning)
10. MyPy + Pyright type checking (optional)

`./dev typecheck-strict` runs only Pyright. See [tool.pyright] in pyproject.toml.

Usage:
    uv run python scripts/run_quality_checks.py
    uv run python scripts/run_quality_checks.py --fix  # Auto-fix issues
    uv run python scripts/run_quality_checks.py --fast  # Skip slow checks
"""

import subprocess
import sys
from pathlib import Path


def run_command(cmd: list[str], description: str, check: bool = True) -> bool:
    """
    Run a command and report results.

    Args:
        cmd: Command to run as list
        description: Human-readable description
        check: Whether to fail on non-zero exit code

    Returns:
        True if command succeeded, False otherwise
    """
    print(f"\n{'=' * 80}")
    print(f"{description}")
    print(f"{'=' * 80}\n")

    result = subprocess.run(cmd, cwd=Path(__file__).parent.parent)

    if result.returncode != 0:
        print(f"\n❌ {description} FAILED")
        if check:
            return False
    else:
        print(f"\n✅ {description} PASSED")

    return result.returncode == 0


def main():
    """Run all quality checks"""
    import argparse

    parser = argparse.ArgumentParser(description="Run SKUEL code quality checks")
    parser.add_argument("--fix", action="store_true", help="Auto-fix issues where possible")
    parser.add_argument("--fast", action="store_true", help="Skip slow checks (MyPy, Pyright)")
    parser.add_argument("--format-only", action="store_true", help="Only run formatting checks")
    args = parser.parse_args()

    print("SKUEL Code Quality Checks")
    print("=" * 80)

    all_passed = True

    # 1. Formatting
    if args.fix:
        # Auto-format
        if not run_command(
            ["uv", "run", "ruff", "format"],
            "Ruff Format (Auto-fix)",
            check=False,
        ):
            all_passed = False
    else:
        # Check only
        if not run_command(
            ["uv", "run", "ruff", "format", "--check"],
            "Ruff Format Check",
            check=False,
        ):
            print(
                "\n💡 Run with --fix to auto-format: uv run python scripts/run_quality_checks.py --fix"
            )
            all_passed = False

    if args.format_only:
        return 0 if all_passed else 1

    # 2. Ruff Linting
    if args.fix:
        if not run_command(
            ["uv", "run", "ruff", "check", "--fix"],
            "Ruff Lint (Auto-fix)",
            check=False,
        ):
            all_passed = False
    else:
        if not run_command(
            ["uv", "run", "ruff", "check"],
            "Ruff Lint Check",
            check=False,
        ):
            all_passed = False

    # 3. SKUEL Linting (consolidated architecture + patterns)
    # --strict: the WARNING tier is at zero codebase-wide (earned 2026-07);
    # strict mode keeps it there by failing quality on any new warning.
    if not run_command(
        ["uv", "run", "python", "scripts/lint_skuel.py", "--strict"],
        "SKUEL Linting",
        check=False,
    ):
        all_passed = False

    # 4. Cypher Query Validation (STRICT MODE - blocks on errors)
    if not run_command(
        ["uv", "run", "python", "scripts/cypher_linter.py", "--errors-only", "--strict"],
        "Cypher Query Validation (Strict Mode)",
        check=False,
    ):
        all_passed = False

    # 5. Route Security Audit (CSRF + auth on mutation handlers; fast AST scan)
    if not run_command(
        ["uv", "run", "python", "scripts/audit_route_security.py"],
        "Route Security Audit",
        check=False,
    ):
        all_passed = False

    # 5b. Raw Headers Audit (advisory: H1/H2 outside approved files; Html(Head()) is blocking)
    if not run_command(
        ["uv", "run", "python", "scripts/audit_raw_headers.py"],
        "Raw Headers Audit",
        check=False,
    ):
        all_passed = False

    # 5c. Font-Size Audit (strict: arbitrary text-[Npx] outside the ADR-084 exception ledger fails)
    if not run_command(
        ["uv", "run", "python", "scripts/audit_font_sizes.py", "--strict"],
        "Font-Size Audit",
        check=False,
    ):
        all_passed = False

    # 6. Skills Validation (.claude/skills/*/SKILL.md structure; fails on errors, not warnings)
    if not run_command(
        ["uv", "run", "python", "scripts/skills_validator.py"],
        "Skills Validation",
        check=False,
    ):
        all_passed = False

    # 6b. Content-boundary guard (no proprietary vault content tracked in this PUBLIC repo)
    if not run_command(
        ["uv", "run", "python", "scripts/audit_content_boundary.py"],
        "Content-Boundary Guard",
        check=False,
    ):
        all_passed = False

    # 6c. Untracked-reference guard (nothing tracked may cite the gitignored
    # plans/ scratch tier — a citation there is invisible to CI, absent from every
    # worktree, and rots silently; see CLAUDE.md § Documentation Architecture)
    if not run_command(
        ["uv", "run", "python", "scripts/audit_untracked_refs.py"],
        "Untracked-Reference Guard",
        check=False,
    ):
        all_passed = False

    # 7. Dead-code gate (PLANNED tier is the escape hatch for staged work)
    if not run_command(
        ["uv", "run", "python", "scripts/detect_bloat.py", "--check"],
        "Dead-Code Gate",
        check=False,
    ):
        all_passed = False

    # 8. Dependency CVE audit — osv-scanner over BOTH lockfiles (uv.lock +
    # package-lock.json), all severities, accepted findings dispositioned in
    # osv-scanner.toml (ADR-067 § 6e). The same script CI's dep_audit job and
    # the scheduled dependency-audit.yml run — one path, findings agree everywhere.
    if not run_command(
        ["bash", "scripts/audit_dependencies.sh"],
        "Dependency CVE Audit (osv-scanner, both ecosystems)",
        check=False,
    ):
        all_passed = False

    # 9. ShellCheck (tracked *.sh + shebang-detected extensionless scripts; warning
    # severity — style notes stay advisory). Discovery lives in shellcheck_tracked.py,
    # shared with the CI lint job so local and CI coverage cannot drift.
    if not run_command(
        ["uv", "run", "python", "scripts/shellcheck_tracked.py"],
        "ShellCheck (shell scripts)",
        check=False,
    ):
        all_passed = False

    # 10. Type Checking (optional - slow)
    if not args.fast:
        print("\n💡 Running type checks (slow). Use --fast to skip.")

        # MyPy
        if not run_command(
            ["uv", "run", "mypy", "."],
            "MyPy Type Checking",
            check=False,
        ):
            all_passed = False

        # Pyright — catches what mypy misses (attribute access on protocols,
        # possibly-unbound variables). Baseline = 0 errors as of 2026-05-18.
        # Config: [tool.pyright] in pyproject.toml.
        if not run_command(
            ["uv", "run", "pyright"],
            "Pyright Type Checking",
            check=False,
        ):
            all_passed = False

    # Summary
    print(f"\n{'=' * 80}")
    print("SUMMARY")
    print(f"{'=' * 80}\n")

    if all_passed:
        print("✅ All quality checks PASSED")
        return 0
    else:
        print("❌ Some quality checks FAILED")
        print("\n💡 Run with --fix to auto-fix issues:")
        print("   uv run python scripts/run_quality_checks.py --fix")
        return 1


if __name__ == "__main__":
    sys.exit(main())
