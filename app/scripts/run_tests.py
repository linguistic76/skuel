#!/usr/bin/env python3
"""
SKUEL Test Runner - Comprehensive test suite execution with multiple modes.

Usage:
    uv run python scripts/run_tests.py [mode] [options]

Modes:
    all           - Run everything under tests/ (needs Docker for integration/e2e)
    comprehensive - unit + integration [RECOMMENDED]
    integration   - Integration tests only (local Docker Neo4j)
    unit          - Unit tests only — fast CI tier (no Docker)
    quick         - Integration + the auth / error-handling unit files

Options:
    -v, --verbose     - Verbose output
    -q, --quiet       - Quiet output
    -k EXPRESSION     - Run tests matching expression
    --cov             - Include coverage report
    --tb=short        - Short traceback format
    --tb=no           - No traceback (fast failures)
    --markers         - Show available test markers
"""

import argparse
import subprocess
import sys
from pathlib import Path


class TestRunner:
    """Manages test execution with predefined configurations."""

    def __init__(self) -> None:
        self.project_root = Path(__file__).parent.parent
        self.tests_dir = self.project_root / "tests"

    def run_all(self, extra_args: list[str]) -> int:
        """Run the complete test suite (everything under tests/)."""
        print("🔍 Running COMPLETE test suite (all of tests/)")
        print("   unit + integration + e2e")
        print("   Integration/e2e need local Docker Neo4j (testcontainers)\n")

        cmd = ["uv", "run", "pytest", "tests/", "-v", *extra_args]
        return subprocess.run(cmd, cwd=self.project_root).returncode

    def run_comprehensive(self, extra_args: list[str]) -> int:
        """Run unit + integration (RECOMMENDED) — both CI tiers in one session.

        tests/unit/ is the fast CI tier: every Docker-free test lives there.
        Excludes only e2e (slow, worker lifecycle) and the uncollected
        benchmarks directory.
        """
        print("✅ Running COMPREHENSIVE test suite (recommended)")
        print("   unit + integration (both CI tiers)")
        print("   Excludes: e2e, benchmarks")
        print("   Integration needs local Docker Neo4j (testcontainers)\n")

        cmd = [
            "uv",
            "run",
            "pytest",
            "tests/",
            "--ignore=tests/e2e/",
            "--ignore=tests/benchmarks/",
            "-v",
            *extra_args,
        ]
        return subprocess.run(cmd, cwd=self.project_root).returncode

    def run_integration(self, extra_args: list[str]) -> int:
        """Run integration tests only (FAST)."""
        print("⚡ Running INTEGRATION tests only (fast)")
        print("   Tests: full tests/integration/ suite")
        print("   Expected: 100% passing")
        print("   Runtime: ~2-4 minutes")
        print("   Quality metric: Test pass rate (not coverage)")
        print("   Note: Use --cov flag if you want coverage reports\n")

        # Run without coverage by default (test pass rate is the quality metric)
        # Coverage percentage is misleading for integration tests because they test
        # specific functionality (CRUD, relationships) not broad coverage
        cmd = [
            "uv",
            "run",
            "pytest",
            "tests/integration/",
            "-v",
            "--override-ini=addopts=",  # Clear default addopts (no coverage by default)
            *extra_args,
        ]
        return subprocess.run(cmd, cwd=self.project_root).returncode

    def run_unit(self, extra_args: list[str]) -> int:
        """Run unit tests only — fast CI tier (no Docker needed)."""
        print("🧪 Running UNIT tests (fast CI tier)")
        print("   Mock-based; no Docker/Neo4j required\n")

        cmd = ["uv", "run", "pytest", "tests/unit/", "-v", *extra_args]
        return subprocess.run(cmd, cwd=self.project_root).returncode

    def run_quick(self, extra_args: list[str]) -> int:
        """Run the integration tier plus the auth / error-handling unit files.

        Not a smoke test: it is the whole integration tier (~1800 tests, ~3 min)
        with four unit files on top. ``./dev smoke`` is the render smoke test.
        """
        print("💨 Running QUICK subset")
        print("   Tests: integration + auth + error handling")
        print("   Expected: 100% passing")
        print("   Runtime: ~3 minutes (needs local Docker Neo4j)\n")

        cmd = [
            "uv",
            "run",
            "pytest",
            "tests/integration/",
            "tests/unit/test_authentication.py",
            "tests/unit/test_auth_session.py",
            "tests/unit/test_core_errors.py",
            "tests/unit/test_error_boundary.py",
            "-v",
            *extra_args,
        ]
        return subprocess.run(cmd, cwd=self.project_root).returncode

    def show_markers(self) -> int:
        """Show available pytest markers."""
        cmd = ["uv", "run", "pytest", "--markers"]
        return subprocess.run(cmd, cwd=self.project_root).returncode


def main():
    parser = argparse.ArgumentParser(
        description="SKUEL Test Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "mode",
        nargs="?",
        default="comprehensive",
        choices=["all", "comprehensive", "integration", "unit", "quick"],
        help="Test mode to run (default: comprehensive)",
    )

    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    parser.add_argument("-q", "--quiet", action="store_true", help="Quiet output")

    parser.add_argument("-k", metavar="EXPRESSION", help="Run tests matching expression")

    parser.add_argument("--cov", action="store_true", help="Include coverage report")

    parser.add_argument(
        "--tb",
        choices=["short", "long", "no", "line", "native"],
        help="Traceback format",
    )

    parser.add_argument("--markers", action="store_true", help="Show available test markers")

    args, extra = parser.parse_known_args()

    runner = TestRunner()

    # Show markers and exit
    if args.markers:
        return runner.show_markers()

    # Build extra arguments
    extra_args = extra.copy()

    if args.verbose and "-v" not in extra_args:
        extra_args.append("-v")

    if args.quiet and "-q" not in extra_args:
        extra_args.append("-q")

    if args.k:
        extra_args.extend(["-k", args.k])

    if args.cov:
        extra_args.extend(
            [
                "--cov=core",
                "--cov=adapters",
                "--cov=ui",
                "--cov=services_bootstrap",
                "--cov-report=term-missing",
            ]
        )

    if args.tb:
        extra_args.append(f"--tb={args.tb}")

    # Run selected mode
    mode_map = {
        "all": runner.run_all,
        "comprehensive": runner.run_comprehensive,
        "integration": runner.run_integration,
        "unit": runner.run_unit,
        "quick": runner.run_quick,
    }

    return mode_map[args.mode](extra_args)


if __name__ == "__main__":
    sys.exit(main())
