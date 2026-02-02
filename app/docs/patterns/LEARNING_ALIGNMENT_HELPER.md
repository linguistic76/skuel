---
title: LearningAlignmentHelper - Unified Learning Integration Pattern
updated: '2026-02-02'
category: patterns
related_skills: []
related_docs: []
---
# LearningAlignmentHelper - Unified Learning Integration Pattern

**Location:** `/core/services/infrastructure/learning_alignment_helper.py`

**Version:** 1.0.0 (Phase 6 - January 2026)

**Status:** ✅ Complete - All 6 Activity Domains integrated

---

## Table of Contents

1. [Overview](#overview)
2. [What It Is](#what-it-is)
3. [What It's Capable Of](#what-its-capable-of)
4. [How It Accomplishes Its Tasks](#how-it-accomplishes-its-tasks)
5. [Core Methods](#core-methods)
6. [Custom Hooks System](#custom-hooks-system)
7. [Domain Integration Examples](#domain-integration-examples)
8. [Usage Patterns](#usage-patterns)
9. [Architecture Benefits](#architecture-benefits)
10. [Migration History](#migration-history)

---

## Overview

The **LearningAlignmentHelper** is a generic infrastructure service that eliminates duplication across all 6 Activity Domain learning services by providing unified implementations of common learning integration patterns.

**The Problem It Solves:**

Before the helper, every domain had identical implementations of learning alignment methods:
- `create_X_with_learning_alignment()` (~65 lines each)
- `get_learning_supporting_X()` (~57 lines each)
- `suggest_learning_aligned_X()` (~72 lines each)
- `assess_X_learning_alignment()` (~55 lines each)

**Total duplication:** ~723 LOC across 6 services

**The Solution:**

Single generic helper that handles the common pattern, reducing each learning service's methods from ~267 LOC → ~12 LOC (95% reduction).

**Impact:**
- ✅ All 6 Activity Domains use the helper
- ✅ ~200+ lines of duplication eliminated
- ✅ Common logic in ONE place
- ✅ Domain-specific customization via hooks
- ✅ No feature loss

---

## What It Is

### Purpose

LearningAlignmentHelper is a **generic, protocol-based infrastructure service** that provides unified implementations for learning path integration across all Activity Domains.

### Key Characteristics

1. **Generic** - Works with any domain model type via TypeScript-style generics: `LearningAlignmentHelper[T, DTO, Request]`
2. **Protocol-based** - Depends on `BackendOperations[T]` protocol, not concrete implementations
3. **Customizable** - Supports 4 optional hooks for domain-specific logic
4. **Extensible** - New capabilities (batch creation, custom fields) added without breaking existing domains
5. **Type-safe** - Full MyPy type checking with generic type variables

### Architecture Position

```
Layer 4: Domain Services (Tasks, Goals, Habits, Events, Choices, Principles)
    ↓ uses
Layer 3: LearningAlignmentHelper (Infrastructure)
    ↓ uses
Layer 2: BaseService (Common service functionality)
    ↓ uses
Layer 1: UniversalNeo4jBackend[T] (Persistence)
```

The helper sits in the **infrastructure layer**, providing reusable patterns for domain services.

---

## What It's Capable Of

### Core Capabilities

| Capability | Method | Description |
|------------|--------|-------------|
| **Entity Creation** | `create_with_learning_alignment()` | Create entity with learning path alignment |
| **Batch Creation** | `create_batch_with_learning_alignment()` | Create multiple entities in batch |
| **Support Filtering** | `get_learning_supporting_entities()` | Get user's entities that support learning |
| **Suggestion Generation** | `suggest_learning_aligned_entities()` | Generate learning-aligned suggestions |
| **Alignment Assessment** | `assess_learning_alignment()` | Assess entity's learning path alignment |
| **Scoring** | `calculate_learning_score()` | Calculate learning alignment score |

### Feature Matrix

| Feature | Description | Domains Using |
|---------|-------------|---------------|
| **Default Implementation** | Generic implementation works out-of-box | Goals, Habits, Choices |
| **Custom Alignment Scoring** | Override scoring algorithm | Principles |
| **Prerequisite Validation** | Validate before creation | Tasks |
| **Embodiment Data** | Merge additional assessment data | Principles |
| **Suggestion Filtering** | Filter generated suggestions | (Available, not yet used) |
| **Custom Fields** | Domain-specific fields in creation | Events |
| **Batch Operations** | Create multiple entities at once | Events |

### Supported Domain Operations

```
┌─────────────────────────────────────────────────────────────┐
│                  LearningAlignmentHelper                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  CREATE                                                     │
│  ├─ Single: create_with_learning_alignment()               │
│  └─ Batch: create_batch_with_learning_alignment()          │
│                                                             │
│  RETRIEVE                                                   │
│  └─ get_learning_supporting_entities()                     │
│                                                             │
│  ANALYZE                                                    │
│  ├─ assess_learning_alignment()                            │
│  └─ calculate_learning_score()                             │
│                                                             │
│  SUGGEST                                                    │
│  └─ suggest_learning_aligned_entities()                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## How It Accomplishes Its Tasks

### 1. Generic Type System

The helper uses Python's generic type variables to work with any domain:

```python
T = TypeVar("T")          # Domain model (Goal, Task, Event, etc.)
DTO = TypeVar("DTO")      # DTO type (GoalDTO, TaskDTO, etc.)
Request = TypeVar("Request")  # Request type (GoalCreateRequest, etc.)

class LearningAlignmentHelper[T, DTO, Request]:
    # Helper is generic over these three types
```

**How it works:**
- Domain service initializes helper with specific types
- Helper uses type parameters for all operations
- MyPy ensures type safety across all domains

**Example:**
```python
# In TasksSchedulingService
self.learning_helper = LearningAlignmentHelper[Task, TaskDTO, TaskCreateRequest](
    service=self,
    # ... configuration ...
)

# Helper now knows:
# - T = Task (domain model)
# - DTO = TaskDTO (transfer object)
# - Request = TaskCreateRequest (creation request)
```

### 2. Protocol-Based Backend Access

The helper doesn't depend on concrete backend implementations - it uses `BaseService` methods:

```python
class LearningAlignmentHelper[T, DTO, Request]:
    def __init__(self, service: BaseService, ...):
        self.service = service
        self.backend = service.backend  # Protocol-based access
```

**How it works:**
- Helper receives a `BaseService` instance
- Accesses backend via service (protocol-based)
- Calls backend methods by name (late binding)
- Uses `BaseService._to_domain_model()` for conversion

**Backend method resolution:**
```python
# Helper stores method names
self.backend_create_method = "create_task"  # Example

# At runtime, resolves to actual method
create_method = getattr(self.backend, self.backend_create_method)

# Calls method with request dict
create_result = await create_method(request_dict)
```

### 3. Learning Position Integration

The helper integrates with SKUEL's learning path system via `LpPosition`:

```python
class LpPosition:
    active_paths: list[LearningPath]           # User's active learning paths
    completed_step_uids: set[str]              # Completed steps
    current_steps: dict[str, LearningStep]     # Current step per path
```

**How it works:**

1. **Entity Creation** - Uses `LpPosition.assess_goal_alignment()` to assess created entity
2. **Scoring** - Checks entity domain/knowledge against active paths
3. **Suggestions** - Generates suggestions based on path steps and outcomes
4. **Assessment** - Builds alignment data from path relationships

**Scoring Algorithm (Default):**
```python
def calculate_learning_score(entity: T, learning_position: LpPosition) -> float:
    score = 0.0

    # Domain alignment: +0.4 if entity domain matches path domain
    if entity.domain == path.domain:
        score += 0.4

    # Knowledge alignment: +0.5 if entity uses path knowledge
    if entity.knowledge_uids ∩ path.knowledge_uids:
        score += 0.5

    # Text alignment: +0.3 if path name in entity text
    if path.name in entity.title or entity.description:
        score += 0.3

    return score  # Range: 0.0-1.5
```

### 4. Custom Hooks System

The helper supports 4 optional hooks for domain-specific customization:

#### Hook 1: `alignment_scorer`
**Purpose:** Override default scoring algorithm

```python
alignment_scorer: Callable[[T, LpPosition], float] | None
```

**When called:** In `calculate_learning_score()` before default algorithm

**Example (Principles):**
```python
def _calculate_virtue_embodiment_score(
    principle: Principle, learning_position: LpPosition
) -> float:
    # Discipline principles: consistency-weighted
    if principle.category in {"personal", "health"}:
        return avg_progress * 0.8

    # Wisdom principles: baseline knowledge valued
    if principle.category in {"intellectual", "professional"}:
        return min(0.9, avg_progress * 0.6 + 0.3)

    return avg_progress * 0.7
```

#### Hook 2: `prerequisite_validator`
**Purpose:** Validate prerequisites before entity creation

```python
prerequisite_validator: Callable[[Request, Any], Result[None]] | None
```

**When called:** In `create_with_learning_alignment()` before backend call

**Example (Tasks):**
```python
async def _validate_task_prerequisites(
    request: TaskCreateRequest, context: UserContext | None
) -> Result[None]:
    if not context:
        return Result.ok(None)

    # Check knowledge prerequisites (O(1) set operations)
    missing_knowledge = set(request.knowledge_uids) - context.completed_ku_uids
    if missing_knowledge:
        return Errors.validation_error(
            f"Missing prerequisite knowledge: {', '.join(missing_knowledge)}"
        )

    return Result.ok(None)
```

#### Hook 3: `suggestion_filter`
**Purpose:** Filter generated suggestions with domain-specific logic

```python
suggestion_filter: Callable[[dict[str, Any], Any], bool] | None
```

**When called:** In `suggest_learning_aligned_entities()` after generation

**Example (Hypothetical - Habits):**
```python
def _filter_habit_suggestions(suggestion: dict, filter_param: Any) -> bool:
    # Only suggest habits with realistic frequency
    frequency = suggestion.get("frequency", "daily")
    return frequency in {"daily", "weekly", "monthly"}
```

#### Hook 4: `embodiment_scorer`
**Purpose:** Add domain-specific data to alignment assessment

```python
embodiment_scorer: Callable[[T, LpPosition], dict[str, Any]] | None
```

**When called:** In `assess_learning_alignment()` after base assessment

**Example (Principles):**
```python
def _calculate_embodiment_data(
    principle: Principle, learning_position: LpPosition
) -> dict[str, Any]:
    score = _calculate_virtue_embodiment_score(principle, learning_position)

    return {
        "virtue_category": principle.category.value,
        "embodiment_depth": score,
        "character_development_stage": (
            "embodied" if score >= 0.7 else
            "practicing" if score >= 0.4 else
            "learning"
        ),
    }
```

### 5. Request Processing Flow

**Complete flow for `create_with_learning_alignment()`:**

```
1. Validate Prerequisites (if hook provided)
   └─ Call prerequisite_validator(request, context)
   └─ Return error if validation fails

2. Prepare Request Dict
   └─ Convert Pydantic request to dict
   └─ Merge custom_fields if provided

3. Create Entity via Backend
   └─ Resolve backend method by name
   └─ Call backend.create_X(request_dict)
   └─ Return error if creation fails

4. Convert to Domain Model
   └─ Use BaseService._to_domain_model()
   └─ Convert DTO → Domain Model

5. Apply Learning Alignment (if LpPosition provided)
   └─ Call learning_position.assess_goal_alignment()
   └─ Log alignment details

6. Return Created Entity
   └─ Result.ok(entity)
```

### 6. Batch Creation Strategy

**How `create_batch_with_learning_alignment()` works:**

```python
async def create_batch_with_learning_alignment(
    requests: list[Request],
    custom_fields_per_request: list[dict] | None
) -> Result[list[T]]:
    # 1. Validate lengths match
    if custom_fields and len(custom_fields) != len(requests):
        return validation_error

    # 2. Create each entity sequentially
    created = []
    for i, request in enumerate(requests):
        custom = custom_fields[i] if custom_fields else None

        # Delegate to single creation method
        result = await create_with_learning_alignment(
            request, learning_position, context, custom
        )

        if result.is_error:
            return result  # Fail fast on first error

        created.append(result.value)

    # 3. Return all created entities
    return Result.ok(created)
```

**Key design decisions:**
- **Sequential creation** - Not parallel (maintains order, easier debugging)
- **Fail-fast** - Returns error on first failure (no partial results)
- **Delegates** - Reuses single creation logic (DRY principle)

---

## Core Methods

### `create_with_learning_alignment()`

**Purpose:** Create entity with learning path alignment

**Signature:**
```python
async def create_with_learning_alignment(
    request: Request,
    learning_position: LpPosition | None = None,
    context: Any = None,
    custom_fields: dict[str, Any] | None = None,
) -> Result[T]
```

**Parameters:**
- `request` - Entity creation request (Pydantic model)
- `learning_position` - User's learning path position (for alignment assessment)
- `context` - Additional context for validators (e.g., UserContext)
- `custom_fields` - Domain-specific fields to merge (e.g., `source_learning_path_uid`)

**Returns:** `Result[T]` containing created domain model

**Usage:**
```python
result = await self.learning_helper.create_with_learning_alignment(
    request=TaskCreateRequest(title="Learn Python", ...),
    learning_position=user_learning_position,
    context=user_context,
)
```

---

### `create_batch_with_learning_alignment()`

**Purpose:** Create multiple entities with learning alignment in batch

**Signature:**
```python
async def create_batch_with_learning_alignment(
    requests: list[Request],
    learning_position: LpPosition | None = None,
    context: Any = None,
    custom_fields_per_request: list[dict[str, Any]] | None = None,
) -> Result[list[T]]
```

**Parameters:**
- `requests` - List of creation requests
- `learning_position` - User's learning path position
- `context` - Additional context for validators
- `custom_fields_per_request` - Optional custom fields per request (must match length)

**Returns:** `Result[list[T]]` containing created entities

**Usage:**
```python
# Create 20 study sessions (4 weeks × 5 sessions)
requests = [EventCreateRequest(...) for _ in range(20)]
custom_fields = [{"source_learning_path_uid": lp_uid} for _ in range(20)]

result = await self.learning_helper.create_batch_with_learning_alignment(
    requests=requests,
    custom_fields_per_request=custom_fields,
)
```

---

### `get_learning_supporting_entities()`

**Purpose:** Get user's entities that support learning progression

**Signature:**
```python
async def get_learning_supporting_entities(
    user_uid: str,
    learning_position: LpPosition,
) -> Result[list[T]]
```

**How it works:**
1. Gets all user's entities from backend
2. Converts to domain models
3. Calculates learning score for each
4. Filters by threshold (score > 0.3)
5. Sorts by knowledge count
6. Returns filtered list

**Returns:** `Result[list[T]]` containing learning-supporting entities

---

### `suggest_learning_aligned_entities()`

**Purpose:** Generate learning-aligned entity suggestions

**Signature:**
```python
async def suggest_learning_aligned_entities(
    learning_position: LpPosition,
    filter_param: Any = None,
    max_suggestions: int = 8,
    custom_suggestions: list[dict[str, Any]] | None = None,
) -> Result[list[dict[str, Any]]]
```

**How it works:**
1. Starts with custom suggestions (if provided)
2. For each active learning path:
   - Suggests mastery-based entity for current step
   - Suggests path completion entity
   - Suggests outcome-based entities
3. Applies custom filter (if hook provided)
4. Sorts by learning_alignment_score
5. Returns top N suggestions

**Suggestion format:**
```python
{
    "title": "Master Python Basics",
    "description": "Achieve mastery in python-basics from Python Learning Path",
    "domain": Domain.TECH,
    "priority": Priority.HIGH,
    "learning_alignment_score": 0.95,
    "supporting_path": "Python Learning Path",
    "suggested_timeline": "5 hours",
    "suggestion_reason": "Current step in Python Learning Path",
}
```

---

### `assess_learning_alignment()`

**Purpose:** Assess entity's alignment with learning paths

**Signature:**
```python
async def assess_learning_alignment(
    entity_uid: str,
    learning_position: LpPosition,
) -> Result[dict[str, Any]]
```

**How it works:**
1. Gets entity from backend
2. Converts to domain model
3. Assesses alignment via learning_position
4. Builds assessment dict
5. Identifies learning milestones
6. Generates recommendations
7. Merges embodiment data (if hook provided)
8. Returns assessment

**Assessment format:**
```python
{
    "entity_uid": "task.learn-python",
    "entity_title": "Learn Python",
    "learning_path_support_score": 0.85,
    "supporting_learning_paths": ["Python Learning Path"],
    "outcome_alignment": [...],
    "recommended_timeline": "2 weeks",
    "prerequisite_steps": ["Install Python", "Setup IDE"],
    "learning_milestones": [...],
    "knowledge_gaps": [...],
    "recommendations": [
        "Task is well-aligned with current learning - proceed with confidence"
    ],
    # If embodiment_scorer hook provided:
    "virtue_category": "intellectual",  # Principles-specific
    "embodiment_depth": 0.75,           # Principles-specific
}
```

---

### `calculate_learning_score()`

**Purpose:** Calculate learning alignment score for an entity

**Signature:**
```python
def calculate_learning_score(
    entity: T,
    learning_position: LpPosition,
) -> float
```

**Default scoring algorithm:**
- Domain alignment: +0.4 per matching path
- Knowledge alignment: +0.5 per matching knowledge unit
- Text alignment: +0.3 per path name match in entity text

**Returns:** Float score (0.0 to infinity, typically 0.0-1.5)

**Custom scoring:** If `alignment_scorer` hook provided, uses that instead

---

## Custom Hooks System

### Overview

The helper supports 4 optional hooks for domain-specific customization without modifying the helper itself.

### Hook Initialization

```python
self.learning_helper = LearningAlignmentHelper[T, DTO, Request](
    service=self,
    backend_get_method="get",
    backend_get_user_method="list_user_tasks",
    backend_create_method="create_task",
    dto_class=TaskDTO,
    model_class=Task,
    domain=Domain.TECH,
    entity_name="task",
    # Optional hooks
    alignment_scorer=custom_scorer_function,           # Override scoring
    prerequisite_validator=validator_function,         # Validate before create
    suggestion_filter=filter_function,                 # Filter suggestions
    embodiment_scorer=embodiment_function,             # Add assessment data
)
```

### Hook Execution Order

```
create_with_learning_alignment():
    1. prerequisite_validator ← Called first (before creation)
    2. Backend creation
    3. (No hooks during creation)
    4. Return entity

calculate_learning_score():
    1. alignment_scorer ← Called instead of default algorithm

suggest_learning_aligned_entities():
    1. Generate default suggestions
    2. Merge custom_suggestions
    3. suggestion_filter ← Called to filter all suggestions

assess_learning_alignment():
    1. Base assessment
    2. embodiment_scorer ← Called to add domain data
```

### Hook Design Patterns

#### Pattern 1: Validator Hook (Fail-Fast)

**Use case:** Validate prerequisites before creation

```python
async def _validate_prerequisites(
    request: Request, context: Any
) -> Result[None]:
    if validation_fails:
        return Errors.validation_error("...")
    return Result.ok(None)  # Success
```

**Characteristics:**
- Returns `Result[None]` (success/failure only)
- Fail-fast - stops creation if returns error
- Receives request + optional context

#### Pattern 2: Scorer Hook (Replace Algorithm)

**Use case:** Domain-specific scoring algorithm

```python
def _custom_scorer(entity: T, learning_position: LpPosition) -> float:
    # Custom calculation
    return score  # 0.0-1.0
```

**Characteristics:**
- Returns float score
- Replaces default algorithm entirely
- Synchronous function (not async)

#### Pattern 3: Filter Hook (Boolean Test)

**Use case:** Filter generated suggestions

```python
def _filter_suggestions(suggestion: dict, filter_param: Any) -> bool:
    return meets_criteria(suggestion)  # True to keep
```

**Characteristics:**
- Returns boolean (True = keep, False = exclude)
- Applied after generation
- Synchronous function

#### Pattern 4: Enrichment Hook (Merge Data)

**Use case:** Add domain-specific assessment data

```python
def _add_embodiment_data(entity: T, learning_position: LpPosition) -> dict[str, Any]:
    return {
        "custom_field_1": value1,
        "custom_field_2": value2,
    }
```

**Characteristics:**
- Returns dict to merge into assessment
- Called after base assessment
- Synchronous function

---

## Domain Integration Examples

### Example 1: Goals (Default - No Hooks)

**Usage:** Simple integration with default behavior

```python
# In GoalsLearningService.__init__
self.learning_helper = LearningAlignmentHelper[Goal, GoalDTO, GoalCreateRequest](
    service=self,
    backend_get_method="get",
    backend_get_user_method="list_user_goals",
    backend_create_method="create_goal",
    dto_class=GoalDTO,
    model_class=Goal,
    domain=Domain.GOALS,
    entity_name="goal",
    # No custom hooks - uses defaults
)

# In create_goal_with_learning_integration()
async def create_goal_with_learning_integration(
    self, goal_request: GoalCreateRequest, learning_position: LpPosition
) -> Result[Goal]:
    return await self.learning_helper.create_with_learning_alignment(
        request=goal_request, learning_position=learning_position
    )
```

**Lines saved:** 65 → 3 (95% reduction)

---

### Example 2: Principles (Custom Scorers)

**Usage:** Custom alignment and embodiment scoring

```python
# Custom scorer functions (outside class)
def _calculate_virtue_embodiment_score(
    principle: Principle, learning_position: LpPosition
) -> float:
    # Discipline: consistency-weighted
    if principle.category in {"personal", "health"}:
        return avg_progress * 0.8
    # Wisdom: baseline knowledge valued
    if principle.category in {"intellectual", "professional"}:
        return min(0.9, avg_progress * 0.6 + 0.3)
    return avg_progress * 0.7

def _calculate_embodiment_data(
    principle: Principle, learning_position: LpPosition
) -> dict[str, Any]:
    score = _calculate_virtue_embodiment_score(principle, learning_position)
    return {
        "virtue_category": principle.category.value,
        "embodiment_depth": score,
        "character_development_stage": (
            "embodied" if score >= 0.7 else "practicing" if score >= 0.4 else "learning"
        ),
    }

# In PrinciplesLearningService.__init__
self.learning_helper = LearningAlignmentHelper[
    Principle, PrincipleDTO, PrincipleCreateRequest
](
    service=self,
    backend_get_method="get",
    backend_get_user_method="list_user_principles",
    backend_create_method="create",
    dto_class=PrincipleDTO,
    model_class=Principle,
    domain=Domain.PRINCIPLES,
    entity_name="principle",
    alignment_scorer=_calculate_virtue_embodiment_score,  # Custom scorer
    embodiment_scorer=_calculate_embodiment_data,         # Custom data
)

# In assess_principle_learning_alignment()
async def assess_principle_learning_alignment(
    self, principle_uid: str, learning_position: LpPosition
) -> Result[dict[str, Any]]:
    return await self.learning_helper.assess_learning_alignment(
        entity_uid=principle_uid, learning_position=learning_position
    )
```

**Lines saved:** 118 → 4 (97% reduction)

**Custom data in result:**
```python
{
    # Standard assessment fields
    "learning_path_support_score": 0.85,
    # Custom Principles fields added via embodiment_scorer
    "virtue_category": "intellectual",
    "embodiment_depth": 0.75,
    "character_development_stage": "practicing",
}
```

---

### Example 3: Tasks (Prerequisite Validator)

**Usage:** Validate prerequisites before creation

```python
# Validator function (outside class)
async def _validate_task_prerequisites(
    request: TaskCreateRequest, context: UserContext | None
) -> Result[None]:
    if not context:
        return Result.ok(None)  # Skip if no context

    # Check knowledge prerequisites (O(1) set operations)
    if request.applies_knowledge_uids:
        missing = set(request.applies_knowledge_uids) - context.completed_ku_uids
        if missing:
            return Errors.validation_error(
                f"Missing prerequisite knowledge: {', '.join(missing)}"
            )

    # Check task prerequisites
    if request.prerequisite_task_uids:
        missing = set(request.prerequisite_task_uids) - context.completed_task_uids
        if missing:
            return Errors.validation_error(
                f"Missing prerequisite tasks: {', '.join(missing)}"
            )

    return Result.ok(None)

# In TasksSchedulingService.__init__
self.learning_helper = LearningAlignmentHelper[Task, TaskDTO, TaskCreateRequest](
    service=self,
    backend_get_method="get",
    backend_get_user_method="list_user_tasks",
    backend_create_method="create_task",
    dto_class=TaskDTO,
    model_class=Task,
    domain=Domain.TECH,
    entity_name="task",
    prerequisite_validator=_validate_task_prerequisites,  # Validator hook
)

# In create_task_with_learning_context()
async def create_task_with_learning_context(
    self,
    task_request: TaskCreateRequest,
    learning_position: LpPosition | None = None,
    context: UserContext | None = None,
) -> Result[Task]:
    return await self.learning_helper.create_with_learning_alignment(
        request=task_request,
        learning_position=learning_position,
        context=context,  # Passed to validator
    )
```

**Lines saved:** 65 → 5 (92% reduction)

**Behavior:**
- If prerequisite validation fails, returns error immediately
- If validation passes, proceeds with creation
- If no context provided, skips validation

---

### Example 4: Events (Custom Fields + Batch)

**Usage:** Domain-specific fields and batch creation

```python
# In EventsLearningService.__init__
self.learning_helper = LearningAlignmentHelper[Event, EventDTO, EventCreateRequest](
    service=self,
    backend_get_method="get",
    backend_get_user_method="list_user_events",
    backend_create_method="create_event",
    dto_class=EventDTO,
    model_class=Event,
    domain=Domain.LEARNING,
    entity_name="event",
    # No hooks needed - uses custom_fields parameter
)

# In create_study_session() - Single creation with custom fields
async def create_study_session(
    self,
    user_uid: str,
    knowledge_uids: list[str],
    event_date: date,
    learning_path_uid: str | None = None,
) -> Result[Event]:
    request = EventCreateRequest(
        user_uid=user_uid,
        title=f"Study Session: {len(knowledge_uids)} topics",
        event_date=event_date,
        status="scheduled",
        event_type="learning",
    )

    # Custom fields for Events domain
    custom_fields = {}
    if learning_path_uid:
        custom_fields["source_learning_path_uid"] = learning_path_uid

    result = await self.learning_helper.create_with_learning_alignment(
        request=request,
        custom_fields=custom_fields or None,
    )

    # GRAPH-NATIVE: Create relationships after entity creation
    if result.is_ok and knowledge_uids:
        for ku_uid in knowledge_uids:
            await self.backend.add_relationship(
                result.value.uid, ku_uid, RelationshipName.PRACTICES_KNOWLEDGE
            )

    return result

# In create_learning_path_schedule() - Batch creation
async def create_learning_path_schedule(
    self,
    user_uid: str,
    learning_path_uid: str,
    study_hours_per_week: int = 5,
) -> Result[list[Event]]:
    # Build 20 study sessions (4 weeks × 5 sessions)
    requests = []
    custom_fields_list = []

    for week in range(4):
        for session in range(study_hours_per_week):
            days_offset = week * 7 + (session * 7 // study_hours_per_week)
            event_date = date.today() + timedelta(days=days_offset)

            request = EventCreateRequest(
                user_uid=user_uid,
                title=f"Learning Path Study - Week {week + 1}",
                event_date=event_date,
                duration_minutes=60,
                status="scheduled",
                event_type="learning",
            )

            custom_fields = {"source_learning_path_uid": learning_path_uid}

            requests.append(request)
            custom_fields_list.append(custom_fields)

    # Create all events in batch
    return await self.learning_helper.create_batch_with_learning_alignment(
        requests=requests,
        custom_fields_per_request=custom_fields_list,
    )
```

**Lines saved:** 133 → 119 (11% reduction, but cleaner structure)

**Features used:**
- `custom_fields` - Merges Events-specific fields
- `create_batch_with_learning_alignment()` - Creates 20 events at once
- Post-creation relationships - GRAPH-NATIVE pattern

---

## Usage Patterns

### Pattern 1: Simple Delegation (Goals, Habits, Choices)

**When to use:** Domain has no special requirements

```python
# Initialization
self.learning_helper = LearningAlignmentHelper[T, DTO, Request](
    service=self,
    # ... standard config ...
)

# Usage
async def create_X_with_learning_alignment(self, request, learning_position):
    return await self.learning_helper.create_with_learning_alignment(
        request=request, learning_position=learning_position
    )
```

**Characteristics:**
- No custom hooks
- Uses default scoring/assessment
- Maximum code reduction

---

### Pattern 2: Custom Scoring (Principles)

**When to use:** Domain needs specialized alignment calculation

```python
# Define scorer function
def _custom_scorer(entity: T, learning_position: LpPosition) -> float:
    # Domain-specific calculation
    return score

# Initialization with hook
self.learning_helper = LearningAlignmentHelper[T, DTO, Request](
    # ... standard config ...
    alignment_scorer=_custom_scorer,
)

# Usage (same as Pattern 1)
async def assess_X_learning_alignment(self, uid, learning_position):
    return await self.learning_helper.assess_learning_alignment(
        entity_uid=uid, learning_position=learning_position
    )
```

**Characteristics:**
- Custom scoring algorithm
- Replaces default calculation
- Assessment includes custom scoring

---

### Pattern 3: Prerequisite Validation (Tasks)

**When to use:** Domain needs validation before creation

```python
# Define async validator
async def _validate_prerequisites(request: Request, context: Any) -> Result[None]:
    if validation_fails:
        return Errors.validation_error("...")
    return Result.ok(None)

# Initialization with hook
self.learning_helper = LearningAlignmentHelper[T, DTO, Request](
    # ... standard config ...
    prerequisite_validator=_validate_prerequisites,
)

# Usage with context
async def create_X_with_learning_context(self, request, learning_position, context):
    return await self.learning_helper.create_with_learning_alignment(
        request=request,
        learning_position=learning_position,
        context=context,  # Passed to validator
    )
```

**Characteristics:**
- Validation before creation
- Fail-fast on validation error
- Context parameter required

---

### Pattern 4: Custom Fields (Events)

**When to use:** Domain has additional fields not in base request

```python
# Usage with custom_fields
async def create_study_session(self, user_uid, learning_path_uid, ...):
    request = EventCreateRequest(...)

    custom_fields = {
        "source_learning_path_uid": learning_path_uid,
        "source_learning_step_uid": step_uid,
    }

    return await self.learning_helper.create_with_learning_alignment(
        request=request,
        custom_fields=custom_fields,
    )
```

**Characteristics:**
- Merges domain-specific fields
- No hook needed (parameter-based)
- Works with batch creation

---

### Pattern 5: Batch Creation (Events)

**When to use:** Creating multiple entities at once

```python
# Build requests and custom fields
requests = [Request(...) for _ in range(N)]
custom_fields = [{"field": value} for _ in range(N)]

# Create batch
result = await self.learning_helper.create_batch_with_learning_alignment(
    requests=requests,
    custom_fields_per_request=custom_fields,
)

if result.is_ok:
    created_entities = result.value  # list[T]
```

**Characteristics:**
- Sequential creation (not parallel)
- Fail-fast on first error
- Validates custom_fields length

---

## Architecture Benefits

### 1. Code Reduction

**Before helper:**
```python
class GoalsLearningService:
    async def create_goal_with_learning_integration(self, ...):  # 65 lines
        # Build DTO manually
        dto = GoalDTO(...)
        # Create via backend
        result = await self.backend.create_goal(dto.to_dict())
        # Convert to domain model
        goal = Goal.from_dto(...)
        # Assess learning alignment
        alignment = learning_position.assess_goal_alignment(...)
        # Log details
        # ...
        return Result.ok(goal)

    # 3 more methods: assess, suggest, support (~200 lines total)
```

**After helper:**
```python
class GoalsLearningService:
    def __init__(self, ...):
        self.learning_helper = LearningAlignmentHelper[...](...) # 10 lines

    async def create_goal_with_learning_integration(self, ...):  # 3 lines
        return await self.learning_helper.create_with_learning_alignment(
            request=goal_request, learning_position=learning_position
        )

    # 3 more methods: each ~3 lines (12 lines total vs 200)
```

**Reduction:** ~188 lines saved per domain × 6 domains = ~1,128 lines eliminated

### 2. Single Source of Truth

**Problem:** Bug in learning alignment logic requires fixing in 6 places

**Solution:** Fix once in helper, all domains benefit

**Example:**
```python
# Before: Fix in 6 files
class GoalsLearningService:
    def calculate_learning_score(...):
        score += 0.4  # BUG: should be 0.5

class HabitsLearningService:
    def calculate_learning_score(...):
        score += 0.4  # BUG: same issue

# ... 4 more domains

# After: Fix in 1 place
class LearningAlignmentHelper:
    def calculate_learning_score(...):
        score += 0.5  # FIXED: all domains updated
```

### 3. Extensibility

**Adding new features doesn't break existing domains:**

```python
# Phase 6: Added batch creation + custom fields
# Old domains (Goals, Habits, Choices): Still work, unchanged
# New domains (Events): Can use new features
```

**Backward compatibility maintained:**
- All parameters optional
- New hooks don't affect existing code
- Default behavior unchanged

### 4. Type Safety

**Generic type system ensures compile-time checking:**

```python
# MyPy catches type errors
helper = LearningAlignmentHelper[Task, GoalDTO, TaskCreateRequest](...)
#                                      ^^^^^^^^ ERROR: DTO doesn't match model type

# Correct
helper = LearningAlignmentHelper[Task, TaskDTO, TaskCreateRequest](...)
#                                      ^^^^^^^ OK: types match
```

### 5. Testability

**Helper tested once, all domains benefit:**

```python
# Test helper with mock types
async def test_create_with_learning_alignment():
    helper = LearningAlignmentHelper[MockEntity, MockDTO, MockRequest](...)
    result = await helper.create_with_learning_alignment(...)
    assert result.is_ok

# All 6 domains inherit tested behavior
```

### 6. Consistency

**All domains use same patterns:**

```python
# User experience: Predictable across domains
await goals_service.create_goal_with_learning_integration(...)
await tasks_service.create_task_with_learning_context(...)
await events_service.create_study_session(...)

# All use same underlying helper
# Same alignment scoring
# Same suggestion format
# Same assessment structure
```

---

## Migration History

### Phase 4 (October 2025) - Initial Implementation

**Domains integrated:** Goals, Habits, Choices (3 of 6)

**Features:**
- `create_with_learning_alignment()`
- `get_learning_supporting_entities()`
- `suggest_learning_aligned_entities()`
- `assess_learning_alignment()`

**Results:**
- ~723 lines eliminated across 3 domains
- Each domain: ~267 LOC → ~12 LOC (95% reduction)

### Phase 6 (January 2026) - Full Integration

**Domains added:** Principles, Tasks, Events (3 more → 6 total)

**New features:**
- Custom hooks system (4 hooks)
- `create_batch_with_learning_alignment()`
- `custom_fields` parameter support

**Results:**
- All 6 Activity Domains using helper
- ~200+ lines eliminated across all migrations
- Batch creation pattern available for all domains

**Domain-specific customizations:**
- Principles: Custom virtue embodiment scoring
- Tasks: Prerequisite validation
- Events: Batch creation + custom fields

---

## See Also

- [Service Consolidation Patterns](/docs/patterns/SERVICE_CONSOLIDATION_PATTERNS.md) - DomainConfig, FacadeDelegationMixin
- [Three-Tier Type System](/docs/patterns/three_tier_type_system.md) - DTO/Domain model conversion
- [Error Handling](/docs/patterns/ERROR_HANDLING.md) - Result[T] pattern
- [Intelligence Services](/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md) - Domain intelligence architecture
- [Protocol Architecture](/docs/patterns/protocol_architecture.md) - Protocol-based dependencies

**ADRs:**
- ADR-025: Service Consolidation Patterns
- ADR-021: UserContext Intelligence Modularization
- ADR-024: BaseAnalyticsService Migration

---

**Last Updated:** January 2026 (Phase 6)

**Status:** ✅ Production - All 6 Activity Domains integrated

**Maintainer:** Infrastructure Team
