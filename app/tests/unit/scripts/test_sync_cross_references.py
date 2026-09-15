"""Writer tests for scripts/sync_cross_references.py.

The script rewrites docs, so its output shape is the contract: the body after the
closing frontmatter fence is preserved verbatim (that blank line included), a new
``## Related Skills`` block is set off by exactly one blank line on each side, a
replaced block is bounded by its own shape so anything the doc keeps between it and
the next heading (a ``---`` rule) survives, a block that already matches its
frontmatter is reported as skipped rather than rewritten, and ``ADR-TEMPLATE.md``
is never walked — a block rendered into the template would be copied into every
ADR authored from it.
"""

from __future__ import annotations

import sys
from pathlib import Path

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from sync_cross_references import (  # type: ignore[import-not-found]
    get_docs_to_process,
    sync_doc_cross_references,
)

BLOCK = (
    "## Related Skills\n"
    "\n"
    "For implementation guidance, see:\n"
    "- [@fasthtml](../../.claude/skills/fasthtml/SKILL.md)\n"
)


def _doc(tmp_path: Path, body: str, name: str = "DOC.md") -> Path:
    path = tmp_path / name
    path.write_text(body)
    return path


class TestInsertingANewBlock:
    def test_blank_line_after_the_fence_survives(self, tmp_path):
        doc = _doc(
            tmp_path,
            "---\nrelated_skills: [fasthtml]\n---\n\n# Title\n\nIntro.\n\n## Context\n\nBody.\n",
        )
        sync_doc_cross_references(doc, dry_run=False)
        assert doc.read_text().startswith("---\nrelated_skills: [fasthtml]\n---\n\n# Title\n")

    def test_block_is_set_off_by_exactly_one_blank_line_each_side(self, tmp_path):
        doc = _doc(
            tmp_path,
            "---\nrelated_skills: [fasthtml]\n---\n\n# Title\n\nIntro.\n\n## Context\n\nBody.\n",
        )
        sync_doc_cross_references(doc, dry_run=False)
        assert doc.read_text() == (
            "---\nrelated_skills: [fasthtml]\n---\n\n# Title\n\nIntro.\n\n"
            + BLOCK
            + "\n## Context\n\nBody.\n"
        )


class TestReplacingAnExistingBlock:
    def test_a_rule_between_the_block_and_the_next_heading_is_kept(self, tmp_path):
        stale = BLOCK.replace("fasthtml", "pwa")
        doc = _doc(
            tmp_path,
            "---\nrelated_skills: [fasthtml]\n---\n\n# Title\n\n"
            + stale
            + "\n---\n\n## Next\n\nBody.\n",
        )
        sync_doc_cross_references(doc, dry_run=False)
        assert doc.read_text() == (
            "---\nrelated_skills: [fasthtml]\n---\n\n# Title\n\n"
            + BLOCK
            + "\n---\n\n## Next\n\nBody.\n"
        )

    def test_a_block_that_already_matches_is_skipped(self, tmp_path):
        content = (
            "---\nrelated_skills: [fasthtml]\n---\n\n# Title\n\n" + BLOCK + "\n## Next\n\nBody.\n"
        )
        doc = _doc(tmp_path, content)
        update = sync_doc_cross_references(doc, dry_run=True)
        assert update.status == "skipped"
        assert update.has_changes is False
        assert doc.read_text() == content


class TestTheWalk:
    def test_the_adr_template_is_never_rendered_into(self, tmp_path):
        decisions = tmp_path / "docs" / "decisions"
        decisions.mkdir(parents=True)
        (decisions / "ADR-TEMPLATE.md").write_text("---\nrelated_skills: [x]\n---\n# T\n")
        (decisions / "ADR-001-real.md").write_text("---\nrelated_skills: [x]\n---\n# R\n")
        names = {p.name for p in get_docs_to_process(tmp_path, "decisions", None)}
        assert names == {"ADR-001-real.md"}
