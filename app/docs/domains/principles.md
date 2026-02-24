---
title: Principles Domain
created: 2025-12-04
updated: 2026-01-19
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
| Relationships | `/core/models/principle/principle_relationships.py` |
| Core Service | `/core/services/principles/principles_core_service.py` |
| Search Service | `/core/services/principles/principles_search_service.py` |
| Alignment Service | `/core/services/principles/principles_alignment_service.py` |
| Learning Service | `/core/services/principles/principles_learning_service.py` |
| Intelligence Service | `/core/services/principles/principles_intelligence_service.py` |
| Reflection Model | `/core/models/principle/reflection.py` |
| Reflection DTO | `/core/models/principle/reflection_dto.py` |
| Reflection Service | `/core/services/principles/principles_reflection_service.py` |
| **Planning Service** | `/core/services/principles/principles_planning_service.py` |
| Facade | `/core/services/principles_service.py` |
| Config | `PRINCIPLES_CONFIG` in `/core/models/relationship_registry.py` |
| UI Components | `/ui/principles/views.py` |
| Routes | `/adapters/inbound/principles_ui.py` |
| Events | `/core/events/principle_events.py` |
| Context Types | `/core/models/context_types.py` (ContextualPrinciple, PracticeOpportunity) |

## Facade Pattern (January 2026)

`PrinciplesService` uses `FacadeDelegationMixin` with signature preservation for clean delegation to **8 specialized sub-services**:

```python
class PrinciplesService(FacadeDelegationMixin, BaseService[PrinciplesOperations, Principle]):
    _delegations = merge_delegations(
        {"get_principle": ("core", "get_principle"), ...},              # Core CRUD
        {"assess_goal_alignment": ("alignment", ...), ...},             # Alignment
        {"frame_principle_practice_with_learning": ("learning", ...), ...},  # Learning
        create_relationship_delegations("principle", include_semantic=False), # Relationships
        {"get_principle_with_context": ("intelligence", ...), ...},     # Intelligence
        {"get_principle_categories": ("search", ...), ...},             # Search
        {"save_reflection": ("reflection", ...), ...},                  # Reflection
        {"get_principles_needing_attention_for_user": ("planning", ...), ...},  # Planning
    )
```

**Sub-services:**
| Service | Purpose |
|---------|---------|
| `core` | CRUD operations for principles |
| `search` | Text search, filtering, graph-aware queries |
| `alignment` | Goal/habit alignment assessment, motivational intelligence |
| `learning` | Learning path integration and knowledge framing |
| `relationships` | Cross-domain links via `UnifiedRelationshipService` |
| `intelligence` | Conflict analysis, adherence trends, context enrichment |
| `reflection` | Graph-connected reflection tracking (January 2026) |
| `planning` | Context-aware recommendations (January 2026) |

Created via `create_common_sub_services()` factory + domain-specific services in facade `__init__`.

## Model Fields

| Field | Type | Description |
|-------|------|-------------|
| `uid` | `str` | Unique identifier |
| `user_uid` | `str` | Owner user |
| `title` | `str` | Principle title |
| `description` | `str?` | Principle description |
| `statement` | `str` | Core principle statement |
| `source` | `str?` | Source/origin of principle |
| `domain` | `Domain` | TECH, HEALTH, PERSONAL, etc. |
| `priority` | `Priority` | Core, Important, Supporting |
| `is_core` | `bool` | Whether this is a core principle |
| `created_at` | `datetime` | When created |

## Relationships

### Outgoing (Principle → Other)

| Key | Relationship | Target | Description |
|-----|--------------|--------|-------------|
| `knowledge` | `GROUNDED_IN_KNOWLEDGE` | Ku | Knowledge that grounds principle |
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
- `core_principles_rich` - Full principle data with graph context

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
| `get_by_domain(domain, user_uid)` | Domain is `core_domain` field |
| `list_categories(user_uid)` | Custom category enumeration |

### Domain-Specific Methods

| Method | Description |
|--------|-------------|
| `get_by_strength(min_strength, user_uid)` | Filter by conviction strength |
| `get_by_category(category, user_uid)` | Filter by category |
| `get_guiding_goals(principle_uid, user_uid)` | Goals guided by principle |
| `get_inspiring_habits(principle_uid, user_uid)` | Habits inspired by principle |
| `get_for_choice(choice_uid, user_uid)` | Relevant principles for decision |
| `get_for_goal(goal_uid, user_uid)` | Principles aligned with goal |
| `get_active_principles(user_uid)` | Active principles only |
| `get_needing_review(user_uid, days=90)` | Principles not reviewed recently |
| `get_related_principles(principle_uid, user_uid)` | Related principles |
| `get_prioritized(user_uid, limit=10)` | Smart prioritization |

**Full catalog:** [Search Service Methods Reference](/docs/reference/SEARCH_SERVICE_METHODS.md)

## Intelligence Service

`PrinciplesIntelligenceService` provides principle analysis and insights:

| Method | Description |
|--------|-------------|
| `get_principle_with_context(uid)` | Principle with full graph neighborhood |
| `assess_principle_alignment(uid, user_uid)` | Calculate alignment score for user |
| `get_principle_adherence_trends(uid, days)` | Adherence trends over time |
| `get_principle_conflict_analysis(uid)` | Analyze conflicts with other principles |

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
| `core_principles_rich` | Rich data with graph context |
| `principle_priorities` | Importance weighting |
| `todays_task_uids` | Today's scheduled tasks |
| `todays_event_uids` | Today's scheduled events |
| `active_goal_uids` | Current active goals |
| `active_tasks_rich` | Task data with principle relationships |
| `active_events_rich` | Event data with principle relationships |
| `active_goals_rich` | Goal data with principle relationships |

## Events/Publishing

The Principles domain publishes domain events for cross-service communication:

| Event | Trigger | Data |
|-------|---------|------|
| `PrincipleCreated` | Principle created | `principle_uid`, `user_uid`, `title` |
| `PrincipleUpdated` | Principle modified | `principle_uid`, `user_uid`, `changed_fields` |
| `PrincipleStrengthChanged` | Strength level changed | `principle_uid`, `user_uid`, `old_strength`, `new_strength` |
| `PrincipleReflectionRecorded` | Reflection saved | `reflection_uid`, `principle_uid`, `alignment_level` |
| `PrincipleConflictRevealed` | Conflict detected | `principle_uid`, `conflicting_principle_uid` |

**Event handling:** Other services subscribe to these events (e.g., UserContext invalidation).

## UI Routes

### Three-View Dashboard

| Route | Method | Description |
|-------|--------|-------------|
| `/principles` | GET | Main dashboard with List/Create/Analytics tabs |
| `/principles?view=list` | GET | List view (default) |
| `/principles?view=create` | GET | Create principle form |
| `/principles?view=analytics` | GET | Principle analytics |

### HTMX Fragments

| Route | Method | Description |
|-------|--------|-------------|
| `/principles/view/list` | GET | List view fragment |
| `/principles/view/create` | GET | Create form fragment |
| `/principles/view/analytics` | GET | Analytics fragment |
| `/principles/list-fragment` | GET | Filtered list for updates |
| `/principles/quick-add` | POST | Create principle via form |

### Detail and Reflection Routes

| Route | Method | Description |
|-------|--------|-------------|
| `/principles/{uid}` | GET | View principle detail |
| `/principles/{uid}/edit` | GET | Edit modal |
| `/principles/{uid}/edit` | POST | Submit edits |
| `/principles/{uid}/reflect` | GET | Reflection form modal |
| `/principles/{uid}/reflect/save` | POST | Save reflection |
| `/principles/{uid}/reflections` | GET | Reflection history view |
| `/principles/{uid}/alignment-trend` | GET | Alignment trend visualization |

## Code Examples

### Create a Principle

```python
from core.models.enums.ku_enums import PrincipleCategory

result = await principles_service.create_principle(
    label="Continuous Learning",
    description="Commit to lifelong learning and growth",
    category=PrincipleCategory.INTELLECTUAL,
    why_matters="Knowledge compounds over time, leading to wisdom",
    user_uid=user_uid,
)
principle = result.value
```

### Record a Reflection

```python
from core.models.principle.reflection import AlignmentLevel

result = await principles_service.save_reflection(
    principle_uid=principle.uid,
    user_uid=user_uid,
    alignment_level=AlignmentLevel.ALIGNED,
    evidence="Spent 2 hours studying new Python patterns today",
    reflection_notes="Feeling energized by the learning",
    trigger_type="habit",
    trigger_uid="habit.daily-learning",
)
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

## PrincipleReflection Feature (January 2026)

### Overview

The PrincipleReflection feature enables users to track how well their actions align with their principles over time. Following the HabitCompletion pattern, reflections are graph-connected entities that capture moments of alignment assessment.

**Key Capabilities:**
- Persist reflections to Neo4j with full graph connectivity
- Track triggering entities (goals, habits, events, choices)
- Detect principle conflicts through reflections
- Calculate alignment trends over time
- Generate cross-domain insights

### PrincipleReflection Model

**Entity Label:** `PrincipleReflection`

| Field | Type | Description |
|-------|------|-------------|
| `uid` | `str` | Unique identifier (auto-generated) |
| `principle_uid` | `str` | UID of the principle being reflected on |
| `user_uid` | `str` | Owner user |
| `reflection_date` | `date` | Date of reflection |
| `alignment_level` | `AlignmentLevel` | ALIGNED, MOSTLY_ALIGNED, PARTIAL, MISALIGNED, UNKNOWN |
| `evidence` | `str` | What was observed (required, min 5 chars) |
| `reflection_notes` | `str?` | Additional thoughts/insights |
| `reflection_quality_score` | `float` | 0.0-1.0 quality score |
| `trigger_type` | `str?` | "goal", "habit", "event", "choice", "manual" |
| `trigger_uid` | `str?` | UID of triggering entity |
| `trigger_context` | `str?` | Situation description |
| `created_at` | `datetime` | When created |
| `updated_at` | `datetime` | When updated |

### AlignmentLevel Enum

```python
class AlignmentLevel(str, Enum):
    ALIGNED = "aligned"           # Fully lived this principle
    MOSTLY_ALIGNED = "mostly_aligned"  # Minor deviations
    PARTIAL = "partial"           # Some alignment, room for growth
    MISALIGNED = "misaligned"     # Actions contradicted principle
    UNKNOWN = "unknown"           # Unsure how to assess
```

### Quality Scoring

Reflection quality (0.0-1.0) is calculated based on:

| Factor | Weight | Description |
|--------|--------|-------------|
| Evidence depth | 0.4 | Length/detail of evidence (>100 chars = full points) |
| Notes provided | 0.3 | Additional reflection notes present |
| Trigger context | 0.2 | Situation context provided |
| Trigger UID | 0.1 | Specific entity reference |

### Graph Schema

```
(User)-[:MADE_REFLECTION]->(PrincipleReflection)-[:REFLECTS_ON]->(Principle)
                                    |
                                    +-[:TRIGGERED_BY]->(Goal|Habit|Event|Choice)
                                    |
                                    +-[:REVEALS_CONFLICT]->(Principle)
```

### Reflection Relationships

| Relationship | Direction | Description |
|--------------|-----------|-------------|
| `MADE_REFLECTION` | (User)→(Reflection) | User created this reflection |
| `REFLECTS_ON` | (Reflection)→(Principle) | Reflection is about this principle |
| `TRIGGERED_BY` | (Reflection)→(Entity) | What prompted the reflection |
| `REVEALS_CONFLICT` | (Reflection)→(Principle) | Conflict detected with another principle |
| `HAS_REFLECTION` | (Principle)→(Reflection) | Principle has this reflection |

### Reflection Service Methods

**Service:** `PrinciplesReflectionService` (`/core/services/principles/principles_reflection_service.py`)

| Method | Description |
|--------|-------------|
| `save_reflection(...)` | Create reflection with full graph connectivity |
| `get_reflections_for_principle(uid, user_uid, limit)` | Fetch reflection history for a principle |
| `get_recent_reflections(user_uid, days, limit)` | Get recent reflections across all principles |
| `calculate_alignment_trend(uid, user_uid, days)` | Analyze alignment trend over time |
| `get_cross_domain_insights(uid, user_uid)` | Which domains align best with this principle |
| `get_reflection_frequency(user_uid, days)` | Reflection frequency metrics |
| `get_conflict_analysis(uid, user_uid)` | Analyze principle conflicts revealed through reflections |

### Facade Delegations

All reflection methods are delegated through `PrinciplesService`:

```python
# Via facade
await principles_service.save_reflection(...)
await principles_service.get_reflections_for_principle(...)
await principles_service.get_alignment_trend(...)  # Maps to calculate_alignment_trend
await principles_service.get_cross_domain_insights(...)
await principles_service.get_reflection_frequency(...)
await principles_service.get_conflict_analysis(...)
```

### Events

**PrincipleReflectionRecorded** - Published when a reflection is saved:
```python
@dataclass(frozen=True)
class PrincipleReflectionRecorded(BaseEvent):
    reflection_uid: str
    principle_uid: str
    user_uid: str
    alignment_level: str
    evidence: str
    occurred_at: datetime
    trigger_type: str | None = None
    trigger_uid: str | None = None
    reflection_quality_score: float = 0.0
```

**PrincipleConflictRevealed** - Published when a conflict is detected:
```python
@dataclass(frozen=True)
class PrincipleConflictRevealed(BaseEvent):
    reflection_uid: str
    principle_uid: str
    conflicting_principle_uid: str
    user_uid: str
    occurred_at: datetime
    conflict_context: str | None = None
```

### UI Routes

| Route | Method | Description |
|-------|--------|-------------|
| `/principles/{uid}/reflect` | GET | Show reflection form (modal) |
| `/principles/{uid}/reflect/save` | POST | Save reflection |
| `/principles/{uid}/reflections` | GET | Reflection history view |
| `/principles/{uid}/alignment-trend` | GET | Alignment trend visualization |

### UI Components

**PrinciplesViewComponents** (`/ui/principles/views.py`):

| Component | Description |
|-----------|-------------|
| `render_reflect_form(principle)` | Reflection form with alignment, evidence, trigger fields |
| `render_reflection_history(principle, reflections)` | List of past reflections |
| `_render_reflection_card(reflection)` | Single reflection card |
| `render_alignment_trend(trend)` | Trend stats and visualization |

### AlignmentTrend Data Structure

```python
@dataclass
class AlignmentTrend:
    principle_uid: str
    period_start: date
    period_end: date
    reflection_count: int
    average_alignment: float  # 0-4 scale
    trend_direction: str      # "improving", "declining", "stable"
    quality_average: float    # 0-1 scale
    trigger_distribution: dict[str, int]  # Count by trigger type
```

### Verification Steps

1. Navigate to `/principles` and click "Reflect" on a principle
2. Fill in the form with evidence, notes, and trigger info
3. Click "Save Reflection" - should persist and close modal
4. Click "View" on the principle - should show recent reflections
5. Click "History" - should show full reflection history
6. Verify in Neo4j:
   ```cypher
   MATCH (r:PrincipleReflection) RETURN r
   MATCH (r:PrincipleReflection)-[rel]->(n) RETURN r, type(rel), n
   ```

---

## See Also

- [Goals Domain](goals.md) - Principles guide goals
- [Choices Domain](choices.md) - Principles guide choices
- [Habits Domain](habits.md) - Habits embody principles
- [Knowledge (KU) Domain](ku.md) - Principles grounded in knowledge
- [Intelligence Services Index](/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md) - PrinciplesIntelligenceService
