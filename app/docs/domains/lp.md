---
title: LP (Learning Path) Domain
created: 2025-12-04
updated: 2026-01-11
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

Learning Paths represent complete, sequential learning journeys. They organize Learning Steps into a coherent curriculum with validation, adaptive sequencing, and progress tracking.

## Service Architecture (ADR-030, ADR-031)

LpService coordinates 5 sub-services:

| Sub-service | Class | Purpose |
|-------------|-------|---------|
| `.core` | LpCoreService | CRUD operations |
| `.search` | LpSearchService | Discovery operations |
| `.relationships` | UnifiedRelationshipService | Path-step associations |
| `.intelligence` | LpIntelligenceService | ALL intelligence operations (created internally) |
| `.progress` | LpProgressService | Event-driven tracking |

**Initialization:** Manual (non-standard core signature requires `ls_service`)
**Intelligence:** Created internally by LpService (January 2026 - unified pattern)
**graph_intel:** REQUIRED (fail-fast validation)

```python
from core.services.lp_service import LpService

# In services_bootstrap.py
lp_service = LpService(
    driver=driver,
    ls_service=ls_service,           # REQUIRED - for step operations
    graph_intelligence_service=graph_intelligence,  # REQUIRED
    event_bus=event_bus,
    # Intelligence dependencies (created internally by LpService)
    embeddings_service=embeddings_service,
    llm_service=llm_service,
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

Both LpCoreService and LpSearchService extend `BaseService` (January 2026 alignment with LS pattern):

```python
class LpCoreService(BaseService["BackendOperations[Lp]", Lp]):
    _dto_class = LpDTO
    _model_class = Lp
    _user_ownership_relationship = None  # Shared curriculum content
    ...

class LpSearchService(BaseService["BackendOperations[Lp]", Lp]):
    _dto_class = LpDTO
    _model_class = Lp
    _search_fields = ["title", "description"]
    _user_ownership_relationship = None  # Shared content
    ...
```

## Key Files

| Component | Location |
|-----------|----------|
| Facade | `/core/services/lp_service.py` |
| Core Service | `/core/services/lp/lp_core_service.py` |
| Search Service | `/core/services/lp/lp_search_service.py` |
| Intelligence Service | `/core/services/lp_intelligence_service.py` |
| Progress Service | `/core/services/lp/lp_progress_service.py` |
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

LpIntelligenceService is created internally by LpService (January 2026 - unified pattern). It coordinates 4 specialized sub-services and provides consolidated intelligence methods:

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

**Internal creation pattern:**
- LpService now creates LpIntelligenceService internally
- Matches the unified pattern used by all other domains (Tasks, Goals, Habits, Events, Choices, Principles, KU, LS, MOC)
- Parameter count reduced from 11+ to 7

### Intelligence Methods

| Category | Method | Returns | Description |
|----------|--------|---------|-------------|
| **Validation** | `validate_path_prerequisites(path_uid)` | `Result[bool]` | Check prerequisites met |
| **Validation** | `identify_path_blockers(path_uid, user_uid)` | `Result[list]` | Find blockers |
| **Validation** | `get_optimal_path_recommendation(user_uid)` | `Result[Lp]` | Best path for user |
| **Context** | `get_path_with_context(path_uid)` | `Result[dict]` | Path with graph context |
| **Analysis** | `analyze_path_knowledge_scope(path_uid)` | `Result[dict]` | Knowledge coverage analysis |
| **Analysis** | `identify_practice_gaps(path_uid)` | `Result[dict]` | *Future* — needs LS practice relationships (BUILDS_HABIT, ASSIGNS_TASK, SCHEDULES_EVENT) |
| **Adaptive** | `find_learning_sequence(goals, user_uid)` | `Result[list]` | Optimal step sequence |
| **Adaptive** | `get_next_adaptive_step(path_uid, user_uid)` | `Result[Ls]` | Best next step |
| **Adaptive** | `get_recommended_learning_steps(user_uid)` | `Result[list]` | Daily "what to learn" |
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

## Future: Practice Gap Analysis

**Status:** Blocked — learning paths need real content with practice relationships populated
**Method:** `LpIntelligenceService.identify_practice_gaps(path_uid)` → `Result[dict]`
**Code location:** TODO block in `/core/services/lp_intelligence_service.py`

### What It Does

For a learning path, analyzes every step to determine which steps lack complete practice
opportunities. A step with full practice has all three relationship types:

| Relationship | Target | Meaning |
|--------------|--------|---------|
| `BUILDS_HABIT` | Habit | "Practice this daily to internalize the knowledge" |
| `ASSIGNS_TASK` | Task | "Do this concrete thing to apply the knowledge" |
| `SCHEDULES_EVENT` | Event | "Attend this to experience the knowledge" |

A step missing one or more of these types has a *practice gap* — the learner can read about
the concept but has no structured way to embody it.

### Existing Infrastructure (Already Built)

The per-step practice analysis already works via `LsIntelligenceService`:

```python
# These methods exist TODAY in /core/services/ls/ls_intelligence_service.py

# Count practice items per step
result = await ls_intelligence.get_practice_summary("ls:functions")
# → {"habits": 2, "tasks": 3, "events": 1, "total": 6}

# Calculate 0.0-1.0 completeness per step
# (each type contributes 1/3: habits + tasks + events)
score = await ls_intelligence.practice_completeness_score("ls:functions")
# → 1.0 (all three types present)

# Boolean checks
await ls_intelligence.has_practice_opportunities("ls:functions")  # → True
```

The Cypher that powers this:

```cypher
MATCH (ls:Ku {uid: $ls_uid})
OPTIONAL MATCH (ls)-[:BUILDS_HABIT]->(h)
OPTIONAL MATCH (ls)-[:ASSIGNS_TASK]->(t)
OPTIONAL MATCH (ls)-[:SCHEDULES_EVENT]->(e)
RETURN count(DISTINCT h) as habits,
       count(DISTINCT t) as tasks,
       count(DISTINCT e) as events
```

### What's Missing (The Gap Between LS and LP)

The per-step methods work, but LP-level analysis needs **cross-service access**:

```
LpIntelligenceService  ──needs──>  LsIntelligenceService
        │                                    │
        │  "For each step in this path,      │  "For this step, count
        │   what practice is missing?"       │   habits, tasks, events"
        └────────────────────────────────────┘
```

**Current state:** `LpIntelligenceService` has no reference to `LsIntelligenceService`.
**Required change:** Inject `ls_intelligence` as a constructor parameter, or access via
`LsService.intelligence` through the existing `ls_service` dependency.

### Implementation Path

When learning paths have content with practice relationships:

1. **Wire the dependency** — `LpIntelligenceService.__init__` accepts `ls_intelligence` parameter
   (or access `ls_service.intelligence` from the factory in `curriculum_domain_config.py`)

2. **Implement the method:**
   ```python
   async def identify_practice_gaps(self, path_uid: str) -> Result[dict[str, Any]]:
       # Get path and its steps
       path = await self.learning_backend.get(path_uid)

       # For each step, call existing LS intelligence
       gaps = []
       for step in path.steps:
           score = await self.ls_intelligence.practice_completeness_score(step.uid)
           if score.value < 1.0:
               summary = await self.ls_intelligence.get_practice_summary(step.uid)
               missing = [t for t in ("habits", "tasks", "events") if summary.value[t] == 0]
               gaps.append({
                   "step_uid": step.uid,
                   "step_title": step.title,
                   "practice_completeness": score.value,
                   "missing_types": missing,
               })

       return Result.ok({
           "path_uid": path_uid,
           "total_steps": len(path.steps),
           "steps_with_gaps": len(gaps),
           "overall_practice_coverage": avg(completeness scores),
           "gaps": gaps,
       })
   ```

3. **Wire to facade** — Add `"identify_practice_gaps"` to `LpService._delegations` map
4. **Wire to protocol** — Add to `LpFacadeProtocol` in `facade_protocols.py`
5. **Wire to route** — Add API endpoint in LP routes

### Expected Return Shape

```json
{
  "path_uid": "lp:python-fundamentals",
  "total_steps": 8,
  "steps_with_gaps": 3,
  "overall_practice_coverage": 0.625,
  "gaps": [
    {
      "step_uid": "ls:decorators",
      "step_title": "Python Decorators",
      "practice_completeness": 0.33,
      "missing_types": ["habits", "events"]
    },
    {
      "step_uid": "ls:generators",
      "step_title": "Generator Functions",
      "practice_completeness": 0.0,
      "missing_types": ["habits", "tasks", "events"]
    }
  ],
  "recommendations": [
    "3 of 8 steps lack complete practice opportunities",
    "ls:generators has no practice at all — consider adding a task or habit"
  ]
}
```

### Why This Matters

SKUEL's [Knowledge Substance Philosophy](../architecture/knowledge_substance_philosophy.md)
measures knowledge by how it's *lived*. A learning path without practice relationships is
a reading list — not a curriculum. Practice gap analysis ensures every step has concrete
ways to embody the knowledge, connecting the curriculum domain (KU/LS/LP) to the activity
domains (Tasks, Habits, Events).

### See Also

- [LS Domain: Practice Infrastructure](ls.md#cross-domain-practice-infrastructure)
- [Knowledge Substance Philosophy](../architecture/knowledge_substance_philosophy.md)
- [Curriculum Grouping Patterns](../architecture/CURRICULUM_GROUPING_PATTERNS.md)

---

## Related ADRs

- [ADR-023: Curriculum BaseService Migration](../decisions/ADR-023-curriculum-base-service.md)
- [ADR-024: BaseAnalyticsService Migration](../decisions/ADR-024-base-intelligence-service.md)
- [ADR-030: Curriculum Domain Unification](../decisions/ADR-030-curriculum-domain-unification.md)
- **ADR-031: LP Intelligence Unification** - Dead code removal, internal creation pattern (January 2026)

## See Also

- [LS Domain](ls.md) - Paths contain steps
- [KU Domain](ku.md) - Steps contain KUs
- [LifePath Domain](lifepath.md) - Ultimate learning goal
- [Curriculum Grouping Patterns](../architecture/CURRICULUM_GROUPING_PATTERNS.md)
