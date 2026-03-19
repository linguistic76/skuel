---
title: Code Quality Enforcement - Linter Rules
updated: 2026-03-19
category: patterns
related_skills:
- python
related_docs: []
---

# Code Quality Enforcement - Linter Rules
## Related Skills

For implementation guidance, see:
- [@python](../../.claude/skills/python/SKILL.md)


## Core Principle: "Automated enforcement prevents pattern violations"

**SKUEL uses automated linting to enforce architectural patterns** that cannot be caught by standard type checkers.

## Linter Configuration

**Primary Linters:**
1. **Ruff** (`ruff check`) - Fast Python linter with 100+ rules
2. **MyPy** (`mypy`) - Static type checker
3. **Pyright** (`pyright`) - Additional type checker for VS Code
4. **SKUEL Pattern Linter** (`scripts/lint_skuel.py`) - Custom architectural patterns
5. **Cypher Linter** (`scripts/cypher_linter.py`) - Static analysis for Neo4j queries (CYP001–CYP010)

**Unit Tests:** Both custom linters have comprehensive unit test coverage:
- `tests/unit/scripts/test_lint_skuel.py` — 83 tests covering all 17 SKUEL rules, LintResult, suppression
- `tests/unit/scripts/test_cypher_linter.py` — 35 tests covering CYP001–CYP006, CYP009, query extraction, helpers

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
| **SKUEL016** | Stale Poetry references | SKUEL uses uv, not Poetry |
| **SKUEL017** | Bare `except Exception` | Use specific exception types from `exception_types.py` |

## Inline Suppression

When a rule needs to be suppressed for a legitimate reason, use inline comments instead of hardcoded allowlists:

```python
# Line-level suppression
route_count = len(app.routes) if hasattr(app, "routes") else 0  # skuel-lint: disable=SKUEL011 -- FastHTML app attribute check

# File-level suppression (place at top of file, before docstring)
# skuel-lint: disable-file=SKUEL005 -- Cache service, raw values not Result[T]
```

**Supported rules:** SKUEL005, SKUEL011, SKUEL012, SKUEL015, SKUEL017.

**SKUEL017** additionally recognizes `# intentional-broad: <reason>` and `# safety-net: <reason>` (261 existing uses).

**Always include a reason** after `--` to document why the suppression is needed.

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

**Cypher query strings:** Use f-strings with `RelationshipName.X.value` interpolation. Escape Neo4j property maps (`{uid: $x}` → `{{uid: $x}}`).

```python
# ❌ VIOLATION - Hardcoded relationship in Cypher
query = """
MATCH (parent:Entity {uid: $uid})-[:HAS_SUBTASK]->(child)
RETURN child
"""

# ✅ CORRECT - Enum in f-string
query = f"""
MATCH (parent:Entity {{uid: $uid}})-[:{RelationshipName.HAS_SUBTASK.value}]->(child)
RETURN child
"""
```

**Coverage (March 2026):** All 80+ relationships enforced — Activity Domain hierarchy (HAS_SUBTASK/SUBTASK_OF, HAS_SUBGOAL/SUBGOAL_OF, HAS_SUBHABIT/SUBHABIT_OF, HAS_SUBPRINCIPLE/SUBPRINCIPLE_OF, HAS_SUBCHOICE/SUBCHOICE_OF, HAS_SUBEVENT/SUBEVENT_OF), cross-domain (SUPPORTS_GOAL, GUIDED_BY_PRINCIPLE, ALIGNED_WITH_PRINCIPLE, CONFLICTS_WITH_PRINCIPLE, REINFORCES_KNOWLEDGE, etc.), Lesson/Ku composition (USES_KU, TRAINS_KU, ORGANIZES), lateral (BLOCKS, BLOCKED_BY, DEPENDS_ON, COMPLEMENTARY_TO, ALTERNATIVE_TO, PREREQUISITE_FOR, SIBLING), sharing (SHARES_WITH, SHARED_WITH_GROUP), groups (MEMBER_OF, FOR_GROUP), ownership (OWNS), achievements (UNLOCKED_ACHIEVEMENT, EARNED_BADGE), reflections (REFLECTS_ON, REVEALS_CONFLICT), life path (ULTIMATE_PATH, SERVES_LIFE_PATH).

**Infrastructure defense-in-depth:** Even when callers use `RelationshipName` enum (safe), the infrastructure layer validates all relationship type strings before Cypher interpolation via `validate_relationship_type()` in `_build_direction_pattern()`, `traverse()`, `find_path()`, and query builder functions. See `/docs/patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md`.

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

## Rule: SKUEL017 - Narrow except Exception Catches

**Pattern:** Use specific exception types instead of bare `except Exception`.

```python
# ❌ VIOLATION - Bare except Exception
try:
    result = await self.backend.get(uid)
except Exception as e:
    return Result.fail(Errors.database(operation="get", message=str(e)))

# ✅ CORRECT - Specific exception type from exception_types.py
from core.utils.exception_types import NEO4J_EXCEPTIONS

try:
    result = await self.backend.get(uid)
except NEO4J_EXCEPTIONS as e:
    return Result.fail(Errors.database(operation="get", message=str(e)))

# ✅ CORRECT - Annotated intentional broad catch (event handlers, monadic boundaries)
except Exception as e:  # intentional-broad: event handler must not propagate
    logger.error(f"Handler failed: {e}")

# ✅ CORRECT - Safety-net during validation period
except Exception as e:  # safety-net: catch unexpected errors
    logger.error(f"Unexpected {type(e).__name__}: {e}")
    return Result.fail(Errors.system(message="Unexpected error", exception=e))
```

**Available exception tuples** (from `core/utils/exception_types.py`):

| Tuple | Exceptions | Maps to |
|-------|-----------|---------|
| `NEO4J_EXCEPTIONS` | Neo4jError, DriverError, ServiceUnavailable, SessionExpired, AuthError | `Errors.database()` |
| `OPENAI_EXCEPTIONS` | APIError, APIConnectionError, APITimeoutError, RateLimitError | `Errors.integration("openai")` |
| `ANTHROPIC_EXCEPTIONS` | APIError, APIConnectionError, APITimeoutError, RateLimitError | `Errors.integration("anthropic")` |
| `LLM_EXCEPTIONS` | All OpenAI + Anthropic exceptions | `Errors.integration("llm")` |
| `FILE_IO_EXCEPTIONS` | FileNotFoundError, PermissionError, IsADirectoryError, OSError | `Errors.system()` |
| `PARSING_EXCEPTIONS` | ValueError, KeyError, JSONDecodeError, YAMLError | `Errors.validation()` |
| `DATA_CONVERSION_EXCEPTIONS` | ValueError, TypeError, AttributeError, KeyError, ZeroDivisionError | `Errors.validation()` / `Errors.system()` |
| `CONFIG_EXCEPTIONS` | FileNotFoundError, JSONDecodeError, ValueError, OSError, KeyError, TypeError | `Errors.system()` |

**Suppression markers** (same line or line above):
- `# intentional-broad: <reason>` — catches that must remain broad (event handlers, monadic boundaries, metrics wrappers)
- `# safety-net: <reason>` — temporary broad catches during narrowing rollout
- `# skuel-lint: disable=SKUEL017 -- <reason>` — unified suppression format (also supported)

**Rationale:**
- Bare `except Exception` masks bugs and makes debugging harder
- Specific types enable correct error categorization (DATABASE vs SYSTEM vs INTEGRATION)
- Suppression markers document why a broad catch is intentional

**Exceptions:**
- Test files (`tests/**/*.py`)
- Scripts (`scripts/**/*.py`)
- `result_simplified.py` (monadic boundaries annotated separately)

## Running the Linters

**Run all linters:**
```bash
# Ruff - fast Python linter
uv run ruff check .

# MyPy - type checking
uv run mypy core/ adapters/ routes/

# SKUEL pattern linter (all rules)
uv run python scripts/lint_skuel.py

# With error exit for CI
uv run python scripts/lint_skuel.py --check
```

**New CLI options (December 2025):**
```bash
# Lint specific file or directory
uv run python scripts/lint_skuel.py --file core/services/

# Run only specific rules
uv run python scripts/lint_skuel.py --rule SKUEL011 --rule SKUEL012

# Show rule documentation
uv run python scripts/lint_skuel.py --explain SKUEL011

# List all available rules
uv run python scripts/lint_skuel.py --list-rules

# Show code context around violations
uv run python scripts/lint_skuel.py --context

# Quiet mode for CI (minimal output)
uv run python scripts/lint_skuel.py --quiet --check

# JSON output for tooling integration
uv run python scripts/lint_skuel.py --json

# Treat warnings as errors
uv run python scripts/lint_skuel.py --strict
```

**Auto-fix violations (where possible):**
```bash
uv run ruff check --fix .
uv run python scripts/lint_skuel.py --fix
```

## CI/CD Integration

Add to pre-commit hooks or CI pipeline:

```yaml
# .github/workflows/ci.yml
- name: Lint SKUEL patterns
  run: uv run python scripts/lint_skuel.py --check
```

## Linter Configuration Files

- **pyproject.toml** - Main configuration for ruff, mypy, pyright
- **scripts/lint_skuel.py** - Custom SKUEL pattern enforcement (17 rules)
- **scripts/cypher_linter.py** - Cypher query static analysis (10 rules, 2 disabled)
- **Exceptions documented in:** `pyproject.toml` section `[tool.ruff.lint.per-file-ignores]`

## Exclusion Patterns

The linter automatically excludes certain files from specific rules. Per-file exemptions use inline suppression comments (see above) rather than hardcoded allowlists.

| Rule | Auto-Excluded Directories | Per-File Suppression |
|------|--------------------------|---------------------|
| **SKUEL005** | Protocol files | `# skuel-lint: disable-file=SKUEL005` |
| **SKUEL008** | Domain backends (`domain_backends.py`) | N/A |
| **SKUEL011** | Tests, `sort_functions.py` | `# skuel-lint: disable=SKUEL011` |
| **SKUEL012** | Tests, `examples/` | `# skuel-lint: disable=SKUEL012` |
| **SKUEL015** | Tests, `scripts/`, `examples/`, `debug_*`, `lint_skuel.py`, `dev`, `__main__` blocks, docstrings | `# skuel-lint: disable=SKUEL015` |
| **SKUEL017** | Tests, `scripts/`, `result_simplified.py` | `# intentional-broad:`, `# safety-net:`, or `# skuel-lint: disable=SKUEL017` |

## Benefits Achieved

1. **Automated Enforcement** - Patterns checked on every commit
2. **Fast Feedback** - Violations caught before code review
3. **Consistent Codebase** - All code follows same patterns
4. **Self-Documenting** - Linter messages explain best practices (`--explain`)
5. **Flexible Severity** - CRITICAL/ERROR block CI, WARNING for gradual improvement

---

**Last Updated:** March 19, 2026
**Status:** Active - 17 rules enforcing SKUEL architectural patterns, unified inline suppression via `# skuel-lint: disable=SKUELXXX`. 118 unit tests cover both linters.
