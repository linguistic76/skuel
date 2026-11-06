---
updated: 2026-11-06
---

# PsIntelligenceService - Practice, Readiness & Per-User Substance

## Overview

**Architecture:** Extends `_CoreIntelligenceMixin[PathStep]` + `BaseAnalyticsService[BackendOperations[PathStep], PathStep]` — graph reads and Python only, no AI dependencies
**Location:** `/core/services/ps/ps_intelligence_service.py`
**Service Name:** `ps.intelligence`
**Facade slot:** `PsService.intelligence` (`/core/services/ps_service.py`)
**Cypher:** none in the service. `PsIntelligenceBackend` (`/adapters/persistence/neo4j/ps_intelligence_backend.py`, ADR-044) holds it behind `PsIntelligenceBackendOperations`. The composition root injects it as `intelligence_backend`; a read that finds none fails through `_require_backend`.

Ku-grain intelligence is a separate service — see [KU_INTELLIGENCE.md](KU_INTELLIGENCE.md). LLM features live in [PsAIService](#psaiservice-full-tier).

---

## Methods

Every `backend` read below is on `PsIntelligenceBackend`. "PLANNED" means no production caller: the method is staged in `PLANNED_METHODS` (`scripts/detect_bloat.py`), not abandoned.

| Method | Answers | Reads | Called by |
|---|---|---|---|
| `get_with_context(uid, depth=2)` | The step and its graph neighbourhood. Inherited from `_CoreIntelligenceMixin` | `UnifiedRelationshipService.get_with_context` | `GET /api/path-steps/context?uid=` |
| `get_domain_insights(uid, _min_confidence=0.7)` | Title, intent, practice summary, completeness and whether prerequisites exist (`PsDomainInsights`). A failed practice or prerequisite read answers zeros or `False`; `_min_confidence` is a placeholder | `backend.get` on the PathStep, then the three methods below | `GET /api/path-steps/insights?uid=` |
| `get_practice_summary(ps_uid)` | How many of each practice edge the step carries: 7 keys, the six domains plus `total` | `fetch_practice_counts` (the six edges below) | `get_domain_insights`, `practice_completeness_score`, `LpIntelligenceService.identify_practice_gaps` |
| `practice_completeness_score(ps_uid)` | The fraction of the six domains present, 0.0-1.0. Each counts once, so a step with five habits and nothing else scores 1/6 | `get_practice_summary` | `get_domain_insights` |
| `has_prerequisites(ps_uid)` | Does any `REQUIRES_STEP` or `REQUIRES_KNOWLEDGE` edge leave the step? Reads no edge property | `backend.has_prerequisites` | `get_domain_insights` |
| `is_ready(ps_uid, completed_step_uids)` | Is every `REQUIRES_STEP` target in the caller's set? | `fetch_prerequisite_step_uids` | PLANNED |
| `calculate_guidance_strength(ps_uid)` | 0.0-1.0: `min(0.4, principles × 0.15) + min(0.6, choices × 0.2)` | `fetch_guidance_counts` (`GUIDED_BY_PRINCIPLE`, `INFORMS_CHOICE`) | PLANNED |
| `has_guidance(ps_uid)` | Does a `GUIDED_BY_PRINCIPLE` or `INFORMS_CHOICE` edge leave the step? | `backend.has_guidance` | PLANNED |
| `has_practice_opportunities(ps_uid)` | Does any of the six practice edges leave the step? | `backend.has_practice_opportunities` | PLANNED |
| `calculate_user_substance(ps_uid, user_context)` | How much one learner has applied the step: overall substance and mastery, per-Ku detail, a status message. Requires a rich context | `fetch_taught_ku_uids`, then the context's channel maps | `PsService.get_user_step_context` ← `GET /api/path-steps/my-context?uid=` |
| `calculate_user_substance_for_steps(ps_uids, channels)` | Substance score per step, for a whole set, in one round trip. Projects the score out of the breakdown below | `calculate_user_substance_breakdown_for_steps` | `PsService.get_user_substance_scores` ← `AnalyticsMetricsService` |
| `calculate_user_substance_breakdown_for_steps(ps_uids, channels)` | Score and per-channel parts per step (`StepSubstance`), in one round trip | `fetch_taught_ku_uids_for_steps` | `PsService.get_user_substance_breakdowns` ← `AnalyticsLifePathService` |

**What reaches a person:** no page calls the three `/api/path-steps` doors above, so they answer JSON clients only. The two batch substance methods do reach learners: the score through the weekly life summary, the breakdown through the life-path alignment. `identify_practice_gaps` feeds `analyze_path_knowledge_scope` on `LpService`, which no route calls.

---

## Notes

### The six practice edges

`PRACTICE_DOMAINS` is the one definition of "what counts as practice". The PS scorer and `identify_practice_gaps` both read it, through `practice_completeness_from_summary` and `missing_practice_domains`.

| Key | Edge from the PathStep |
|---|---|
| `habits` | `BUILDS_HABIT` |
| `tasks` | `ASSIGNS_TASK` |
| `events` | `SCHEDULES_EVENT` |
| `goals` | `SUPPORTS_GOAL` |
| `principles` | `GUIDED_BY_PRINCIPLE` |
| `choices` | `INFORMS_CHOICE` |

### Readiness and prerequisites ask different questions

`has_prerequisites` counts `REQUIRES_STEP` and `REQUIRES_KNOWLEDGE`. `is_ready` checks `REQUIRES_STEP` only, so a step whose only prerequisite is a `REQUIRES_KNOWLEDGE` edge has prerequisites and is ready. A step with no `REQUIRES_STEP` edge is ready, and so is a uid that names nothing.

### Substance

A step's substance is the mean over the Kus it teaches, reached through `CURRICULUM_COMPOSITION_EDGES`. Each Ku is scored against one learner's six activity channels by `core/services/knowledge/user_substance.py`. A step teaching no Ku scores 0.0.

- **Which channels:** the per-step method reads the context it is given, and a standard build leaves those maps empty, so it needs `build_rich()`. The batch methods take the maps as an argument because a cumulative figure needs the unwindowed `get_user_knowledge_channels`; a context's maps stop at the planning window.
- **Parts and whole:** `sum(breakdown.values())` may exceed `score`. Each Ku's score is capped at 1.0 while its channels can total 1.30, so normalise proportions against the breakdown's own sum.
- **Status message:** `calculate_user_substance` reads the mean against 0.7, 0.4 and 0.

---

## PsAIService (FULL Tier)

**Architecture:** Extends `BaseAIService[PsOperations, PathStep]`
**Location:** `/core/services/ps/ps_ai_service.py`
**Service Name:** `ps.ai`
**Tier:** FULL only (`None` when `INTELLIGENCE_TIER=core`)
**Access:** `ps_service.ai`

PsAIService provides LLM-powered features for PathSteps, separate from the graph analytics above (`INTELLIGENCE_TIER`, ADR-043). All methods require the AI service to be wired (check `ps_service.ai is not None`).

`find_similar_steps`, `generate_step_insight`, `explain_step` and `suggest_practice_activities` answer `/api/path-steps/ai/*` (`AI_ROUTE_SPECS`). The other three have no route and no caller, and are PLANNED; `PsService` delegates to them.

### AI Methods

**`suggest_step_applications(ps_uid)`** → `Result[StepApplicationsResult]`
Suggests how to apply this path step across activity domains. Returns categorized suggestions: tasks (concrete work), habits (behaviors to build), goals (outcomes enabled), and real-world examples.

**`suggest_learning_sequence(ps_uid, max_suggestions=5)`** → `Result[StepLearningSequenceResult]`
Suggests prerequisite steps (what to learn first) and next steps (natural progressions). Each item includes a title and reason. Uses JSON prompts for reliable structured output.

**`search_by_semantic_query(query_text, limit=20, min_score=0.5)`** → `Result[list[PathStep]]`
The PathSteps nearest to the query in the PathStep vector index (`Neo4jVectorSearchService.find_similar_by_text`, whose index query withholds draft-marked steps), read back as models in score order. **FULL tier only** — this is a `.ai` sub-service method, and `.ai` is `None` in CORE, so no CORE caller reaches it (the `PsService` facade answers keyword search in CORE). An embedding or index failure is the method's failure; there is no keyword fallback.

**`explain_step(ps_uid, target_level="standard")`** → `Result[str]`
AI explanation at a specific level. `target_level` values: `beginner` (no assumed knowledge), `intermediate` (assumes familiarity), `advanced` (in-depth, connects to broader concepts), `standard` (default), `brief` (2-3 sentences), `detailed` (comprehensive with examples).

**`suggest_practice_activities(ps_uid, num_activities=3)`** → `Result[list[dict[str, str]]]`
Suggests practice activities (name, type, description). Uses JSON prompts for structured output.

**`generate_step_insight(ps_uid)`** → `Result[str]`
Brief encouraging insight about a path step (value + motivation tip).

**`find_similar_steps(ps_uid, limit=5)`** → `Result[list[tuple[EntityUID, float]]]`
The steps nearest to `ps_uid` in the PathStep vector index — the source's stored vector (or its canonical embedding text when it has none) through `rank_similar_curriculum` (`core/services/curriculum_similarity.py`). Draft-marked steps are withheld by the index query as a post-filter, so the list can hold fewer than `limit`; scores are the index's `[0, 1]` cosine scale, thresholded at `ku_similar_min_score`. An unknown uid is not-found.

### TypedDicts

```python
from core.ports.query_types import StepApplicationsResult, StepLearningSequenceResult, StepLearningSequenceItem
```

`StepApplicationsResult` — `{ps_uid, ps_title, tasks, habits, goals, real_world_examples}` (each a `list[str]`)
`StepLearningSequenceResult` — `{ps_uid, ps_title, prerequisites, next_steps}` (each a `list[StepLearningSequenceItem]`)
`StepLearningSequenceItem` — `{title, reason}`

### Usage Example

```python
# Only available in FULL tier
if ps_service.ai:
    # Categorized applications across activity domains
    apps = await ps_service.suggest_step_applications(ps_uid)
    # apps.value: {"ps_uid": ..., "ps_title": ..., "tasks": [...], "habits": [...], "goals": [...], "real_world_examples": [...]}

    # Learning sequence
    seq = await ps_service.suggest_learning_sequence(ps_uid, max_suggestions=5)
    # seq.value["prerequisites"]: [{"title": ..., "reason": ...}]; seq.value["next_steps"] likewise

    # Semantic search (the facade answers keyword search on CORE)
    results = await ps_service.search_by_semantic_query("introduction to functions", limit=10)

    # Explanation at a level
    explanation = await ps_service.ai.explain_step(ps_uid, target_level="beginner")
```

---

## See Also

- [INTELLIGENCE_SERVICES_INDEX.md](INTELLIGENCE_SERVICES_INDEX.md) - Master index
- [ADR-024](../decisions/ADR-024-base-intelligence-service-migration.md) - BaseAnalyticsService pattern
- [ADR-044](../decisions/ADR-044-neo4j-committed-architectural-choice.md) - Cypher below the boundary
- [CURRICULUM_GROUPING_PATTERNS.md](../architecture/CURRICULUM_GROUPING_PATTERNS.md) - Path Step architecture
- `/core/services/base_analytics_service.py` - Base implementation
- `/core/services/ps_service.py` - PsService facade
- `/core/services/ps/ps_ai_service.py` - PsAIService
- `/adapters/persistence/neo4j/ps_intelligence_backend.py` - PsIntelligenceBackend
