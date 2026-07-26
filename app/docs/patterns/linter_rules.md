---
title: Code Quality Enforcement - Linter Rules
updated: 2026-07-17
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

> **Quick start:** See [Linter Guide](../guides/LINTER_GUIDE.md) for how to run linters and the full command reference. See [UV Guide](../guides/UV_GUIDE.md) for package manager commands.

## Linter Configuration

**Primary Linters:**
1. **Ruff** (`ruff check`) - Fast Python linter with 100+ rules
2. **MyPy** (`mypy`) - Static type checker
3. **Pyright** (`pyright`) - Additional type checker for VS Code
4. **SKUEL Pattern Linter** (`scripts/lint_skuel.py`) - Custom architectural patterns
5. **Cypher Linter** (`scripts/cypher_linter.py`) - Static analysis for Neo4j queries (CYP001–CYP011), covering Cypher embedded in Python strings AND standalone `.cypher` files (indexes, migrations — semicolon-split statements, comment-masked; since PR #710)

**Unit Tests:** Both custom linters have comprehensive unit test coverage:
- `tests/unit/scripts/test_lint_skuel.py` — 367 tests covering all 26 active SKUEL rules, LintResult, suppression + the SKUEL026 audit
- `tests/unit/scripts/test_cypher_linter.py` — 76 tests covering CYP001–CYP006, CYP009, Python query extraction, `.cypher` statement extraction, file discovery, helpers

## SKUEL-Specific Rules

The unified linter enforces SKUEL architectural patterns with three severity levels:

### CRITICAL (blocks CI)
| Rule | Pattern | Enforcement |
|------|---------|-------------|
| **SKUEL001** | Any `apoc.*` above the boundary — `core/`, `adapters/inbound/`, `ui/` | Use CypherGenerator / pure Cypher below the boundary (ADR-044); namespace-matched, docstring-aware, unsuppressable |

### ERROR (blocks CI)
| Rule | Pattern | Enforcement |
|------|---------|-------------|
| **SKUEL002** | Magic semantic strings | Use `SemanticRelationshipType` enum (AST rule, docstring-aware) |
| **SKUEL003** | `.is_err` usage | Use `.is_error` instead [auto-fix] |
| **SKUEL020** | `request: Any` on `@rt`/`@app.*` handlers | Annotate `request: Request` (AST rule) |
| **SKUEL021** | Raw Cypher above the boundary — `core/`, `adapters/inbound/`, `ui/` | Relocate below the boundary (ADR-044) |
| **SKUEL022** | `adapters/` imports in `core/` | Depend on a `core/ports` protocol; inject the adapter (ADR-044) |
| **SKUEL023** | `self.backend` typed against an adapter class in `core/` | Type against the `core/ports` protocol (AST rule, ADR-044) |
| **SKUEL024** | Hardcoded `cls=` + `**kwargs` splat without a `cls` param | Add explicit `cls: str = ""` and merge (AST rule) |
| **SKUEL025** | A deleted Activity `*UpdatePayload` name (ADR-066) | Use the domain `*UpdateIntent` / `*UpdateRequest.to_intent()` (AST rule) |
| **SKUEL027** | Runtime `adapters/` imports in `ui/` | Move shared code inward or pass values in from the route (AST rule, SKUEL022's ui/ sibling) |

### WARNING (blocks `./dev lint` / `./dev quality` via `--strict`; plain runs report only)

The WARNING tier reached zero codebase-wide in July 2026 and both gate commands
now pass `--strict`, so a new warning fails lint/quality. The tier still differs
from ERROR: a plain `uv run python scripts/lint_skuel.py` (no `--strict`) reports
warnings without failing, which is the on-ramp for prototyping a new rule.

> **SKUEL004 (confidence thresholds on semantic queries) was deleted 2026-07.**
> Its premise — Cypher authored in services — is structurally impossible since
> SKUEL021 banned all raw Cypher in `core/`, it had zero hits, and its
> "look 5 lines past MATCH for 'confidence'" heuristic could not be made sound
> as a structural AST rule. Rule IDs are not renumbered.

| Rule | Pattern | Enforcement |
|------|---------|-------------|
| **SKUEL005** | Non-Result return types | Async service methods return `Result[T]` (AST rule — catches multi-line signatures; Protocol stubs, nested helpers, `@classmethod` factories exempt) |
| **SKUEL006** | TODO/FIXME tracking | Categorizes and tracks TODO/FIXME comments [INFO] |
| **SKUEL007** | String `Result.fail()` | Use `Errors` factory (catches literal and `str(...)` first arguments) |
| **SKUEL008** | Backend wrapper classes | Use `UniversalNeo4jBackend` directly |
| **SKUEL009** | Tuple defaults | Single-element tuple bug [auto-fix] |
| **SKUEL010** | Nested tuples | Neo4j can't store nested collections [auto-fix] |
| **SKUEL011** | `hasattr()` usage | Use Protocol/isinstance |
| **SKUEL012** | Lambda expressions | Use named functions |
| **SKUEL013** | RelationshipName strings | Use `RelationshipName` enum (AST rule, docstring-aware, exact-value match) |
| **SKUEL014** | EntityType/NonKuDomain strings in comparisons | Use `EntityType` or `NonKuDomain` enum (AST rule — flags `==`/`!=`/`in` shapes incl. literal containers) |
| **SKUEL015** | Print in production code | Use `logger.*()` instead |
| **SKUEL016** | Stale Poetry references | SKUEL uses uv, not Poetry |
| **SKUEL017** | Bare `except Exception` | Use specific exception types from `exception_types.py` (AST rule — catches formatter-wrapped clauses and `Exception` inside tuples) |
| **SKUEL018** | Direct read of `RichUserContext` rich-only fields | Use accessor methods (`get_X()` / `X_or_empty()`) |
| **SKUEL019** | Credential reads bypassing `get_credential()` | ERROR for catalog keys, WARNING for credential-shape names |
| **SKUEL026** | Suppression comment that suppresses nothing | Delete the rotted comment — see "Suppression audit" below |
| **SKUEL030** | Unregistered label / relationship type in persistence Cypher | Register it in `NeoLabel` / `RelationshipName`, or fix the name (AST rule, docstring-aware) |
| **SKUEL031** | Stale pip references (`pip/pip3 install\|uninstall\|freeze`, `python -m pip`, incl. `uv pip install`) | SKUEL is lockfile-managed by uv — `uv add` / `uv sync` / `uv remove` / `uv export`; the `pip-audit` tool name is not caught |

## Inline Suppression

When a rule needs to be suppressed for a legitimate reason, use inline comments instead of hardcoded allowlists:

```python
# Line-level suppression
route_count = len(app.routes) if hasattr(app, "routes") else 0  # skuel-lint: disable=SKUEL011 -- FastHTML app attribute check

# File-level suppression (place at top of file, before docstring)
# skuel-lint: disable-file=SKUEL005 -- Cache service, raw values not Result[T]
```

**Supported rules:** SKUEL005, SKUEL011, SKUEL012, SKUEL013, SKUEL014, SKUEL015, SKUEL017, SKUEL018, SKUEL019, SKUEL020, SKUEL021, SKUEL022, SKUEL023, SKUEL024, SKUEL025, SKUEL027, SKUEL028, SKUEL029, SKUEL030 — the `SUPPRESSIBLE_RULES` set in `lint_skuel.py`, drift-guarded by `TestSuppressibleRulesDrift` (a source scan of the suppression-helper call sites). A comment naming any other rule does nothing and is flagged by SKUEL026.

**SKUEL017** additionally recognizes `# intentional-broad: <reason>` and `# safety-net: <reason>` (anywhere in the except-clause header, or the line above — both survive formatter wrapping).

**Always include a reason** after `--` to document why the suppression is needed.

### Suppression audit (SKUEL026)

Every run audits suppression comments: files containing them are shadow-linted with
suppressions ignored, and a comment is **used** only if it actually suppressed a
violation. Anything else — the guarded violation was refactored away, the rule isn't
suppressible, a typo'd rule ID, a malformed comment — is flagged as SKUEL026 (WARNING,
so it fails the `--strict` gates). The summary reports active/used counts per rule, and
`--json` includes a full `suppressions` block.

Discovery is tokenize-based: only genuine `#` comments count, so suppression examples
inside string literals and docstrings (rule docs, linter tests) are never audited.

**Suppression placement (span-aware since 2026-07):** every checker reads the
`# skuel-lint: disable=` comment off the exact line it reports — except the two
rules that fire on multi-line headers, which honor the comment on **any line of
the construct's header**:

- **SKUEL005** — anywhere from the `async def` line through the line before the
  body (so a comment the formatter strands on the closing `) -> X:` line still
  suppresses).
- **SKUEL017** — anywhere from the `except` line through the line before the
  handler body (`# intentional-broad:` / `# safety-net:` markers are additionally
  honored on the line above the `except`).

The `Violation.suppression_span` field carries that range, and the SKUEL026 audit
reads the SAME span — so a header-stranded suppression is correctly marked *used*,
not rot. This closes the pre-#590 formatter trap where wrapping a statement
silently killed its trailing suppression. For every other rule the comment must
sit on the reported line; file-level suppression is always the fallback.

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

# ❌ VIOLATION - str() wrap (dodges the literal shape, same flattening)
return Result.fail(str(e))
return Result.fail(str(result.error))

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

# ✅ CORRECT - Error propagation across type boundaries
return Result.fail(result)
```

**Rationale:**
- Searchable error codes (e.g., `NOT_FOUND_TASK`, `DB_GET_TASK`)
- Structured details for analytics
- User-safe messages separate from developer messages
- Automatic source location tracking

`Result.fail(str(result.error))` deserves special mention: it *looks* like
propagation but flattens a structured `ErrorContext` into a generic SYSTEM error,
losing the category, code, and details. Use `Result.fail(result)` — six such
wraps hid in `ingestion_tracker.py` until the `str(...)` shape was added to the
pattern (2026-07).

**Detection (2026-07):** regex on the first argument — a string literal
(plain/f-string, same line or wrapped to the next) or a `str(...)` call. It
previously matched literals only and carried line-based exemptions for
`result.error` / `.error)` substrings, which would have masked exactly the
`str(result.error)` shape; both gaps are closed.

**Scope:** any `/services/` path **plus the inbound/presentation layers** —
`adapters/inbound/` and `ui/` (widened 2026-07, same layers as
SKUEL013/SKUEL014). Test files are skipped.

## Rule: SKUEL012 - Lambda Expressions

**Pattern:** Use named functions instead of lambda expressions.

For **simple attribute or item extraction**, use `operator.attrgetter` /
`operator.itemgetter` — they are named stdlib callables that satisfy this rule and
require no helper file:

```python
# ❌ VIOLATION - Lambda
tasks.sort(key=lambda t: t.due_date)
results.sort(key=lambda r: r[1], reverse=True)

# ✅ CORRECT - stdlib callables for plain extraction
from operator import attrgetter, itemgetter

tasks.sort(key=attrgetter('due_date'))
results.sort(key=itemgetter(1), reverse=True)

# ✅ CORRECT - named helper only when there is real logic
def get_priority_value(item):
    """Convert priority enum/string to numeric, with Neo4j string fallback."""
    ...

tasks.sort(key=get_priority_value, reverse=True)
```

**Do NOT** add one-liner wrappers to `core/utils/sort_functions.py` for plain field
access — that file is for domain logic, None-fallback, and composite sort keys.

**Rationale:**
- Named functions are self-documenting
- `operator.attrgetter`/`itemgetter` communicate intent precisely and avoid a junk-drawer module
- Easier to test and debug
- Standard enforcement via ruff E731

**Exceptions:**
- `tests/**/*.py` - Tests can use lambdas for mocking
- `examples/**/*.py` - Examples can use lambdas for demonstration
- `scripts/**/*.py` - Scripts can use lambdas (non-production, matches SKUEL015 exemption)

## Rule: SKUEL013 - RelationshipName Enum

**Pattern:** Use `RelationshipName` enum instead of magic strings for relationship types.

```python
# ❌ VIOLATION - Magic string
await backend.add_relationship(uid1, "SUPPORTS_GOAL", uid2)

# ✅ CORRECT - Use enum
from core.models.relationship_names import RelationshipName
await backend.add_relationship(uid1, RelationshipName.SUPPORTS_GOAL, uid2)
```

**Detection (AST, 2026-07):** flags a *used* string constant whose value is exactly
a relationship name — docstrings, comments, and prose are structurally immune, and a
name embedded in a longer string (Cypher text, log messages) is not an exact match,
so no Cypher-context heuristics are needed.

**Scope:** any `/services/` path **plus the inbound/presentation layers** —
`adapters/inbound/` and `ui/` (widened 2026-07: raw relationship strings
crept into routes and renderers too). Test files are
skipped. `adapters/persistence/` is below the boundary and stays out of scope —
Cypher there interpolates `RelationshipName.X.value` by convention, guarded by
`validate_relationship_type()` at runtime.

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

**Coverage (2026-07):** the linter's `RELATIONSHIP_NAMES` catalog mirrors the **complete** `RelationshipName` enum (all 170 values), pinned by `TestRelationshipNamesDrift` in `test_lint_skuel.py` — add a member to the enum and the drift test tells you to mirror it. (It previously drifted to a ~30-value hand-picked subset with four stale names, silently under-enforcing the rule.)

**Suppression:** boundary-shaped literals — e.g. mapping an *external* system's status/type string that merely collides with a relationship name (`"IN_PROGRESS"` in `calendar_adapters.py` is an EventStatus literal, not the relationship) — are legitimate; annotate with `# skuel-lint: disable=SKUEL013 -- <reason>`.

**Infrastructure defense-in-depth:** Even when callers use `RelationshipName` enum (safe), the infrastructure layer validates all interpolated identifiers before Cypher interpolation. Shared guards `validate_label()` and `validate_identifier()` in `_helpers.py` are used by all 5 query builder modules (`crud_queries.py`, `domain_queries.py`, `relationship_queries.py`, `semantic_queries.py`, `intelligence_queries.py`). Backend mixins additionally use `validate_relationship_type()` in `_build_direction_pattern()`, `traverse()`, `find_path()`. See `/docs/patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md`.

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

**Detection (AST, 2026-07):** flags COMPARISON shapes only — `== / !=` against an
entity-type string (either side, case-insensitive), `"task" in x` membership, and
`x in ("task", "goal")` literal containers (including multi-line ones the old
single-line regex missed). A Compare that references `EntityType` / `NonKuDomain` /
`Domain` anywhere in it (e.g. `EntityType.TASK.value == raw`) is exempt — `Domain`
is included because its values overlap the catalog ("learning", "finance", …), so a
comparison routed through it is enum-safe, just a different taxonomy. Plain string
literals outside comparisons (dict keys, log messages) are deliberately not flagged.

**Scope:** any `/services/` path **plus the inbound/presentation layers** —
`adapters/inbound/` and `ui/` (widened 2026-07, same layers as SKUEL013).
Test files are skipped.

**Catalog (2026-07):** `ENTITY_TYPE_ENUM_VALUES` mirrors the **complete**
`EntityType` + `NonKuDomain` value sets (29 values), pinned by
`TestEntityTypeCatalogDrift` in `test_lint_skuel.py` — it previously drifted to 22
values (all six `*_template` types, `user_entry`, and `group`/`calendar`/`learning`
were missing). `LEGACY_ENTITY_TYPE_ALIASES` additionally catches comparisons against
stale identifiers from removed/renamed types (`lesson`, `submission`, `je_input`, …);
it is hand-curated, and a drift test keeps it disjoint from the live enum values.

**Suppression:** boundary-shaped comparisons against a *local* taxonomy whose values
merely collide with entity-type names are legitimate — e.g. a progress-state form
protocol (`state == "learning"`), UI tab ids (`tab in (..., "ku")`), a source-kind
union (`kind == "submission"` meaning ku|submission|web), table column-header labels,
or an active-page nav id (`page == "calendar"`). Annotate with
`# skuel-lint: disable=SKUEL014 -- <reason>`.

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

**Detection (AST, 2026-07):** flags every `ast.ExceptHandler` whose type resolves to
`Exception` — bare, inside a tuple (`except (ValueError, Exception)`), or
formatter-wrapped across lines (`except (\n    Exception\n) as e:` — invisible to the
old single-line regex). Bare `except:` is ruff E722's territory. File-level
`disable-file=SKUEL017` is honored (previously documented but dead).

**Suppression markers** (anywhere in the except-clause header, or the line above):
- `# intentional-broad: <reason>` — catches that must remain broad (event handlers, monadic boundaries, metrics wrappers)
- `# safety-net: <reason>` — broad catches at boundaries where exceptions are unpredictable (API boundaries, JSON parsing, cleanup, UI rendering)
- `# skuel-lint: disable=SKUEL017 -- <reason>` — unified suppression format (also supported; honored on any header line, see "Suppression placement")

**Status:** ✅ Zero violations (March 2026). Persistence layer uses `NEO4J_EXCEPTIONS`; API/UI boundaries use `# safety-net:` annotations.

**Rationale:**
- Bare `except Exception` masks bugs and makes debugging harder
- Specific types enable correct error categorization (DATABASE vs SYSTEM vs INTEGRATION)
- Suppression markers document why a broad catch is intentional

**Exceptions:**
- Test files (`tests/**/*.py`)
- Scripts (`scripts/**/*.py`)
- `result_simplified.py` (monadic boundaries annotated separately)

## Rule: SKUEL019 - Credential Reads Must Use get_credential()

**Pattern:** Credential-shaped env reads must route through `get_credential()` from `core.config.credential_store`. The funnel dispatches to the active backend (`SKUEL_CREDENTIAL_BACKEND=keyring` → OS keychain, unset → Fernet-encrypted JSON) and falls back to env when neither has the value. Raw `os.getenv` reads silently skip the keychain under Stage 3.

```python
# ❌ VIOLATION (ERROR) — catalog credential read via env
import os
api_key = os.environ.get("OPENAI_API_KEY")
hf_token = os.getenv("HF_API_TOKEN")
neo4j_pw = os.environ["NEO4J_PASSWORD"]

# ❌ VIOLATION (WARNING) — credential-shaped name not yet in catalog
custom_secret = os.getenv("THIRDPARTY_API_KEY")   # *_API_KEY suffix
vendor_pat = os.getenv("VENDOR_PAT_PROD")         # *_PAT_* suffix

# ✅ CORRECT — route through the credential funnel
from core.config.credential_store import get_credential
api_key = get_credential("OPENAI_API_KEY", fallback_to_env=True)
if not api_key:
    raise RuntimeError("OPENAI_API_KEY missing — set via `uv run python -m core.config`")
```

**Severity logic:**
- **ERROR** — name is in the credential catalog mirrored from `core/config/credential_setup.py::CredentialSetup.CREDENTIALS`. These are known credentials and must use the funnel.
- **WARNING** — name matches the credential-shape regex (`_PASSWORD`, `_TOKEN`, `_API_KEY`, `_SECRET`, `_AUTH`, `_PAT_*`) but isn't catalogued yet. Likely a new credential — add it to `CredentialSetup.CREDENTIALS` (and the linter will pick it up automatically via the drift test).

**Catalog drift test:** `tests/unit/scripts/test_lint_skuel.py::TestCredentialCatalogDrift::test_linter_catalog_matches_credential_setup` pins `SkuelLinter.CREDENTIAL_CATALOG` against `CredentialSetup.CREDENTIALS`. Add a new credential to one place, the test tells you to mirror it in the other.

**Exempt files** (raw env reads ARE the implementation):
- `core/config/credential_store.py` — defines `get_credential()`
- `core/config/credential_setup.py` — reads `SKUEL_MASTER_KEY` to unlock the Fernet store
- `scripts/migrate_secrets_to_homedir.py` — Stage 2 migration source
- `scripts/migrate_secrets_to_keychain.py` — Stage 3 migration source
- Test files (`tests/**/*.py`) — fixtures often poke env directly

**False-positive guards** built into the regex:
- `SKUEL_MASTER_KEY` doesn't match — ends in `_KEY`, not any credential suffix
- `SKUEL_CREDENTIAL_BACKEND` doesn't match — backend selector, not a credential
- `*_PATH`, `*_DIR`, `*_FILE`, `*_BACKEND`, `*_USERNAME` all don't match

**Suppression:**
- `# skuel-lint: disable=SKUEL019 -- <reason>` (line)
- `# skuel-lint: disable-file=SKUEL019 -- <reason>` (file)

**See:** `docs/roadmap/secrets-out-of-worktree.md` — full credential storage architecture and the `fed4287f` fail-fast wiring that makes this rule load-bearing.

## Rule: SKUEL021 - No Raw Cypher Above the Boundary

**Pattern:** ADR-044 puts the hexagonal boundary at `UniversalNeo4jBackend` / `adapters/persistence/neo4j/` — all Cypher lives below it. Code above the boundary — all of `core/` **plus the inbound/presentation layers (`adapters/inbound/`, `ui/`)** — orchestrates and calls backend methods; it does not author Cypher. (SKUEL001 bans only APOC; SKUEL021 covers raw Cypher generally — both share one gate, and both skip APOC/Cypher named in docstrings and comments. SKUEL001 matches the whole `apoc.` namespace rather than a curated procedure list: `CALL apoc.` is not a `CYPHER_MARKER`, so without it a route could author `RETURN apoc.convert.fromJsonMap($json)` and trip neither rule. It matches **invocation, not mention** — three forms: `CALL apoc.x.y`, `apoc.x.y(`, or a string whose *entire* value is a dotted apoc path (a name assembled into a query elsewhere, `proc = "apoc.path.subgraphAll"` + `f"CALL {proc}(n)"`). Prose that merely names a procedure, e.g. `logger.warning("apoc.convert.fromJsonMap is unavailable")`, matches none of the three and so does not trip a CRITICAL unsuppressable rule. The `CALL` branch is case-sensitive and word-boundary anchored — each condition kills a different English phrasing that otherwise reads as an invocation: `"Please call apoc.convert.fromJsonMap"` needs the uppercase requirement, `"Recall apoc.meta.stats"` needs the `\b`. Nothing real is lost, since Neo4j procedure names are themselves case-sensitive lowercase (`APOC.meta.data` does not resolve on the server). Same paren/sigil discipline as `CYPHER_MARKERS`. Genuinely out of reach: a split that puts no apoc text in any single literal — `"CALL " + proc` where `proc` arrives from elsewhere — which no string-matching rule can see.)

```python
# ❌ VIOLATION (ERROR) — Cypher authored in a core/ module and used
query = "MATCH (n:Task) WHERE n.uid = $uid RETURN n"
rows = await self.executor.execute_query(query, {"uid": uid})

# ❌ VIOLATION — a marker interpolated into an f-string is still authored Cypher
q = f"MATCH (n) WHERE n.id = {uid} RETURN n"

# ✅ CORRECT — call a backend method; the Cypher lives below the boundary
rows = await self.backend.get_tasks(user_uid)

# ✅ NOT FLAGGED — Cypher inside a docstring / USAGE EXAMPLES block is documentation
def fetch() -> None:
    """Fetch tasks.

    Example:
        MATCH (n:Task) RETURN n
    """
```

**AST-based, docstring-aware:** Cypher only matters when it is *used* (assigned, passed, returned, interpolated). The checker walks string `Constant` nodes (including f-string literal parts). String literals that are **inert bare-expression statements** — module/class/function docstrings AND mid-body `USAGE EXAMPLES` blocks — are skipped by node identity. This is why the rule can cover `core/utils`, whose docstrings legitimately quote Cypher (processor_functions.py, neo4j_mapper.py, …), without false-positiving. One violation per source line (collapses the several `Constant` parts an f-string splits into).

**Two anchors decide whether a literal is Cypher:**

| Anchor | Owner | Matches | Examples |
|--------|-------|---------|----------|
| **Substring, anywhere** | `SkuelLinter.CYPHER_MARKERS` (this rule) | paren/sigil-anchored clauses that never follow the keyword in prose | `MATCH (`, `MERGE (`, `OPTIONAL MATCH (`, `OPTIONAL MATCH path`, `CREATE (`, `UNWIND $`, `CALL db.` |
| **Statement head** | `cypher_vocabulary.leading_cypher_clause` (shared with SKUEL030 + CYP011) | an UPPERCASE clause keyword at the head of the literal, followed by whitespace and an operand | every entry of `CYPHER_LEADING_CLAUSES` — `RETURN`, `SHOW`, `PROFILE`, `EXPLAIN`, `DELETE`, `DETACH DELETE`, `SET`, `REMOVE`, `LOAD CSV`, `CALL`, `MATCH`, `MERGE`, `CREATE`, `INSERT`, `NODETACH`, `UNWIND`, `WITH`, `FOREACH`, `DROP`, `USE`, `OPTIONAL MATCH` |

**The head anchor is not this rule's own.** SKUEL021 grew one in #829 and SKUEL030/CYP011 grew one in #831; the two copies had drifted in five behaviours before either was a month old, every drift leaving #829's the narrower gate — it required the operand on the clause's own line, skipped only `//` comment lines (so a `/* hint */` hid the statement in either position), did not strip a `CYPHER <options>` preamble, and lacked `INSERT` and `NODETACH`. Both now read `cypher_vocabulary`, which is the module both linters already imported (the reverse direction is circular). There is no SKUEL021-specific clause list to tune: a clause that should open a statement is added there, once, and `::test_every_shared_clause_is_live_in_this_rule` — parametrized over the tuple itself, so it cannot go stale — proves the whole list stays live here.

**The two anchors disagree on comment masking, deliberately.** The head anchor masks comments; the substring anchor does not, so a commented-out `MATCH (` in a *used* literal still reports. Masking both is defensible (a comment cannot execute — the reasoning that exempts docstrings), but the anchors fail in opposite directions: masking only ever moves the head anchor's single match position past a planner hint, while the substring anchor matches anywhere in every string across all three trees, so masking it could only ever *remove* detections. A silent miss is what this rule exists to prevent; an over-report on a commented-out query is one suppression comment. Measured when the anchors were consolidated: masking the substring anchor would have moved **zero** verdicts in any of the three trees (40 non-inert constants there contain `//` or `/*`). `::TestSKUEL021AnchorMaskingAsymmetry` pins the asymmetry so it stays a decision rather than an accident.

The head anchor exists because the substring anchor has a structural ceiling: a marker matched anywhere must be paren/sigil-shaped to stay out of prose, which left whole statement families with nothing to match on. **A real leak lived in that blind spot** — `core/services/system_service_init.py` ran `await session.run("RETURN 1 as ping")` for a long time, fully in scope, with no suppression comment, and the rule never fired. Position supplies the signal a substring cannot: `"DETACH DELETE n"` is Cypher, `"cascade DETACH DELETE (default False)"` is prose (the clause is named mid-sentence in ~30 places across `core/`).

**Composite strings are judged as a whole, never as their torn parts.** `ast.walk` yields a `JoinedStr` (or a `+` chain) *and* its `Constant` children, and the children are fragments. Both `f"RETURN {value}"` and `"RETURN " + projection` tear into a leading piece with no operand left to anchor on, while `f"cascade {mode} DETACH DELETE (default False)"` tears into a trailing piece that *falsely* leads with a clause keyword. The head anchor therefore runs against the reconstructed whole — `render_fstring()` output for f-strings, an `Add`-spine flatten for concatenation — with interpolations replaced by a sentinel. Concatenation is flattened along the `+` spine only, never into an operand's own expression, so a string literal buried in a call argument is not spliced into the query text. Nested `+` links resolve to their outermost root, so a chain reports once.

The anywhere-markers keep scanning per piece, preserving their per-line granularity. To avoid double-reporting, the composite-level pass skips only when **a piece actually matched** — not when the rendered text merely matched. Those are genuinely different: `"MATCH " + "(n) RETURN n"` renders to a marker that *no single piece contains*, because two literal operands concatenate with nothing between them. (An f-string cannot hit this — the parser never leaves two adjacent `Constant` parts, so its pieces really are sentinel-separated. Concatenation broke that invariant when it was added.)

All of this lives in **one traversal**, `SkuelLinter.iter_authored_cypher`, which `tests/unit/test_core_utils_boundary.py` also calls. Sharing only the predicate was not enough — the guard and the rule disagreed on f-strings until they shared the walk too.

Three conditions keep the head anchor quiet on prose, each load-bearing: head position, UPPERCASE, and a following whitespace + operand (which rules out the bare HTTP verb `"DELETE"`, header names like `"SET-COOKIE"`, and `RETURNS`/`CREATED`/`WITHOUT`-style words). **Known, deliberate limit:** lowercase Cypher (`"return 1 as ping"`) is not detected — matching case-insensitively would light up ordinary prose, and every query in this tree is uppercase. Extending the rule's scope to `adapters/inbound/` + `ui/` put a hard number on that: measured across those two trees, a case-insensitive head anchor yields **~80 hits, not one of them Cypher** — button labels and help text that merely open with a clause word (`"Create Invoice"`, `"Delete"`, `"Show All"`, `"Set your goals"`, `"Remove this relationship?"`, `methods=["DELETE"]`) — while all three conditions together yield **zero**. The presentation layer is where relaxing any of the three fails loudest; `TestSKUEL021::test_english_ui_strings_are_not_cypher` pins that corpus. Admin/security DDL (`GRANT`, `REVOKE`, `ALTER`) is deliberately absent: `core/` has no admin-DDL surface and those words carry real prose risk in a codebase with roles and permissions.

**Scope:** all of `core/`, any `/services/` path, and the inbound/presentation layers (`adapters/inbound/`, `ui/` — the `SkuelLinter.INBOUND_LAYER_PREFIXES` tuple, single-sourced so the test harness's scope mirror cannot drift). It grew from `core/services|ingestion|infrastructure` to all of `core/` once the last Cypher-authoring leaks were relocated below the boundary — `core/utils/connection_fetcher.py` (PR #75) and `core/models/search_request.py::to_graph_patterns` (PR #78) — and then to the inbound layers, which are above the boundary for the same reason `core/` is: a route composes services and a renderer renders FTs; neither talks to the driver. That second extension mirrors SKUEL027, the `ui/` sibling SKUEL022 grew for the import-direction rule. `adapters/persistence/neo4j/` is below the boundary and is not checked; neither is `scripts/`, which authors Cypher legitimately (audits, migrations, benchmarks). Test files are skipped.

**Not every above-boundary probe is a port candidate.** `services_bootstrap/_system_health.py` runs a raw `RETURN 1 as ping` on a session it opens itself, and that is correct: the composition root owns the driver it just built, and a liveness ping carries no domain meaning to name a port after. The composition root is deliberately outside this rule's scope. Routing that ping through a domain backend would invent a port for something that is not a domain operation.

**How to fix a violation:** relocate the query into an adapter backend in `adapters/persistence/neo4j/` behind a `core/ports` protocol, and inject it at the composition root. For an "inverted boundary" case (a `core/` model/util that builds a Cypher string handed to a passthrough executor), pass the domain *intent* down and author the Cypher below the boundary — see `ConnectionFetchBackend` / `ConnectionFetchOperations` (PR #75) and `build_relationship_filter_fragments` (PR #78) for the patterns.

**Guard test:** `tests/unit/scripts/test_lint_skuel.py::TestSKUEL021` covers used Cypher in `core/services`/`core/utils`/`core/models`, in `adapters/inbound/` and `ui/`, f-strings, passed/returned strings, docstring + `USAGE EXAMPLES` + comment skips, the English-UI-string corpus, out-of-scope silence for `scripts/` and `adapters/persistence/`, multi-line collapse, and suppression. `::TestSKUEL021LeadingClauseAnchor` covers the head anchor: each newly-visible statement family, each prose guard, each of the five drifts closed by adopting the shared matcher, the derived whole-list check, and a regression test that lints the real `core/ports/` files whose docstrings name `DETACH DELETE` (a synthetic stand-in would only prove the stand-in is clean). `::TestSKUEL021AnchorMaskingAsymmetry` pins the masking asymmetry between the two anchors. `tests/unit/test_core_utils_boundary.py` additionally bans execution primitives (neo4j driver imports, `.execute_query(` calls) that SKUEL021 does not cover; its Cypher-string sub-check now *derives* from `SkuelLinter` rather than hand-copying the markers, after the copy silently drifted a marker behind. The real tree is held clean by `./dev quality` in CI.

**Suppression:**
- `# skuel-lint: disable=SKUEL021 -- <reason>` (line)
- `# skuel-lint: disable-file=SKUEL021 -- <reason>` (file)

## Rule: SKUEL022 - core/ Must Not Import adapters/

**Pattern:** The hexagonal dependency direction is **core → adapter**, never the reverse (ADR-044). A module under `core/` that imports from `adapters/` inverts it — `core` defines ports (`core/ports`) and receives concrete adapters by injection at the composition root, it does not reach down into them. This is the import-direction sibling of SKUEL021 (which bans raw Cypher above the boundary): together — with SKUEL001 (APOC) — they keep `core/` independent of the Neo4j adapter. SKUEL022 stays `core/`-only: `ui/` has its own sibling (SKUEL027), and `adapters/inbound/` importing `adapters/` is the composition a route exists to do. SKUEL001/021 do extend past `core/` to the inbound layers, because *authoring Cypher* is wrong there in a way *importing an adapter* is not.

```python
# ❌ VIOLATION (ERROR) — module-level adapter import in a core/ file
from adapters.persistence.neo4j.ps_engagement_backend import PsEngagementBackend

# ❌ VIOLATION (ERROR) — hidden inside a function (same runtime dependency, deferred)
def __init__(self, executor) -> None:
    from adapters.persistence.neo4j.ps_engagement_backend import PsEngagementBackend
    self._backend = PsEngagementBackend(executor)

# ✅ CORRECT — depend on a core/ports protocol; inject the adapter at composition
def __init__(self, backend: PsEngagementOperations) -> None:
    self._backend = backend

# ✅ CORRECT — type-only import under TYPE_CHECKING (never executes, exempt)
if TYPE_CHECKING:
    from adapters.persistence.neo4j.ps_engagement_backend import PsEngagementBackend
```

**AST-based, runtime scope:** flags `import adapters...` / `from adapters... import ...` at module scope **and inside functions**. A function-local import is the same core→adapter runtime dependency, just deferred past module load — it's the dodge a module-level-only check (e.g. a line-anchored grep) would miss.

**TYPE_CHECKING is exempt:** an import under `if TYPE_CHECKING:` (or `if typing.TYPE_CHECKING:`) never executes, so it *cannot* create a runtime dependency — you can't smuggle a real runtime import through it (it would `NameError`). Typing `self.backend` against a concrete adapter class under `TYPE_CHECKING` is a separate, lower-priority purity concern (type against `core/ports` instead), not a layering violation. Relative imports (`from . import x`) are not adapter imports and are never flagged.

**Scope:** all of `core/` (not just `core/services/`). `adapters/`, `services_bootstrap/` (the composition root — it SHOULD import adapters), and `routes/` are not checked; `ui/` gets the same enforcement from SKUEL027. Test files are skipped.

**How to fix a violation:** move the adapter construction to the composition root (`services_bootstrap/`) or a factory below the boundary, and inject the result behind a `core/ports` protocol. See the PsEngagement (port injection), UnifiedIngestion (`adapters/persistence/neo4j/ingestion_service_factory.py`), and finance-renderer (`InvoiceRenderer` port) inversions for the patterns.

**Guard test:** `tests/unit/scripts/test_lint_skuel.py::TestSKUEL022` covers module-level, plain `import`, function-local, both `TYPE_CHECKING` forms, relative imports, adapter/composition-root/test-file exemptions, and suppression. The real `core/` tree is held clean by `./dev quality` (which runs `lint_skuel.py`) in CI.

**Suppression:**
- `# skuel-lint: disable=SKUEL022 -- <reason>` (line)
- `# skuel-lint: disable-file=SKUEL022 -- <reason>` (file)

## Rule: SKUEL027 - ui/ Must Not Import adapters/

**Pattern:** `ui/` is pure presentation — it renders what routes hand it. The dependency arrows point inward: `adapters/inbound` (routes) imports `ui/` components, never the reverse at runtime. This is SKUEL022's sibling for the `ui/` layer; both share the same AST scan (`_collect_runtime_adapter_imports`). Before this rule, no lint watched `ui/`, which is how `ui/calendar/converters.py` grew an adapters import (fixed in #653) and CSRF render helpers were consumed from `adapters/inbound/csrf.py` (split inward in #654). The rule replaced the interim unit-test guard `tests/unit/test_ui_layer_boundary.py` (one enforcement point — lint fires in `./dev quality`, not only under pytest; inline suppressions beat a remote sanction list).

```python
# ❌ VIOLATION (ERROR) — module-level adapter import in a ui/ file
from adapters.inbound.auth import get_session_user

# ❌ VIOLATION (ERROR) — hidden inside a function (where the last real violations hid,
# BasePage/navbar session readers, cleared by the middleware-set auth context in #655)
def Navbar(request):
    from adapters.inbound.auth import get_session_user
    user = get_session_user(request)

# ✅ CORRECT — request-derived state flows inward via a middleware-set ContextVar
from core.utils.auth_context import current_auth_state

# ✅ CORRECT — type-only import under TYPE_CHECKING (never executes, exempt;
# the Request protocol lives at the FastHTML boundary by design)
if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import Request
```

**AST-based, runtime scope:** same mechanics as SKUEL022 — flags `import adapters...` / `from adapters... import ...` at module scope **and inside functions**; `TYPE_CHECKING` bodies (both `TYPE_CHECKING` and `typing.TYPE_CHECKING` forms) are exempt, the `else`/`elif` branch is not; adapter paths in docstrings/strings are prose, never flagged.

**Scope:** all of `ui/`. `core/` is SKUEL022's territory; `adapters/`, `services_bootstrap/`, and test files are not checked.

**How to fix a violation:** move the shared code inward (`core/utils/` or `ui/`) or pass the value in from the route. For request-derived state, use the middleware-set ContextVar shape — `core/utils/auth_context.py` (auth flags) and `core/utils/csrf_token_context.py` (CSRF token) are the reference implementations: the middleware (adapters → core) writes, layout components (ui → core) read.

**Guard test:** `tests/unit/scripts/test_lint_skuel.py::TestSKUEL027` covers module-level, plain `import`, function-local, both `TYPE_CHECKING` forms, else-branch/try-except runtime branches, docstring prose, inward imports, layer-scope exemptions (core/, routes, test files), and suppression. The real `ui/` tree is held clean by `./dev quality` in CI.

**Suppression:**
- `# skuel-lint: disable=SKUEL027 -- <reason>` (line)
- `# skuel-lint: disable-file=SKUEL027 -- <reason>` (file)

## Rule: SKUEL024 - No cls= / **kwargs Collision in FT Helpers

**Pattern:** A UI/FT helper that hardcodes a `cls=` keyword **and** splats `**kwargs` into the same call, without declaring an explicit `cls` parameter, is a latent crash. When any caller passes `cls=`, that value lands in `**kwargs` and collides with the hardcoded keyword: `TypeError: <fn>() got multiple values for keyword argument 'cls'`.

```python
# BAD — caller cls= collides with the hardcoded one
def SmallText(text: str, **kwargs: Any) -> Span:
    return Span(text, cls="text-sm", **kwargs)   # SmallText("x", cls="y") -> TypeError

# GOOD — explicit cls param, merged into the base classes
def SmallText(text: str, cls: str = "", **kwargs: Any) -> Span:
    return Span(text, cls=f"text-sm {cls}".strip(), **kwargs)
```

**Why it matters:** this 500'd the `/insights` page in production via `SmallText("Recommended Actions:", cls="font-semibold mb-1")` (PR #154); an AST sweep then found six sibling helpers (PRs #156/#157). It is invisible to mypy and ruff — only a caller that actually passes `cls=` triggers it, so a helper can ship the landmine and sit dormant until the first styling override.

**Detection (AST), scope-resolution model:** the rule walks the tree carrying a stack of enclosing function scopes. For each call passing **both** a `cls=` keyword and a `**Name` splat, it resolves `Name` to the **nearest enclosing scope that binds it** (where "binds" means a parameter **or any local assignment**: `=`, `:=`, augmented/annotated, `for`/`with`/`except` targets, imports, nested `def`/`class` names — matching Python's symbol-table scoping). It flags the call iff `Name` is that resolved scope's `**kwargs` parameter and the scope has **no keyword-passable `cls` parameter** (positional-or-keyword or keyword-only; a *positional-only* `cls` does **not** absorb a keyword `cls=`). Resolution is **structural** (a compile-time scope-binding fact), so it handles every nesting case soundly: a nested `def`/`lambda` that **closes over** the outer `**kwargs` is flagged against the outer scope; a nested factory whose own scope **owns** the name as a plain local (`def make(): kwargs = {...}; Div(cls=.., **kwargs)`, no `**kwargs` param) resolves to itself and is cleared by the param mismatch.

A local **reassignment of an owned `**kwargs`** is **not** treated as clearing the collision — proving it sanitizes every path needs control-flow domination (a conditional or post-splat `kwargs = {}` does not), the same reason there is no `kwargs.pop("cls")` exemption.

**Documented boundary — name resolution, not value tracking.** The rule resolves a splat *name* to its binding scope but does **not** track a local variable's *value*. So value-flow / alias / taint cases are deliberately **not** chased: a simple alias (`attrs = kwargs; Div(cls=.., **attrs)`) and copies/transforms/merges (`dict(kwargs)`, `{**kwargs}`, `kwargs | extra`). Sound detection there requires control-flow analysis (flow-insensitive alias tracking gives both false negatives *and* false positives — e.g. an earlier `Div(cls=.., **attrs)` before a later `attrs = kwargs`), these forms do not occur in real FT helpers, and the explicit `cls: str = ""` parameter is the contract that removes the entire class regardless. One violation per binding scope. There is **no** `kwargs.pop("cls")` exemption: proving a pop actually defuses the splat needs control-flow domination — a conditional pop (`if flag: kwargs.pop("cls")`), a pop *after* the splat, or a `kwargs.get("cls")` (which doesn't remove the key) all leave the collision live — and the explicit `cls: str = ""` parameter is the contract anyway. Pop-based helpers are therefore flagged too; adopt the explicit parameter, or suppress with a reason if a genuinely-sound pop form is needed. (The simpler, sound rule beats an exemption heuristic with an unbounded tail of unsound cases.)

**Scope:** all non-test files (the shape is language-general — any `f(cls=x, **kwargs)` without a `cls` param crashes when a caller passes `cls`). The contract is guarded at runtime by `tests/unit/ui/test_cls_merge_contract.py`, which renders every `cls`-merging helper with `cls=` set.

**Guard test:** `tests/unit/scripts/test_lint_skuel.py::TestSKUEL024` covers literal and variable `cls=`, alternate `**` names, the explicit-param / keyword-only-param / positional-or-keyword clean cases, positional-only `cls` flagged, the `@classmethod` receiver flagged, closures and nested-`def`/`lambda` resolution, nested-local-rebinding clean, the no-pop-exemption (pop / conditional-pop flagged), the no-reassignment-exemption (conditional and same-scope reassign flagged), the documented value-flow boundary (alias and `dict(kwargs)` copy not chased), spaced `cls = "x"`, no-kwargs / no-cls clean cases, suppression, and the test-file skip.

**Suppression:**
- `# skuel-lint: disable=SKUEL024 -- <reason>` (line)
- `# skuel-lint: disable-file=SKUEL024 -- <reason>` (file)

## Rule: SKUEL025 - No Deleted Activity *UpdatePayload (ADR-066)

**Pattern:** ADR-066 (Phase 7a) replaced the six Activity Domain `*UpdatePayload` TypedDicts with frozen `*UpdateIntent` dataclasses and a CRUD base parameterized over the update type `U`. The deleted names — `TaskUpdatePayload`, `GoalUpdatePayload`, `HabitUpdatePayload`, `EventUpdatePayload`, `ChoiceUpdatePayload`, `PrincipleUpdatePayload` — must not return; referencing one rebuilds the abandoned dict write-path (One Path Forward).

```python
# BAD — resurrects the deleted TypedDict write-path
from core.ports.query_types import TaskUpdatePayload   # SKUEL025
updates: TaskUpdatePayload = {"status": "in_progress"}

# GOOD — the frozen intent is the one update path
from core.models.task import TaskUpdateIntent
await tasks_service.update_task(uid, TaskUpdateIntent(status="in_progress"))
```

**Why it matters:** the six TypedDicts were decorative — structurally just `dict`, so the type was advisory and never enforced at the write seam. ADR-066 made the contract real (frozen dataclass, `UNSET` vs `None`, single `to_changes()` materialization). The non-activity payloads (curriculum `Ku`/`Ps`/`Lp`, `Finance`, `Report`) are **intentionally not forbidden** — they remain valid, flowing as `RawChanges` through the same base `U`.

**Detection (AST), trivially sound:** a fixed forbidden set of exactly the six deleted names. The rule flags an import alias, a bare `Name`, or an `Attribute` whose identifier is in the set — all structural facts, no flow analysis. A string literal naming a deleted type (a test asserting its removal, this rule's own metadata) is never a `Name`/`Attribute` node, so it is never flagged. Deduped per `(line, name)`.

**Scope:** all non-test files.

**Suppression:**
- `# skuel-lint: disable=SKUEL025 -- <reason>` (line)
- `# skuel-lint: disable-file=SKUEL025 -- <reason>` (file)

## Rule: SKUEL028 - Propagate Errors with Result.fail(result)

**Severity:** ERROR

`Result.fail(result)` is THE propagation path across type boundaries (CLAUDE.md § Error
Handling) — it re-wraps the failed result's typed error intact. `.expect_error()` exists
to READ the error (logging, branching on category), not to feed it back into
`Result.fail()`. The direct form is a pointless unwrap/re-wrap; the sibling shape
`Errors.database(op, str(result.expect_error()))` is worse — it flattens a typed error
into a stringly Database/Integration error, losing the original category (the family
PR #674 cleaned out of `ingestion_tracker.py`; the rule's introduction cleaned the same
shape from `system_api.py`, `askesis_citation_service.py`, `neo4j_vector_search_service.py`,
and `lp_service.py`).

**Detection:** AST-based — flags any `Result.fail(...)` call whose argument expression
contains an `.expect_error()` call anywhere in its subtree (direct, conditional-expression,
and `str(...)`-wrapped forms). `.expect_error()` outside a `Result.fail(...)` argument is
the sanctioned read use and is never flagged.

```python
# ❌ Violations
return Result.fail(result.expect_error())
return Result.fail(
    r.expect_error() if r.is_error else Errors.not_found("Task", uid)
)
return Result.fail(Errors.database("op", str(result.expect_error())))

# ✅ Correct
if result.is_error:
    return Result.fail(result)                       # typed error propagates intact
logger.warning(f"failed: {result.expect_error()}")   # reading is what it's for
```

**Scope:** all non-test files.

**Suppression:**
- `# skuel-lint: disable=SKUEL028 -- <reason>` (line)
- `# skuel-lint: disable-file=SKUEL028 -- <reason>` (file)

## Rule: SKUEL029 - async def Without await

**Severity:** ERROR — runs in every default sweep.

CLAUDE.md's async/sync rule: async for I/O, sync for computation — "if you need `await`
inside the function, make it `async def`; otherwise use `def`." An `async def` whose body
never awaits (no `await` / `async for` / `async with` of its own — awaits inside *nested*
defs belong to the nested function) wraps a synchronous computation in a coroutine: every
caller pays the event-loop round-trip and the signature misreports I/O.

**History:** codified as an opt-in audit at a ~215-site baseline (2026-07-17), then
promoted to an enforced ERROR on 2026-07-18 after the reduction arc drove the count to 0
(PRs #679–#696) — the CYP003 staged path: codify, shrink the debt, promote. Genuinely
interface-required async (Protocol/ABC overrides, awaited callbacks such as
health-checkers and `system_calculator`, facade delegation, async context-manager
`__aenter__`, asyncio task machinery/lifecycle) keeps `async def` with an inline
suppression naming the contract.

**Exemptions:** trivial bodies (docstring-only, `pass`, `...`, bare `raise`) — protocol
methods and abstract stubs are declarations, not offenders — and async generators (an
own `yield`): their `async def` is load-bearing even without awaits, since sync-ifying
turns the async iterator into a sync generator and breaks every `async for` caller.

**Scope:** all non-test files.

## Rule: SKUEL030 - Persistence Cypher Vocabulary Must Be Registered

**Severity:** WARNING — runs on `adapters/persistence/**` only.

Every relationship type and node label written in persistence-layer Cypher must be a
registered member of `RelationshipName` / `NeoLabel`. Both enums document themselves as
the single source of truth for the graph vocabulary ("All valid Neo4j relationship type
names" / "All valid Neo4j node labels in SKUEL"); an edge or label the registry has never
heard of makes that claim false.

**Why it matters:** Neo4j validates neither labels nor relationship types. A typo'd
`(:KnowlegeDomain)` or `[:OWNS_ENTITY]` raises no error — the pattern simply matches zero
rows, silently, forever. Worse, an unregistered edge inside `WHERE NOT (x)<-[:REL]-(u)`
makes the filter *always true*, so the query returns unfiltered results. This rule is the
only check standing between a one-character typo and a feature that quietly returns
nothing (or everything) in production.

**This is a vocabulary rule, not an interpolation-style rule.** A plain `[:OWNS]` literal
is fine below the boundary — SKUEL013's `[:{RelationshipName.OWNS}]` form is *not*
required here, and no 300-site interpolation rewrite is implied. The rule reads the NAME,
never the syntax around it.

**Every position vocabulary can occupy is scanned:**

- **Pattern** — `(n:Label)`, `[r:TYPE]`, multi-label `(n:Entity:Ku)`, alternation
  `[:A|B]`, var-length `[:OWNS*1..3]`, and Neo4j 5 typed DDL
  (`CREATE FULLTEXT|VECTOR|RANGE|TEXT|POINT INDEX ... FOR (n:Label)`). Queries that
  OPEN with a procedure call (`CALL db.index.vector.queryNodes(...) YIELD node WHERE
  ...`) are recognised too — vector/fulltext search has no leading clause keyword.
- **Predicate** — `type(r) = 'X'`, `type(r) IN ['A','B']`, `WHERE n:Label`,
  `AND NOT n:Label`. A typo here makes the predicate unsatisfiable, which fails
  exactly as silently as a typo'd pattern; this is what caught `get_siblings`
  filtering on five edge types that do not exist. Parameterized forms
  (`type(r) = $rel_type`) carry no static name and are skipped.
- **Mutation** — `SET n:Label`, `REMOVE n:Label`, `SET n:A:B`, and the comma-separated
  form `SET a:Ku, b:PathStep` (each item judged independently, including the mixed
  `SET n.title = $t, n:Ku`). A label attached here is never written in pattern
  position, so the pattern regexes cannot see it — and a typo is strictly worse than a
  typo'd read, because Neo4j writes the label it is given and the graph ends up
  carrying a name nothing will ever match. `SET n.prop = $x` is a dot, not a colon,
  and is left alone; so is a map literal (`SET n = {a:Foo}`), which splits into items
  that are not a bare `var:Label`.

**Comments are masked before both the gate and the scan** (`mask_cypher_comments`,
shared with `cypher_linter`'s statement splitter — one implementation, not two).
Masking is length- and newline-preserving, so every offset and line number still
points at the right place, and it is string-aware, so `'bolt://host'` is not mistaken
for a comment. A comment cannot execute, so vocabulary written in one is not
load-bearing — the same reasoning that exempts docstrings. This matters more since the
head anchor: a statement whose only remaining content is a comment is now admitted, so
masking for admission but scanning the raw text would have turned every explanatory
`// was [:OLD_EDGE]` into a violation.

**The gate: two anchors, one predicate.** Nothing above runs unless
`looks_like_cypher()` first accepts the fragment — `scan_names()` returns `[]` outright
for a rejected one, and a rule that silently scans nothing reports clean. Two orthogonal
anchors decide:

1. A **paren/sigil-anchored marker anywhere** in the fragment (`MATCH (`, `MERGE (`,
   `CREATE ... INDEX|CONSTRAINT`, `MATCH x = (`, `UNWIND $`, `CALL db.`). Position
   carries no signal here, so each arm must earn its keep from shape alone.
2. An **UPPERCASE clause keyword at the HEAD** of the fragment, followed by whitespace
   and an operand. Position is the signal, so no paren is needed.

Anchor 1 alone has a ceiling, and its last three arms are the tell: each was bolted on
case-by-case after a form the paren anchor could not see turned up. Whole statement
families have no paren adjacent to their clause keyword —
`RETURN [(a)-[:TYPO_EDGE]->(b) | b] AS xs` carries a real relationship type, and
`MATCH path = shortestPath((a:Entity)-[:X]-(b))` misses the named-path arm because a
function call sits between the `=` and the pattern. Anchor 2 closes the class rather
than the next instance of it. Its three conditions are each load-bearing: head position
(`"cascade DETACH DELETE (default False)"` is prose), uppercase (drops the whole
lowercase-English surface), and whitespace+operand (rules out the bare HTTP verb
`DELETE`, `SET-COOKIE`, and `RETURNS`/`CREATED`/`WITHOUT`). The clause list is
deliberately *not* pruned to "clauses that can carry vocabulary" — that is a second
judgement call, and it gets `DROP CONSTRAINT ... FOR (n:Label)` wrong. One question, one
answer. SKUEL021 asks the same question of `core/` + `adapters/inbound/` + `ui/` and now
reads the same answer: `CYPHER_LEADING_CLAUSES` and its matcher live here, exposed as
`leading_cypher_clause()`, and all three rules consult one implementation. They did each
keep a copy for one release, and the copies drifted in five behaviours before either was
a month old — see SKUEL021's section for the list.

**The scanner reports what it could not read** — `scripts/cypher_scan_diagnostics.py`.

Every failure mode of `scan_names` used to be silent, which is the fault these rules
exist to catch reproduced one layer down: an item that does not full-match is dropped, a
pattern body whose parts all fail the name regex yields nothing, a rejected fragment
returns `[]`. The cost was measured — PR #831 ran 19 review rounds without converging,
because the only way to find a gap was for a reviewer to *imagine* an input, and roughly
16 of its ~27 findings were valid Cypher forms with zero instances in this tree.

`recording_scan_diagnostics()` makes each drop visible; the script runs both rules' real
code paths under it and prints the spans. It is **opt-in, not wired into `./dev quality`,
and never exits nonzero on findings** — a drop is not a violation. Most are correct: a
property-only `SET n.title = $t` has no label to miss, a `$(labelExpr)` operand has no
static name to check. Promoting a category to a violation class is a separate decision.

First full run over `adapters/persistence/**/*.py` + every `.cypher` file:

| Issue | Count | Reading |
|---|---|---|
| `unparsed-mutation-item` | **0** | No label-shaped `SET`/`REMOVE` item in the tree defeats the item regex. |
| `unreadable-pattern-body` | 16 | All template placeholders (`__DAG__`, `zpd_proximal_edges`) substituted from `RelationshipName` constants at runtime. Correct drops. |
| `rejected-by-gate` | 3 | One prose false positive of the diagnostic's own name filter; **two real** — bare pattern fragments assigned to a variable and composed into a query later (`activity_backends.py:94`). Both name `Entity`, which is registered, so nothing fires today; a typo'd one would be invisible to both anchors. A known, now-measured gap. |
| `mutation-clause-no-item-matched` | 265 | Property assignments. The unfiltered denominator, kept so the shape filter above cannot hide a class. |

**Python edge lists — the rule's second scanner (since tranche 5).** An alternation is
as often assembled from a Python literal as written inline:
`{"practice": ["PRACTICES", "REINFORCES", "APPLIES_KNOWLEDGE"]}`, or a bare
`"rel_types": "PARENT_OF|CHILD_OF"` in a query spec. Those names never sit inside a
Cypher fragment, so the Cypher scanner could not see them — while the alternation they
build silently matches only its live arms. Four such sites surfaced across four tranches,
the last found by this scanner on its first run. Both shapes are covered: a
list/tuple/set literal of bare edge names, and a bare `A|B` alternation string. Same
scope, baseline, suppression and severity as the Cypher half — one rule, two positions.

*Corroboration keeps false positives at zero.* A group of UPPER_SNAKE strings counts as
graph vocabulary only when at least one member is a registered `RelationshipName`; that
sibling is the evidence. Without it, every list of UPPER_SNAKE constants in the
persistence layer (status codes, header names) would be flagged. The deliberate trade:
**a group in which every name is wrong stays invisible.** That is the safe direction to
fail, and all four known sites carried a registered sibling.

**Scope and exemptions:**

- `adapters/persistence/**` `.py` string literals. The `.cypher` half is CYP011 in
  `cypher_linter.py` — splitting by file type avoids double-reporting, and only the
  Python side has the AST context needed to tell an executable query from a docstring.
- Docstrings and other inert bare-string statements are skipped (the SKUEL001/SKUEL021
  model), so illustrative Cypher in prose never trips it.
- f-strings are flattened *whole* before scanning; names touching an interpolation
  (`[:HAS_{domain.upper()}]`) are unresolvable statically and skipped. Scanning an
  f-string's Constant children individually would tear `[:HAS_{domain}]` into `[:HAS_`
  and report a bogus `HAS_` — hence `fstring_part_ids`.
- `scripts/migrations/*` is excluded by design: a rename migration's job is to reference
  the vocabulary it is renaming away.

**The registry is read, not mirrored.** `scripts/cypher_vocabulary.py` recovers the enum
members by AST-parsing the two declaration sites — no import, so the linters still carry
no runtime dependency on `core/`. This replaced SKUEL013's 170-entry hand-mirror, which
had already drifted once to a ~30-value subset with four stale names, silently
under-enforcing for months. A parser cannot drift; a mirror always eventually does. An
unreadable or empty registry raises `VocabularyError` rather than returning an empty set —
failing closed is the only safe default for a rule whose value is catching what nothing
else catches.

**The baseline.** The 2026-07-19 introduction sweep found 65 unregistered names across 194
sites. 32 were live vocabulary with real writers and were registered. The remaining 33
went into `SkuelLinter.SKUEL030_BASELINE` — every one a **known finding, not an accepted
name**: reads against vocabulary nothing writes. They are baselined rather than registered
because registering them would bless the bug; the fix is to repoint or delete the reader,
which changes query semantics and belongs in its own PR. Full triage:
[CYPHER_VOCABULARY_FINDINGS.md](CYPHER_VOCABULARY_FINDINGS.md).

Five tranches worked that list down from 45 `(file, name)` pairs to **2**, both belonging
to the semantic-relationship-layer roadmap rather than to this rule. Note what the count
does *not* measure: SKUEL030 checks whether a name is **registered**, never whether
anything **writes** it, so registered-but-dead vocabulary passes cleanly and never appears
in the baseline at all. The findings document is explicit that it is a lower bound.

Baseline entries are **`(file, name)` pairs, not bare names.** Scoping to the file that
already carries the finding keeps the invariant honest: a new query introducing `:Report`
or `[:PRACTICES]` *anywhere else* still fails. A name-keyed set would have globally waved
the name through and quietly re-opened the hole the rule exists to close. File-level rather
than line-level is deliberate — line numbers churn on every edit above them, turning the
baseline into merge-conflict bait; the case that trades away is a second bad name in an
already-flagged file, and that file is already on the fix list.

The baseline is a **shrinking list, never a growing one**. Two tests keep it from rotting
into a mask: one fails if a baselined name later gets registered, the other if a baselined
path no longer exists.

**Suppress:** `# skuel-lint: disable=SKUEL030 -- <reason>` (line) /
`disable-file=SKUEL030` (file) for a label or edge genuinely owned by an external or
infrastructural schema the domain registry should not absorb. The `.cypher` equivalents
are `// noqa: CYP011 - <reason>` and, for a file that is dead end to end,
`// noqa-file: CYP011 - <reason>`.

## Authoring AST Rules

Two bug classes recur when writing AST-based rules (SKUEL020, SKUEL021, SKUEL022). Both are
load-bearing and both are easy to reintroduce — guard new AST rules against them.

1. **Iterate the field, never walk the compound node.** When collecting the
   lines/nodes *inside* a compound statement (`If`, `Try`, `For`, `While`, `With`,
   `FunctionDef`), iterate the specific field (`node.body`) — never `ast.walk(node)`
   on the whole node. `ast.walk` also descends into the *sibling* fields (`orelse`,
   `handlers`, `finalbody`, a loop's `else`), which execute at runtime. Walking the
   whole `if TYPE_CHECKING:` node, for instance, sweeps its `else:` branch into the
   "type-only, exempt" set and silently bypasses SKUEL022 (the bug PR #64 fixed).
   Recursing *within* `node.body` into nested structures is correct; jumping to a
   sibling field is the leak.
2. **Pin the base of a Name/Attribute match — don't accept a loose tail.** Matching
   `attr == "Foo"` (or `id == "foo"`) without validating the base/binding accepts
   unintended targets: `anything.Foo`, a local var shadowing a known name. SKUEL022's
   `_is_type_checking_test` pins the Attribute form to `typing.TYPE_CHECKING` (so
   `settings.TYPE_CHECKING` is not exempted); SKUEL020's `_annotation_is_request`
   checks the full dotted name against an allowlist (`VALID_REQUEST_QUALNAMES`) so
   `foo.Request` is flagged, not waved through. A wrongly-loose match in an *exemption*
   path is a false-negative bypass; tightening it can at worst produce a safe,
   suppressible false-positive.

## Running the Linters

**Primary interface — use `./dev` commands:**
```bash
./dev format        # Auto-format with Ruff
./dev lint          # Run Ruff + SKUEL pattern linter
./dev lint-fix      # Auto-fix Ruff issues
./dev quality       # Run ALL checks (format + Ruff + SKUEL + Cypher + MyPy)
./dev quality-fix   # Run all checks with auto-fix
```

**Direct uv commands** (when you need options `./dev` doesn't expose):
```bash
# Ruff - fast Python linter
uv run ruff check .

# MyPy - type checking
uv run mypy core/ adapters/ routes/

# SKUEL pattern linter (all rules)
uv run python scripts/lint_skuel.py

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

# Quiet gate mode (minimal output, warnings fail)
uv run python scripts/lint_skuel.py --quiet --strict

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
  run: uv run python scripts/lint_skuel.py --strict
```

## Linter Configuration Files

- **pyproject.toml** - Main configuration for ruff, mypy, pyright
- **scripts/lint_skuel.py** - Custom SKUEL pattern enforcement (25 rules)
- **scripts/cypher_linter.py** - Cypher query static analysis (11 rules, 2 disabled)
- **Exceptions documented in:** `pyproject.toml` section `[tool.ruff.lint.per-file-ignores]`

**See:** [UV Guide](../guides/UV_GUIDE.md) for package manager commands, [Linter Guide](../guides/LINTER_GUIDE.md) for full CLI reference

## Exclusion Patterns

The linter automatically excludes certain files from specific rules. Per-file exemptions use inline suppression comments (see above) rather than hardcoded allowlists.

| Rule | Auto-Excluded Directories | Per-File Suppression |
|------|--------------------------|---------------------|
| **SKUEL005** | Protocol files | `# skuel-lint: disable-file=SKUEL005` |
| **SKUEL008** | Domain backends (`adapters/persistence/neo4j/backends/`) | N/A |
| **SKUEL011** | Tests, `sort_functions.py` | `# skuel-lint: disable=SKUEL011` |
| **SKUEL012** | Tests, `examples/` | `# skuel-lint: disable=SKUEL012` |
| **SKUEL015** | Tests, `scripts/`, `examples/`, `debug_*`, `lint_skuel.py`, `dev`, `__main__` blocks, docstrings | `# skuel-lint: disable=SKUEL015` |
| **SKUEL017** | Tests, `scripts/`, `result_simplified.py` | `# intentional-broad:`, `# safety-net:`, or `# skuel-lint: disable=SKUEL017` |
| **SKUEL018** | Tests, `unified_user_context.py`, `user_context_populator.py` | `# skuel-lint: disable=SKUEL018` |
| **SKUEL019** | Tests, `credential_store.py`, `credential_setup.py`, both `migrate_secrets_*` scripts, `lint_skuel.py` | `# skuel-lint: disable=SKUEL019` |
| **SKUEL030** | Everything outside `adapters/persistence/`; `scripts/migrations/`; docstrings; names in `SKUEL030_BASELINE` | `# skuel-lint: disable=SKUEL030` |

## Benefits Achieved

1. **Automated Enforcement** - Patterns checked on every commit
2. **Fast Feedback** - Violations caught before code review
3. **Consistent Codebase** - All code follows same patterns
4. **Self-Documenting** - Linter messages explain best practices (`--explain`)
5. **Flexible Severity** - CRITICAL/ERROR always fail; WARNING fails the `--strict` gates (`./dev lint` / `./dev quality`) now that the tier is at zero, but stays advisory in plain runs

---

**Last Updated:** 2026-07-19
**Status:** Active - 25 rules (SKUEL001–SKUEL026; SKUEL004 deleted 2026-07, IDs not renumbered) enforcing SKUEL architectural patterns, unified inline suppression via `# skuel-lint: disable=SKUELXXX` with a per-run unused-suppression audit (SKUEL026). Files are parsed ONCE per run — `_lint_file` hands a shared AST to every tree-based rule. Unit tests cover both linters.
