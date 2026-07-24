# Service Decomposition Rule

**Line counts guide and suggest; coherence determines.** The two thresholds in this document
(~350 intelligence / ~700 facade) are **advisory signals**, never extraction mandates:
tripping one triggers a merit check (thin-method ratio, coherent clusters), not automatic
extraction. The determining test is always: **4+ coherent extractable methods whose
extraction genuinely improves the host**. *"Over the threshold but coherent" is a valid,
documented end state* — prefer raising a threshold over forcing a split. Files that tripped
a signal, were merit-checked, and were judged coherent as-is are recorded in
[Deliberately Long](#deliberately-long-judged-2026-07-23--do-not-re-flag) below so future
surveys don't re-flag them.

## Mixin vs Sub-Service Rule

### When to create an Intelligence Mixin

An intelligence service **file exceeding ~350 lines** is the signal to run the merit check;
extract into mixins only when the methods group into coherent analytical concerns:

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

A facade **file exceeding ~700 lines** is the signal to run the merit check. Extract only
when BOTH also hold:
1. **4+ methods share a coherent domain theme**, AND
2. The extracted unit is either **reused across domains**, **independently testable**, or **prevents the host file from becoming unreadable**

A facade over the signal that fails this test stays whole and gets a row in
[Deliberately Long](#deliberately-long-judged-2026-07-23--do-not-re-flag) instead.

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
- Any method in a facade below the ~700-line signal
- Any facade over the signal whose methods are mostly thin delegation (see Deliberately Long)

### Sub-service (not a mixin)

A full class with its own backend access, injected as `self.progress`, `self.scheduling`, etc. Create when:
- Operations form a complete functional domain needing independent data access
- Logic exceeds ~200 lines (not just delegation)
- Testable in isolation

## Current State (July 2026)

| Domain | Intelligence Decomposed | Facade Decomposed |
|--------|------------------------|-------------------|
| Tasks  | ✅ `_core_intelligence_mixin`, `_analytics_mixin`, `_productivity_mixin` | `_orchestration_mixin` |
| Goals  | ✅ `_core_intelligence_mixin`, `_analytics_mixin`, `_predictive_mixin`, `_dual_track_mixin` | `_orchestration_mixin` |
| Habits | ✅ 3 mixins | `_completion_mixin`, `_enrichment_mixin`, `_orchestration_mixin` |
| Events | ✅ `_core_intelligence_mixin`, `_analytics_mixin`, `_behavioral_signals_mixin` | `_orchestration_mixin`, `_scheduling_mixin` |
| Choices | ✅ 3 mixins | `_option_management_mixin`, `_enrichment_mixin` |
| Principles | ✅ 3 mixins | `_embodiment_mixin`, `_gravity_mixin`, `_enrichment_mixin` |

## Deliberately Long (judged 2026-07-23 — do not re-flag)

Surveyed with line counts + AST thin-method analysis ("thin" = ≤2 non-docstring statements,
pure delegation). Each file tripped a threshold, was merit-checked, and was judged coherent
as-is — the amended rule working as intended. Do not re-flag these in future bloat surveys;
re-open a row only if the file itself starts causing pain.

| File | Lines | Evidence |
|------|-------|----------|
| `core/services/ps_service.py` | 1085 | 91 methods, 78 thin (86%) + 101-line `__init__` — canonical pure-delegation facade |
| `core/services/tasks_service.py` | 1087 | 49/61 methods thin; already has `_OrchestrationMixin`; only 2 fat methods — fails the 4+ coherence test |
| `core/services/intelligence/query_intelligence_service.py` | 666 | Already internally decomposed: `IntentScorer` / `FacetDetector` / `ResultRanker` + thin orchestrator |
| `core/services/ps/ps_intelligence_service.py` | 621 | Pattern-conformant (`_CoreIntelligenceMixin` + `BaseAnalyticsService`); single coherent readiness/practice theme |

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
