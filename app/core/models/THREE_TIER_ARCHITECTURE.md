# Three-Tier Model Architecture

## Overview

Each domain in SKUEL follows a **three-tier model architecture** that separates concerns and maintains clean boundaries:

```
External World → [Tier 1: Pydantic] → [Tier 2: DTOs] → [Tier 3: Domain Models] → Core Logic
```

## The Three Tiers

### Tier 1: Request/Response Models (Pydantic)
- **Location**: `*_request.py` files
- **Purpose**: API boundary validation and serialization
- **Characteristics**:
  - Uses Pydantic BaseModel
  - Handles external data validation
  - Converts to/from JSON
- **Examples**: `TaskCreateRequest`, `EventUpdateRequest`

### Tier 2: Data Transfer Objects (DTOs)
- **Location**: `*_dto.py` files
- **Purpose**: Transfer data between layers
- **Characteristics**:
  - Simple dataclasses
  - Mutable
  - No business logic
- **Examples**: `TaskDTO`, `EventDTO`

### Tier 3: Domain Models (Core)
- **Location**: `*.py` files (e.g., `task.py`, `event.py`)
- **Purpose**: Core business entities with business logic
- **Characteristics**:
  - Frozen dataclasses (`@dataclass(frozen=True)`)
  - Immutable
  - Contains business logic methods
- **Examples**: `Task`, `Event`, `Habit`, `Goal`

## Directory Structure

```
/home/mike/skuel/app/core/models/
├── task/
│   ├── __init__.py
│   ├── task.py            # Tier 3: Domain model
│   ├── task_dto.py        # Tier 2: DTO
│   └── task_request.py    # Tier 1: Request/Response
├── event/
│   ├── __init__.py
│   ├── event.py           # Tier 3: Domain model
│   ├── event_dto.py       # Tier 2: DTO
│   └── event_request.py   # Tier 1: Request/Response
├── habit/
│   ├── __init__.py
│   ├── habit.py           # Tier 3: Domain model
│   ├── habit_dto.py       # Tier 2: DTO
│   └── habit_request.py   # Tier 1: Request/Response
├── goal/
│   ├── __init__.py
│   ├── goal.py            # Tier 3: Domain model
│   ├── goal_dto.py        # Tier 2: DTO
│   └── goal_request.py    # Tier 1: Request/Response
└── shared_enums.py        # Shared enumerations across domains
```

## Import Examples

### Correct Imports
```python
# Import domain model (Tier 3)
from core.models.task.task import Task

# Import DTO (Tier 2)
from core.models.task.task_dto import TaskDTO

# Import request models (Tier 1)
from core.models.task.task_request import TaskCreateRequest, TaskUpdateRequest

# Import shared enums
from core.models.enums import Priority, KuStatus
```

### WRONG Imports (Do NOT use)
```python
# WRONG - These files don't exist anymore
from core.models.task_pure import TaskPure  # ❌
from core.models.task_schemas import TaskCreateSchema  # ❌
```

## Data Flow Example

```python
# 1. API receives data (Tier 1)
request_data = TaskCreateRequest(title="Learn Python", due_date=date.today())

# 2. Convert to DTO for transfer (Tier 2)
task_dto = TaskDTO(
    uid=generate_uid(),
    title=request_data.title,
    due_date=request_data.due_date
)

# 3. Create domain model for business logic (Tier 3)
task = Task(
    uid=task_dto.uid,
    title=task_dto.title,
    due_date=task_dto.due_date
)

# 4. Use business logic
if task.is_overdue():
    # Handle overdue task
    pass
```

## Key Benefits

1. **Separation of Concerns**: Each tier has a specific responsibility
2. **Immutability**: Domain models are frozen, preventing accidental mutations
3. **Type Safety**: Strong typing at each layer
4. **Clean Architecture**: Business logic isolated in domain models
5. **Testability**: Each tier can be tested independently

## Migration Status

### Fully Migrated to Three-Tier
- ✅ Task
- ✅ Event
- ✅ Habit
- ✅ Goal

### Still Using Legacy Structure
- ⏳ Finance (in schemas_legacy/)
- ⏳ Journal (in schemas_legacy/)
- ⏳ Transcription (in schemas_legacy/)

## Important Notes

1. **Never mix tiers**: Don't use Pydantic models in business logic
2. **Always use proper imports**: Import from the correct tier for your use case
3. **Domain models are frozen**: Create new instances instead of mutating
4. **ConversionService**: Handles conversions between tiers
5. **No backwards compatibility**: We use the three-tier system exclusively