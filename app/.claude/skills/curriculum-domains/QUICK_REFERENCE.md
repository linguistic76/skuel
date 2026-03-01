# Curriculum Domains Quick Reference

> Fast lookup for file locations and domain-specific details.

## File Locations

### Models (all in `core/models/curriculum/`)
| Domain | Model | DTO | Request |
|--------|-------|-----|---------|
| **Base** | `curriculum.py` | `curriculum_dto.py` | `curriculum_requests.py` |
| **KU** | `ku.py` (leaf) | `ku_dto.py` | `curriculum_requests.py` |
| **LS** | `learning_step.py` | `learning_step_dto.py` | `curriculum_requests.py` |
| **LP** | `learning_path.py` | `learning_path_dto.py` | `curriculum_requests.py` |
| **Exercise** | `exercise.py` | `exercise_dto.py` | `exercise_request.py` |

### Services (Facade + Sub-services)
| Domain | Facade | Core | Search | Intelligence |
|--------|--------|------|--------|--------------|
| KU | `core/services/ku_service.py` | `ku/ku_core_service.py` | `ku/ku_search_service.py` | (via `ku_adaptive_service.py`) |
| LS | `core/services/ls_service.py` | `ls/ls_core_service.py` | `ls/ls_search_service.py` | `ls/ls_intelligence_service.py` |
| LP | `core/services/lp_service.py` | `lp/lp_core_service.py` | `lp/lp_search_service.py` | `lp_intelligence_service.py` (top-level) |

### KU Sub-services (`core/services/ku/`)
| Service | Purpose |
|---------|---------|
| `ku_core_service.py` | CRUD operations |
| `ku_search_service.py` | Text search, filtering |
| `ku_graph_service.py` | Graph navigation |
| `ku_semantic_service.py` | Semantic relationship management |
| `ku_practice_service.py` | Practice tracking |
| `ku_interaction_service.py` | Pedagogical tracking (VIEWED → IN_PROGRESS → MASTERED) |
| `ku_adaptive_service.py` | Adaptive learning recommendations |
| `ku_organization_service.py` | ORGANIZES relationships (non-linear nav / MOC pattern) |
| `ku_ai_service.py` | AI-powered KU operations |

### Factory Functions
| Domain | Factory | Location |
|--------|---------|----------|
| **KU** | `create_ku_sub_services()` | `core/utils/curriculum_domain_config.py` |
| **LS** | `create_curriculum_sub_services()` | `core/utils/curriculum_domain_config.py` |
| **LP** | `create_lp_sub_services()` | `core/utils/curriculum_domain_config.py` |

### Routes
All curriculum domain routes are consolidated under:
- `adapters/inbound/ku_routes.py` — KU domain (all 9 sub-services)
- `adapters/inbound/learning_routes.py` — LS and LP routes

**Note**: No separate `ls_routes.py`, `lp_routes.py`, or `moc_routes.py` files exist.

## UID Formats

| Domain | Format | Example |
|--------|--------|---------|
| KU | `ku_{slug}_{random}` | `ku_meditation-basics_a1b2c3d4` |
| LS | `ls:{random}` | `ls:a1b2c3d4` |
| LP | `lp:{random}` | `lp:x9y8z7w6` |

**KU uses flat identity (ADR-013)** - slug from title, no hierarchical path. Hierarchy is in `ORGANIZES` relationships, not UIDs.

## Key Relationships

### KU Relationships
| Relationship | Direction | Target | Purpose |
|--------------|-----------|--------|---------|
| `REQUIRES_KNOWLEDGE` | outgoing | KU | Prerequisites |
| `ENABLES` | outgoing | KU | Unlocks next concepts |
| `HAS_NARROWER` | outgoing | KU | Subconcepts |
| `RELATED_TO` | both | KU | Related topics |
| `ORGANIZES` | outgoing | KU | Non-linear organization (MOC pattern) |

### LS Relationships
| Relationship | Direction | Target | Purpose |
|--------------|-----------|--------|---------|
| `REQUIRES_STEP` | outgoing | LS | Step prerequisites |
| `REQUIRES_KNOWLEDGE` | outgoing | KU | Knowledge prerequisites |
| `BUILDS_HABIT` | outgoing | Habit | Practice integration |
| `ASSIGNS_TASK` | outgoing | Task | Practice integration |
| `SCHEDULES_EVENT` | outgoing | Event | Practice integration |
| `GUIDED_BY_PRINCIPLE` | outgoing | Principle | Guidance |
| `OFFERS_CHOICE` | outgoing | Choice | Decision points |

### LP Relationships
| Relationship | Direction | Target | Purpose |
|--------------|-----------|--------|---------|
| `CONTAINS_STEP` | outgoing | LS | Path structure |
| `ALIGNED_WITH_GOAL` | outgoing | Goal | Goal alignment |
| `HAS_MILESTONE_EVENT` | outgoing | Event | Milestone tracking |
| `SERVES_LIFE_PATH` | incoming | User | Life path designation |

## Common Imports

```python
# Models (all in core/models/curriculum/)
from core.models.curriculum.curriculum import Curriculum
from core.models.curriculum.curriculum_dto import CurriculumDTO
from core.models.curriculum.ku import Ku
from core.models.curriculum.ku_dto import KuDTO
from core.models.curriculum.learning_step import LearningStep
from core.models.curriculum.learning_step_dto import LearningStepDTO
from core.models.curriculum.learning_path import LearningPath
from core.models.curriculum.learning_path_dto import LearningPathDTO

# Results
from core.utils.result_simplified import Result

# Factory functions
from core.utils.curriculum_domain_config import (
    create_ku_sub_services,
    create_curriculum_sub_services,
    create_lp_sub_services,
)
```

## Bootstrap Location

Services wired in: `services_bootstrap.py`

```python
async def compose_services(neo4j_adapter, event_bus=None) -> Result[Services]:
    # Curriculum services use factories
    ku_service = KuService(ku_backend, graph_intel, event_bus)
    ls_service = LsService(driver, graph_intel, event_bus)
    lp_service = LpService(driver, ls_service, graph_intel, event_bus)  # Cross-domain dep
```

## Intelligence Service Access

```python
# KU - adaptive recommendations (9 sub-services)
ku_service.adaptive.get_recommendations(user_uid)
ku_service.organization.get_subkus(parent_uid)  # Non-linear nav

# LS - 4 sub-services, generic factory
ls_service.intelligence.is_ready(ls_uid, completed_uids)

# LP - 5 sub-services, specialized factory
lp_service.intelligence.validate_path_prerequisites(lp_uid)
lp_service.intelligence.get_adaptive_sequence(lp_uid, user_uid)
```

## Sub-service Summary

| Domain | Count | Key Services |
|--------|-------|--------------|
| **KU** | 9 | core, search, graph, semantic, practice, interaction, adaptive, organization, ai |
| **LS** | 4 | core, search, intelligence, (ai) |
| **LP** | 5 | core, search, progress, intelligence, (ai) |

## Documentation

| Topic | Doc File |
|-------|----------|
| Architecture | `/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md` |
| MOC/Organization | `/docs/domains/moc.md` |
| ADR-013 (flat UID) | `/docs/decisions/ADR-013-ku-uid-flat-identity.md` |
| ADR-023 (BaseService) | `/docs/decisions/ADR-023-curriculum-baseservice-migration.md` |
