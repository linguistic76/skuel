---
title: PS (Path Step) Domain
created: 2025-12-04
updated: 2026-01-11
status: current
category: domains
tags:
- ps
- path-step
- curriculum-domain
- domain
- adr-030
related_skills:
- curriculum-domains
---

# PS (Path Step) Domain

**Type:** Curriculum Domain (2 of 4)
**UID Prefix:** `ls:`
**Entity Label:** `Ls`
**Topology:** Collection (a collection of lessons)

## Purpose

**Skill:** [@curriculum-domains](../../.claude/skills/curriculum-domains/SKILL.md)

Path Steps are collections of lessons within a learning path. They aggregate lessons into a coherent learning experience with practice opportunities (habits, tasks, events).

## Service Architecture (ADR-030)

PsService coordinates 4 common sub-services via factory:

| Sub-service | Class | Purpose |
|-------------|-------|---------|
| `.core` | PsCoreService | CRUD operations |
| `.search` | PsSearchService | Discovery operations |
| `.relationships` | UnifiedRelationshipService | Step-path associations |
| `.intelligence` | PsIntelligenceService | Readiness, practice analysis |

**Initialization:** Uses `create_curriculum_sub_services()` factory (standard signatures)
**graph_intel:** REQUIRED (fail-fast validation)

```python
from core.services.ps_service import PsService

# In services_bootstrap.py
ps_service = PsService(
    driver=driver,
    graph_intel=graph_intelligence,  # REQUIRED
    event_bus=event_bus,
)

# Access sub-services
await ps_service.core.create_step(step)
await ps_service.search.search(query)
await ps_service.relationships.get_related_uids("in_paths", step_uid)
await ps_service.intelligence.is_ready(step_uid, completed_steps)
```

## Key Files

| Component | Location |
|-----------|----------|
| Facade | `/core/services/ps_service.py` |
| Core Service | `/core/services/ps/ps_core_service.py` |
| Search Service | `/core/services/ps/ps_search_service.py` |
| Intelligence Service | `/core/services/ps/ps_intelligence_service.py` |
| Backend | `PsBackend` in `/adapters/persistence/neo4j/domain_backends.py` (71+ methods via 5 mixins + 4 search queries) |
| Model | `/core/models/pathways/path_step.py` |
| DTO | `/core/models/pathways/path_step_dto.py` |
| Relationship Config | `PS_CONFIG` in `/core/models/relationship_registry.py` |
| Factory | `/core/services/curriculum_domain_config.py` |

## Model Fields

| Field | Type | Description |
|-------|------|-------------|
| `uid` | `str` | Unique identifier |
| `title` | `str` | Step title |
| `intent` | `str?` | Learning intent/goal |
| `description` | `str?` | Step description |
| `sequence` | `int` | Order within learning path |
| `estimated_minutes` | `int` | Estimated completion time |
| `mastery_threshold` | `float` | Required mastery (0.0-1.0) |

## Relationships

| Relationship | Direction | Target | Description |
|--------------|-----------|--------|-------------|
| `CONTAINS_KNOWLEDGE` | Outgoing | Ku | Knowledge units in this step |
| `HAS_STEP` (incoming) | Incoming | Lp | Parent learning path (via `in_paths` key) |
| `REQUIRES_STEP` | Outgoing | Ls | Prerequisite steps |
| `REQUIRES_KNOWLEDGE` | Outgoing | Ku | Prerequisite knowledge (`{type: 'prerequisite'}`) |
| `BUILDS_HABIT` | Via Lesson | Habit | Practice via habits (on Lessons, PS inherits via HAS_LESSON traversal) |
| `ASSIGNS_TASK` | Via Lesson | Task | Practice via tasks (on Lessons, PS inherits via HAS_LESSON traversal) |
| `SCHEDULES_EVENT` | Via Lesson | Event | Practice via events (on Lessons, PS inherits via HAS_LESSON traversal) |
| `GUIDED_BY_PRINCIPLE` | Via Lesson | Principle | Values-based guidance (on Lessons, PS inherits via HAS_LESSON traversal) |
| `INFORMS_CHOICE` | Via Lesson | Choice | Decision points (on Lessons, PS inherits via HAS_LESSON traversal) |

## Intelligence Methods

PsIntelligenceService provides:

| Method | Returns | Description |
|--------|---------|-------------|
| `is_ready(ps_uid, completed_uids)` | `bool` | Check if prerequisites are met |
| `get_practice_summary(ps_uid)` | `dict` | Count habits, tasks, events |
| `practice_completeness_score(ps_uid)` | `float` | 0.0-1.0 practice score |
| `calculate_guidance_strength(ps_uid)` | `float` | Principles + Choices alignment |
| `has_prerequisites(ps_uid)` | `bool` | Has REQUIRES_STEP or REQUIRES_KNOWLEDGE |
| `has_guidance(ps_uid)` | `bool` | Has GUIDED_BY_PRINCIPLE or INFORMS_CHOICE (via Lessons) |
| `has_practice_opportunities(ps_uid)` | `bool` | Has habits, tasks, or events |

## Cross-Domain: Practice Infrastructure

Activity domain relationships (BUILDS_HABIT, ASSIGNS_TASK, SCHEDULES_EVENT, GUIDED_BY_PRINCIPLE, INFORMS_CHOICE) live on **Lessons**, not directly on PS. Path Steps inherit these connections via `(PS)-[:HAS_LESSON|CONTAINS_KNOWLEDGE]->(Lesson)` graph traversal. This means practice and guidance coverage is authored at the Lesson level and automatically aggregated at the PS level.

```
PS (Path Step)
 └── HAS_LESSON ──→ Lesson
                     ├── BUILDS_HABIT ──→ Habit    "Practice this daily"
                     ├── ASSIGNS_TASK ──→ Task     "Do this concrete thing"
                     └── SCHEDULES_EVENT → Event   "Attend this experience"
```

### Per-Step Practice Analysis

`PsIntelligenceService` provides methods that measure practice coverage for individual steps:

| Method | Returns | Description |
|--------|---------|-------------|
| `get_practice_summary(ps_uid)` | `dict` | `{"habits": int, "tasks": int, "events": int, "goals": int, "principles": int, "choices": int, "total": int}` |
| `practice_completeness_score(ps_uid)` | `float` | 0.0-1.0 — each of 6 activity domains contributes 1/6 |
| `has_practice_opportunities(ps_uid)` | `bool` | True if any practice relationship exists on constituent Lessons |

These methods traverse through Lessons via HAS_LESSON:

```cypher
MATCH (ls:Entity {uid: $ps_uid})
OPTIONAL MATCH (ls)-[:HAS_LESSON|CONTAINS_KNOWLEDGE]->(l1)-[:BUILDS_HABIT]->(h)
OPTIONAL MATCH (ls)-[:HAS_LESSON|CONTAINS_KNOWLEDGE]->(l2)-[:ASSIGNS_TASK]->(t)
OPTIONAL MATCH (ls)-[:HAS_LESSON|CONTAINS_KNOWLEDGE]->(l3)-[:SCHEDULES_EVENT]->(e)
OPTIONAL MATCH (ls)-[:HAS_LESSON|CONTAINS_KNOWLEDGE]->(l4)-[:SUPPORTS_GOAL]->(g)
OPTIONAL MATCH (ls)-[:HAS_LESSON|CONTAINS_KNOWLEDGE]->(l5)-[:GUIDED_BY_PRINCIPLE]->(p)
OPTIONAL MATCH (ls)-[:HAS_LESSON|CONTAINS_KNOWLEDGE]->(l6)-[:INFORMS_CHOICE]->(c)
RETURN count(DISTINCT h) as habits,
       count(DISTINCT t) as tasks,
       count(DISTINCT e) as events,
       count(DISTINCT g) as goals,
       count(DISTINCT p) as principles,
       count(DISTINCT c) as choices
```

### LP-Level Consumption

These per-step methods are the building blocks for LP-level practice gap analysis.
When learning paths have content with practice relationships on Lessons,
`LpIntelligenceService.identify_practice_gaps()` will iterate through path steps
and aggregate these scores into a path-wide coverage report.

See: [LP Domain: Future Practice Gap Analysis](lp.md#future-practice-gap-analysis)

### Knowledge Substance Connection

Practice relationships are how SKUEL measures whether knowledge is being *lived*, not
just studied. A step with all three types (habit + task + event) has full practice coverage.
A step with none is pure theory — valuable but incomplete without embodiment.

See: [Knowledge Substance Philosophy](../architecture/knowledge_substance_philosophy.md)

## Relationship Config

PS uses `PS_CONFIG` from the relationship registry:

```python
from core.models.relationship_registry import PS_CONFIG

config = PS_CONFIG
# Defines: in_paths, knowledge, prerequisites, practice relationships
```

## Related ADRs

- [ADR-023: Curriculum BaseService Migration](../decisions/ADR-023-curriculum-base-service.md)
- [ADR-024: BaseAnalyticsService Migration](../decisions/ADR-024-base-intelligence-service.md)
- [ADR-030: Curriculum Domain Unification](../decisions/ADR-030-curriculum-domain-unification.md)

## See Also

- [KU Domain](ku.md) - KUs are aggregated into steps
- [LP Domain](lp.md) - LPs contain steps
- [Curriculum Grouping Patterns](../architecture/CURRICULUM_GROUPING_PATTERNS.md)
