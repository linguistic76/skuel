---
title: Choices Domain
created: 2025-12-04
updated: 2026-11-12
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
| UI Routes | `/adapters/inbound/choices_ui.py` |
| View Components | `/ui/activities/choices_views.py` |

## Domain Enums

| Enum | Import | Values | YAML Field |
|------|--------|--------|------------|
| `ChoiceType` | `core.models.enums` | BINARY, MULTIPLE, RANKING, ALLOCATION, STRATEGIC, OPERATIONAL | `choice_type` |
| `Priority` | `core.models.enums` | LOW, MEDIUM, HIGH | `priority` |

**See:** [Enum Architecture](../architecture/ENUM_ARCHITECTURE.md)

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

Graph relationship methods (`link_choice_to_goal/habit/principle`, `unlink_choice_from_principle`, `create_semantic_choice_relationship`, `find_choices_aligned_with_principle`) are inline on `ChoicesService` directly — inlined June 2026 per the decomposition floor rule.

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
| `status` | `EntityStatus` | `draft`, `active`, `completed`, `archived` (the decision stages are read from fields, § Decision Tracking) |
| `priority` | `Priority` | Low, Medium, High, Critical |
| `domain` | `Domain` | Personal, Business, Health, Finance, Social |
| `options` | `list[ChoiceOptionDTO]` | Available options (see below) |
| `selected_option_uid` | `str?` | UID of chosen option |
| `decision_context` | `str?` | The circumstance forcing the decision — authored up front, survives whichever option wins |
| `decision_rationale` | `str?` | Why this option was chosen — written at decision time by `make_decision` |
| `decision_confidence` | `float?` | How sure the learner was, 0.0-1.0 (the decide form's five levels) — written at decision time by `make_decision`; none when unstated |
| `decision_criteria` | `list[str]` | Criteria for evaluation |
| `constraints` | `list[str]` | Constraints to consider |
| `stakeholders` | `list[str]` | Affected stakeholders |
| `decision_deadline` | `datetime?` | When decision is needed |
| `decided_at` | `datetime?` | When decision was made |
| `satisfaction_score` | `int?` | How satisfied the learner is with how it turned out (`SatisfactionScale`, 1-5) |
| `actual_outcome` | `str?` | What happened |
| `lessons_learned` | `list[str]` | Lessons learned, one per item |

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
| `goals` | `AFFECTS_GOAL` | Goal | Goals affected by choice |
| `learning_paths` | `OPENS_LEARNING_PATH` | Lp | Learning paths opened by choice |

### Incoming (Other → Choice)

| Key | Relationship | Source | Description |
|-----|--------------|--------|-------------|
| `inspired_choices` | `INSPIRED_BY_CHOICE` | Goal | Goals this choice inspired |
| `implementing_tasks` | `IMPLEMENTS_CHOICE` | Task | Tasks implementing this choice |
| `informing_principles` | `INFORMS_CHOICE` | Principle | Principles that inform this choice (YAML: `connections.informing_principles`). One edge per principle ↔ choice link, read from the principle as `informed_choices` |
| `informing_habits` | `INFORMS_CHOICE` | Habit | Habits that inform this choice |

`INFORMS_CHOICE` has three kinds of source — principles, habits and PathSteps (`choice_uids`) — so
each choice view names its kind: a keyed read of `informing_principles` returns principles only, and
`informing_habits` habits only. A PathStep that informs the choice is on no choice view.

`related_choices` is a shared-neighbour view: other choices that affect the same goal
(`AFFECTS_GOAL`). `generate_graph_enrichment` leaves it out of the patterns it computes, as it
leaves out every shared-neighbour view (no search service reads those patterns today).

## Events/Publishing

The Choices domain publishes domain events for cross-service communication:

Payloads below are the dataclass fields, minus the `occurred_at` / `metadata`
every event carries.

| Event | Trigger | Data |
|-------|---------|------|
| `ChoiceCreated` | Choice created — from `ChoicesCoreService.create`, so both create doors fire it | `choice_uid`, `user_uid`, `choice_description`, `domain`, `urgency` |
| `ChoiceUpdated` | Choice modified, incl. option add/update/remove | `choice_uid`, `user_uid`, `updated_fields` |
| `ChoiceMade` | Decision selected | `choice_uid`, `user_uid`, `selected_option`, `confidence` (the stored `decision_confidence`, `None` when unstated) |
| `ChoiceOutcomeRecorded` | An outcome recorded on a decided choice | `choice_uid`, `user_uid`, `outcome_quality` (0.0-1.0, the satisfaction rescaled: `core.models.choice.choice.outcome_quality`), `lessons_learned` (one per line) |

**Event handling:** `ChoiceEventHandlerService` subscribes to `ChoiceOutcomeRecorded` (outcome quality analysis, principle alignment correlation) and `ChoiceMade` (decision pattern tracking, confidence analysis, insight persistence). `ChoiceMade` also runs the PathStep engagement's auto-complete check (`_AutoCompletionHandler.on_choice_made`): a spawned choice is done for its engagement once decided. Every choice event invalidates the owner's UserContext.

## UI Routes

Live in `adapters/inbound/choices_ui.py`: list `/choices` and detail
`/choices/detail` (registered via `create_activity_ui_routes`), plus
`GET|POST /choices/create` and `GET|POST /choices/edit` rendered by
`ui/activities/choices_form.py`.

The detail page's Options section (`OptionsSection`, `ui/activities/choices_views.py`)
and its Outcome section (`OutcomeSection`) carry four controls, each a door in
`adapters/inbound/choices_api.py` that verifies the owner, reads JSON or the form through
`parse_body`, and answers the page with its detail view re-rendered:

| Control | Door | Body |
|---|---|---|
| Add an option | `POST /api/choices/{uid}/options` | `ChoiceOptionRequest` |
| Remove an option (×) | `POST /api/choices/{uid}/options/{option_uid}/remove` | none |
| Decide | `POST /api/choices/{uid}/decide` | `ChoiceDecisionRequest` |
| How did it turn out? | `POST /api/choices/{uid}/outcome` | `ChoiceEvaluationRequest` |

Add and remove show while `Choice.options_open()`; remove only where removing leaves two
options. The decide form shows on a pending choice with two options or more: one radio
per option, an optional rationale, and how sure the learner is (five levels,
`DECISION_CONFIDENCE_LEVELS`). A decided choice shows its options with the selected one
marked, and its outcome form: how satisfied the learner is (`SATISFACTION_LEVELS`), what
happened, and the lessons, one per line. Once an outcome is recorded the page shows it,
and the same form, filled in, updates it. Open or closed, a decided choice takes an
outcome.

The list card (`ChoiceCard`) closes a choice and reopens it, through the status door
`POST /api/choices/{uid}/status`: an open choice is marked completed; a completed one
reopens `active` when a decision is recorded and `draft` when it was closed without one.
The detail page has no close control, as no Activity detail page does.

## Options at Creation

**Options are optional at creation. A supplied set must hold at least 2, and a
BINARY choice that carries options must carry exactly 2.**

Both create doors carry nested `options` and enforce that rule identically — they
did not always, see *History* below.

### The two doors

| Door | Path | Options | Rules |
|------|------|---------|-------|
| API — generated CRUD route | `CRUDRouteFactory` → `ConversionServiceV2.choice_create_to_pure` → `ChoicesService.create` | carried | enforced |
| Facade — UI form, DSL | `ChoicesService.create_choice` → `ChoicesCoreService.create_choice` | carried | enforced |

Both converge on `ChoicesCoreService.create`, the one create primitive: it calls
`CrudOperationsMixin.create` (which is what runs `_validate_create`), then
publishes `ChoiceCreated` and the ADR-074 embedding refresh. `ChoicesService.create`
exists solely to route the generated route into it — the same reconciliation
`ChoicesService.update`/`update_for_user` make on the update path.

Both doors build the entity through the **same converter**
(`ConversionServiceV2.choice_create_to_pure`), so neither can quietly drop a
request field the other keeps.

Only the request door holds `informed_by_knowledge_uids`. It writes them as
`INFORMED_BY_KNOWLEDGE` edges through the admission guard
(`keep_permitted_link_edges`: the uid exists, is unowned or the caller's, and is a
Ku) before announcing the choice, and credits knowledge substance only for the
edges it wrote.

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

Options are added and removed on the detail page (see *UI Routes*).

### History

Until this reconciliation the two doors disagreed, and neither validated:

- The API door's converter built `ChoiceOption` values and persisted them, but
  `_validate_create` resolved to the base no-op — the rules live on
  `ChoicesCoreService`, which the facade holds as the delegated attribute
  `self.core` and does **not** inherit, so the override was never in the facade's
  MRO. That door also published no `ChoiceCreated` event.
- The facade door hand-listed fields onto `ChoiceDTO.create_choice`, which takes
  `**kwargs` — so `options`, `choice_type`, `decision_criteria`, `constraints`,
  `stakeholders` and `tags` were all dropped in silence. It persisted through the
  since-deleted `_create_and_convert`, which called `backend.create` directly and
  never entered `CrudOperationsMixin.create`, so no rule ran there either.

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

Refused, with the choice unchanged, when the choice is already decided, holds fewer than
two options, or `selected_option_uid` is not one of its options. `confidence` is stored as
`decision_confidence` and carried on `ChoiceMade`; left out, nothing is stored and the event
carries `None`, so no confidence category or high-confidence insight follows.

### Record the Outcome

```python
from core.models.choice.choice_request import ChoiceEvaluationRequest

result = await choices_service.evaluate_choice_outcome(
    choice.uid,
    ChoiceEvaluationRequest(
        satisfaction_score=4,
        actual_outcome="Shipped in two weeks",
        lessons_learned=["Prototype the hardest page first"],
    ),
)
```

Refused, with the choice unchanged, when the choice is not decided. The write carries the
three outcome fields alone, planned from the choice under its lock, so it writes no status;
a later outcome replaces the earlier one. Publishes `ChoiceOutcomeRecorded`.

### Add Option Later

```python
from core.models.choice.choice_request import ChoiceOptionRequest

result = await choices_service.add_option(
    choice.uid,
    ChoiceOptionRequest(
        title="Next.js",
        description="React-based with SSR",
        feasibility_score=0.7,
        risk_level=0.4,
    ),
)
```

The option is built by `ConversionServiceV2.choice_option_from_request`, the builder the
create door uses, so an option added later is stored exactly like one created with the
choice. Each option write (`add_option`, `update_option`, `remove_option`) and the
decision are planned from the choice under its lock
(`rewrite_under_lock`), and an option write carries the options
alone.

### Link a Principle

```python
result = await choices_service.link_choice_to_principle(
    choice_uid=choice.uid,
    principle_uid="principle.continuous-learning",
)
```

Writes `(Principle)-[:INFORMS_CHOICE]->(Choice)` — the one principle ↔ choice edge, with no
properties. The principle's own door (`POST /api/principles/link`, `link_type=choice`) and
`POST /api/choices/link-principle` both write it, as do a choice file's
`connections.informing_principles` and a principle file's `connections.informs_choice`, so the link
shows on both pages whichever door made it. Choice create has no principle field, and the DSL's
`@context(choice) @link(principle:…)` is parsed and dropped (both registered in the
[Activity Links registered residuals](../roadmap/activity-links-registered-residuals.md#1-link-doors-and-the-dsl), item 18).
`unlink_choice_from_principle(uid, principle_uid)` removes the link and leaves a habit's informing
link to the same choice alone; no HTTP route calls it.

## Cross-Domain Mappings

| Field | Target Label | Relationships |
|-------|--------------|---------------|
| `knowledge` | Ku | `INFORMED_BY_KNOWLEDGE` |
| `informing_principles` | Principle | `INFORMS_CHOICE` (incoming) |
| `goals` | Goal | `AFFECTS_GOAL` |

## Query Intent

**Default:** `QueryIntent.HIERARCHICAL`

| Context | Intent |
|---------|--------|
| `context` | `HIERARCHICAL` |
| `impact` | `HIERARCHICAL` |

## MEGA-QUERY Sections

- `pending_choice_uids` - UIDs of the choices awaiting a decision (`Choice.is_pending()`)
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

A Choice's `status` is one of `draft` / `active` / `completed` / `archived`. The decision
stages are not statuses — they are read from the choice's fields:

| Stage | How it is read | Key Fields |
|-------|----------------|------------|
| **Pending** | `Choice.is_pending()` — not decided and not archived | `options`, `decision_criteria`, `constraints` |
| **Decided** | `Choice.is_decided()` — a `decided_at`, or status `completed` | `selected_option_uid`, `decision_rationale`, `decision_confidence`, `decided_at` |
| **Implemented** | `(Task)-[:IMPLEMENTS_CHOICE]->(Choice)` edges | — |
| **Evaluated** | an outcome is recorded (`evaluate_choice_outcome`, the page's outcome form), open or closed | `satisfaction_score`, `actual_outcome`, `lessons_learned` |

A decided choice stays `active` until it is completed. An archived choice that was never
decided is neither pending nor decided. A decision is recorded once: `make_decision`
refuses a decided choice, and a decided choice's options are frozen
(`Choice.options_open`), its type with them.

**Closing.** A decided choice is completed or archived, and reopened, like any activity
(`update_choice`, which stamps `completed_at` on completion and clears it on reopen). It
never goes back to `draft` once a decision is recorded: `update_choice` refuses that
target, asked of the choice under its lock, so an archived decided choice is refused too.
A choice closed without a decision reopens as a draft.

**A spawned choice** (a PathStep engagement's, from a `ChoiceTemplate`) starts an undecided
`draft` without the template's `decision_rationale`, as one the learner creates does:
`CHOICE_SPEC.uncopied_fields` (`core/services/ps_engagement/_spawn_orchestrator.py`). The list page and its stats bar, the daily plan's
stats, and the decision-rate analytics call the two methods; `ChoicesBackend.get_pending_choices` /
`get_choices_needing_decision` / `get_stats_for_user` and UserContext's `pending_choice_uids`
compose their Cypher spelling (`adapters/persistence/neo4j/query/cypher/choice_fragments.py`).

## Search Methods

**Service:** `ChoicesSearchService` (`/core/services/choices/choices_search_service.py`)

Its methods with their real signatures, its search fields, and which of its methods are staged: [Search Service Methods § ChoicesSearchService](../reference/SEARCH_SERVICE_METHODS.md#choicessearchservice). That catalog is generated from the class, so it lists only what the class has.

## Intelligence Service

`ChoicesIntelligenceService` provides decision support and analysis:

| Method | Description |
|--------|-------------|
| `get_with_context(uid)` | Choice with full graph neighborhood (shared mechanism B) |
| `get_decision_intelligence(uid)` | AI-powered decision insights |
| `analyze_choice_impact(uid)` | Impact analysis across domains |

**See:** [Intelligence Services Index](../intelligence/INTELLIGENCE_SERVICES_INDEX.md)

## See Also

- [Principles Domain](principles.md) - Principles inform choices
- [Goals Domain](goals.md) - Choices affect goals
- [Knowledge (KU) Domain](ku.md) - Knowledge informs choices
- [Tasks Domain](tasks.md) - Tasks implement choices
- [Intelligence Services Index](../intelligence/INTELLIGENCE_SERVICES_INDEX.md)
