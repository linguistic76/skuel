# Activity Domains Skill

> Use when building features for Tasks, Goals, Habits, Choices, or Principles (the 5 Activity Domains). For Events, see also: Events is a cross-cutting scheduling/integration layer — it shares this infrastructure but serves the Activity Domains rather than being a peer.

## When to Use This Skill

- Adding new features to any Activity Domain
- Creating new UI routes or views
- Implementing service methods
- Understanding cross-domain relationships
- Debugging domain-specific issues

## The 5 Activity Domains

All 5 follow **identical architecture** - learn one, know all:

| Domain | Purpose | UID Prefix | Special Features |
|--------|---------|------------|------------------|
| **Tasks** | Work items with dependencies | `task_{slug}_{random}` | Progress tracking, scheduling |
| **Goals** | Desired outcomes | `goal_{slug}_{random}` | Milestones, progress percentage |
| **Habits** | Recurring behaviors | `habit_{slug}_{random}` | Streak tracking, habit loop (cue/craving/response/reward) |
| **Choices** | Decisions | `choice_{slug}_{random}` | Options at creation, outcome tracking |
| **Principles** | Core values | `principle_{slug}_{random}` | Reflections, alignment tracking |

**Events** shares this infrastructure (BaseService, DomainConfig, UserOwnedEntity) but is classified as a **Scheduling / Integration Domain** — it gives activities a time-bound, schedulable form rather than being a pure Activity Domain peer.

## Architecture Overview

```
User Request → FastHTML Route → Service Facade → Sub-service → Backend → Neo4j
                    ↓
              View Component (HTMX response)
```

**Each domain has:**
- **Facade Service** - Single entry point (`{domain}_service.py`)
- **5-7 Sub-services** - Specialized functionality (core, search, intelligence, etc.)
- **Domain Events** - Cross-service communication
- **Three-View UI** - List, Create, Analytics tabs

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

adapters/inbound/{domain}_ui.py    # Routes
ui/{domain}/views.py               # View components
core/events/{domain}_events.py     # Domain events
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
- [FOURTEEN_DOMAIN_ARCHITECTURE.md](/docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md) - Complete domain architecture (14 domains)
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
