# PsIntelligenceService - Practice Integration & Guidance Assessment

## Overview

**Architecture:** Extends `BaseAnalyticsService[BackendOperations[PathStep], PathStep]`
**Location:** `/core/services/ps/ps_intelligence_service.py`
**Service Name:** `ps.intelligence`
**Lines:** ~530

---

## Purpose

PsIntelligenceService provides lightweight intelligence for Path Steps, focusing on practice integration and guidance assessment. It evaluates prerequisite readiness, analyzes practice opportunities across habits/tasks/events, and calculates guidance strength from principles and choices.

**Design Philosophy:** Intentionally lightweight compared to Activity Domain intelligence services - Path Steps serve as connective tissue between knowledge units and learning paths, emphasizing practice integration over complex analytics.

---

## Core Methods

### Method 1: is_ready()

**Purpose:** Check if path step is ready based on prerequisite completion. A step is ready when ALL its prerequisite steps (via REQUIRES_STEP relationship) have been completed.

**Signature:**
```python
async def is_ready(
    self,
    ps_uid: str,
    completed_step_uids: set[str]
) -> Result[bool]:
```

**Parameters:**
- `ps_uid` (str) - UID of the path step
- `completed_step_uids` (set[str]) - Set of completed step UIDs

**Returns:**
```python
Result[bool]  # True if all prerequisites are met
```

**Example:**
```python
# Check if step is ready to learn
completed_steps = {"ls.intro", "ls.syntax"}

result = await ps_service.intelligence.is_ready(
    ps_uid="ls.functions",
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

**Purpose:** Get summary of practice opportunities for a path step. Counts habits, tasks, and events connected to this path step via direct activity domain relationships.

**Signature:**
```python
async def get_practice_summary(
    self,
    ps_uid: str
) -> Result[dict[str, int]]:
```

**Parameters:**
- `ps_uid` (str) - UID of the path step

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
result = await ps_service.intelligence.get_practice_summary("ls.functions")

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
- Six activity domain relationship types: BUILDS_HABIT, ASSIGNS_TASK, SCHEDULES_EVENT, SUPPORTS_GOAL, GUIDED_BY_PRINCIPLE, INFORMS_CHOICE

---

### Method 3: practice_completeness_score()

**Purpose:** Calculate practice completeness score (0.0-1.0). Full practice suite (all 6 activity domains) scores 1.0. Each domain contributes 1/6 of the score.

**Signature:**
```python
async def practice_completeness_score(
    self,
    ps_uid: str
) -> Result[float]:
```

**Parameters:**
- `ps_uid` (str) - UID of the path step

**Returns:**
```python
Result[float]  # Score from 0.0 (no practice) to 1.0 (full practice suite)
```

**Scoring Formula:**
```
domains = ["habits", "tasks", "events", "goals", "principles", "choices"]
present = sum(1.0 for d in domains if summary[d] > 0)
score = present / 6.0
```

**Example:**
```python
result = await ps_service.intelligence.practice_completeness_score("ls.functions")

if result.is_ok:
    score = result.value
    print(f"Practice completeness: {score:.0%}")

    if score < 0.17:
        print("Low practice integration - consider adding activities")
    elif score < 0.5:
        print("Moderate practice - several domains missing")
    else:
        print("Excellent practice coverage across activity domains")
```

**Dependencies:**
- Calls `get_practice_summary()` internally
- Inherits all dependencies from get_practice_summary()

**Implementation Notes:**
- Binary presence (has/doesn't have) - count doesn't affect score
- 0.0 = no practice opportunities
- 0.17 = one domain only
- 0.33 = two domains
- 0.5 = three domains (half coverage)
- 0.83 = five domains
- 1.0 = complete practice suite (all six activity domains)

---

### Method 4: calculate_guidance_strength()

**Purpose:** Calculate how well this step guides the learner (0.0-1.0). Measures values-based guidance from principles and decision-making guidance from choices.

**Signature:**
```python
async def calculate_guidance_strength(
    self,
    ps_uid: str
) -> Result[float]:
```

**Parameters:**
- `ps_uid` (str) - UID of the path step

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
result = await ps_service.intelligence.calculate_guidance_strength("ls.functions")

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
- Uses GUIDED_BY_PRINCIPLE and INFORMS_CHOICE relationships

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

**Purpose:** Check if path step has any prerequisites. Checks for REQUIRES_STEP relationships (other steps) and REQUIRES_KNOWLEDGE {type: 'prerequisite'} relationships (prerequisite knowledge).

**Signature:**
```python
async def has_prerequisites(
    self,
    ps_uid: str
) -> Result[bool]:
```

**Parameters:**
- `ps_uid` (str) - UID of the path step

**Returns:**
```python
Result[bool]  # True if step has prerequisites
```

**Example:**
```python
result = await ps_service.intelligence.has_prerequisites("ls.functions")

if result.is_ok:
    if result.value:
        print("This step has prerequisites - check readiness before starting")
    else:
        print("No prerequisites - ready to start immediately")
```

**Dependencies:**
- GraphQueryExecutor (REQUIRED - uses `execute_exists()`)
- Checks REQUIRES_STEP or REQUIRES_KNOWLEDGE {type: 'prerequisite'} relationships

**Implementation Notes:**
- Uses `execute_exists()` pattern for efficient boolean check
- Returns True if EITHER relationship type exists
- Does not count prerequisites - just checks for existence

---

### Method 6: has_guidance()

**Purpose:** Check if path step has guidance (principles or choices). Quick boolean check for learner support.

**Signature:**
```python
async def has_guidance(
    self,
    ps_uid: str
) -> Result[bool]:
```

**Parameters:**
- `ps_uid` (str) - UID of the path step

**Returns:**
```python
Result[bool]  # True if step has guidance
```

**Example:**
```python
result = await ps_service.intelligence.has_guidance("ls.functions")

if result.is_ok:
    if result.value:
        print("This step has guidance - principles or choices available")
    else:
        print("No guidance - consider adding principles or choices")
```

**Dependencies:**
- GraphQueryExecutor (REQUIRED - uses `execute_exists()`)
- Checks GUIDED_BY_PRINCIPLE or INFORMS_CHOICE relationships

**Implementation Notes:**
- Uses `execute_exists()` for efficient boolean check
- Returns True if EITHER relationship type exists
- For detailed guidance analysis, use `calculate_guidance_strength()`

---

### Method 7: has_practice_opportunities()

**Purpose:** Check if path step has practice opportunities. Checks for any BUILDS_HABIT, ASSIGNS_TASK, or SCHEDULES_EVENT relationships authored directly on the PathStep.

**Signature:**
```python
async def has_practice_opportunities(
    self,
    ps_uid: str
) -> Result[bool]:
```

**Parameters:**
- `ps_uid` (str) - UID of the path step

**Returns:**
```python
Result[bool]  # True if step has practice opportunities
```

**Example:**
```python
result = await ps_service.intelligence.has_practice_opportunities("ls.functions")

if result.is_ok:
    if result.value:
        print("This step has practice opportunities - activities available")
    else:
        print("No practice - consider linking tasks, habits, or events")
```

**Dependencies:**
- GraphQueryExecutor (REQUIRED - uses `execute_exists()`)
- Checks BUILDS_HABIT, ASSIGNS_TASK, or SCHEDULES_EVENT relationships (authored directly on the PathStep)

**Implementation Notes:**
- Uses `execute_exists()` for efficient boolean check
- Returns True if ANY practice relationship type exists
- For detailed practice analysis, use `get_practice_summary()`

---

### Method 8: calculate_user_substance()

**Purpose:** Calculate how much a user has applied the knowledge taught by this PathStep. PathSteps are curriculum entities; their "substance" is derived by analyzing the user's application of the underlying atomic Knowledge Units (via USES_KU).

**Signature:**
```python
async def calculate_user_substance(
    self,
    ps_uid: str,
    user_context: UserContext
) -> Result[dict[str, Any]]:
```

**Parameters:**
- `ps_uid` (str) - UID of the path step
- `user_context` (UserContext) - Context of the user

**Returns:**
```python
Result[dict[str, Any]]  # Aggregated substance metrics
```

**Dependencies:**
- Grabs underlying KU references.
- Uses `_substance_calculator.calculate_aggregate_substance(...)`.

**Implementation Notes:**
- Calculates aggregate substance from related KUs, not from the Step itself.

---

## BaseAnalyticsService Features

### Inherited Infrastructure

**Fail-Fast Validation:**

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

## Integration with PsService

### Facade Access

```python
# PsService creates intelligence internally
ps_service = PsService(
    backend=ps_backend,
    graph_intel=graph_intelligence,
    relationship_service=relationship_service,
    event_bus=event_bus,
)

# Access via .intelligence attribute
result = await ps_service.intelligence.is_ready(
    ps_uid="ls.functions",
    completed_step_uids={"ls.intro", "ls.syntax"}
)
```

### Typical Usage Pattern

```python
# 1. Check readiness
readiness = await ps_service.intelligence.is_ready(
    ps_uid="ls.functions",
    completed_step_uids=user_completed_steps
)

# 2. Analyze practice integration
practice = await ps_service.intelligence.get_practice_summary("ls.functions")
score = await ps_service.intelligence.practice_completeness_score("ls.functions")

# 3. Evaluate guidance
guidance = await ps_service.intelligence.calculate_guidance_strength("ls.functions")

# 4. Quick boolean checks
has_prereqs = await ps_service.intelligence.has_prerequisites("ls.functions")
has_guidance = await ps_service.intelligence.has_guidance("ls.functions")
has_practice = await ps_service.intelligence.has_practice_opportunities("ls.functions")
```

---

## Domain-Specific Features

### Lightweight by Design

PsIntelligenceService is **intentionally minimal** compared to Activity Domain intelligence:
- **No knowledge generation** - Path Steps organize existing KU content
- **No behavioral insights** - Steps are structural, not behavioral entities
- **No performance analytics** - Progress tracked at LP/KU level
- **LLM integration via PsAIService** - AI features are FULL-tier only, separate from analytics (see below)

This reflects Path Steps' role as **connective tissue** in the curriculum architecture. LLM-powered features live in `PsAIService` (FULL tier).

### Practice Integration Focus

The primary intelligence focus is **practice integration**:

**Six Activity Domains (direct relationships on PathStep):**
1. **Habits** (BUILDS_HABIT) - Behaviors to repeat
2. **Tasks** (ASSIGNS_TASK) - Work to complete
3. **Events** (SCHEDULES_EVENT) - Time to commit
4. **Goals** (SUPPORTS_GOAL) - Outcomes to pursue
5. **Principles** (GUIDED_BY_PRINCIPLE) - Values to embody
6. **Choices** (INFORMS_CHOICE) - Decisions to consider

**Practice Completeness Scoring:**
- 0.0 = Theory only (no practice)
- 0.17 = Single domain (limited integration)
- 0.5 = Three domains (half coverage)
- 1.0 = All six domains (complete practice suite)

### Guidance Strength Assessment

**Two Guidance Dimensions:**

1. **Values-Based (40% max)** - GUIDED_BY_PRINCIPLE relationships
   - Provides ethical/philosophical context
   - Helps learner understand "why" to learn
   - Each principle adds up to 15% (capped at 40%)

2. **Decision-Making (60% max)** - INFORMS_CHOICE relationships
   - Provides options and alternatives
   - Helps learner explore different approaches
   - Each choice adds up to 20% (capped at 60%)

**Rationale:** Choices matter more (60%) than principles (40%) because Path Steps are action-oriented - learners need concrete options more than abstract values.

### Prerequisite Readiness

**Binary Readiness Model:**
- Step is ready when **ALL** prerequisites completed
- Checks both REQUIRES_STEP (other steps) and REQUIRES_KNOWLEDGE {type: 'prerequisite'} (KU)
- No partial readiness - either ready or not ready

This supports LP's sequential progression model.

### Direct Cypher Queries

Unlike Activity Domain intelligence services that use shared utilities, PsIntelligenceService uses **direct Cypher queries** via GraphQueryExecutor:

**Why direct queries?**
- Path Step queries are domain-specific (practice aggregation, guidance scoring)
- No shared patterns with Activity Domains
- Lightweight service doesn't warrant abstraction overhead

**Pattern:**
```python
# All methods use GraphQueryExecutor
return await self.executor.execute(
    query="MATCH (ps:PathStep {uid: $ps_uid})...",
    params={"ps_uid": ps_uid},
    processor=lambda records: ...,
    operation="method_name"
)
```

---

## PsAIService (FULL Tier)

**Architecture:** Extends `BaseAIService[PsOperations, PathStep]`
**Location:** `/core/services/ps/ps_ai_service.py`
**Service Name:** `ps.ai`
**Tier:** FULL only (`None` when `INTELLIGENCE_TIER=core`)
**Access:** `ps_service.ai`

PsAIService provides LLM-powered features for PathSteps, separated from graph analytics per ADR-030. All methods require the AI service to be wired (check `ps_service.ai is not None`).

### AI Methods

**`suggest_step_applications(ps_uid)`** → `Result[StepApplicationsResult]`
Suggests how to apply this path step across activity domains. Returns categorized suggestions: tasks (concrete work), habits (behaviors to build), goals (outcomes enabled), and real-world examples.

**`suggest_learning_sequence(ps_uid, max_suggestions=5)`** → `Result[StepLearningSequenceResult]`
Suggests prerequisite steps (what to learn first) and next steps (natural progressions). Each item includes a title and reason. Uses JSON prompts for reliable structured output.

**`search_by_semantic_query(query_text, limit=20, min_score=0.5)`** → `Result[list[PathStep]]`
Embedding similarity across all PathSteps. **FULL tier only** — this is a `.ai` sub-service method, and `.ai` is `None` in CORE, so no CORE caller reaches it. Its keyword fallback fires when the similarity call *errors*, not when the tier is CORE.

**`explain_step(ps_uid, target_level="standard")`** → `Result[str]`
AI explanation at a specific level. `target_level` values: `beginner` (no assumed knowledge), `intermediate` (assumes familiarity), `advanced` (in-depth, connects to broader concepts), `standard` (default), `brief` (2-3 sentences), `detailed` (comprehensive with examples).

**`suggest_practice_activities(ps_uid, num_activities=3)`** → `Result[list[dict[str, str]]]`
Suggests practice activities (name, type, description). Uses JSON prompts for structured output.

**`generate_step_insight(ps_uid)`** → `Result[str]`
Brief encouraging insight about a path step (value + motivation tip).

**`find_similar_steps(ps_uid, limit=5)`** → `Result[list[tuple[str, float]]]`
Finds semantically similar path steps using embedding similarity.

### TypedDicts

```python
from core.ports.query_types import StepApplicationsResult, StepLearningSequenceResult, StepLearningSequenceItem
```

`StepApplicationsResult` — `{ps_uid, ps_title, tasks, habits, goals, real_world_examples}` (each a `list[str]`)
`StepLearningSequenceResult` — `{ps_uid, ps_title, prerequisites, next_steps}` (each a `list[StepLearningSequenceItem]`)
`StepLearningSequenceItem` — `{title, reason}`

### Usage Example

```python
# Only available in FULL tier
if ps_service.ai:
    # Categorized applications across activity domains
    apps = await ps_service.suggest_step_applications(ps_uid)
    # {"tasks": [...], "habits": [...], "goals": [...], "real_world_examples": [...]}

    # Learning sequence
    seq = await ps_service.suggest_learning_sequence(ps_uid, max_suggestions=5)
    # {"prerequisites": [{"title": ..., "reason": ...}], "next_steps": [...]}

    # Semantic search (falls back to keyword on CORE)
    results = await ps_service.search_by_semantic_query("introduction to functions", limit=10)

    # Explanation at a level
    explanation = await ps_service.suggest_step_applications(ps_uid)
    explanation = await ps_service.ai.explain_step(ps_uid, target_level="beginner")
```

---

## Testing

### Unit Tests
```bash
uv run python -m pytest tests/unit/services/test_ps_intelligence_service.py -v
```

### Integration Tests
```bash
# Test with real backend
uv run python -m pytest tests/integration/intelligence/test_ls_intelligence.py -v

# Test specific method
uv run python -m pytest tests/integration/intelligence/ -k "test_is_ready" -v
```

### Example Test
```python
from unittest.mock import Mock
from core.services.ps.ps_intelligence_service import PsIntelligenceService

# Create mock backend with driver
backend = Mock()
backend.driver = Mock()

# Instantiate service
service = PsIntelligenceService(backend=backend)

# Verify initialization
assert service._service_name == "ps.intelligence"
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

    result = await service.practice_completeness_score("ps.test")

    assert result.is_ok
    # Two types (habits + events) = 2/3 = 0.67
    assert result.value == 0.67
```

---

## See Also

- `/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md` - Master index
- `/docs/decisions/ADR-024-base-intelligence-service-migration.md` - BaseAnalyticsService pattern
- `/core/services/base_intelligence_service.py` - Base implementation
- `/core/services/ps/ps_service.py` - PsService facade
- `/core/services/ps/ps_ai_service.py` - PsAIService (FULL tier AI features)
- `/core/services/graph_query_executor.py` - GraphQueryExecutor pattern
- `/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md` - Path Step architecture
