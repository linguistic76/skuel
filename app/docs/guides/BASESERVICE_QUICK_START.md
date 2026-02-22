# BaseService Quick Start Guide

**Purpose:** Get new developers productive with SKUEL's BaseService architecture in <30 minutes.

**Audience:** Developers new to SKUEL's service layer

**Last Updated:** 2026-01-29

---

## TL;DR - 30 Second Summary

SKUEL uses **BaseService** (7 mixins) + **Facade Pattern** (3-11 sub-services) for all Activity Domains.

**For Production:**
```python
from core.services.tasks_service import TasksService  # Import facade
result = await tasks_service.create_task(request, user_uid)  # Auto-delegates to sub-services
```

**For Testing:**
```python
from core.services.tasks import TasksCoreService  # Import sub-service directly
core = TasksCoreService(backend=mock_backend)
```

**Key Concept:** Facades auto-delegate 50+ methods to specialized sub-services. You don't need to know which sub-service handles what - just call the facade method.

---

## Architecture Overview (5 Minutes)

### The Big Picture

SKUEL's service layer has **3 levels**:

```
1. BaseService (7 mixins)          ← Foundation layer
   ├─ ConversionHelpersMixin        ← DTO conversion
   ├─ CrudOperationsMixin           ← CRUD + ownership
   ├─ SearchOperationsMixin         ← Search/filtering
   ├─ RelationshipOperationsMixin   ← Graph relationships
   ├─ TimeQueryMixin                ← Date-based queries
   ├─ UserProgressMixin             ← Progress tracking
   └─ ContextOperationsMixin        ← Graph context

2. Sub-Services (3-11 per domain)  ← Implementation layer
   ├─ CoreService                   ← CRUD operations
   ├─ SearchService                 ← Search/discovery
   ├─ IntelligenceService           ← Analytics
   ├─ RelationshipsService          ← Cross-domain relationships
   └─ Domain-specific services      ← Progress, Scheduling, Planning, etc.

3. Facade (1 per domain)           ← Public API layer
   └─ TasksService                  ← Auto-delegates to sub-services
```

### Key Concepts

**1. BaseService provides 100+ methods via 7 mixins**
- Methods like `create()`, `get()`, `search()`, `verify_ownership()`
- All Activity Domain services extend BaseService

**2. Sub-services specialize in one responsibility**
- CoreService = CRUD
- SearchService = Queries
- IntelligenceService = Analytics

**3. Facades auto-delegate to sub-services**
- FacadeDelegationMixin generates ~50 delegation methods
- Call `tasks_service.create_task()` → delegates to `core.create_task()`

**4. DomainConfig configures BaseService behavior**
- Single source of truth for search fields, date fields, ownership, etc.
- Replaces 18 scattered class attributes

---

## Common Tasks (10 Minutes)

### Task 1: Create a new entity

**Question:** "How do I create a Task?"

**Answer:** Use the facade's create method:

```python
from core.services.tasks_service import TasksService
from core.models.task.task_request import TaskCreateRequest

# In production code (route/service)
tasks_service = services.tasks  # Get from DI container
request = TaskCreateRequest(
    title="Learn BaseService",
    description="Read quick start guide",
    priority="high",
)
result = await tasks_service.create_task(request, user_uid="user.mike")

if result.is_ok:
    task = result.value
    print(f"Created task: {task.uid}")
else:
    error = result.expect_error()
    print(f"Failed: {error.message}")
```

**Behind the scenes:**
1. `tasks_service.create_task()` → delegates to `core.create_task()`
2. `core.create_task()` → validates, converts to domain model, calls backend
3. Backend → saves to Neo4j
4. Event published: `TaskCreated`

---

### Task 2: Search for entities

**Question:** "How do I search for Tasks?"

**Answer:** Use the facade's search method:

```python
# Text search
result = await tasks_service.search("meditation", limit=10)

# Filter by status
from core.models.enums import KuStatus
result = await tasks_service.get_by_status(KuStatus.ACTIVE)

# Filter by category
result = await tasks_service.get_by_category("health")

# Domain-specific query
result = await tasks_service.get_tasks_for_goal(goal_uid="goal.health-2024")
```

**Behind the scenes:**
- `search()` → delegates to `search.search()`
- Uses `DomainConfig.search_fields` to determine which fields to search
- Returns list of domain models (not DTOs)

---

### Task 3: Update an entity

**Question:** "How do I update a Task?"

**Answer:** Use the facade's update method:

```python
result = await tasks_service.update_task(
    uid="task.learn-baseservice",
    updates={"priority": "urgent", "status": "in_progress"},
)
```

**With ownership verification:**
```python
# Ensures user owns the task before updating
result = await tasks_service.update_for_user(
    uid="task.learn-baseservice",
    user_uid="user.mike",
    updates={"priority": "urgent"},
)
# Returns 404 if user doesn't own the task
```

---

### Task 4: Complete an entity

**Question:** "How do I mark a Task as complete?"

**Answer:** Use the domain-specific completion method:

```python
result = await tasks_service.complete_task_with_cascade(
    task_uid="task.learn-baseservice",
    user_context=user_context,  # Rich context for analytics
    actual_minutes=30,
    quality_score=4,
)
```

**Cascade behavior:**
1. Updates Task status to COMPLETED
2. Records completion time and quality
3. Updates UserContext statistics
4. Checks and unblocks dependent tasks
5. Triggers knowledge generation (if configured)
6. Publishes TaskCompleted event

---

### Task 5: Query relationships

**Question:** "How do I find Tasks that require a specific KU?"

**Answer:** Use the relationships service:

```python
result = await tasks_service.get_tasks_applying_knowledge(
    knowledge_uid="ku.graph-databases"
)

# Or use relationships service directly
result = await tasks_service.relationships.find_by_semantic_filter(
    target_uid="ku.graph-databases",
    min_confidence=0.7,
    direction="incoming",
)
```

---

### Task 6: Get analytics

**Question:** "How do I analyze a user's task patterns?"

**Answer:** Use the intelligence service:

```python
# Learning metrics
metrics_result = await tasks_service.analyze_task_learning_metrics(user_uid="user.mike")

# Learning patterns
patterns_result = await tasks_service.analyze_learning_patterns(
    user_uid="user.mike",
    timeframe_days=30,
)

# Knowledge-aware priorities
priorities_result = await tasks_service.calculate_knowledge_aware_priorities(
    user_uid="user.mike"
)
```

**Behind the scenes:**
- Delegates to `intelligence.analyze_task_learning_metrics()`
- Pure Cypher analytics (no AI/LLM dependencies)
- Cross-domain graph analysis

---

## Decision Trees (5 Minutes)

### Decision 1: Which service should I import?

```
Am I writing production code (routes, services)?
├─ YES → Import the FACADE
│  └─ from core.services.tasks_service import TasksService
│
└─ NO → Am I writing unit tests?
    ├─ YES → Import the SUB-SERVICE directly
    │  └─ from core.services.tasks import TasksCoreService
    │
    └─ NO → Am I implementing a new feature?
        └─ Add method to appropriate sub-service (core/search/intelligence)
```

**Why?**
- **Facade:** Provides complete API, auto-delegation, easier to use
- **Sub-service:** Easier to mock in tests, fine-grained control

---

### Decision 2: Which sub-service handles my operation?

```
What do I want to do?
│
├─ Create/Read/Update/Delete?
│  └─ Use: facade method (delegates to core)
│     Example: tasks_service.create_task()
│
├─ Search or filter?
│  └─ Use: facade search method (delegates to search)
│     Example: tasks_service.search("query")
│
├─ Analyze or get insights?
│  └─ Use: facade intelligence method (delegates to intelligence)
│     Example: tasks_service.analyze_task_learning_metrics(user_uid)
│
├─ Complete or track progress?
│  └─ Use: facade progress method (delegates to progress)
│     Example: tasks_service.complete_task_with_cascade(uid, context)
│
└─ Create/query relationships?
   └─ Use: facade relationship method (delegates to relationships)
      Example: tasks_service.link_task_to_knowledge(task_uid, ku_uid)
```

**Key Insight:** You don't need to know which sub-service handles what - just call the facade method!

---

### Decision 3: How do I find available methods?

```
I need to find a method...
│
├─ I know the operation name (e.g., "create task")
│  └─ Use IDE autocomplete: tasks_service.create_<TAB>
│
├─ I want to see all methods
│  ├─ Read: /docs/reference/BASESERVICE_METHOD_INDEX.md
│  └─ Or: Read facade docstring (has full delegation list)
│
├─ I want to understand a specific sub-service
│  └─ Read: /docs/reference/SUB_SERVICE_CATALOG.md
│
└─ I want to see the big picture
   └─ Read: /docs/architecture/SERVICE_TOPOLOGY.md
```

---

## Common Patterns (5 Minutes)

### Pattern 1: Result[T] Error Handling

All service methods return `Result[T]`:

```python
result = await tasks_service.create_task(request, user_uid)

# Check for errors
if result.is_error:
    error = result.expect_error()
    print(f"Failed: {error.message} ({error.code})")
    return

# Extract value
task = result.value
print(f"Success: {task.uid}")
```

**Key methods:**
- `result.is_ok` - Check for success
- `result.is_error` - Check for failure
- `result.value` - Get successful value
- `result.expect_error()` - Get error object

---

### Pattern 2: Ownership Verification

Activity Domains (Tasks, Goals, Habits, etc.) require ownership checks:

```python
# Verify ownership before retrieving
task_result = await tasks_service.verify_ownership(
    uid="task.learn-baseservice",
    user_uid="user.mike",
)
# Returns Task if owned, NotFound error if not owned

# Or use get_for_user (same as verify_ownership)
task_result = await tasks_service.get_for_user(
    uid="task.learn-baseservice",
    user_uid="user.mike",
)
```

**Why?**
- Multi-tenant security: users can only access their own entities
- Returns 404 for entities they don't own (not 403 - prevents enumeration)

**Curriculum domains (KU, LS, LP) don't need ownership checks** - content is shared.

---

### Pattern 3: Graph Context Retrieval

Get entity with full graph context (neighborhood):

```python
result = await tasks_service.get_task_with_context(
    uid="task.learn-baseservice",
    depth=2,  # How many hops to traverse
)

if result.is_ok:
    task, graph_context = result.value
    print(f"Task: {task.title}")
    print(f"Related KUs: {graph_context.knowledge_units}")
    print(f"Related Goals: {graph_context.goals}")
```

**Depth parameter:**
- `depth=1` - Direct neighbors only
- `depth=2` - Neighbors + their neighbors (default)
- `depth=3+` - Deeper traversal (use sparingly - performance impact)

---

### Pattern 4: Factory Pattern for Sub-Services

When implementing a new facade, use the factory:

```python
from core.utils.activity_domain_config import create_common_sub_services

class TasksService(FacadeDelegationMixin, BaseService):
    def __init__(self, backend, ...):
        super().__init__(backend, "tasks")

        # Factory creates 4 common sub-services
        common = create_common_sub_services(
            domain="tasks",
            backend=backend,
            graph_intel=graph_intelligence_service,
            event_bus=event_bus,
        )

        self.core = common.core                # TasksCoreService
        self.search = common.search            # TasksSearchService
        self.relationships = common.relationships  # UnifiedRelationshipService
        self.intelligence = common.intelligence    # TasksIntelligenceService
```

**Eliminates:** ~80 lines of repetitive initialization code

---

## Testing Patterns (5 Minutes)

### Pattern 1: Mock Sub-Services in Tests

```python
import pytest
from unittest.mock import AsyncMock
from core.services.tasks import TasksCoreService
from core.utils.result_simplified import Result

@pytest.fixture
def mock_backend():
    """Mock backend for testing."""
    backend = AsyncMock()
    backend.create.return_value = Result.ok(task)
    return backend

async def test_create_task(mock_backend):
    """Test task creation."""
    core = TasksCoreService(backend=mock_backend)

    result = await core.create_task(request, user_uid="user.test")

    assert result.is_ok
    assert result.value.uid == "task.test"
    mock_backend.create.assert_called_once()
```

---

### Pattern 2: Integration Testing with Real Backend

```python
from core.adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.task.task import Task

@pytest.fixture
async def tasks_core_service(neo4j_driver):
    """Real TasksCoreService with real backend."""
    backend = UniversalNeo4jBackend[Task](
        driver=neo4j_driver,
        entity_label="Task",
        model_class=Task,
    )
    return TasksCoreService(backend=backend)

async def test_task_lifecycle(tasks_core_service):
    """Test full task lifecycle."""
    # Create
    create_result = await tasks_core_service.create_task(request, user_uid)
    task = create_result.value

    # Update
    update_result = await tasks_core_service.update_task(task.uid, {"priority": "high"})

    # Delete
    delete_result = await tasks_core_service.delete_task(task.uid)

    assert all(r.is_ok for r in [create_result, update_result, delete_result])
```

---

## FAQ (5 Minutes)

### Q: Why 7 mixins instead of one big BaseService?

**A:** Single Responsibility Principle + Composability

- Each mixin has ONE focused responsibility
- Easier to understand, test, and maintain
- Services can pick which mixins they need (future flexibility)

---

### Q: Why facades with auto-delegation?

**A:** DRY + Clean Public API

- **Before:** 50+ one-line delegation methods (boilerplate)
- **After:** Declarative `_delegations` dict + auto-generation
- Reduces 1,500 lines of boilerplate across 6 Activity Domains

---

### Q: When should I access sub-services directly?

**A:** Rarely - only for testing or custom composition

**95% of usage:** Call facade methods (auto-delegates)
**5% of usage:** Direct sub-service access (testing, debugging)

---

### Q: How do I add a new method to a domain?

**A:** Add to appropriate sub-service, then add delegation entry

```python
# 1. Add method to sub-service (e.g., TasksCoreService)
async def my_new_method(self, arg: str) -> Result[Task]:
    ...

# 2. Add delegation entry in facade (TasksService)
_delegations = {
    "my_new_method": ("core", "my_new_method"),
}

# 3. Use from facade
result = await tasks_service.my_new_method("value")
```

---

### Q: What's the difference between Intelligence and AI services?

**A:** Intelligence = Pure Cypher analytics, AI = LLM-powered features

**IntelligenceService (BaseAnalyticsService):**
- Pure Cypher graph queries
- No AI/LLM dependencies
- App works without it
- Performance metrics, pattern detection

**AIService (BaseAIService) - OPTIONAL:**
- LLM-powered features
- Embeddings, semantic search
- Content generation
- App works without it (fail-fast if missing)

---

### Q: How do I know which DomainConfig to use?

**A:** Use factory functions for common patterns

```python
# Activity Domains (Tasks, Goals, Habits, Events, Choices, Principles)
from core.services.domain_config import create_activity_domain_config

_config = create_activity_domain_config(
    dto_class=TaskDTO,
    model_class=Task,
    domain_name="tasks",
    date_field="due_date",
    completed_statuses=("completed",),
)

# Curriculum Domains (KU, LS, LP)
from core.services.domain_config import create_curriculum_domain_config

_config = create_curriculum_domain_config(
    dto_class=KuDTO,
    model_class=KnowledgeUnit,
    domain_name="ku",
    search_fields=("title", "content", "description"),
)
```

---

## Protocol-Mixin Compliance (2 Minutes)

**Key Achievement:** 100% protocol-mixin alignment with automated verification.

### The Pattern

Each BaseService mixin has a corresponding protocol:
- `ConversionHelpersMixin` → `ConversionOperations`
- `CrudOperationsMixin` → `CrudOperations`
- `SearchOperationsMixin` → `SearchOperations`
- (and 4 more)

### Automated Verification

**TYPE_CHECKING blocks** ensure protocols match implementations:

```python
# All 7 mixins include this verification pattern
if TYPE_CHECKING:
    from core.ports.base_service_interface import ConversionOperations

    # MyPy verifies signatures match - fails at compile time if they don't
    _protocol_check: type[ConversionOperations[Any]] = ConversionHelpersMixin
```

**How It Works:**
- ✅ Zero runtime cost (only runs during MyPy type checking)
- ✅ Automatic verification (29 tests catch all mismatches)
- ✅ Self-maintaining (tests fail immediately if signatures drift)

### Verification Commands

```bash
# Run protocol compliance tests
poetry run pytest tests/unit/test_protocol_mixin_compliance.py -v
# Expected: 29 passed

# Verify with MyPy
poetry run mypy core/services/mixins/*.py
```

**Result:** No manual synchronization needed - the system enforces correctness automatically.

**See:** `/docs/patterns/protocol_architecture.md` for details

---

## Next Steps

**Congratulations!** You now understand SKUEL's BaseService architecture.

### Recommended Reading Order

1. ✅ **This guide** (you are here)
2. 📖 [Sub-Service Catalog](/docs/reference/SUB_SERVICE_CATALOG.md) - Which service does what
3. 📖 [Method Index](/docs/reference/BASESERVICE_METHOD_INDEX.md) - Complete method listing
4. 📊 [Service Topology](/docs/architecture/SERVICE_TOPOLOGY.md) - Architecture diagrams
5. 📚 [BaseService Source](/core/services/base_service.py) - Implementation details
6. 📚 [FacadeDelegationMixin Source](/core/services/mixins/facade_delegation_mixin.py) - Auto-delegation magic

### Practice Exercise

**Try this:** Create a Goal, link it to a KU, complete it, and analyze the results.

```python
# 1. Create a goal
goal_result = await goals_service.create_goal(
    GoalCreateRequest(title="Learn SKUEL Architecture", target_date=date.today() + timedelta(days=30)),
    user_uid="user.you",
)
goal = goal_result.value

# 2. Link to knowledge
await goals_service.link_goal_to_knowledge(
    goal_uid=goal.uid,
    knowledge_uid="ku.graph-databases",
    knowledge_score_required=0.8,
)

# 3. Complete the goal
await goals_service.complete_goal_with_cascade(
    goal_uid=goal.uid,
    user_context=user_context,
)

# 4. Analyze
metrics_result = await goals_service.analyze_goal_metrics(user_uid="user.you")
print(metrics_result.value)
```

**Expected time:** 10 minutes

---

## Getting Help

- 📖 **Documentation:** `/docs/` directory
- 💬 **Ask:** Questions in team chat
- 🐛 **Issues:** File in GitHub
- 📝 **CLAUDE.md:** Quick reference for AI-assisted development

**Remember:** The facade handles 95% of use cases. Start there, only dive into sub-services when you need fine-grained control.
