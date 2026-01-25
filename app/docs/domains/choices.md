---
title: Choices Domain
created: 2025-12-04
updated: 2026-01-14
status: current
category: domains
tags: [choices, activity-domain, domain]
---

# Choices Domain

**Type:** Activity Domain (5 of 6)
**UID Prefix:** `choice:`
**Entity Label:** `Choice`
**Config:** `CHOICE_CONFIG`

## Purpose

Choices represent decisions with outcome tracking. They connect knowledge, principles, and goals to decision-making processes.

## Key Files

| Component | Location |
|-----------|----------|
| Model | `/core/models/choice/choice.py` |
| DTO | `/core/models/choice/choice_dto.py` |
| Request Models | `/core/models/choice/choice_request.py` |
| Relationships | `/core/models/choice/choice_relationships.py` |
| Core Service | `/core/services/choices/choices_core_service.py` |
| Search Service | `/core/services/choices/choices_search_service.py` |
| Intelligence Service | `/core/services/choices/choices_intelligence_service.py` |
| Analytics Service | `/core/services/choices/choices_analytics_service.py` |
| Facade | `/core/services/choices_service.py` |
| Config | `CHOICE_CONFIG` in `/core/services/relationships/domain_configs.py` |
| Events | `/core/events/choice_events.py` |
| UI Routes | `/adapters/inbound/choice_ui.py` |
| View Components | `/components/choices_views.py` |

## Facade Pattern (January 2026)

`ChoicesService` uses `FacadeDelegationMixin` with signature preservation for clean delegation to 6 specialized sub-services:

```python
class ChoicesService(FacadeDelegationMixin, BaseService[ChoicesOperations, Choice]):
    _delegations = merge_delegations(
        {"get_choice": ("core", "get_choice"), ...},           # Core CRUD
        {"search_choices": ("search", "search"), ...},         # Search
        create_relationship_delegations("choice"),              # Relationships
        {"analyze_decision_patterns": ("analytics", ...), ...}, # Analytics
    )
```

**Sub-services:**
| Service | Purpose |
|---------|---------|
| `core` | CRUD operations, option management, make_decision |
| `search` | Text search, filtering, graph-aware queries |
| `learning` | Learning path guidance integration |
| `relationships` | Cross-domain links via `UnifiedRelationshipService` |
| `intelligence` | Decision support, outcome analysis |
| `analytics` | Decision pattern analysis, impact tracking |

Created via `create_common_sub_services()` factory in facade `__init__`.

## Model Fields

| Field | Type | Description |
|-------|------|-------------|
| `uid` | `str` | Unique identifier |
| `user_uid` | `str` | Owner user |
| `title` | `str` | Choice/decision title |
| `description` | `str` | Choice description |
| `choice_type` | `ChoiceType` | Binary, Multiple, Ranking, Strategic, Operational |
| `status` | `ChoiceStatus` | Pending, Decided, Implemented, Evaluated |
| `priority` | `Priority` | Low, Medium, High, Critical |
| `domain` | `Domain` | Personal, Business, Health, Finance, Social |
| `options` | `list[ChoiceOptionDTO]` | Available options (see below) |
| `selected_option_uid` | `str?` | UID of chosen option |
| `decision_rationale` | `str?` | Why this option was chosen |
| `decision_criteria` | `list[str]` | Criteria for evaluation |
| `constraints` | `list[str]` | Constraints to consider |
| `stakeholders` | `list[str]` | Affected stakeholders |
| `decision_deadline` | `datetime?` | When decision is needed |
| `decided_at` | `datetime?` | When decision was made |
| `satisfaction_score` | `int?` | Outcome satisfaction (1-5) |
| `actual_outcome` | `str?` | Outcome description |
| `lessons_learned` | `list[str]` | Post-decision insights |

### ChoiceOptionDTO Fields

Each option in `options` list:

| Field | Type | Description |
|-------|------|-------------|
| `uid` | `str` | Option identifier |
| `title` | `str` | Option title |
| `description` | `str` | Option description |
| `feasibility_score` | `float` | Feasibility (0.0-1.0) |
| `risk_level` | `float` | Risk level (0.0-1.0) |
| `potential_impact` | `float` | Impact score (0.0-1.0) |
| `resource_requirement` | `float` | Resources needed (0.0-1.0) |
| `estimated_duration` | `int?` | Duration in minutes |
| `dependencies` | `list[str]` | Dependency UIDs |
| `tags` | `list[str]` | Categorization tags |

## Relationships

### Outgoing (Choice → Other)

| Key | Relationship | Target | Description |
|-----|--------------|--------|-------------|
| `knowledge` | `INFORMED_BY_KNOWLEDGE` | Ku | Knowledge that informed decision |
| `principles` | `INFORMED_BY_PRINCIPLE` | Principle | Principles that guided decision |
| `goals` | `AFFECTS_GOAL` | Goal | Goals affected by choice |
| `learning_paths` | `OPENS_LEARNING_PATH` | Lp | Learning paths opened by choice |

### Incoming (Other → Choice)

| Key | Relationship | Source | Description |
|-----|--------------|--------|-------------|
| `inspired_choices` | `INSPIRED_BY_CHOICE` | Choice | Choices inspired by this one |
| `implementing_tasks` | `IMPLEMENTS_CHOICE` | Task | Tasks implementing this choice |

## Events/Publishing

The Choices domain publishes domain events for cross-service communication:

| Event | Trigger | Data |
|-------|---------|------|
| `ChoiceCreated` | Choice created | `choice_uid`, `user_uid`, `title` |
| `ChoiceUpdated` | Choice modified | `choice_uid`, `user_uid`, `changed_fields` |
| `ChoiceMade` | Decision selected | `choice_uid`, `user_uid`, `selected_option_uid` |
| `ChoiceOutcomeRecorded` | Outcome evaluated | `choice_uid`, `user_uid`, `satisfaction_score` |

**Event handling:** Other services subscribe to these events (e.g., UserContext invalidation).

## UI Routes

### Three-View Dashboard

| Route | Method | Description |
|-------|--------|-------------|
| `/choices` | GET | Main dashboard with List/Create/Analytics tabs |
| `/choices?view=list` | GET | List view (default) |
| `/choices?view=create` | GET | Create decision form |
| `/choices?view=analytics` | GET | Decision analytics |

### HTMX Fragments

| Route | Method | Description |
|-------|--------|-------------|
| `/choices/view/list` | GET | List view fragment |
| `/choices/view/create` | GET | Create form fragment |
| `/choices/view/analytics` | GET | Analytics fragment |
| `/choices/list-fragment` | GET | Filtered list for updates |
| `/choices/quick-add` | POST | Create choice via form |

### Detail Routes

| Route | Method | Description |
|-------|--------|-------------|
| `/choices/{uid}` | GET | View choice detail |
| `/choices/{uid}/edit` | GET | Edit modal |
| `/choices/{uid}/edit` | POST | Submit edits |
| `/choices/{uid}/decide` | GET | Decision modal |
| `/choices/{uid}/decide` | POST | Submit decision |
| `/choices/{uid}/add-option` | GET | Add option modal |
| `/choices/{uid}/add-option` | POST | Submit new option |

## Dynamic Options at Creation (January 2026)

Choices require **at least 2 options** at creation time, managed via Alpine.js for a dynamic UX.

### Alpine.js Component

The `choiceOptions()` component in `/static/js/skuel.js`:

```javascript
Alpine.data('choiceOptions', function() {
    return {
        options: [
            { title: '', description: '' },
            { title: '', description: '' }
        ],
        addOption() { this.options.push({ title: '', description: '' }); },
        removeOption(index) { if (this.options.length > 2) this.options.splice(index, 1); },
        canRemove() { return this.options.length > 2; },
        isValid() {
            if (this.options.length < 2) return false;
            return this.options.every(o => o.title.trim() && o.description.trim());
        }
    };
});
```

### Form Integration

The Create form in `/components/choices_views.py`:
- Wraps form with `x-data="choiceOptions()"`
- Uses `x-for` to render dynamic option inputs
- Uses `x-model` and `x-bind:name` for form field binding
- Disables submit when `!isValid()`

### Server-Side Parsing

The `_parse_options_from_form()` helper in `/adapters/inbound/choice_ui.py`:
- Parses `options[0].title`, `options[0].description`, etc.
- Validates minimum 2 options (returns 400 if fewer)
- Converts to `ChoiceOptionCreateRequest` objects

## Code Examples

### Create Choice with Options

```python
from core.models.choice.choice_request import (
    ChoiceCreateRequest,
    ChoiceOptionCreateRequest
)
from core.models.choice.choice import ChoiceType
from core.models.shared_enums import Domain, Priority

# Create request with options
choice_request = ChoiceCreateRequest(
    title="Which web framework to use?",
    description="Choosing framework for new project",
    choice_type=ChoiceType.MULTIPLE,
    domain=Domain.TECH,
    priority=Priority.HIGH,
    options=[
        ChoiceOptionCreateRequest(
            title="FastHTML",
            description="Python-native, hypermedia-driven"
        ),
        ChoiceOptionCreateRequest(
            title="Django",
            description="Full-featured, batteries included"
        ),
        ChoiceOptionCreateRequest(
            title="Flask",
            description="Minimal, flexible"
        ),
    ]
)

result = await choices_service.create_choice(choice_request, user_uid)
choice = result.value
```

### Make a Decision

```python
result = await choices_service.make_decision(
    choice_uid=choice.uid,
    selected_option_uid=choice.options[0].uid,
    decision_rationale="Best fit for hypermedia-driven architecture",
    confidence=0.85,
)
```

### Add Option Later

```python
result = await choices_service.add_option(
    choice_uid=choice.uid,
    title="Next.js",
    description="React-based with SSR",
    feasibility_score=0.7,
    risk_level=0.4,
)
```

## Cross-Domain Mappings

| Field | Target Label | Relationships |
|-------|--------------|---------------|
| `knowledge` | Ku | `INFORMED_BY_KNOWLEDGE` |
| `principles` | Principle | `INFORMED_BY_PRINCIPLE`, `GUIDES_CHOICE` |
| `goals` | Goal | `AFFECTS_GOAL` |

## Query Intent

**Default:** `QueryIntent.HIERARCHICAL`

| Context | Intent |
|---------|--------|
| `context` | `HIERARCHICAL` |
| `impact` | `HIERARCHICAL` |

## MEGA-QUERY Sections

- `pending_choice_uids` - Pending choice UIDs (status = pending or active)
- `recent_choices_rich` - Full choice data with graph context

## Scoring Weights

| Factor | Weight | Description |
|--------|--------|-------------|
| `principles` | 0.4 | Principle alignment |
| `knowledge` | 0.3 | Knowledge informed |
| `goals` | 0.2 | Goal impact |
| `habits` | 0.1 | Habit influence |
| `tasks` | 0.0 | Not directly related |

## Decision Tracking

Choices support full decision lifecycle:

| Stage | Status | Key Fields |
|-------|--------|------------|
| **Pending** | `PENDING` | `options`, `decision_criteria`, `constraints` |
| **Decided** | `DECIDED` | `selected_option_uid`, `decision_rationale`, `decided_at` |
| **Implemented** | `IMPLEMENTED` | `implementing_tasks` relationship |
| **Evaluated** | `EVALUATED` | `satisfaction_score`, `actual_outcome`, `lessons_learned` |

## Search Methods

**Service:** `ChoicesSearchService` (`/core/services/choices/choices_search_service.py`)

### Inherited from BaseService

| Method | Description |
|--------|-------------|
| `search(query, user_uid)` | Text search across title, description |
| `get_by_status(status, user_uid)` | Filter by ChoiceStatus |
| `get_by_domain(domain, user_uid)` | Filter by Domain |
| `get_by_category(category, user_uid)` | Filter by category field |
| `get_by_relationship(related_uid, rel, dir)` | Graph traversal |
| `graph_aware_faceted_search(request)` | Unified search with graph context |

### Domain-Specific Methods

| Method | Description |
|--------|-------------|
| `get_pending(user_uid)` | Undecided choices |
| `get_by_urgency(urgency, user_uid)` | Filter by urgency level |
| `get_affecting_goal(goal_uid, user_uid)` | Choices affecting a goal |
| `get_needing_decision(user_uid, days=7)` | Choices with deadline approaching |
| `get_aligned_with_principle(principle_uid, user_uid)` | Choices aligned with principle |
| `get_decided(user_uid, days=30)` | Recently decided choices |
| `get_prioritized(user_uid, limit=10)` | Smart prioritization |

**Full catalog:** [Search Service Methods Reference](/docs/reference/SEARCH_SERVICE_METHODS.md)

## Intelligence Service

`ChoicesIntelligenceService` provides decision support and analysis:

| Method | Description |
|--------|-------------|
| `get_choice_with_context(uid)` | Choice with full graph neighborhood |
| `get_decision_intelligence(uid)` | AI-powered decision insights |
| `analyze_choice_impact(uid)` | Impact analysis across domains |

**See:** [Intelligence Services Index](/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md)

## See Also

- [Principles Domain](principles.md) - Principles guide choices
- [Goals Domain](goals.md) - Choices affect goals
- [Knowledge (KU) Domain](ku.md) - Knowledge informs choices
- [Tasks Domain](tasks.md) - Tasks implement choices
- [Intelligence Services Index](/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md)
