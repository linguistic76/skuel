#!/usr/bin/env python3
"""
SKUEL Test Runner - Comprehensive test suite execution with multiple modes.

Usage:
    uv run python scripts/run_tests.py [mode] [--cov] [pytest args...]

Modes (the FIRST argument when given; omitted = comprehensive):
    comprehensive - unit + integration [RECOMMENDED] — one serial session
    integration   - Integration tests only (local Docker Neo4j) — serial
    unit          - Unit tests only — fast CI tier (no Docker) — PARALLEL
    quick         - Integration + the auth / error-handling unit files — serial

Runner options (the only ones parsed here):
    --cov             - Collect coverage — THE one coverage path (opt-in; writes
                        coverage.xml + coverage.json + htmlcov/ and prints
                        term-missing). A plain run collects none.
    --markers         - Show the declared pytest markers and exit

Every other argument is pytest's and is forwarded verbatim, in order — ``-k EXPR``,
``-x``, ``-q``, ``--tb=auto``, ``--lf`` … The four pytest ``./dev test*`` arms
(``test``, ``test-unit``, ``test-integration``, ``test-quick``) forward their flags
here: ``./dev test-unit -k tasks -x``, ``./dev test --cov``.

Parallelism — the unit tier only. ``unit`` appends ``-n logical --maxprocesses
8 --dist loadfile`` (pytest-xdist: one worker per logical CPU, at most eight, a
module never split across workers) unless the forwarded args already carry a
worker or distribution choice (``-n`` / ``--numprocesses`` / ``--dist``), so
``./dev test-unit -n 1`` — or ``-n 0`` for an in-process serial run — overrides
it with no parser surface. ``logical`` rather than ``auto`` because xdist
resolves ``auto`` to PHYSICAL cores when psutil is importable (it is — a main
dependency), which on a 4-vCPU runner is two workers; the hyperthreads are
real capacity for a tier this subprocess- and I/O-heavy. The cap is measured,
not a guess: every worker imports the app (~0.5 GB resident) and the tier's
critical path is its longest module (the corpus scanners, ~20–35 s), so eight
workers already sit on that floor — fourteen run no shorter and cost a 16 GB
laptop its swap. A 4-vCPU runner never reaches the cap. The other three modes
run serially, by ruling: each holds the integration tier, whose session-scoped
fixtures are three Neo4j testcontainers and one app boot, and under xdist every
worker builds its own set — N workers cost N container sets. ``comprehensive``
is the composed-session guard (one session, both tiers — the shape the per-tier
CI jobs never run; ``.github/workflows/composed-test-run.yml`` runs it weekly,
with ``--cov``); its wall time is the integration tier's plus the unit tier's,
serial.
"""

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Coverage is opt-in: pyproject's addopts collects none, so these flags are the
# whole coverage configuration a run receives. Report shapes (omit list, html
# directory, xml and json paths) live in pyproject's [tool.coverage.*] tables.
# Four reports, four readers: term-missing for the console, html for a browser,
# xml (Cobertura) for tools that read it, json for scripts/coverage_summary.py —
# the one lossless form under four `--cov=` trees (see that script's docstring).
COVERAGE_ARGS: tuple[str, ...] = (
    "--cov=core",
    "--cov=adapters",
    "--cov=ui",
    "--cov=services_bootstrap",
    "--cov-report=term-missing",
    "--cov-report=xml",
    "--cov-report=json",
    "--cov-report=html:htmlcov",
)

DEFAULT_MODE = "comprehensive"
MODE_NAMES: tuple[str, ...] = (DEFAULT_MODE, "integration", "unit", "quick")

# The unit tier's parallel default: one xdist worker per logical CPU, capped
# at eight (see the module docstring for the measurement), a test module never
# split across workers (the corpus-scanning modules carry module-scoped
# fixtures, so the critical path is the longest module, not the sum). Appended
# by the ``unit`` mode alone. A forwarded ``--maxprocesses N`` is not a worker
# choice — it lands after this one and pytest keeps the last.
UNIT_PARALLEL_ARGS: tuple[str, ...] = (
    "-n",
    "logical",
    "--maxprocesses",
    "8",
    "--dist",
    "loadfile",
)

# The options that make a forwarded arg list a worker / distribution choice of
# its own. ``-n`` also matches its attached-value spelling (``-n0``, ``-nauto``);
# a ``--n…`` long option (``--no-header``, ``--nf``) is not ``-n``.
WORKER_CHOICE_OPTIONS: tuple[str, ...] = ("-n", "--numprocesses", "--dist")


def carries_worker_choice(pytest_args: list[str]) -> bool:
    """True when the forwarded pytest args already choose workers or distribution.

    A membership test, never a parse: the runner declares no ``-n`` (a re-parse
    narrows what pytest accepts), it only looks for one. Any hit means the user
    wrote the whole choice and the parallel default is withheld wholesale —
    ``-n 0`` alone must not gain a ``--dist loadfile``, which xdist refuses
    without workers.
    """
    for arg in pytest_args:
        if arg in WORKER_CHOICE_OPTIONS:
            return True
        if arg.startswith(("--numprocesses=", "--dist=")):
            return True
        if arg.startswith("-n"):
            return True
    return False


def unit_tier_args(pytest_args: list[str]) -> list[str]:
    """The unit tier's pytest args: the parallel default unless one was forwarded."""
    if carries_worker_choice(pytest_args):
        return list(pytest_args)
    return [*UNIT_PARALLEL_ARGS, *pytest_args]


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
        only the uncollected benchmarks directory. Serial: the session holds
        the integration tier's containers (see the module docstring).
        """
        print("✅ Running COMPREHENSIVE test suite (recommended)")
        print("   unit + integration (both CI tiers), one serial session")
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
        """Run unit tests only — fast CI tier (no Docker needed), in parallel.

        pytest-xdist with one worker per logical CPU (at most eight) unless
        ``extra_args`` carries its own worker choice (``-n 1``, ``-n 0`` for
        serial).
        """
        print("🧪 Running UNIT tests (fast CI tier)")
        print("   Mock-based; no Docker/Neo4j required")
        print(
            "   Parallel: -n logical --maxprocesses 8 --dist loadfile unless -n / --dist is given\n"
        )

        cmd = ["uv", "run", "pytest", "tests/unit/", *unit_tier_args(extra_args)]
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


@dataclass(frozen=True)
class Invocation:
    """What one command line asks for: a mode, the two runner options, pytest's args."""

    mode: str
    cov: bool
    markers: bool
    pytest_args: list[str]


def parse_invocation(argv: list[str]) -> Invocation:
    """Split a command line into the runner's part and pytest's part.

    The mode is the FIRST argument when it names one, otherwise the default —
    position is the only thing that can tell a mode word from a pytest option's
    value: argparse cannot know the arity of an option it does not declare, so a
    ``mode`` positional would swallow the ``tasks`` of ``-k tasks`` (or the
    ``short`` of ``--tb short``) whenever the mode is omitted. Only ``--cov`` and
    ``--markers`` are parsed; everything else is pytest's, forwarded verbatim
    and in order. ``allow_abbrev=False`` because argparse would otherwise claim
    any unambiguous prefix of a runner option — pytest's own ``--co``
    (collect-only) would arrive as ``--cov``.
    """
    if argv and argv[0] in MODE_NAMES:
        mode, rest = argv[0], argv[1:]
    else:
        mode, rest = DEFAULT_MODE, argv

    parser = argparse.ArgumentParser(
        prog="run_tests.py",
        usage="%(prog)s [mode] [--cov] [pytest args...]",
        description="SKUEL Test Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
        allow_abbrev=False,
    )
    parser.add_argument(
        "--cov",
        action="store_true",
        help="Collect coverage (opt-in; writes coverage.xml + coverage.json + htmlcov/)",
    )
    parser.add_argument("--markers", action="store_true", help="Show the declared markers")
    args, pytest_args = parser.parse_known_args(rest)
    return Invocation(mode=mode, cov=args.cov, markers=args.markers, pytest_args=pytest_args)


def main() -> int:
    invocation = parse_invocation(sys.argv[1:])
    runner = TestRunner()

    if invocation.markers:
        return runner.show_markers()

    extra_args = list(invocation.pytest_args)
    if invocation.cov:
        extra_args.extend(COVERAGE_ARGS)

    mode_map = {
        "comprehensive": runner.run_comprehensive,
        "integration": runner.run_integration,
        "unit": runner.run_unit,
        "quick": runner.run_quick,
    }
    return mode_map[invocation.mode](extra_args)


if __name__ == "__main__":
    sys.exit(main())
