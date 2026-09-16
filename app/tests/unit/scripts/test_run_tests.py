"""
run_tests.py — the runner forwards pytest's flags and owns only its own
=======================================================================

Every ``./dev test*`` arm forwards ``"${@:2}"`` to ``scripts/run_tests.py``, so
what the runner does with an argument it does not own decides whether a flag
reaches pytest. Three invariants, each pinned here:

- **The mode is position-first and the parser declares no positional.**
  argparse cannot know the arity of an option it does not declare, so a
  ``mode`` positional would take the ``tasks`` of ``-k tasks`` (or the
  ``short`` of ``--tb short``) as the mode whenever the mode is omitted.
- **No abbreviation matching**: pytest's ``--co`` (collect-only) is not the
  runner's ``--cov``.
- **No pytest option is re-parsed**: a re-parse narrows what pytest accepts —
  ``--tb=auto`` is pytest's to validate, and pytest accepts it.

The unit tier's parallel default is the fourth invariant and obeys the third:
``unit`` appends ``-n logical --maxprocesses 8 --dist loadfile`` unless the
forwarded args already carry a worker or distribution choice — a membership test on the args, not a
declared ``-n`` — so ``./dev test-unit -n 1`` overrides it and the other three
modes (each holds the integration tier and its session containers) never gain it.
"""

import sys
from pathlib import Path

import pytest

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from run_tests import (  # type: ignore[import-not-found]
    COVERAGE_ARGS,
    DEFAULT_MODE,
    MODE_NAMES,
    UNIT_PARALLEL_ARGS,
    carries_worker_choice,
    parse_invocation,
    unit_tier_args,
)

# Bound under a name pytest does not collect: ``Test*`` in a test module is a
# test class to the collector, and this one has a constructor.
from run_tests import TestRunner as RunnerUnderTest  # type: ignore[import-not-found]


def test_mode_omitted_keeps_value_taking_option_values() -> None:
    """``-k tasks`` / ``--tb short`` with no mode: the value is pytest's, not the mode."""
    for argv in (["-k", "tasks"], ["--tb", "short"]):
        invocation = parse_invocation(argv)
        assert invocation.mode == DEFAULT_MODE
        assert invocation.pytest_args == argv


def test_mode_is_the_first_argument() -> None:
    for mode in MODE_NAMES:
        invocation = parse_invocation([mode, "-x", "--tb=auto"])
        assert invocation.mode == mode
        assert invocation.pytest_args == ["-x", "--tb=auto"]


def test_a_mode_word_after_position_zero_is_pytest_s() -> None:
    """``-k unit`` filters on the word ``unit``; it does not select the unit tier."""
    invocation = parse_invocation(["tests/unit/test_x.py", "-k", "unit"])
    assert invocation.mode == DEFAULT_MODE
    assert invocation.pytest_args == ["tests/unit/test_x.py", "-k", "unit"]


def test_collect_only_is_not_coverage() -> None:
    invocation = parse_invocation(["unit", "--co"])
    assert invocation.cov is False
    assert invocation.pytest_args == ["--co"]


def test_runner_options_are_taken_out_and_the_rest_stays_in_order() -> None:
    invocation = parse_invocation(["quick", "-q", "--cov", "-k", "tasks", "--markers"])
    assert invocation.mode == "quick"
    assert invocation.cov is True
    assert invocation.markers is True
    assert invocation.pytest_args == ["-q", "-k", "tasks"]


def test_coverage_args_are_the_whole_coverage_configuration() -> None:
    """One path: the four source trees and the three reports a coverage run writes."""
    assert {a for a in COVERAGE_ARGS if a.startswith("--cov=")} == {
        "--cov=core",
        "--cov=adapters",
        "--cov=ui",
        "--cov=services_bootstrap",
    }
    assert {a for a in COVERAGE_ARGS if a.startswith("--cov-report=")} == {
        "--cov-report=term-missing",
        "--cov-report=xml",
        "--cov-report=html:htmlcov",
    }


def test_no_argument_means_the_default_mode_and_nothing_forwarded() -> None:
    invocation = parse_invocation([])
    assert invocation.mode == DEFAULT_MODE
    assert invocation.pytest_args == []
    assert invocation.cov is False


def test_unit_tier_is_parallel_by_default() -> None:
    """No worker choice forwarded: the default leads, the user's args follow, in order."""
    assert unit_tier_args([]) == list(UNIT_PARALLEL_ARGS)
    assert unit_tier_args(["-k", "tasks", "-x"]) == [*UNIT_PARALLEL_ARGS, "-k", "tasks", "-x"]
    assert UNIT_PARALLEL_ARGS == ("-n", "logical", "--maxprocesses", "8", "--dist", "loadfile")


def test_a_forwarded_cap_lands_after_the_default_so_pytest_keeps_it() -> None:
    """``--maxprocesses 4`` is not a worker choice: the default stays, the cap wins by order."""
    argv = ["--maxprocesses", "4"]
    assert carries_worker_choice(argv) is False
    args = unit_tier_args(argv)
    assert args == [*UNIT_PARALLEL_ARGS, "--maxprocesses", "4"]
    assert args[-2:] == ["--maxprocesses", "4"]


@pytest.mark.parametrize(
    "argv",
    [
        ["-n", "1"],
        ["-n", "0"],
        ["-n1"],
        ["-nauto"],
        ["--numprocesses", "2"],
        ["--numprocesses=2"],
        ["--dist", "loadgroup"],
        ["--dist=no"],
        ["-k", "tasks", "-n", "4", "-x"],
    ],
)
def test_a_forwarded_worker_choice_withholds_the_whole_default(argv: list[str]) -> None:
    """``-n 1`` is the override; ``-n 0`` must not gain a ``--dist`` xdist refuses."""
    assert carries_worker_choice(argv) is True
    assert unit_tier_args(argv) == argv


@pytest.mark.parametrize(
    "argv",
    [
        ["--no-header"],
        ["--nf"],
        ["-k", "n"],
        ["-k", "numprocesses"],
        ["tests/unit/test_x.py", "-x", "--tb=auto"],
    ],
)
def test_only_the_worker_options_count_as_a_choice(argv: list[str]) -> None:
    """A ``--n…`` long option, or ``n`` as a value, is not ``-n``."""
    assert carries_worker_choice(argv) is False
    assert unit_tier_args(argv) == [*UNIT_PARALLEL_ARGS, *argv]


def test_the_worker_choice_reaches_the_runner_unparsed() -> None:
    """``-n 1`` is forwarded verbatim — the runner declares no ``-n`` of its own."""
    invocation = parse_invocation(["unit", "-n", "1", "-k", "tasks"])
    assert invocation.mode == "unit"
    assert invocation.pytest_args == ["-n", "1", "-k", "tasks"]


def _captured_command(mode_method_name: str, extra_args: list[str]) -> list[str]:
    runner = RunnerUnderTest()
    captured: list[list[str]] = []

    def record(cmd: list[str]) -> int:
        captured.append(cmd)
        return 0

    runner._run = record  # type: ignore[method-assign]
    getattr(runner, mode_method_name)(extra_args)
    (cmd,) = captured
    return cmd


def test_unit_mode_runs_the_tier_in_parallel() -> None:
    cmd = _captured_command("run_unit", ["-q"])
    assert cmd == ["uv", "run", "pytest", "tests/unit/", *UNIT_PARALLEL_ARGS, "-q"]


def test_unit_mode_override_is_the_forwarded_choice_alone() -> None:
    cmd = _captured_command("run_unit", ["-n", "1"])
    assert cmd == ["uv", "run", "pytest", "tests/unit/", "-n", "1"]


@pytest.mark.parametrize("mode_method_name", ["run_comprehensive", "run_integration", "run_quick"])
def test_the_modes_holding_the_integration_tier_stay_serial(mode_method_name: str) -> None:
    """Session-scoped testcontainers: N xdist workers would mean N container sets."""
    cmd = _captured_command(mode_method_name, ["-q"])
    assert not carries_worker_choice(cmd)
    assert cmd[-1] == "-q"
