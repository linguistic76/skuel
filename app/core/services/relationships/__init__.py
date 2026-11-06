"""
Relationships Module - Unified Relationship Services for SKUEL
================================================================

Configuration-driven approach to relationship services.

**Components:**

1. **DomainRelationshipConfig** - Source of truth in ``core.models.relationship_registry``
2. **UnifiedRelationshipService** - Generic service that uses configuration
3. **Path-Aware Factory** - Creates typed path-aware entities from raw data

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
"""

from core.services.relationships.path_aware_factory import (
    CROSS_CONTEXT_TYPE_MAP,
    PATH_AWARE_TYPE_MAP,
    create_cross_context,
    create_path_aware_entities_batch,
    create_path_aware_entity,
    get_domain_from_label,
)
from core.services.relationships.unified_relationship_service import UnifiedRelationshipService

__all__ = [
    "CROSS_CONTEXT_TYPE_MAP",
    "PATH_AWARE_TYPE_MAP",
    # Service
    "UnifiedRelationshipService",
    "create_cross_context",
    "create_path_aware_entities_batch",
    # Path-aware factory
    "create_path_aware_entity",
    "get_domain_from_label",
]
