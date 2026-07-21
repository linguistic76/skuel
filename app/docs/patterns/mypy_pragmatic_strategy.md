---
title: MyPy Zero-Error Strategy - From Pragmatic Acceptance to Clean Baseline
updated: 2026-03-27
category: patterns
related_skills: []
related_docs:
- /docs/patterns/MYPY_TYPE_SAFETY_PATTERNS.md
- /docs/patterns/RETURN_TYPE_ERROR_PROPAGATION.md
---

# MyPy Zero-Error Strategy - From Pragmatic Acceptance to Clean Baseline

**Last Updated:** March 27, 2026
**Status:** Zero Errors - `./dev quality` passes clean

> **For systematic error reduction patterns:** See [MYPY_TYPE_SAFETY_PATTERNS.md](MYPY_TYPE_SAFETY_PATTERNS.md) for proven techniques used during the reduction (183 -> 114 -> 0 errors).

## Executive Summary

**Question:** "How did SKUEL go from 2200+ MyPy errors to zero?"

**Answer:** **Systematic reduction across three phases** — fix real bugs, resolve type inference noise through targeted patterns, and eliminate stub errors through configuration.

### Current State (March 2026)

- **Total MyPy Errors:** 0
- **`./dev quality`:** Passes clean (MyPy, Ruff, SKUEL linter — all zero errors)
- **Reduction path:** 2247 -> 183 -> 114 -> 0
- **Zero is the enforced baseline.** New code must not introduce MyPy errors.

### The Philosophy

**MyPy's job:** Find bugs before runtime
**Our job:** Fix bugs that matter, configure away noise, enforce zero going forward
**The result:** Type errors are teachers — and we graduated

---

## The 3 Categories of MyPy Errors (All Resolved)

### Category 1: REAL BUGS (Fixed)

**Example:**
```python
# WRONG - Creates tuple instead of list!
action_items: list[str] = field(default_factory=list),  # Trailing comma!

# CORRECT
action_items: list[str] = field(default_factory=list)
```

**Impact:** Runtime crash
**Count:** 82 errors initially (Phase 1); 138 additional found in Phase 4 (~220 total)
**Status:** **FIXED** — Phase 1 via a one-shot automated script (since deleted), Phase 4 via manual sweep after re-enabling `assignment` error code

---

### Category 2: TYPE INFERENCE NOISE (Resolved)

**Example:**
```python
# MyPy complains: "Incompatible types in assignment"
optional_parameters: set[str] = field(default_factory=set)

# But this works perfectly at runtime!
```

**Why MyPy complained:** It couldn't infer that `field(default_factory=set)` returns `set[str]`

**Count:** ~2000 errors
**Status:** **RESOLVED** — via per-module `disable_error_code` overrides in `pyproject.toml`, explicit type narrowing with `int()`/`float()`/`str()` casts on Neo4j properties, and targeted `# type: ignore` annotations where the code was correct but MyPy lacked context.

---

### Category 3: MISSING TYPE STUBS (Resolved)

**Example:**
```python
# MyPy: "Cannot find implementation or library stub for module 'neo4j'"
from neo4j import AsyncDriver
```

**Why:** External libraries (neo4j, langchain, etc.) don't provide type stubs

**Count:** ~165 errors
**Status:** **RESOLVED** — via `follow_imports = "skip"` for external libraries without stubs in `pyproject.toml` overrides.

---

## The March 2026 Resolution

The path from 114 errors to 0 used five key techniques:

### 1. Neo4j Property Type Narrowing

Neo4j returns `Any`-typed values from property dictionaries. Arithmetic or string operations on these trigger MyPy errors. The fix: explicit casts at the point of use.

```python
# BEFORE: MyPy error - unsupported operand types
total = record["count"] + record["extra"]

# AFTER: Explicit narrowing tells MyPy the type
total = int(record["count"]) + int(record["extra"])

# Same pattern for other types
name: str = str(props.get("name", ""))
score: float = float(props.get("score", 0.0))
```

### 2. Domain Backend `# type: ignore[attr-defined]`

Domain backends (e.g., `PsBackend`, `HabitsBackend`) add methods beyond what `BackendOperations[T]` defines. When services call these domain-specific methods through a generically-typed `self.backend`, MyPy cannot verify the attribute exists.

```python
# Backend protocol defines generic ops, but PsBackend adds domain methods
result = await self.backend.get_ps_with_kus(uid)  # type: ignore[attr-defined]
```

This is a conscious trade-off: the backend IS the correct type at runtime (guaranteed by composition), but the generic protocol cannot express every domain extension.

### 3. Per-Module `disable_error_code` in pyproject.toml

Structural MRO conflicts and mixin patterns produce errors that are correct from MyPy's perspective but irrelevant to runtime behavior. Rather than littering code with inline ignores, these are suppressed at the module level:

```toml
[[tool.mypy.overrides]]
module = ["adapters.persistence.neo4j.backends.activity_backends", ...]  # the 8 cluster files
disable_error_code = ["misc"]
```

**No error codes are globally disabled** (the global `disable_error_code` was deleted when the `arg-type` sweep completed, 2026-05-31). The `assignment` error code was re-enabled in March 2026 after fixing all 277 assignment errors (138 trailing-comma tuple bugs + 139 real type mismatches). `tests`/`examples`/`scripts` scope-disable `[method-assign, type-var, misc, arg-type]` (framework-mock noise — fixtures parameterize generics with DTOs, monkey-patch service methods, etc.).

**`arg-type` is ENFORCED on all four first-party trees** — `core/` (2026-05-29), `services_bootstrap/` (2026-05-30), `adapters/` + `ui/` (2026-05-31). A 12-PR sweep drove `core/` 194 → 0 (~80% real signal — frozen-model / enum-NewType / typed-payload boundaries per the functional-direction roadmap); follow-on campaigns cleared `services_bootstrap/` (the composition root, where service↔protocol conformance gaps aggregate; PRs #121–128), `adapters/` (micro-PRs AD-1..AD-8 — AD-9 finance was dissolved by the finance demolition, not rewritten), and `ui/` (UI-1..UI-4 — the FastHTML/MonsterUI boundary, where genuinely-irreducible Alpine colon/`@`/dot attribute splats carry a `# fasthtml dynamic-attr splat` ignore). The global `disable_error_code = ["arg-type"]` was then deleted (UI-5); `arg-type` is now the toolchain default everywhere. **No suppressions to hit the number** — every gap was fixed structurally; PR #120's attempt to flip `services_bootstrap` first (reaching 0 via 21 `# type: ignore`) was rejected and re-sequenced (enforce at the leaves first, the root last).

### 4. Typed Executor Instead of `Any`

Backend mixins that accept a query executor were typed as `Any`. Replacing with the concrete type eliminated errors at every call site:

```python
# BEFORE
async def _execute(self, executor: Any, query: str) -> list[Record]:

# AFTER
from adapters.persistence.neo4j.types import Neo4jQueryExecutor
async def _execute(self, executor: Neo4jQueryExecutor, query: str) -> list[Record]:
```

### 5. Protocol Alignment

Protocol definitions and their implementations had drifted — missing optional parameters, mismatched return types. Aligning protocols to match actual implementations (or vice versa) resolved the remaining errors:

```python
# Protocol was missing the optional parameter
class SearchOperations(Protocol):
    async def search(self, query: str, limit: int = 10,
                     include_archived: bool = False) -> list[Entity]: ...
    #                ^^^ added to match implementation
```

---

## The Solution: Selective Strictness

### Current pyproject.toml Config

```toml
[tool.mypy]
# PRAGMATIC APPROACH: Strict where it matters, lenient for models
strict = false  # Use per-module overrides instead

# Core checks enabled globally
warn_unused_configs = true
no_implicit_optional = true
warn_redundant_casts = true
strict_equality = true

# Lenient global defaults
disallow_untyped_defs = false  # Only enforce in critical modules (core.ports.* overrides to true)
disallow_incomplete_defs = false
warn_return_any = false
warn_unreachable = false
```

### Per-Module Strictness

**Critical modules** (type safety matters):
- `core.utils.result` - Result[T] pattern
- `adapters.inbound.boundary` + `core.utils.error_boundary` - Error handling
- `config` - Application configuration
- `core.ports.*` - Protocol definitions (`disallow_untyped_defs = true` + `warn_return_any = true`)
- `core.auth.*` - Auth boundary (`warn_return_any = true`)

**Medium strictness:**
- `core.services.*` - Business logic
- `core.models.*` - Domain models

**Lenient:**
- `core.events.*` - Auto-generated patterns
- `adapters.*` - Framework integration
- `tests.*` - Testing utilities

---

## How to Use MyPy Effectively

### Goal: Maintain Zero Errors

**Every change must keep `./dev quality` passing.** Zero is the enforced baseline — not a target, the floor.

```bash
# The single command — runs MyPy, Ruff, and SKUEL linter
./dev quality  # 0 errors expected across all tools

# Check specific file during development
uv run mypy core/services/my_new_service.py

# Check with error codes for debugging
uv run mypy --show-error-codes core
```

### When You Encounter a New MyPy Error

1. **Real bug** (wrong type, missing check) — **FIX THE CODE**
2. **Neo4j property type** — **Add explicit cast** (`int()`, `float()`, `str()`)
3. **Domain backend method** — **Add `# type: ignore[attr-defined]`** with comment
4. **Structural/MRO conflict** — **Add per-module override** in `pyproject.toml`
5. **Protocol drift** — **Align protocol to implementation** (or vice versa)

### When to IGNORE MyPy Errors

You should not need to ignore errors — the goal is zero. If an error cannot be fixed cleanly, use the appropriate suppression technique (inline ignore with error code, per-module override) so the total stays at zero.

---

## The Pragmatic Workflow

### For New Code

```python
# REQUIRED - Type hints from the start
async def create_task(
    self,
    title: str,
    user_uid: UserUID
) -> Result[Task]:
    """Create a new task."""
    ...
```

### For Existing Code

```python
# ACCEPTABLE - No type hints if it works and MyPy doesn't complain
async def create_task(self, title, user_uid):
    """Create a new task."""
    ...  # Works fine, don't break it
```

### For Refactoring

```python
# IDEAL - Add types when refactoring
async def create_task(
    self,
    title: str,
    user_uid: UserUID
) -> Result[Task]:
    """Create a new task - refactored with types."""
    ...
```

---

## MyPy Error Suppression Techniques

### Technique 1: Per-Line Suppression

```python
# When MyPy is wrong but code works — always include the error code
result = some_function()  # type: ignore[return-value]
```

### Technique 2: Per-File Suppression

```python
# At top of file
# mypy: disable-error-code="return-value,arg-type"
```

### Technique 3: Per-Module Config

```toml
# In pyproject.toml
[[tool.mypy.overrides]]
module = ["core.utils.*"]
disallow_untyped_defs = false
warn_return_any = false
```

---

## The Reduction Journey

**Phase 1 (December 2025):** Fix real bugs — 82 trailing commas in dataclasses caught by automated script. Runtime crashes prevented.

**Phase 2 (January-February 2026):** Systematic reduction — TYPE_CHECKING imports, Union return fixes, Nullable guards, Protocol sync. 183 -> 114 errors (38% reduction).

**Phase 3 (Early March 2026):** Zero achieved — Neo4j property narrowing, `# type: ignore[attr-defined]` for domain backends, per-module `disable_error_code`, typed executors, protocol alignment. 114 -> 0 errors.

**Phase 4 (Late March 2026): `assignment` re-enabled** — A comprehensive sweep uncovered 277 suppressed `assignment` errors:
- **138 trailing-comma tuple bugs** (total ~220 caught across all phases, up from the original 82)
- **139 real type mismatches** — `BoundLogger` vs `Logger`, `float`/`int` arithmetic on Neo4j properties, `str | None` where `str` was expected, `Result` invariance issues, and more
- **3 `ignore_errors` overrides removed** — `error_handler` (deleted), `schema_change` and `principles_alignment_service` (now pass clean)
- **`assignment` error code re-enabled** globally (reduced from 5 disabled codes to 4)
- **`disallow_untyped_defs = true` enabled for `core.ports.*`** — all protocol definitions now require typed signatures

---

## Comparison with Other Quality Tools

| Tool | Errors | Strategy |
|------|--------|----------|
| **Ruff** | 0 | Enforced — `./dev quality` fails on any error |
| **MyPy** | 0 | Enforced — `./dev quality` fails on any error |
| **SKUEL Linter** | 0 | Enforced — architectural pattern compliance |

**All three work together:**
- Ruff catches style and syntax errors
- MyPy catches type errors
- SKUEL linter enforces architectural patterns

**One command:** `./dev quality` runs all three. All must pass.

---

## Success Metrics

### What Success Looks Like

- **`./dev quality` passes clean** (zero errors across all tools)
- **New code has type hints** (maintained by habit)
- **Critical modules are strict** (Result[T], error handling)
- **Zero errors is the enforced baseline** (regressions caught immediately)

### What Failure Looks Like

- Introducing MyPy errors and suppressing them without understanding why
- Adding blanket `# type: ignore` without specifying the error code
- Disabling MyPy checks globally instead of per-module

---

## The Bottom Line

### From 2200 Errors to Zero

1. Fixed ~220 **REAL BUGS** (trailing-comma tuples: 82 in Phase 1, 138 in Phase 4)
2. Fixed 139 **TYPE MISMATCHES** (BoundLogger, float/int, str|None, Result invariance)
3. Resolved ~2000 **TYPE INFERENCE** errors (per-module overrides, type narrowing)
4. Resolved ~165 **MISSING STUB** errors (`follow_imports = "skip"`)
5. **Re-enabled `assignment`** error code (reduced disabled codes from 5 to 4)
6. Achieved and **ENFORCED ZERO** (March 2026)

### The Philosophy

> "Type errors are teachers, showing us where components don't flow together properly. When errors appear, investigate the fundamental design first rather than working around with quick fixes."

The 2200 errors were not all teachers. Some were noise. The art was knowing which was which — and then systematically addressing both.

---

## Type Narrowing Patterns (December 2025)

When fixing MyPy errors, use these patterns for type narrowing:

### Pattern 1: Direct None Checks (WORKS)

```python
# CORRECT - MyPy narrows the type
if self.relationships is None:
    return Result.fail(Errors.system("Relationships not configured"))
# After this check, MyPy knows self.relationships is not None
await self.relationships.get_related()
```

### Pattern 2: getattr() Does NOT Narrow (FAILS)

```python
# WRONG - MyPy doesn't narrow with getattr()
if getattr(self, "relationships", None) is None:
    return ...
# MyPy still thinks self.relationships might be None!
await self.relationships.get_related()  # Error: might be None
```

### Pattern 3: Assert for Decorator-Guaranteed State

```python
@requires_graph_intelligence("get_with_context")
async def get_with_context(self, uid: str) -> Result[...]:
    # Decorator guarantees graph_intel exists, but MyPy doesn't know
    assert self.graph_intel is not None  # Tells MyPy it's safe
    return await self.graph_intel.analyze(uid)
```

### Pattern 4: Guard with Multiple Conditions

```python
# CORRECT - Combined guard
if include_predictions and self.intelligence_factory:
    # Both conditions must be true to enter
    predictions = await self.intelligence_factory.create()
```

---

## Quick Reference

### Running Quality Checks

```bash
# The single command — 0 errors expected
./dev quality

# Check specific file during development
uv run mypy core/services/my_service.py

# Check with error codes for debugging
uv run mypy --show-error-codes core

# Check with color output
uv run mypy --pretty core
```

### Configuration

- **Main config:** `pyproject.toml` — `[tool.mypy]` section
- **Per-module overrides:** `pyproject.toml` — `[[tool.mypy.overrides]]` sections
- **Ignored libraries:** `pyproject.toml` — `follow_imports = "skip"` overrides

---

## Conclusion

**SKUEL runs with zero MyPy errors.**

- ~220 trailing-comma bugs fixed (82 in Phase 1, 138 in Phase 4)
- 139 real type mismatches fixed (Phase 4)
- ~2000 type inference errors resolved (Phase 2-3)
- ~165 missing stub errors resolved (Phase 3)
- `assignment` error code re-enabled, `core.ports.*` enforces typed defs (Phase 4)
- New code maintains zero baseline
- `./dev quality` enforces it
