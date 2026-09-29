# Python Type Hints Reference

## Modern Syntax (Python 3.14)

### Built-in Generic Types

```python
# Use lowercase built-in types (3.10+)
items: list[str] = []
mapping: dict[str, int] = {}
coords: tuple[float, float] = (0.0, 0.0)
unique: set[int] = set()
frozen: frozenset[str] = frozenset()

# Variable-length tuple
args: tuple[int, ...] = (1, 2, 3)
```

### Union Types

```python
# Use pipe syntax (3.10+)
value: int | str = 42
maybe: Task | None = None

# Multiple types
result: Success | Failure | Pending = Success()
```

### Optional Shorthand

```python
# These are equivalent
task: Task | None = None
task: Optional[Task] = None  # Older style - avoid

# Prefer the pipe syntax
```

## Collections.abc Types

```python
from collections.abc import (
    Sequence,     # Read-only list-like
    Mapping,      # Read-only dict-like
    MutableMapping,  # Writable dict-like
    Iterable,     # Can iterate
    Iterator,     # Has __next__
    Callable,     # Can call
    Awaitable,    # Can await
)

# Function parameters: accept broad types
def process(items: Sequence[Task]) -> None:
    """Accepts list, tuple, or any sequence"""
    for item in items:
        ...

# Return types: be specific
def get_all() -> list[Task]:
    """Returns specifically a list"""
    return [...]
```

## Callable Types

```python
from collections.abc import Callable, Awaitable

# Simple callback
Callback = Callable[[str], None]

# With multiple args
Processor = Callable[[Task, dict], Result[Task]]

# Async callback
AsyncCallback = Callable[[str], Awaitable[Result[Task]]]

# No args
Factory = Callable[[], Task]

# With keyword args (use ParamSpec for full typing)
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")

def decorator(func: Callable[P, R]) -> Callable[P, R]:
    ...
```

## Generic Types

SKUEL's core generics use PEP 695 syntax — `class Result[T]:`,
`class CrudOperations[T: "DomainModelProtocol"](Protocol):`, `def require_found[T](...)`.
Older modules still use `TypeVar` + `Generic[T]`; both pass the lint (UP046/UP047 are ignored).

```python
# PEP 695 (Python 3.12+) — no TypeVar declaration
class Repository[T]:
    async def get(self, uid: str) -> Result[T | None]: ...

def first[T](items: Sequence[T]) -> T | None:
    return items[0] if items else None

# Bounded
class Store[T: DomainModelProtocol]: ...
```

### TypeVar

```python
from typing import TypeVar

# Basic TypeVar
T = TypeVar("T")

# Bounded TypeVar
TaskLike = TypeVar("TaskLike", bound="Task")

# Constrained TypeVar
Number = TypeVar("Number", int, float)
```

### Generic Classes

```python
from typing import Generic, TypeVar

T = TypeVar("T")

class Repository(Generic[T]):
    def __init__(self, model_class: type[T]) -> None:
        self.model_class = model_class

    async def get(self, uid: str) -> Result[T | None]:
        ...

    async def create(self, data: dict) -> Result[T]:
        ...

# Usage
task_repo: Repository[Task] = Repository(Task)
```

### Covariance and Contravariance

```python
from typing import TypeVar

# Covariant (output positions)
T_co = TypeVar("T_co", covariant=True)

# Contravariant (input positions)
T_contra = TypeVar("T_contra", contravariant=True)

class Reader(Generic[T_co]):
    def read(self) -> T_co: ...

class Writer(Generic[T_contra]):
    def write(self, value: T_contra) -> None: ...
```

## Protocol Types

SKUEL's attribute protocols (`HasUID`, `HasScore`, `HasCreatedAt`, …) live in the
"Attribute Protocols" section of `core/ports/base_protocols.py` — they replace `hasattr()`
(SKUEL011).

```python
from typing import Protocol, runtime_checkable

class HasUID(Protocol):
    """Protocol for entities with UID"""
    uid: str

class Closeable(Protocol):
    """Protocol for closeable resources"""
    def close(self) -> None: ...

# Runtime checkable for isinstance()
@runtime_checkable
class Serializable(Protocol):
    def to_dict(self) -> dict: ...

# Usage
def process(entity: HasUID) -> str:
    return entity.uid

if isinstance(obj, Serializable):
    data = obj.to_dict()
```

## Type Aliases

SKUEL writes aliases with the `type` statement (PEP 695):

```python
# Simple alias (core/models/type_hints.py)
type UIDList = list[EntityUID]

# Complex alias
type EntityMap = dict[str, list[Task | Goal | Habit]]

# Parameterized alias
type ResultList[T] = Result[list[T]]
```

**SKUEL-specific type aliases** (from `core/models/type_hints.py`):

```python
from core.models.type_hints import Neo4jProperties, FilterParams, Neo4jValue, Metadata

# Neo4j node property dicts — use instead of dict[str, Any]
type Neo4jValue = str | int | float | bool | list[str | int | float] | None | datetime
type Neo4jProperties = dict[str, Neo4jValue]

# Search/filter parameters — use instead of dict[str, Any]
type FilterValue = str | int | float | bool | list[str | int | float] | None
type FilterParams = dict[str, FilterValue]

# Dynamic request data — use only for truly dynamic data
type Metadata = dict[str, Any]  # boundary: use specific types above when possible
```

## Literal Types

```python
from typing import Literal

# Exact values
Direction = Literal["incoming", "outgoing", "both"]
Status = Literal["pending", "in_progress", "completed"]

def get_related(
    uid: str,
    direction: Direction = "outgoing"
) -> Result[list[str]]:
    ...
```

## TypedDict

```python
from typing import TypedDict, Required, NotRequired

class TaskData(TypedDict):
    uid: str
    title: str
    description: NotRequired[str]  # Optional key

class TaskCreateData(TypedDict, total=False):
    title: Required[str]  # Required even with total=False
    description: str
    priority: str

# Usage
data: TaskData = {"uid": "123", "title": "Test"}
```

**SKUEL protocol return TypedDicts** (from `core/ports/query_types.py`):

```python
from core.ports.query_types import (
    # Input types (filters; non-activity update payloads — activity domains use
    # frozen *UpdateIntent dataclasses instead, ADR-066)
    ActivityFilterSpec, KuUpdatePayload, CypherParams,
    # Domain stats
    TaskStats, GoalStats, HabitStats, EventStats, ChoiceStats, PrincipleStats,
    # System health + finance
    SystemInfoResult, HealthSummaryResult, AlertCheckResult,
    SystemHealthStatus, HealthCheckValidation,
    ComponentHealthStatus, HealthCheckerValidationResult,
    InvoiceStats,
    # Teacher review + submissions + review queue
    ReportSubmitResult, ExerciseWithSubmissionCounts, SubmissionStatistics,
    ReportSummary, LearningLoopChain, SubmissionChain,
    GroupMemberProgress, ReviewRequestResult, PendingReviewItem,
    # Visualization configs
    ChartJsConfig, GanttConfig,
    # Other output types (protocol return shapes)
    SignInResult, ReviewQueueItem, TeacherDashboardStats,
    KnowledgeSuggestionsResult, KnowledgePrerequisitesResult,
    LifePathStatus, LifePathAlignmentResult,
    LateralRelationshipItem, BlockingChainResult,
    AnnotationResult, PrivacySummary,
    ContextDashboard, ContextSummary, IntelligenceResult,
    # Context intelligence results
    NextActionResult, AtRiskHabitsResult, AdaptiveLearningPathResult,
    FutureContextStateResult, ContextHealthResult,
    # Graph entity results
    GraphInfluenceItem, RelationshipSummaryResult,
    # Curriculum structure results
    PsKnowledgeSummaryResult,
    PsPracticeSummaryResult, UserProgressResult,
    # UserContext field types
    RichEntityItem, RichKnowledgeUnitItem, RichLearningPathItem,
    RichPathStepItem, CrossDomainInsightsData,
    UnsubmittedExerciseItem, FacetInteractionItem,
)

# Protocol methods use these as return types instead of dict[str, Any]
async def get_dashboard_stats(self, teacher_uid: str) -> Result[TeacherDashboardStats]: ...
async def sign_in(self, email: str, password: str) -> Result[SignInResult]: ...
async def get_full_status(self, user_uid: UserUID) -> Result[LifePathStatus]: ...
```

## Final and ClassVar

```python
from typing import Final, ClassVar

class Config:
    # Class variable (not instance)
    default_timeout: ClassVar[int] = 30

    # Cannot be reassigned
    MAX_RETRIES: Final = 3

    def __init__(self) -> None:
        self.timeout = Config.default_timeout
```

## Self Type

```python
from typing import Self

class Task:
    def with_priority(self, priority: Priority) -> Self:
        """Returns same type for method chaining"""
        return replace(self, priority=priority)

class HighPriorityTask(Task):
    # with_priority returns HighPriorityTask, not Task
    pass
```

## Overload

```python
from typing import overload

@overload
def get(uid: str) -> Task: ...

@overload
def get(uid: str, default: T) -> Task | T: ...

def get(uid: str, default: T | None = None) -> Task | T | None:
    result = fetch(uid)
    return result if result else default
```

## NewType for Semantic Types

```python
from typing import NewType

# Create distinct types for type checking (from core/models/type_hints.py)
UserUID = NewType("UserUID", str)     # User identity — auth boundary creates these
EntityUID = NewType("EntityUID", str) # Entity identity — generic entity references

# All protocols, services, backends use typed UIDs:
async def verify_ownership(self, uid: str, user_uid: UserUID) -> Result[T]: ...
async def get_context(self, entity_uid: EntityUID) -> Result[dict]: ...

# Auth creates UserUID at the boundary:
user_uid: UserUID = require_authenticated_user(request)

# A required field has no default — kw_only=True lets it follow defaulted base fields
# (core/models/user_owned_entity.py):
user_uid: UserUID

# Type checker catches identity mixing:
task_uid = TaskUID("task_a1b2c3d4")
get_user_tasks(task_uid)  # Type error! TaskUID != UserUID
```

## Type Guards

```python
from typing import TypeGuard

def is_task(entity: Task | Goal | Habit) -> TypeGuard[Task]:
    """Narrow type to Task"""
    return isinstance(entity, Task)

def due_date_of(entity: Task | Goal | Habit) -> date | None:
    if is_task(entity):
        return entity.due_date  # narrowed to Task — a Task-specific attribute
    return None
```

## Common Patterns

### Function Signatures

```python
# Accept broad, return specific
def filter_tasks(
    tasks: Sequence[Task],
    predicate: Callable[[Task], bool]
) -> list[Task]:
    return [t for t in tasks if predicate(t)]

# Async function
async def fetch_task(uid: str) -> Result[Task]:
    ...

# Generator
def iter_tasks(tasks: Sequence[Task]) -> Iterator[Task]:
    for task in tasks:
        yield task

# Async generator
async def stream_tasks() -> AsyncIterator[Task]:
    async for task in task_stream:
        yield task
```

### Class Type Hints

Never quote an annotation — UP037 is live. PEP 649 defers annotation evaluation, so a
class can name itself (or a `TYPE_CHECKING`-only import) unquoted:

```python
from dataclasses import dataclass
from typing import Self

from core.utils.uid_generator import UIDGenerator

@dataclass(frozen=True, kw_only=True)
class Node:
    uid: str
    title: str
    children: tuple[Node, ...] = ()  # the class names itself, unquoted

    @classmethod
    def create(cls, title: str) -> Self:
        return cls(uid=UIDGenerator.generate_uid("node"), title=title)  # "node_a1b2c3d4"
```

A `NameError` from an `__annotate__` frame means something *read* the annotation at runtime:
a `@rt()` handler needs a real import, not a `TYPE_CHECKING` one. See
`/docs/TROUBLESHOOTING.md § Forward References — Never Quote an Annotation`.

### Context Managers

```python
from contextlib import contextmanager, asynccontextmanager
from collections.abc import Generator, AsyncGenerator

@contextmanager
def transaction() -> Generator[Connection, None, None]:
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except BaseException:  # intentional-broad: roll back on any exit (cancellation included), then re-raise
        conn.rollback()
        raise

@asynccontextmanager
async def async_transaction() -> AsyncGenerator[Connection, None]:
    conn = await get_connection()
    try:
        yield conn
        await conn.commit()
    except BaseException:  # intentional-broad: roll back on any exit (cancellation included), then re-raise
        await conn.rollback()
        raise
```

## Anti-Patterns

### Don't Use `Any` Unnecessarily

```python
# BAD
def process(data: Any) -> Any:
    return data["result"]

# GOOD
def process(data: TaskData) -> str:
    return data["result"]
```

### Don't Mix Old and New Syntax

```python
# BAD - mixing styles
from typing import List, Optional

def process(items: List[str]) -> str | None:  # Inconsistent
    ...

# GOOD - consistent modern syntax
def process(items: list[str]) -> str | None:
    ...
```

### Don't Ignore Generic Parameters

```python
# BAD
tasks: list = get_tasks()  # Untyped list

# GOOD
tasks: list[Task] = get_tasks()
```

## MyPy Configuration

SKUEL uses per-module strictness overrides (not global strict mode). As of March 2026, `./dev quality` enforces **0 MyPy errors**. Key config in `pyproject.toml`:

```toml
[tool.mypy]
strict = false  # Per-module overrides instead
warn_unused_configs = true
no_implicit_optional = true
# No global disable_error_code — arg-type is enforced on all first-party trees
# (core, services_bootstrap, adapters, ui) as of 2026-05-31. tests/examples/scripts
# scope-disable [method-assign, type-var, misc, arg-type] (framework-mock noise).
```

No error codes are globally disabled (the `arg-type` sweep completed 2026-05-31, deleting the last global disable). The `assignment` code is enabled — it catches trailing-comma tuple bugs (e.g., `x = value,` silently creating a tuple) and type mismatches on variable reassignment.

### Per-Module Strictness

`core.ports.*` enforces `disallow_untyped_defs = true` — all protocol methods must have full type annotations.

### Neo4j Property Type Narrowing

When values come from `Neo4jProperties` (`dict.get()`), narrow with casts before arithmetic:

```python
# Neo4j dict.get() returns str | int | float | bool | list | datetime | None
total = int(progress_data.get("total_lessons", 0))
ema = float(state.get("feedback_ema_hours") or 0.0)
```
