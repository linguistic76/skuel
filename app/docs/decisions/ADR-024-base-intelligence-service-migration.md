---
title: ADR-024: BaseIntelligenceService Migration (now BaseAnalyticsService)
updated: 2026-01-19
status: accepted
category: decisions
tags: [adr, decisions, intelligence-services, base-class, facade-pattern, intelligence-operations-protocol, analytics, ai-separation]
related: [ADR-023-curriculum-baseservice-migration.md, ADR-021-user-context-intelligence-modularization.md, ADR-030-dual-track-assessment-pattern.md]
---

# ADR-024: BaseIntelligenceService Migration (now BaseAnalyticsService)

**Status:** Accepted (Architecture Update January 18, 2026)

**Date:** 2026-01-06 (Initial), 2026-01-08 (Extended to Curriculum Domains), 2026-01-17 (IntelligenceOperations Protocol), 2026-01-18 (Analytics/AI Separation), 2026-01-19 (Naming Convention Documented)

---

## Architecture Update (January 18, 2026)

**`BaseIntelligenceService` has been replaced by two separate base classes:**

| Base Class | Purpose | AI Dependencies |
|------------|---------|-----------------|
| **`BaseAnalyticsService`** | Graph-based analytics | NO (app runs without LLM) |
| **`BaseAIService`** | AI-powered features | YES (LLM, embeddings) |

**Key Changes:**
- All 10 domain intelligence services now extend `BaseAnalyticsService` (not `BaseIntelligenceService`)
- `BaseAnalyticsService` explicitly has NO `embeddings` or `llm` attributes
- `BaseAIService` exists for optional AI-powered features (semantic search, AI insights)
- Logger prefix changed: `skuel.analytics.{service_name}` (was `skuel.intelligence.{service_name}`)

**Files:**
- `/core/services/base_analytics_service.py` - Graph analytics (NO AI deps)
- `/core/services/base_ai_service.py` - AI features (optional)
- `/core/services/base_intelligence_service.py` - DELETED

**See:** ADR-030 for dual-track assessment pattern (extends `BaseAnalyticsService`)

### File Naming Convention (Intelligence vs Analytics)

**Why `*_intelligence_service.py` not `*_analytics_service.py`?**

The naming reflects a semantic distinction:
- **File name** = User-facing capability (what it provides)
- **Base class** = Implementation detail (how it's built)

| Layer | File Pattern | Base Class | Rationale |
|-------|-------------|-----------|-----------|
| **Intelligence** | `*_intelligence_service.py` | `BaseAnalyticsService` | "Intelligence" = insights + recommendations + analysis |
| **AI** | `*_ai_service.py` | `BaseAIService` | "AI" = LLM-powered semantic features |

**The convention:**
- `*IntelligenceService` = Graph analytics (NO AI) - the critical path
- `*AIService` = LLM/embeddings features (OPTIONAL) - the enhancement layer

All 10 domain intelligence services correctly extend `BaseAnalyticsService` - the name "Intelligence" describes what users get (actionable insights), while `BaseAnalyticsService` describes how it's implemented (graph queries + Python).

---

**Decision Type:** Pattern/Practice

**Related ADRs:**
- ADR-023: Curriculum BaseService Migration (similar base class pattern)
- ADR-021: UserContextIntelligence Modularization (central intelligence hub)

---

## Context

**What was the issue?**

Nine intelligence services (6 Activity + 2 Curriculum Domains + LS) had repetitive initialization code:
- Logger setup with hierarchical naming
- Backend/graph_intel/relationships attribute assignment
- Fail-fast validation for required dependencies
- Domain model conversion helpers

Each service duplicated ~15-20 lines of boilerplate initialization.

**Initial Services Affected (2026-01-06):**
- `TasksIntelligenceService`
- `GoalsIntelligenceService`
- `HabitsIntelligenceService`
- `EventsIntelligenceService`
- `ChoicesIntelligenceService`
- `PrinciplesIntelligenceService`

**Extended to Curriculum Domains (2026-01-08):**
- `KuIntelligenceService`
- `LsIntelligenceService` (already using BaseIntelligenceService)
- `LpIntelligenceService` (facade pattern with BaseIntelligenceService)

---

## Decision

**Create `BaseIntelligenceService[B, T]` generic base class to standardize intelligence service initialization.**

### Implementation

**New Base Class:** `core/services/base_intelligence_service.py`

```python
class BaseIntelligenceService(Generic[B, T]):
    """
    Base class for domain intelligence services.

    Provides:
    - Standardized initialization for common attributes
    - Logger setup with hierarchical naming
    - Fail-fast validation for required dependencies
    """

    # Class attributes for configuration
    _service_name: ClassVar[str] = "intelligence"  # Override for logger name
    _require_relationships: ClassVar[bool] = False  # If True, fail if relationships not provided

    def __init__(
        self,
        backend: B,
        graph_intelligence_service=None,
        relationship_service=None,
        embeddings_service=None,
        llm_service=None,
    ) -> None:
        self.backend = backend
        self.graph_intel = graph_intelligence_service
        self.relationships = relationship_service
        self.embeddings = embeddings_service
        self.llm = llm_service
        self.logger = get_logger(f"skuel.services.{self._service_name}")

        # Fail-fast validation
        if self._require_relationships and not relationship_service:
            raise ValueError(f"{self._service_name} requires relationship_service")
```

**Helper Methods:**
- `_require_graph_intelligence()` - Fail-fast guard for graph_intel
- `_require_relationship_service()` - Fail-fast guard for relationships
- `_to_domain_model(dto_or_dict, dto_class, model_class)` - DTO/dict conversion

### Migration Pattern

Each intelligence service now inherits from the base class:

```python
class TasksIntelligenceService(BaseIntelligenceService[TasksOperations, Task]):
    _service_name = "tasks.intelligence"

    def __init__(
        self,
        backend: TasksOperations,
        graph_intelligence_service=None,
        relationship_service=None,
        embeddings_service=None,
        llm_service=None,
    ) -> None:
        super().__init__(
            backend=backend,
            graph_intelligence_service=graph_intelligence_service,
            relationship_service=relationship_service,
            embeddings_service=embeddings_service,
            llm_service=llm_service,
        )
        # Domain-specific initialization only
```

---

## Services Migrated

### Activity Domains (2026-01-06)

| Service | File | Lines Saved | Notes |
|---------|------|-------------|-------|
| HabitsIntelligenceService | `habits/habits_intelligence_service.py` | ~20 | `_require_relationships = True` |
| PrinciplesIntelligenceService | `principles/principles_intelligence_service.py` | ~15 | Standard migration |
| GoalsIntelligenceService | `goals/goals_intelligence_service.py` | ~15 | Has domain-specific `progress_service` |
| EventsIntelligenceService | `events/events_intelligence_service.py` | ~12 | Standard migration |
| ChoicesIntelligenceService | `choices/choices_intelligence_service.py` | ~10 | Has domain-specific `path_helper` |
| TasksIntelligenceService | `tasks/tasks_intelligence_service.py` | ~20 | Required attribute rename: `self.graph` → `self.graph_intel` |

**Activity Domain Lines Saved:** ~92 lines

### Curriculum Domains (2026-01-08)

| Service | File | Lines Saved | Notes |
|---------|------|-------------|-------|
| KuIntelligenceService | `ku_intelligence_service.py` | ~18 | Standard migration, KuService creates intelligence internally |
| LsIntelligenceService | `ls/ls_intelligence_service.py` | N/A | Already extended BaseIntelligenceService (2026-01-06) |
| LpIntelligenceService | `lp_intelligence_service.py` | ~22 | Facade pattern, maintains backward compatibility with LP-specific parameters |

**Curriculum Domain Lines Saved:** ~40 lines

**Total Lines Saved:** ~132 lines across 9 services

---

## Facade Factory Extraction (Companion Work)

As part of this consolidation, created `core/utils/activity_domain_config.py` with:

1. **`ActivityDomainConfig`** - Dataclass holding domain configuration
2. **`ACTIVITY_DOMAIN_CONFIGS`** - Registry of all 6 domain configurations
3. **`create_common_sub_services()`** - Factory function creating 4 common sub-services

```python
common = create_common_sub_services(
    domain="events",
    backend=backend,
    graph_intel=graph_intelligence_service,
    event_bus=event_bus,
)
self.core = common.core
self.search = common.search
self.relationships = common.relationships
self.intelligence = common.intelligence
```

**Facades Updated:**
- EventsService, ChoicesService, HabitsService, PrinciplesService - Full factory usage
- GoalsService - Factory + manual intelligence (needs `progress_service`)
- TasksService - Factory for search/relationships + manual core/intelligence

---

## Curriculum Domain Extension (2026-01-08)

**Goal:** Unify all intelligence services under BaseIntelligenceService pattern, extending beyond Activity Domains to Curriculum Domains.

### KuIntelligenceService Migration

**Before:**
```python
class KuIntelligenceService:
    def __init__(self, backend, graph_intelligence_service, ...):
        self.backend = backend
        self.graph = graph_intelligence_service  # ❌ Inconsistent naming
        self.logger = get_logger(__name__)  # ❌ Non-hierarchical
```

**After:**
```python
class KuIntelligenceService(BaseIntelligenceService[KuOperations, Ku]):
    _service_name = "ku.intelligence"

    def __init__(self, backend, graph_intelligence_service, ...):
        super().__init__(
            backend=backend,
            graph_intelligence_service=graph_intelligence_service,
            relationship_service=relationship_service,
            embeddings_service=embeddings_service,
            llm_service=llm_service,
        )
```

**Changes:**
- Updated method calls: `self.graph` → `self.graph_intel` (3 occurrences)
- Added `_require_graph_intelligence()` validation
- KuService now creates intelligence internally (not passed from bootstrap)
- Removed duplicate intelligence creation in services_bootstrap.py

### LpIntelligenceService Migration

**Unique Architecture:** LpIntelligenceService is a **facade** coordinating 4 sub-services:
- LearningStateAnalyzer (557 lines)
- LearningRecommendationEngine (862 lines)
- ContentAnalyzer (383 lines)
- ContentQualityAssessor (442 lines)

**Before:**
```python
class LpIntelligenceService:
    def __init__(self, progress_backend, learning_backend, embeddings_service, ...):
        self.progress_backend = progress_backend
        self.learning_backend = learning_backend
        self.logger = get_logger(__name__)  # ❌ Non-hierarchical
```

**After:**
```python
class LpIntelligenceService(BaseIntelligenceService[Any, Lp]):
    _service_name = "lp.intelligence"

    def __init__(
        self,
        backend: Any | None = None,  # NEW - BaseIntelligenceService parameter
        graph_intelligence_service: Any | None = None,
        relationship_service: Any | None = None,
        embeddings_service: OpenAIEmbeddingsService | None = None,
        llm_service: Any | None = None,
        # LP-specific dependencies
        progress_backend: Any | None = None,
        learning_backend: Any | None = None,
        vectors_backend: Any | None = None,
        ku_service: Any | None = None,
        event_bus: Any | None = None,
        user_service: Any | None = None,
    ):
        # Map learning_backend to backend for backward compatibility
        primary_backend = backend if backend is not None else learning_backend

        # Initialize BaseIntelligenceService
        super().__init__(
            backend=primary_backend,
            graph_intelligence_service=graph_intelligence_service,
            relationship_service=relationship_service,
            embeddings_service=embeddings_service,
            llm_service=llm_service,
            event_bus=event_bus,
        )

        # Store LP-specific dependencies
        self.progress_backend = progress_backend
        self.learning_backend = learning_backend or primary_backend
        self.vectors = vectors_backend
        self.ku_service = ku_service
        self.user_service = user_service

        # Initialize 4 sub-services (unchanged)
```

**Key Design Decisions:**
- **Backward compatibility:** Accepts both `backend` (new) and `learning_backend` (old) parameters
- **Standalone service:** NOT created by LpService facade (unlike KuService)
- **Facade pattern preserved:** Zero business logic, pure delegation to 4 sub-services
- **Multiple backends:** Has `progress_backend`, `learning_backend`, and `vectors_backend`

### Documentation

Created comprehensive intelligence service documentation (January 2026):
- 10 individual intelligence service guides (one per service)
- Master index: `/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md`
- Complete coverage: 6 Activity + 3 Curriculum + 1 Meta (UserContext)

---

## Consequences

### Positive

- **~132 lines of duplicate code eliminated** across 9 intelligence services (6 Activity + 2 Curriculum)
- **Complete architecture unification** - All 9 domain intelligence services now extend BaseIntelligenceService
- **Consistent initialization pattern** - All services follow same structure
- **Standardized logging** with hierarchical names (e.g., `skuel.services.tasks.intelligence`, `skuel.services.ku.intelligence`)
- **Fail-fast validation** built into base class via `_require_relationships`
- **Easier testing** - Mock base class behavior once
- **Clear extension points** - Domain-specific code clearly separated from boilerplate
- **Comprehensive documentation** - 10 intelligence service guides + master index (January 2026)

### Negative

- **Additional abstraction layer** - Developers must understand base class
- **Some services still need domain-specific parameters:**
  - GoalsIntelligenceService needs `progress_service`
  - LpIntelligenceService needs multiple backends (`progress_backend`, `learning_backend`, `vectors_backend`)
- **Backward compatibility overhead** - LpIntelligenceService dual parameter support (`backend` + `learning_backend`)

### Neutral

- **Type variance** - Generic `[B, T]` parameters provide type safety without runtime overhead
- **Migration effort** - One-time effort, low risk due to clear pattern
- **Facade patterns vary** - KuService creates intelligence internally; LpIntelligenceService remains standalone

---

## Related Files

| File | Purpose |
|------|---------|
| `core/services/base_analytics_service.py` | Base class for graph analytics (NO AI deps) |
| `core/services/base_ai_service.py` | Base class for AI features (optional) |
| `core/services/base_intelligence_service.py` | **DELETED** - replaced by above two classes |
| `core/utils/activity_domain_config.py` | Domain registry + factory |
| `core/services/{domain}/{domain}_intelligence_service.py` | Migrated services (extend BaseAnalyticsService) |

---

## Test Results

### Activity Domain Migration (2026-01-06)
- **Before:** 646 passed, 34 errors
- **After:** 678 passed, 2 errors (+32 passing tests, -32 errors)

### Curriculum Domain Extension (2026-01-08)
- All existing tests passing
- KuIntelligenceService: Inheritance verified, instantiation successful
- LpIntelligenceService: Inheritance verified, 4 sub-services created, backward compatibility maintained

### Final State
- **10 services extending BaseIntelligenceService** (6 Activity + 4 Curriculum)
- **1 modular package** (UserContext - different architecture per ADR-021)
- **11 comprehensive documentation guides** + master index
- **Zero breaking changes** to existing code

---

## IntelligenceOperations Protocol Extension (2026-01-17)

**Goal:** Standardize intelligence API across all domain services via the `IntelligenceOperations` protocol, enabling automatic route generation via `IntelligenceRouteFactory`.

### Protocol Definition

All 10 domain intelligence services now implement three standardized methods:

```python
class IntelligenceOperations(Protocol[T]):
    async def get_with_context(
        self, uid: str, depth: int = 2
    ) -> Result[tuple[T, GraphContext]]:
        """Entity with full graph neighborhood."""
        ...

    async def get_performance_analytics(
        self, user_uid: str, period_days: int = 30
    ) -> Result[dict[str, Any]]:
        """User-specific analytics (or overall stats for shared content)."""
        ...

    async def get_domain_insights(
        self, uid: str, min_confidence: float = 0.7
    ) -> Result[dict[str, Any]]:
        """Domain-specific intelligence and recommendations."""
        ...
```

### Implementation Pattern

Each service uses `GraphContextOrchestrator` for the `get_with_context` method:

```python
# Initialize orchestrator in __init__
if graph_intelligence_service:
    self.orchestrator = GraphContextOrchestrator[Task, TaskDTO](
        service=self,
        backend_get_method="get",
        dto_class=TaskDTO,
        model_class=Task,
        domain=Domain.TASKS,
    )

# Protocol method delegates to orchestrator
async def get_with_context(self, uid: str, depth: int = 2) -> Result[tuple[Task, GraphContext]]:
    if not hasattr(self, "orchestrator"):
        return Result.fail(Errors.system(message="Graph intelligence service required"))
    return await self.orchestrator.get_with_context(uid=uid, depth=depth)
```

### Bug Fixes Applied

| Bug | Location | Fix |
|-----|----------|-----|
| SUCCESS_RATE UNIT INCONSISTENCY | `goals_intelligence_service.py` | Habit.success_rate is 0.0-1.0, not 0-100 (4 fixes) |
| Missing `is_on_track()` | `goal.py` | Added method to check progress vs. expected |
| Unguarded `self.progress` calls | `goals_intelligence_service.py` | Added fail-fast guard |
| `period_days` ignored | `goals_intelligence_service.py` | Added TODO documentation |
| Logging emoji | `intelligence_route_factory.py` | Removed for consistency |

### Rollout Status

| Service | Protocol Methods | Orchestrator | Status |
|---------|------------------|--------------|--------|
| TasksIntelligenceService | ✅ | ✅ | Complete |
| GoalsIntelligenceService | ✅ | ✅ (pilot) | Complete |
| HabitsIntelligenceService | ✅ | ✅ | Complete |
| EventsIntelligenceService | ✅ | ✅ | Complete |
| ChoicesIntelligenceService | ✅ | ✅ | Complete |
| PrinciplesIntelligenceService | ✅ | ✅ | Complete |
| KuIntelligenceService | ✅ | ✅ | Complete |
| LsIntelligenceService | ✅ | ✅ | Complete |
| LpIntelligenceService | ✅ | ✅ | Complete |
| MocIntelligenceService | ✅ | ✅ | Complete |

### Routes Generated

`IntelligenceRouteFactory` automatically generates routes for each domain:
- `GET /api/{domain}/context?uid=...&depth=2`
- `GET /api/{domain}/analytics?user_uid=...&period_days=30`
- `GET /api/{domain}/insights?uid=...&min_confidence=0.7`

### Test Results (2026-01-17)

- **Intelligence Route Factory:** 12/12 tests passing
- **Intelligence Services:** 108/108 tests passing
- **Goal-related:** 111/111 tests passing
