#!/usr/bin/env python3
"""
Generate CROSS_REFERENCE_INDEX.md from skills metadata and pattern frontmatter.

This script creates a comprehensive bidirectional mapping between skills and docs.

The output is a pure function of its two sources — ``.claude/skills/skills_metadata.yaml``
and ``docs/patterns/*.md`` frontmatter — with no timestamps, so the drift test can
regenerate and byte-compare it
(``tests/unit/scripts/test_generate_cross_reference_index.py``). There is NO commit-time
automation, deliberately: ``generate_method_index.py``'s original docstring claimed a
pre-commit hook that was never wired, which is exactly how that artifact silently sat
stale — CI failing on a stale artifact is the enforcement path, in two halves matching
the CI path filters: unit_tests runs the drift-test file when the ``py`` filter fires
(generator edits), and ``validate_documentation`` runs the SAME file when doc-side
inputs change (a docs-only PR skips unit_tests entirely, and a bare ``--check`` cannot
see doc-side corruption that renders "fresh" — Codex P2 x2, PR #1213). ``--check``
remains for local/manual use.

Usage:
    uv run python scripts/generate_cross_reference_index.py          # regenerate
    uv run python scripts/generate_cross_reference_index.py --check  # exit 1 on drift
"""

import argparse
import os
import sys
from operator import itemgetter
from pathlib import Path
from typing import Any

import yaml
from adr_links import (  # type: ignore[import-not-found]
    adr_display,
    adr_sort_key,
    resolve_adr_filename,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_PATH = PROJECT_ROOT / "docs" / "CROSS_REFERENCE_INDEX.md"

sys.path.insert(0, str(PROJECT_ROOT))

from core.utils.frontmatter import split_frontmatter


def _normalize_related_skills(value: object) -> list[str]:
    """Frontmatter ``related_skills`` as a list of names, whatever form it was authored in.

    The scalar form (``related_skills: fasthtml``) is a supported authoring shape —
    ``validate_cross_references.py`` tolerates it explicitly — and ``list.extend()`` on
    that string iterates CHARACTERS, rendering one phantom skill per letter (``@f, @a,
    …``) with the freshness test green over the corrupted artifact (Codex P2, PR #1213).
    Mirrors the validator's normalization: scalar wraps, non-string members drop.
    """
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list):
        return []
    return [name for name in value if isinstance(name, str)]


def load_skills_metadata(base_path: Path) -> dict[str, Any]:
    """Load skills metadata from YAML."""
    metadata_file = base_path / ".claude" / "skills" / "skills_metadata.yaml"
    with metadata_file.open() as f:
        return yaml.safe_load(f)


def load_pattern_frontmatter(base_path: Path) -> dict[str, dict[str, Any]]:
    """Load frontmatter from all pattern docs.

    Fence grammar comes from the repo's canonical parser (``split_frontmatter``),
    not a local regex: a private strict grammar silently skipped docs whose fences
    the rest of the repo accepts (``--- `` trailing space, CRLF), losing their
    ``related_skills`` from the index while the artifact rendered "fresh" (Codex
    P2, PR #1213 round 6). A YAML-failed block is skipped here and rejected by the
    drift test's honesty guard, which shares this extraction.

    Traversal is recursive and keys are paths RELATIVE to docs/patterns/ (flat
    docs keep their bare filename): ``glob("*.md")`` made subdirectory patterns
    (``curriculum/…``) invisible, and a bare-filename key could collide across
    subdirectories and emits the wrong link for them (Codex P2, PR #1213 round 7).
    """
    patterns_dir = base_path / "docs" / "patterns"
    pattern_data = {}

    for doc_path in patterns_dir.rglob("*.md"):
        raw, _body = split_frontmatter(doc_path.read_text())
        if raw is None:
            continue

        try:
            frontmatter = yaml.safe_load(raw)
            pattern_data[str(doc_path.relative_to(patterns_dir))] = frontmatter
        except yaml.YAMLError:
            pass

    return pattern_data


def doc_link(target: str) -> str:
    """``target`` as this artifact cites it.

    A docs→docs link is written relative to the citing file (the vault rule —
    ``scripts/docs_relative_links.py``), and this index lives at the root of ``docs/``,
    so ``/docs/architecture/X.md`` becomes ``architecture/X.md``. A target outside
    ``docs/`` (``/monitoring/README.md``) keeps its repo-root-absolute spelling.
    """
    if not target.startswith("/docs/"):
        return target
    return os.path.relpath(PROJECT_ROOT / target.lstrip("/"), ARTIFACT_PATH.parent)


def generate_index_content(base_path: Path) -> str:
    """Generate the cross-reference index content."""
    skills_data = load_skills_metadata(base_path)
    pattern_data = load_pattern_frontmatter(base_path)
    decisions_dir = base_path / "docs" / "decisions"

    content = ["# Cross-Reference Index: Skills ↔ Documentation"]
    content.append("")
    content.append(
        "**Purpose:** Single source of truth for bidirectional skill-documentation mapping."
    )
    content.append("")
    content.append(
        "**Generated:** This file is auto-generated from `skills_metadata.yaml` and pattern doc frontmatter."
    )
    content.append("**Regenerate:** Run `uv run python scripts/generate_cross_reference_index.py`")
    content.append("")
    content.append("---")
    content.append("")

    # Part 1: By Skill
    content.append("## By Skill")
    content.append("")
    content.append(
        "For each skill, this section shows all related documentation (architecture docs, patterns, ADRs)."
    )
    content.append("")

    for skill in sorted(skills_data["skills"], key=itemgetter("name")):
        name = skill["name"]
        description = skill.get("description", "")
        primary_docs = skill.get("primary_docs", [])
        patterns = skill.get("patterns", [])
        related_adrs = skill.get("related_adrs", [])

        content.append(f"### @{name}")
        content.append("")
        content.append(f"**Description:** {description}")
        content.append("")

        if primary_docs:
            # Categorize primary docs
            arch_docs = [d for d in primary_docs if "/docs/architecture/" in d]
            pattern_docs = [d for d in primary_docs if "/docs/patterns/" in d]
            guide_docs = [d for d in primary_docs if "/docs/guides/" in d]
            intel_docs = [d for d in primary_docs if "/docs/intelligence/" in d]
            domain_docs = [d for d in primary_docs if "/docs/domains/" in d]
            other_docs = [
                d
                for d in primary_docs
                if d not in arch_docs + pattern_docs + guide_docs + intel_docs + domain_docs
            ]

            if arch_docs:
                content.append("**Architecture:**")
                for doc in arch_docs:
                    doc_name = doc.split("/")[-1]
                    content.append(f"- [{doc_name}]({doc_link(doc)})")
                content.append("")

            if intel_docs:
                content.append("**Intelligence:**")
                for doc in intel_docs:
                    doc_name = doc.split("/")[-1]
                    content.append(f"- [{doc_name}]({doc_link(doc)})")
                content.append("")

            if pattern_docs:
                content.append("**Patterns (Primary):**")
                for doc in pattern_docs:
                    doc_name = doc.split("/")[-1]
                    content.append(f"- [{doc_name}]({doc_link(doc)})")
                content.append("")

            if guide_docs:
                content.append("**Guides:**")
                for doc in guide_docs:
                    doc_name = doc.split("/")[-1]
                    content.append(f"- [{doc_name}]({doc_link(doc)})")
                content.append("")

            if domain_docs:
                content.append("**Domain Docs:**")
                for doc in domain_docs:
                    doc_name = doc.split("/")[-1]
                    content.append(f"- [{doc_name}]({doc_link(doc)})")
                content.append("")

            if other_docs:
                content.append("**Other:**")
                for doc in other_docs:
                    doc_name = doc.split("/")[-1]
                    content.append(f"- [{doc_name}]({doc_link(doc)})")
                content.append("")

        if patterns:
            content.append("**Patterns (Additional):**")
            for doc in patterns:
                doc_name = doc.split("/")[-1]
                content.append(f"- [{doc_name}]({doc_link(doc)})")
            content.append("")

        if related_adrs:
            content.append("**ADRs:**")
            for adr in related_adrs:
                adr_file = resolve_adr_filename(adr, decisions_dir)
                adr_path = f"/docs/decisions/{adr_file}"
                content.append(f"- [{adr_display(adr)}]({doc_link(adr_path)})")
            content.append("")

        if not primary_docs and not patterns and not related_adrs:
            content.append("*No documentation links yet.*")
            content.append("")

    # Part 2: By Document Category
    content.append("---")
    content.append("")
    content.append("## By Document Category")
    content.append("")
    content.append("For each documentation category, this section shows which skills are relevant.")
    content.append("")

    # 2.1: Architecture Docs
    content.append("### Architecture Docs")
    content.append("")

    arch_to_skills: dict[str, list[str]] = {}
    for skill in skills_data["skills"]:
        for doc in skill.get("primary_docs", []):
            if "/docs/architecture/" in doc:
                doc_name = doc.split("/")[-1]
                if doc_name not in arch_to_skills:
                    arch_to_skills[doc_name] = []
                arch_to_skills[doc_name].append(skill["name"])

    for doc_name in sorted(arch_to_skills.keys()):
        skills = sorted(set(arch_to_skills[doc_name]))
        skills_str = ", ".join(f"@{s}" for s in skills)
        doc_path = f"/docs/architecture/{doc_name}"
        content.append(f"- [{doc_name}]({doc_link(doc_path)}) → {skills_str}")

    content.append("")

    # 2.2: Intelligence Docs
    content.append("### Intelligence Docs")
    content.append("")

    intel_to_skills: dict[str, list[str]] = {}
    for skill in skills_data["skills"]:
        for doc in skill.get("primary_docs", []):
            if "/docs/intelligence/" in doc:
                doc_name = doc.split("/")[-1]
                if doc_name not in intel_to_skills:
                    intel_to_skills[doc_name] = []
                intel_to_skills[doc_name].append(skill["name"])

    for doc_name in sorted(intel_to_skills.keys()):
        skills = sorted(set(intel_to_skills[doc_name]))
        skills_str = ", ".join(f"@{s}" for s in skills)
        doc_path = f"/docs/intelligence/{doc_name}"
        content.append(f"- [{doc_name}]({doc_link(doc_path)}) → {skills_str}")

    content.append("")

    # 2.3: Pattern Docs
    content.append("### Pattern Docs")
    content.append("")

    pattern_to_skills: dict[str, list[str]] = {}

    # From skills metadata (primary_docs + patterns). Keyed by the path relative
    # to docs/patterns/ — the same key load_pattern_frontmatter uses — so a
    # subdirectory doc named by both sources merges instead of forking.
    for skill in skills_data["skills"]:
        for doc in skill.get("primary_docs", []) + skill.get("patterns", []):
            if "/docs/patterns/" in doc:
                doc_name = doc.split("/docs/patterns/", 1)[1]
                if doc_name not in pattern_to_skills:
                    pattern_to_skills[doc_name] = []
                pattern_to_skills[doc_name].append(skill["name"])

    # From pattern frontmatter
    for doc_name, frontmatter in pattern_data.items():
        related_skills = _normalize_related_skills(frontmatter.get("related_skills"))
        if doc_name not in pattern_to_skills:
            pattern_to_skills[doc_name] = []
        pattern_to_skills[doc_name].extend(related_skills)

    for doc_name in sorted(pattern_to_skills.keys()):
        skills = sorted(set(pattern_to_skills[doc_name]))
        if not skills:
            continue
        skills_str = ", ".join(f"@{s}" for s in skills)
        doc_path = f"/docs/patterns/{doc_name}"
        content.append(f"- [{doc_name}]({doc_link(doc_path)}) → {skills_str}")

    content.append("")

    # 2.4: ADRs
    content.append("### ADRs (Architecture Decision Records)")
    content.append("")

    # Keyed by the RESOLVED filename, not the authored ref: two skills may now spell
    # one ADR differently (a bare number and a full filename both resolve), and
    # keying on the spelling would render that single ADR as two rows.
    adr_to_skills: dict[str, list[str]] = {}
    for skill in skills_data["skills"]:
        for adr in skill.get("related_adrs", []):
            adr_file = resolve_adr_filename(adr, decisions_dir)
            if adr_file not in adr_to_skills:
                adr_to_skills[adr_file] = []
            adr_to_skills[adr_file].append(skill["name"])

    for adr_file in sorted(adr_to_skills.keys(), key=adr_sort_key):
        skills = sorted(set(adr_to_skills[adr_file]))
        skills_str = ", ".join(f"@{s}" for s in skills)
        adr_path = f"/docs/decisions/{adr_file}"
        content.append(f"- [{adr_display(adr_file)}]({doc_link(adr_path)}) → {skills_str}")

    content.append("")

    # Statistics
    content.append("---")
    content.append("")
    content.append("## Statistics")
    content.append("")
    content.append(f"- **Total skills:** {len(skills_data['skills'])}")
    content.append(f"- **Architecture docs:** {len(arch_to_skills)} docs linked to skills")
    content.append(f"- **Intelligence docs:** {len(intel_to_skills)} docs linked to skills")
    content.append(
        f"- **Pattern docs:** {len([d for d in pattern_to_skills if pattern_to_skills[d]])} docs linked to skills"
    )
    content.append(f"- **ADRs:** {len(adr_to_skills)} ADRs linked to skills")
    content.append("")

    # Footer
    content.append("---")
    content.append("")
    content.append("## Maintenance")
    content.append("")
    content.append("**When to Update:**")
    content.append("- After adding a new skill")
    content.append("- After creating a new pattern doc")
    content.append("- After writing a new ADR")
    content.append("- After updating skills_metadata.yaml")
    content.append("")
    content.append("**How to Update:**")
    content.append("```bash\nuv run python scripts/generate_cross_reference_index.py\n```")
    content.append("")
    content.append("**Related Files:**")
    content.append("- `.claude/skills/skills_metadata.yaml` - Machine-readable metadata")
    content.append("- `docs/patterns/*.md` - Pattern doc frontmatter")
    content.append("- `scripts/generate_cross_reference_index.py` - This generator script")
    content.append("")

    return "\n".join(content)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Generate docs/CROSS_REFERENCE_INDEX.md")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if the checked-in artifact differs from a fresh render (no write).",
    )
    args = parser.parse_args()

    content = generate_index_content(PROJECT_ROOT)

    if args.check:
        on_disk = ARTIFACT_PATH.read_text(encoding="utf-8") if ARTIFACT_PATH.exists() else ""
        if on_disk != content:
            print("❌ CROSS_REFERENCE_INDEX.md is stale.")
            print(
                "   Regenerate: cd app && uv run python scripts/generate_cross_reference_index.py"
            )
            return 1
        print("✅ CROSS_REFERENCE_INDEX.md is fresh.")
        return 0

    ARTIFACT_PATH.write_text(content, encoding="utf-8")
    print(f"✅ Generated: {ARTIFACT_PATH}")
    print(f"   Lines: {len(content.splitlines())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
