#!/usr/bin/env python3
"""Content-boundary guard — keep proprietary vault content out of the PUBLIC repo.

SKUEL's principle: **the repo carries the machinery and the mechanism; the vault
carries the content and the ontology.** Code, ADRs, and technical patterns are public;
Kus, PathSteps, taxonomies, and per-user vault mirrors are private and live under
``~/0bsidian`` (or the gitignored ``data/user_vaults`` staging mirror), never on GitHub.

This is the enforced backstop to that discipline (``.gitignore`` is the first line).
It fails if any *tracked* file:

1. sits under a forbidden path prefix (``docs/content/``, ``data/user_vaults/``,
   ``data/staging/``, ``yaml_templates/``), or
2. IS a vault entity — a Markdown/YAML file whose leading frontmatter declares a
   content ``type:`` (Ku, PathStep, Exercise, LearningPath, Resource, *Template).
   Structural, not heuristic: the frontmatter must be at file start, so fenced
   ``yaml`` examples inside docs never match.

Run: ``uv run python scripts/audit_content_boundary.py`` (also wired into
``./dev quality`` and asserted by ``tests/unit/test_content_boundary.py`` so the CI
gate enforces it). Exit 0 = clean, 1 = violations.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Tracked paths (relative to app/) that must never hold committed content.
FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "docs/content/",
    "data/user_vaults/",
    "data/staging/",
    "yaml_templates/",
)

# Binary archives can smuggle a whole vault export past the text-based type checks
# (a .zip isn't Markdown/YAML), so tracked archives are rejected as content carriers.
ARCHIVE_SUFFIXES: tuple[str, ...] = (".zip", ".tar", ".gz", ".tgz", ".bz2", ".7z", ".rar")
# Exact-path allowlist for the one intentional public archive (the empty vault
# template users download). Deliberately NOT a prefix: a new archive anywhere else,
# including elsewhere under static/, is flagged. Add a path here only for a reviewed,
# genuinely-public bundle.
ALLOWED_ARCHIVES: frozenset[str] = frozenset({"static/templates/activity-vault-template.zip"})

# ``type:`` values that mark a file as an ingestible vault entity — the full vault
# surface, not just curriculum, so no authoring shape slips through. Lowercased for
# comparison. Kept as a curated literal (this guard runs on bare Python in CI, so it
# must not import the EntityType enum); extend it when a new authorable type appears.
CONTENT_TYPES: frozenset[str] = frozenset(
    {
        # Curriculum
        "ku",
        "knowledge",
        "knowledgeunit",
        "knowledgecluster",
        "pathstep",
        "learningpath",
        "exercise",
        "revisedexercise",
        "resource",
        # Activity domains
        "task",
        "goal",
        "habit",
        "event",
        "choice",
        "principle",
        # Activity templates
        "tasktemplate",
        "goaltemplate",
        "habittemplate",
        "eventtemplate",
        "choicetemplate",
        "principletemplate",
        # Learning loop / other authorable entities
        "userentry",
        "entryreport",
        "activityreport",
        "interaction",
        "lifepath",
        "formtemplate",
        "formsubmission",
        "conversation",
        # Ingestion aliases (core/services/ingestion/detector.py TYPE_MAPPING),
        # relationship configs, and non-Ku domains — all normalized (see below).
        "lesson",
        "learningstep",
        "lp",
        "ps",
        "ia",
        "edge",
        "expense",
        "finance",
        "group",
        # Remaining EntityType.from_string() aliases (entity_enums._ENTITY_TYPE_ALIASES)
        # so the guard is a superset of the ingestion vocabulary. Completeness is
        # enforced by test_guard_covers_ingestion_aliases (fails if ingestion drifts).
        "book",
        "film",
        "talk",
        "form",
        "path",
        "step",
        "ue",
        # Legacy USER_ENTRY aliases: ingestion REJECTS these, but a tracked file
        # carrying one is unambiguously vault content, so flag it anyway.
        "jeinput",
        "jeoutput",
        "exercisesubmission",
    }
)


def _normalize_type(raw: str) -> str:
    """Normalize a ``type:`` value to the concatenated form used in CONTENT_TYPES,
    so snake_case / kebab / alias spellings all collapse to one key (e.g.
    ``user_entry`` → ``userentry``, ``path_step`` → ``pathstep``)."""
    return raw.strip().lower().replace("_", "").replace("-", "").replace(" ", "")


_FRONTMATTER = re.compile(r"^﻿?---\s*\n(.*?)\n---\s*\n", re.DOTALL)
# Captures spaced display-names too ("Path Step", "Learning Path") — ingestion's
# EntityType.from_string() normalizes spaces/hyphens, so the guard must as well.
# ``\s*`` before the colon: PyYAML accepts ``type : Ku`` / ``moc : true``, so the
# guard must too, or that spacing would bypass it.
_TYPE_FIELD = re.compile(r"^type\s*:\s*[\"']?([A-Za-z][A-Za-z _-]*)", re.MULTILINE | re.IGNORECASE)
# A markdown file with `moc: true` is classified as a PathStep by the ingestion
# detector even without a `type:` field — so it is vault content too.
_MOC_FLAG = re.compile(r"^moc\s*:\s*true\s*$", re.MULTILINE | re.IGNORECASE)


def _tracked_files() -> list[str]:
    out = subprocess.check_output(["git", "ls-files"], cwd=REPO_ROOT, text=True)
    return out.splitlines()


def _looks_like_vault_entity(path: Path) -> str | None:
    """Return the offending ``type`` value if the file is a content entity, else None.

    Covers both authoring shapes SKUEL ingests:
    - Markdown (``.md``): a leading ``---`` frontmatter block (PathSteps, MD Kus).
      Requiring the fence avoids false positives from ```yaml examples in doc prose.
    - Plain YAML (``.yaml``/``.yml``): the whole file IS the document (YAML Kus, LP,
      edges), so a top-level ``type:`` is inspected directly — no fence exists.
    """
    suffix = path.suffix.lower()
    if suffix not in (".md", ".yaml", ".yml"):
        return None
    try:
        head = path.read_text(encoding="utf-8", errors="ignore")[:4000]
    except OSError:
        return None

    if suffix == ".md":
        fm = _FRONTMATTER.match(head)
        scope = fm.group(1) if fm else None
    else:
        # A whole YAML file is the document; top-level `type:` may follow comments.
        scope = head

    if scope is None:
        return None
    tm = _TYPE_FIELD.search(scope)
    if tm and _normalize_type(tm.group(1)) in CONTENT_TYPES:
        return tm.group(1).strip()
    # MOC markdown: ingestion classifies `moc: true` frontmatter as a PathStep
    # even with no `type:` field, so it is vault content in its own right.
    if suffix == ".md" and _MOC_FLAG.search(scope):
        return "PathStep (moc: true)"
    return None


def find_violations() -> list[str]:
    """Return human-readable violation lines (empty = clean)."""
    violations: list[str] = []
    for rel in _tracked_files():
        if rel.startswith(FORBIDDEN_PREFIXES):
            violations.append(f"{rel}: under a forbidden content path prefix")
            continue
        if rel.lower().endswith(ARCHIVE_SUFFIXES) and rel not in ALLOWED_ARCHIVES:
            violations.append(
                f"{rel}: tracked archive may carry a vault export past the text checks "
                f"— add to ALLOWED_ARCHIVES only if it is a reviewed public bundle"
            )
            continue
        entity_type = _looks_like_vault_entity(REPO_ROOT / rel)
        if entity_type:
            violations.append(
                f"{rel}: leading frontmatter declares content type '{entity_type}' "
                f"— vault content does not belong in this repo"
            )
    return violations


def main() -> int:
    violations = find_violations()
    if violations:
        print("❌ Content-boundary guard FAILED — proprietary content in the repo:\n")
        for v in violations:
            print(f"  • {v}")
        print(
            "\nThe repo is PUBLIC. Move vault content/ontology into the private vault "
            "(~/0bsidian) and keep only mechanism-level docs here.\n"
            "See docs/patterns/NOUS_SUBTOPIC_FACET.md for the pattern."
        )
        return 1
    print("✅ Content-boundary guard passed — no vault content tracked in the repo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
