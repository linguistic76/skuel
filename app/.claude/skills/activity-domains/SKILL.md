# Activity Domains Skill

> Use when building features for Tasks, Goals, Habits, Events, Choices, or Principles (the 6 Activity Domains).

> All 6 Activity Domains have **read-focused UI** — Tasks (`/tasks`), Goals (`/goals`), Habits (`/habits`), Events (`/events`), Choices (`/choices`), Principles (`/principles`). Each has list + detail views with cross-domain connection badges, `EntityRelationshipsSection`, HTMX status toggles, and filtering. All share a collapsible Activity sidebar (`SidebarPage` pattern) with hub at `/activities`. Goals and Principles use gravity-well pattern (incoming connections). Activity data enters via bulk upload at `/upload` or admin ingestion. Service facades and backends are fully active.

## When to Use This Skill

- Adding new features to any Activity Domain
- Implementing service methods
- Understanding cross-domain relationships
- Debugging domain-specific issues

## The 6 Activity Domains

All 6 follow **identical architecture** - learn one, know all:

| Domain | Purpose | UID Prefix | Special Features |
|--------|---------|------------|------------------|
| **Tasks** | Work items with dependencies | `task_{slug}_{random}` | Progress tracking, scheduling |
| **Goals** | Desired outcomes | `goal_{slug}_{random}` | Milestones, progress percentage |
| **Habits** | Recurring behaviors | `habit_{slug}_{random}` | Streak tracking, habit loop (cue/craving/response/reward) |
| **Events** | Time commitments | `event_{slug}_{random}` | Habit integration, learning bridge, calendar polymorphism |
| **Choices** | Decisions | `choice_{slug}_{random}` | Options at creation, outcome tracking |
| **Principles** | Core values | `principle_{slug}_{random}` | Reflections, alignment tracking |

Events additionally has integration sub-services (`EventsHabitIntegrationService`, `EventsLearningService`) that bridge it with other Activity types. The **Calendar** cross-cutting system aggregates Events alongside Tasks, Habits, and Goals — Calendar is the scheduling system, Events are the things being scheduled.

## Knowledge Substance Connections

Each Activity Domain connects to knowledge via YAML `connections.*` fields, feeding the substance tracking pipeline:

| Domain | YAML Field | Relationship | Weight |
|--------|-----------|-------------|--------|
| Task | `connections.applies_knowledge` | APPLIES_KNOWLEDGE | 0.05 (max 0.25) |
| Habit | `connections.reinforces_knowledge` | REINFORCES_KNOWLEDGE | 0.10 (max 0.30) |
| Event | `connections.applies_knowledge` | APPLIES_KNOWLEDGE | 0.05 (max 0.25) |
| Choice | `connections.informed_by_knowledge` | INFORMED_BY_KNOWLEDGE | 0.07 (max 0.15) |
| Principle | `connections.grounded_in_knowledge` | GROUNDED_IN_KNOWLEDGE | 0.07 (max 0.15) |

These edges are created at ingestion time from YAML templates. At runtime, domain events (`KnowledgeAppliedInTask`, `KnowledgeBuiltIntoHabit`, etc.) increment substance counters on knowledge nodes. See `/docs/architecture/knowledge_substance_philosophy.md`.

## Architecture Overview

```
User YAML upload (/upload) → UserUploadService → UnifiedIngestionService → Neo4j
Admin YAML/Markdown → UnifiedIngestionService → Service Facade → Backend → Neo4j
ActivityReport UI ← Service Facade (read path)
```

**Each domain has:**
- **Facade Service** - Single entry point (`{domain}_service.py`)
- **6-13 Sub-services** - Specialized functionality (core, search, intelligence, event_handler, etc.)
- **Domain Events** - Cross-service communication
- **Event Handler Service** - Fire-and-forget reactive handlers (`*_event_handler_service.py`) — all 6 Activity Domains have dedicated handlers; all persist structured insights to `InsightStore` (Neo4j `Insight` nodes) at key decision points (overdue tasks, priority inflation, goal stalls, rescheduling patterns, etc.). The Learning Loop has a parallel handler (`LearningLoopEventHandlerService`) tracking submission iterations, feedback turnaround, and mastery velocity.
- **Read-Focused UI** — All 6 domains have dedicated list + detail views with cross-domain connections and `EntityRelationshipsSection`, sharing a collapsible Activity sidebar (`ui/activities/nav.py`). Activity Domains are embedded inline in `/profile` via `ActivityHubView()`. `/activities` redirects 301 → `/profile`. Activity data also viewable via ActivityReport UI at `/activity-reports`.

## Key Files Per Domain

```
core/models/{domain}/
├── {domain}.py              # Frozen dataclass model
├── {domain}_dto.py          # Mutable DTO
├── {domain}_request.py      # Pydantic request models

core/services/{domain}/
├── {domain}_core_service.py
├── {domain}_search_service.py
├── {domain}_intelligence_service.py
└── ... (domain-specific services)

core/services/{domain}_service.py  # Facade
core/events/{domain}_events.py     # Domain events

# Read-focused UI (all 6 domains + hub):
adapters/inbound/activity_hub_routes.py  # /activities → /profile redirect (301)
adapters/inbound/{domain}_routes.py  # Route wiring
adapters/inbound/{domain}_ui.py      # UI Routes (list, detail, HTMX fragment)
adapters/inbound/{domain}_api.py     # API Routes (status toggle)
ui/activities/nav.py                 # Activity sidebar config + render_activity_sidebar_page()
ui/activities/activity_hub.py        # ActivityHubView — 6 domain preview blocks (embedded in /profile)
ui/activities/{domain}_views.py      # Pure view components
```

## Common Operations

### Get an entity with context
```python
result = await service.intelligence.get_{domain}_with_context(uid)
```

### Search with filters
```python
result = await service.search.search(query, limit=50, user_uid=user_uid)
result = await service.search.get_by_status(status, limit=100, user_uid=user_uid)
```

### Link to another domain
```python
await service.link_{domain}_to_goal(entity_uid, goal_uid)
await service.link_{domain}_to_principle(entity_uid, principle_uid)
```

## Deep Dive Resources

**Architecture:**
- [ENTITY_TYPE_ARCHITECTURE.md](/docs/architecture/ENTITY_TYPE_ARCHITECTURE.md) - Complete domain architecture (entity types)
- [SERVICE_TOPOLOGY.md](/docs/architecture/SERVICE_TOPOLOGY.md) - Service architecture diagrams

**Patterns:**
- [SERVICE_CONSOLIDATION_PATTERNS.md](/docs/patterns/SERVICE_CONSOLIDATION_PATTERNS.md) - Facade delegation patterns
- [OWNERSHIP_VERIFICATION.md](/docs/patterns/OWNERSHIP_VERIFICATION.md) - ContentScope.USER_OWNED pattern

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
