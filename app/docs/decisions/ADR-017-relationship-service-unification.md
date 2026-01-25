---
title: ADR-017: Relationship Service Unification
updated: 2026-01-06
status: current
category: decisions
tags: [adr, decisions, pattern, relationship-services]
related: []
---

# ADR-017: Relationship Service Unification

**Status:** Accepted

**Date:** 2025-12-05

**Decision Type:** Pattern/Practice

---

## Context

**What is the issue we're facing?**

SKUEL's 14 domains each required relationship management for graph traversal, cross-domain connections, and semantic relationships. Initially, this was implemented with 14 separate domain-specific relationship services:

- TasksRelationshipService
- GoalsRelationshipService
- HabitsRelationshipService
- EventsRelationshipService
- ChoicesRelationshipService
- PrinciplesRelationshipService
- JournalRelationshipService
- LpRelationshipService
- LsRelationshipService
- MocRelationshipService
- UserRelationshipService
- AssignmentRelationshipService
- ReportRelationshipService
- FinanceRelationshipService (Finance is NOT an Activity Domain)

**Problems with this approach:**

1. **Code duplication:** ~11,000 lines of code with 80-90% overlap in functionality
2. **Maintenance burden:** Bug fixes and features required updates in 14 places
3. **Inconsistent APIs:** Method names varied across domains (e.g., `get_task_knowledge` vs `get_habit_knowledge`)
4. **Testing overhead:** Each service required separate test coverage

**Constraints:**

- Must maintain backward compatibility during migration
- Some domains have genuinely unique relationship patterns
- Performance must not degrade

---

## Decision

**What is the change we're proposing/making?**

Replace domain-specific relationship services with a **configuration-driven generic service**:

1. **UnifiedRelationshipService** - Single generic service (~1,500 lines)
2. **RelationshipConfig** - Domain-specific configuration objects
3. **Domain Configs** - Pre-defined configurations (TASK_CONFIG, GOAL_CONFIG, etc.)

**Two Patterns by Design:**

| Pattern | Domains | Use Case |
|---------|---------|----------|
| **Config-driven (UnifiedRelationshipService)** | Tasks, Goals, Habits, Events, Choices, Principles | Semantic relationships, entity retrieval, cross-domain intelligence |
| **Direct Driver (domain-specific services retained)** | Journal, LP, LS, MOC, User, Assignment, Report | Simple UID queries, read-heavy traversal, domain-specific complexity |

**Why two patterns?**

The Curriculum (KU, LP, LS), Content/Organization (MOC, Journal, Assignment), and system domains (User, Report) have:
- Simpler relationship patterns (mostly UID lookups)
- Direct Cypher queries that are clearer without abstraction
- No need for the helper-based semantic relationship features

**Implementation:**

```python
# Before: Domain-specific service
tasks_service = TasksRelationshipService(backend, graph_intel)
knowledge_uids = await tasks_service.get_task_knowledge(task_uid)

# After: Unified service with config
from core.services.relationships import UnifiedRelationshipService, TASK_CONFIG

tasks_service = UnifiedRelationshipService(backend, TASK_CONFIG, graph_intel)
knowledge_uids = await tasks_service.get_related_uids("knowledge", task_uid)
```

**Files:**

- `/core/services/relationships/__init__.py` - Module exports
- `/core/services/relationships/unified_relationship_service.py` - Generic service (~1,500 lines)
- `/core/services/relationships/relationship_config.py` - Configuration dataclass
- `/core/services/relationships/domain_configs.py` - Pre-defined configs
- `/core/services/relationships/extended_config.py` - Full specifications

---

## Alternatives Considered

### Alternative 1: Full Abstraction (All Domains)
**Description:** Force all 14 domains through UnifiedRelationshipService

**Pros:**
- Maximum code reduction
- Single mental model

**Cons:**
- Curriculum domains have simpler needs; abstraction adds overhead
- Direct Cypher is clearer for simple lookups
- Forced complexity where none needed

**Why rejected:** Over-engineering for domains with simple relationship patterns

### Alternative 2: Keep All Domain-Specific Services
**Description:** Continue with 14 separate services

**Pros:**
- No migration effort
- Maximum flexibility per domain

**Cons:**
- ~11,000 lines of duplicated code
- Maintenance nightmare
- Bug fixes in 14 places

**Why rejected:** Unsustainable maintenance burden

### Alternative 3: Shared Base Class Inheritance
**Description:** Abstract base class with domain overrides

**Pros:**
- Familiar OOP pattern
- Some code sharing

**Cons:**
- Deep inheritance hierarchies cause coupling
- Less flexible than composition
- Still requires domain-specific class files

**Why rejected:** Composition (config objects) preferred over inheritance

---

## Consequences

### Positive Consequences
- ~90% code reduction (~11,000 → ~1,500 lines for Activity Domains)
- Single point of maintenance for common functionality
- Consistent API across all Activity Domains
- Type-safe configuration with `RelationshipConfig`
- Easier testing (one service, multiple configurations)

### Negative Consequences
- Migration effort required for existing code
- Two mental models (config-driven vs direct driver)
- Slightly more indirection for Activity Domains

### Neutral Consequences
- Curriculum domains retain domain-specific services (intentional)
- Learning curve for understanding configuration objects

### Risks & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Performance regression | Low | Medium | Benchmark before/after; config caching |
| Breaking changes during migration | Medium | Low | Gradual migration; deprecation warnings |
| Confusion about which pattern to use | Low | Low | Clear documentation in module docstrings |

---

## Implementation Details

### Code Location
- Primary file: `/core/services/relationships/unified_relationship_service.py`
- Configuration: `/core/services/relationships/domain_configs.py`
- Module exports: `/core/services/relationships/__init__.py`
- Tests: `/tests/unit/services/relationships/`

### Migration Status (as of 2026-01-06)

| Domain | Pattern | Status |
|--------|---------|--------|
| Tasks | Config-driven | ✅ Complete - old service DELETED |
| Goals | Config-driven | ✅ Complete - old service DELETED |
| Habits | Config-driven | ✅ Complete - old service DELETED |
| Events | Config-driven | ✅ Complete - old service DELETED |
| Choices | Config-driven | ✅ Complete - old service DELETED |
| Principles | Config-driven | ✅ Complete - old service DELETED |
| Journal | Direct Driver | Retained (intentional) |
| LP | Direct Driver | Retained (intentional) |
| LS | Direct Driver | Retained (intentional) |
| MOC | Direct Driver | Retained (intentional) |
| User | Direct Driver | Retained (intentional) |
| Assignment | Direct Driver | Retained (intentional) |
| Report | Direct Driver | Retained (intentional) |

**Import Cleanup (January 2026):**
- Removed all TYPE_CHECKING imports of deleted services from:
  - `core/services/user/intelligence/core.py`
  - `core/services/user/intelligence/factory.py`
  - `core/services/tasks/tasks_planning_service.py`
  - `core/services/tasks/tasks_analytics_service.py`
  - `core/services/ku_analytics_engine.py`
  - `core/services/goals/goals_learning_service.py`
  - `core/services/goals/goals_progress_service.py`
  - `core/services/events/events_learning_service.py`

**Full API Migration (January 2026 - COMPLETE):**
All services now use `UnifiedRelationshipService` type hints (no `Any`):

| File | Migration Pattern |
|------|-------------------|
| `tasks_planning_service.py` | Generic API + Direct Cypher helpers |
| `tasks_analytics_service.py` | Already using UnifiedRelationshipService |
| `events_learning_service.py` | Direct Cypher for reverse queries |
| `goals_learning_service.py` | Already using UnifiedRelationshipService |
| `goals_progress_service.py` | Already using UnifiedRelationshipService |

**Migration Patterns Used:**
1. **Generic API** (`get_related_uids`): Simple relationship→UIDs queries
2. **UID→Entity conversion**: `get_related_uids()` + `backend.get_many()` for domain objects
3. **Direct Cypher**: Reverse/cross-domain queries (e.g., find Tasks pointing TO a KU)

### Available Domain Configs

```python
from core.services.relationships import (
    TASK_CONFIG,
    GOAL_CONFIG,
    HABIT_CONFIG,
    EVENT_CONFIG,
    CHOICE_CONFIG,
    PRINCIPLE_CONFIG,
    ACTIVITY_DOMAIN_CONFIGS,  # Registry of all configs
    get_config_for_domain,     # Lookup by domain name
)
```

---

## Future Considerations

### When to Revisit
- If Curriculum domains need semantic relationship features
- If performance becomes a concern (unlikely with config caching)
- If Neo4j 5.x introduces new relationship patterns

### Evolution Path
1. Current: Two patterns coexist (config-driven + direct driver)
2. Future: May consolidate if Curriculum needs grow
3. Long-term: Config system may extend to other service types

---

## Changelog

| Date | Author | Change | Version |
|------|--------|--------|---------|
| 2025-12-03 | Development | Implementation complete | 2.0.0 |
| 2025-12-05 | Claude | ADR created to document decision | 1.0 |
| 2026-01-06 | Claude | Import cleanup - removed all references to deleted services, MyPy clean | 2.1.0 |
| 2026-01-06 | Claude | Full API migration complete - all services type-safe, no `Any` hints | 2.2.0 |
