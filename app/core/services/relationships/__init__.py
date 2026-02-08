"""
Relationships Module - Unified Relationship Services for SKUEL
================================================================

Configuration-driven approach to relationship services.

**Components:**

1. **DomainRelationshipConfig** - Source of truth in ``core.models.relationship_registry``
2. **UnifiedRelationshipService** - Generic service that uses configuration
3. **Path-Aware Factory** - Creates typed path-aware entities from raw data
4. **DomainRelationships** - Generic relationship data container
5. **Extended Config** - Full specifications with query specs, link methods, etc.

**Usage:**

```python
from core.models.relationship_registry import TASKS_CONFIG
from core.services.relationships import UnifiedRelationshipService

tasks_relationship_service = UnifiedRelationshipService(
    backend=tasks_backend,
    graph_intel=graph_intel,
    config=TASKS_CONFIG,
)

await tasks_relationship_service.get_related_uids("knowledge", task_uid)
await tasks_relationship_service.get_cross_domain_context(task_uid)
```

Version: 3.0.0
Date: 2026-02-07
"""

from core.services.relationships.extended_config import (
    CrossContextSpec,
    ExtendedRelationshipConfig,
    LinkMethodSpec,
    PathAwareTypeSpec,
    PlanningMethodSpec,
    QuerySpec,
)
from core.services.relationships.path_aware_factory import (
    CROSS_CONTEXT_TYPE_MAP,
    PATH_AWARE_TYPE_MAP,
    create_cross_context,
    create_path_aware_entities_batch,
    create_path_aware_entity,
    get_domain_from_label,
)
from core.services.relationships.relationships_container import (
    DomainRelationships,
    GenericRelationships,
)
from core.services.relationships.unified_relationship_service import UnifiedRelationshipService

__all__ = [
    "CROSS_CONTEXT_TYPE_MAP",
    "CrossContextSpec",
    # Relationship container
    "DomainRelationships",
    # Extended configuration
    "ExtendedRelationshipConfig",
    "GenericRelationships",
    "LinkMethodSpec",
    "PATH_AWARE_TYPE_MAP",
    "PathAwareTypeSpec",
    "PlanningMethodSpec",
    "QuerySpec",
    # Service
    "UnifiedRelationshipService",
    "create_cross_context",
    "create_path_aware_entities_batch",
    # Path-aware factory
    "create_path_aware_entity",
    "get_domain_from_label",
]
