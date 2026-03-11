# Documentation & Skills Evolution

**Expert guide for how SKUEL's documentation and skills evolve in rhythm with the ecosystem.**

## Core Philosophy: Alignment with Ecosystem

**SKUEL doesn't dictate evolution - it responds to and aligns with the evolution of its tech stack.**

### The Fundamental Principle

SKUEL is built on established open-source technologies:
- **FastHTML** - Server-rendered hypermedia framework
- **Neo4j** - Graph database
- **Pydantic** - Data validation
- **Alpine.js** - Client-side reactivity
- **Prometheus** - Metrics collection

**When these libraries evolve, SKUEL adapts.** We don't maintain backward compatibility or create legacy wrappers. We follow the "One Path Forward" philosophy.

### What This Means

| Scenario | SKUEL Response |
|----------|----------------|
| **Library upgrades to new major version** | Update all code to use new API (no wrappers) |
| **Library deprecates a feature** | Remove usage immediately, adopt replacement |
| **Library introduces better pattern** | Evaluate and adopt if superior |
| **Library changes philosophy** | Align with new direction or re-evaluate dependency |

### Historical Context Preservation

When patterns change, **we delete the old code but preserve the context**:

```markdown
## ADR-XXX: Migrated from Pattern A to Pattern B

**Context:**
FastHTML 1.4 introduced automatic form validation (PEP 695 type hints),
deprecating manual validation decorators.

**Decision:**
Remove all @validate decorators, adopt native FastHTML validation.

**Historical Note:**
Prior to FastHTML 1.4, we used manual @validate decorators (see commit abc123).
This pattern was necessary because FastHTML lacked native validation.
When FastHTML added this feature, we immediately migrated to align with
the framework's intended usage.
```

**Key**: ADRs show *why* we changed (external forces), not just *what* changed.

---

## Two Drivers of Doc Evolution

Doc evolution has two equally important triggers:

| Driver | Frequency | Workflow |
|--------|-----------|----------|
| **Library upgrade** | Major versions, deprecations | Part 1 (Library Upgrade) |
| **Internal refactor** | Decompositions, renames, merges | Part 2b (Stale Document Audit) |

**Documentation changes more frequently (70% of evolution):**
- Code patterns evolve → docs updated
- Bug fixes reveal edge cases → docs clarified
- Library minor versions → syntax examples updated
- Performance optimizations → pattern docs evolved
- Internal refactors drift from existing docs → staleness audit

**Skills change less frequently (30% of evolution):**
- Library major version changes core API
- Fundamental pattern shifts across many files
- New cross-cutting concerns emerge
- Internal refactors change file layouts referenced in skills

**Post-commit hook detects new documentation files** and prompts INDEX updates. Cross-reference validation (`validate_cross_references.py`) is a manual tool — run it after major changes.

---

## Part 1: Library Upgrade Workflow

### When a Core Library Upgrades

**Philosophy**: SKUEL aligns with ecosystem evolution, not resists it.

**Automatic Detection** (post-merge hook):
```bash
# After git pull, if uv.lock changed:
⚠️  Library versions changed. Consider reviewing:

📦 python-fasthtml: 0.12.21 → 0.12.39
   Skills potentially affected:
   - @fasthtml
   - @html-htmx
   - @skuel-form-patterns

   Changelog: https://github.com/AnswerDotAI/fasthtml/releases
```

**Manual Workflow:**

#### 1. Identify Impact
Which SKUEL patterns use this library?

```bash
# Search documentation
grep -r "FastHTML" docs/patterns/

# Check skills metadata
cat .claude/skills/skills_metadata.yaml | grep -A5 "python-fasthtml"
```

#### 2. Test Existing Patterns
Do current examples still work?

```bash
# Run affected tests
uv run pytest tests/unit/test_fasthtml*.py

# Check for deprecation warnings
uv run python -W all start_server.py
```

#### 3. Research Evolution
What's new that SKUEL should adopt?

- Read library release notes/changelog
- Identify breaking changes vs enhancements
- Check migration guides

#### 4. Decide Adaptation

| Change Type | SKUEL Response |
|-------------|----------------|
| **Breaking change** | MUST update (no backward compatibility) |
| **Enhancement** | SHOULD adopt if better than current pattern |
| **New feature** | EVALUATE if it solves an existing problem |
| **Deprecation** | REMOVE immediately, adopt replacement |

#### 5. Document the Change

Create ADR using `/docs/decisions/ADR-TEMPLATE.md`:

```markdown
## Context
FastHTML 1.5 introduced automatic route registration via decorators,
deprecating manual app.register() calls.

## Decision
Migrate all routes to decorator-based registration.

## Consequences
- 30% less boilerplate in route files
- Aligns with FastHTML's intended usage pattern
- No manual registration errors

## Historical Context
Prior to FastHTML 1.5, we used manual app.register() (see ADR-020).
This was necessary because FastHTML lacked decorator support.
```

#### 6. Update Artifacts (In Order)

**a) Code first** - Update all usage (no legacy wrappers)
```bash
# Find all occurrences
rg "old_pattern" --type py

# Replace everywhere
# NO backward compatibility shims
```

**b) Documentation second** - Update pattern docs with new syntax
```bash
# Update pattern doc
vim docs/patterns/FASTHTML_ROUTE_REGISTRATION.md

# Add @fasthtml reference if not present
```

**c) Skills third** - Update if library API significantly changed
```bash
# Update skill metadata version
vim .claude/skills/skills_metadata.yaml
# Change library_version: "0.12.39"

# Update skill content if API changed
vim .claude/skills/fasthtml/SKILL.md
```

**d) CLAUDE.md last** - Update quick-reference if fundamental
```bash
# Only if pattern is core to SKUEL's identity
vim CLAUDE.md
```

#### 7. Validate

```bash
# Run cross-reference validator
uv run python scripts/validate_cross_references.py

# Check for orphaned references
rg "old_pattern" docs/

# Run full test suite
uv run pytest

# Commit with library upgrade context
git commit -m "Upgrade FastHTML to 1.5, adopt decorator routes

See ADR-XXX for migration rationale.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Part 2: Pattern Deprecation Workflow

### When Deprecating an Old Pattern

**Philosophy**: Delete old path, preserve context for why we changed.

#### 1. Confirm Superiority
Is new pattern objectively better?

- ✅ Performance improvement measured
- ✅ Aligns with library best practices
- ✅ Reduces complexity/boilerplate
- ❌ Just "different" (not better)

#### 2. Document the Decision

Create ADR:

```markdown
## ADR-XXX: Migrate from Manual Validation to Pydantic V2

**Context:**
Pydantic V2 introduced field validators with better type inference,
making our custom validation decorators redundant.

**Decision:**
Remove all custom @validate decorators, use Pydantic field_validator.

**Why:**
- Native Pydantic support (no custom code maintenance)
- Better IDE autocomplete
- 40% less boilerplate

**Historical Note:**
Prior to Pydantic V2, we used custom @validate decorators (see commit xyz789).
This was necessary because Pydantic V1 lacked field-level validators.
When Pydantic V2 added this feature, we migrated to align with the library's
intended usage pattern.
```

#### 3. Update All Code (Zero Tolerance)

```bash
# Find all occurrences
rg "old_pattern" --type py

# Replace everywhere - NO compatibility shims
# NO legacy wrappers
# NO "_deprecated" functions

# Example: Don't do this ❌
def old_function(*args):
    warnings.warn("Use new_function instead")
    return new_function(*args)

# Just delete and update call sites ✅
```

#### 3b. Update `stale_names.py`

When you rename or delete something significant, add it to the scanner so doc code blocks are flagged automatically:

```python
# scripts/health/stale_names.py

RENAMED: dict[str, str] = {
    "OldClassName": "NewClassName",           # class rename
    "EntityType.OLD_VALUE": "EntityType.NEW_VALUE",  # enum value
    "old_method_name": "new_method_name",     # method rename
    "from old.module.path import": "from new.module.path import",  # module move
}

DELETED: dict[str, str] = {
    "DeletedClass": "reason or replacement description",
    "old_module_name": "replaced by NewModule",
}
```

Then verify no docs still use the old name:

```bash
./dev health-names   # exit non-zero = stale doc code blocks found
```

#### 4. Update Documentation

```bash
# Replace pattern doc
mv docs/patterns/OLD_PATTERN.md docs/patterns/NEW_PATTERN.md

# Update cross-references
rg "@old-pattern" docs/ | # Find all references
# Replace with @new-pattern or remove

# Don't create "deprecated" docs
# Delete old doc completely
```

#### 5. Preserve Context (ADR Only)

- ✅ **ADR remains** - Shows evolution history
- ✅ **Git history** - Preserves old code for reference
- ❌ **No deprecation warnings** - Code is deleted, not deprecated
- ❌ **No _OLD files** - Clean removal

#### 6. Validate

```bash
# Run cross-reference validator manually
uv run python scripts/validate_cross_references.py

# Run tests
uv run pytest

# Check for old pattern usage
rg "old_pattern" . --type py  # Should return nothing
```

---

## Part 2b: Stale Document Audit Workflow

### When Internal Refactors Outpace Docs

**Trigger:** A batch of internal refactors (file renames, service splits, model renames, class hierarchy changes) leaves existing docs describing code that no longer exists.

**Philosophy**: Don't hand-patch stale docs line-by-line. Investigate first — confirm replacements exist, verify live symbols, regenerate auto-generated files, then fix cross-references in one sweep.

#### The Four-Tier Investigation Process

Triage all suspect docs before touching anything:

**Tier 1: Confirmed Replacements (delete immediately)**

The old doc explicitly says "superseded by X" *and* the replacement fully covers the scope:

```bash
# Check if replacement doc exists and covers the same ground
ls docs/patterns/UNIFIED_RELATIONSHIP_SERVICE.md  # replacement exists?
grep -c "DOMAIN_RELATIONSHIPS_PATTERN" docs/patterns/UNIFIED_RELATIONSHIP_SERVICE.md
```

If the replacement covers all key patterns → delete the old doc.

**Tier 2: Verify Against Codebase Before Deleting**

Doc may be stale, but grep live `.py` sources first to confirm the referenced symbols are actually gone:

```bash
# Does the three-layer architecture described in this doc still exist?
rg "relationship_base" --type py    # Layer 1
rg "relationship_validation" --type py  # Layer 2
rg "unified_relationships" --type py   # Layer 3

# If nothing returns — the pattern is truly gone, delete the doc
# If results return — the doc is stale but the pattern lives on; UPDATE not delete
```

`./dev health-modules` automates the harder version of this: it finds Python files that are *never imported* anywhere, surfacing orphaned modules that refactors left behind. Run it after a major dissolution to get the full list at once rather than grepping file-by-file.

**Tier 3: Regenerate, Don't Hand-Edit**

For auto-generated reference docs (method indexes, catalogs), run the generator rather than editing manually:

```bash
# Stale method index → regenerate from live code
uv run python scripts/generate_method_index.py

# Don't manually patch 50 method signatures — regenerate always wins
```

**Tier 4: Fix Cross-References in One Pass**

After deletions/merges, update the registry files:

```bash
# 1. Remove deleted entries from INDEX.md
# 2. Remove deleted entries from CROSS_REFERENCE_INDEX.md
# 3. Find all broken doc links (automated):
./dev health-links          # lists every broken markdown/backtick/bare path reference
# 4. Fix dangling references in docs that pointed to deleted files
```

`dead_doc_links.py` replaces the manual `rg "DELETED_DOC_NAME" docs/` pattern. It catches three reference kinds at once (markdown links, backtick paths, bare absolute paths) across all 330+ docs and skills. When `docs/INDEX.md` has broken links, it calls it out specifically:

```
⚠  docs/INDEX.md has 24 broken reference(s) — update the index to match current files
```

#### Document Consolidation (Merge, Not Delete)

When two docs have overlapping scope, merge the narrower into the broader canonical doc:

1. **Identify the canonical doc** — which one has broader scope and more up-to-date content?
2. **Absorb missing content** — fold unique sections from the narrower doc into the canonical
3. **Strip stale language** — remove "pending", "future", "Phase N complete", "rollout phases" (these become noise once the feature ships)
4. **Update cross-references** — redirect all `@skill` or `/docs/...` references to the canonical doc
5. **Delete the absorbed doc**

```bash
# Example: after merging SERVICE_FILE_ORGANIZATION.md → SERVICE_TOPOLOGY.md
rg "SERVICE_FILE_ORGANIZATION" docs/ --type md  # Find all references
# Update each reference to SERVICE_TOPOLOGY.md
```

#### Audit Commit Pattern

Batch all audit changes into one commit with a tiered message:

```
docs: prune 6 superseded pattern docs, update cross-references

Tier 1 (confirmed replacements):
- Delete OLD_DOC.md → REPLACEMENT.md (confirmed coverage)

Tier 2 (verified against codebase):
- Delete OTHER_DOC.md — symbols no longer exist in .py sources

Tier 3 (auto-generated):
- Regenerate BASESERVICE_METHOD_INDEX.md from live code

Tier 4 (cross-references):
- Remove deleted-file entries from INDEX.md and CROSS_REFERENCE_INDEX.md
- Fix dangling references in N docs and skills_metadata.yaml
```

#### Skill Updates After Internal Refactors

When a refactor changes file layouts or class names referenced in a skill, update the skill too:

```bash
# Example: domain_views.py decomposed into 4 modules
# → Update skuel-ui SKILL.md Key Files table and strategy examples
grep -l "domain_views" .claude/skills/*/SKILL.md  # Find affected skills
```

Concrete real-world examples in skills are more valuable than abstract descriptions. When a refactor improves the architecture, update the skill's examples to show the new pattern.

---

## Part 3: New Feature Documentation Workflow

### When Adding New Feature to SKUEL

**Philosophy**: Document as you build, validate as you commit.

#### 1. Implement Feature (Code First)

Write the code, tests, then docs.

#### 2. Determine Doc Type

| Feature Type | Documentation Path |
|--------------|-------------------|
| New pattern approach | `/docs/patterns/FEATURE_NAME.md` |
| Architectural change | `/docs/architecture/SYSTEM_NAME.md` |
| Major decision | `/docs/decisions/ADR-XXX.md` |
| Implementation detail | Docstrings only (no separate doc) |

**Three-Layer Documentation** (see `/docs/patterns/DOCSTRING_STANDARDS.md`):

| Layer | Purpose | Location |
|-------|---------|----------|
| **Implementation** | "What does THIS do?" | Docstrings in code |
| **Pattern** | "How do we solve this?" | `/docs/patterns/` |
| **Architecture** | "Why designed this way?" | `/docs/architecture/` |

#### 3. Write Documentation

**Pattern Doc Template:**

```markdown
# Pattern Name

**Purpose**: One-sentence description

**Use When**: Specific scenarios where this pattern applies

**Core Concept**: Brief explanation

## Implementation

[Code examples]

## When NOT to Use

[Anti-patterns, alternatives]

## Related

- See: @relevant-skill
- See: /docs/architecture/RELATED_ARCHITECTURE.md
```

#### 4. Cross-Reference

**In documentation** - Add skill references:
```markdown
See: @fasthtml for route registration patterns
```

**In skill metadata** - Add doc references (if skill affected):
```yaml
# .claude/skills/skills_metadata.yaml
- name: fasthtml
  primary_docs:
    - /docs/patterns/FASTHTML_ROUTE_REGISTRATION.md
    - /docs/patterns/NEW_FEATURE.md  # <-- Add here
```

#### 5. Commit (Pre-commit Validates)

```bash
git add .
git commit -m "Add feature X with pattern docs

Implements new pattern for Y.
See /docs/patterns/FEATURE_X.md for usage.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"

# Post-commit hook runs:
# ✅ Detects new .md files → prompts INDEX.md update
# ✅ Detects new skill docs → prompts CLAUDE.md update
# (Cross-reference analysis removed — too many false positives)
```

#### 6. Update Index (If Needed)

```bash
# Auto-generated on next commit, or manual:
uv run python scripts/generate_cross_reference_index.py
```

---

## Part 4: Cross-Reference System

### How Skills ↔ Docs Link Bidirectionally

**Central Registry**: `.claude/skills/skills_metadata.yaml`

```yaml
- name: fasthtml
  library_package: python-fasthtml  # PyPI package
  library_version: "0.12.39"       # Last reviewed version
  primary_docs:
    - /docs/patterns/FASTHTML_ROUTE_REGISTRATION.md
  related_adrs:
    - ADR-020
  patterns:
    - /docs/patterns/ROUTE_FACTORIES.md
```

**In Documentation** - Reference skills:
```markdown
See: @fasthtml for route registration patterns
```

**Auto-Generated Index**: `/docs/CROSS_REFERENCE_INDEX.md`
- Maps skills → docs
- Maps docs → skills
- Shows bidirectional links
- Regenerate: `uv run python scripts/generate_cross_reference_index.py`

### Coverage Metrics

```bash
uv run python scripts/validate_cross_references.py

# Output:
📊 Statistics:
   Total skills: 27
   Total docs scanned: 352
   Bidirectional links: 95/120 (79.2%)
   Broken links: 0
   Missing reverse links: 25
```

---

## Part 5: Validation & Tooling

### Post-Commit Hook (Automatic)

**Location**: `scripts/hooks/post-commit`

**Runs after every commit — new file detection only:**
- ✅ New `.md` in `docs/` → prompts `docs/INDEX.md` update (CRITICAL)
- ✅ New `.md` in `.claude/skills/` → prompts `CLAUDE.md` update (HIGH)

Cross-reference analysis was removed (flagged every doc mentioning a changed
filename, regardless of whether the API changed — too many false positives).
Semantic doc awareness is handled by the Claude Code PostToolUse hook.

```bash
# Disable if needed:
git config skuel.docs-check false

# Re-enable:
git config skuel.docs-check true
```

### Post-Merge Hook (Automatic)

**Location**: `.git/hooks/post-merge` → `scripts/hooks/post-merge`

**Detects library changes after git pull:**
```bash
$ git pull

# ... merge happens ...

⚠️  Library versions changed. Consider reviewing:

📦 python-fasthtml: 0.12.21 → 0.12.39
   Skills potentially affected:
   - @fasthtml (primary)
   - @html-htmx (depends on fasthtml)

   Workflow: See @docs-skills-evolution "Library Upgrade Workflow"
   Changelog: https://github.com/AnswerDotAI/fasthtml/releases
```

### Health Check Scripts (./dev health)

Three automated scripts in `scripts/health/` that prevent drift between refactors, doc links, and terminology. These are the automated counterpart to the manual verification steps in Part 2b.

```bash
./dev health              # run all three checks (exit non-zero if any issues)
./dev health-modules      # dead Python modules only
./dev health-links        # broken doc links only
./dev health-names        # stale identifiers in doc code blocks only
```

| Script | What it finds | When to run |
|--------|--------------|-------------|
| `dead_modules.py` | Python files with zero importers | After a monolith dissolution or service split |
| `dead_doc_links.py` | Broken markdown links, backtick paths, bare absolute paths | After any file rename/delete |
| `stale_names.py` | Old class/method/enum names in doc code blocks | After a rename or deprecation |

**`dead_doc_links.py`** is the fastest way to confirm INDEX.md is clean after pruning docs. It specifically calls out INDEX.md violations:

```
⚠  docs/INDEX.md has 24 broken reference(s) — update the index to match current files
```

**`stale_names.py`** is only as useful as its RENAMED/DELETED tables. Update it whenever you rename or delete something significant (see Part 2, Step 3b). Run `./dev health-names --list` to see all tracked renames.

**See:** `docs/tools/HEALTH_CHECKS.md` for full reference including known limitations.

### Manual Validation

```bash
# Full validation with warnings
uv run python scripts/validate_cross_references.py

# Errors only
uv run python scripts/validate_cross_references.py --errors-only

# Verbose (show all issues including info)
uv run python scripts/validate_cross_references.py --verbose
```

### Detection Script

```bash
# Detect library changes manually
uv run python scripts/detect_library_changes.py

# Compare with specific ref
uv run python scripts/detect_library_changes.py --from-ref HEAD~5
```

---

## Part 6: Validation Checklist

### When to Run Validation

**Automatic** (already in place):
- ✅ **On every commit** - Post-commit hook prompts INDEX update when new `.md` files added
- ✅ **After git pull** - Post-merge hook detects library changes

**Manual** (after major changes):
- After file renames/deletes:
  ```bash
  ./dev health-links   # find all broken doc references
  ```
- After class/method/enum renames (update stale_names.py first):
  ```bash
  ./dev health-names   # find stale identifiers in doc code blocks
  ```
- After a major dissolution or service split:
  ```bash
  ./dev health-modules  # find orphaned Python modules
  ```
- After library upgrade:
  ```bash
  uv run python scripts/validate_cross_references.py
  ```
- After pattern deprecation:
  ```bash
  ./dev health-names && \
  uv run pytest && \
  uv run python scripts/validate_cross_references.py
  ```
- **Monthly audit** - Full sweep:
  ```bash
  ./dev health
  uv run python scripts/validate_cross_references.py --verbose
  ```

### What Validators Check

**Post-commit hook** (automatic — `docs_contextual_check_v2.py`):

| Check | Confidence | Action |
|-------|------------|--------|
| New `.md` in `docs/` | CRITICAL | Prompts INDEX.md update |
| New `.md` in `.claude/skills/` | HIGH | Prompts CLAUDE.md update |

**Manual validator** (`validate_cross_references.py`):

| Check | Severity | Notes |
|-------|----------|-------|
| **Broken skill references** | ❌ Error | `@skill-name` in docs exists? |
| **Broken doc links** | ❌ Error | `/docs/...` file exists? |
| **Missing reverse links** | ⚠️  Warning | Bidirectional coverage |
| **Orphaned docs** | ℹ️  Info | Suggests improvements |

---

## Part 7: ADR Creation Pattern

### Documenting Architectural Decisions

**When to Create ADR:**
- Library upgrade changes core patterns
- Deprecating a significant pattern
- Making architectural decision with multiple options
- External forces (library evolution) drive change

**Template**: `/docs/decisions/ADR-TEMPLATE.md`

**Key Sections for Ecosystem Alignment:**

```markdown
## Context

**External Forces:**
- FastHTML 1.5 introduced feature X
- Neo4j deprecated APOC procedure Y
- Pydantic V2 changed validation approach

**Internal Impact:**
- 45 files use the old pattern
- Migration effort: 3 hours
- Risk: Medium (well-tested migration path)

## Decision

We will [specific action].

## Consequences

**Positive:**
- Aligns with library best practices
- Reduces maintenance burden
- Improves performance by X%

**Negative:**
- Short-term migration effort
- Must update documentation

## Historical Context

Prior to [library version], we used [old pattern] because [reason].
This pattern was necessary at the time but is now superseded by
the library's native support for [feature].

**Evidence of Evolution:**
- Commit abc123: Old pattern implementation
- Library changelog: https://...
- Migration commit: xyz789
```

**Key**: Show *why* SKUEL changed (library evolved) not just *what* changed.

---

## Part 8: Fundamentals vs Adaptive Patterns

### What is "Fundamental"?

**Fundamental = Patterns dictated by the core tech stack**

These should be respected and aligned with:

| Library | Fundamental Patterns |
|---------|---------------------|
| **FastHTML** | Route registration, FT components, request handling |
| **Neo4j** | Cypher query syntax, relationship patterns, driver usage |
| **Pydantic** | Validation models, BaseModel usage, field validators |
| **Python** | Async/await, type hints, protocol classes |
| **Alpine.js** | x-data, x-show, x-on directives |

**When library upgrades, SKUEL adapts fundamentals.**

### What is "Adaptive"?

**Adaptive = SKUEL-specific patterns built on fundamentals**

These can evolve independently:

| SKUEL Pattern | Built On |
|---------------|----------|
| **Result[T]** | Python types (fundamental) |
| **BaseService** | Neo4j driver (fundamental) + SKUEL architecture |
| **DomainConfig** | Pydantic (fundamental) + SKUEL design |
| **Route Factories** | FastHTML (fundamental) + SKUEL patterns |

**When fundamentals change, adaptive patterns must be re-evaluated.**

### Decision Matrix

```
Does the pattern exist in the library's official docs?
├─ YES → Fundamental (respect library's approach)
└─ NO  → Is it built directly on a fundamental?
    ├─ YES → Adaptive (can evolve, but must respect fundamentals)
    └─ NO  → Custom (maximum flexibility)
```

---

## Quick Reference

### File Locations

| Purpose | Location |
|---------|----------|
| Health check scripts | `scripts/health/` (`dead_modules.py`, `dead_doc_links.py`, `stale_names.py`) |
| Health check docs | `docs/tools/HEALTH_CHECKS.md` |
| Skills metadata | `.claude/skills/skills_metadata.yaml` |
| Post-commit hook | `scripts/hooks/post-commit` → `scripts/docs_contextual_check_v2.py` |
| Post-merge hook | `scripts/hooks/post-merge` |
| Cross-reference validator | `scripts/validate_cross_references.py` |
| Library change detector | `scripts/detect_library_changes.py` |
| Cross-reference index | `docs/CROSS_REFERENCE_INDEX.md` (auto-generated) |
| ADR template | `docs/decisions/ADR-TEMPLATE.md` |

### Key Commands

```bash
# Health checks (run after any refactor/rename)
./dev health              # all three checks
./dev health-modules      # orphaned Python modules
./dev health-links        # broken doc links
./dev health-names        # stale identifiers in doc code blocks
./dev health-names --list # print full RENAMED/DELETED tables

# Cross-reference validation
uv run python scripts/validate_cross_references.py
uv run python scripts/validate_cross_references.py --verbose

# Detect library changes
uv run python scripts/detect_library_changes.py

# Regenerate cross-reference index
uv run python scripts/generate_cross_reference_index.py
```

### Evolution Philosophy Summary

1. **SKUEL aligns with ecosystem** - Library evolution drives SKUEL evolution
2. **One path forward** - No backward compatibility, no legacy wrappers
3. **Preserve context** - ADRs show *why* we changed (external forces)
4. **Documentation focus** - 70% docs evolve, 30% skills evolve
5. **Validate early** - Post-commit detects new docs; post-merge detects library changes; run `validate_cross_references.py` manually after major changes
6. **Fundamentals vs adaptive** - Respect library patterns, adapt SKUEL patterns

---

## Related Documentation

### Core Philosophy
- `/docs/patterns/DOCSTRING_STANDARDS.md` - Three-layer documentation approach
- `/docs/decisions/ADR-TEMPLATE.md` - How to document decisions
- `/CLAUDE.md` - "One Path Forward" philosophy

### Cross-Reference System
- `/docs/CROSS_REFERENCE_INDEX.md` - Auto-generated skill↔doc mapping
- `.claude/skills/skills_metadata.yaml` - Central registry

### Health Check Tooling
- `/docs/tools/HEALTH_CHECKS.md` - Complete reference for the three health scripts
- `scripts/health/stale_names.py` - Maintainable RENAMED/DELETED tables (update on every rename)

### Example ADRs Showing Evolution
- `/docs/decisions/ADR-020.md` - FastHTML route registration
- `/docs/decisions/ADR-035.md` - Pydantic tier selection
- `/docs/decisions/ADR-037.md` - Neo4j lateral relationships

---

**Last Updated:** 2026-03-03
