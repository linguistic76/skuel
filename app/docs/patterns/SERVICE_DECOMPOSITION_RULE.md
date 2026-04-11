# Service Decomposition Rule

## Mixin vs Sub-Service Rule

### When to create an Intelligence Mixin

Extract intelligence methods into mixins when the intelligence service **file exceeds ~350 lines**. Group by analytical concern:

| Mixin | Contents |
|-------|----------|
| `_core_intelligence_mixin.py` | Domain alias for `get_with_context()`, raw context categorization |
| `_analytics_mixin.py` | Performance dashboards, batch analysis, metrics |
| `_predictive_mixin.py` | Forecasting, success probability, scenario analysis |
| `_behavioral_signals_mixin.py` | Dual-track assessment, ZPD signals, behavioral patterns |
| `_productivity_mixin.py` | Analytics engine delegation (learning patterns, mastery progression) |

The shell `{domain}_intelligence_service.py` becomes a thin import + delegation class (~150-200 lines) that keeps only the protocol methods (`get_with_context`, `get_performance_analytics`, `get_domain_insights`) and `__init__`.

**Pattern (established in Goals, April 2026; applied to Tasks and Events, April 2026):**

```python
class TasksIntelligenceService(
    _CoreIntelligenceMixin,   # context retrieval + cross-domain categorization
    _AnalyticsMixin,          # behavioral + performance analytics
    _ProductivityMixin,       # analytics engine methods
    BaseAnalyticsService["TasksOperations", Task],
):
    """Shell: __init__ + protocol methods only."""
```

### When to create a Facade Mixin

Extract facade methods into mixins when:
1. The facade **file exceeds ~700 lines**, AND
2. **4+ methods share a coherent domain theme**

| Mixin | Theme | Example Methods |
|-------|-------|-----------------|
| `_orchestration_mixin.py` | Multi-service coordination | `create_*_with_context`, attendee management, status transitions |
| `_scheduling_mixin.py` | Time/recurrence operations | `check_conflicts`, `create_recurring_instances` |
| `_relationship_mixin.py` | Cross-domain graph links | `link_*_to_goal/habit/knowledge` |
| `_completion_mixin.py` | Completion cascade logic | `complete_*_with_cascade`, quality scoring |

**Pattern (applied to Events, April 2026):**

```python
class EventsService(
    _OrchestrationMixin,              # status, attendees, linking, context-aware creation
    _SchedulingMixin,                 # conflict detection, recurring instances
    KnowledgeIntelligenceDelegationMixin,
    BaseService["EventsOperations", Event],
):
    """Shell: __init__ + thin delegation methods (~50) + get_filtered_context."""
```

### When to keep as explicit delegation on the facade

- Thin 1-3 line pass-throughs to a single sub-service
- Methods that don't cluster into a domain-coherent group of 4+
- Any method in a facade that is < 700 lines

### Sub-service (not a mixin)

A full class with its own backend access, injected as `self.progress`, `self.scheduling`, etc. Create when:
- Operations form a complete functional domain needing independent data access
- Logic exceeds ~200 lines (not just delegation)
- Testable in isolation

## Current State (April 2026)

| Domain | Intelligence Decomposed | Facade Decomposed |
|--------|------------------------|-------------------|
| Tasks  | ✅ `_core_intelligence_mixin`, `_analytics_mixin`, `_productivity_mixin` | `_orchestration_mixin`, `_relationship_mixin` |
| Goals  | ✅ `_core_intelligence_mixin`, `_analytics_mixin`, `_predictive_mixin`, `_dual_track_mixin` | `_orchestration_mixin`, `_relationship_mixin` |
| Habits | ✅ 3 mixins | `_completion_mixin`, `_enrichment_mixin`, `_orchestration_mixin` |
| Events | ✅ `_core_intelligence_mixin`, `_analytics_mixin`, `_behavioral_signals_mixin` | `_orchestration_mixin`, `_scheduling_mixin` |
| Choices | ✅ 3 mixins | `_option_management_mixin`, `_enrichment_mixin`, `_relationship_mixin` |
| Principles | ✅ 3 mixins | `_embodiment_mixin`, `_gravity_mixin`, `_enrichment_mixin` |

## Mixin Class Template

```python
"""
{Theme} Mixin — {Domain}IntelligenceService / {Domain}Service
==============================================================

{One-sentence summary of what this mixin provides}.

Part of {domain}_intelligence_service.py / {domain}_service.py decomposition (April 2026).
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

class _{Theme}Mixin:
    """
    {Theme} for {Domain}Service.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by {Domain}Service.__init__ / BaseService
    backend: Any
    logger: Any
    # ... other attributes used by the mixin methods
```
