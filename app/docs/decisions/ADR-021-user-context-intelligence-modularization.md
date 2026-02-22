---
title: ADR-021: User Context Intelligence Modularization
updated: 2026-01-04
status: current
category: decisions
tags: [adr, architecture, refactoring, separation-of-concerns, one-path-forward]
related: [ADR-016]
---

# ADR-021: User Context Intelligence Modularization

**Status:** Accepted

**Date:** January 4, 2026

**Decision Type:** Pattern/Practice

---

## Context

**What is the issue we're facing?**

The `user_context_intelligence.py` file had grown to 2,703 lines with 8 distinct method groups:
- Learning intelligence (Methods 1-4)
- Daily planning (Method 5 - THE FLAGSHIP)
- Cross-domain synergies (Method 6)
- Life path alignment (Method 7)
- Schedule-aware recommendations (Method 8)
- Graph-native intelligence methods
- Data classes (return types)
- Factory class

**Constraints:**
- Follow SKUEL's "One Path Forward" principle (no backwards compatibility)
- Maintain all 8 core intelligence methods
- Keep mixin architecture for clean composition
- Update all import sites immediately

---

## Decision

**Decompose into modular package using mixin architecture:**

```
core/services/user/intelligence/
├── __init__.py                      (95 lines)  - Package exports
├── types.py                         (205 lines) - Data classes
├── learning_intelligence.py         (445 lines) - Methods 1-4
├── life_path_intelligence.py        (429 lines) - Method 7
├── synergy_intelligence.py          (382 lines) - Method 6
├── schedule_intelligence.py         (469 lines) - Method 8
├── daily_planning.py                (254 lines) - Method 5 (THE FLAGSHIP)
├── graph_native.py                  (366 lines) - Context-based intelligence
├── core.py                          (245 lines) - Main class (composes mixins)
└── factory.py                       (234 lines) - Factory class
```

**Mixin Architecture:**

```python
class UserContextIntelligence(
    LearningIntelligenceMixin,      # Methods 1-4
    LifePathIntelligenceMixin,      # Method 7
    SynergyIntelligenceMixin,       # Method 6
    ScheduleIntelligenceMixin,      # Method 8
    DailyPlanningMixin,             # Method 5
    GraphNativeMixin,               # Graph-native methods
):
    """Main intelligence class - composes all mixins."""

    def __init__(self, context, tasks, goals, habits, ...):
        # Store all 13 domain services
        self.context = context
        self.tasks = tasks
        # ... etc
```

---

## One Path Forward

**Following SKUEL principles, NO backwards compatibility was maintained:**

```python
# OLD (removed entirely):
from core.services.user.user_context_intelligence import UserContextIntelligence

# NEW (only path):
from core.services.user.intelligence import UserContextIntelligence
```

**All 5 import sites were updated immediately:**
- `services_bootstrap.py`
- `core/services/askesis_service.py`
- `core/services/user/user_context_service.py`
- `core/services/user/__init__.py`
- `core/services/user_service.py`

---

## Alternatives Considered

### Alternative 1: Keep single file with sections
**Pros:** No migration needed
**Cons:** 2,703 lines remains difficult to navigate
**Why rejected:** Doesn't address maintainability

### Alternative 2: Backwards compatibility shim
**Pros:** Gradual migration
**Cons:** Violates SKUEL's "One Path Forward" principle
**Why rejected:** SKUEL does not maintain backwards compatibility

### Alternative 3: Composition over mixins
**Pros:** More explicit dependencies
**Cons:** More boilerplate, less natural method access
**Why rejected:** Mixins are cleaner for this use case

---

## Consequences

### Positive Consequences
- ✅ Each file has single responsibility (< 500 lines each)
- ✅ Clear separation: learning, life path, synergy, schedule, daily planning
- ✅ Mixins enable independent testing
- ✅ Follows existing pattern (ADR-016 context builder decomposition)
- ✅ Aligns with SKUEL's "One Path Forward" principle

### Negative Consequences
- ⚠️ More files to navigate (10 instead of 1)
- ⚠️ All import sites needed immediate update

### Neutral Consequences
- ℹ️ Public API unchanged
- ℹ️ All 8 core methods preserved
- ℹ️ Total lines increased slightly (3,124 vs 2,703) due to proper module docstrings

---

## Implementation Details

### Files Created
- `/core/services/user/intelligence/__init__.py` - Package exports
- `/core/services/user/intelligence/types.py` - LifePathAlignment, DailyWorkPlan, etc.
- `/core/services/user/intelligence/learning_intelligence.py` - LearningIntelligenceMixin
- `/core/services/user/intelligence/life_path_intelligence.py` - LifePathIntelligenceMixin
- `/core/services/user/intelligence/synergy_intelligence.py` - SynergyIntelligenceMixin
- `/core/services/user/intelligence/schedule_intelligence.py` - ScheduleIntelligenceMixin
- `/core/services/user/intelligence/daily_planning.py` - DailyPlanningMixin
- `/core/services/user/intelligence/graph_native.py` - GraphNativeMixin
- `/core/services/user/intelligence/core.py` - UserContextIntelligence
- `/core/services/user/intelligence/factory.py` - UserContextIntelligenceFactory

### Files Deleted
- `/core/services/user/user_context_intelligence.py` (2,703 lines)

### Files Updated (imports)
- `services_bootstrap.py`
- `core/services/askesis_service.py`
- `core/services/user/user_context_service.py`
- `core/services/user/__init__.py`
- `core/services/user_service.py`

---

## The 8 Core Methods

| # | Method | Mixin | Purpose |
|---|--------|-------|---------|
| 1 | `get_optimal_next_learning_steps()` | LearningIntelligenceMixin | What should I learn next? |
| 2 | `get_learning_path_critical_path()` | LearningIntelligenceMixin | Fastest route to life path? |
| 3 | `get_knowledge_application_opportunities()` | LearningIntelligenceMixin | Where can I apply this? |
| 4 | `get_unblocking_priority_order()` | LearningIntelligenceMixin | What unlocks the most? |
| 5 | `get_ready_to_work_on_today()` | DailyPlanningMixin | **THE FLAGSHIP** - What's optimal for TODAY? |
| 6 | `get_cross_domain_synergies()` | SynergyIntelligenceMixin | Cross-domain synergy detection |
| 7 | `calculate_life_path_alignment()` | LifePathIntelligenceMixin | Life path alignment scoring |
| 8 | `get_schedule_aware_recommendations()` | ScheduleIntelligenceMixin | Schedule-aware recommendations |

---

## Related Documentation

- ADR-016: Context Builder Decomposition (same pattern)
- `/docs/patterns/CONTEXT_FIRST_RELATIONSHIP_PATTERN.md`
- `/docs/architecture/UNIFIED_USER_ARCHITECTURE.md`

---

## Changelog

| Date | Author | Change | Version |
|------|--------|--------|---------|
| 2026-01-04 | Claude | Initial implementation | 1.0 |
