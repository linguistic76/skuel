"""The ``--json`` mode of scripts/skills_validator.py emits machine-clean stdout.

WHY THIS EXISTS

CI's Generate Metrics job (ci.yml, ``documentation_metrics``) runs::

    uv run python scripts/skills_validator.py --json > skills.json

and ``json.load()``s the file. The validator's progress narration
("Running validation checks...", the numbered ✅ lines) was printed to stdout
*before* the JSON, so ``skills.json`` opened with prose and the parse died with
``Expecting value: line 1 column 1`` — failing the job, and with it every CI
run on main pushes, for weeks (first diagnosed 2026-08-07 while checking in on
the PR #968 merge). The fix routes narration to stderr; stdout is the report
channel.

These tests RUN the shipped script as a subprocess — the same way CI consumes
it — rather than asserting things about its internals, so the pin holds
against any future refactor that reintroduces stdout narration.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = APP_ROOT / "scripts" / "skills_validator.py"


@pytest.fixture(scope="module")
def json_run() -> subprocess.CompletedProcess[str]:
    """One shared ``--json`` invocation against the real repo (~1s)."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--json"],
        capture_output=True,
        text=True,
        cwd=APP_ROOT,
        timeout=120,
    )


class TestJsonStdoutContract:
    def test_stdout_is_parseable_json(self, json_run: subprocess.CompletedProcess[str]) -> None:
        report = json.loads(json_run.stdout)
        assert isinstance(report, dict)

    def test_stdout_carries_no_progress_narration(
        self, json_run: subprocess.CompletedProcess[str]
    ) -> None:
        # The exact prose that corrupted skills.json in CI.
        assert "Running validation checks" not in json_run.stdout

    def test_progress_narration_moved_to_stderr_not_deleted(
        self, json_run: subprocess.CompletedProcess[str]
    ) -> None:
        assert "Running validation checks" in json_run.stderr

    def test_report_has_every_key_the_ci_parser_reads(
        self, json_run: subprocess.CompletedProcess[str]
    ) -> None:
        """ci.yml's inline parser indexes these — a rename breaks the job again."""
        report = json.loads(json_run.stdout)
        for key in ("total_skills", "passed_checks", "total_checks", "warnings", "errors"):
            assert key in report, f"CI-parsed key missing from --json report: {key}"
        for error in report["errors"]:
            assert "severity" in error  # CI filters errors by severity
