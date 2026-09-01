"""
Drift + honesty guards for docs/CROSS_REFERENCE_INDEX.md
========================================================

Same pattern as test_generate_method_index.py: the artifact is a checked-in
generated view whose freshness is enforced by byte-comparing it against a
fresh render. There is no commit-time automation — deliberately (see the
generator's docstring); enforcement is this file, run by BOTH unit_tests and
CI's validate_documentation job — the latter because every generator input is
doc-side and a docs-only PR skips unit_tests, and it runs the full file
rather than a ``--check`` byte-compare because the honesty guards catch
corruption that renders "fresh" (Codex P2 x2, PR #1213). Before this,
nothing compared the checked-in file against its sources
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

import yaml
from generate_cross_reference_index import (  # type: ignore[import-not-found]
    ARTIFACT_PATH,
    PROJECT_ROOT,
    _normalize_related_skills,
    generate_index_content,
    load_pattern_frontmatter,
    load_skills_metadata,
)


def _frontmatter_block(doc_path: Path) -> list[str] | None:
    """The raw frontmatter lines, extracted independently of the generator's pipeline."""
    lines = doc_path.read_text(encoding="utf-8").split("\n")
    if lines[0] != "---" or "---" not in lines[1:]:
        return None
    return lines[1 : lines[1:].index("---") + 1]


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
        block = _frontmatter_block(doc_path)
        if block is None or not any(line.startswith("related_skills:") for line in block):
            continue
        assert doc_path.name in parsed, (
            f"{doc_path.name} declares related_skills: but load_pattern_frontmatter "
            "dropped it — almost certainly a YAML syntax error elsewhere in its "
            "frontmatter (an unquoted colon in title: is the known shape). Its "
            "skills would silently vanish from the index."
        )


def test_declared_skills_render_in_pattern_mapping() -> None:
    """Every skill a pattern doc declares appears, whole, in its rendered mapping line.

    The corruption this pins: ``related_skills: fasthtml`` (the scalar form the
    cross-reference validator explicitly supports) fed to ``list.extend()`` renders one
    phantom skill per CHARACTER — and the freshness test stays green over the corrupted
    artifact, because a wrong render is faithfully wrong twice (Codex P2, PR #1213).
    The declared set is re-derived here with an independent frontmatter parse.
    """
    content = generate_index_content(PROJECT_ROOT)
    rendered: dict[str, str] = {}
    for line in content.splitlines():
        match = re.match(r"^- \[([^\]]+)\]\(/docs/patterns/[^)]+\) → (.+)$", line)
        if match:
            rendered[match.group(1)] = match.group(2)

    checked = 0
    for doc_path in sorted((PROJECT_ROOT / "docs" / "patterns").glob("*.md")):
        block = _frontmatter_block(doc_path)
        if block is None:
            continue
        try:
            frontmatter = yaml.safe_load("\n".join(block)) or {}
        except yaml.YAMLError:
            continue
        declared = _normalize_related_skills(frontmatter.get("related_skills"))
        if not declared:
            continue
        mapping = rendered.get(doc_path.name, "")
        rendered_skills = {chunk.strip().removeprefix("@") for chunk in mapping.split(",")}
        for skill in declared:
            checked += 1
            assert skill in rendered_skills, (
                f"{doc_path.name} declares related_skills {declared} but its rendered "
                f"mapping line reads {mapping!r} — the declared name is not there whole "
                "(a per-character split renders '@f, @a, …')."
            )
    assert checked > 0, "guard checked nothing — no pattern doc declares related_skills?"


def test_normalize_related_skills_forms() -> None:
    """Scalar wraps, list passes, non-string members and junk drop — the validator's shape."""
    assert _normalize_related_skills("fasthtml") == ["fasthtml"]
    assert _normalize_related_skills(["fasthtml", "pytest"]) == ["fasthtml", "pytest"]
    assert _normalize_related_skills(["fasthtml", 3, None]) == ["fasthtml"]
    assert _normalize_related_skills(None) == []
    assert _normalize_related_skills({"not": "a list"}) == []
