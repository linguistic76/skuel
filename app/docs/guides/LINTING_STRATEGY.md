---
title: SKUEL Linting Strategy
updated: 2025-11-27
status: current
category: guides
tags: [guides, linting, strategy]
related: []
---

# SKUEL Linting Strategy
**Research & Recommendation**
*Date: January 2025*

---

## Executive Summary

**Question:** Should SKUEL build a custom linter or leverage existing tools like Ruff?

**Answer:** **Use both in a layered approach:**
1. **Ruff** for standard Python quality (fast, comprehensive, industry-standard)
2. **Custom architecture linter** for SKUEL-specific patterns (domain rules that Ruff cannot enforce)

---

## Current State Analysis

### ✅ What We Have

**1. Ruff Configuration (pyproject.toml)**
```toml
[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = [
    "F",     # Pyflakes
    "E",     # pycodestyle (errors)
    "W",     # pycodestyle (warnings)
    "I",     # isort
    "N",     # pep8-naming
    "UP",    # pyupgrade
    "B",     # flake8-bugbear
    "SIM",   # flake8-simplify
    "TCH",   # flake8-type-checking
    "ARG",   # flake8-unused-arguments
    "PTH",   # flake8-use-pathlib
    "RUF",   # Ruff-specific rules
    "ANN",   # flake8-annotations (type hints)
    "ASYNC", # flake8-async
    "LOG",   # flake8-logging-format
]
```

**Key Rules Enabled:**
- ✅ **E731**: Detect lambda assignments (enforces our "no lambda" policy)
- ✅ **ANN**: Type annotation checking
- ✅ **TCH**: Type-checking imports optimization
- ✅ **B**: Bugbear (common mistakes)
- ✅ **SIM**: Simplify suggestions

**2. Custom Architecture Linter (archived)**
- Location: `scripts/archive/2025_migrations/lint_skuel_architecture.py`
- Status: Archive (Phase 8.1 - October 2025)
- Purpose: SKUEL-specific architectural rules

**3. Type Checkers**
- MyPy (strict mode enabled)
- Pyright (VS Code integration)

---

## What Ruff Can Do (Standard Python Quality)

### ✅ Already Catching

| Rule | What It Catches | SKUEL Benefit |
|------|----------------|---------------|
| **E731** | Lambda assignments | Enforces "no lambda" policy |
| **ANN** | Missing type hints | Type safety |
| **TCH** | Type-checking imports | Import optimization |
| **ARG** | Unused arguments | Clean code |
| **SIM** | Simplifiable code | Readability |
| **B** | Common mistakes | Bug prevention |
| **UP** | Outdated syntax | Modern Python |

### ✅ Can Configure for SKUEL

```toml
[tool.ruff.lint.per-file-ignores]
# Domain services MUST NOT use APOC (Phase 5)
"core/services/**/*.py" = []  # No exceptions

# Adapters CAN use APOC (infrastructure layer)
"adapters/**/*.py" = []

# Test flexibility
"tests/**/*.py" = ["ANN", "ARG001", "S101"]
```

### ✅ Auto-Fix Capabilities

```bash
# Fix violations automatically
poetry run ruff check --fix

# Show what would be fixed
poetry run ruff check --diff

# Fix unsafe violations too
poetry run ruff check --fix --unsafe-fixes
```

---

## What Ruff Cannot Do (SKUEL-Specific Architecture)

### ❌ Domain-Specific Rules Ruff Cannot Enforce

| Rule | Why Ruff Can't Catch | Needs Custom Linter |
|------|---------------------|---------------------|
| **APOC in services** | Domain-specific ban | YES - Critical |
| **Semantic type enums** | Context-aware (not magic strings) | YES - Important |
| **Result[T] returns** | Convention, not syntax error | YES - Important |
| **Protocol-based DI** | Architectural pattern | YES - Nice to have |
| **100% Dynamic Pattern** | SKUEL-specific concept | YES - Important |
| **Confidence thresholds** | Semantic query best practice | YES - Nice to have |

---

## Recommended Layered Approach

### Layer 1: Ruff (Standard Quality) ⚡

**Purpose:** Fast, comprehensive, industry-standard Python linting

**When to run:**
- ✅ Pre-commit hook (fast, catches common issues)
- ✅ CI/CD pipeline (gating deployment)
- ✅ Editor integration (real-time feedback)

**Command:**
```bash
# Run on whole codebase (fast - seconds)
poetry run ruff check .

# Auto-fix violations
poetry run ruff check --fix .

# CI/CD mode (exit code for failures)
poetry run ruff check . --output-format=github
```

**Benefits:**
- ⚡ Blazingly fast (10-100x faster than pylint)
- 🔧 Auto-fix for most violations
- 📊 Comprehensive rule coverage (700+ rules)
- 🎯 Zero configuration overhead (sensible defaults)
- 🚀 Active development (Rust-based, maintained)

### Layer 2: Custom SKUEL Linter (Architecture Enforcement) 🏛️

**Purpose:** Enforce SKUEL-specific architectural patterns

**When to run:**
- ✅ Weekly architecture review
- ✅ Before major refactoring
- ✅ CI/CD (non-blocking warnings)
- ❌ NOT in pre-commit (too slow, too specific)

**Command:**
```bash
# Restore from archive
cp scripts/archive/2025_migrations/lint_skuel_architecture.py scripts/

# Run architecture checks
poetry run python scripts/lint_skuel_architecture.py

# Strict mode (treat warnings as errors)
poetry run python scripts/lint_skuel_architecture.py --strict
```

**Critical Rules to Keep:**

1. **SKUEL001: APOC in Domain Services (CRITICAL)**
   ```python
   def _check_apoc_in_services(self):
       """Phase 5: APOC is ONLY allowed in adapter layer"""
       banned_apoc = [
           "apoc.path.subgraphNodes",
           "apoc.path.expandConfig",
           # ... etc
       ]
   ```

2. **SKUEL002: Magic String Semantic Types (ERROR)**
   ```python
   def _check_semantic_type_strings(self):
       """Use SemanticRelationshipType enum, not magic strings"""
       # Catch: relationship_type = "REQUIRES_KNOWLEDGE"
       # Want: relationship_type = SemanticRelationshipType.REQUIRES_KNOWLEDGE
   ```

3. **SKUEL003: 100% Dynamic Pattern Violations (ERROR)**
   ```python
   def _check_wrapper_functions(self):
       """Detect wrapper functions hiding UniversalNeo4jBackend"""
       # Catch: def _create_domain_backends() -> dict
       # Want: backend = UniversalNeo4jBackend[Task](driver, "Task", Task)
   ```

4. **SKUEL004: Result[T] Return Types (WARNING)**
   ```python
   def _check_result_return_types(self):
       """Service methods should return Result[T]"""
       # Catch: async def get_task(...) -> Task:
       # Want: async def get_task(...) -> Result[Task]:
   ```

### Layer 3: Type Checkers (Type Safety) 🔒

**Already configured:**
- MyPy (strict mode)
- Pyright (VS Code integration)

**When to run:**
- ✅ Pre-commit (fast, catches type errors)
- ✅ CI/CD pipeline (gating deployment)
- ✅ Editor integration (real-time)

---

## Recommended Workflow

### 1. Daily Development (Fast Feedback)

```bash
# Pre-commit hook (runs automatically)
poetry run ruff check --fix .
poetry run mypy core adapters
```

### 2. Pre-Pull Request (Comprehensive Check)

```bash
# Standard quality
poetry run ruff check .

# Type safety
poetry run mypy core adapters

# Architecture (if touching services)
poetry run python scripts/lint_skuel_architecture.py
```

### 3. CI/CD Pipeline (Automated Gating)

```yaml
# .github/workflows/lint.yml
jobs:
  lint:
    steps:
      - name: Ruff (fast, comprehensive)
        run: poetry run ruff check . --output-format=github

      - name: MyPy (type safety)
        run: poetry run mypy core adapters

      - name: SKUEL Architecture (non-blocking)
        run: poetry run python scripts/lint_skuel_architecture.py
        continue-on-error: true  # Warnings, not blockers
```

### 4. Weekly Architecture Review

```bash
# Deep architectural analysis
poetry run python scripts/lint_skuel_architecture.py --strict

# Review output:
# - CRITICAL: Must fix immediately
# - ERROR: Fix before next release
# - WARNING: Technical debt to address
# - INFO: Suggestions for improvement
```

---

## Recommendations

### ✅ DO

1. **Keep Ruff as primary linter**
   - Fast, comprehensive, industry-standard
   - Replaces: flake8, isort, pyupgrade, black
   - Auto-fix saves time

2. **Restore custom architecture linter**
   - Move from `scripts/archive/` to `scripts/`
   - Update for current patterns:
     - 100% Dynamic Pattern enforcement
     - Operator standardization checking
     - Sort function usage validation

3. **Add new SKUEL rules:**
   ```python
   def _check_operator_usage(self):
       """SKUEL rule: No lambda, use operator or named functions"""

   def _check_dynamic_pattern(self):
       """SKUEL rule: Direct UniversalNeo4jBackend usage"""

   def _check_sort_functions(self):
       """SKUEL rule: Use centralized sort_functions.py"""
   ```

4. **Layer the approach:**
   - Ruff: Pre-commit + CI/CD (fast, blocking)
   - SKUEL linter: Weekly + pre-refactor (comprehensive, non-blocking)
   - Type checkers: Pre-commit + CI/CD (type safety, blocking)

### ❌ DON'T

1. **Don't replace Ruff with custom linter**
   - Ruff is orders of magnitude faster
   - Industry-standard rules are valuable
   - Auto-fix is a huge time saver

2. **Don't run architecture linter in pre-commit**
   - Too slow (seconds vs milliseconds)
   - Too specific (not all commits touch architecture)
   - Better as periodic deep check

3. **Don't duplicate Ruff rules in custom linter**
   - E731 (lambda) already caught by Ruff
   - Let Ruff handle standard Python quality
   - Custom linter = SKUEL-specific only




## Example Output

### Ruff Output (Fast, Standard)

```bash
$ poetry run ruff check core/services/

core/services/tasks_service.py:45:5: E731 Do not assign a lambda expression, use a def
    |
45  |     sort_key = lambda x: x.priority
    |     ^^^^^^^^ E731
    |

core/services/events_service.py:102:1: ANN201 Missing return type annotation for public function
    |
102 | def create_event(self, data):
    | ^^^^ ANN201
    |

Found 2 errors.
[*] 1 fixable with --fix
```

### SKUEL Linter Output (Architecture, Domain-Specific)

```bash
$ poetry run python scripts/lint_skuel_architecture.py --strict

================================================================================
SKUEL ARCHITECTURE LINTER - PHASE 8.1
================================================================================

🔴 CRITICAL: 1 violation(s)
--------------------------------------------------------------------------------
  core/services/knowledge_service.py:156
  [SKUEL001] APOC procedure 'apoc.path.subgraphNodes' in domain service
  💡 Use CypherGenerator instead. Phase 5 eliminated APOC from domain services.

❌ ERROR: 2 violation(s)
--------------------------------------------------------------------------------
  core/services/tasks_service.py:89
  [SKUEL002] Magic string 'REQUIRES_KNOWLEDGE' instead of enum
  💡 Use SemanticRelationshipType.REQUIRES_KNOWLEDGE enum.

  core/services/goals_service.py:45
  [SKUEL011] Wrapper function hiding UniversalNeo4jBackend
  💡 Use UniversalNeo4jBackend[Goal] directly at point of use.

⚠️  WARNING: 3 violation(s)
--------------------------------------------------------------------------------
  core/services/habits_service.py:120
  [SKUEL004] Service method should return Result[T]
  💡 Change return type to Result[Habit]. Phase 7.1 pattern.

  ...

================================================================================
Total violations: 6
  Critical: 1
  Errors: 2
  Warnings: 3
  Info: 0
================================================================================

🔴 CRITICAL violations found. Must fix before merging.
```

---

## Conclusion

**Best Practice: Layered Linting Strategy**

1. **Ruff** - Daily, fast, auto-fix standard Python quality
2. **Custom SKUEL Linter** - Weekly, comprehensive, architecture enforcement
3. **Type Checkers** - Daily, type safety, CI/CD gating

**Key Insight:** Don't build what exists (Ruff handles 90% of quality checks). Build what's unique to SKUEL (architectural patterns Ruff cannot understand).

---

## References

- **Ruff Documentation**: https://docs.astral.sh/ruff/
- **Custom Linter**: `/scripts/archive/2025_migrations/lint_skuel_architecture.py`
- **SKUEL Patterns**: `/home/mike/0bsidian/skuel/docs/CLAUDE.md`
- **Phase 5 (No APOC)**: Archived migrations
- **100% Dynamic Pattern**: CLAUDE.md section

---

*Last Updated: January 2025*
*Next Review: Quarterly*
