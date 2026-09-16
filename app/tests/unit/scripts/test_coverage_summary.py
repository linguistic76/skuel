"""
coverage_summary.py — the gap picture is derived from the report, never a gate
==============================================================================

``scripts/coverage_summary.py`` turns the ``coverage.json`` a ``--cov`` run writes
into three Markdown tables (per-package rates, zero-coverage files, large files
under 50 %). It carries no threshold: the only non-zero exit is an unreadable
report. Pinned here:

- the three tables select and order what the docstring says they do, from a
  hand-written report (three files, one at 0 %), with the size gates exercised at
  their edges;
- the rendered text is Markdown with one heading per table, so it reads in a
  terminal and renders in the weekly run's step summary alike;
- ``main`` reads the configured default path and fails loudly on a missing or
  malformed report;
- the script reads what the runner writes: ``COVERAGE_ARGS`` asks for the JSON
  report, pyproject names the file the script defaults to, and coverage itself
  accepts ``include_namespace_packages`` — without it a never-imported module in a
  namespace-package directory is absent from every report, which is exactly the
  file the zero-coverage table exists to name.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import coverage
import pytest

APP_ROOT = Path(__file__).resolve().parents[3]
PYPROJECT = APP_ROOT / "pyproject.toml"
DEV = APP_ROOT / "dev"

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(APP_ROOT / "scripts"))

from coverage_summary import (  # type: ignore[import-not-found]  # noqa: E402
    DEFAULT_REPORT,
    LOW_COVERAGE_MAX_ROWS,
    LOW_COVERAGE_MIN_STATEMENTS,
    PACKAGE_MIN_STATEMENTS,
    ZERO_COVERAGE_MAX_ROWS,
    ZERO_COVERAGE_MIN_STATEMENTS,
    CoverageReport,
    FileCoverage,
    ReportError,
    large_low_coverage,
    load_report,
    main,
    package_key,
    per_package,
    render,
    zero_coverage,
)
from run_tests import COVERAGE_ARGS  # type: ignore[import-not-found]  # noqa: E402

# The hand-written report: three files, one at 0 %. Shapes mirror coverage.py's
# JSON format 3 — only the keys the script reads are populated.
FIXTURE_FILES: dict[str, tuple[int, int]] = {
    "core/services/ku/ku_service.py": (300, 240),  # 80 %
    "adapters/inbound/tasks_routes.py": (200, 60),  # 30 % — large and low
    "ui/patterns/ingestion_preview.py": (120, 0),  # 0 % — zero coverage
}


def _coverage_json(files: dict[str, tuple[int, int]]) -> dict[str, object]:
    """A coverage.py JSON report (format 3) over ``{path: (statements, covered)}``."""
    return {
        "meta": {
            "format": 3,
            "version": "7.15.4",
            "timestamp": "2026-09-16T05:00:00.000000",
            "branch_coverage": False,
            "show_contexts": False,
        },
        "files": {
            path: {
                "executed_lines": list(range(1, covered + 1)),
                "summary": {
                    "covered_lines": covered,
                    "num_statements": statements,
                    "percent_covered": 100 * covered / statements if statements else 100.0,
                    "missing_lines": statements - covered,
                    "excluded_lines": 0,
                },
                "missing_lines": list(range(covered + 1, statements + 1)),
                "excluded_lines": [],
            }
            for path, (statements, covered) in files.items()
        },
        "totals": {
            "covered_lines": sum(c for _, c in files.values()),
            "num_statements": sum(s for s, _ in files.values()),
            "percent_covered": 0.0,
            "missing_lines": sum(s - c for s, c in files.values()),
            "excluded_lines": 0,
        },
    }


def _files(spec: dict[str, tuple[int, int]]) -> tuple[FileCoverage, ...]:
    return tuple(
        FileCoverage(path=path, statements=statements, covered=covered)
        for path, (statements, covered) in spec.items()
    )


@pytest.fixture
def fixture_report(tmp_path: Path) -> Path:
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps(_coverage_json(FIXTURE_FILES)), encoding="utf-8")
    return path


# --- Reading the report --------------------------------------------------------


def test_the_fixture_parses_into_files_and_totals(fixture_report: Path) -> None:
    report = load_report(fixture_report)
    assert {f.path for f in report.files} == set(FIXTURE_FILES)
    assert report.total_statements == 620
    assert report.total_covered == 300
    assert report.rate == pytest.approx(300 / 620)
    assert report.generated_at == "2026-09-16T05:00:00.000000"
    assert report.coverage_version == "7.15.4"


def test_a_file_with_no_statements_is_fully_covered_not_a_division_error() -> None:
    empty = FileCoverage(path="ui/__init__.py", statements=0, covered=0)
    assert empty.rate == 1.0
    assert empty.missed == 0
    assert CoverageReport((), 0, 0, "t", "v").rate == 1.0


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        ("not json {", "is not JSON"),
        (json.dumps({"files": {}}), "expected meta/files/totals"),
        (
            json.dumps({"meta": {}, "files": {"a.py": {}}, "totals": {}}),
            "expected meta/files/totals",
        ),
    ],
)
def test_a_malformed_report_is_a_report_error(tmp_path: Path, content: str, reason: str) -> None:
    path = tmp_path / "coverage.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ReportError, match=re.escape(reason)):
        load_report(path)


def test_a_missing_report_is_a_report_error(tmp_path: Path) -> None:
    with pytest.raises(ReportError, match="cannot read"):
        load_report(tmp_path / "absent.json")


# --- The three tables ----------------------------------------------------------


def test_package_key_is_the_first_two_path_segments() -> None:
    assert package_key("core/services/ku/ku_service.py") == "core/services"
    assert package_key("adapters/inbound/tasks_routes.py") == "adapters/inbound"
    assert package_key("ui/theme.py") == "ui"
    assert package_key("services_bootstrap/compose.py") == "services_bootstrap"


def test_per_package_sums_files_lowest_rate_first_and_size_gated() -> None:
    files = _files(
        {
            "core/services/a.py": (150, 150),
            "core/services/b.py": (150, 0),  # core/services: 300 stmts, 50 %
            "ui/x.py": (PACKAGE_MIN_STATEMENTS, 20),  # ui: at the gate, 10 %
            "adapters/inbound/y.py": (PACKAGE_MIN_STATEMENTS - 1, 0),  # under it: unlisted
        }
    )
    rows = per_package(files)
    assert [(r.key, r.statements, r.covered) for r in rows] == [
        ("ui", PACKAGE_MIN_STATEMENTS, 20),
        ("core/services", 300, 150),
    ]
    assert rows[0].rate == pytest.approx(0.1)


def test_zero_coverage_lists_only_empty_files_of_size_largest_first() -> None:
    files = _files(
        {
            "ui/small.py": (ZERO_COVERAGE_MIN_STATEMENTS - 1, 0),  # under the gate
            "ui/at_gate.py": (ZERO_COVERAGE_MIN_STATEMENTS, 0),
            "ui/big.py": (400, 0),
            "ui/one_hit.py": (400, 1),  # not zero: belongs to the low table, if large
        }
    )
    assert [f.path for f in zero_coverage(files)] == ["ui/big.py", "ui/at_gate.py"]


def test_large_low_coverage_excludes_zero_files_the_gate_and_exactly_half() -> None:
    files = _files(
        {
            "core/a.py": (LOW_COVERAGE_MIN_STATEMENTS, 0),  # zero: the other table's
            "core/b.py": (LOW_COVERAGE_MIN_STATEMENTS - 1, 1),  # under the size gate
            "core/half.py": (200, 100),  # exactly 50 %: not under it
            "core/low.py": (200, 60),  # 30 %, 140 missed
            "core/lower.py": (LOW_COVERAGE_MIN_STATEMENTS, 1),  # 149 missed
        }
    )
    assert [f.path for f in large_low_coverage(files)] == ["core/lower.py", "core/low.py"]


def test_the_fixture_lands_one_file_in_each_file_table(fixture_report: Path) -> None:
    report = load_report(fixture_report)
    assert [f.path for f in zero_coverage(report.files)] == ["ui/patterns/ingestion_preview.py"]
    assert [f.path for f in large_low_coverage(report.files)] == [
        "adapters/inbound/tasks_routes.py"
    ]
    assert [r.key for r in per_package(report.files)] == [
        "adapters/inbound",
        "core/services",
    ]  # ui/patterns has 120 statements — under the package gate


# --- Rendering -----------------------------------------------------------------


def test_render_is_markdown_with_a_total_and_one_heading_per_table(fixture_report: Path) -> None:
    text = render(load_report(fixture_report))
    lines = text.splitlines()
    assert lines[0] == "## Coverage — 48.4 % of 620 statements (300 covered)"
    headings = [line for line in lines if line.startswith("### ")]
    assert headings == [
        f"### Per package (≥ {PACKAGE_MIN_STATEMENTS} statements, lowest first)",
        f"### Files with zero coverage (≥ {ZERO_COVERAGE_MIN_STATEMENTS} statements)"
        " — 1 files, 120 statements",
        f"### Large files (≥ {LOW_COVERAGE_MIN_STATEMENTS} statements) under 50.0 % — 1 files",
    ]
    assert "| `adapters/inbound` | 200 | 60 | 30.0 % |" in lines
    assert "| `core/services` | 300 | 240 | 80.0 % |" in lines
    assert "| 120 | `ui/patterns/ingestion_preview.py` |" in lines
    assert "| 30.0 % | 200 | 140 | `adapters/inbound/tasks_routes.py` |" in lines
    assert lines.index("| `adapters/inbound` | 200 | 60 | 30.0 % |") < lines.index(
        "| `core/services` | 300 | 240 | 80.0 % |"
    )
    assert "no threshold" in text
    assert text.endswith("\n")


def test_render_names_an_empty_table_rather_than_omitting_it() -> None:
    text = render(CoverageReport((), 0, 0, "2026-09-16", "7.15.4"))
    assert text.count("### ") == 3
    assert "| _none_ |" in text
    assert f"| _none of ≥ {PACKAGE_MIN_STATEMENTS} statements_ |" in text


def test_render_caps_the_file_tables_and_says_how_many_rows_it_hides() -> None:
    zero = {f"ui/z{i:03d}.py": (100, 0) for i in range(ZERO_COVERAGE_MAX_ROWS + 3)}
    low = {f"core/l{i:03d}.py": (200, 10) for i in range(LOW_COVERAGE_MAX_ROWS + 2)}
    report = CoverageReport(_files({**zero, **low}), 1, 1, "t", "v")
    text = render(report)
    assert text.count("| `ui/z") == ZERO_COVERAGE_MAX_ROWS
    assert "| … | _3 more_ |" in text
    assert text.count("| `core/l") == LOW_COVERAGE_MAX_ROWS
    assert "| … | | | _2 more_ |" in text


# --- The command line ------------------------------------------------------------


def test_main_reads_the_default_path_from_the_working_directory(
    fixture_report: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(fixture_report.parent)
    assert fixture_report.name == str(DEFAULT_REPORT)
    assert main([]) == 0
    captured = capsys.readouterr()
    assert captured.out.startswith("## Coverage — 48.4 %")
    assert captured.err == ""


def test_main_takes_an_explicit_path(
    fixture_report: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([str(fixture_report)]) == 0
    assert "`ui/patterns/ingestion_preview.py`" in capsys.readouterr().out


def test_main_fails_loudly_on_a_missing_or_malformed_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([str(tmp_path / "absent.json")]) == 1
    assert "coverage_summary: cannot read" in capsys.readouterr().err

    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    assert main([str(bad)]) == 1
    captured = capsys.readouterr()
    assert "is not JSON" in captured.err
    assert captured.out == ""


# --- The script reads what the runner writes ---------------------------------------


def test_the_runner_writes_the_report_the_summary_reads() -> None:
    """``--cov`` asks for the JSON report, at the path the script defaults to.

    Read through coverage's own config parser, not tomllib: a misspelled key in
    pyproject would be an "unrecognized option" coverage warns about and ignores,
    and this test must see what coverage sees.
    """
    assert "--cov-report=json" in COVERAGE_ARGS
    config = coverage.Coverage(config_file=str(PYPROJECT)).config
    assert config.json_output == str(DEFAULT_REPORT)


def test_never_imported_modules_in_namespace_packages_are_discovered() -> None:
    """The zero-coverage table can only name a file the report contains.

    ``core/``, ``core/services/``, ``core/utils/``, ``adapters/persistence/`` … are
    namespace packages (no ``__init__.py``). coverage's sweep for never-imported
    files stops at the first such directory unless ``include_namespace_packages``
    is on — and a module nothing imports then vanishes from every report, its
    statements out of the denominator. The setting is read through coverage's own
    parser so a misspelling (it lives under ``[report]``, not ``[run]``) fails here
    rather than as an ignored warning.
    """
    config = coverage.Coverage(config_file=str(PYPROJECT)).config
    assert config.include_namespace_packages is True
    namespace_dirs = [
        d
        for d in ("core", "core/services", "core/utils")
        if not (APP_ROOT / d / "__init__.py").exists()
    ]
    assert namespace_dirs, (
        "the measured trees have grown __init__.py files — the setting is now inert"
    )


def test_the_dev_arm_forwards_its_arguments_to_the_script() -> None:
    """``./dev coverage-summary [path]`` is the documented entry point."""
    text = DEV.read_text(encoding="utf-8")
    arm = re.search(r"^  coverage-summary\)\n(.*?)^    ;;", text, re.MULTILINE | re.DOTALL)
    assert arm, "dev has no coverage-summary arm"
    assert 'uv run python scripts/coverage_summary.py "${@:2}"' in arm.group(1)
    assert ">&2" in arm.group(1), "the status line must go to stderr so stdout stays the tables"
