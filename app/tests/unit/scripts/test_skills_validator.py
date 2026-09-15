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


# ---------------------------------------------------------------------------
# Check 8: every ADR a SKILL.md cites is listed in that skill's related_adrs
# ---------------------------------------------------------------------------

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from skills_validator import (  # type: ignore[import-not-found]  # noqa: E402
    validate_skill_md_adr_closure,
)


def _skill(skills_dir: Path, name: str, skill_md: str, **files: str) -> None:
    d = skills_dir / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(skill_md)
    for fname, body in files.items():
        (d / fname).write_text(body)


class TestSkillMdAdrClosure:
    """A SKILL.md citation is a commitment; a reference-file mention is not."""

    def test_a_skill_md_citation_must_be_listed(self, tmp_path: Path) -> None:
        _skill(tmp_path, "s", "# S\n\nUpdates go through a typed intent (ADR-066).\n")
        errors = validate_skill_md_adr_closure([{"name": "s", "related_adrs": []}], tmp_path)
        assert [(e.check, e.severity, e.context["adr"]) for e in errors] == [
            ("skill_md_adr_closure", "error", "ADR-066")
        ]

    def test_a_listed_citation_is_clean_and_extras_are_allowed(self, tmp_path: Path) -> None:
        _skill(tmp_path, "s", "# S\n\nSee ADR-066.\n")
        skill = {"name": "s", "related_adrs": ["ADR-066", "ADR-020"]}  # ADR-020 is a curated extra
        assert validate_skill_md_adr_closure([skill], tmp_path) == []

    def test_a_full_filename_entry_covers_a_bare_number(self, tmp_path: Path) -> None:
        _skill(tmp_path, "s", "# S\n\nPersistence per ADR-030.\n")
        skill = {"name": "s", "related_adrs": ["ADR-030-dual-track-assessment-pattern.md"]}
        assert validate_skill_md_adr_closure([skill], tmp_path) == []

    def test_a_reference_file_may_mention_an_adr_freely(self, tmp_path: Path) -> None:
        _skill(
            tmp_path,
            "s",
            "# S\n\nNo citations here.\n",
            **{"reference.md": "Deep dive (ADR-044).\n"},
        )
        assert validate_skill_md_adr_closure([{"name": "s", "related_adrs": []}], tmp_path) == []

    def test_each_missing_adr_is_one_error(self, tmp_path: Path) -> None:
        _skill(tmp_path, "s", "# S\n\nADR-013 and ADR-054, and ADR-013 again.\n")
        errors = validate_skill_md_adr_closure(
            [{"name": "s", "related_adrs": ["ADR-054"]}], tmp_path
        )
        assert [e.context["adr"] for e in errors] == ["ADR-013"]
