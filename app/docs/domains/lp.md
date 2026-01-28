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
| Relationship Config | `/core/services/relationships/domain_configs.py` (`get_lp_config()`) |

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
| **Analysis** | `identify_practice_gaps(path_uid, user_uid)` | `Result[list]` | Missing practice areas |
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

LP uses `get_lp_config()` for UnifiedRelationshipService:

```python
from core.services.relationships.domain_configs import get_lp_config

config = get_lp_config()
# Defines: steps, prerequisites, enables, goal alignment, milestones
```

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
