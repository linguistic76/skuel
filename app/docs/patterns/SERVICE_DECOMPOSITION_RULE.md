# Service Decomposition Rule

## Mixin vs Sub-Service Rule

### When to create an Intelligence Mixin

Extract intelligence methods into mixins when the intelligence service **file exceeds ~350 lines**. Group by analytical concern:

| Mixin | Contents |
|-------|----------|
| `_core_intelligence_mixin.py` | Per-package wrapper over generic `_CoreIntelligenceMixin[T]` — only where the domain adds real methods (Events/Choices/Principles); Tasks/Goals/Habits inherit the shared mixin directly (domain-named aliases were deleted in the tasks bloat campaign) |
| `_analytics_mixin.py` | Performance dashboards, batch analysis, metrics |
| `_predictive_mixin.py` | Forecasting, success probability, scenario analysis |
| `_behavioral_signals_mixin.py` | Dual-track assessment, ZPD signals, behavioral patterns |
| `_productivity_mixin.py` | TaskKnowledgeAnalyzer delegation (learning patterns, mastery progression, task insights) |

The shell `{domain}_intelligence_service.py` becomes a thin import + delegation class (~150-200 lines). `get_with_context()` is inherited from `_CoreIntelligenceMixin[T]` — services implement only `get_performance_analytics`, `get_domain_insights`, and `__init__`.

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

Extract facade methods into mixins when ALL are true:
1. The facade **file exceeds ~700 lines**, AND
2. **4+ methods share a coherent domain theme**, AND
3. The extracted unit is either **reused across domains**, **independently testable**, or **prevents the host file from becoming unreadable**

**Floor rule — prefer inlining when most are true:**
- The file is under ~250 lines
- It has a single consumer
- It mostly delegates to one dependency
- It exists only to satisfy a previous line-count rule
- The reader must open it nearly every time they inspect the host

| Mixin | Theme | Example Methods |
|-------|-------|-----------------|
| `_orchestration_mixin.py` | Multi-service coordination | `create_*_with_context`, attendee management, status transitions |
| `_scheduling_mixin.py` | Time/recurrence operations | `check_conflicts`, `create_recurring_instances` |
| `_completion_mixin.py` | Completion cascade logic | `complete_*_with_cascade`, quality scoring |

**Note:** `_relationship_mixin.py` was **inlined back** into Goals, Tasks, and Choices services (June 2026) — it was a thin single-consumer delegation slice that added MRO complexity without payoff. The graph link methods now live directly on the facade.

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

## Current State (June 2026)

| Domain | Intelligence Decomposed | Facade Decomposed |
|--------|------------------------|-------------------|
| Tasks  | ✅ `_core_intelligence_mixin`, `_analytics_mixin`, `_productivity_mixin` | `_orchestration_mixin` |
| Goals  | ✅ `_core_intelligence_mixin`, `_analytics_mixin`, `_predictive_mixin`, `_dual_track_mixin` | `_orchestration_mixin` |
| Habits | ✅ 3 mixins | `_completion_mixin`, `_enrichment_mixin`, `_orchestration_mixin` |
| Events | ✅ `_core_intelligence_mixin`, `_analytics_mixin`, `_behavioral_signals_mixin` | `_orchestration_mixin`, `_scheduling_mixin` |
| Choices | ✅ 3 mixins | `_option_management_mixin`, `_enrichment_mixin` |
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
