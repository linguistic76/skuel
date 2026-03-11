---
title: Codebase Health Checks
updated: 2026-03-04
status: current
category: tools
tags: [health, scripts, dead-code, documentation, maintenance, drift]
related: [AUTOMATIC_DOCS_CHECK.md]
---

# Codebase Health Checks

**Status:** ✅ Active
**Date Added:** 2026-03-03
**Location:** `scripts/health/`

## Overview

Four automated checks that prevent codebase drift — the kind that accumulates silently between refactors: orphaned files, broken doc links, stale names in documentation examples, and skill↔doc cross-reference inconsistencies.

```bash
./dev health              # run all four checks
./dev health-modules      # dead Python modules only
./dev health-links        # broken doc links only
./dev health-names        # stale identifiers in docs only
./dev health-xref         # cross-reference + staleness only
```

All four exit non-zero when issues are found, so they can be used in CI.

---

## The Four Checks

### 1. `dead_modules.py` — Zero-Importer Python Files

Scans all production Python files and finds those that are never imported anywhere.

```
Dead Module Detector
============================================================
Scanning 934 production Python files (758 subjects)...

Dead Modules — 23 files with zero importers:
These are not imported anywhere in production code.
Review before deleting — some may be loaded by convention.

  ● adapters/persistence/neo4j/query/skuel_query_templates.py  (644 lines)
      module: adapters.persistence.neo4j.query.skuel_query_templates
      hint:   SKUEL-Specific Query Templates - Pure Cypher patterns
```

**What it scans:** All `.py` files outside `tests/`, `scripts/`, `__pycache__`, `node_modules`.

**What counts as "imported":** Three patterns are detected:
| Pattern | Example |
|---------|---------|
| Direct import | `import core.services.tasks_service` |
| From-import | `from core.services.tasks_service import TasksService` |
| Package import | `from core.services import tasks_service` |

**What is excluded from the dead list (but still scanned for imports):**
- `__init__.py` files — re-exports count, but `__init__.py` itself isn't flagged
- `scripts/` directory — `scripts/dev/bootstrap.py` loads routes; those imports count
- Entry points: `main.py`, `services_bootstrap.py`

**Output:** File path, line count, first comment/docstring as a hint.

**False positive rate:** Low. The scanner handles:
- Multi-line parenthesized imports (with comment-aware `)` matching)
- Relative imports (`.foo`, `..bar`) resolved to absolute dotted paths
- Docstring and comment pseudo-imports that happen to match `from X import`

**When a file is flagged:** Review before deleting. Ask:
1. Is it imported indirectly (dynamic loading, plugin system)?
2. Is it a convention-loaded file (e.g., a config that's imported by name at runtime)?
3. Is it actually dead and should be deleted?

---

### 2. `dead_doc_links.py` — Broken Documentation Links

Scans all `.md` files in `docs/` and `.claude/skills/` for broken path references.

```
Dead Doc Link Validator
============================================================
Scanning 339 Markdown files in docs/ and .claude/skills/...

Broken References — 1360 dead links:

  docs/INDEX.md  [INDEX.md]
    L  14  [link]      docs/decisions/ADR-030-analytics-vs-ai.md

  docs/patterns/three_tier_type_system.md
    L 500  [backtick]  /core/models/task/task_converters.py
```

**Three reference kinds detected:**

| Kind | Example | Detection Method |
|------|---------|-----------------|
| `[link]` | `[text](path/to/file.md)` | Markdown link syntax |
| `[backtick]` | `` `core/services/tasks.py` `` | Inline code spans that look like paths |
| `[bare]` | `/docs/patterns/foo.md` in prose | Bare absolute paths with project prefixes |

**Absolute paths** (starting with `/`) are resolved relative to the repo root.
**Relative paths** are resolved relative to the source file's directory.
**External URLs** (`http://`, `https://`, etc.) and anchor-only links (`#section`) are skipped.

**Special callout:** When `docs/INDEX.md` has broken links, the output highlights it:
```
⚠  docs/INDEX.md has 24 broken reference(s) — update the index to match current files
```

**When references break:**
- A file is renamed or deleted but the docs aren't updated
- A skill directory is listed in the index before it's created
- A test file referenced in a doc is deleted after the test is removed

---

### 3. `stale_names.py` — Deprecated Identifiers in Doc Code Blocks

Scans **code blocks only** (fenced ` ``` ` blocks and inline backtick spans) in all docs for identifiers that have been renamed or deleted.

```
Stale Name Scanner
============================================================
Rules: 32 renamed identifiers, 14 deleted identifiers

  docs/patterns/three_tier_type_system.md
    L 822  KuType → EntityType
    L 823  KuStatus → EntityStatus

  CLAUDE.md
    L  47  KuTaskCreateRequest → TaskCreateRequest
    L 945  [DELETED] ProfileLayout
               reason: deleted — use BasePage(page_type=PageType.CUSTOM)
```

**Why code blocks only:** Prose mentions like "we renamed `AiFeedback` to `ActivityReport`" are legitimate historical context. Only code *examples* using the old name need updating.

**What's tracked (as of 2026-03-03):**

| Category | Examples |
|----------|---------|
| EntityType renames | `EntityType.CURRICULUM` → `EntityType.KU` |
| Class renames | `AiFeedback` → `ActivityReport`, `ActivityReviewService` → `ActivityReportService` |
| Enum type renames | `KuStatus` → `EntityStatus`, `KuType` → `EntityType` |
| UserContext fields | `active_tasks_rich` → `entities_rich["tasks"]` |
| Method renames | `list_reports` → `list_submissions` |
| Old module paths | `from core.models.ku.ku_enums import` → `from core.models.enums.entity_enums import` |
| Deleted modules | `daisy_components`, `htmx_a11y`, `sel_routes`, `ActivityDataReader` |
| Deleted classes | `ProfileLayout`, `ActivityReviewService` |

Run `./dev health-names --list` to print the complete RENAMED and DELETED tables.

---

### 4. `validate_cross_references.py` — Skill↔Doc Cross-References

Validates bidirectional consistency between skills and documentation, and detects stale skills whose primary docs have been updated since `last_reviewed`.

```
Cross-Reference Validation Report
================================================================================

📊 Statistics:
   Total skills: 23
   Total docs scanned: 257
   Skill references in docs: 111
   Doc references in skills: 101

✅ Bidirectional Links: 80/111 (72.1%)
❌ Broken Links: 1
⚠️  Missing Reverse Links: 51
🔵 Stale Skills: 0
```

**What it checks:**

| Check | Severity | Meaning |
|-------|----------|---------|
| Broken skill reference | ❌ Error | `@skill-name` in a doc doesn't exist in `skills_metadata.yaml` |
| Broken doc link | ❌ Error | Doc in `skills_metadata.yaml` doesn't exist on disk |
| Missing reverse link | ⚠️ Warning | Unidirectional reference (A→B but not B→A) |
| Stale skill | 🔵 Info | Primary docs have git commits after `last_reviewed` |

**Verbose mode:** `uv run python scripts/validate_cross_references.py --verbose` includes orphaned docs and info-level issues.

**Errors-only mode:** `uv run python scripts/validate_cross_references.py --errors-only` for CI (exit 1 if errors).

---

## Maintaining `stale_names.py`

This script is only as useful as its RENAMED/DELETED tables. **Update it whenever you rename or delete something significant.**

### When to add a RENAMED entry

```python
# In scripts/health/stale_names.py

RENAMED: dict[str, str] = {
    # Add when you rename a class, enum value, method, or module
    "OldClassName": "NewClassName",
    "EntityType.OLD_VALUE": "EntityType.NEW_VALUE",
    "old_method_name": "new_method_name",
    "from old.module.path import": "from new.module.path import",
}
```

### When to add a DELETED entry

```python
DELETED: dict[str, str] = {
    # Add when you delete a class, module, or file that docs might reference
    "DeletedClass": "reason or replacement description",
    "old_module_name": "replaced by NewModule",
}
```

### When to archive an entry

Once a rename has been fully applied to ALL code and docs and the scanner reports zero violations for that entry, move it to the archive comment at the bottom of `stale_names.py`. This keeps the active tables lean.

---

## When to Run

| Trigger | Why |
|---------|-----|
| Before a major refactor | Establish a clean baseline |
| After renaming/deleting files | Verify docs stayed in sync |
| After a `ku/` monolith-style dissolution | Catch stale import paths in docs |
| Monthly maintenance | Catch slow drift |
| Before cutting a release | Ensure docs are accurate |

The scripts are fast enough to run on every commit if desired (a few seconds each).

---

## Known Limitations

**`dead_modules.py`:**
- Dynamic imports (`importlib.import_module("some.module")`) are not detected — those modules will be incorrectly flagged as dead
- String-based module loading (plugin systems, `__import__`) is not detected
- Files imported via environment-specific wiring not in `scripts/dev/bootstrap.py` may appear dead

**`dead_doc_links.py`:**
- Relative links in template files may appear broken (the template is never at its "real" location)
- Links to anchors within files are not validated (only the file existence is checked)
- Links inside HTML comments or non-standard syntax may be missed

**`stale_names.py`:**
- Only catches names that are explicitly listed in RENAMED/DELETED — it won't catch names you forgot to add
- Prose mentions inside code blocks (docstring examples, prose in fenced blocks) are also checked, which may trigger false positives if a doc legitimately shows before/after migration history

---

## File Structure

```
scripts/health/
├── dead_modules.py                    # Zero-importer Python module detection
├── dead_doc_links.py                  # Markdown link validator
└── stale_names.py                     # Deprecated identifier scanner
scripts/validate_cross_references.py   # Skill↔doc cross-reference validator
```

**Related:**
- `./dev health` — runs all four
- `./dev bloat` — separate check for unused events/methods (different scope)
- `docs/tools/AUTOMATIC_DOCS_CHECK.md` — post-commit hook for doc freshness
- `docs/user-guides/documentation-freshness.md` — unified user guide
