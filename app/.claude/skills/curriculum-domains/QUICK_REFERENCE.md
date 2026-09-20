# Curriculum Domains Quick Reference

> Fast lookup for file locations and domain-specific details.

## File Locations

### Models

| Domain | Directory | Model | DTO | Request |
|--------|-----------|-------|-----|---------|
| **Base** | `core/models/` | `curriculum.py` | `curriculum_dto.py` | — |
| **KU** | `core/models/ku/` | `ku.py` (extends Entity) | `ku_dto.py` | — |
| **PS** | `core/models/pathways/` | `path_step.py` (extends Curriculum) | `path_step_dto.py` | `pathways_request.py` |
| **LP** | `core/models/pathways/` | `learning_path.py` | `learning_path_dto.py` | `pathways_request.py` |
| **Exercise** | `core/models/exercises/` | `exercise.py` | `exercise_dto.py` | `exercise_request.py` |

PathStep is THE curriculum content entity — it composes atomic Kus into coherent learning content and sits within a LearningPath.

### Services (Facade + Sub-services)
| Domain | Facade | Core | Search | Intelligence |
|--------|--------|------|--------|--------------|
| KU | `core/services/ku_service.py` | `ku/ku_core_service.py` | `ku/ku_search_service.py` | `ku/ku_intelligence_service.py` |
| PS | `core/services/ps_service.py` | `ps/ps_core_service.py` | `ps/ps_search_service.py` | `ps/ps_intelligence_service.py` |
| LP | `core/services/lp_service.py` | `lp/lp_core_service.py` | `lp/lp_search_service.py` | `lp/lp_intelligence_service.py` |

### Domain Backends
| Domain | Backend | Key Methods |
|--------|---------|-------------|
| KU | `KuBackend` (protocol: `KuOperations`) | ORGANIZES graph, usage summary, namespace/alias search, substance, prereqs, learning state |
| PS | `PsBackend` (5 mixins, protocol: `PsOperations`) | ORGANIZES, learning state (VIEWED/IN_PROGRESS/MASTERED/BOOKMARKED), semantic, knowledge context, adaptive |
| LP | `LpBackend` (3 mixins, protocol: `LpOperations`) | Path CRUD, HAS_STEP management, intelligence queries, graph context, mastery progress, search queries |
| Exercise | `ExerciseBackend` | Curriculum links, OWNS, student queries (group sharing via UnifiedSharingService, ADR-053) |

`KuBackend`, `PsBackend`, `LpBackend` live in `adapters/persistence/neo4j/backends/curriculum_backends.py`; `ExerciseBackend` lives in `backends/exercise_backends.py` alongside `RevisedExerciseBackend` and `EntryReportBackend`. Services call typed backend methods — no inline Cypher in service layer.

### PS Sub-services (`core/services/ps/`)
| Service | Purpose |
|---------|---------|
| `ps_core_service.py` | CRUD operations + persistence |
| `ps_search_service.py` | Text search, filtering |
| `ps_graph_service.py` | Graph traversal, prerequisites |
| `ps_semantic_service.py` | Semantic relationship management |
| `ps_practice_service.py` | Event-driven practice tracking |
| `ps_mastery_service.py` | Pedagogical tracking (VIEWED → IN_PROGRESS → MASTERED) |
| `ps_adaptive_service.py` | Adaptive learning recommendations |
| `ps_application_discovery_service.py` | Reverse relationship queries (where is knowledge applied?) |
| `ps_context_service.py` | Context-first knowledge recommendations |
| `ps_organization_service.py` | ORGANIZES relationships (non-linear nav / MOC pattern) |
| `ps_intelligence_service.py` | Readiness assessment, practice analysis |
| `ps_progress_service.py` | KU completion progress (event-driven) |
| `ps_ai_service.py` | Optional LLM/embedding features (FULL tier) |

### KU Sub-services (`core/services/ku/`)
| Service | Purpose |
|---------|---------|
| `ku_core_service.py` | CRUD operations for atomic knowledge units |
| `ku_search_service.py` | Text search, filtering |
| `ku_intelligence_service.py` | Usage summary, substance metrics |

### LP Sub-services (`core/services/lp/`)
| Service | Purpose |
|---------|---------|
| `lp_core_service.py` | CRUD + HAS_STEP management |
| `lp_search_service.py` | Search/filter |
| `lp_progress_service.py` | Mastery progress |
| `lp_intelligence_service.py` | Adaptive step, path validation |
| `lp_ai_service.py` | Optional LLM features |

### Factory Functions
| Domain | Factory | Location |
|--------|---------|----------|
| **PS** | `create_ps_sub_services()` | `core/services/curriculum_domain_config.py` |
| **LP** | `create_lp_sub_services()` | `core/services/curriculum_domain_config.py` |

### Routes
| Domain | Route file |
|--------|-----------|
| KU | `adapters/inbound/ku_routes.py` + `ku_ui.py` (KuService — the two learning-state POSTs); the Ku page is `learning_loop_routes.py`, the index `library_ui.py` |
| PS (API + UI) | `adapters/inbound/path_steps_routes.py` → `path_steps_api.py` + `path_steps_ui.py` |
| LP | `adapters/inbound/pathways_routes.py` |
| Exercise | `adapters/inbound/exercises_routes.py` + `exercises_ui.py` |

**PathStep UI / learning-loop routes:**
- `GET /path-steps` — PathStep list (fragment: `/path-steps/content`); rows link to `/explore/ps/{uid}`, with an "Enrolled" badge on the session user's IN_PROGRESS steps
- `GET /explore/ps/{uid}` — PathStep detail page in the Explore hub (reading-first, no sidebar; Alpine `pathstep` manages progress/bookmark)
- `POST /explore/ps/{uid}/progress` — update progress state (`state=learning|read`)
- `POST /explore/ps/{uid}/bookmark` — toggle bookmark (`on=true|false`)
- `GET /learning-loop/ps/{ps_uid}/exercises`, `/learning-loop/ps/{ps_uid}/submissions-and-feedback` — the HTMX fragments the PathStep page loads for the learning loop (`ui/explore/ps_detail.py`); `/learning-loop/ps/{ps_uid}/forms` (+ `POST …/forms/{template_uid}/submit`) is registered but no page loads it
- `POST /api/path-steps/organize` — ORGANIZES hierarchy (admin)
- `POST /api/path-steps/content` — content updates (admin)

**Ku UI Routes:**
- `GET /explore/library` — the full Ku/PathStep catalog (search + bento grid); `GET /library/ku` is the signed-in user's bookmarked Kus (`PINNED`), not an index
- `GET /explore/ku/{uid}` — Ku page (shell; body via `/explore/ku/{uid}/content`, related via `/explore/ku/{uid}/related`; `POST /explore/ku/{uid}/mastery-checkin`); there is no `/ku` route
- `POST /api/ku/{uid}/mark-studying` — Mark Ku as studying (IN_PROGRESS)
- `POST /api/ku/{uid}/mark-understood` — Mark Ku as understood (MASTERED)

**Note**: Ku has its own dedicated route config (`KU_CONFIG` in `ku_routes.py`), separate from PS routes. PS UI is absorbed into `path_steps_routes.py` (no separate `lp_routes.py` file — LP routes live in `pathways_routes.py`).

## UID Formats

| Domain | Format (authored = stored) | Example |
|--------|--------|---------|
| KU | `ku.{ns}.{slug}` authored; `ku_{slug}_{random}` API-generated | `ku.sel.empathy`, `ku_meditation-basics_x9y8z7w6` |
| PS | `ps.{namespace}.{slug}` | `ps.core.meditation-basics` |
| LP | `lp.{namespace}.{slug}` | `lp.core.intro-mindfulness` |

Dots join authored curriculum segments; a colon never appears in an authored curriculum uid — it is reserved for machine-minted identifiers, and the one entity family that carries it is the periodic UserEntry (`ue:daily:{user_uid}:{date}`, `ensure_periodic_note()`), which is a valid `ORGANIZES` target (CLAUDE.md § Curriculum Grouping Patterns, Separator grammar). **KU** is an atomic knowledge unit — lightweight, extends Entity directly. Hierarchy is in `ORGANIZES` relationships, not UIDs.

## Key Relationships

### PS (PathStep) Relationships
| Relationship | Direction | Target | Purpose |
|--------------|-----------|--------|---------|
| `USES_KU` | outgoing | KU | PathStep composes atomic Kus |
| `REQUIRES_KNOWLEDGE` | outgoing | KU | Knowledge prerequisites |
| `ENABLES_KNOWLEDGE` | outgoing | KU | Knowledge this step unlocks |
| `HAS_NARROWER` | outgoing | PS | Subconcepts |
| `RELATED_TO` | both | PS | Related topics |
| `ORGANIZES` | outgoing | PS / KU | Non-linear organization (MOC pattern) |
| `REQUIRES_STEP` | outgoing | PS | Step prerequisites |
| `IN_PROGRESS` / `MASTERED` / `BOOKMARKED` / `VIEWED` / `MARKED_AS_READ` | incoming | User | Learning state (user-owned edges) |

### KU Relationships
| Relationship | Direction | Target | Purpose |
|--------------|-----------|--------|---------|
| `USES_KU` | incoming | PS | Composed into PathSteps |
| `TRAINS_KU` | incoming | PS | Trained by Path Steps |
| `ORGANIZES` | both | KU / PS | Hierarchical grouping |

### PS Activity Relationships
Activity-domain integration lives directly on PathSteps (no intermediate Lesson node):

| Relationship | Direction | Target | Purpose |
|--------------|-----------|--------|---------|
| `BUILDS_HABIT` | outgoing | Habit | Practice integration |
| `ASSIGNS_TASK` | outgoing | Task | Practice integration |
| `SCHEDULES_EVENT` | outgoing | Event | Practice integration |
| `SUPPORTS_GOAL` | outgoing | Goal | Goal alignment |
| `GUIDED_BY_PRINCIPLE` | outgoing | Principle | Guidance |
| `INFORMS_CHOICE` | outgoing | Choice | Decision points |

### LP Relationships
| Relationship | Direction | Target | Purpose |
|--------------|-----------|--------|---------|
| `HAS_STEP` | outgoing | PS | Path structure (ordered) |
| `ALIGNED_WITH_GOAL` | outgoing | Goal | Goal alignment |
| `HAS_MILESTONE_EVENT` | outgoing | Event | Milestone tracking |
| `SERVES_LIFE_PATH` | incoming | User | Life path designation |

## Common Imports

```python
# Models
from core.models.curriculum import Curriculum
from core.models.curriculum_dto import CurriculumDTO
from core.models.ku.ku import Ku
from core.models.ku.ku_dto import KuDTO
from core.models.pathways.path_step import PathStep
from core.models.pathways.path_step_dto import PathStepDTO
from core.models.pathways.learning_path import LearningPath
from core.models.pathways.learning_path_dto import LearningPathDTO

# Results
from core.utils.result_simplified import Result

# Factory functions
from core.services.curriculum_domain_config import (
    create_ps_sub_services,
    create_lp_sub_services,
)
```

## Bootstrap Location

Services wired in: `services_bootstrap/_learning_services.py`

```python
# The shape of the wiring — read the live keyword set off the file itself
atomic_ku_service = KuService(
    backend=atomic_ku_backend,
    graph_intel=graph_intelligence,  # REQUIRED — fail-fast
    event_bus=event_bus,
)
ps_service = PsService(
    backend=knowledge_backend,
    executor=query_executor,
    graph_intel=graph_intelligence,
    event_bus=event_bus,
    ku_backend=atomic_ku_backend,
    chunking_service=chunking_service,
    user_service=user_service,
    vector_search_service=vector_search_service,
    embeddings_service=embeddings_service,
    ps_intelligence_backend=PsIntelligenceBackend(query_executor),
)
learning_paths = LpService(
    backend=lp_backend,
    ps_service=ps_service,
    ku_service=ps_service,  # PsService handles curriculum content
    progress_service=user_progress,
    graph_intel=graph_intelligence,
    event_bus=event_bus,
    progress_backend=progress_backend,
    user_service=user_service,  # without it LearningRecommendationEngine's handler exits early
)
```

## Intelligence Service Access

```python
# PS — the sub-service slots, read off PsService.__init__
ps_service.core.create_step(step)
ps_service.search.search(query)                      # BaseService search
ps_service.intelligence.is_ready(ps_uid, completed_step_uids)
ps_service.adaptive.get_sel_journey(user_uid)
ps_service.organization.get_organized_children(parent_uid)  # Non-linear nav (MOC)
ps_service.mastery.mark_mastered(user_uid, ps_uid, mastery_score)
# ps_service.progress is event-driven (handle_knowledge_mastered) — nothing to call

# KU — 4 sub-services
ku_service.core.create_ku(...)
ku_service.search.search(...)
ku_service.intelligence.get_usage_summary(ku_uid)

# LP — 5 sub-services (specialized Cypher on LpBackend)
lp_service.intelligence.validate_path_prerequisites(lp_uid)
lp_service.intelligence.get_next_adaptive_step(step_uid, user_uid)

# LP Facade aggregation
lp_service.get_dashboard_summary(user_uid, user_progress)
lp_service.filter_paths(difficulty, domain, duration)
lp_service.get_path_detail_progress(path_uid, user_progress, user_uid)
lp_service.get_learning_analytics(user_uid, user_progress)
```

## Sub-service Summary

| Domain | Count | Key Services |
|--------|-------|--------------|
| **KU** | 4 | core, search, relationships, intelligence |
| **PS** | 13 | core, search, graph, semantic, practice, mastery, relationships, intelligence, adaptive, application_discovery, context_service, organization, progress (+ optional `ai`) — read them off `PsService.__init__` |
| **LP** | 5 | core, search, relationships, intelligence, progress (+ optional `ai`) |

## Documentation

| Topic | Doc File |
|-------|----------|
| Architecture | `/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md` |
| PathStep content | `/docs/architecture/PATHSTEP_CONTENT_ARCHITECTURE.md` |
| MOC/Organization | `/docs/domains/moc.md` |
| ADR-013 (flat KU UID) | `/docs/decisions/ADR-013-ku-uid-flat-identity.md` |
| ADR-023 (BaseService) | `/docs/decisions/ADR-023-curriculum-baseservice-migration.md` |
