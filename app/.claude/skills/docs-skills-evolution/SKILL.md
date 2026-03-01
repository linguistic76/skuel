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

## Documentation Focus vs Skills Focus

**Documentation changes more frequently (70% of evolution):**
- Code patterns evolve → docs updated
- Bug fixes reveal edge cases → docs clarified
- Library minor versions → syntax examples updated
- Performance optimizations → pattern docs evolved

**Skills change less frequently (30% of evolution):**
- Library major version changes core API
- Fundamental pattern shifts across many files
- New cross-cutting concerns emerge

**Post-commit hook detects new documentation files** and prompts INDEX updates. Cross-reference validation (`validate_cross_references.py`) is a manual tool — run it after major changes.

---

## Part 1: Library Upgrade Workflow

### When a Core Library Upgrades

**Philosophy**: SKUEL aligns with ecosystem evolution, not resists it.

**Automatic Detection** (post-merge hook):
```bash
# After git pull, if poetry.lock changed:
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
poetry run pytest tests/unit/test_fasthtml*.py

# Check for deprecation warnings
poetry run python -W all start_server.py
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
poetry run python scripts/validate_cross_references.py

# Check for orphaned references
rg "old_pattern" docs/

# Run full test suite
poetry run pytest

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
poetry run python scripts/validate_cross_references.py

# Run tests
poetry run pytest

# Check for old pattern usage
rg "old_pattern" . --type py  # Should return nothing
```

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
poetry run python scripts/generate_cross_reference_index.py
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
- Regenerate: `poetry run python scripts/generate_cross_reference_index.py`

### Coverage Metrics

```bash
poetry run python scripts/validate_cross_references.py

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

### Manual Validation

```bash
# Full validation with warnings
poetry run python scripts/validate_cross_references.py

# Errors only
poetry run python scripts/validate_cross_references.py --errors-only

# Verbose (show all issues including info)
poetry run python scripts/validate_cross_references.py --verbose
```

### Detection Script

```bash
# Detect library changes manually
poetry run python scripts/detect_library_changes.py

# Compare with specific ref
poetry run python scripts/detect_library_changes.py --from-ref HEAD~5
```

---

## Part 6: Validation Checklist

### When to Run Validation

**Automatic** (already in place):
- ✅ **On every commit** - Post-commit hook prompts INDEX update when new `.md` files added
- ✅ **After git pull** - Post-merge hook detects library changes

**Manual** (after major changes):
- After library upgrade:
  ```bash
  poetry run python scripts/validate_cross_references.py
  ```
- After pattern deprecation:
  ```bash
  poetry run pytest && \
  poetry run python scripts/validate_cross_references.py
  ```
- **Monthly audit** - Full validation + review warnings:
  ```bash
  poetry run python scripts/validate_cross_references.py --verbose
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
| Skills metadata | `.claude/skills/skills_metadata.yaml` |
| Post-commit hook | `scripts/hooks/post-commit` → `scripts/docs_contextual_check_v2.py` |
| Post-merge hook | `scripts/hooks/post-merge` |
| Cross-reference validator | `scripts/validate_cross_references.py` |
| Library change detector | `scripts/detect_library_changes.py` |
| Cross-reference index | `docs/CROSS_REFERENCE_INDEX.md` (auto-generated) |
| ADR template | `docs/decisions/ADR-TEMPLATE.md` |

### Key Commands

```bash
# Validate cross-references
poetry run python scripts/validate_cross_references.py

# Detect library changes
poetry run python scripts/detect_library_changes.py

# Regenerate cross-reference index
poetry run python scripts/generate_cross_reference_index.py

# Run with verbose output
poetry run python scripts/validate_cross_references.py --verbose
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

### Example ADRs Showing Evolution
- `/docs/decisions/ADR-020.md` - FastHTML route registration
- `/docs/decisions/ADR-035.md` - Pydantic tier selection
- `/docs/decisions/ADR-037.md` - Neo4j lateral relationships

---

**Last Updated:** 2026-03-01
