# Activity Domains Skill

> Use when building features for Tasks, Goals, Habits, Events, Choices, or Principles (the 6 Activity Domains).

> All 6 Activity Domains have **list/detail pages and create/edit forms** — Tasks (`/tasks`), Goals (`/goals`), Habits (`/habits`), Events (`/events`; the calendar month/week views at `/cal` are the temporal lenses), Choices (`/choices`), Principles (`/principles`). Each has list + detail views showing the domain's links under its own names for them (the registry's `page_heading` views, both directions, ADR-090 §2), `EntityRelationshipsSection`, HTMX status toggles, and filtering. All are pages of the Tasks+ section — one sidebar (`SidebarPage` via `render_activity_sidebar_page`) with the Tasks+ door (→ `/today`) lit in the chrome; the calendar month/week views and `/today` carry the same list, each calendar view rendering its declared membership (`VIEW_SPECS`: the month shows events only, the week adds habits, goal milestones and high-priority tasks behind the kind legend). Activity data enters through the per-domain create/edit forms (`/{domain}/create`, `/{domain}/edit?uid=`), the JSON API, `/submissions/sync` (Obsidian vault sync) and content-vault ingestion.

## When to Use This Skill

- Adding new features to any Activity Domain
- Implementing service methods
- Understanding cross-domain relationships
- Debugging domain-specific issues

## Design Principle: Harmony Without Over-Generalization

The 6 Activity Domains share one shape — seven common sub-services: `core`, `search`, `relationships`, `intelligence`, `event_handler`, `learning`, `knowledge_intelligence`. Every domain answers to all seven. None opts out. `create_common_sub_services()` builds most of them, but not every slot for every domain: `intelligence` comes from the factory only for Principles (the other five facades construct their own, each with a domain-specific dependency), Tasks also builds its own `core` (`skip={"core"}`) and `event_handler`, and `knowledge_intelligence` is the shared singleton the factory passes through.

**The shared shape is a contract for interconnectivity, not a cage.** What flows across domains — unified search, user context aggregation, cross-domain relationship queries, the knowledge substance pipeline, the ZPD assessment that ties curriculum to lived activity — works *because* every domain exposes the same surface in the same place. When the system asks "what is this user working on today," the answer doesn't care whether it comes from Tasks, Habits, or Events; each is addressable the same way.

**Inside that shape, each domain keeps its voice.** Habits has `completions` and `patterns` because streaks and ritual cadence aren't universal concerns. Events has `habits` (`EventsHabitIntegrationService`) because materializing a recurring habit as discrete calendar events is an Events problem. Principles has `alignment` because assessing goals and habits against a value is unique to values. Several domains carry a `progress`, `scheduling` or `planning` slot, but each is the domain's own class (`TasksSchedulingService` is context-aware task creation; `GoalsSchedulingService` checks goal capacity and timelines): the name is shared, the service is not. Facade mixins organize domain-specific delegation methods the same way: Goals's `_OrchestrationMixin` is about goal mechanics, Principles's `_GravityMixin` about the links a principle attracts — they do not belong on any other domain.

**The harmony enables the uniqueness.** Without the shared shape, every cross-domain operation would fragment into a case statement. Without the domain-specific sub-services, the model would collapse into a generic "thing with a status" — exactly the over-generalization the principle is named against. The pattern: one shape for what a domain owes the rest of the system, total freedom for what it owes itself.

**When adding a capability, ask in this order:**
1. Does it fit in the existing shared shape? (new method on `core` / `search` / `intelligence` / etc.)
2. Is it cross-domain infrastructure all 6 will benefit from? (extend `create_common_sub_services()` — raises the floor for every domain at once, the way the shared `learning` slot does)
3. Is it genuinely domain-specific? (new domain-specific sub-service or facade mixin — keep it out of the shared layer)

**Never** promote a capability only one domain uses into a common sub-service. **Never** push a genuinely domain-specific concern into a shared sub-service to save a file. The seven common services earn their universality by actually being universal; the domain-specific services earn their specialness by actually being specific.

### Two labels, two jobs — `entity_label` + `config_lookup_label`

Each service surfaces **two** label attributes via `DomainConfig`, with distinct responsibilities:

1. **`entity_label`** — Neo4j base-label for multi-label Cypher matching. All 6 Activity Domains set this to `"Entity"` (matches `:Entity:Task`, `:Entity:Habit`, … via the unified `:Entity` base label). Curriculum domains similarly use `"Entity"` (PathStep, LearningPath, Exercise, RevisedExercise) or `"Ku"`.
2. **`config_lookup_label`** — key for `LABEL_CONFIGS` registry lookup. Defaults to `model_class.__name__` (`"Task"`, `"Goal"`, `"Habit"`, …) and is used by `context_operations_mixin.get_with_context()` to fetch the domain-specific `DomainRelationshipConfig`. Also used by factory functions (`create_activity_domain_config`, `create_curriculum_domain_config`) to generate `graph_enrichment_patterns` and `prerequisite_relationships`.

Each Activity Domain has its own `LABEL_CONFIGS` entry, and both factories (`create_activity_domain_config`, `create_curriculum_domain_config`) raise `ValueError` if the `config_lookup_label` is missing from `LABEL_CONFIGS`. Decision record: [ADR-056 Service-Layer Label Split](../../../docs/decisions/ADR-056-service-layer-label-split.md).

**When building a new domain:**
- Set `entity_label="Entity"` (or `"Ku"`) — the Neo4j base label.
- Let `config_lookup_label` default to `model_class.__name__`, or pass it explicitly if your model name diverges from the registry key.
- Ensure `LABEL_CONFIGS` has an entry keyed by your `config_lookup_label` before calling the factory.

## The 6 Activity Domains

All 6 share the facade shape above; the table lists what each adds:

| Domain | Purpose | UID Prefix | Special Features |
|--------|---------|------------|------------------|
| **Tasks** | Work items with dependencies | `task_{slug}_{random}` | Progress tracking, scheduling |
| **Goals** | Desired outcomes | `goal_{slug}_{random}` | Milestones, progress percentage |
| **Habits** | Recurring behaviors | `habit_{slug}_{random}` | Streak tracking, habit loop (cue/craving/response/reward) |
| **Events** | Time commitments | `event_{slug}_{random}` | Habit integration, learning bridge, calendar polymorphism |
| **Choices** | Decisions | `choice_{slug}_{random}` | Options at creation, outcome tracking |
| **Principles** | Core values | `principle_{slug}_{random}` | Reflections, alignment tracking |

Events additionally has `habits` (`EventsHabitIntegrationService`), which materializes a recurring habit as calendar events; its `learning` slot is `EventsLearningService`. The **Calendar** cross-cutting system aggregates Events alongside Tasks, Habits, and Goals — Calendar is the scheduling system, Events are the things being scheduled.

## Knowledge Substance Connections

Each Activity Domain connects to knowledge via YAML `connections.*` fields, feeding the substance tracking pipeline:

| Domain | YAML Field | Relationship | Weight |
|--------|-----------|-------------|--------|
| Task | `connections.applies_knowledge` | APPLIES_KNOWLEDGE | 0.05 (max 0.25) |
| Habit | `connections.reinforces_knowledge` | REINFORCES_KNOWLEDGE | 0.10 (max 0.30) |
| Event | `connections.applies_knowledge` | APPLIES_KNOWLEDGE | 0.05 (max 0.25) |
| Choice | `connections.informed_by_knowledge` | INFORMED_BY_KNOWLEDGE | 0.07 (max 0.15) |
| Principle | `connections.grounded_in_knowledge` | GROUNDED_IN_KNOWLEDGE | 0.07 (max 0.15) |

The weights and caps are `USER_SUBSTANCE_CHANNELS` (`core/services/knowledge/user_substance.py`), which has a sixth, non-Activity channel: UserEntry, 0.07 (max 0.20). The edges come from the `connections.*` frontmatter at ingestion and from the create/update doors. The knowledge events (`KnowledgeAppliedInTask`, `KnowledgePracticedInEvent`, `KnowledgeBuiltIntoHabit`, `KnowledgeInformedChoice`, `KnowledgeReflectedInEntry`, in `core/events/knowledge_substance_events.py`) increment the per-node counters that `Curriculum.substance_score()` reads. Principles have no per-node counter; they count only in the per-user channels. See `/docs/architecture/knowledge_substance_philosophy.md`.

## Cross-Domain UID Fields

Every cross-domain UID field on an Activity Domain model is either a **structural anchor** (persisted to the Neo4j node, written at creation) or an **enrichment link** (DERIVED FROM EDGE — never persisted, populated at read time by a batch enrich step). Confusing the two produces stale denormalized data or phantom traversal.

**Structural anchors** across all 6 Activity Domains:

| Domain | Field | Relationship |
|--------|-------|-------------|
| Task | `fulfills_goal_uid` | Task → Goal hierarchy membership (dual-written with the `FULFILLS_GOAL` edge) |
| Task | `source_path_step_uid` | Spawn-time PS origin (all 6 domains share this) |
| Task | `scheduled_event_uid` | Scheduling appointment to an Event |
| Goal | `fulfills_goal_uid` | Sub-goal → parent goal hierarchy |
| Goal | `selected_choice_option_uid` | Which ChoiceOption inspired this Goal (sub-entity; edge points to the Choice entity) |

**Enrichment links** (DERIVED FROM EDGE — absent from DTO):

| Domain | Field | Edge |
|--------|-------|------|
| Task | `reinforces_habit_uid` | `(Task)-[:REINFORCES_HABIT]->(Habit)` |
| Habit | `supports_goal_uid` | `(Habit)-[:SUPPORTS_GOAL]->(Goal)` |
| Event | `reinforces_habit_uid` | `(Event)-[:REINFORCES_HABIT]->(Habit)` |
| Event | `contributes_to_goal_uid` | `(Event)-[:CONTRIBUTES_TO_GOAL]->(Goal)` |

`source_path_step_uid` is present on all 6 Activity Domains. It serves two purposes: (1) a read-optimization on the `SPAWNED_FROM` 2-hop path for template-spawned activities; (2) the only back-reference for activities created via non-template scheduling paths (no `SPAWNED_FROM` edge exists there). Always read the field; traverse the edge only when you need to interrogate the template itself.

**See:** `/docs/architecture/CROSS_DOMAIN_UID_PATTERNS.md` — complete table, sub-entity variant (`selected_choice_option_uid`), and the rule for adding new cross-domain UID fields.

## Architecture Overview

```
Create/edit forms + JSON API → {Domain}Service facade → sub-service → domain backend → Neo4j
Vault sync (/submissions/sync) + content-vault ingestion → UnifiedIngestionService → Neo4j
List/detail pages (activity_ui_factory) ← facade reads (read path)
```

**Each domain has:**
- **Facade Service** - Single entry point (`{domain}_service.py`)
- **8-13 Sub-services** (counting the FULL-tier `.ai`) - the seven common ones plus the domain's own. `create_common_sub_services()` accepts `skip` names `core`, `search` and `relationships` only (anything else raises `ValueError`). It builds `intelligence` only for a domain whose `ActivityDomainConfig.intelligence_class` is set, which today is only Principles; it always builds `event_handler` and `learning`. The facade's `__init__` is the authority on which slot came from where.
- **1-3 Facade Mixins** - Group related delegation methods by concern. Tasks (1: `_OrchestrationMixin`), Goals (1: `_OrchestrationMixin`), Habits (3: `_CompletionMixin`, `_EnrichmentMixin`, `_OrchestrationMixin`), Events (2: `_OrchestrationMixin`, `_SchedulingMixin`), Choices (1: `_OptionManagementMixin`), Principles (3: `_EmbodimentMixin`, `_GravityMixin`, `_EnrichmentMixin`). Graph link methods sit directly on the facade (the floor rule in `SERVICE_DECOMPOSITION_RULE.md`).
- **Domain Events** - Cross-service communication
- **Event Handler Service** - Fire-and-forget reactive handlers (`*_event_handler_service.py`) — all 6 Activity Domains have dedicated handlers; all persist structured insights to `InsightStore` (Neo4j `Insight` nodes) at key decision points (overdue tasks, priority inflation, goal stalls, rescheduling patterns, etc.). The Learning Loop has a parallel handler (`LearningLoopEventHandlerService`) tracking submission iterations, feedback turnaround, and mastery velocity.
- **UI** — All 6 domains have dedicated list + detail views and create/edit forms with cross-domain connections and `EntityRelationshipsSection`, sharing the Tasks+ sidebar (`ui/activities/nav.py`) — the calendar views too (fluid width, same sidebar). The section's landing is `/today`; it has no hub page. Activity data also viewable via ActivityReport in the GradeBook's Activity reports group (`/gradebook`; detail at `/activity-reports/detail`).

## Key Files Per Domain

```
core/models/{domain}/
├── {domain}.py              # Frozen dataclass model
├── {domain}_dto.py          # Mutable DTO
├── {domain}_request.py      # Pydantic request models
├── {domain}_update_intent.py  # Frozen *UpdateIntent (ADR-066)

core/services/{domain}/
├── {domain}_core_service.py
├── {domain}_search_service.py
├── {domain}_intelligence_service.py
├── _*_mixin.py              # Facade mixins (Goals/Habits/Choices/Principles)
└── ... (domain-specific services)

core/services/{domain}_service.py  # Facade
core/events/{domain}_events.py     # Domain events

# UI (all 6 domains):
adapters/inbound/{domain}_routes.py      # Route wiring (DomainRouteConfig + register_domain_routes)
adapters/inbound/{domain}_ui.py          # ActivityUIConfig + create_activity_ui_routes(), then the create/edit form
                                         #   routes (Tasks adds subtask/dependency fragments, Habits insight/choice fragments)
adapters/inbound/activity_ui_factory.py  # THE shared factory — ActivityUIConfig dataclass + create_activity_ui_routes()
                                         #   Generates 5 routes per domain:
                                         #     /{domain}                — Page shell (HTMX loading placeholder)
                                         #     /{domain}/content        — HTMX fragment: filter bar + list + stats bar
                                         #     /{domain}/list-fragment  — HTMX fragment: filtered list only
                                         #     /{domain}/detail         — Detail page shell (HTMX loading placeholder)
                                         #     /{domain}/detail/content — HTMX fragment: entity detail + connections
                                         #   plus POST /{domain}/dual-track/results for Goals, Habits, Principles
adapters/inbound/{domain}_api.py         # create_activity_field_api_routes (status + priority), hierarchy and
                                         #   link API factories, plus the domain's own routes
ui/activities/nav.py                     # Activity sidebar config + render_activity_sidebar_page()
ui/activities/badges.py, domain_stats_config.py  # Sidebar badge renderers + per-row extractors (/api/sidebar/badges)
ui/activities/{domain}_views.py          # Pure view components (StatsBar, List, Card, DetailView)
ui/activities/{domain}_form.py           # Create/edit forms (render_activity_form)
ui/activities/filter_bar.py              # Shared config-driven filter bar (plain <select>, not <uk-select>)
ui/activities/_shared.py                 # Shared helpers (MetadataField, ConnectionsSection, ConnectionRows, safe_id)
core/utils/entity_filters.py            # filter_tasks/goals/habits/events/choices/principles (business rules)
```

## Common Operations

### Get an entity with context
```python
result = await service.intelligence.get_with_context(uid)  # Result[tuple[T, GraphContext]]
```

### Search with filters
```python
result = await service.search.search(query, limit=50, user_uid=user_uid)
result = await service.search.get_by_status(status, limit=100, user_uid=user_uid)
```

### Link to another domain
The facades name each edge explicitly, and not every domain has every link:
```python
await tasks_service.link_task_to_goal(task_uid, goal_uid)                 # also Choices, Events
await goals_service.link_goal_to_principle(goal_uid, principle_uid)       # also Choices, Habits
```

### Update an entity (ADR-066 — typed intent, never a dict)
```python
from core.models.enums import EntityStatus
from core.models.task import TaskUpdateIntent

await tasks_service.update_task(uid, TaskUpdateIntent(status=EntityStatus.ACTIVE.value))
# from an HTTP body: service.update_for_user(uid, request.to_intent(), user_uid)
```
See [COMMON_PATTERNS.md § How to update an entity](COMMON_PATTERNS.md#how-to-update-an-entity-the-one-path--adr-066) for the full write-path contract.

## Deep Dive Resources

**Architecture:**
- [ENTITY_TYPE_ARCHITECTURE.md](/docs/architecture/ENTITY_TYPE_ARCHITECTURE.md) - Complete domain architecture (entity types)
- [SERVICE_TOPOLOGY.md](/docs/architecture/SERVICE_TOPOLOGY.md) - Service architecture diagrams

**Patterns:**
- [SERVICE_CONSOLIDATION_PATTERNS.md](/docs/patterns/SERVICE_CONSOLIDATION_PATTERNS.md) - Facade delegation patterns
- [OWNERSHIP_VERIFICATION.md](/docs/patterns/OWNERSHIP_VERIFICATION.md) - ContentScope.USER_OWNED pattern
- [TEMPLATES.md](TEMPLATES.md) - Activity Template entities, TemplateBundle, DomainSpawnSpec registry, and template lifecycle

**Intelligence:**
- [INTELLIGENCE_SERVICES_INDEX.md](/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md) - Intelligence services for all 6 activity domains

**Guides:**
- [BASESERVICE_QUICK_START.md](/docs/guides/BASESERVICE_QUICK_START.md) - Service architecture onboarding
- [SUB_SERVICE_CATALOG.md](/docs/reference/SUB_SERVICE_CATALOG.md) - Which service does what

---

## Related Skills

- [result-pattern](../result-pattern/SKILL.md) - All methods return `Result[T]`
- [fasthtml](../fasthtml/SKILL.md) - Route and view patterns
- [neo4j-cypher-patterns](../neo4j-cypher-patterns/SKILL.md) - Graph queries

## Related Documentation

- `/docs/domains/{domain}.md` - Domain-specific docs
- `/docs/patterns/SERVICE_CONSOLIDATION_PATTERNS.md` - Facade patterns
- `/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md` - Intelligence services
