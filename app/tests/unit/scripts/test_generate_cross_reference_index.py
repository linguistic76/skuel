"""
Drift + honesty guards for docs/CROSS_REFERENCE_INDEX.md
========================================================

Same pattern as test_generate_method_index.py: the artifact is a checked-in
generated view whose freshness is enforced by byte-comparing it against a
fresh render. There is no commit-time automation — deliberately (see the
generator's docstring); enforcement is this test plus the ``--check`` step in
CI's validate_documentation job, which covers the doc-side inputs a docs-only
PR can change while skipping unit_tests (Codex P2, PR #1213). Before either
existed, nothing compared the checked-in file against its sources
(``.claude/skills/skills_metadata.yaml`` + ``docs/patterns/*.md``
frontmatter), so the index could drift indefinitely — the gap #1212 recorded
when it excluded this file from the ``updated:`` guard.

The honesty guards pin the properties the index exists to provide:

- every skill in ``skills_metadata.yaml`` renders a ``### @skill`` section
  (a new skill cannot be silently omitted),
- every doc path the metadata names survives the renderer's category
  bucketing (the ``other_docs`` catch-all is a construction, not a law — a
  doc in a new directory must land somewhere, never vanish), and
- a pattern doc that declares ``related_skills:`` is actually represented:
  ``load_pattern_frontmatter`` swallows ``yaml.YAMLError`` per file, and 35
  docs in the corpus carry an unquoted ``title: … : …`` that is a YAML
  syntax error — the moment one of those gains ``related_skills:``, its
  half of the bidirectional mapping would vanish silently. This guard turns
  that silent loss into a red test.
"""

import re
import sys
from pathlib import Path

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from generate_cross_reference_index import (  # type: ignore[import-not-found]
    ARTIFACT_PATH,
    PROJECT_ROOT,
    generate_index_content,
    load_pattern_frontmatter,
    load_skills_metadata,
)


def test_artifact_is_fresh() -> None:
    """The checked-in markdown must byte-match a fresh render of its sources."""
    assert ARTIFACT_PATH.exists(), (
        f"{ARTIFACT_PATH} is missing. "
        "Generate it: cd app && uv run python scripts/generate_cross_reference_index.py"
    )
    assert ARTIFACT_PATH.read_text(encoding="utf-8") == generate_index_content(PROJECT_ROOT), (
        "docs/CROSS_REFERENCE_INDEX.md is stale — skills_metadata.yaml or a "
        "pattern doc's frontmatter changed without regenerating the view. "
        "Run: cd app && uv run python scripts/generate_cross_reference_index.py"
    )


def test_every_skill_renders_a_section() -> None:
    """The ``### @skill`` sections mirror skills_metadata.yaml exactly."""
    metadata_names = {skill["name"] for skill in load_skills_metadata(PROJECT_ROOT)["skills"]}
    rendered_names = set(
        re.findall(r"^### @(\S+)$", generate_index_content(PROJECT_ROOT), re.MULTILINE)
    )
    assert rendered_names == metadata_names


def test_every_metadata_doc_link_survives_rendering() -> None:
    """No doc path named in skills_metadata.yaml is dropped by category bucketing."""
    content = generate_index_content(PROJECT_ROOT)
    for skill in load_skills_metadata(PROJECT_ROOT)["skills"]:
        for doc in skill.get("primary_docs", []) + skill.get("patterns", []):
            assert f"]({doc})" in content, (
                f"@{skill['name']} names {doc} in skills_metadata.yaml but the "
                "rendered index never links it — a renderer bucket dropped it."
            )


def test_related_skills_frontmatter_never_silently_swallowed() -> None:
    """A pattern doc declaring ``related_skills:`` must survive the YAML parse.

    Deliberately re-derives "declares related_skills" from the raw text with an
    independent scan rather than the generator's own regex + yaml pipeline — the
    whole point is to catch a doc that pipeline dropped.
    """
    parsed = load_pattern_frontmatter(PROJECT_ROOT)
    for doc_path in sorted((PROJECT_ROOT / "docs" / "patterns").glob("*.md")):
        lines = doc_path.read_text(encoding="utf-8").split("\n")
        if lines[0] != "---" or "---" not in lines[1:]:
            continue
        block = lines[1 : lines[1:].index("---") + 1]
        if not any(line.startswith("related_skills:") for line in block):
            continue
        assert doc_path.name in parsed, (
            f"{doc_path.name} declares related_skills: but load_pattern_frontmatter "
            "dropped it — almost certainly a YAML syntax error elsewhere in its "
            "frontmatter (an unquoted colon in title: is the known shape). Its "
            "skills would silently vanish from the index."
        )
