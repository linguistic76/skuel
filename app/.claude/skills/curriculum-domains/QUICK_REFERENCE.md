# Curriculum Domains Quick Reference

> Fast lookup for file locations and domain-specific details.

## File Locations

### Models

| Domain | Directory | Model | DTO | Request |
|--------|-----------|-------|-----|---------|
| **Base** | `core/models/` | `curriculum.py` | `curriculum_dto.py` | — |
| **Article** | `core/models/article/` | `article.py` (extends Curriculum) | `article_dto.py` | `article_request.py` |
| **KU** | `core/models/ku/` | `ku.py` (extends Entity) | `ku_dto.py` | — |
| **LS** | `core/models/pathways/` | `learning_step.py` | `learning_step_dto.py` | `pathways_request.py` |
| **LP** | `core/models/pathways/` | `learning_path.py` | `learning_path_dto.py` | `pathways_request.py` |
| **Exercise** | `core/models/exercises/` | `exercise.py` | `exercise_dto.py` | `exercise_request.py` |

### Services (Facade + Sub-services)
| Domain | Facade | Core | Search | Intelligence |
|--------|--------|------|--------|--------------|
| Article | `core/services/article_service.py` | `article/article_core_service.py` | `article/article_search_service.py` | (via `article_adaptive_service.py`) |
| KU | `core/services/ku_service.py` | `ku/ku_core_service.py` | `ku/ku_search_service.py` | `ku/ku_intelligence_service.py` |
| LS | `core/services/ls_service.py` | `ls/ls_core_service.py` | `ls/ls_search_service.py` | `ls/ls_intelligence_service.py` |
| LP | `core/services/lp_service.py` | `lp/lp_core_service.py` | `lp/lp_search_service.py` | `lp_intelligence_service.py` (top-level) |

### Article Sub-services (`core/services/article/`)
| Service | Purpose |
|---------|---------|
| `article_core_service.py` | CRUD operations |
| `article_search_service.py` | Text search, filtering |
| `article_graph_service.py` | Graph navigation |
| `article_semantic_service.py` | Semantic relationship management |
| `article_practice_service.py` | Practice tracking |
| `article_mastery_service.py` | Pedagogical tracking (VIEWED → IN_PROGRESS → MASTERED) |
| `article_adaptive_service.py` | Adaptive learning recommendations |
| `article_organization_service.py` | ORGANIZES relationships (non-linear nav / MOC pattern) |
| `article_ai_service.py` | AI-powered Article operations |
| `article_relationship_helpers.py` | Relationship filtering utilities |

### KU Sub-services (`core/services/ku/`)
| Service | Purpose |
|---------|---------|
| `ku_core_service.py` | CRUD operations for atomic knowledge units |
| `ku_search_service.py` | Text search, filtering |

### Factory Functions
| Domain | Factory | Location |
|--------|---------|----------|
| **Article** | `create_article_sub_services()` | `core/utils/curriculum_domain_config.py` |
| **LS** | `create_curriculum_sub_services()` | `core/utils/curriculum_domain_config.py` |
| **LP** | `create_lp_sub_services()` | `core/utils/curriculum_domain_config.py` |

### Routes
| Domain | Route file |
|--------|-----------|
| Article | `adapters/inbound/article_routes.py` (all Article sub-services) |
| KU | (via Article routes or dedicated — see `article_routes.py`) |
| LS + LP | `adapters/inbound/pathways_routes.py` |

**Note**: No separate `ls_routes.py`, `lp_routes.py`, or `moc_routes.py` files exist.

## UID Formats

| Domain | Format | Example |
|--------|--------|---------|
| Article | `a_{slug}_{random}` | `a_meditation-basics_a1b2c3d4` |
| KU | `ku_{slug}_{random}` | `ku_meditation-basics_x9y8z7w6` |
| LS | `ls:{random}` | `ls:a1b2c3d4` |
| LP | `lp:{random}` | `lp:x9y8z7w6` |

**Article** uses flat identity — slug from title, no hierarchical path. Hierarchy is in `ORGANIZES` relationships, not UIDs.

**KU** is an atomic knowledge unit — lightweight, extends Entity directly.

## Key Relationships

### Article Relationships
| Relationship | Direction | Target | Purpose |
|--------------|-----------|--------|---------|
| `USES_KU` | outgoing | KU | Article composes atomic Kus |
| `REQUIRES_KNOWLEDGE` | outgoing | Article | Prerequisites |
| `ENABLES` | outgoing | Article | Unlocks next concepts |
| `HAS_NARROWER` | outgoing | Article | Subconcepts |
| `RELATED_TO` | both | Article | Related topics |
| `ORGANIZES` | outgoing | Article | Non-linear organization (MOC pattern) |

### KU Relationships
| Relationship | Direction | Target | Purpose |
|--------------|-----------|--------|---------|
| `USES_KU` | incoming | Article | Composed into Articles |
| `TRAINS_KU` | incoming | LS | Trained by Learning Steps |

### LS Relationships
| Relationship | Direction | Target | Purpose |
|--------------|-----------|--------|---------|
| `REQUIRES_STEP` | outgoing | LS | Step prerequisites |
| `TRAINS_KU` | outgoing | KU | Trains atomic knowledge units |
| `REQUIRES_KNOWLEDGE` | outgoing | Article | Knowledge prerequisites |
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
# Models
from core.models.curriculum import Curriculum
from core.models.curriculum_dto import CurriculumDTO
from core.models.article.article import Article
from core.models.article.article_dto import ArticleDTO
from core.models.ku.ku import Ku
from core.models.ku.ku_dto import KuDTO
from core.models.pathways.learning_step import LearningStep
from core.models.pathways.learning_step_dto import LearningStepDTO
from core.models.pathways.learning_path import LearningPath
from core.models.pathways.learning_path_dto import LearningPathDTO

# Results
from core.utils.result_simplified import Result

# Factory functions
from core.utils.curriculum_domain_config import (
    create_article_sub_services,
    create_curriculum_sub_services,
    create_lp_sub_services,
)
```

## Bootstrap Location

Services wired in: `services_bootstrap.py`

```python
async def compose_services(neo4j_adapter, event_bus=None) -> Result[Services]:
    # Curriculum services use factories
    article_service = ArticleService(article_backend, graph_intel, event_bus)
    ku_service = KuService(ku_backend, event_bus)
    ls_service = LsService(driver, graph_intel, event_bus)
    lp_service = LpService(driver, ls_service, graph_intel, event_bus)  # Cross-domain dep
```

## Intelligence Service Access

```python
# Article - adaptive recommendations (10 sub-services)
article_service.adaptive.get_recommendations(user_uid)
article_service.organization.get_organized_children(parent_uid)  # Non-linear nav

# KU - 4 sub-services, generic factory (matches LS)
ku_service.core.create_ku(...)
ku_service.search_service.search(...)
ku_service.intelligence.get_usage_summary(ku_uid)

# LS - 4 sub-services, generic factory
ls_service.intelligence.is_ready(ls_uid, completed_uids)

# LP - 5 sub-services, specialized factory
lp_service.intelligence.validate_path_prerequisites(lp_uid)
lp_service.intelligence.get_adaptive_sequence(lp_uid, user_uid)
```

## Sub-service Summary

| Domain | Count | Key Services |
|--------|-------|--------------|
| **Article** | 10 | core, search, graph, semantic, practice, interaction, adaptive, organization, ai, relationship_helpers |
| **KU** | 4 | core, search, relationships, intelligence |
| **LS** | 4 | core, search, intelligence, (ai) |
| **LP** | 5 | core, search, progress, intelligence, (ai) |

## Documentation

| Topic | Doc File |
|-------|----------|
| Architecture | `/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md` |
| MOC/Organization | `/docs/domains/moc.md` |
| ADR-013 (flat UID) | `/docs/decisions/ADR-013-ku-uid-flat-identity.md` |
| ADR-023 (BaseService) | `/docs/decisions/ADR-023-curriculum-baseservice-migration.md` |
