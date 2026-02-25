---
title: Code Quality Enforcement - Linter Rules
updated: 2026-01-05
category: patterns
related_skills:
- python
related_docs: []
---

# Code Quality Enforcement - Linter Rules
## Related Skills

For implementation guidance, see:
- [@python](../../.claude/skills/python/SKILL.md)


## Quick Reference

SKUEL uses automated linting to enforce architectural patterns that cannot be caught by standard type checkers.

## Core Principle: "Automated enforcement prevents pattern violations"

**SKUEL uses automated linting to enforce architectural patterns** that cannot be caught by standard type checkers.

## Linter Configuration

**Primary Linters:**
1. **Ruff** (`ruff check`) - Fast Python linter with 100+ rules
2. **MyPy** (`mypy`) - Static type checker
3. **Pyright** (`pyright`) - Additional type checker for VS Code
4. **SKUEL Pattern Linter** (`scripts/lint_skuel.py`) - Custom architectural patterns

## SKUEL-Specific Rules

The unified linter enforces SKUEL architectural patterns with three severity levels:

### CRITICAL (blocks CI)
| Rule | Pattern | Enforcement |
|------|---------|-------------|
| **SKUEL001** | APOC in services | Use CypherGenerator, not APOC in domain services |

### ERROR (blocks CI)
| Rule | Pattern | Enforcement |
|------|---------|-------------|
| **SKUEL002** | Magic semantic strings | Use `SemanticRelationshipType` enum |
| **SKUEL003** | `.is_err` usage | Use `.is_error` instead [auto-fix] |

### WARNING (reported, doesn't block)
| Rule | Pattern | Enforcement |
|------|---------|-------------|
| **SKUEL004** | Missing confidence threshold | Semantic queries need confidence filters |
| **SKUEL005** | Non-Result return types | Service methods should return `Result[T]` |
| **SKUEL007** | String `Result.fail()` | Use `Errors` factory |
| **SKUEL008** | Backend wrapper classes | Use `UniversalNeo4jBackend` directly |
| **SKUEL009** | Tuple defaults | Single-element tuple bug [auto-fix] |
| **SKUEL010** | Nested tuples | Neo4j can't store nested collections [auto-fix] |
| **SKUEL011** | `hasattr()` usage | Use Protocol/isinstance |
| **SKUEL012** | Lambda expressions | Use named functions |
| **SKUEL013** | RelationshipName strings | Use `RelationshipName` enum |
| **SKUEL014** | EntityType/NonKuDomain strings | Use `EntityType` or `NonKuDomain` enum |
| **SKUEL015** | Print in production code | Use `logger.*()` instead |

## Rule: SKUEL003 - Deprecated .is_err

**Pattern:** Prefer `.is_error` over `.is_err` for better readability.

```python
# ❌ VIOLATION - Deprecated .is_err
if result.is_err:
    return result

# ✅ CORRECT - Use .is_error
if result.is_error:
    return result
```

**Rationale:**
- `.is_ok` / `.is_error` provides better symmetry
- More explicit than `.is_ok` / `.is_err`
- Documented standard since October 11, 2025

**Exceptions:** None - `.is_err` is deprecated everywhere

## Rule: SKUEL011 - hasattr() in Production Code

**Pattern:** Use explicit type checks instead of `hasattr()`.

```python
# ❌ VIOLATION - hasattr() for type checking
if hasattr(obj, 'value'):
    return obj.value

if hasattr(user, 'preferences'):
    prefs = user.preferences

# ✅ CORRECT - Explicit type checks
from core.ports import get_enum_value
value = get_enum_value(obj)  # Helper for enum extraction

if user.preferences is not None:
    prefs = user.preferences

# ✅ CORRECT - Try/except for duck typing
try:
    task_dict = task.to_dict()
except AttributeError:
    task_dict = task
```

**Rationale:**
- Type safety - explicit checks are clearer
- Protocols - use `isinstance(obj, Protocol)` for interface checking
- Optional fields - use `obj.field is not None` for presence checks

**Exceptions:**
- `core/utils/sort_functions.py` - Duck typing for generic sort utilities
- `core/utils/mock_decorators.py` - Testing function metadata
- `tests/**/*.py` - Test utilities can use `hasattr()`

## Rule: SKUEL007 - String-Based Result.fail()

**Pattern:** Use `Errors` factory for all error creation.

```python
# ❌ VIOLATION - String-based error
return Result.fail("Task not found")
return Result.fail(f"Analysis error: {e}")

# ❌ VIOLATION - Dict-based error
return Result.fail({
    "message": "No valid items found",
    "errors": parse_errors
})

# ✅ CORRECT - Errors factory
return Result.fail(Errors.not_found(resource="Task", identifier=uid))
return Result.fail(Errors.system(message="Analysis failed", exception=e))
return Result.fail(Errors.validation(
    message="No valid items found",
    details={"errors": parse_errors}
))
```

**Rationale:**
- Searchable error codes (e.g., `NOT_FOUND_TASK`, `DB_GET_TASK`)
- Structured details for analytics
- User-safe messages separate from developer messages
- Automatic source location tracking

**Exceptions:**
- Error propagation: `Result.fail(result.error)` is ACCEPTABLE (passing errors up)

## Rule: SKUEL012 - Lambda Expressions

**Pattern:** Use named functions instead of lambda expressions.

```python
# ❌ VIOLATION - Lambda assignment
get_priority = lambda item: item.priority.to_numeric()
tasks.sort(key=lambda t: t.priority.to_numeric())

# ✅ CORRECT - Named function
from core.utils.sort_functions import get_priority_value

def get_priority(item):
    """Get numeric priority value for sorting."""
    return item.priority.to_numeric()

tasks.sort(key=get_priority_value, reverse=True)
```

**Rationale:**
- Named functions are self-documenting
- Easier to test and debug
- Can be reused across codebase
- Standard enforcement via ruff E731

**Exceptions:**
- `tests/**/*.py` - Tests can use lambdas for mocking
- `examples/**/*.py` - Examples can use lambdas for demonstration
- `core/utils/mock_decorators.py` - Mock utilities

## Rule: SKUEL013 - RelationshipName Enum

**Pattern:** Use `RelationshipName` enum instead of magic strings for relationship types.

```python
# ❌ VIOLATION - Magic string
await backend.add_relationship(uid1, "SERVES_GOAL", uid2)

# ✅ CORRECT - Use enum
from core.models.relationship_names import RelationshipName
await backend.add_relationship(uid1, RelationshipName.SERVES_GOAL, uid2)
```

**Rationale:**
- Type safety - IDE autocomplete and MyPy verification
- Single source of truth - all relationships in one place
- Refactoring safety - rename in one place

**Note:** Cypher query strings still use literal relationship names (unavoidable).

## Rule: SKUEL014 - EntityType / NonKuDomain Enum

**Pattern:** Use `EntityType` or `NonKuDomain` enum instead of magic strings for entity type identification.

```python
# ❌ VIOLATION - Magic string comparison
if entity_type == "task":
    ...
if "task" in contexts:
    ...

# ✅ CORRECT - Use enum
from core.models.enums.entity_enums import EntityType
if entity.entity_type == EntityType.TASK:
    ...
if EntityType.TASK in activity.contexts:
    ...

# ✅ CORRECT - Non-entity domains
from core.models.enums.entity_enums import NonKuDomain
if domain == NonKuDomain.FINANCE:
    ...
```

**Rationale:**
- Type safety with compile-time verification
- Better IDE support and autocomplete
- Consistent with domain-first model (`DomainIdentifier = EntityType | NonKuDomain`)

## Rule: SKUEL015 - Print Statements in Production Code

**Pattern:** Use `logger.*()` instead of `print()` for production runtime output.

```python
# VIOLATION - print bypasses logging infrastructure
def validate_config():
    if missing:
        print(f"Missing: {missing}")
        return False

# CORRECT - structured logging
from core.utils.logging import get_logger
logger = get_logger("skuel.config")

def validate_config():
    if missing:
        logger.error("Missing config", missing=missing)
        return False
```

**Rationale:**
- Structured logging enables log analysis and monitoring
- Logs are persisted to files with rotation
- Log levels allow filtering (DEBUG/INFO/WARNING/ERROR)
- Context fields support structured queries

**Exceptions (print is acceptable):**
- **Docstring examples** - Pedagogically clearer than logger calls
- **CLI utilities** - Interactive terminal tools (e.g., `credential_setup.py`)
- **`if __name__ == "__main__"` blocks** - Demo/development code only

**See:** [LOGGING_PATTERNS.md](LOGGING_PATTERNS.md) for complete logging guidelines.

## Running the Linters

**Run all linters:**
```bash
# Ruff - fast Python linter
poetry run ruff check .

# MyPy - type checking
poetry run mypy core/ adapters/ routes/

# SKUEL pattern linter (all rules)
poetry run python scripts/lint_skuel.py

# With error exit for CI
poetry run python scripts/lint_skuel.py --check
```

**New CLI options (December 2025):**
```bash
# Lint specific file or directory
poetry run python scripts/lint_skuel.py --file core/services/

# Run only specific rules
poetry run python scripts/lint_skuel.py --rule SKUEL011 --rule SKUEL012

# Show rule documentation
poetry run python scripts/lint_skuel.py --explain SKUEL011

# List all available rules
poetry run python scripts/lint_skuel.py --list-rules

# Show code context around violations
poetry run python scripts/lint_skuel.py --context

# Quiet mode for CI (minimal output)
poetry run python scripts/lint_skuel.py --quiet --check

# JSON output for tooling integration
poetry run python scripts/lint_skuel.py --json

# Treat warnings as errors
poetry run python scripts/lint_skuel.py --strict
```

**Auto-fix violations (where possible):**
```bash
poetry run ruff check --fix .
poetry run python scripts/lint_skuel.py --fix
```

## CI/CD Integration

Add to pre-commit hooks or CI pipeline:

```yaml
# .github/workflows/ci.yml
- name: Lint SKUEL patterns
  run: poetry run python scripts/lint_skuel.py --check
```

## Linter Configuration Files

- **pyproject.toml** - Main configuration for ruff, mypy, pyright
- **scripts/lint_skuel.py** - Custom SKUEL pattern enforcement (15 rules)
- **Exceptions documented in:** `pyproject.toml` section `[tool.ruff.lint.per-file-ignores]`

## Exclusion Patterns

The linter automatically excludes certain files from specific rules:

| Rule | Excluded Files/Patterns |
|------|------------------------|
| **SKUEL008** | Curriculum backends (`ls_backend.py`, `lp_backend.py`, `moc_backend.py`, `ku_backend.py`) - legitimate domain-specific extensions |
| **SKUEL011** | UI routes (`*_ui.py`), components (`*_components.py`), tests, sort utilities |
| **SKUEL012** | Tests, examples, mock utilities |
| **SKUEL015** | Scripts, tests, examples, CLI utilities, `__main__` blocks, docstrings |

## Benefits Achieved

1. **Automated Enforcement** - Patterns checked on every commit
2. **Fast Feedback** - Violations caught before code review
3. **Consistent Codebase** - All code follows same patterns
4. **Self-Documenting** - Linter messages explain best practices (`--explain`)
5. **Flexible Severity** - CRITICAL/ERROR block CI, WARNING for gradual improvement

---

**Last Updated:** January 5, 2026
**Status:** Active - 15 rules enforcing SKUEL architectural patterns
