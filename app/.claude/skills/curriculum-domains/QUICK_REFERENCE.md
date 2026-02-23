# Curriculum Domains Quick Reference

> Fast lookup for file locations and domain-specific details.

## File Locations

### Models
| Domain | Model | DTO | Request |
|--------|-------|-----|---------|
| KU | `core/models/ku/ku.py` | `ku_dto.py` | `ku_request.py` |
| LS | `core/models/ls/ls.py` | `ls_dto.py` | `ls_request.py` |
| LP | `core/models/lp/lp.py` | `lp_dto.py` | `lp_request.py` |
| MOC | `core/models/moc/moc.py` | `moc_dto.py` | `moc_request.py` |

### Services (Facade + Sub-services)
| Domain | Facade | Core | Search | Intelligence |
|--------|--------|------|--------|--------------|
| KU | `core/services/ku_service.py` | `ku/ku_core_service.py` | `ku_search_service.py` | `ku_intelligence_service.py` |
| LS | `core/services/ls_service.py` | `ls/ls_core_service.py` | `ls/ls_search_service.py` | `ls/ls_intelligence_service.py` |
| LP | `core/services/lp_service.py` | `lp/lp_core_service.py` | `lp/lp_search_service.py` | `lp_intelligence_service.py` |
| MOC | `core/services/moc_service.py` | `moc/moc_core_service.py` | `moc/moc_search_service.py` | `moc/moc_intelligence_service.py` |

### Factory Functions
| Domain | Factory | Location |
|--------|---------|----------|
| KU | `create_ku_sub_services()` | `core/utils/curriculum_domain_config.py` |
| LS | `create_curriculum_sub_services()` | `core/utils/curriculum_domain_config.py` |
| LP | `create_lp_sub_services()` | `core/utils/curriculum_domain_config.py` |
| MOC | Manual in `__init__()` | `core/services/moc_service.py` |

### UI
| Domain | Routes | Views |
|--------|--------|-------|
| KU | `adapters/inbound/ku_routes.py` | `components/ku_views.py` |
| LS | `adapters/inbound/ls_routes.py` | `components/ls_views.py` |
| LP | `adapters/inbound/lp_routes.py` | `components/lp_views.py` |
| MOC | `adapters/inbound/moc_routes.py` | `components/moc_views.py` |

## UID Formats

| Domain | Format | Example |
|--------|--------|---------|
| KU | `ku.{filename}` | `ku.python-basics` |
| LS | `ls.{path-slug}.{step-name}` | `ls.python-fundamentals.variables` |
| LP | `lp.{path-name}` | `lp.python-fundamentals` |
| MOC | `moc.{map-name}` | `moc.python-ecosystem` |

**Note:** KU uses flat identity (ADR-013) - filename only, NOT hierarchical path.

## Key Relationships

### KU Relationships
| Relationship | Direction | Target | Purpose |
|--------------|-----------|--------|---------|
| `REQUIRES_KNOWLEDGE` | outgoing | KU | Prerequisites |
| `ENABLES` | outgoing | KU | Unlocks next concepts |
| `HAS_NARROWER` | outgoing | KU | Subconcepts |
| `RELATED_TO` | both | KU | Related topics |

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

### MOC Relationships
| Relationship | Direction | Target | Purpose |
|--------------|-----------|--------|---------|
| `CONTAINS_PATH` | outgoing | LP | Contains learning paths |
| `CONTAINS_PRINCIPLE` | outgoing | Principle | Contains principles |
| `BRIDGES_TO` | both | MOC | Cross-domain bridges |
| `HAS_SECTION` | outgoing | Section | Hierarchical structure |

## Common Imports

```python
# Models
from core.models.ku.ku import Ku
from core.models.ku.curriculum_dto import CurriculumDTO
from core.models.ls.ls import Ls
from core.models.ls.ls_dto import LearningStepDTO
from core.models.lp.lp import Lp
from core.models.lp.lp_dto import LearningPathDTO
from core.models.moc.moc import Moc, MapOfContent
from core.models.moc.moc_dto import MocDTO

# Results
from core.utils.result_simplified import Result

# Relationship configs (direct from registry)
from core.models.relationship_registry import KU_CONFIG, LS_CONFIG, LP_CONFIG, LABEL_CONFIGS

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
    # Curriculum services use factories or manual creation
    ku_service = KuService(ku_backend, graph_intel, event_bus)
    ls_service = LsService(driver, graph_intel, event_bus)  # Creates backend internally
    lp_service = LpService(driver, ls_service, graph_intel, event_bus)  # Cross-domain dep
    moc_service = MocService(moc_backend, driver, graph_intel, event_bus)  # Manual creation
```

## Intelligence Service Access

All Curriculum domains create intelligence internally:

```python
# KU - 8 sub-services, specialized factory
# Intelligence created BEFORE core (circular dependency)
ku_service.intelligence.get_ku_with_context(uid)
ku_service.intelligence.calculate_user_substance(ku_uid, user_uid)

# LS - 4 sub-services, generic factory (simplest)
ls_service.intelligence.is_ready(ls_uid, completed_uids)
ls_service.intelligence.calculate_guidance_strength(ls_uid)
ls_service.intelligence.practice_completeness_score(ls_uid)

# LP - 5 sub-services, specialized factory
# Intelligence consolidates validation, analysis, adaptive, context
lp_service.intelligence.validate_path_prerequisites(lp_uid)
lp_service.intelligence.get_adaptive_sequence(lp_uid, user_uid)
lp_service.intelligence.identify_path_blockers(lp_uid, user_uid)

# MOC - 8 sub-services, manual creation (circular core↔section)
moc_service.intelligence.suggest_navigation(moc_uid, user_context)
moc_service.intelligence.calculate_coverage(moc_uid)
```

## Sub-service Summary

| Domain | Count | Pattern | Key Services |
|--------|-------|---------|--------------|
| **KU** | 8 | Specialized factory | core, search, graph, semantic, practice, interaction, relationships, intelligence |
| **LS** | 4 | Generic factory | core, search, relationships, intelligence |
| **LP** | 5 | Specialized factory | core, search, relationships, progress, intelligence |
| **MOC** | 8 | Manual | core, section, content, discovery, search, intelligence, relationships (x2) |

## Documentation

| Domain | Doc File |
|--------|----------|
| KU | `/docs/intelligence/KU_INTELLIGENCE.md` |
| LS | `/docs/intelligence/LS_INTELLIGENCE.md` |
| LP | `/docs/intelligence/LP_INTELLIGENCE.md` |
| MOC | `/docs/intelligence/MOC_INTELLIGENCE.md` |
| Architecture | `/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md` |
| ADR-023 | `/docs/decisions/ADR-023-curriculum-baseservice-migration.md` |
| ADR-026 | `/docs/decisions/ADR-026-unified-relationship-registry.md` |
