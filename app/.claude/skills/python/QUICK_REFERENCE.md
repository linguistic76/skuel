# Python - Quick Reference

> **Fast lookup** for common syntax, methods, and operations

---

## Canonical Shapes

### Result[T] service method

```python
from core.utils.result_simplified import Errors, Result

async def get(self, uid: str) -> Result[Task]:
    result = await self.backend.get(uid)
    if result.is_error:
        return Result.fail(result)          # propagate across type boundaries
    if result.value is None:
        return Result.fail(Errors.not_found("Task", uid))
    return Result.ok(result.value)
```

**When to use**: Every service operation — `Result[T]` internally, HTTP conversion only at route boundaries. `.is_error` (never `.is_err`, SKUEL003); `.expect_error()` only when you need to *read* the error.

### Fetch + not-found guard in routes

```python
from adapters.inbound.result_helpers import require_found

result = require_found(await service.get(uid), "Task", uid)
```

**When to use**: Route handlers — collapses error-propagate + None→NOT_FOUND + type narrowing (`Result[T | None]` → `Result[T]`) into one call. Adapters-side only (core can't import adapters, SKUEL022).

### Errors factory (never construct ErrorContext by hand)

```python
Errors.not_found("Task", uid)                     # missing resource
Errors.validation("Title is required", field="title")  # single-field input
Errors.business("no_overlap", "Overlapping budget exists")  # domain rule / multi-entity
Errors.database("create_task", "Query failed")    # Neo4j operation
Errors.integration("openai", "Rate limited", status_code=429)  # external service
Errors.unavailable("semantic_search", "Embeddings not configured")  # optional feature off
Errors.system("Unexpected failure", exception=e)  # last resort
```

**When to use**: All error creation (SKUEL007). Each returns `ErrorContext` — wrap with `Result.fail(...)`. Multi-field uniqueness and state checks are `business`, not `validation`.

### Frozen dataclass domain model

```python
from dataclasses import dataclass, replace

@dataclass(frozen=True, kw_only=True)
class Task(UserOwnedEntity):
    ...

updated = replace(task, status=EntityStatus.COMPLETED)  # immutable update
```

**When to use**: All core domain models (Tier 3). `Entity` in `core/models/entity.py` is the base; Pydantic at edges, DTOs for transfer, frozen dataclasses at the core.

### Async for I/O, sync for computation

```python
async def get_task(self, uid: str) -> Result[Task]:   # awaits backend → async
    return await self.backend.get(uid)

def to_numeric(self) -> int:                          # pure computation → sync
    return _PRIORITY_NUMERIC_VALUES[self]
```

**When to use**: If the body needs `await` (database, service calls), make it `async def`. Otherwise plain `def` — conversions, scoring, formatting stay sync.

### Protocol-based typing

```python
from typing import Protocol

class TasksBackendOperations(Protocol):
    async def get(self, uid: str) -> Result[Task | None]: ...
```

**When to use**: Typing `self.backend` in services and route-facing thin services. Protocols live in `core/ports/`. Two layers: `*BackendOperations` (backend contract) vs `*Operations` (route-facing API) — verify the layer before retyping. Facades (Tasks, Goals, …) use concrete classes.

### Narrow exception handling (SKUEL017)

```python
from core.utils.exception_types import NEO4J_EXCEPTIONS

try:
    records = await session.run(query)
except NEO4J_EXCEPTIONS as e:
    return Result.fail(Errors.database("run_query", str(e)))
```

**When to use**: Every `except` — pick the tuple from `core/utils/exception_types.py` (`NEO4J_EXCEPTIONS`, `LLM_EXCEPTIONS`, `DATA_CONVERSION_EXCEPTIONS`, `FILE_IO_EXCEPTIONS`, `YAML_EXCEPTIONS`, `PARSING_EXCEPTIONS`, …). Intentional broad catches need `# intentional-broad:` or `# safety-net:` annotations.

### Logging

```python
from core.utils.logging import get_logger

logger = get_logger("skuel.services.tasks")
logger.info("Created task '%s' with %d knowledge links", task.title, count)
```

**When to use**: All production runtime output — `print()` is SKUEL015; `print()` is only for interactive CLI scripts.

---

## Key Conventions

| Convention | Rule |
|-----------|------|
| Imports | `Result`/`Errors` from `core.utils.result_simplified`; `RelationshipName` from `core.models.relationship_names`; `EntityType`/`EntityStatus` from `core.models.enums.entity_enums` |
| Enums | Members, not strings (SKUEL014); `.value` only at serialization boundaries; presentation logic lives IN the enum (`Priority.get_color()`) |
| Type syntax | Modern generics: `class Result[T]:`, `def require_found[T](...)`, `list[str]`, `Task | None` — no `typing.List/Optional` |
| `Any` | Must mean *genuinely heterogeneous*; every new `Any` needs a `# boundary:` comment |
| Suppression | `# skuel-lint: disable=SKUELXXX -- <reason>` (line) / `disable-file=` (file) |
| Run code | `uv run python script.py` — uv for everything, never Poetry (SKUEL016) |
| Quality gate | `./dev quality` (Ruff + MyPy 0 errors + audit scripts); `./dev format`; `./dev bloat` |

---

## Common Pitfalls

| Problem | Solution |
|---------|----------|
| `result.is_err` | `.is_error` (SKUEL003) |
| `Result.fail(result.expect_error())` to propagate | `Result.fail(result)` — accepts a failed Result directly |
| `hasattr(obj, "x")` | Protocol / `isinstance` / `getattr` (SKUEL011) |
| `key=lambda t: t.priority` | Named function (SKUEL012) |
| `print()` in production code | `get_logger(...)` (SKUEL015) |
| `except Exception:` bare | Tuple from `exception_types.py`, or annotate (SKUEL017) |
| Raw Cypher / APOC in `core/` | Cypher lives in `adapters/persistence/neo4j/` (SKUEL021/SKUEL001) |
| `from adapters...` inside `core/` | Forbidden (SKUEL022) — `TYPE_CHECKING`-only imports exempt |
| `os.getenv("OPENAI_API_KEY")` | `get_credential()` (SKUEL019) |
| Route handler `request: Any` | `request: Request` — `Any` causes FastHTML 400 (SKUEL020) |
| Mutating a frozen dataclass | `dataclasses.replace(obj, field=new)` |
| `async def` with no `await` inside | Make it sync `def` |

---

**See Also**: [SKILL.md](SKILL.md) for detailed explanations
**See Also**: [PATTERNS.md](PATTERNS.md) for design patterns
**See Also**: [async-patterns.md](async-patterns.md) and [type-hints-reference.md](type-hints-reference.md)
