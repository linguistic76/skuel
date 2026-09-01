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
- no pattern doc's frontmatter fails the YAML parse:
  ``load_pattern_frontmatter`` swallows ``yaml.YAMLError`` per file, and 35
  docs in the corpus carry an unquoted ``title: … : …`` that is a YAML
  syntax error — one of those in docs/patterns/ would have its whole
  metadata, ``related_skills`` included, vanish from the index silently.
  This guard rejects the parse failure itself, which covers every spelling
  of every key at once.
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
    load_skills_metadata,
)

from core.utils.frontmatter import split_frontmatter


def _raw_frontmatter(doc_path: Path) -> str | None:
    """The raw frontmatter text, by the repo's canonical fence grammar.

    Deliberately the SAME extraction the generator uses — a stricter private
    grammar here silently skipped docs whose fences the canonical parser accepts
    (``--- `` trailing space, CRLF), exactly the docs the old generator dropped
    (Codex P2, PR #1213 round 6). A doc the canonical grammar rejects has no
    frontmatter anywhere in the repo's machinery, which is the stamper's and
    validator's own definition of the case.
    """
    raw, _body = split_frontmatter(doc_path.read_text(encoding="utf-8"))
    return raw


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
    """No doc path named in skills_metadata.yaml is dropped by category bucketing.

    Asserted inside the OWNING skill's ``### @skill`` section, not globally: the
    same path is emitted again under "By Document Category" (and by any other
    skill sharing it), so a whole-render substring stays green while this skill's
    own association is lost (Codex P2, PR #1213 round 7).
    """
    content = generate_index_content(PROJECT_ROOT)
    by_skill_part = content.split("## By Document Category")[0]
    sections: dict[str, str] = {}
    for chunk in re.split(r"^### @", by_skill_part, flags=re.MULTILINE)[1:]:
        name, _, body = chunk.partition("\n")
        sections[name.strip()] = body

    for skill in load_skills_metadata(PROJECT_ROOT)["skills"]:
        section = sections.get(skill["name"], "")
        for doc in skill.get("primary_docs", []) + skill.get("patterns", []):
            assert f"]({doc})" in section, (
                f"@{skill['name']} names {doc} in skills_metadata.yaml but its own "
                "rendered section never links it — a renderer bucket dropped it."
            )


def test_every_pattern_frontmatter_parses() -> None:
    """No pattern doc's frontmatter may fail the YAML parse.

    ``load_pattern_frontmatter`` swallows ``yaml.YAMLError`` per file, so an
    unparseable block makes the doc's ENTIRE metadata — ``related_skills`` in any
    of its legal spellings included — silently invisible to the generator, with
    the artifact still rendering "fresh". Guarding the declaration textually is an
    unwinnable enumeration (bare key, spaced colon, indented key, quoted key —
    Codex P2s, PR #1213 rounds 2/4/5); guarding the PRECONDITION of the loss is
    total: reject the parse failure itself, before anything is declared in it.
    Zero pattern docs fail today (the 35 unquoted-``title:`` docs in the corpus
    all live outside docs/patterns/), so this is enforceable now. Every other
    swallow shape is already loud: a block parsing to a non-mapping crashes
    ``generate_index_content`` on ``.get``, which errors the freshness test.
    """
    for doc_path in sorted((PROJECT_ROOT / "docs" / "patterns").rglob("*.md")):
        raw = _raw_frontmatter(doc_path)
        if raw is None:
            continue
        try:
            yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            raise AssertionError(
                f"{doc_path.name} has unparseable frontmatter — its metadata is "
                "silently invisible to generate_cross_reference_index.py (an "
                "unquoted colon in title: is the known shape). Fix the YAML: "
                f"{exc}"
            ) from exc


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
    patterns_dir = PROJECT_ROOT / "docs" / "patterns"
    for doc_path in sorted(patterns_dir.rglob("*.md")):
        raw = _raw_frontmatter(doc_path)
        if raw is None:
            continue
        try:
            frontmatter = yaml.safe_load(raw) or {}
        except yaml.YAMLError:
            continue
        declared = _normalize_related_skills(frontmatter.get("related_skills"))
        if not declared:
            continue
        mapping = rendered.get(str(doc_path.relative_to(patterns_dir)), "")
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
