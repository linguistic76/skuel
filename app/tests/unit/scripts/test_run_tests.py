"""
run_tests.py — the runner forwards pytest's flags and owns only its own
=======================================================================

Every ``./dev test*`` arm forwards ``"${@:2}"`` to ``scripts/run_tests.py``, so
what the runner does with an argument it does not own decides whether a flag
reaches pytest. Three ways it can mangle one, each pinned here:

- **A ``mode`` positional would eat an option's value** whenever the mode is
  omitted — argparse cannot know the arity of an option it does not declare, so
  ``run_tests.py -k tasks`` would read ``tasks`` as the mode (Codex P2, #1351).
  The mode is therefore position-first (the first argument when it names one)
  and the parser declares no positional at all.
- **Abbreviation matching would claim pytest's ``--co``** (collect-only) as the
  runner's ``--cov``.
- **Re-parsing a pytest option narrows it** — the retired ``--tb`` re-parse
  carried a five-value ``choices`` list that rejected ``--tb=auto``.
"""

import sys
from pathlib import Path

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from run_tests import (  # type: ignore[import-not-found]
    COVERAGE_ARGS,
    DEFAULT_MODE,
    MODE_NAMES,
    parse_invocation,
)


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
    """One path: the four source trees and the three reports PR 4 consumes."""
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
