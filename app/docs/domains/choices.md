---
title: Choices Domain
created: 2025-12-04
updated: 2026-04-11
status: current
category: domains
tags: [choices, activity-domain, domain]
---

# Choices Domain

**Type:** Activity Domain (5 of 6)
**UID Prefix:** `choice:`
**Entity Label:** `Choice`
**Config:** `CHOICES_CONFIG` (from `core.models.relationship_registry`)

## Purpose

Choices represent decisions with outcome tracking. They connect knowledge, principles, and goals to decision-making processes.

## Key Files

| Component | Location |
|-----------|----------|
| Model | `/core/models/choice/choice.py` |
| DTO | `/core/models/choice/choice_dto.py` |
| Request Models | `/core/models/choice/choice_request.py` |
| Relationships | `/core/services/choices/choice_relationships.py` |
| Core Service | `/core/services/choices/choices_core_service.py` |
| Search Service | `/core/services/choices/choices_search_service.py` |
| Intelligence Service | `/core/services/choices/choices_intelligence_service.py` |
| Event Handler Service | `/core/services/choices/choice_event_handler_service.py` |
| Facade | `/core/services/choices_service.py` |
| Config | `CHOICES_CONFIG` in `/core/models/relationship_registry.py` |
| Events | `/core/events/choice_events.py` |
| UI Routes | `/adapters/inbound/choice_ui.py` |
| View Components | `/ui/choices/views.py` |

## Domain Enums

| Enum | Import | Values | YAML Field |
|------|--------|--------|------------|
| `ChoiceType` | `core.models.enums` | BINARY, MULTIPLE, RANKING, ALLOCATION, STRATEGIC, OPERATIONAL | `choice_type` |
| `Priority` | `core.models.enums` | LOW, MEDIUM, HIGH, CRITICAL | `priority` |

**See:** [Enum Architecture](/docs/architecture/ENUM_ARCHITECTURE.md)

## Facade Pattern (February 2026, mixins April 2026)

`ChoicesService` delegates to sub-services + 1 focused facade mixin for option management:

```python
class ChoicesService(
    _OptionManagementMixin,  # add/update/remove option, make_decision
    KnowledgeIntelligenceDelegationMixin,
    BaseService[ChoicesOperations, Choice],
):
    # Delegation methods delegate to the sub-services below
    async def get_choice(self, uid: str) -> Result[Choice]:
        return await self.core.get_choice(uid)
```

**Facade Mixin** (`core/services/choices/`):

| Mixin | File | Methods |
|-------|------|---------|
| `_OptionManagementMixin` | `_option_management_mixin.py` | `add_option`, `update_option`, `remove_option`, `make_decision` |

Graph relationship methods (`link_choice_to_goal/habit/principle`, `create_semantic_choice_relationship`, `find_choices_aligned_with_principle`) are inline on `ChoicesService` directly — inlined June 2026 per the decomposition floor rule.

**Sub-services:**
| Service | Purpose |
|---------|---------|
| `core` | CRUD operations, option management, make_decision |
| `search` | Text search, filtering, graph-aware queries |
| `learning` | Learning path guidance integration |
| `relationships` | Cross-domain links via `UnifiedRelationshipService` |
| `intelligence` | Decision support, dual-track assessment, prediction (takes `cross_domain_query` for ZPD behavioral signals; decomposed into 3 intelligence mixins — see CHOICES_INTELLIGENCE.md) |
| `event_handler` | Event-driven handlers (outcome tracking, decision patterns) |

Created via `create_common_sub_services()` factory in facade `__init__` (intelligence skipped — built manually with `cross_domain_query` dependency).

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
| `knowledge` | `INFORMED_BY_KNOWLEDGE` | Ku | Knowledge that informed decision (YAML: `connections.informed_by_knowledge`) |
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

**Event handling:** `ChoiceEventHandlerService` subscribes to `ChoiceOutcomeRecorded` (outcome quality analysis, principle alignment correlation) and `ChoiceMade` (decision pattern tracking, confidence analysis, insight persistence). Other services subscribe for UserContext invalidation.

## UI Routes

Read-focused UI at `/choices` is planned. API routes remain active.

## Options at Creation

### Where options are entered

`ChoiceCreateRequest.options` exists as a `list[ChoiceOptionRequest]`
(`core/models/choice/choice_request.py`), but **the web form does not collect
it.** `GET|POST /choices/create` is rendered by `FormGenerator` via
`ui/activities/choices_form.py`, whose own docstring records that the nested
`options` list and the free-text list fields are excluded; the form carries no
Alpine component beyond the default `formValidator`. Options are added on the
**detail page** after the choice exists.

> Do not infer the minimum-option rule from `ChoicesCoreService._validate_create`
> — it defines "at least 2 options" and "BINARY needs exactly 2", but nothing on
> the choice create path calls it. Verify before relying on either rule.

> **Historical note.** This section previously documented a `choiceOptions()`
> Alpine component with add/remove/validate methods, mounted on a create form in
> `ui/choices/views.py`. None of that exists: the component was deleted in
> `327f26623` (2026-03-28) along with 11 other Alpine components, and the
> `ui/choices/` directory is gone — choices UI lives in
> `adapters/inbound/choices_ui.py`. The dynamic two-option-minimum entry UX it
> described was never rebuilt.

### Server-Side Parsing

The `_parse_options_from_form()` helper in `/adapters/inbound/choices_ui.py`:
- Parses `options[0].title`, `options[0].description`, etc.
- Validates minimum 2 options (returns 400 if fewer)
- Converts to `ChoiceOptionCreateRequest` objects

### Static Option Lists

Choice types and domains are module-level constants in `choices_ui.py` (not service calls):

```python
CHOICE_TYPES = ["binary", "multiple", "ranking", "strategic", "operational"]
DOMAINS = ["personal", "business", "health", "finance", "social"]
```

### List-Page Stats

List-page stats (counts + average satisfaction) are computed directly from the fetched choice list in `ui/activities/choices_views.py` (`StatsGrid`); per-choice outcome data (`actual_outcome`, `satisfaction_score`, `lessons_learned`) renders on the detail page.

## Code Examples

### Create Choice with Options

```python
from core.models.choice.choice_request import (
    ChoiceCreateRequest,
    ChoiceOptionCreateRequest
)
from core.models.choice.choice import ChoiceType
from core.models.enums import Domain, Priority

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
- `entities_rich["choices"]` - Full choice data with graph context

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
| `get_by_category(category, user_uid)` | Filter by category field |
| `get_by_relationship(related_uid, rel, dir)` | Graph traversal |
| `graph_aware_faceted_search(request)` | Unified search with graph context |

### Domain-Specific Methods

| Method | Description |
|--------|-------------|
| `get_pending(user_uid)` | Undecided choices |
| `get_needing_decision(user_uid, days=7)` | Choices with deadline approaching |
| `get_prioritized(user_uid, limit=10)` | Smart prioritization |

**Full catalog:** [Search Service Methods Reference](/docs/reference/SEARCH_SERVICE_METHODS.md)

## Intelligence Service

`ChoicesIntelligenceService` provides decision support and analysis:

| Method | Description |
|--------|-------------|
| `get_with_context(uid)` | Choice with full graph neighborhood (shared mechanism B) |
| `get_decision_intelligence(uid)` | AI-powered decision insights |
| `analyze_choice_impact(uid)` | Impact analysis across domains |

**See:** [Intelligence Services Index](/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md)

## See Also

- [Principles Domain](principles.md) - Principles guide choices
- [Goals Domain](goals.md) - Choices affect goals
- [Knowledge (KU) Domain](ku.md) - Knowledge informs choices
- [Tasks Domain](tasks.md) - Tasks implement choices
- [Intelligence Services Index](/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md)
