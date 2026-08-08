---
title: Codebase Health Checks
updated: 2026-08-07
status: current
category: tools
tags: [health, scripts, dead-code, documentation, maintenance, drift]
related: [AUTOMATIC_DOCS_CHECK.md, BLOAT_DETECTION.md]
---

# Codebase Health Checks

**Status:** ✅ Active
**Date Added:** 2026-03-03
**Location:** `scripts/health/`

## Overview

Five automated checks that prevent codebase drift — the kind that accumulates silently between refactors: orphaned files, broken doc links, stale names in documentation examples, skill↔doc cross-reference inconsistencies, and mypy suppressions that have stopped suppressing anything.

```bash
./dev health              # run the first four checks
./dev health-modules      # dead Python modules only
./dev health-links        # broken doc links only
./dev health-names        # stale identifiers in docs only
./dev health-xref         # cross-reference + staleness only
./dev health-mypy         # dead mypy suppressions only (~80s — NOT in ./dev health)
```

All five exit non-zero when issues are found, so they can be used in CI —
and all five now ARE: the first four run weekly via
`.github/workflows/weekly-janitor.yml` (Mondays 06:30 UTC, together with the
full bloat report), which maintains an always-open status issue and fails
its run on findings; `health-mypy` has its own weekly workflow
(`mypy-suppressions.yml`, Mondays 06:00 UTC). Both are advisory — neither
feeds the CI gate.

**`health-mypy` is deliberately outside `./dev health`.** The first four are file scans that finish in seconds; the mypy audit needs one full type-check run per suppression it verifies. Bolting ~80s onto the aggregate target is how a health target stops being run at all — so it gets its own entry point and a weekly CI schedule instead.

---

## The Five Checks

### 1. `dead_modules.py` — Zero-Importer Python Files

Scans all production Python files and finds those that are never imported anywhere.

```
Dead Module Detector
============================================================
Scanning 934 production Python files (758 subjects)...

Dead Modules — 23 files with zero importers:
These are not imported anywhere in production code.
Review before deleting — some may be loaded by convention.

  (example removed — skuel_query_templates.py deleted March 2026)
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
    L  14  [link]      docs/decisions/ADR-029-graphnative-service-removal.md

  docs/patterns/three_tier_type_system.md
    L 500  [backtick]  /core/services/base_service.py
```

**Four reference kinds detected** (examples cite real files — the checker scans
this doc too, including these fenced samples, so a made-up example path would
self-report as broken):

| Kind | Example | Detection Method |
|------|---------|-----------------|
| `[link]` | `[text](/docs/INDEX.md)` | Markdown link syntax |
| `[backtick]` | `` `core/services/base_service.py` `` | Inline code spans that look like paths |
| `[bare]` | `/docs/patterns/linter_rules.md` in prose | Bare absolute paths with project prefixes |
| `[code]` | `cp core/services/base_service.py …` inside a ` ``` ` block | Path-looking tokens in fenced code blocks |

**Absolute paths** (starting with `/`) are resolved relative to the repo root — the ONE
canonical citation style. Machine-absolute paths (`/home/.../app/...`) are deliberately
not rescued: they resolve under the repo root and report broken identically in every
checkout, so the doc gets fixed rather than the alternative style preserved.
**Relative paths** are resolved relative to the source file's directory; if that misses,
they are retried relative to the repo root (docs routinely cite root-relative paths like
`docs/patterns/linter_rules.md` without a leading slash).
**External URLs** (`http://`, `https://`, etc.) and anchor-only links (`#section`) are skipped.

**Special callout:** When `docs/INDEX.md` has broken links, the output highlights it:
```
⚠  docs/INDEX.md has 24 broken reference(s) — update the index to match current files
```

**When references break:**
- A file is renamed or deleted but the docs aren't updated
- A skill directory is listed in the index before it's created
- A test file referenced in a doc is deleted after the test is removed

#### The `[code]` pass and the 807 → 908 step (PR #872)

The first three kinds are prose-shaped, and how-to guides are mostly *fence*. That
left a structural blind spot: `DOMAIN_LATERAL_SERVICE_QUICK_START.md` told readers to
`cp core/services/goals/goals_lateral_service.py …` for ~6 months after that file was
deleted (`e8818dc26`), and this checker reported **zero** broken references for it
across 13 maintenance sweeps (PR #870).

The gap was narrower than "fences are never scanned". `[bare]` detection is already
fence-blind, so a project-rooted *absolute* path inside a fence has always been
reported; only **relative** tokens were invisible — precisely the shape a copy-paste
shell instruction uses.

**The total moved 807 → 908. That step is the new pass, not new rot**, and it
decomposes as:

| Step | Total | Δ |
|------|-------|---|
| Baseline at `28e406602` | 807 | — |
| Extended placeholder guard (also applies to the older passes) | 806 | −1 |
| New `[code]` pass | 909 | +103 |
| Fixed this doc's own stale `ADR-030` sample, which the new pass caught | **908** | −1 |

Of the 102 remaining `[code]` reports, **96 are genuine** — mostly docs telling you to
`uv run python scripts/<gone>.py` or `pytest tests/<never-existed>.py`. **6 are known
false positives** that no structural rule catches: three `docs/roadmap/` forward
references annotated `(new)`/`(when implemented)`, two citations of an aspirational
`recording_rules.yml`, and one simulated `git status` sample in a git tutorial.
**Precision ≈ 94%**, measured over the whole candidate surface rather than a sample —
a widening only turns non-reports into reports, so the previously-unreported set *was*
the complete candidate surface (653 fenced tokens, 176 dead, 103 not already reported).

Excluding `docs/roadmap/` wholesale was considered and rejected: it would drop 3 false
positives but also a genuine one (a roadmap doc citing an `activity.py` under
`adapters/persistence/neo4j/backends/`, where the real file is `activity_backends.py`),
reintroducing exactly the doc-class blind spot this pass closes. The `(when implemented)` annotation is visible to the reader on the same line.

**Fence boundaries come from a CommonMark parser** (`markdown-it-py`, dev-only), not a
hand-written scanner. A scanner was tried first and accrued **five** container-handling
bugs in one review — blockquoted fences never opening, an unclosed quoted fence leaking
into later prose, a nested-quote fence not closing with its inner quote, a list-item fence
swallowing the document after a dedent, and a four-space-indented delimiter (an *indented
code block* under CommonMark) opened as a real fence. Each falsely reported ordinary prose
as `[code]`.

Worth recording why the migration happened late: a tree-wide differential against the
parser found **zero disagreements**, which read as "the scanner is equivalent" but only
ever meant "the corpus contains none of the shapes where they differ." All three
later-found shapes are absent from `docs/` today. Corpus-relative agreement is not
correctness. Swapping the parser in left the report byte-identical at 908.

Other latent gaps closed on review (Codex, PR #872), each with a measured tree-wide delta
of **0 dead refs** — they widen *coverage*, not the count:

- **Blockquoted fences** (`> ` before the delimiter) never opened, so quoted examples were
  skipped whole. One lives at `UNIFIED_RELATIONSHIP_SERVICE.md:318`; 4 previously-invisible
  lines are now scanned, none holding a path token today.
- **`./`-prefixed paths** (`cp ./core/services/base_service.py`) start with neither `/` nor a project
  directory, so the guard dropped them. 8 such tokens exist tree-wide, all currently live.
- **Dedup is keyed on the resolved target, not the raw string.** Once the dot-slash form
  became checkable, the backtick pass reported it while `[bare]` independently matched its
  leading-slash tail — one defect, two lines. Two spellings of one dead file on one line are
  now one finding; two different dead files on one line remain two.

Placeholder shapes are rejected by the shared `_looks_like_local_path` guard, not a
second filter: syntactic markers (`{domain}`, `<name>`, `*`) plus a lexical vocabulary
for the prose convention (`your_service.py`, `test_foo.py`, `alpine.X.Y.Z.min.js`).
That vocabulary only ever *subtracts* reports, so a gap in it costs one noisy advisory
line rather than a false failure — never invert it to decide something *is* broken.
Every entry is pinned by `tests/unit/scripts/test_dead_doc_links.py`, which also pins
all four cells of the {inline, fenced} × {relative, absolute} matrix.

---

### 3. `stale_names.py` — Deprecated Identifiers in Doc Code Blocks

Scans **code blocks only** (fenced ` ``` ` blocks and inline backtick spans) in all docs for identifiers that have been renamed or deleted. This file itself is excluded (`SKIP_FILES` in the script) — documenting the scanner requires naming tracked identifiers as examples.

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

### 5. `mypy_suppressions.py` — Dead MyPy Suppressions

The mypy counterpart to SKUEL026. SKUEL026 flags any `# skuel-lint: disable=...` comment that suppresses nothing; mypy had no equivalent, so its suppressions drifted unwatched until PR #876 swept them by hand. This makes that sweep repeatable.

```
MyPy Suppression Auditor
============================================================
13 override blocks, 5 (block, code) pairs to verify.

Load-bearing disable_error_code entries:
  ● arg-type suppresses 2260 errors
      pyproject.toml:347  module = [tests.*, examples.*, scripts.*]
  ● misc suppresses 8 errors
      pyproject.toml:309  module = [adapters.persistence.neo4j.backends...]

✓ No dead mypy suppressions (5 entries verified load-bearing)
```

**What it reports:**

| Finding | Meaning |
|---------|---------|
| Vacuous `disable_error_code` entry | The code currently suppresses 0 errors in that scope — it will silently eat the FIRST real violation someone writes |
| Unused override section | A module pattern matching nothing, taken straight from mypy's own `unused section(s)` note |

**What counts as a scope.** Both the global `[tool.mypy]` table and each `[[tool.mypy.overrides]]` block. The global table is the widest suppression there is — it silences a code across every checked file — so auditing only the overrides would leave it invisible behind a clean report. This repo has carried a global entry before; the note atop its `[tool.mypy]` table records the deletion.

**How it measures.** For each (scope, error code) pair it writes a copy of `pyproject.toml` with that one code removed from that one scope, runs `uv run mypy .` against it, and attributes errors by the trailing `[code-name]`. The generated config is re-parsed with `tomllib` and checked against the intended edit before it is trusted.

**Why the unit is the pair, not the code.** PR #876 measured by stripping every code at once and attributing by code, then confirming each zero individually. That is necessary but not sufficient: what you delete is a (scope, code) pair, and `misc` is currently disabled in two different scopes. An aggregate reading of `misc 32` cannot tell you whether both earn it or whether all 32 sit in one — in fact they split 24/8. The aggregate survives as `--census`, which refreshes the backlog figures quoted in `pyproject.toml` and is explicitly not evidence for a deletion.

**Fail-safe direction:** it under-reports rather than over-reports. Stripping one pair can only surface errors inside that scope, so a non-zero count proves the entry is load-bearing, and every zero is confirmed by the run that isolates it. That holds only for runs that *completed*, so any mypy invocation the script cannot prove finished aborts the whole audit — a crashed mypy prints no errors, and an empty error set is indistinguishable from a clean one. An aborted audit reports nothing; it never reports zero.

**Exit codes** — unlike the other four checks, this one distinguishes *found something* from *could not measure*:

| Code | Meaning |
|------|---------|
| 0 | Clean |
| 1 | Confirmed findings, and nothing else |
| 2 | The instrument could not measure (incomplete mypy run, malformed config, any unexpected exception) |

Exit 1 is load-bearing: the scheduled workflow opens an issue on it asserting dead suppressions were found, so every non-finding outcome — including Python's default status for an uncaught exception — is mapped to 2 instead.

---

## Maintaining `stale_names.py`

This script is only as useful as its RENAMED/DELETED tables. **Update it whenever you rename or delete something significant.**

**Matching semantics:** keys refuse alphanumeric neighbors — `PageHead` does NOT fire on `PageHeader` — but underscore adjacency still matches, so deleted snake_case names are caught inside derived symbols (`sel_routes` fires on `create_sel_routes`). Keys ending in a non-word character (e.g. the trailing dot in `core.models.ku.`) prefix-match, so deleted-package paths work as before.

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

The first four scripts are fast enough to run on every commit if desired (a few seconds each); since 2026-08 they run weekly regardless via `.github/workflows/weekly-janitor.yml`, so drift no longer waits for someone to remember. `mypy_suppressions.py` runs a full type check per suppression, so it has its own weekly CI schedule (`.github/workflows/mypy-suppressions.yml`) and is worth running locally when editing `[tool.mypy]` config.

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

**`mypy_suppressions.py`:**
- **The verdict is per (scope, code), not per module pattern.** An override listing several module patterns is earned as a whole, so a pattern producing none of the code is still marked load-bearing. The live case: the domain-backends override lists seven modules, but all 8 `misc` errors come from `activity_backends` (6) and `curriculum_backends` (2) — a first `misc` violation in the other five would be suppressed with this audit green. The report prints the files behind each verdict so the gap is visible rather than silent; closing it properly is tracked separately, because a pattern cannot be isolated by deleting it from the list (for a block that sets other options too, that changes all of them for the module and measures the wrong thing).
- It measures what mypy reports **today**. A code that is load-bearing now can become vacuous later when the last violation is fixed, which is why the weekly schedule is not gated on `pyproject.toml` changing.

---

## File Structure

```
scripts/health/
├── dead_modules.py                    # Zero-importer Python module detection
├── dead_doc_links.py                  # Markdown link validator
├── stale_names.py                     # Deprecated identifier scanner
├── markdown_fences.py                 # Shared CommonMark fence walker (links + names)
└── mypy_suppressions.py               # Dead mypy suppression auditor
scripts/validate_cross_references.py   # Skill↔doc cross-reference validator
```

**Related:**
- `./dev health` — runs the first four
- `./dev bloat` — separate check for unused events/methods (different scope) — see [BLOAT_DETECTION.md](BLOAT_DETECTION.md)
- `docs/tools/AUTOMATIC_DOCS_CHECK.md` — post-commit hook for doc freshness
- `docs/user-guides/documentation-freshness.md` — unified user guide
