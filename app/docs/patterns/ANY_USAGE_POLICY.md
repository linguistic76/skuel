# Any Usage Policy

*Last updated: 2026-02-28*

SKUEL treats `Any` as a last resort, not a default. Every use of `Any` must belong to one
of the three categories below. Unlabelled `Any` annotations are technical debt and should
be refactored toward a specific type.

---

## Category A — Lazy Typing (Must Not Exist)

These are `Any` uses that exist out of habit or because no one got around to typing them.
They provide no value and actively undermine type safety.

**Examples of Category A (now fixed):**
- `logger: Any` — Should always be `logging.Logger`
- `driver: Any` (concrete `__init__` parameter) — Should be `neo4j.AsyncDriver`
- `prometheus_metrics: Any` — Should be `PrometheusMetrics | None`
- `services: Any` (in route factories) — Should be `Services | None`
- `priority: Any` in Protocol attributes — Should be the specific enum

If you encounter Category A `Any` during development, fix it immediately. There is no
architectural reason for these to exist.

---

## Category B — Reducible (Use Specific Types Below)

These `Any` uses can be replaced with more precise types that SKUEL defines.

### Neo4j Boundary Types

When handling raw data from the Neo4j driver, use these aliases instead of `dict[str, Any]`:

```python
from core.models.type_hints import Neo4jProperties, Neo4jValue

# For node property dicts from the driver
node_data: Neo4jProperties  # = dict[str, Neo4jValue]

# For individual values
value: Neo4jValue  # = str | int | float | bool | list[...] | None | datetime
```

**When to use:** `from_neo4j_node()`, any function that accepts raw Neo4j node data as input.

### Filter/Query Parameters

When accepting search or filter parameters with known value shapes:

```python
from core.models.type_hints import FilterParams, FilterValue

async def find_by_filters(filters: FilterParams) -> list[Entity]: ...
# FilterParams = dict[str, FilterValue]
# FilterValue = str | int | float | bool | list[str | int | float] | None
```

**When to use:** Search service methods, `find_by()` style functions.

### Relationship Metadata

The `RelationshipMetadata` TypedDict (in `core/ports/base_protocols.py`) covers 27 common
relationship edge properties. Use it instead of `Metadata` for relationship operations.

```python
from core.ports.base_protocols import RelationshipMetadata

async def create_relationship(
    from_uid: str, to_uid: str, properties: RelationshipMetadata | None = None
) -> Result[bool]: ...
```

### Generic Function Types

Instead of `Callable[[Any], bool]`, use the generic versions:

```python
from core.models.type_hints import EntityFilter, Validator, Scorer

sorter: EntityFilter[Task]   # = Callable[[Task], bool]
scorer: Scorer[Goal]         # = Callable[[Goal], Score]
validator: Validator[Habit]  # = Callable[[Habit], list[str]]
```

---

## Category C — Permanent Boundaries (Document with `# boundary:`)

These `Any` uses represent genuine limits of Python's type system or the capabilities of
third-party libraries. They cannot be eliminated without disproportionate effort or loss
of expressiveness. All must be annotated with a `# boundary:` comment.

### `# boundary: neo4j-primitives`

Neo4j node property *values* can be any Neo4j primitive (use `Neo4jProperties` for the
dict, but the values inside mapper internals may still be `Any` during conversion).
The `from_neo4j_node` mapper accepts `Neo4jProperties` at its entry point, but internally
handles conversions that require type narrowing with `Any`.

```python
node_data: dict[str, Any]  # boundary: neo4j-primitives — raw record from driver.data()
```

### `# boundary: fasthtml-elements`

FastHTML HTML element factories (`Div`, `Span`, `CardBody`, etc.) accept variadic children
and arbitrary HTML attributes. HTML structure is inherently dynamic; a complete TypedDict
for all HTML attributes would be impractical.

```python
def CardBody(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    # boundary: fasthtml-elements — html children and attrs are structurally dynamic
```

### `# boundary: fasthtml-app`

The FastHTML `app` object's type hierarchy is not exported by the library. The `FastHTMLApp`
protocol in `adapters/inbound/fasthtml_types.py` captures the minimal interface SKUEL uses.
The `Any` in its `__call__` signature (ASGI scope/receive/send) is a framework boundary.

### `# boundary: error-metadata`

`ErrorContext.details: dict[str, Any]` — Error diagnostic metadata is intrinsically
heterogeneous. A `ValidationError` carries field names and values; a `DatabaseError` carries
query fragments and retries; an `IntegrationError` carries HTTP status codes. A single
TypedDict cannot cover all cases without being a large union, defeating the purpose.

```python
details: dict[str, Any]  # boundary: error-metadata — error context is heterogeneous
```

### `# boundary: placeholder`

Functions with `_underscored` parameters that are explicitly marked as placeholders for
future implementation. These use `Any` intentionally until the service type is defined.

```python
_tasks_service: Any = None  # boundary: placeholder — TasksService not yet threaded here
```

---

## Quick Reference

| Situation | Old | Correct |
|-----------|-----|---------|
| Logger field | `logger: Any` | `logger: logging.Logger` |
| Neo4j driver | `driver: Any` | `driver: AsyncDriver` |
| Metrics | `prometheus_metrics: Any` | `prometheus_metrics: PrometheusMetrics \| None` |
| Services container | `services: Any` | `services: Services \| None` |
| FastHTML `rt` | `rt: Any` | `rt: RouteDecorator` (from `fasthtml_types`) |
| FastHTML `app` | `app: Any` | `app: FastHTMLApp` (from `fasthtml_types`) |
| Neo4j node dict | `dict[str, Any]` | `Neo4jProperties` |
| Search filters | `dict[str, Any]` | `FilterParams` |
| Relationship props | `Metadata` | `RelationshipMetadata` |
| Generic callable | `Callable[[Any], bool]` | `EntityFilter[T]` |
| HTML children | `*c: Any` | *keep — Category C boundary* |
| Error details | `dict[str, Any]` | *keep — Category C boundary* |

---

## Enforcement

- The ruff linter does not currently flag `Any` usage (too broad to auto-enforce).
- Code reviewers should challenge any new `Any` that is not in a `# boundary:` comment.
- When refactoring, replace `Any` with the most specific type from this policy.
- If a new boundary is genuinely needed, add it to this document with an explanation.
