"""
Relationships Module - Unified Relationship Services for SKUEL
================================================================

This module provides a configuration-driven approach to relationship services,
replacing 14 domain-specific services (~11,000 lines) with a single generic
service + configuration objects.

**Components:**

1. **RelationshipConfig** - Configuration dataclass for domain-specific behavior
2. **UnifiedRelationshipService** - Generic service that uses configuration
3. **Domain Configs** - Pre-defined configurations for all 14 domains
4. **Path-Aware Factory** - Creates typed path-aware entities from raw data
5. **DomainRelationships** - Generic relationship data container
6. **Extended Config** - Full specifications with query specs, link methods, etc.

**Usage:**

```python
from core.services.relationships import (
    UnifiedRelationshipService,
    TASK_CONFIG,
    GOAL_CONFIG,
)

# Create relationship service for tasks
tasks_relationship_service = UnifiedRelationshipService(
    backend=tasks_backend,
    graph_intel=graph_intel,
    config=TASK_CONFIG,
)

# All methods available generically
await tasks_relationship_service.get_related_uids("knowledge", task_uid)
await tasks_relationship_service.has_relationship("prerequisites", task_uid)
await tasks_relationship_service.get_cross_domain_context(task_uid)
await tasks_relationship_service.fetch_all_relationships(task_uid)

# UserContext-aware methods
await tasks_relationship_service.get_actionable_for_user(context)
await tasks_relationship_service.get_blocked_for_user(context)

# Typed link methods
await tasks_relationship_service.link_to_knowledge(task_uid, ku_uid)
await tasks_relationship_service.link_to_goal(task_uid, goal_uid)
```

**Migration Path:**

Old service-specific code:
```python
# Before
tasks_service = TasksRelationshipService(backend, graph_intel)
knowledge_uids = await tasks_service.get_task_knowledge(task_uid)
```

New unified approach:
```python
# After
tasks_service = UnifiedRelationshipService(backend, TASK_CONFIG, graph_intel)
knowledge_uids = await tasks_service.get_related_uids("knowledge", task_uid)
```

Version: 2.0.0
Date: 2025-12-03
"""

from core.services.relationships.domain_configs import (
    ACTIVITY_DOMAIN_CONFIGS,
    CHOICE_CONFIG,
    EVENT_CONFIG,
    GOAL_CONFIG,
    HABIT_CONFIG,
    PRINCIPLE_CONFIG,
    TASK_CONFIG,
    get_config_for_domain,
)
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
from core.services.relationships.relationship_config import (
    CrossDomainMapping,
    RelationshipConfig,
    RelationshipSpec,
)
from core.services.relationships.relationships_container import (
    DomainRelationships,
    GenericRelationships,
)
from core.services.relationships.unified_relationship_service import UnifiedRelationshipService

__all__ = [
    # Registry
    "ACTIVITY_DOMAIN_CONFIGS",
    "CHOICE_CONFIG",
    "CROSS_CONTEXT_TYPE_MAP",
    "EVENT_CONFIG",
    "GOAL_CONFIG",
    "HABIT_CONFIG",
    "PATH_AWARE_TYPE_MAP",
    "PRINCIPLE_CONFIG",
    # Activity Domain configs (6 domains - User-owned)
    "TASK_CONFIG",
    "CrossContextSpec",
    "CrossDomainMapping",
    # Relationship container
    "DomainRelationships",
    # Extended configuration
    "ExtendedRelationshipConfig",
    "GenericRelationships",
    "LinkMethodSpec",
    "PathAwareTypeSpec",
    "PlanningMethodSpec",
    "QuerySpec",
    # Configuration classes
    "RelationshipConfig",
    "RelationshipSpec",
    # Service
    "UnifiedRelationshipService",
    "create_cross_context",
    "create_path_aware_entities_batch",
    # Path-aware factory
    "create_path_aware_entity",
    "get_config_for_domain",
    "get_domain_from_label",
]
