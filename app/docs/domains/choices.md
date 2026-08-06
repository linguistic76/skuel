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

Payloads below are the dataclass fields, minus the `occurred_at` / `metadata`
every event carries.

| Event | Trigger | Data |
|-------|---------|------|
| `ChoiceCreated` | Choice created — from `ChoicesCoreService.create`, so both create doors fire it | `choice_uid`, `user_uid`, `choice_description`, `domain`, `urgency` |
| `ChoiceUpdated` | Choice modified, incl. option add/update/remove | `choice_uid`, `user_uid`, `updated_fields` |
| `ChoiceMade` | Decision selected | `choice_uid`, `user_uid`, `selected_option`, `confidence` |
| `ChoiceOutcomeRecorded` | Outcome evaluated | `choice_uid`, `user_uid`, `outcome_quality`, `lessons_learned` |

**Event handling:** `ChoiceEventHandlerService` subscribes to `ChoiceOutcomeRecorded` (outcome quality analysis, principle alignment correlation) and `ChoiceMade` (decision pattern tracking, confidence analysis, insight persistence). Other services subscribe for UserContext invalidation.

## UI Routes

Live in `adapters/inbound/choices_ui.py`: list `/choices` and detail
`/choices/detail` (registered via `create_activity_ui_routes`), plus
`GET|POST /choices/create` and `GET|POST /choices/edit` rendered by
`ui/activities/choices_form.py`.

## Options at Creation

**Options are optional at creation. A supplied set must hold at least 2, and a
BINARY choice that carries options must carry exactly 2.**

Both create doors carry nested `options` and enforce that rule identically — they
did not always, see *History* below.

### The two doors

| Door | Path | Options | Rules |
|------|------|---------|-------|
| API — generated CRUD route | `CRUDRouteFactory` → `ConversionServiceV2.choice_create_to_pure` → `ChoicesService.create` | carried | enforced |
| Facade — UI form, DSL, learning guidance | `ChoicesService.create_choice` → `ChoicesCoreService.create_choice` | carried | enforced |

Both converge on `ChoicesCoreService.create`, the one create primitive: it calls
`CrudOperationsMixin.create` (which is what runs `_validate_create`), then
publishes `ChoiceCreated` and the ADR-074 embedding refresh. `ChoicesService.create`
exists solely to route the generated route into it — the same reconciliation
`ChoicesService.update`/`update_for_user` make on the update path.

Both doors build the entity through the **same converter**
(`ConversionServiceV2.choice_create_to_pure`), so neither can quietly drop a
request field the other keeps.

### Why optional, not required

`_validate_create` reads "at least 2" as a property of a choice that *has*
options, not a precondition for creating one, because three live doors create
optionless choices on purpose:

- **The create form** (`ui/activities/choices_form.py`) omits the nested `options`
  list and every free-text list field — they hit the FormGenerator list-input bug
  and belong on the detail page. Options are added afterwards via `add_option`.
- **DSL activity ingestion** (`core/services/dsl/activity_domain_converters.py`)
  builds a `ChoiceCreateRequest` from one line of prose with no options, and infers
  `BINARY` from keywords like "should i" / "whether" — so optionless BINARY drafts
  are normal and must be accepted.
- **Learning guidance** (`ChoicesLearningService`) creates from a request that need
  not carry options.

Requiring 2 up front would reject every choice those doors make. The `>= 2` floor
is enforced from then on by `remove_option` and `_validate_update`.

`STRATEGIC` choices additionally require a 50+ character description — a rule that
only became reachable when the create paths were reconciled.

The dynamic add/remove option entry UX once provided by the `choiceOptions()`
Alpine component (deleted in `327f26623`, 2026-03-28, with the `ui/choices/`
directory) has not been rebuilt; `add_option` on the detail page is the path.

### History

Until this reconciliation the two doors disagreed, and neither validated:

- The API door's converter built `ChoiceOption` values and persisted them, but
  `_validate_create` resolved to the base no-op — the rules live on
  `ChoicesCoreService`, which the facade holds as the delegated attribute
  `self.core` and does **not** inherit, so the override was never in the facade's
  MRO. That door also published no `ChoiceCreated` event.
- The facade door hand-listed fields onto `ChoiceDTO.create_choice`, which takes
  `**kwargs` — so `options`, `choice_type`, `decision_criteria`, `constraints`,
  `stakeholders` and `tags` were all dropped in silence. It persisted through
  `_create_and_convert`, which calls `backend.create` directly and never enters
  `CrudOperationsMixin.create`, so no rule ran there either.

Pinned by `tests/unit/test_choice_create_path_parity.py`.

### List-Page Stats

List-page stats (counts + average satisfaction) are computed directly from the fetched choice list in `ui/activities/choices_views.py` (`ChoiceStatsBar`, rendered via `StatsGrid`); per-choice outcome data (`actual_outcome`, `satisfaction_score`, `lessons_learned`) renders on the detail page.

## Code Examples

### Create Choice with Options

The nested option model is `ChoiceOptionRequest`.

```python
from core.models.choice.choice_request import (
    ChoiceCreateRequest,
    ChoiceOptionRequest,
)
from core.models.enums import Domain, Priority
from core.models.enums.choice_enums import ChoiceType

# Create request with options
choice_request = ChoiceCreateRequest(
    title="Which web framework to use?",
    description="Choosing framework for new project",
    choice_type=ChoiceType.MULTIPLE,
    domain=Domain.TECH,
    priority=Priority.HIGH,
    options=[
        ChoiceOptionRequest(
            title="FastHTML",
            description="Python-native, hypermedia-driven"
        ),
        ChoiceOptionRequest(
            title="Django",
            description="Full-featured, batteries included"
        ),
        ChoiceOptionRequest(
            title="Flask",
            description="Minimal, flexible"
        ),
    ]
)

result = await choices_service.create_choice(choice_request, user_uid)
choice = result.value
assert len(choice.options) == 3  # carried through both create doors
```

Omitting `options` is equally valid — the create form and DSL ingestion both do —
and yields a draft whose options are added later via `add_option`.

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
