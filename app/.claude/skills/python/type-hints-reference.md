# Python Type Hints Reference

## Modern Python 3.10+ Syntax

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

```python
from typing import TypeAlias

# Simple alias
UID: TypeAlias = str
Metadata: TypeAlias = dict[str, Any]

# Complex alias
EntityMap: TypeAlias = dict[str, list[Task | Goal | Habit]]

# Parameterized alias (3.12+)
type ResultList[T] = Result[list[T]]

# Or with TypeVar (3.9+)
T = TypeVar("T")
ResultList = Result[list[T]]
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

# Create distinct types for type checking
UserUID = NewType("UserUID", str)
TaskUID = NewType("TaskUID", str)

def get_user_tasks(user_uid: UserUID) -> list[Task]:
    ...

# Type checker catches this mistake
task_uid = TaskUID("task:123")
get_user_tasks(task_uid)  # Type error!
```

## Type Guards

```python
from typing import TypeGuard

def is_task(entity: Task | Goal | Habit) -> TypeGuard[Task]:
    """Narrow type to Task"""
    return isinstance(entity, Task)

def process(entity: Task | Goal | Habit) -> None:
    if is_task(entity):
        # entity is now typed as Task
        print(entity.due_date)  # Task-specific attribute
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

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class Task:
    uid: str
    title: str
    subtasks: list["Task"] = field(default_factory=list)  # Forward ref

    @classmethod
    def create(cls, title: str) -> "Task":  # Forward ref for return
        return cls(uid=generate_uid(), title=title)
```

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
    except:
        conn.rollback()
        raise

@asynccontextmanager
async def async_transaction() -> AsyncGenerator[Connection, None]:
    conn = await get_connection()
    try:
        yield conn
        await conn.commit()
    except:
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

SKUEL uses strict MyPy settings. Key options in `pyproject.toml`:

```toml
[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
warn_unused_ignores = true
disallow_untyped_defs = true
```
