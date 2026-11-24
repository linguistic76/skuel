---
title: PS (Path Step) Domain
created: 2025-12-04
updated: 2026-11-24
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
**UID Prefix:** `ps.`
**Entity Label:** `PathStep`
**Topology:** Content Unit (composes Kus into a coherent learning experience)

## Purpose

**Skill:** [@curriculum-domains](../../.claude/skills/curriculum-domains/SKILL.md)

PathStep is THE curriculum content entity in SKUEL. It composes atomic Kus into a coherent learning experience with practice opportunities (habits, tasks, events, goals, principles, choices) named on the step as Activity Templates — each learner who engages the step gets their own Activity from each. A step is authored only in the content vault (ADR-091); the app reads it and records what learners do with it. As of 2026-04, the former `Lesson` entity has been merged into `PathStep`.

## Service Architecture (ADR-030)

PsService coordinates 12 factory-built sub-services plus `progress` (built in the facade) and an optional `.ai` slot (FULL tier):

| Sub-service | Class | Purpose |
|-------------|-------|---------|
| `.core` | PsCoreService | Step reads |
| `.search` | PsSearchService | Discovery operations |
| `.graph` | PsGraphService | Graph navigation and relationship reads |
| `.semantic` | PsSemanticService | Semantic relationship reads (takes `intelligence`) |
| `.practice` | PsPracticeService | Practice integration (habits, tasks, events) |
| `.mastery` | PsMasteryService | Mastery tracking |
| `.relationships` | UnifiedRelationshipService | Step-path associations |
| `.intelligence` | PsIntelligenceService | Readiness, practice analysis |
| `.adaptive` | PsAdaptiveService | Personalized curriculum delivery |
| `.application_discovery` | PsApplicationDiscoveryService | Reverse queries: where a step's knowledge is applied |
| `.context_service` | PsContextService | Context-first recommendations from UserContext |
| `.organization` | PsOrganizationService | ORGANIZES hierarchy reads (takes `core`) |
| `.progress` | PsProgressService | Event-driven progress (facade-built) |

**Initialization:** `create_ps_sub_services()` in `core/services/curriculum_domain_config.py` (`PsSubServices` dataclass, fixed creation order — see `SERVICE_CONSOLIDATION_PATTERNS.md` § 6)
**graph_intel:** REQUIRED (fail-fast validation)

```python
from core.services.ps_service import PsService

# In services_bootstrap/_learning_services.py
ps_service = PsService(
    backend=knowledge_backend,
    graph_intel=graph_intelligence,  # REQUIRED
    event_bus=event_bus,
    ku_backend=atomic_ku_backend,
    chunking_service=chunking_service,
    user_service=user_service,
    vector_search_service=vector_search_service,
    embeddings_service=embeddings_service,
    ps_intelligence_backend=PsIntelligenceBackend(query_executor),
)

# Access sub-services
await ps_service.core.get_step(step_uid)
await ps_service.search.search(query)
await ps_service.relationships.get_related_uids("in_paths", step_uid)
await ps_service.intelligence.get_practice_summary(step_uid)
```

## Key Files

| Component | Location |
|-----------|----------|
| Facade | `/core/services/ps_service.py` |
| Core Service | `/core/services/ps/ps_core_service.py` |
| Search Service | `/core/services/ps/ps_search_service.py` |
| Intelligence Service | `/core/services/ps/ps_intelligence_service.py` |
| Backend | `PsBackend` in `/adapters/persistence/neo4j/backends/curriculum_backends.py` (71+ methods via 5 mixins + 4 search queries) |
| Model | `/core/models/pathways/path_step.py` |
| DTO | `/core/models/pathways/path_step_dto.py` |
| Relationship Config | `PS_CONFIG` in `/core/models/relationship_registry.py` |
| Factory | `/core/services/curriculum_domain_config.py` |

## Model Fields

| Field | Type | Description |
|-------|------|-------------|
| `uid` | `str` | Unique identifier (`ps.{namespace}.{slug}`) |
| `title` | `str` | Step title |
| `intent` | `str?` | Learning intent/goal |
| `description` | `str?` | Step description |
| `sequence` | `int` | Order within learning path |
| `estimated_minutes` | `int` | Estimated completion time |
| `mastery_threshold` | `float` | Target mastery the author sets (0.0-1.0) — the same for every learner; a learner's mastery of the step is their `(User)-[:MASTERED]->(PathStep)` edge |

## Relationships

| Relationship | Direction | Target | Description |
|--------------|-----------|--------|-------------|
| `USES_KU` | Outgoing | Ku | Atomic Kus composed into this step |
| `CONTAINS_KNOWLEDGE` | Outgoing | Ku | Additional knowledge units in this step |
| `HAS_STEP` (incoming) | Incoming | Lp | Parent learning path (via `in_paths` key) |
| `REQUIRES_STEP` | Outgoing | PathStep | Prerequisite steps |
| `REQUIRES_KNOWLEDGE` | Outgoing | Ku | Prerequisite knowledge (`prerequisite_knowledge_uids`) |
| `HAS_HABIT_TEMPLATE` … `HAS_CHOICE_TEMPLATE` | Outgoing | HabitTemplate … ChoiceTemplate | Practice: the six Activity Template channels (`habit_template_uids`, …); each learner who engages the step gets their own Activity from each, stamped `source_path_step_uid` |
| `MASTERED` (incoming) | Incoming | User | Derived: `PsMasteryService.handle_knowledge_mastered` writes it the moment the step's last Ku is mastered — same writer (`mark_mastered`) and shape (`mastered_at`, `mastery_score` 1.0, `confidence`, `method = 'derived'`) as a Ku's edge; the step's `IN_PROGRESS` enrollment is retired in the same write. A step teaching no Ku is never derived — it is a content defect the knowledge-health gauge lists (`../roadmap/done/zero-ku-step-mastery.md`) |

## Intelligence Methods

See [PS_INTELLIGENCE.md](../intelligence/PS_INTELLIGENCE.md): each `PsIntelligenceService` method, what it reads and who calls it.

## Adaptive curriculum

`PsService.adaptive` (`PsAdaptiveService`, `/core/services/ps/ps_adaptive_service.py`) delivers
personalized path steps. `SELCategory` is a lens over Ku and PathStep — the `sel_category`
field on both carries one of the five CASEL competencies (`self_awareness`, `self_management`,
`social_awareness`, `relationship_skills`, `responsible_decision_making`); there is no SEL
domain, page or sidebar. Two public methods, each delegated by the facade:

| Method | Returns | Description |
|--------|---------|-------------|
| `get_personalized_curriculum(user_uid, sel_category, limit=10)` | `list[PathStep]` | Steps in the category the learner is ready for (not mastered, prerequisites met, level fits; a step that authored no level fits every learner), ranked by learning value |
| `get_sel_journey(user_uid)` | `LearningJourney` | Progress across all five categories + the recommended next one |

Routes (JSON, authenticated; `adapters/inbound/path_steps_api.py`): `GET /api/path-steps/journey`
and `GET /api/path-steps/curriculum/{category}?limit=10` — an unknown category is a 400. Their
HTMX twins `GET /api/path-steps/journey-html` and `GET /api/path-steps/curriculum-html/{category}`
(rendered by `ui/patterns/curriculum_adaptive.py`) are staged: no page loads them — see
`../roadmap/sel-journey-fragments-staged.md`; the retired SEL page's record is
`../migrations/SEL_UX_MODERNIZATION_2026-02-03.md`.

## Cross-Domain: Practice Infrastructure

A PathStep names its practice as Activity Templates — blueprints that belong to no one.
Engaging the step gives the learner their own Activity from each, stamped with the step
(`source_path_step_uid`); a step names no Activity itself, since an Activity is one learner's and
the step is shared (the content vault refuses `habit_uids:` and its five siblings, naming the
template key). LearningPaths aggregate their steps' templates via `(LP)-[:HAS_STEP]->(PathStep)`.

```
PathStep
 ├── HAS_HABIT_TEMPLATE ──→ HabitTemplate        "Practice this daily"
 ├── HAS_TASK_TEMPLATE ──→ TaskTemplate          "Do this concrete thing"
 ├── HAS_EVENT_TEMPLATE ──→ EventTemplate        "Attend this experience"
 ├── HAS_GOAL_TEMPLATE ──→ GoalTemplate
 ├── HAS_PRINCIPLE_TEMPLATE ──→ PrincipleTemplate
 └── HAS_CHOICE_TEMPLATE ──→ ChoiceTemplate
         ⋮ on engagement
 learner's own Habit / Task / … {source_path_step_uid: <the step>}
```

The two grains are read by two kinds of reader. Everyone sees what the step offers — its
templates (`get_practice_summary`, `GET /api/path-steps/insights`, the step's `/context`). One
learner's context holds their own Activities from the step (the rich context's
`practice_habits` / `practice_tasks`, read off their `OWNS` edges by the stamp).

### Per-Step Practice Analysis

`PsIntelligenceService` provides methods that measure practice coverage for individual steps:

| Method | Returns | Description |
|--------|---------|-------------|
| `get_practice_summary(ps_uid)` | `dict` | `{"habits": int, "tasks": int, "events": int, "goals": int, "principles": int, "choices": int, "total": int}` — the templates the step names per domain |
| `practice_completeness_score(ps_uid)` | `float` | 0.0-1.0 — each of 6 activity domains the step names a template in contributes 1/6 |
| `has_practice_opportunities(ps_uid)` | `bool` | True if the step names any template (staged) |

Backend: `PsIntelligenceBackend.fetch_practice_counts`, one `OPTIONAL MATCH` per template channel.

### LP-Level Consumption

These per-step methods are the building blocks for LP-level practice gap analysis.
When learning paths contain PathSteps that name templates,
`LpIntelligenceService.identify_practice_gaps()` iterates through the path's steps
and aggregates these scores into a path-wide coverage report.

See: [LP Domain: Future Practice Gap Analysis](lp.md#future-practice-gap-analysis)

### Knowledge Substance Connection

Practice is how SKUEL measures whether knowledge is being *lived*, not just studied. A step
that names a template in all six domains has full practice coverage. A step with none is pure
theory — valuable but incomplete without embodiment.

See: [Knowledge Substance Philosophy](../architecture/knowledge_substance_philosophy.md)

## Relationship Config

PS uses `PS_CONFIG` from the relationship registry:

```python
from core.models.relationship_registry import PS_CONFIG

config = PS_CONFIG
# Defines: in_paths, knowledge, prerequisites, practice relationships
```

## Related ADRs

- [ADR-023: Curriculum BaseService Migration](../decisions/ADR-023-curriculum-baseservice-migration.md)
- [ADR-024: BaseAnalyticsService Migration](../decisions/ADR-024-base-intelligence-service-migration.md)
- [ADR-030: Curriculum Domain Unification](../decisions/ADR-030-curriculum-domain-unification.md)

## See Also

- [KU Domain](ku.md) - Kus are composed into steps
- [LP Domain](lp.md) - LPs contain steps
- [Curriculum Grouping Patterns](../architecture/CURRICULUM_GROUPING_PATTERNS.md)
