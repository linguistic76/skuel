# Curriculum Domains Quick Reference

> Fast lookup for file locations and domain-specific details.

## File Locations

### Models

| Domain | Directory | Model | DTO | Request |
|--------|-----------|-------|-----|---------|
| **Base** | `core/models/` | `curriculum.py` | `curriculum_dto.py` | — |
| **Lesson** | `core/models/lesson/` | `lesson.py` (extends Curriculum) | `lesson_dto.py` | `lesson_request.py` |
| **KU** | `core/models/ku/` | `ku.py` (extends Entity) | `ku_dto.py` | — |
| **PS** | `core/models/pathways/` | `path_step.py` | `path_step_dto.py` | `pathways_request.py` |
| **LP** | `core/models/pathways/` | `learning_path.py` | `learning_path_dto.py` | `pathways_request.py` |
| **Exercise** | `core/models/exercises/` | `exercise.py` | `exercise_dto.py` | `exercise_request.py` |

### Services (Facade + Sub-services)
| Domain | Facade | Core | Search | Intelligence |
|--------|--------|------|--------|--------------|
| Lesson | `core/services/lesson_service.py` | `lesson/lesson_core_service.py` | `lesson/lesson_search_service.py` | (via `lesson_adaptive_service.py`) |
| KU | `core/services/ku_service.py` | `ku/ku_core_service.py` | `ku/ku_search_service.py` | `ku/ku_intelligence_service.py` |
| PS | `core/services/ps_service.py` | `ps/ps_core_service.py` | `ps/ps_search_service.py` | `ps/ps_intelligence_service.py` |
| LP | `core/services/lp_service.py` | `lp/lp_core_service.py` | `lp/lp_search_service.py` | `lp/lp_intelligence_service.py` |

### Domain Backends
| Domain | Backend | Key Methods |
|--------|---------|-------------|
| Lesson | `LessonBackend` (59 methods, 5 mixins) | Organizes, learning state, semantic, knowledge context, adaptive |
| KU | `KuBackend` | ORGANIZES graph, usage summary, namespace/alias search (13 methods) |
| PS | `PsBackend` | CONTAINS_KNOWLEDGE CRUD, lesson progress tracking |
| LP | `LpBackend` (23 methods) | Path CRUD, HAS_STEP management, intelligence queries, graph context, mastery progress |
| Exercise | `ExerciseBackend` | Curriculum links, OWNS/FOR_GROUP, student queries (6 methods) |

All in `adapters/persistence/neo4j/domain_backends.py`. Services call typed backend methods — no inline Cypher in service layer.

### Lesson Sub-services (`core/services/lesson/`)
| Service | Purpose |
|---------|---------|
| `lesson_core_service.py` | CRUD operations |
| `lesson_search_service.py` | Text search, filtering |
| `lesson_graph_service.py` | Graph traversal, prerequisites, hub scores |
| `lesson_application_discovery_service.py` | Reverse relationship queries (where is knowledge applied?) |
| `lesson_context_service.py` | Context-first knowledge recommendations (*_for_user) |
| `lesson_semantic_service.py` | Semantic relationship management |
| `lesson_practice_service.py` | Practice tracking |
| `lesson_mastery_service.py` | Pedagogical tracking (VIEWED → IN_PROGRESS → MASTERED) |
| `lesson_adaptive_service.py` | Adaptive learning recommendations |
| `lesson_organization_service.py` | ORGANIZES relationships (non-linear nav / MOC pattern) |
| `lesson_ai_service.py` | AI-powered Lesson operations |
| `lesson_relationship_filters.py` | Relationship filtering utilities |

### KU Sub-services (`core/services/ku/`)
| Service | Purpose |
|---------|---------|
| `ku_core_service.py` | CRUD operations for atomic knowledge units |
| `ku_search_service.py` | Text search, filtering |

### Factory Functions
| Domain | Factory | Location |
|--------|---------|----------|
| **Lesson** | `create_lesson_sub_services()` | `core/services/curriculum_domain_config.py` |
| **PS** | `create_curriculum_sub_services()` | `core/services/curriculum_domain_config.py` |
| **LP** | `create_lp_sub_services()` | `core/services/curriculum_domain_config.py` |

### Routes
| Domain | Route file |
|--------|-----------|
| Lesson | `adapters/inbound/lesson_routes.py` (LessonService) |
| Lesson UI | `adapters/inbound/lesson_ui.py` (detail page + learning actions) |
| Lesson Listing | `adapters/inbound/curriculum_hub_ui.py` (`/lessons` browser with enrollment) |
| KU | `adapters/inbound/ku_routes.py` + `ku_ui.py` (KuService — index, detail, studying/understood) |
| PS + LP | `adapters/inbound/pathways_routes.py` |

**Lesson UI Routes:**
- `GET /lessons` — Lesson browser with enrollment buttons (Start Lesson / In Progress / Mastered)
- `GET /lesson/{uid}/details` — Full lesson reading page (markdown + TOC sidebar + metadata + actions)
- `POST /api/lesson/{uid}/start` — Start a lesson (marks IN_PROGRESS via `LessonMasteryService`)
- `POST /api/lesson/{uid}/mark-read` — Mark lesson as read
- `POST /api/lesson/{uid}/bookmark` — Toggle lesson bookmark

**Ku UI Routes:**
- `GET /ku` — Knowledge index with bookmarks sidebar
- `GET /ku/{uid}` — Ku detail page (description content, metadata, exercises)
- `POST /api/ku/{uid}/mark-studying` — Mark Ku as studying (IN_PROGRESS)
- `POST /api/ku/{uid}/mark-understood` — Mark Ku as understood (MASTERED)

**Note**: Ku has its own dedicated route config (`KU_CONFIG` in `ku_routes.py`), separate from Lesson routes. No separate `ls_routes.py`, `lp_routes.py`, or `moc_routes.py` files exist.

## UID Formats

| Domain | Format | Example |
|--------|--------|---------|
| Lesson | `l_{slug}_{random}` | `l_meditation-basics_a1b2c3d4` |
| KU | `ku_{slug}_{random}` | `ku_meditation-basics_x9y8z7w6` |
| PS | `ps:{random}` | `ps:a1b2c3d4` |
| LP | `lp:{random}` | `lp:x9y8z7w6` |

**Lesson** uses flat identity — slug from title, no hierarchical path. Hierarchy is in `ORGANIZES` relationships, not UIDs.

**KU** is an atomic knowledge unit — lightweight, extends Entity directly.

## Key Relationships

### Lesson Relationships
| Relationship | Direction | Target | Purpose |
|--------------|-----------|--------|---------|
| `USES_KU` | outgoing | KU | Lesson composes atomic Kus |
| `REQUIRES_KNOWLEDGE` | outgoing | Lesson | Prerequisites |
| `ENABLES` | outgoing | Lesson | Unlocks next concepts |
| `HAS_NARROWER` | outgoing | Lesson | Subconcepts |
| `RELATED_TO` | both | Lesson | Related topics |
| `ORGANIZES` | outgoing | Lesson | Non-linear organization (MOC pattern) |

### KU Relationships
| Relationship | Direction | Target | Purpose |
|--------------|-----------|--------|---------|
| `USES_KU` | incoming | Lesson | Composed into Lessons |
| `TRAINS_KU` | incoming | PS | Trained by Path Steps |

### PS Relationships
| Relationship | Direction | Target | Purpose |
|--------------|-----------|--------|---------|
| `HAS_LESSON` | outgoing | Lesson | Contains lesson (activity domains inherited via traversal) |
| `REQUIRES_STEP` | outgoing | PS | Step prerequisites |
| `TRAINS_KU` | outgoing | KU | Trains atomic knowledge units |
| `REQUIRES_KNOWLEDGE` | outgoing | Lesson | Knowledge prerequisites |

Activity domain relationships live on **Lessons**, inherited by PS via `(PS)-[:HAS_LESSON]->(Lesson)-[:rel]->`:

### Lesson Activity Relationships
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
| `CONTAINS_STEP` | outgoing | PS | Path structure |
| `ALIGNED_WITH_GOAL` | outgoing | Goal | Goal alignment |
| `HAS_MILESTONE_EVENT` | outgoing | Event | Milestone tracking |
| `SERVES_LIFE_PATH` | incoming | User | Life path designation |

## Common Imports

```python
# Models
from core.models.curriculum import Curriculum
from core.models.curriculum_dto import CurriculumDTO
from core.models.lesson.lesson import Lesson
from core.models.lesson.lesson_dto import LessonDTO
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
    create_lesson_sub_services,
    create_curriculum_sub_services,
    create_lp_sub_services,
)
```

## Bootstrap Location

Services wired in: `services_bootstrap/_learning_services.py`

```python
# In _create_learning_services():
    # Curriculum services use factories
    lesson_service = LessonService(lesson_backend, graph_intel, event_bus)
    ku_service = KuService(ku_backend, event_bus)
    ps_service = PsService(driver, graph_intel, event_bus)
    lp_service = LpService(backend=lp_backend, ps_service=ps_service, graph_intelligence_service=graph_intel, event_bus=event_bus)
```

## Intelligence Service Access

```python
# Lesson - adaptive recommendations (12 sub-services)
lesson_service.adaptive.get_recommendations(user_uid)
lesson_service.organization.get_organized_children(parent_uid)  # Non-linear nav
lesson_service.get_navigation(lesson_uid)  # Prev/next sibling in MOC order → KuNavigation

# KU - 4 sub-services, generic factory (matches PS)
ku_service.core.create_ku(...)
ku_service.search_service.search(...)
ku_service.intelligence.get_usage_summary(ku_uid)

# PS - 4 sub-services, generic factory
ps_service.intelligence.is_ready(ps_uid, completed_uids)

# LP - 5 sub-services, specialized factory (Cypher on LpBackend)
lp_service.intelligence.validate_path_prerequisites(lp_uid)
lp_service.intelligence.get_next_adaptive_step(step_uid, user_uid)

# LP Facade aggregation (extracted from pathways_ui.py, March 2026)
lp_service.get_dashboard_summary(user_uid, user_progress)  # Full dashboard data
lp_service.filter_paths(difficulty, domain, duration)       # Filtered path list
lp_service.get_path_detail_progress(path_uid, user_progress, user_uid)  # Path + mastery
lp_service.get_learning_analytics(user_uid, user_progress)  # Knowledge profile stats
```

## Sub-service Summary

| Domain | Count | Key Services |
|--------|-------|--------------|
| **Lesson** | 10 | core, search, graph, semantic, practice, mastery, adaptive, organization, ai, relationship_helpers |
| **KU** | 4 | core, search, relationships, intelligence |
| **PS** | 4 | core, search, intelligence, (ai) |
| **LP** | 5 | core, search, progress, intelligence, (ai) |

## Documentation

| Topic | Doc File |
|-------|----------|
| Architecture | `/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md` |
| MOC/Organization | `/docs/domains/moc.md` |
| ADR-013 (flat UID) | `/docs/decisions/ADR-013-ku-uid-flat-identity.md` |
| ADR-023 (BaseService) | `/docs/decisions/ADR-023-curriculum-baseservice-migration.md` |
