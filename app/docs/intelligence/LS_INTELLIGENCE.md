# LsIntelligenceService - Practice Integration & Guidance Assessment

## Overview

**Architecture:** Extends `BaseAnalyticsService[BackendOperations[Ls], Ls]`
**Location:** `/core/services/ls/ls_intelligence_service.py`
**Service Name:** `ls.intelligence`
**Lines:** ~530

---

## Purpose

LsIntelligenceService provides lightweight intelligence for Learning Steps, focusing on practice integration and guidance assessment. It evaluates prerequisite readiness, analyzes practice opportunities across habits/tasks/events, and calculates guidance strength from principles and choices.

**Design Philosophy:** Intentionally lightweight compared to Activity Domain intelligence services - Learning Steps serve as connective tissue between knowledge units and learning paths, emphasizing practice integration over complex analytics.

---

## Core Methods

### Method 1: is_ready()

**Purpose:** Check if learning step is ready based on prerequisite completion. A step is ready when ALL its prerequisite steps (via REQUIRES_STEP relationship) have been completed.

**Signature:**
```python
async def is_ready(
    self,
    ls_uid: str,
    completed_step_uids: set[str]
) -> Result[bool]:
```

**Parameters:**
- `ls_uid` (str) - UID of the learning step
- `completed_step_uids` (set[str]) - Set of completed step UIDs

**Returns:**
```python
Result[bool]  # True if all prerequisites are met
```

**Example:**
```python
# Check if step is ready to learn
completed_steps = {"ls.intro", "ls.syntax"}

result = await ls_service.intelligence.is_ready(
    ls_uid="ls.functions",
    completed_step_uids=completed_steps
)

if result.is_ok and result.value:
    print("Ready to learn functions!")
else:
    print("Prerequisites not yet completed")
```

**Dependencies:**
- Neo4j driver (REQUIRED - uses direct Cypher via GraphQueryExecutor)
- Uses `GraphQueryExecutor.execute()` pattern

**Implementation Notes:**
- Returns `True` if step has no prerequisites (ready by default)
- Checks that ALL prerequisite UIDs are in completed set
- Uses REQUIRES_STEP relationship traversal

---

### Method 2: get_practice_summary()

**Purpose:** Get summary of practice opportunities for a learning step. Counts habits, tasks, and events associated with this step via BUILDS_HABIT, ASSIGNS_TASK, and SCHEDULES_EVENT relationships.

**Signature:**
```python
async def get_practice_summary(
    self,
    ls_uid: str
) -> Result[dict[str, int]]:
```

**Parameters:**
- `ls_uid` (str) - UID of the learning step

**Returns:**
```python
{
    "habits": 2,      # Count of BUILDS_HABIT relationships
    "tasks": 5,       # Count of ASSIGNS_TASK relationships
    "events": 3,      # Count of SCHEDULES_EVENT relationships
    "total": 10       # Sum of all practice opportunities
}
```

**Example:**
```python
result = await ls_service.intelligence.get_practice_summary("ls.functions")

if result.is_ok:
    summary = result.value
    print(f"Practice opportunities:")
    print(f"  Habits: {summary['habits']}")
    print(f"  Tasks: {summary['tasks']}")
    print(f"  Events: {summary['events']}")
    print(f"  Total: {summary['total']} items")
```

**Dependencies:**
- Neo4j driver (REQUIRED - uses direct Cypher via GraphQueryExecutor)
- Uses OPTIONAL MATCH for each practice type

**Implementation Notes:**
- Returns zeros if step has no practice opportunities
- Uses `count(DISTINCT ...)` to avoid double-counting
- Three relationship types: BUILDS_HABIT, ASSIGNS_TASK, SCHEDULES_EVENT

---

### Method 3: practice_completeness_score()

**Purpose:** Calculate practice completeness score (0.0-1.0). Full practice suite (habits + tasks + events) scores 1.0. Each type contributes 1/3 of the score.

**Signature:**
```python
async def practice_completeness_score(
    self,
    ls_uid: str
) -> Result[float]:
```

**Parameters:**
- `ls_uid` (str) - UID of the learning step

**Returns:**
```python
Result[float]  # Score from 0.0 (no practice) to 1.0 (full practice suite)
```

**Scoring Formula:**
```
score = (has_tasks + has_habits + has_events) / 3.0
where each has_* is 1.0 if count > 0, else 0.0
```

**Example:**
```python
result = await ls_service.intelligence.practice_completeness_score("ls.functions")

if result.is_ok:
    score = result.value
    print(f"Practice completeness: {score:.0%}")

    if score < 0.33:
        print("Low practice integration - consider adding activities")
    elif score < 0.67:
        print("Moderate practice - one type missing")
    else:
        print("Excellent practice coverage across all types")
```

**Dependencies:**
- Calls `get_practice_summary()` internally
- Inherits all dependencies from get_practice_summary()

**Implementation Notes:**
- Binary presence (has/doesn't have) - count doesn't affect score
- 0.0 = no practice opportunities
- 0.33 = one type only (tasks OR habits OR events)
- 0.67 = two types (tasks + habits, etc.)
- 1.0 = complete practice suite (all three types)

---

### Method 4: calculate_guidance_strength()

**Purpose:** Calculate how well this step guides the learner (0.0-1.0). Measures values-based guidance from principles and decision-making guidance from choices.

**Signature:**
```python
async def calculate_guidance_strength(
    self,
    ls_uid: str
) -> Result[float]:
```

**Parameters:**
- `ls_uid` (str) - UID of the learning step

**Returns:**
```python
Result[float]  # Guidance strength score from 0.0 (no guidance) to 1.0 (maximum guidance)
```

**Scoring Formula:**
```
Principles: min(0.4, principle_count × 0.15)  # Max 40%
Choices:    min(0.6, choice_count × 0.2)      # Max 60%
Total:      min(1.0, principles + choices)
```

**Example:**
```python
result = await ls_service.intelligence.calculate_guidance_strength("ls.functions")

if result.is_ok:
    strength = result.value
    print(f"Guidance strength: {strength:.0%}")

    if strength < 0.3:
        print("Consider adding principles or choices for better guidance")
    elif strength < 0.7:
        print("Moderate guidance - learner has some direction")
    else:
        print("Strong guidance - learner has clear values and options")
```

**Dependencies:**
- Neo4j driver (REQUIRED - uses direct Cypher via GraphQueryExecutor)
- Uses GUIDED_BY_PRINCIPLE and OFFERS_CHOICE relationships

**Implementation Notes:**
- Principles provide values-based guidance (40% max contribution)
- Choices provide inspiration and decision-making options (60% max)
- Each principle adds up to 15% (capped at 40% total)
- Each choice adds up to 20% (capped at 60% total)
- Final score capped at 1.0

**Guidance Interpretation:**
- 0.0-0.3: Low guidance - learner may feel directionless
- 0.3-0.7: Moderate guidance - some direction provided
- 0.7-1.0: Strong guidance - clear values and options

---

### Method 5: has_prerequisites()

**Purpose:** Check if learning step has any prerequisites. Checks for both REQUIRES_STEP relationships (other steps) and REQUIRES_KNOWLEDGE relationships (KU prerequisites).

**Signature:**
```python
async def has_prerequisites(
    self,
    ls_uid: str
) -> Result[bool]:
```

**Parameters:**
- `ls_uid` (str) - UID of the learning step

**Returns:**
```python
Result[bool]  # True if step has prerequisites
```

**Example:**
```python
result = await ls_service.intelligence.has_prerequisites("ls.functions")

if result.is_ok:
    if result.value:
        print("This step has prerequisites - check readiness before starting")
    else:
        print("No prerequisites - ready to start immediately")
```

**Dependencies:**
- GraphQueryExecutor (REQUIRED - uses `execute_exists()`)
- Checks REQUIRES_STEP OR REQUIRES_KNOWLEDGE relationships

**Implementation Notes:**
- Uses `execute_exists()` pattern for efficient boolean check
- Returns True if EITHER relationship type exists
- Does not count prerequisites - just checks for existence

---

### Method 6: has_guidance()

**Purpose:** Check if learning step has guidance (principles or choices). Quick boolean check for learner support.

**Signature:**
```python
async def has_guidance(
    self,
    ls_uid: str
) -> Result[bool]:
```

**Parameters:**
- `ls_uid` (str) - UID of the learning step

**Returns:**
```python
Result[bool]  # True if step has guidance
```

**Example:**
```python
result = await ls_service.intelligence.has_guidance("ls.functions")

if result.is_ok:
    if result.value:
        print("This step has guidance - principles or choices available")
    else:
        print("No guidance - consider adding principles or choices")
```

**Dependencies:**
- GraphQueryExecutor (REQUIRED - uses `execute_exists()`)
- Checks GUIDED_BY_PRINCIPLE OR OFFERS_CHOICE relationships

**Implementation Notes:**
- Uses `execute_exists()` for efficient boolean check
- Returns True if EITHER relationship type exists
- For detailed guidance analysis, use `calculate_guidance_strength()`

---

### Method 7: has_practice_opportunities()

**Purpose:** Check if learning step has practice opportunities. Checks for any BUILDS_HABIT, ASSIGNS_TASK, or SCHEDULES_EVENT relationships.

**Signature:**
```python
async def has_practice_opportunities(
    self,
    ls_uid: str
) -> Result[bool]:
```

**Parameters:**
- `ls_uid` (str) - UID of the learning step

**Returns:**
```python
Result[bool]  # True if step has practice opportunities
```

**Example:**
```python
result = await ls_service.intelligence.has_practice_opportunities("ls.functions")

if result.is_ok:
    if result.value:
        print("This step has practice opportunities - activities available")
    else:
        print("No practice - consider linking tasks, habits, or events")
```

**Dependencies:**
- GraphQueryExecutor (REQUIRED - uses `execute_exists()`)
- Checks BUILDS_HABIT OR ASSIGNS_TASK OR SCHEDULES_EVENT relationships

**Implementation Notes:**
- Uses `execute_exists()` for efficient boolean check
- Returns True if ANY practice relationship type exists
- For detailed practice analysis, use `get_practice_summary()`

---

## BaseAnalyticsService Features

### Inherited Infrastructure

**Fail-Fast Validation:**
- `_require_graph_intelligence()` - Ensures graph_intel available (not used by LS)
- `_require_relationship_service()` - Ensures relationships available (not used by LS)

**Standard Attributes:**
- `self.backend` - BackendOperations[Ls] (REQUIRED)
- `self.graph_intel` - GraphIntelligenceService (optional, not currently used)
- `self.relationships` - UnifiedRelationshipService (optional, not currently used)
- `self.embeddings` - OpenAIEmbeddingsService (optional, not currently used)
- `self.llm` - LLMService (optional, not currently used)
- `self.event_bus` - EventBus (optional, not currently used)

**Domain-Specific Attributes:**
- `self.executor` - GraphQueryExecutor for direct Cypher queries
- `self.driver` - Neo4j driver from backend

**Logging:**
```python
self.logger.info("Message")  # Logs to: skuel.intelligence.ls.intelligence
```

---

## Integration with LsService

### Facade Access

```python
# LsService creates intelligence internally
ls_service = LsService(
    backend=ls_backend,
    graph_intelligence_service=graph_intelligence,
    relationship_service=relationship_service,
    event_bus=event_bus,
)

# Access via .intelligence attribute
result = await ls_service.intelligence.is_ready(
    ls_uid="ls.functions",
    completed_step_uids={"ls.intro", "ls.syntax"}
)
```

### Typical Usage Pattern

```python
# 1. Check readiness
readiness = await ls_service.intelligence.is_ready(
    ls_uid="ls.functions",
    completed_step_uids=user_completed_steps
)

# 2. Analyze practice integration
practice = await ls_service.intelligence.get_practice_summary("ls.functions")
score = await ls_service.intelligence.practice_completeness_score("ls.functions")

# 3. Evaluate guidance
guidance = await ls_service.intelligence.calculate_guidance_strength("ls.functions")

# 4. Quick boolean checks
has_prereqs = await ls_service.intelligence.has_prerequisites("ls.functions")
has_guidance = await ls_service.intelligence.has_guidance("ls.functions")
has_practice = await ls_service.intelligence.has_practice_opportunities("ls.functions")
```

---

## Domain-Specific Features

### Lightweight by Design

LsIntelligenceService is **intentionally minimal** compared to Activity Domain intelligence:
- **No knowledge generation** - Learning Steps organize existing KU content
- **No behavioral insights** - Steps are structural, not behavioral entities
- **No performance analytics** - Progress tracked at LP/KU level
- **No LLM integration** - All intelligence is graph-based calculation

This reflects Learning Steps' role as **connective tissue** in the curriculum architecture.

### Practice Integration Focus

The primary intelligence focus is **practice integration**:

**Three Practice Types:**
1. **Habits** (BUILDS_HABIT) - Lifestyle integration
2. **Tasks** (ASSIGNS_TASK) - Real-world application
3. **Events** (SCHEDULES_EVENT) - Scheduled practice sessions

**Practice Completeness Scoring:**
- 0.0 = Theory only (no practice)
- 0.33 = Single practice type (limited integration)
- 0.67 = Two practice types (good coverage)
- 1.0 = Complete practice suite (excellent integration)

### Guidance Strength Assessment

**Two Guidance Dimensions:**

1. **Values-Based (40% max)** - GUIDED_BY_PRINCIPLE relationships
   - Provides ethical/philosophical context
   - Helps learner understand "why" to learn
   - Each principle adds up to 15% (capped at 40%)

2. **Decision-Making (60% max)** - OFFERS_CHOICE relationships
   - Provides options and alternatives
   - Helps learner explore different approaches
   - Each choice adds up to 20% (capped at 60%)

**Rationale:** Choices matter more (60%) than principles (40%) because Learning Steps are action-oriented - learners need concrete options more than abstract values.

### Prerequisite Readiness

**Binary Readiness Model:**
- Step is ready when **ALL** prerequisites completed
- Checks both REQUIRES_STEP (other steps) and REQUIRES_KNOWLEDGE (KU)
- No partial readiness - either ready or not ready

This supports LP's sequential progression model.

### Direct Cypher Queries

Unlike Activity Domain intelligence services that use shared utilities, LsIntelligenceService uses **direct Cypher queries** via GraphQueryExecutor:

**Why direct queries?**
- Learning Step queries are domain-specific (practice aggregation, guidance scoring)
- No shared patterns with Activity Domains
- Lightweight service doesn't warrant abstraction overhead

**Pattern:**
```python
# All methods use GraphQueryExecutor
return await self.executor.execute(
    query="MATCH (ls:Ls {uid: $ls_uid})...",
    params={"ls_uid": ls_uid},
    processor=lambda records: ...,
    operation="method_name"
)
```

---

## Testing

### Unit Tests
```bash
poetry run python -m pytest tests/unit/services/test_ls_intelligence_service.py -v
```

### Integration Tests
```bash
# Test with real backend
poetry run python -m pytest tests/integration/intelligence/test_ls_intelligence.py -v

# Test specific method
poetry run python -m pytest tests/integration/intelligence/ -k "test_is_ready" -v
```

### Example Test
```python
from unittest.mock import Mock
from core.services.ls.ls_intelligence_service import LsIntelligenceService

# Create mock backend with driver
backend = Mock()
backend.driver = Mock()

# Instantiate service
service = LsIntelligenceService(backend=backend)

# Verify initialization
assert service._service_name == "ls.intelligence"
assert service.backend == backend
assert service.driver == backend.driver
assert service.executor is not None
```

### Test Practice Completeness Scoring
```python
# Test practice completeness calculation
async def test_practice_completeness_score():
    # Mock get_practice_summary to return specific counts
    service.get_practice_summary = AsyncMock(return_value=Result.ok({
        "habits": 2,
        "tasks": 0,
        "events": 3,
        "total": 5
    }))

    result = await service.practice_completeness_score("ls.test")

    assert result.is_ok
    # Two types (habits + events) = 2/3 = 0.67
    assert result.value == 0.67
```

---

## See Also

- `/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md` - Master index
- `/docs/decisions/ADR-024-base-intelligence-service-migration.md` - BaseAnalyticsService pattern
- `/core/services/base_intelligence_service.py` - Base implementation
- `/core/services/ls/ls_service.py` - LsService facade
- `/core/services/graph_query_executor.py` - GraphQueryExecutor pattern
- `/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md` - Learning Step architecture
