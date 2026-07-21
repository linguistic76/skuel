---
title: LP (Learning Path) Domain
created: 2025-12-04
updated: 2026-04-11
status: current
category: domains
tags:
- lp
- learning-path
- curriculum-domain
- domain
- adr-030
- adr-031
related_skills:
- curriculum-domains
---

# LP (Learning Path) Domain

**Type:** Curriculum Domain (3 of 4)
**UID Prefix:** `lp:`
**Entity Label:** `Lp`
**Topology:** Path (complete sequence)

## Purpose

**Skill:** [@curriculum-domains](../../.claude/skills/curriculum-domains/SKILL.md)

Learning Paths represent complete, sequential learning journeys. They organize Path Steps into a coherent curriculum with validation, adaptive sequencing, and progress tracking.

## Service Architecture (ADR-030, ADR-031)

LpService coordinates 5 sub-services:

| Sub-service | Class | Purpose |
|-------------|-------|---------|
| `.core` | LpCoreService | CRUD operations |
| `.search` | LpSearchService | Discovery operations |
| `.relationships` | UnifiedRelationshipService | Path-step associations |
| `.intelligence` | LpIntelligenceService | ALL intelligence operations (created internally) |
| `.progress` | LpProgressService | Event-driven tracking |

**Initialization:** Manual (non-standard core signature requires `ps_service`)
**Intelligence:** Created internally by LpService (January 2026 - unified pattern)
**graph_intel:** REQUIRED — gates the inherited mechanism-B `get_with_context` (fail-fast validation)

```python
from core.services.lp_service import LpService

# In services_bootstrap.py
lp_service = LpService(
    backend=lp_backend,
    ps_service=ps_service,           # REQUIRED - for step operations
    graph_intel=graph_intelligence,  # REQUIRED
    event_bus=event_bus,
    progress_backend=progress_backend,
    user_service=user_service,
)

# Access sub-services
await lp_service.core.create_path(...)
await lp_service.search.search(query)
await lp_service.relationships.get_related_uids("steps", path_uid)
await lp_service.intelligence.analyze_learning_state(user_context)
await lp_service.intelligence.validate_path_prerequisites(path_uid)
await lp_service.intelligence.get_next_adaptive_step(path_uid, user_uid)
```

## BaseService Inheritance

Both LpCoreService and LpSearchService extend `BaseService` (January 2026 alignment with PS pattern):

```python
class LpCoreService(BaseService["BackendOperations[Lp]", Lp]):
    _dto_class = LpDTO
    _model_class = Lp
    _user_ownership_relationship = None  # Shared curriculum content
    ...

class LpSearchService(BaseService["LpOperations", Lp]):
    _config = create_curriculum_domain_config(...)
    # Type-narrowed to LpOperations (April 2026) — gives access to
    # domain-specific backend methods like get_paths_aligned_with_goal()
    ...
```

## Backend Methods (LpBackend)

All Cypher queries are encapsulated in `LpBackend` (28 methods decomposed into 3 focused mixins — `_LpStepMixin`, `_LpProgressMixin`, `_LpIntelligenceMixin`). LpCoreService and LpSearchService call typed backend methods — no inline Cypher in services.

| Method | Purpose |
|--------|---------|
| `get_path_with_steps(uid)` | Single LP + HAS_STEP steps |
| `get_paths_batch_with_steps(uids)` | Batch LP fetch (GraphQL DataLoader) |
| `list_user_paths_with_steps(user_uid, limit)` | User's LPs with steps |
| `list_all_paths_with_steps(limit, offset, order_by, order_desc)` | All LPs with `_ALLOWED_ORDER_BY` validation |
| `update_path_properties(set_clauses, params)` | Dynamic SET update |
| `delete_path_cascade(uid)` | Cascade delete LP + step nodes |
| `persist_path_with_steps(user_uid, path_params, steps_params)` | Create LP node + User relationship + steps |
| `entity_exists(uid)` | Simple existence check |
| `get_steps_raw(path_uid, depth)` | Ordered steps as raw dicts |
| `get_parent_path_raw(step_uid)` | Parent LP for a step |
| `add_step_to_path(path_uid, step_uid, sequence, order)` | HAS_STEP creation (idempotent) |
| `remove_step_from_path(path_uid, step_uid)` | HAS_STEP removal + reorder |
| `reorder_steps(path_uid, step_uids)` | Batch step reordering |
| `get_paths_containing_ku(ku_uid)` | LPs that include a KU |
| `get_ku_mastery_progress(lp_uid, user_uid)` | KU completion state for LP |
| `get_paths_aligned_with_goal(goal_uid)` | LPs aligned with a goal |
| `get_paths_by_knowledge(ku_uid)` | LPs containing a KU |
| `get_user_paths_prioritized(user_uid, context)` | User's LPs ranked by priority |
| `get_paths_containing_step(ps_uid)` | LPs containing a specific step |
| `validate_path_prerequisites(path_uid)` | Prerequisite ordering validation |
| `identify_path_blockers(path_uid, user_uid)` | Find blockers for a user |
| `get_optimal_path_recommendations(user_uid, goal_domain)` | Best path recommendations |
| `find_learning_sequence(start_uid, goal_uid)` | Shortest path graph traversal |
| `get_next_adaptive_step(current_step_uid, user_uid)` | Adaptive next step |
| `get_recommended_path_steps(user_uid, max_difficulty, limit)` | Recommended steps by progress |
| `get_all_knowledge_uids(path_uid)` | Distinct KU UIDs across all steps (deduped) |
| `get_knowledge_scope_summary(path_uid)` | Structural scope facts: steps, unique KUs, density, prereq depth |

## Key Files

| Component | Location |
|-----------|----------|
| Facade | `/core/services/lp_service.py` |
| Core Service | `/core/services/lp/lp_core_service.py` |
| Search Service | `/core/services/lp/lp_search_service.py` |
| Intelligence Service | `/core/services/lp/lp_intelligence_service.py` |
| Progress Service | `/core/services/lp/lp_progress_service.py` |
| Domain Backend | `/adapters/persistence/neo4j/backends/curriculum_backends.py` (`LpBackend`) |
| Step Mixin | `/adapters/persistence/neo4j/_lp_step_mixin.py` (14 methods) |
| Progress Mixin | `/adapters/persistence/neo4j/_lp_progress_mixin.py` (6 methods) |
| Intelligence Mixin | `/adapters/persistence/neo4j/_lp_intelligence_mixin.py` (10 methods) |
| Model | `/core/models/lp/lp.py` |
| DTO | `/core/models/lp/lp_dto.py` |
| Relationship Config | `LP_CONFIG` in `/core/models/relationship_registry.py` |

### Intelligence Sub-Services

| Component | Location |
|-----------|----------|
| Learning State Analyzer | `/core/services/lp_intelligence/learning_state_analyzer.py` |
| Learning Recommendation Engine | `/core/services/lp_intelligence/learning_recommendation_engine.py` |
| Content Analyzer | `/core/services/lp_intelligence/content_analyzer.py` |
| Content Quality Assessor | `/core/services/lp_intelligence/content_quality_assessor.py` |
| Types | `/core/services/lp_intelligence/types.py` |

## Model Fields

| Field | Type | Description |
|-------|------|-------------|
| `uid` | `str` | Unique identifier |
| `title` | `str` | Path title |
| `description` | `str?` | Path description |
| `section` | `LpSection` | Foundation, Practice, Integration |
| `stream` | `str?` | Learning stream category |
| `estimated_hours` | `float` | Estimated completion time |
| `difficulty` | `Difficulty` | Beginner, Intermediate, Advanced |
| `domain` | `Domain` | TECH, HEALTH, PERSONAL, etc. |
| `is_published` | `bool` | Whether publicly available |

## Sections

| Section | Order | Purpose |
|---------|-------|---------|
| `foundation` | 1 | Core concepts and prerequisites |
| `practice` | 2 | Hands-on application |
| `integration` | 3 | Real-world synthesis |

## Relationships

| Relationship | Direction | Target | Description |
|--------------|-----------|--------|-------------|
| `HAS_STEP` | Outgoing | Ls | Learning steps in path (via `steps` key) |
| `REQUIRES_PATH` | Outgoing | Lp | Prerequisite paths |
| `ENABLES_PATH` | Outgoing | Lp | Paths this enables |
| `ALIGNED_WITH_GOAL` | Outgoing | Goal | Goal alignment |
| `HAS_MILESTONE_EVENT` | Outgoing | Event | Milestone tracking |
| `ENROLLED_IN` | Incoming | User | Users enrolled |
| `ULTIMATE_PATH` | Incoming | User | User's life path designation |

## Intelligence Service

LpIntelligenceService is created internally by LpService (January 2026 - unified pattern). It coordinates 4 specialized sub-services and delegates Cypher queries to `LpBackend` (April 2026 — no `executor` or `graph_intel` dependencies):

| Sub-service | Class | Purpose |
|-------------|-------|---------|
| State Analyzer | LearningStateAnalyzer | Learning state assessment |
| Recommendation Engine | LearningRecommendationEngine | Personalized recommendations |
| Content Analyzer | ContentAnalyzer | Content metadata extraction |
| Quality Assessor | ContentQualityAssessor | Quality scoring, similarity |

### January 2026 Unification (ADR-031)

**Dead code removed:**
- `vectors_backend` parameter - stored but never used
- `ku_service` parameter - circular dependency workaround never completed
- `executor` parameter - removed April 2026 (all Cypher moved to LpBackend)

**Internal creation pattern:**
- LpService now creates LpIntelligenceService internally
- Matches the unified pattern used by all other domains (Tasks, Goals, Habits, Events, Choices, Principles, KU, PS, MOC)
- All 7 intelligence Cypher queries delegated to `LpBackend` (April 2026)
- Service-layer consumers extract records from `result.value` (a `list[dict]`) before accessing keys — never call `.get()` directly on the list
- `graph_intel` retained to gate the inherited mechanism-B `get_with_context` (registry-sourced via `self.relationships`)

### Facade Aggregation Methods (March 2026)

Extracted from `pathways_ui.py` route handlers into `LpService` facade:

| Method | Returns | Description |
|--------|---------|-------------|
| `calculate_path_progress(paths)` | `tuple[list[ActivePathData], float]` | Pure computation: progress %, current step, hours for each path |
| `get_dashboard_summary(user_uid, user_progress?)` | `Result[dict]` | Full dashboard: active paths + stats (completion rate, concepts mastered) |
| `filter_paths(difficulty, domain, duration, limit)` | `Result[list[dict]]` | Fetch + filter paths by difficulty/domain/duration |
| `get_path_detail_progress(path_uid, user_progress, user_uid)` | `Result[dict]` | Path with mastery info: progress, mastered_uids, is_enrolled |
| `get_learning_analytics(user_uid, user_progress)` | `Result[dict]` | Knowledge profile stats: mastered, in_progress, needs_review, struggling |

### Intelligence Methods

| Category | Method | Returns | Description |
|----------|--------|---------|-------------|
| **Validation** | `validate_path_prerequisites(path_uid)` | `Result[LpPrerequisiteValidation]` | Check prerequisites met (→ LpBackend) |
| **Validation** | `identify_path_blockers(path_uid, user_uid)` | `Result[LpBlockerAnalysis]` | Find blockers (→ LpBackend) |
| **Validation** | `get_optimal_path_recommendation(user_uid)` | `Result[LpPathRecommendation]` | Best path for user (→ LpBackend) |
| **Analysis** | `analyze_path_knowledge_scope(path_uid)` | `Result[dict]` | KU coverage + structural complexity: unique KUs, steps, breadth density, prereq depth, `complexity_score`, `practice_coverage` (→ LpBackend + PS practice reads). No primary/supporting split — PS→KU edges carry no importance weight (a KU importance scale is a deferred arc) |
| **Analysis** | `identify_practice_gaps(path_uid)` | `Result[LpPracticeGapAnalysis]` | Per-step practice completeness via `PsIntelligenceService`; the path-level mean feeds `practice_coverage` into the scope summary |
| **Adaptive** | `find_learning_sequence(start_uid, goal_uid)` | `Result[list[str]]` | Optimal step sequence (→ LpBackend) |
| **Adaptive** | `get_next_adaptive_step(step_uid, user_uid)` | `Result[str\|None]` | Best next step (→ LpBackend) |
| **Adaptive** | `get_recommended_path_steps(user_uid)` | `Result[list[LpRecommendedStep]]` | Daily "what to learn" (→ LpBackend) |
| **State** | `analyze_learning_state(context)` | `Result[LearningAnalysis]` | Comprehensive state analysis |
| **Content** | `recommend_content(context, pool)` | `Result[list]` | Content recommendations |

## MEGA-QUERY Sections

- `enrolled_path_uids` - Paths user is enrolled in
- `enrolled_paths_rich` - Full path data with graph context

## Life Path Connection

One special LP is the user's "life path":
- Connected via `ULTIMATE_PATH` relationship
- All other learning flows toward this
- Measured by life alignment score

## Relationship Config

LP uses `LP_CONFIG` from the relationship registry:

```python
from core.models.relationship_registry import LP_CONFIG

config = LP_CONFIG
# Defines: steps, prerequisites, enables, goal alignment, milestones
```

## Practice Gap Analysis

**Method:** `LpIntelligenceService.identify_practice_gaps(path_uid)` → `Result[LpPracticeGapAnalysis]`
**Facade:** `LpService.identify_practice_gaps(path_uid)`

### What It Does

For a learning path, scores every step's practice completeness and surfaces the steps that
lack complete practice. A step's completeness is the fraction of the **six activity-domain
practice edges** present on it (the canonical PS measure — see below):

| Relationship | Target | Meaning |
|--------------|--------|---------|
| `BUILDS_HABIT` | Habit | "Practice this daily to internalize the knowledge" |
| `ASSIGNS_TASK` | Task | "Do this concrete thing to apply the knowledge" |
| `SCHEDULES_EVENT` | Event | "Attend this to experience the knowledge" |
| `SUPPORTS_GOAL` | Goal | "This advances a goal you're pursuing" |
| `GUIDED_BY_PRINCIPLE` | Principle | "A value that frames how you apply it" |
| `INFORMS_CHOICE` | Choice | "A decision this knowledge informs" |

A step below 1.0 has a *practice gap* — the learner can read the concept but has an incomplete
set of structured ways to embody it. The path-level mean completeness is
`overall_practice_coverage`, which is also folded into `analyze_path_knowledge_scope` as
`practice_coverage`.

### Reuses the PS Practice Measure (One Path Forward)

Rather than fork its own definition of "practice", LP reuses `PsIntelligenceService`:

```python
# /core/services/ps/ps_intelligence_service.py

# Count the six practice domains for one step
summary = await ps_intelligence.get_practice_summary("ps.python.decorators")
# → {"habits": 2, "tasks": 3, "events": 1, "goals": 0,
#    "principles": 0, "choices": 0, "total": 6}

# Fraction of the six domains present (0.0-1.0) — shared pure helper, the single
# source of truth for the score (used by both the PS scorer and the LP rollup)
practice_completeness_from_summary(summary)  # → 0.5  (3 of 6 domains present)
```

`identify_practice_gaps` iterates the path's steps (`LpBackend.get_steps_raw`), calls
`get_practice_summary` once per step, and derives each step's completeness and missing
domains from that single summary. The Cypher that counts the six edges lives once, in
`PsIntelligenceBackend.fetch_practice_counts` — LP never duplicates it.

`ps_intelligence` is injected into `LpIntelligenceService` from the owning `PsService`
(`ps_service.intelligence`) in `create_lp_sub_services` (`curriculum_domain_config.py`).

### Return Shape (`LpPracticeGapAnalysis`)

```json
{
  "path_uid": "lp.python.fundamentals",
  "total_steps": 8,
  "steps_with_gaps": 3,
  "overall_practice_coverage": 0.625,
  "gaps": [
    {
      "step_uid": "ps.python.decorators",
      "step_title": "Python Decorators",
      "practice_completeness": 0.3333,
      "missing_types": ["events", "goals", "principles", "choices"]
    },
    {
      "step_uid": "ps.python.generators",
      "step_title": "Generator Functions",
      "practice_completeness": 0.0,
      "missing_types": ["habits", "tasks", "events", "goals", "principles", "choices"]
    }
  ],
  "recommendations": [
    "3 of 8 steps lack complete practice opportunities.",
    "Generator Functions has no practice at all — add a task or habit."
  ]
}
```

`missing_types` is ordered by the canonical `PRACTICE_DOMAINS` sequence (habits, tasks,
events, goals, principles, choices). `practice_coverage` on the scope summary degrades to
`null` only if practice intelligence is unwired — it never fails the whole scope analysis.

### Why This Matters

SKUEL's [Knowledge Substance Philosophy](../architecture/knowledge_substance_philosophy.md)
measures knowledge by how it's *lived*. A learning path without practice relationships is
a reading list — not a curriculum. Practice gap analysis ensures every step has concrete
ways to embody the knowledge, connecting the curriculum domain (KU/PS/LP) to the activity
domains (Tasks, Habits, Events).

### See Also

- [PS Domain: Practice Infrastructure](ls.md#cross-domain-practice-infrastructure)
- [Knowledge Substance Philosophy](../architecture/knowledge_substance_philosophy.md)
- [Curriculum Grouping Patterns](../architecture/CURRICULUM_GROUPING_PATTERNS.md)

---

## Related ADRs

- [ADR-023: Curriculum BaseService Migration](../decisions/ADR-023-curriculum-base-service.md)
- [ADR-024: BaseAnalyticsService Migration](../decisions/ADR-024-base-intelligence-service.md)
- [ADR-030: Curriculum Domain Unification](../decisions/ADR-030-curriculum-domain-unification.md)
- **ADR-031: LP Intelligence Unification** - Dead code removal, internal creation pattern (January 2026)

## See Also

- [PS Domain](ls.md) - Paths contain steps
- [KU Domain](ku.md) - Steps contain KUs
- [LifePath Domain](lifepath.md) - Ultimate learning goal
- [Curriculum Grouping Patterns](../architecture/CURRICULUM_GROUPING_PATTERNS.md)
