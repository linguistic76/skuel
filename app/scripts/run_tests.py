#!/usr/bin/env python3
"""
SKUEL Test Runner - Comprehensive test suite execution with multiple modes.

Usage:
    uv run python scripts/run_tests.py [mode] [--cov] [pytest args...]

Modes:
    comprehensive - unit + integration [RECOMMENDED]
    integration   - Integration tests only (local Docker Neo4j)
    unit          - Unit tests only — fast CI tier (no Docker)
    quick         - Integration + the auth / error-handling unit files

Runner options (the only ones parsed here):
    --cov             - Collect coverage — THE one coverage path (opt-in; writes
                        coverage.xml + htmlcov/ and prints term-missing). A plain
                        run collects none.
    --markers         - Show the declared pytest markers and exit

Every other argument is pytest's and is forwarded verbatim, in order — ``-k EXPR``,
``-x``, ``-q``, ``--tb=auto``, ``--lf`` … Each ``./dev test*`` arm forwards its
flags here: ``./dev test-unit -k tasks -x``, ``./dev test --cov``.
"""

import argparse
import subprocess
import sys
from pathlib import Path

# Coverage is opt-in: pyproject's addopts collects none, so these flags are the
# whole coverage configuration a run receives. Report shapes (omit list, html
# directory, xml path) live in pyproject's [tool.coverage.*] tables.
COVERAGE_ARGS: tuple[str, ...] = (
    "--cov=core",
    "--cov=adapters",
    "--cov=ui",
    "--cov=services_bootstrap",
    "--cov-report=term-missing",
    "--cov-report=xml",
    "--cov-report=html:htmlcov",
)


class TestRunner:
    """Manages test execution with predefined configurations."""

    def __init__(self) -> None:
        self.project_root = Path(__file__).parent.parent

    def _run(self, cmd: list[str]) -> int:
        # The banner precedes pytest's output only if it leaves the buffer first:
        # piped (`./dev test | tee`), print() holds it until exit, after the run.
        sys.stdout.flush()
        return subprocess.run(cmd, cwd=self.project_root).returncode

    def run_comprehensive(self, extra_args: list[str]) -> int:
        """Run unit + integration (RECOMMENDED) — both CI tiers in one session.

        tests/unit/ is the fast CI tier: every Docker-free test lives there;
        tests/integration/ (e2e flows included) is the Docker tier. Excludes
        only the uncollected benchmarks directory.
        """
        print("✅ Running COMPREHENSIVE test suite (recommended)")
        print("   unit + integration (both CI tiers)")
        print("   Excludes: benchmarks")
        print("   Integration needs local Docker Neo4j (testcontainers)\n")

        cmd = [
            "uv",
            "run",
            "pytest",
            "tests/",
            "--ignore=tests/benchmarks/",
            *extra_args,
        ]
        return self._run(cmd)

    def run_integration(self, extra_args: list[str]) -> int:
        """Run integration tests only (FAST)."""
        print("⚡ Running INTEGRATION tests only (fast)")
        print("   Tests: full tests/integration/ suite")
        print("   Expected: 100% passing")
        print("   Runtime: ~2-4 minutes")
        print("   Quality metric: Test pass rate (not coverage)")
        print("   Note: Use --cov flag if you want coverage reports\n")

        cmd = ["uv", "run", "pytest", "tests/integration/", *extra_args]
        return self._run(cmd)

    def run_unit(self, extra_args: list[str]) -> int:
        """Run unit tests only — fast CI tier (no Docker needed)."""
        print("🧪 Running UNIT tests (fast CI tier)")
        print("   Mock-based; no Docker/Neo4j required\n")

        cmd = ["uv", "run", "pytest", "tests/unit/", *extra_args]
        return self._run(cmd)

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
            *extra_args,
        ]
        return self._run(cmd)

    def show_markers(self) -> int:
        """Show available pytest markers."""
        cmd = ["uv", "run", "pytest", "--markers"]
        return self._run(cmd)


def main() -> int:
    # allow_abbrev=False: argparse would otherwise claim any unambiguous prefix
    # of a runner option, so pytest's own ``--co`` (collect-only) would arrive
    # here as ``--cov``. Only the mode and the two runner options are parsed;
    # everything else reaches pytest untouched.
    parser = argparse.ArgumentParser(
        description="SKUEL Test Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
        allow_abbrev=False,
    )

    parser.add_argument(
        "mode",
        nargs="?",
        default="comprehensive",
        choices=["comprehensive", "integration", "unit", "quick"],
        help="Test mode to run (default: comprehensive)",
    )

    parser.add_argument(
        "--cov",
        action="store_true",
        help="Collect coverage (opt-in; writes coverage.xml + htmlcov/)",
    )

    parser.add_argument("--markers", action="store_true", help="Show the declared markers")

    args, extra_args = parser.parse_known_args()

    runner = TestRunner()

    # Show markers and exit
    if args.markers:
        return runner.show_markers()

    if args.cov:
        extra_args.extend(COVERAGE_ARGS)

    # Run selected mode
    mode_map = {
        "comprehensive": runner.run_comprehensive,
        "integration": runner.run_integration,
        "unit": runner.run_unit,
        "quick": runner.run_quick,
    }

    return mode_map[args.mode](extra_args)


if __name__ == "__main__":
    sys.exit(main())
