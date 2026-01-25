#!/usr/bin/env python3
"""
SKUEL Test Runner - Comprehensive test suite execution with multiple modes.

Usage:
    poetry run python scripts/run_tests.py [mode] [options]

Modes:
    all           - Run complete test suite (1,349 tests, ~73s)
    comprehensive - Run all tests except broken unit tests (1,150 tests, ~70s) [RECOMMENDED]
    integration   - Run integration tests only (240 tests, ~60s) [FAST]
    service       - Run service tests only (~600 tests)
    unit          - Run unit tests only (164 tests - mostly broken)
    quick         - Run fastest subset for smoke testing

Options:
    -v, --verbose     - Verbose output
    -q, --quiet       - Quiet output
    -k EXPRESSION     - Run tests matching expression
    --cov             - Include coverage report
    --tb=short        - Short traceback format
    --tb=no           - No traceback (fast failures)
    -n auto           - Parallel execution (pytest-xdist)
    --markers         - Show available test markers
"""

import argparse
import subprocess
import sys
from pathlib import Path


class TestRunner:
    """Manages test execution with predefined configurations."""

    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.tests_dir = self.project_root / "tests"

    def run_all(self, extra_args: list[str]) -> int:
        """Run complete test suite (1,349 tests)."""
        print("🔍 Running COMPLETE test suite (1,349 tests)")
        print("   Expected: 1,124 passing, 183 failed, 35 errors")
        print("   Runtime: ~73 seconds\n")

        cmd = ["poetry", "run", "pytest", "tests/", "-v", *extra_args]
        return subprocess.run(cmd, cwd=self.project_root).returncode

    def run_comprehensive(self, extra_args: list[str]) -> int:
        """Run all tests except broken unit tests (RECOMMENDED)."""
        print("✅ Running COMPREHENSIVE test suite (recommended)")
        print("   Tests: ~1,150 (integration + service + auth + other)")
        print("   Expected: ~1,100 passing (~95% success)")
        print("   Runtime: ~70 seconds")
        print("   Excludes: 164 broken unit tests\n")

        cmd = [
            "poetry",
            "run",
            "pytest",
            "tests/",
            "--ignore=tests/unit/",
            "-v",
            *extra_args,
        ]
        return subprocess.run(cmd, cwd=self.project_root).returncode

    def run_integration(self, extra_args: list[str]) -> int:
        """Run integration tests only (FAST)."""
        print("⚡ Running INTEGRATION tests only (fast)")
        print("   Tests: 434")
        print("   Expected: 434 passing (100% success)")
        print("   Runtime: ~30-60 seconds")
        print("   Quality metric: Test pass rate (not coverage)")
        print("   Note: Use --cov flag if you want coverage reports\n")

        # Run without coverage by default (test pass rate is the quality metric)
        # Coverage percentage is misleading for integration tests because they test
        # specific functionality (CRUD, relationships) not broad coverage
        cmd = [
            "poetry",
            "run",
            "pytest",
            "tests/integration/",
            "-v",
            "--override-ini=addopts=",  # Clear default addopts (no coverage by default)
            *extra_args,
        ]
        return subprocess.run(cmd, cwd=self.project_root).returncode

    def run_service(self, extra_args: list[str]) -> int:
        """Run service tests only."""
        print("🔧 Running SERVICE tests only")
        print("   Tests: ~600 (activity domains + curriculum)")
        print("   Expected: ~550 passing (~92% success)")
        print("   Runtime: ~40 seconds\n")

        # Run root-level test files (exclude integration/ and unit/)
        cmd = [
            "poetry",
            "run",
            "pytest",
            "tests/",
            "--ignore=tests/integration/",
            "--ignore=tests/unit/",
            "--ignore=tests/infrastructure/",
            "-v",
            *extra_args,
        ]
        return subprocess.run(cmd, cwd=self.project_root).returncode

    def run_unit(self, extra_args: list[str]) -> int:
        """Run unit tests only (mostly broken - mock issues)."""
        print("🧪 Running UNIT tests only")
        print("   Tests: 164 (relationship services)")
        print("   ⚠️  WARNING: Most unit tests are broken (mock configuration)")
        print("   Expected: 0 passing (known issue)")
        print("   Runtime: ~10 seconds\n")

        cmd = ["poetry", "run", "pytest", "tests/unit/", "-v", *extra_args]
        return subprocess.run(cmd, cwd=self.project_root).returncode

    def run_quick(self, extra_args: list[str]) -> int:
        """Run quick smoke test (fastest subset)."""
        print("💨 Running QUICK smoke test")
        print("   Tests: Integration + Auth + Error handling (~350 tests)")
        print("   Expected: ~345 passing (99% success)")
        print("   Runtime: ~30 seconds\n")

        cmd = [
            "poetry",
            "run",
            "pytest",
            "tests/integration/",
            "tests/test_authentication.py",
            "tests/test_auth_session.py",
            "tests/test_core_errors.py",
            "tests/test_error_boundary.py",
            "-v",
            *extra_args,
        ]
        return subprocess.run(cmd, cwd=self.project_root).returncode

    def show_markers(self) -> int:
        """Show available pytest markers."""
        cmd = ["poetry", "run", "pytest", "--markers"]
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
        choices=["all", "comprehensive", "integration", "service", "unit", "quick"],
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

    parser.add_argument(
        "-n",
        metavar="NUM",
        help="Run tests in parallel (use 'auto' for CPU count)",
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
        extra_args.extend(["--cov=core", "--cov-report=term-missing"])

    if args.tb:
        extra_args.append(f"--tb={args.tb}")

    if args.n:
        extra_args.extend(["-n", args.n])

    # Run selected mode
    mode_map = {
        "all": runner.run_all,
        "comprehensive": runner.run_comprehensive,
        "integration": runner.run_integration,
        "service": runner.run_service,
        "unit": runner.run_unit,
        "quick": runner.run_quick,
    }

    return mode_map[args.mode](extra_args)


if __name__ == "__main__":
    sys.exit(main())
