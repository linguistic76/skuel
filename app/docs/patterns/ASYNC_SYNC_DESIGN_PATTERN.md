---
title: Async/Sync Design Pattern
updated: 2026-01-03
status: current
category: patterns
tags: [async, sync, patterns, architecture, performance]
related: [protocol_architecture.md, ERROR_HANDLING.md, event_driven_architecture.md]
---

# Async/Sync Design Pattern

## Core Principle: "Async for I/O, Sync for Computation"

SKUEL intentionally uses a mixed async/sync architecture. This is **correct by design**, not technical debt.

- **Async (`async def`)**: Any method that performs I/O (database, network, file system)
- **Sync (`def`)**: Any method that performs pure computation (type conversion, validation, business logic)

## Layer-by-Layer Distribution

| Layer | Async | Sync | Rationale |
|-------|-------|------|-----------|
| **Database/Persistence** | 100% | 0% | All Neo4j operations require await |
| **Service Layer** | ~95% | ~5% | Most methods call backends; init/helpers are sync |
| **Data Conversion** | 0% | 100% | Pure type transformation, no I/O |
| **Domain Models** | 0% | 100% | Pure business logic and computed properties |
| **Utilities** | ~5% | ~95% | Most are pure functions; few handle async resources |
| **Routes** | ~95% | ~5% | HTTP handlers async; UI component rendering sync |

## Correct Patterns by Layer

### 1. Database/Persistence Layer (100% Async)

All database operations are async because they involve I/O wait time:

```python
# adapters/persistence/neo4j/universal_backend.py

async def create(self, entity: T) -> Result[T]:
    """HAS I/O - Neo4j database write"""
    node_data = to_neo4j_node(entity)  # Sync helper (pure)

    query = f"CREATE (n:{self.label}) SET n = $props RETURN n"

    async with self.driver.session() as session:
        result = await session.run(query, {"props": node_data})  # I/O!
        record = await result.single()  # I/O!

    created = from_neo4j_node(dict(record["n"]), self.entity_class)  # Sync (pure)
    return Result.ok(created)

async def get(self, uid: str) -> Result[T | None]:
    """HAS I/O - Neo4j database read"""
    # ... database query with await

async def find_by(self, limit: int = 100, **filters) -> Result[list[T]]:
    """HAS I/O - Neo4j query execution"""
    # ... database query with await
```

**Sync helpers in backends are correct** when they perform pure computation:

```python
def _extract_label_from_uid(self, uid: str) -> str | None:
    """NO I/O - Pure string pattern matching"""
    patterns = {"task:": "Task", "event:": "Event", "habit:": "Habit"}
    for prefix, label in patterns.items():
        if uid.startswith(prefix):
            return label
    return None

def _build_generic_context_query(self, uid: str, intent: QueryIntent) -> str:
    """NO I/O - Pure Cypher query string building"""
    return f"MATCH (n) WHERE n.uid = $uid ..."
```

### 2. Service Layer (~95% Async)

Service methods are async when they call backends or other services:

```python
# core/services/base_service.py

async def create(self, entity: T) -> Result[T]:
    """Calls backend - must be async"""
    return await self.backend.create(entity)

async def get(self, uid: str) -> Result[T]:
    """Calls backend - must be async"""
    return await self.backend.get(uid)

async def verify_ownership(self, uid: str, user_uid: str) -> Result[T]:
    """Calls backend - must be async"""
    result = await self.backend.get(uid)
    # ... ownership check logic
```

**Sync service methods are correct** for pure operations:

```python
def __init__(self, backend: B, service_name: str | None = None) -> None:
    """NO I/O - Just attribute assignment"""
    self.backend = backend
    self.service_name = service_name

def _ensure_exists(self, result: Result[T | None], resource_name: str, identifier: str) -> Result[T]:
    """NO I/O - Pure Result monad operation"""
    if result.is_error:
        return Result.fail(result)
    if result.value is None:
        return Result.fail(Errors.not_found(resource_name, identifier))
    return Result.ok(result.value)
```

### 3. Data Conversion Layer (100% Sync)

Type conversion is pure computation with no I/O:

```python
# core/utils/neo4j_mapper.py

def to_neo4j_node(entity: Any) -> dict[str, Any]:
    """NO I/O - Pure type transformation"""
    node_data: dict[str, Any] = {}
    for field in fields(entity):
        value = getattr(entity, field.name)
        if isinstance(value, Enum):
            node_data[field.name] = value.value  # Pure extraction
        elif isinstance(value, date | datetime):
            node_data[field.name] = value.isoformat()  # Pure formatting
        else:
            node_data[field.name] = value
    return node_data

def from_neo4j_node[T](data: dict[str, Any], entity_class: type[T]) -> T:
    """NO I/O - Pure type reconstruction"""
    # Type hint parsing, enum instantiation, date parsing
    # All pure computation
```

### 4. Domain Models (100% Sync)

Domain models contain business logic, not I/O:

```python
# core/models/task.py

@dataclass(frozen=True)
class Task:
    uid: str
    title: str
    due_date: date | None

    def is_overdue(self) -> bool:
        """NO I/O - Pure date comparison"""
        if self.due_date is None:
            return False
        return date.today() > self.due_date

    def calculate_priority_score(self) -> float:
        """NO I/O - Pure business logic calculation"""
        score = 0.0
        if self.is_overdue():
            score += 10.0
        # ... more pure computation
        return score
```

### 5. Utilities (90%+ Sync)

Most utilities are pure functions:

```python
# core/utils/timestamp_helpers.py

def format_datetime(dt: datetime) -> str:
    """NO I/O - Pure string formatting"""
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def parse_date(date_str: str) -> date | None:
    """NO I/O - Pure parsing"""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None

# core/utils/uid_generator.py

def generate_uid(prefix: str) -> str:
    """NO I/O - Pure string generation"""
    return f"{prefix}:{uuid4().hex[:12]}"
```

## Decision Criteria

Use this checklist when writing new methods:

| Question | If Yes → | If No → |
|----------|----------|---------|
| Does it query Neo4j? | `async def` | Continue |
| Does it call an async method? | `async def` | Continue |
| Does it make HTTP requests? | `async def` | Continue |
| Does it read/write files? | `async def` | Continue |
| Does it use async context managers? | `async def` | Continue |
| Otherwise (pure computation) | `def` | `def` |

**Simple rule:** If you need `await` inside the function, make it `async def`.

## Common Mistakes to Avoid

### Mistake 1: Making pure functions async

```python
# WRONG - unnecessary async overhead
async def validate_email(email: str) -> bool:
    return "@" in email and "." in email

# CORRECT - pure validation is sync
def validate_email(email: str) -> bool:
    return "@" in email and "." in email
```

### Mistake 2: Making I/O functions sync

```python
# WRONG - blocks the event loop
def get_user(uid: str) -> User:
    result = driver.execute_query(...)  # Blocking I/O!
    return User(**result)

# CORRECT - async for I/O
async def get_user(uid: str) -> User:
    async with driver.session() as session:
        result = await session.run(...)  # Non-blocking
    return User(**result)
```

### Mistake 3: Mixing sync calls in async context unnecessarily

```python
# WRONG - sync helper called with await
result = await to_neo4j_node(entity)  # to_neo4j_node is sync!

# CORRECT - call sync helpers directly
result = to_neo4j_node(entity)  # No await needed
```

## Why This Pattern Matters

1. **Performance**: Async for I/O allows concurrent operations; sync avoids async overhead for pure computation
2. **Clarity**: The signature communicates intent - `async def` means "this waits for something"
3. **Testing**: Sync functions are easier to unit test (no async fixtures needed)
4. **Debugging**: Stack traces are clearer without unnecessary async boundaries

## Related Documentation

- `/docs/patterns/protocol_architecture.md` - Protocol definitions include async method signatures
- `/docs/patterns/ERROR_HANDLING.md` - Result[T] pattern works with both async and sync
- `/docs/patterns/event_driven_architecture.md` - Event handlers are async
