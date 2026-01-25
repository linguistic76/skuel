#!/usr/bin/env python3
"""
Code Quality Checks Runner
===========================

Runs all code quality checks in sequence:
1. Ruff formatting check
2. Ruff linting
3. SKUEL linting (consolidated architecture + patterns)
4. Cypher query validation
5. MyPy type checking (optional)

Usage:
    poetry run python scripts/run_quality_checks.py
    poetry run python scripts/run_quality_checks.py --fix  # Auto-fix issues
    poetry run python scripts/run_quality_checks.py --fast  # Skip slow checks
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
            ["poetry", "run", "ruff", "format"],
            "Ruff Format (Auto-fix)",
            check=False,
        ):
            all_passed = False
    else:
        # Check only
        if not run_command(
            ["poetry", "run", "ruff", "format", "--check"],
            "Ruff Format Check",
            check=False,
        ):
            print(
                "\n💡 Run with --fix to auto-format: poetry run python scripts/run_quality_checks.py --fix"
            )
            all_passed = False

    if args.format_only:
        return 0 if all_passed else 1

    # 2. Ruff Linting
    if args.fix:
        if not run_command(
            ["poetry", "run", "ruff", "check", "--fix"],
            "Ruff Lint (Auto-fix)",
            check=False,
        ):
            all_passed = False
    else:
        if not run_command(
            ["poetry", "run", "ruff", "check"],
            "Ruff Lint Check",
            check=False,
        ):
            all_passed = False

    # 3. SKUEL Linting (consolidated architecture + patterns)
    if not run_command(
        ["poetry", "run", "python", "scripts/lint_skuel.py"],
        "SKUEL Linting",
        check=False,
    ):
        all_passed = False

    # 4. Cypher Query Validation (STRICT MODE - blocks on errors)
    if not run_command(
        ["poetry", "run", "python", "scripts/cypher_linter.py", "--errors-only", "--strict"],
        "Cypher Query Validation (Strict Mode)",
        check=False,
    ):
        all_passed = False

    # 5. Type Checking (optional - slow)
    if not args.fast:
        print("\n💡 Running type checks (slow). Use --fast to skip.")

        # MyPy
        if not run_command(
            ["poetry", "run", "mypy", "."],
            "MyPy Type Checking",
            check=False,
        ):
            print("⚠️  MyPy found type issues (not blocking)")
            # Don't fail on MyPy - we have ~2200 known issues

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
        print("   poetry run python scripts/run_quality_checks.py --fix")
        return 1


if __name__ == "__main__":
    sys.exit(main())
