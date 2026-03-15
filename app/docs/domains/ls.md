---
title: LS (Learning Step) Domain
created: 2025-12-04
updated: 2026-01-11
status: current
category: domains
tags:
- ls
- learning-step
- curriculum-domain
- domain
- adr-030
related_skills:
- curriculum-domains
---

# LS (Learning Step) Domain

**Type:** Curriculum Domain (2 of 4)
**UID Prefix:** `ls:`
**Entity Label:** `Ls`
**Topology:** Collection (a collection of lessons)

## Purpose

**Skill:** [@curriculum-domains](../../.claude/skills/curriculum-domains/SKILL.md)

Learning Steps are collections of lessons within a learning path. They aggregate lessons into a coherent learning experience with practice opportunities (habits, tasks, events).

## Service Architecture (ADR-030)

LsService coordinates 4 common sub-services via factory:

| Sub-service | Class | Purpose |
|-------------|-------|---------|
| `.core` | LsCoreService | CRUD operations |
| `.search` | LsSearchService | Discovery operations |
| `.relationships` | UnifiedRelationshipService | Step-path associations |
| `.intelligence` | LsIntelligenceService | Readiness, practice analysis |

**Initialization:** Uses `create_curriculum_sub_services()` factory (standard signatures)
**graph_intel:** REQUIRED (fail-fast validation)

```python
from core.services.ls_service import LsService

# In services_bootstrap.py
ls_service = LsService(
    driver=driver,
    graph_intel=graph_intelligence,  # REQUIRED
    event_bus=event_bus,
)

# Access sub-services
await ls_service.core.create_step(step)
await ls_service.search.search(query)
await ls_service.relationships.get_related_uids("in_paths", step_uid)
await ls_service.intelligence.is_ready(step_uid, completed_steps)
```

## Key Files

| Component | Location |
|-----------|----------|
| Facade | `/core/services/ls_service.py` |
| Core Service | `/core/services/ls/ls_core_service.py` |
| Search Service | `/core/services/ls/ls_search_service.py` |
| Intelligence Service | `/core/services/ls/ls_intelligence_service.py` |
| Model | `/core/models/ls/ls.py` |
| DTO | `/core/models/ls/ls_dto.py` |
| Relationship Config | `LS_CONFIG` in `/core/models/relationship_registry.py` |
| Factory | `/core/utils/curriculum_domain_config.py` |

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
| `REQUIRES_KNOWLEDGE` | Outgoing | Ku | Prerequisite knowledge |
| `BUILDS_HABIT` | Outgoing | Habit | Practice via habits |
| `ASSIGNS_TASK` | Outgoing | Task | Practice via tasks |
| `SCHEDULES_EVENT` | Outgoing | Event | Practice via events |
| `GUIDED_BY_PRINCIPLE` | Outgoing | Principle | Values-based guidance |
| `OFFERS_CHOICE` | Outgoing | Choice | Decision points |

## Intelligence Methods

LsIntelligenceService provides:

| Method | Returns | Description |
|--------|---------|-------------|
| `is_ready(ls_uid, completed_uids)` | `bool` | Check if prerequisites are met |
| `get_practice_summary(ls_uid)` | `dict` | Count habits, tasks, events |
| `practice_completeness_score(ls_uid)` | `float` | 0.0-1.0 practice score |
| `calculate_guidance_strength(ls_uid)` | `float` | Principles + Choices alignment |
| `has_prerequisites(ls_uid)` | `bool` | Has REQUIRES_STEP or REQUIRES_KNOWLEDGE |
| `has_guidance(ls_uid)` | `bool` | Has GUIDED_BY_PRINCIPLE or OFFERS_CHOICE |
| `has_practice_opportunities(ls_uid)` | `bool` | Has habits, tasks, or events |

## Cross-Domain: Practice Infrastructure

Learning Steps are where SKUEL's curriculum domain connects to the activity domains.
The three practice relationships bridge "what to learn" with "how to live it":

```
LS (Learning Step)
 ├── BUILDS_HABIT ──→ Habit    "Practice this daily"
 ├── ASSIGNS_TASK ──→ Task     "Do this concrete thing"
 └── SCHEDULES_EVENT → Event   "Attend this experience"
```

### Per-Step Practice Analysis

`LsIntelligenceService` provides methods that measure practice coverage for individual steps:

| Method | Returns | Description |
|--------|---------|-------------|
| `get_practice_summary(ls_uid)` | `dict` | `{"habits": int, "tasks": int, "events": int, "total": int}` |
| `practice_completeness_score(ls_uid)` | `float` | 0.0-1.0 — each type contributes 1/3 |
| `has_practice_opportunities(ls_uid)` | `bool` | True if any practice relationship exists |

These methods query the graph directly:

```cypher
MATCH (ls:LearningStep {uid: $ls_uid})
OPTIONAL MATCH (ls)-[:BUILDS_HABIT]->(h)
OPTIONAL MATCH (ls)-[:ASSIGNS_TASK]->(t)
OPTIONAL MATCH (ls)-[:SCHEDULES_EVENT]->(e)
RETURN count(DISTINCT h) as habits,
       count(DISTINCT t) as tasks,
       count(DISTINCT e) as events
```

### LP-Level Consumption

These per-step methods are the building blocks for LP-level practice gap analysis.
When learning paths have content with practice relationships populated,
`LpIntelligenceService.identify_practice_gaps()` will iterate through path steps
and aggregate these scores into a path-wide coverage report.

See: [LP Domain: Future Practice Gap Analysis](lp.md#future-practice-gap-analysis)

### Knowledge Substance Connection

Practice relationships are how SKUEL measures whether knowledge is being *lived*, not
just studied. A step with all three types (habit + task + event) has full practice coverage.
A step with none is pure theory — valuable but incomplete without embodiment.

See: [Knowledge Substance Philosophy](../architecture/knowledge_substance_philosophy.md)

## Relationship Config

LS uses `LS_CONFIG` from the relationship registry:

```python
from core.models.relationship_registry import LS_CONFIG

config = LS_CONFIG
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
