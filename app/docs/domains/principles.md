---
title: Principles Domain
created: 2025-12-04
updated: 2026-08-19
status: current
category: domains
tags: [principles, activity-domain, domain, reflections, planning]
---

# Principles Domain

**Type:** Activity Domain (6 of 6)
**UID Prefix:** `principle:`
**Entity Label:** `Principle`
**Config:** `PRINCIPLES_CONFIG` (from `core.models.relationship_registry`)

## Purpose

Principles represent core values and guiding beliefs that inform goals, choices, and habits. They provide the philosophical foundation for decision-making.

## Key Files

| Component | Location |
|-----------|----------|
| Model | `/core/models/principle/principle.py` |
| DTO | `/core/models/principle/principle_dto.py` |
| Request Models | `/core/models/principle/principle_request.py` |
| Relationships | `/core/services/principles/principle_relationships.py` |
| Core Service | `/core/services/principles/principles_core_service.py` |
| Search Service | `/core/services/principles/principles_search_service.py` |
| Alignment Service | `/core/services/principles/principles_alignment_service.py` |
| Learning Service | `/core/services/principles/principles_learning_service.py` |
| Intelligence Service | `/core/services/principles/principles_intelligence_service.py` |
| Intelligence Mixins | `_core_intelligence_mixin.py`, `_alignment_intelligence_mixin.py`, `_influence_mixin.py` |
| Facade Mixins | `_embodiment_mixin.py`, `_gravity_mixin.py`, `_enrichment_mixin.py` |
| Event Handler | `/core/services/principles/principle_event_handler_service.py` |
| Request Models | `/core/models/principle/principle_request.py` |
| **Planning Service** | `/core/services/principles/principles_planning_service.py` |
| Facade | `/core/services/principles_service.py` |
| Config | `PRINCIPLES_CONFIG` in `/core/models/relationship_registry.py` |
| UI Components | `/ui/principles/views.py` |
| Routes | `/adapters/inbound/principles_ui.py` |
| Events | `/core/events/principle_events.py` |
| Context Types | `/core/models/context_types.py` (ContextualPrinciple, PracticeOpportunity) |

## Domain Enums

| Enum | Import | Values | YAML Field |
|------|--------|--------|------------|
| `PrincipleCategory` | `core.models.enums` | SPIRITUAL, ETHICAL, RELATIONAL, PERSONAL, PROFESSIONAL, INTELLECTUAL, HEALTH, CREATIVE | `category` |
| `PrincipleSource` | `core.models.enums` | PHILOSOPHICAL, RELIGIOUS, CULTURAL, PERSONAL, SCIENTIFIC, MENTOR, LITERATURE | `source` |
| `PrincipleStrength` | `core.models.enums` | CORE, STRONG, MODERATE, DEVELOPING, EXPLORING | `strength` |
| `AlignmentLevel` | `core.models.enums` | FLOURISHING, ALIGNED, MOSTLY_ALIGNED, EXPLORING, PARTIAL, DRIFTING, MISALIGNED, UNKNOWN | — (reflection scoring) |
| `TriggerType` | `core.models.enums` | GOAL, HABIT, EVENT, CHOICE, MANUAL | — (what activates a principle) |
| `Priority` | `core.models.enums` | LOW, MEDIUM, HIGH, CRITICAL | `priority` |

**See:** [Enum Architecture](/docs/architecture/ENUM_ARCHITECTURE.md)

## Facade Pattern (February 2026, mixins April 2026)

`PrinciplesService` delegates to sub-services + 3 focused mixins for consistency with Habits and Choices:

```python
class PrinciplesService(
    _EmbodimentMixin,     # expressions, alignment history, portfolio, integrity
    _GravityMixin,        # cross-domain links (goals, habits, knowledge, choices)
    _EnrichmentMixin,     # analytics summary, search, sources, prioritization
    KnowledgeIntelligenceDelegationMixin,
    BaseService[PrinciplesOperations, Principle],
):
```

**Facade Mixins** (`core/services/principles/`):
| Mixin | Purpose |
|-------|---------|
| `_EmbodimentMixin` | How values are lived — expressions, alignment history, portfolio, integrity |
| `_GravityMixin` | The gravitational pull — links to goals, habits, knowledge, choices |
| `_EnrichmentMixin` | Analytics and discovery — summary, search, sources, prioritization |

**Sub-services:**
| Service | Purpose |
|---------|---------|
| `core` | CRUD operations for principles |
| `search` | Text search, filtering, graph-aware queries |
| `alignment` | Graph-based goal/habit alignment assessment, motivational intelligence (via `CrossDomainQueryService`) |
| `learning` | Learning path integration and knowledge framing |
| `relationships` | Cross-domain links via `UnifiedRelationshipService` |
| `intelligence` | Conflict analysis, adherence trends, context enrichment |
| `planning` | Context-aware recommendations (January 2026) |
| `event_handler` | Event-driven cascade analysis and conflict intelligence (March 2026) |

Created via `create_common_sub_services()` factory + domain-specific services in facade `__init__`.

### Facade Aggregation Methods (March 2026)

| Method | Returns | Description |
|--------|---------|-------------|
| `get_analytics_summary(user_uid)` | `Result[dict]` | Analytics: total, core_count, active_count, overall_adherence, recent reflections |
| `get_filtered_context(user_uid, ...)` | `Result[ListContext]` | Filtered + sorted principles with stats |

`get_analytics_summary` orchestrates `core`, `alignment`, and `reflection` sub-services. Extracted from route-level `get_analytics_data` inner function.

## Model Fields

| Field | Type | Description |
|-------|------|-------------|
| `uid` | `str` | Unique identifier |
| `user_uid` | `str` | Owner user |
| `title` | `str` | Principle title |
| `description` | `str?` | Principle description |
| `statement` | `str` | Core principle statement |
| `why_important` | `str?` | Why holding this principle matters |
| `source` | `str?` | Source/origin of principle |
| `domain` | `Domain` | TECH, HEALTH, PERSONAL, etc. |
| `priority` | `Priority` | Core, Important, Supporting |
| `is_core` | `bool` | Whether this is a core principle |
| `created_at` | `datetime` | When created |

## Relationships

### Outgoing (Principle → Other)

| Key | Relationship | Target | Description |
|-----|--------------|--------|-------------|
| `knowledge` | `GROUNDED_IN_KNOWLEDGE` | Ku | Knowledge that grounds principle (YAML: `connections.grounded_in_knowledge`) |
| `guided_goals` | `GUIDES_GOAL` | Goal | Goals this principle guides |
| `guided_choices` | `GUIDES_CHOICE` | Choice | Choices this principle guides |

### Incoming (Other → Principle)

| Key | Relationship | Source | Description |
|-----|--------------|--------|-------------|
| `embodying_habits` | `EMBODIES_PRINCIPLE` | Habit | Habits that embody this principle |
| `supporting_principles` | `SUPPORTS_PRINCIPLE` | Principle | Related principles that support |
| `conflicting_principles` | `CONFLICTS_WITH_PRINCIPLE` | Principle | Potentially conflicting principles |
| `aligned_tasks` | `ALIGNED_WITH_PRINCIPLE` | Task | Tasks aligned with principle |

### Bidirectional

- `SUPPORTS_PRINCIPLE` - Principle support relationships
- `CONFLICTS_WITH_PRINCIPLE` - Principle conflicts

## Cross-Domain Mappings

| Field | Target Label | Relationships |
|-------|--------------|---------------|
| `knowledge` | Ku | `GROUNDED_IN_KNOWLEDGE` |
| `goals` | Goal | `GUIDES_GOAL` |
| `choices` | Choice | `GUIDES_CHOICE` |
| `habits` | Habit | `EMBODIES_PRINCIPLE` |
| `tasks` | Task | `ALIGNED_WITH_PRINCIPLE` |

## Query Intent

**Default:** `QueryIntent.HIERARCHICAL`

| Context | Intent |
|---------|--------|
| `context` | `HIERARCHICAL` |
| `impact` | `HIERARCHICAL` |

## MEGA-QUERY Sections

- `core_principle_uids` - Core principle UIDs
- `entities_rich["principles"]` - Full principle data with graph context

## Scoring Weights

| Factor | Weight | Description |
|--------|--------|-------------|
| `alignment` | 0.5 | How aligned actions are |
| `goals` | 0.3 | Goal guidance strength |
| `knowledge` | 0.2 | Knowledge grounding |
| `habits` | 0.0 | Via embodiment |
| `tasks` | 0.0 | Via alignment |

## Principle Philosophy

Principles in SKUEL are:

1. **Foundational** - They ground decision-making
2. **Living** - They are embodied through habits
3. **Guiding** - They direct goals and choices
4. **Knowledge-based** - They are grounded in understanding

## Principle Conflict Detection

The `CONFLICTS_WITH_PRINCIPLE` relationship helps identify when principles may be in tension, enabling thoughtful resolution.

## Search Methods

**Service:** `PrinciplesSearchService` (`/core/services/principles/principles_search_service.py`)

### Inherited from BaseService

| Method | Description |
|--------|-------------|
| `search(query, user_uid)` | Text search across title, description, rationale |
| `get_by_relationship(related_uid, rel, dir)` | Graph traversal |
| `graph_aware_faceted_search(request)` | Unified search with graph context |

### Overridden Methods

| Method | Override Reason |
|--------|-----------------|
| `get_by_status(status, user_uid)` | Principles use `is_active: bool` instead of `status: str` |
| `list_categories(user_uid)` | Custom category enumeration |

### Domain-Specific Methods

| Method | Description |
|--------|-------------|
| `get_by_category(category, user_uid)` | Filter by category |
| `get_for_goal(goal_uid, user_uid)` | Principles aligned with goal |
| `get_for_habit(habit_uid, user_uid)` | Principles inspiring habit |
| `get_active(user_uid)` | Override of `TimeQueryMixin.get_active` — filters on the `is_active` flag and sorts by strength |
| `get_upcoming(days_ahead, user_uid)` | Override — principles approaching the 90-day review threshold |
| `get_overdue(user_uid)` | Override — thin delegation to `get_needing_review(days_threshold=90)` |
| `get_needing_review(user_uid, days=90)` | Principles not reviewed recently |
| `get_related_principles(principle_uid, user_uid)` | Related principles |
| `get_prioritized(user_uid, limit=10)` | Smart prioritization |

**Full catalog:** [Search Service Methods Reference](/docs/reference/SEARCH_SERVICE_METHODS.md)

## Intelligence Service (mixins April 2026)

`PrinciplesIntelligenceService` delegates to 3 focused mixins:

```python
class PrinciplesIntelligenceService(
    _CoreIntelligenceMixin,          # protocol bridges + graph context
    _AlignmentIntelligenceMixin,     # alignment assessment, dual-track, adherence trends
    _InfluenceMixin,                 # conflict detection, impact metrics, choice guidance
    BaseAnalyticsService[PrinciplesOperations, Principle],
):
```

**Intelligence Mixins** (`core/services/principles/`):
| Mixin | Purpose |
|-------|---------|
| `_CoreIntelligenceMixin` | `get_performance_analytics`, `get_domain_insights`; inherits `get_with_context` from shared base |
| `_AlignmentIntelligenceMixin` | `assess_principle_alignment`, `assess_alignment_dual_track`, `get_principle_adherence_trends`, helpers |
| `_InfluenceMixin` | `get_principle_conflict_analysis`, `get_quick_principle_impact`, `batch_analyze_principle_adoption`, `get_choice_guidance_effectiveness` |

**See:** [Intelligence Services Index](/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md)

## Planning Service (January 2026)

`PrinciplesPlanningService` provides context-aware principle recommendations following the `TasksPlanningService` pattern.

**Philosophy:** "Filter by attention needed, rank by relevance, enrich with insights"

**Pattern:** Context-First - All methods use `UserContext` (~240 fields) for personalization.

### Planning Methods

| Method | Description |
|--------|-------------|
| `get_principles_needing_attention_for_user(context, limit)` | Principles that need review/practice |
| `get_contextual_principles_for_user(context, limit)` | Principles relevant to today's activities |
| `get_principle_practice_opportunities_for_user(context, principle_uid, limit)` | Activities that strengthen alignment |

### get_principles_needing_attention_for_user()

**THE KEY METHOD** - Surfaces principles that need attention based on:
- Days since last reflection (> 14 days triggers attention)
- Low alignment scores (< 0.5)
- Declining alignment trends
- High priority but underengaged

Returns `list[ContextualPrinciple]` sorted by attention urgency.

### get_contextual_principles_for_user()

Finds principles relevant to today's scheduled activities:
- Linked to today's tasks via `ALIGNED_WITH_PRINCIPLE`
- Linked to today's events via relationship graph
- Connected to active goals via `GUIDES_GOAL`
- Boosted if in `core_principle_uids`

Returns `list[ContextualPrinciple]` with connected activity UIDs.

### get_principle_practice_opportunities_for_user()

Identifies activities that could strengthen principle alignment:
- Today's tasks aligned with principles
- Today's events connected to principles
- Prioritizes principles with low alignment (practice what you need)

Returns `list[PracticeOpportunity]` with guidance text.

### Context Types

**ContextualPrinciple** (`/core/models/context_types.py`):

| Field | Type | Description |
|-------|------|-------------|
| `uid` | `str` | Principle UID |
| `name` | `str` | Principle name |
| `attention_score` | `float` | How urgently needs attention (0-1) |
| `relevance_score` | `float` | Relevance to today's activities (0-1) |
| `alignment_score` | `float` | Current alignment level (0-1) |
| `alignment_trend` | `str` | "improving", "declining", "stable" |
| `days_since_reflection` | `int` | Days since last reflection |
| `attention_reasons` | `tuple[str, ...]` | Why principle needs attention |
| `suggested_action` | `str` | Actionable recommendation |
| `connected_task_uids` | `tuple[str, ...]` | Today's tasks connected to principle |
| `connected_event_uids` | `tuple[str, ...]` | Today's events connected to principle |
| `connected_goal_uids` | `tuple[str, ...]` | Active goals connected to principle |
| `practice_opportunity` | `str` | Description of practice opportunity |

**PracticeOpportunity** (`/core/models/context_types.py`):

| Field | Type | Description |
|-------|------|-------------|
| `principle_uid` | `str` | Principle this strengthens |
| `principle_name` | `str` | Principle name |
| `activity_type` | `str` | "task", "event", "goal", "habit" |
| `activity_uid` | `str` | Activity UID |
| `activity_title` | `str` | Activity title |
| `opportunity_type` | `str` | "direct_alignment", "practice_context", "reflection_trigger" |
| `guidance` | `str` | Actionable suggestion for user |

### Code Examples

```python
# Get principles needing attention
result = await principles_service.get_principles_needing_attention_for_user(
    context=user_context,
    limit=5,
)
for principle in result.value:
    print(f"{principle.title}: {principle.suggested_action}")
    # "Continuous Learning: Schedule time to reflect on this principle today"

# Get principles relevant to today
result = await principles_service.get_contextual_principles_for_user(
    context=user_context,
    limit=3,
)
for principle in result.value:
    print(f"{principle.title}: {principle.practice_opportunity}")
    # "Integrity: Connected to 2 tasks and 1 event today"

# Get practice opportunities
result = await principles_service.get_principle_practice_opportunities_for_user(
    context=user_context,
    principle_uid="principle.integrity",  # Optional, omit for all
    limit=5,
)
for opp in result.value:
    print(f"{opp.activity_title}: {opp.guidance}")
    # "Review quarterly budget: This task directly embodies your principle."
```

### Attention Score Calculation

The attention score (0-1) determines how urgently a principle needs attention:

| Factor | Weight | Description |
|--------|--------|-------------|
| Reflection gap | 0.4 | Days since reflection / (threshold × 2) |
| Alignment weakness | 0.35 | 1.0 - alignment_score |
| Trend decline | 0.25 | 1.0 if declining, 0.3 if stable, 0.0 if improving |

**Threshold:** Principles with attention_score < 0.3 are considered healthy.

### UserContext Fields Used

The planning service extracts data from `UserContext`:

| Field | Usage |
|-------|-------|
| `core_principle_uids` | Target principles for analysis |
| `entities_rich["principles"]` | Rich data with graph context |
| `principle_priorities` | Importance weighting |
| `todays_task_uids` | Today's scheduled tasks |
| `todays_event_uids` | Today's scheduled events |
| `active_goal_uids` | Current active goals |
| `entities_rich["tasks"]` | Task data with principle relationships |
| `entities_rich["events"]` | Event data with principle relationships |
| `entities_rich["goals"]` | Goal data with principle relationships |

## Events/Publishing

The Principles domain publishes domain events for cross-service communication:

| Event | Trigger | Data |
|-------|---------|------|
| `PrincipleCreated` | Principle created | `principle_uid`, `user_uid`, `title` |
| `PrincipleUpdated` | Principle modified | `principle_uid`, `user_uid`, `changed_fields` |
| `PrincipleStrengthChanged` | Strength level changed | `principle_uid`, `user_uid`, `old_strength`, `new_strength` |
| `PrincipleReflectionRecorded` | Reflection saved | `reflection_uid`, `principle_uid`, `alignment_level` |
| `PrincipleConflictRevealed` | Conflict detected | `principle_uid`, `conflicting_principle_uid` |

**Event handling:** `PrincipleEventHandlerService` subscribes to `PrincipleStrengthChanged`, `PrincipleReflectionRecorded`, and `PrincipleConflictRevealed` for cascade analysis, cross-domain insights, and conflict resolution guidance. Other services subscribe for UserContext invalidation.

## UI Routes

Read-focused UI at `/principles` is planned. API routes remain active.

## Code Examples

### Create a Principle

```python
from core.models.enums.principle_enums import PrincipleCategory
from core.models.principle.principle_request import PrincipleCreateRequest

request = PrincipleCreateRequest(
    title="Continuous Learning",
    statement="Commit to lifelong learning and growth",
    category=PrincipleCategory.INTELLECTUAL,
    why_important="Knowledge compounds over time, leading to wisdom",
)
result = await principles_service.create_principle(request, user_uid)
principle = result.value
```

### Record a Reflection

```python
from core.models.enums.principle_enums import AlignmentLevel

result = await principles_service.record_principle_reflection(
    principle_uid=principle.uid,
    user_uid=user_uid,
    alignment_level=AlignmentLevel.ALIGNED.value,
    evidence="Spent 2 hours studying new Python patterns today",
    trigger_type="habit",
    trigger_uid="habit.daily-learning",
)
# Publishes PrincipleReflectionRecorded; supply conflicting_principle_uid
# to also publish PrincipleConflictRevealed.
```

### Get Alignment Trend

```python
result = await principles_service.get_alignment_trend(
    principle_uid=principle.uid,
    user_uid=user_uid,
    days=30,
)
trend = result.value
print(f"Trend: {trend.trend_direction}, Avg: {trend.average_alignment}")
```

### Assess Goal Alignment

```python
result = await principles_service.assess_goal_alignment(
    goal_uid="goal.learn-rust",
    user_uid=user_uid,
)
assessment = result.value
print(f"Aligned principles: {assessment.aligned_principles}")
```

---

## API Routes (June 2026)

All ownership-verified unless otherwise noted.

| Route | Method | Description |
|-------|--------|-------------|
| `/api/principles/expression?uid=` | POST | Append a lived expression (context + behavior) |
| `/api/principles/portfolio` | GET | Authenticated user's complete principle portfolio |
| `/api/principles/integrity?uid=` | GET | Action-alignment integrity score for a principle |
| `/api/principles/link?uid=` | POST | Link principle → goal / habit / Ku / principle |
| `/api/principles/links?uid=&link_type=` | GET | Cross-domain links (all or filtered by type) |
| `/api/principles/impact?uid=` | GET | Quick impact metrics (adoption level, counts) |
| `/api/principles/batch-impact` | POST | Parallel adoption analysis for N principles |
| `/api/principles/choice-effectiveness?uid=&period_days=` | GET | How effectively principle guides choices |
| `/api/principles/reflection` | POST | Record alignment evidence; publishes events |
| `/api/principles/link-knowledge` | POST | Link principle to a Ku (GROUNDED_IN_KNOWLEDGE) |
| `/api/principles/children?uid=` | GET | Direct sub-principles |
| `/api/principles/parent?uid=` | GET | Immediate parent principle |
| `/api/principles/hierarchy?uid=` | GET | Full ancestor/sibling/child context |
| `/api/principles/remove-child` | POST | Remove a sub-principle relationship |

**Reflection request body** (`PrincipleReflectionRequest`):
```json
{
  "principle_uid": "principle.integrity",
  "alignment_level": "aligned",
  "evidence": "Kept my commitment despite pressure to cut corners",
  "trigger_type": "choice",
  "trigger_uid": "choice:...",
  "conflicting_principle_uid": null,
  "reflection_quality_score": 0.8
}
```
Publishes `PrincipleReflectionRecorded`. Supply `conflicting_principle_uid` to also fire `PrincipleConflictRevealed`.

---

## See Also

- [Goals Domain](goals.md) - Principles guide goals
- [Choices Domain](choices.md) - Principles guide choices
- [Habits Domain](habits.md) - Habits embody principles
- [Knowledge (KU) Domain](ku.md) - Principles grounded in knowledge
- [Intelligence Services Index](/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md) - PrinciplesIntelligenceService
