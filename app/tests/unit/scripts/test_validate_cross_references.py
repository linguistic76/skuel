"""Reader tests for scripts/validate_cross_references.py.

The validator once regexed ``@([a-z0-9-]+)`` out of doc *bodies* while the repo
declared its doc→skill links in ``related_skills:`` frontmatter, so the two
halves of the cross-reference system never met: a doc could carry
``related_skills: [activity-domains]`` and still be reported as not referencing
that skill. These pin the canonical field as the one that is read, and prose as
the one that is not.
"""

from __future__ import annotations

import sys
from pathlib import Path

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from validate_cross_references import (  # type: ignore[import-not-found]
    find_skill_references_in_file,
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
