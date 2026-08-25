---
title: Codebase Health Checks
updated: 2026-08-12
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

Automated checks that prevent codebase drift — the kind that accumulates silently between refactors: orphaned files, broken doc links, stale names in documentation examples, duplicated document sections, skill↔doc cross-reference inconsistencies, and mypy suppressions that have stopped suppressing anything.

```bash
./dev health              # run every check except health-mypy
./dev health-modules      # dead Python modules only
./dev health-links        # broken doc links only
./dev health-names        # stale identifiers in docs only
./dev health-headings     # repeated headings under one parent only
./dev health-xref         # cross-reference + staleness only
./dev health-mypy         # dead mypy suppressions only (~80s — NOT in ./dev health)
```

Every check exits non-zero when issues are found, so they can be used in CI —
and all of them now ARE: everything in `./dev health` runs weekly via
`.github/workflows/weekly-janitor.yml` (Mondays 06:30 UTC, together with the
full bloat report), which maintains an always-open status issue and fails
its run on findings; `health-mypy` has its own weekly workflow
(`mypy-suppressions.yml`, Mondays 06:00 UTC). Both are advisory — neither
feeds the CI gate.

> The per-check sections below are the inventory. This overview deliberately carries no
> count and no roster: it went stale the moment a sixth check landed, and
> `duplicate_headings.py` exists precisely because a summary that restates a fact
> outlives the fact.

**`health-mypy` is deliberately outside `./dev health`.** The others are file scans that finish in seconds; the mypy audit needs one full type-check run per suppression it verifies. Bolting ~80s onto the aggregate target is how a health target stops being run at all — so it gets its own entry point and a weekly CI schedule instead.

---

## The Checks

### 1. `dead_modules.py` — Zero-Importer Python Files and Orphan Packages

Scans all production Python files and finds those that are never imported anywhere,
then scans every package for one nothing outside it imports.

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

#### The orphan-package pass

That third exclusion has a cost the module pass cannot see: an `__init__.py` is
not a subject but *is* an importer, so a self-contained package clears itself.
Its `__init__` imports its modules, so every module in it has an importer, and
the package reads as alive from the inside. `core/services/search` survived that
way for the repo's entire history — 357 lines, never imported by anything, and
only the one file its `__init__` forgot to re-export was ever flagged (#1086).

The second pass asks a different question: **does anything outside this
directory tree import it?** Three scoping rules, all deliberate:

- **Tests count as importers here** (unlike the module pass). A package whose
  only consumers are tests is exercised, not abandoned. Ignoring them condemns
  `agent/` (an ADR-075 entry point) and `core/models/vectors` (test-covered) —
  neither is dead, and deleting on that signal is the known bloat-scanner
  test-reference failure.
- **Packages holding no code are skipped** — a docstring-only namespace
  directory (`ui/curriculum`, `ui/study`). This is deliberately *not* "every
  `__init__`-only package": an `__init__.py` can be the implementation —
  `core/services/templates` defines seven service classes in 230 lines with no
  module beside it — and skipping those would make them permanently invisible.
  Re-export-only facades are checked too: a facade nothing imports is exactly
  what this pass is for.
- **Packages holding an entry-point, convention-loaded, or staged module are
  skipped**, mirroring the module pass — they are reached by execution or
  registration, never by import, so "nobody imports it" says nothing about
  them. Without this, `agent/` (the ADR-075 vault-agent CLI) passed only
  because tests happen to import it; deleting those tests would have reported
  a live CLI as orphaned and failed the weekly janitor.

Pinned by `tests/unit/scripts/test_dead_modules.py`.

**Output:** File path, line count, first comment/docstring as a hint.

**How imports are found:** `collect_imports` parses each file with `ast` and
reads `Import` / `ImportFrom` nodes. Multi-line parenthesized imports, `as`
aliases, and relative imports (`.foo`, `..bar`, resolved to absolute dotted
paths) all come out of the parser correctly — no pattern-matching involved.

**An import in prose is not a reference.** This is the point of parsing rather
than scanning text, and the reason it matters is subtle: the previous regex
matched `from x import y` anywhere in a file, *including inside the module's own
docstring*. A module whose USAGE block read `from core.utils.thing import helper`
therefore vouched for itself and could never be reported dead. Three modules hid
that way for months and were deleted in #1088.

A file that will not parse is **reported and fails the run** rather than skipped:
it contributes no imports, so anything only it imports would otherwise be
misreported as dead — a false positive is worse than a loud complaint.

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
Rules: 67 renamed identifiers, 21 deleted identifiers

  docs/patterns/three_tier_type_system.md
    L 822  KuType → EntityType
    L 823  KuStatus → EntityStatus

  CLAUDE.md
    L  47  KuTaskCreateRequest → TaskCreateRequest
    L 945  [DELETED] ProfileLayout
               reason: deleted — use BasePage(page_type=PageType.CUSTOM)
```

**Why code blocks only:** Prose mentions like "we renamed `AiFeedback` to `ActivityReport`" are legitimate historical context. Only code *examples* using the old name need updating.

**What's tracked:** the `RENAMED` and `DELETED` dicts in the script, and nothing else. Print them:

```bash
./dev health-names --list
```

A key is whatever literal a doc would write — an enum member (`EntityType.OLD_VALUE`), a class (`OldClassName`), a method or field (`old_method_name`), a module or package (`old_module_name`), an attribute path (`OldService.old_attribute`), or an import prefix (`from old.module.path import`). Which dict a given retirement belongs in, and how matching treats neighbors and prefixes, is covered under **Maintaining `stale_names.py`** below.

**This document deliberately does not mirror those dicts.** It is the sole `SKIP_FILES` entry, so a summary here is the one copy in the repo that no check can score. The "as of 2026-03-03" table that stood here until August 2026 had drifted into four wrong entries — a rename pointed at the wrong replacement, and three renames filed as deletions, one of which the same table also listed correctly as a rename six rows above.

---

### 4. `validate_cross_references.py` — Skill↔Doc Cross-References

Validates bidirectional consistency between skills and documentation, and detects stale skills whose primary docs have been updated since `last_reviewed`.

**Doc→skill links live in `related_skills:` frontmatter.** That field is the canonical representation — the same one `skills_validator.py` validates, `sync_cross_references.py` projects into doc bodies, and `generate_cross_reference_index.py` indexes. Prose `@skill` mentions are *not* links: until PR #1023 this script read only prose, which made the two halves of the system invisible to each other (and counted `@pytest.fixture` in a code block as a link).

```
Cross-Reference Validation Report
================================================================================

📊 Statistics:
   Total skills: 30
   Total docs scanned: 410
   Skill references in docs: 116
   Doc references in skills: 108

✅ Bidirectional Links: 86/116 (74.1%)
❌ Broken Links: 0
⚠️  Missing Reverse Links: 52
🔵 Stale Skills: 0
ℹ️  Orphaned Docs: 321
ℹ️  Skills Without Docs: 2
```

**What it checks:**

| Check | Severity | Meaning |
|-------|----------|---------|
| Broken skill reference | ❌ Error | A name in a doc's `related_skills` doesn't exist in `skills_metadata.yaml` |
| Broken doc link | ❌ Error | Doc in `skills_metadata.yaml` doesn't exist on disk |
| Missing reverse link | ⚠️ Warning | Unidirectional reference (A→B but not B→A) |
| Orphaned doc | 🔵 Info | Doc declares no `related_skills` at all |
| Stale skill | 🔵 Info | Primary docs have git commits after `last_reviewed` |

The orphaned/skills-without-docs counts are printed in the statistics block because the listings below them are truncated — read the count, not the length of the list.

**Verbose mode:** `uv run python scripts/validate_cross_references.py --verbose` includes orphaned docs and info-level issues.

**Errors-only mode:** `uv run python scripts/validate_cross_references.py --errors-only` for CI (exit 1 if errors).

---

### 5. `mypy_suppressions.py` — Dead MyPy Suppressions

The mypy counterpart to SKUEL026. SKUEL026 flags any `# skuel-lint: disable=...` comment that suppresses nothing; mypy had no equivalent, so its suppressions drifted unwatched until PR #876 swept them by hand. This makes that sweep repeatable.

```
MyPy Suppression Auditor
============================================================
14 suppression scopes, 8 (scope, code) pairs to verify.

Load-bearing disable_error_code entries:
  ● arg-type suppresses 2449 errors
      pyproject.toml:355  module = [tests.*]
      in: tests/unit/services/test_user_entry_service.py (80), and 287 more files
      msg (95x): "Argument "uid" to "Curriculum" has incompatible type "str"; expected "EntityUID""
  ● misc suppresses 8 errors
      pyproject.toml:313  module = [adapters.persistence.neo4j.backends...]
      in: adapters/persistence/neo4j/backends/activity_backends.py (6), adapters/persistence/neo4j/backends/curriculum_backends.py (2)
      patterns: ...activity_backends (6), ...curriculum_backends (2)
      msg (8x): "Definition of "get_related_entities" in base class "_RelationshipQueryMixin" is incompatible with definitio..."

✓ No dead mypy suppressions (8 entries verified load-bearing, 2 pattern memberships probed)
```

The `in:` line is mypy's own file attribution; the `patterns:` line is each pattern's probe-measured share; the `msg` lines are mypy's messages verbatim — put there so the human-written rationale comment above the entry can be checked against what the code actually suppresses (that comment drifted twice, #883 and #1000, while the entry itself stayed load-bearing).

**What it reports:**

| Finding | Meaning |
|---------|---------|
| Vacuous `disable_error_code` entry | The code currently suppresses 0 errors in that scope — it will silently eat the FIRST real violation someone writes |
| Unused override section | A module pattern matching nothing, taken straight from mypy's own `unused section(s)` note |

**What counts as a scope.** Both the global `[tool.mypy]` table and each `[[tool.mypy.overrides]]` block. The global table is the widest suppression there is — it silences a code across every checked file — so auditing only the overrides would leave it invisible behind a clean report. This repo has carried a global entry before; the note atop its `[tool.mypy]` table records the deletion.

**How it measures.** For each (scope, error code) pair it writes a copy of `pyproject.toml` with that one code removed from that one scope, runs `uv run mypy .` against it, and attributes errors by the trailing `[code-name]`. The generated config is re-parsed with `tomllib` and checked against the intended edit before it is trusted. Multi-pattern blocks then get one further run per module pattern: an appended override carrying only `module = [<pattern>]` and `enable_error_code = [<code>]` — a *later config-level* enable lifts an earlier block's per-module disable (measured on mypy 2.3.0). A pattern earning 0 is a finding: its membership suppresses nothing and only stands to eat that pattern's first violation. Note the CLI spelling cannot do this — `mypy --enable-error-code X` sits below per-module config sections in mypy's precedence, so a hand-probe with the flag reads as a clean pass over a scope that disables the code. Probe by editing config (best: by running this script); see `docs/patterns/mypy_pragmatic_strategy.md § Probing Whether a Suppression Is Still Needed`.

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

### 6. `duplicate_headings.py` — Repeated Headings Under One Parent

**What it finds:** two headings with the same text, at the same level, under the same
parent — the shape a superseded section leaves when it outlives its replacement.

**Why `git grep` does not cover it:** the duplicate is found by *position*, not by string.
Grepping the heading text returns both copies and looks correct; you have to notice there
are two, in a file long enough that nobody scrolls it end to end. PR #1153 shipped two
`## PR-5` sections that way, and a stale `### EventHandlerService` catalog entry had been
sitting in `SUB_SERVICE_CATALOG.md` describing six domains where the live one described
seven.

**The scoping rule is the whole design.** Measured over the authored corpus:

| Rule | Hits |
|---|---|
| same text anywhere in the file | 137 — unusable |
| same text + same level + **same parent** | 3 — this rule |

The 134-hit difference is legitimate structure: `### Tests` under each of five PR sections
is good writing, not a defect. Only a repeat under the same parent means two headings claim
to be the same section of the same outline.

**Two deliberate narrowings**, each pinned by a test so a later reader does not "fix" them
back into false positives:

- **Setext headings are ignored.** An unfilled ADR template writes `**Pros:**` above an
  empty `-` bullet, and CommonMark reads a lone `-` after a paragraph as a setext underline
  rather than a list item — so the bold label renders as an `<h2>`. Six such phantoms exist
  in the tree; they are a template artifact, not an authored section. (They are also a real
  minor rendering bug in `ADR-TEMPLATE.md` and `ADR-010`, for whoever fixes that template.)
- **Blockquoted headings are ignored** — quoted material is someone else's outline.

**Scope:** `docs/` + `.claude/skills/`, excluding `docs/design-principles/` — that tier
holds pasted transcripts and raw working notes where a repeated `## next` is faithful
capture. The exclusion is by scope, not suppression: the run prints how many files it
skipped.

**Comparison is on RENDERED text**, so `## Setup` and `## **Setup**` are one heading in
two costumes — the shape where a replacement reformats its title and the superseded
section survives underneath. It is also an anchor collision: GitHub derives anchors from
rendered text, so both resolve to `#setup`, and two headings colliding there are the same
section as far as any link is concerned. Links, code spans and image alt text all
collapse to their displayed characters, and internal whitespace is collapsed the way HTML
collapses it (`## Quick Start` and `## Quick  Start` are one heading). A heading that
renders to **nothing** never matches — an empty key cannot identify a section, and it is
where an unrecognised inline token would otherwise turn into a false positive — but it
still occupies the outline, so two untitled image headings each holding a `#### Setup`
keep those subsections in separate scopes.

**Headings come from the CommonMark parser, never a regex** — the sibling
`markdown_fences.py` documents what hand-rolled Markdown scanning costs.

**Run:** `./dev health-headings`

---

## Maintaining `stale_names.py`

This script is only as useful as its RENAMED/DELETED tables. **Update it whenever you rename or delete something significant.**

**Matching semantics:** keys refuse alphanumeric neighbors — `PageHead` does NOT fire on `PageHeader` — but underscore adjacency still matches, so deleted snake_case names are caught inside derived symbols (`sel_routes` fires on `create_sel_routes`). Keys ending in a non-word character (e.g. the trailing dot in `core.models.ku.`) prefix-match, so deleted-package paths work as before.

### When an old identifier is intentional

Some docs must name a retired identifier — an ADR's before/after table, an import-error string users search for verbatim, a doc that demonstrates this scanner, a frozen before/after snippet inside a still-maintained migration guide. Two exemption tiers exist; **each is audited so an exemption that hides nothing is a finding** (`test_stale_names_allowed_occurrences.py`, the SKUEL026 discipline). Reach for the narrowest that fits — never widen a whole file to force the count down (reverted in PR #986).

- **`ALLOWED_OCCURRENCES`** — a **counted** set of hits for one identifier at one **line**, one otherwise-scanned doc. Every other line, every other identifier, and any hit *beyond the count* on the same line is still scanned — anchoring on `(line, hits)`, not a coarse `(file, identifier)` key, is what closes the blind spot where a second stale mention would ride along silently (Codex, PR #988). Each entry needs a rationale and its `hits` must equal the real number of matches at that line (`hits` defaults to 1; read the line off `--verbose`):

  ```python
  ALLOWED_OCCURRENCES: dict[str, dict[tuple[int, str], Allow]] = {
      "docs/decisions/ADR-0XX-example.md": {
          (42, "LegacyType"): Allow("before/after table — the ADR's subject IS this rename"),
          # hits > 1 when one line names it twice (e.g. two inline-code spans):
          (57, "LegacyType"): Allow("verbatim import-error string users search", hits=2),
      },
  }
  ```

- **`SKIP_FILES`** — one whole file, kept to exactly the scanner's own documentation (this file), audited section-by-section by `test_stale_names_suppression.py`.

There is deliberately **no directory-scope exclusion**. An earlier cut excluded `docs/migrations/` wholesale as a "frozen archive", but the premise is false: several migration guides are maintained and current-facing (they get updated to current names and swept by rename campaigns), so blinding the subtree would hide a genuine rename in them. Frozen snippets inside those guides get occurrence-level allowances instead — each individually audited.

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

The `./dev health` scripts are fast enough to run on every commit if desired (a few seconds each); since 2026-08 they run weekly regardless via `.github/workflows/weekly-janitor.yml`, so drift no longer waits for someone to remember. `mypy_suppressions.py` runs a full type check per suppression, so it has its own weekly CI schedule (`.github/workflows/mypy-suppressions.yml`) and is worth running locally when editing `[tool.mypy]` config.

---

## Known Limitations

**`dead_modules.py`:**
- Dynamic imports (`importlib.import_module("some.module")`) are not detected — those modules will be incorrectly flagged as dead
- The orphan-package pass is import-graph only: a package reached solely through
  dynamic loading, or one whose only consumers are docs, will be flagged
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
- **Pattern verdicts are pair-restricted; file-level inline comments are a separate surface.** (The per-scope-only verdict was the former limitation here; per-pattern probes closed it 2026-08-09 — the five backend modules and the `examples.*`/`scripts.*` memberships they flagged were narrowed out the same day.) A probe's *explicit* enable can pierce a file-level `# mypy: disable-error-code` comment naming a parent code (sub-code inheritance, e.g. `assignment` over `method-assign`) and surface errors the block entry never suppressed — counting those would mark a vacuous membership as earned, so each pattern's verdict counts only its share of the pair's own errors and the extras are printed as a note. Attribution is reconciled by error identity: any pair error appearing in *no* probe aborts the audit. The residual gap is the inline comments themselves — file-level `# mypy: disable-error-code` comments are their own suppression surface, and this audit measures only `pyproject.toml` scopes.
- It measures what mypy reports **today**. A code that is load-bearing now can become vacuous later when the last violation is fixed, which is why the weekly schedule is not gated on `pyproject.toml` changing.

---

## File Structure

```
scripts/health/
├── dead_modules.py                    # Zero-importer modules + orphan packages
├── dead_doc_links.py                  # Markdown link validator
├── stale_names.py                     # Deprecated identifier scanner
├── duplicate_headings.py              # Repeated headings under one parent
├── markdown_fences.py                 # Shared CommonMark fence walker (links + names)
└── mypy_suppressions.py               # Dead mypy suppression auditor
scripts/validate_cross_references.py   # Skill↔doc cross-reference validator
```

**Related:**
- `./dev health` — runs every check above except `mypy_suppressions.py` (weekly CI)
- `./dev bloat` — separate check for unused events/methods (different scope) — see [BLOAT_DETECTION.md](BLOAT_DETECTION.md)
- `docs/tools/AUTOMATIC_DOCS_CHECK.md` — post-commit hook for doc freshness
- `docs/user-guides/documentation-freshness.md` — unified user guide
