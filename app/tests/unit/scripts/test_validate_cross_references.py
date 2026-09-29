"""Reader tests for scripts/validate_cross_references.py.

The validator once regexed ``@([a-z0-9-]+)`` out of doc *bodies* while the repo
declared its doc→skill links in ``related_skills:`` frontmatter, so the two
halves of the cross-reference system never met: a doc could carry
``related_skills: [activity-domains]`` and still be reported as not referencing
that skill. These pin the canonical field as the one that is read, and prose as
the one that is not.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from validate_cross_references import (  # type: ignore[import-not-found]
    check_skill_staleness,
    find_skill_references_in_file,
    get_doc_last_modified,
)


def _doc(tmp_path: Path, body: str, name: str = "DOC.md") -> Path:
    path = tmp_path / name
    path.write_text(body)
    return path


class TestFrontmatterIsCanonical:
    def test_reads_related_skills_from_frontmatter(self, tmp_path):
        doc = _doc(
            tmp_path,
            "---\ntitle: Arch\nrelated_skills: [activity-domains, fasthtml]\n---\n\n# Arch\n",
        )
        assert find_skill_references_in_file(doc) == {"activity-domains", "fasthtml"}

    def test_tolerates_scalar_form(self, tmp_path):
        doc = _doc(tmp_path, "---\nrelated_skills: fasthtml\n---\n\n# Doc\n")
        assert find_skill_references_in_file(doc) == {"fasthtml"}

    def test_empty_and_absent_field_both_yield_nothing(self, tmp_path):
        absent = _doc(tmp_path, "---\ntitle: X\n---\n\n# X\n", "A.md")
        empty = _doc(tmp_path, "---\nrelated_skills: []\n---\n\n# Y\n", "B.md")
        none_valued = _doc(tmp_path, "---\nrelated_skills:\n---\n\n# Z\n", "C.md")
        assert find_skill_references_in_file(absent) == set()
        assert find_skill_references_in_file(empty) == set()
        assert find_skill_references_in_file(none_valued) == set()

    def test_no_frontmatter_at_all_is_not_an_error(self, tmp_path):
        assert find_skill_references_in_file(_doc(tmp_path, "# Plain doc\n")) == set()


class TestProseIsNotALink:
    def test_prose_mention_is_not_a_link(self, tmp_path):
        doc = _doc(
            tmp_path,
            "---\ntitle: ADR\n---\n\n# ADR\n\nSee the @fasthtml skill for routing.\n",
        )
        assert find_skill_references_in_file(doc) == set()

    def test_decorator_in_a_code_block_is_not_a_link(self, tmp_path):
        """`@pytest.fixture` in an example is not a reference to the pytest skill."""
        doc = _doc(
            tmp_path,
            "---\nrelated_skills: [python]\n---\n\n"
            "# Guide\n\n```python\n@pytest.fixture\ndef svc(): ...\n```\n",
        )
        assert find_skill_references_in_file(doc) == {"python"}

    def test_pasted_validator_output_is_not_a_link(self, tmp_path):
        """GIT_HOOKS.md documents this tool by pasting its output, which names skills."""
        doc = _doc(
            tmp_path,
            "---\ntitle: Hooks\n---\n\n# Hooks\n\n"
            "```\n🔵 STALE SKILLS (1):\n  @domain-route-config\n```\n",
        )
        assert find_skill_references_in_file(doc) == set()

    def test_generated_related_skills_section_does_not_add_edges(self, tmp_path):
        """The body section is a projection of frontmatter; only the source counts.

        Three docs in the tree already have a section that drifted from the field
        it was generated from — reading the body would import that staleness.
        """
        doc = _doc(
            tmp_path,
            "---\nrelated_skills: [fasthtml, pwa]\n---\n\n# PWA\n\n"
            "## Related Skills\n\n- [@fasthtml](../../.claude/skills/fasthtml/SKILL.md)\n",
        )
        assert find_skill_references_in_file(doc) == {"fasthtml", "pwa"}


class TestUnknownNamesSurviveForTheBrokenLinkCheck:
    def test_unregistered_name_is_returned_verbatim(self, tmp_path):
        """Filtering against the registry here is what made broken_link unreachable.

        The old reader kept only names already known to be valid, so the caller's
        "skill not found in metadata" branch could never fire. Returning the name
        as authored is what lets a retired skill (e.g. ``js-alpine``) be reported.
        """
        doc = _doc(tmp_path, "---\nrelated_skills: [js-alpine, fasthtml]\n---\n\n# Doc\n")
        assert find_skill_references_in_file(doc) == {"js-alpine", "fasthtml"}

    def test_non_string_entries_are_dropped(self, tmp_path):
        doc = _doc(tmp_path, "---\nrelated_skills: [fasthtml, 42, null]\n---\n\n# Doc\n")
        assert find_skill_references_in_file(doc) == {"fasthtml"}


# ============================================================================
# Skill staleness — a primary doc committed after the skill's last review
# ============================================================================


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    _git(tmp_path, "init", "-q", "-b", "main", str(root))
    return root


def _commit_doc(repo: Path, name: str, when: str) -> str:
    """Commit ``docs/<name>`` with ``when`` as its committer timestamp."""
    (repo / "docs" / name).write_text(f"# {name}\n\n{when}\n")
    _git(repo, "add", "-A")
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", name],
        check=True,
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": str(repo),
            "GIT_AUTHOR_DATE": when,
            "GIT_COMMITTER_DATE": when,
            "GIT_AUTHOR_NAME": "T",
            "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "T",
            "GIT_COMMITTER_EMAIL": "t@example.com",
        },
    )
    return f"/docs/{name}"


def _skill(last_reviewed: str, *primary_docs: str) -> dict:
    return {"name": "demo", "last_reviewed": last_reviewed, "primary_docs": list(primary_docs)}


class TestSkillStaleness:
    """A skill is stale when a primary doc's last commit falls on a later UTC day than
    its ``last_reviewed`` — the calendar the docs' ``updated:`` stamp uses."""

    def test_doc_changed_after_the_review_flags_the_skill(self, repo: Path) -> None:
        doc = _commit_doc(repo, "LATER.md", "2026-09-12T12:00:00+00:00")
        [issue] = check_skill_staleness(_skill("2026-09-10", doc), repo)
        assert issue.category == "stale_skill"
        assert "LATER.md (modified 2026-09-12)" in issue.message

    def test_doc_changed_before_the_review_does_not(self, repo: Path) -> None:
        doc = _commit_doc(repo, "EARLIER.md", "2026-09-08T12:00:00+00:00")
        assert check_skill_staleness(_skill("2026-09-10", doc), repo) == []

    def test_doc_changed_on_the_review_day_does_not(self, repo: Path) -> None:
        doc = _commit_doc(repo, "SAME.md", "2026-09-10T23:59:00+00:00")
        assert check_skill_staleness(_skill("2026-09-10", doc), repo) == []

    def test_the_day_is_the_utc_day_of_the_commit(self, repo: Path) -> None:
        """Dated as the docs' ``updated:`` stamp is — never the committer's local day.

        An evening commit west of UTC is already tomorrow in UTC, and a morning
        commit east of UTC is still yesterday.
        """
        west = _commit_doc(repo, "WEST.md", "2026-09-10T20:00:00-07:00")
        east = _commit_doc(repo, "EAST.md", "2026-09-11T08:00:00+09:00")
        assert get_doc_last_modified(west, repo) == date(2026, 9, 11)
        assert get_doc_last_modified(east, repo) == date(2026, 9, 10)
        assert check_skill_staleness(_skill("2026-09-10", east), repo) == []
        assert len(check_skill_staleness(_skill("2026-09-10", west), repo)) == 1

    def test_an_uncommitted_doc_has_no_day(self, repo: Path) -> None:
        (repo / "docs" / "NEW.md").write_text("# New\n")
        assert get_doc_last_modified("/docs/NEW.md", repo) is None
        assert check_skill_staleness(_skill("2026-09-10", "/docs/NEW.md"), repo) == []

    def test_a_malformed_review_date_is_reported_not_raised(self, repo: Path) -> None:
        doc = _commit_doc(repo, "LATER.md", "2026-09-12T12:00:00+00:00")
        [issue] = check_skill_staleness(_skill("Sept 10", doc), repo)
        assert issue.severity == "error"
        assert issue.category == "malformed_date"
