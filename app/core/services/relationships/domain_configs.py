"""
Domain Configurations - RelationshipConfig Definitions for Searchable Domains
=============================================================================

**January 2026 Unified Architecture:**

Activity and Curriculum domains use UnifiedRelationshipService.
Finance is standalone (no relationship configuration).

**Activity Domains (6):** Generated from UnifiedRelationshipRegistry
- Tasks, Goals, Habits, Events, Choices, Principles

**Curriculum Domains (4):** Manual configs with ordering/edge metadata support
- LP (Learning Path), LS (Learning Step), KU (Knowledge Unit), MOC (Map of Content)

**Key Features for Curriculum:**
- order_by_property: Ordered relationships (HAS_STEP ordered by sequence)
- include_edge_properties: Edge metadata retrieval
- ownership_relationship=None: Shared content (no user ownership)

**Usage:**
```python
from core.services.relationships import LP_CONFIG, UnifiedRelationshipService

lp_relationship_service = UnifiedRelationshipService(
    backend=lp_backend,
    graph_intel=graph_intel,
    config=LP_CONFIG,
)

# Get steps in order
result = await lp_relationship_service.get_ordered_related_uids(
    "steps", "lp:python"
)
```

Version: 3.0.0
Date: 2026-01-07
"""

from collections.abc import Callable

from core.models.relationship_names import RelationshipName
from core.models.shared_enums import Domain

# =============================================================================
# CONFIGURATION REGISTRY - Generated from UnifiedRelationshipRegistry
# =============================================================================
from core.models.unified_relationship_registry import generate_relationship_config
from core.services.relationships.relationship_config import RelationshipConfig, RelationshipSpec

# Activity Domain configs (6 domains - User-owned entities)
# Note: Finance is standalone bookkeeping (not in unified architecture)
#
# All configs are GENERATED from UnifiedRelationshipRegistry (ADR-026).

# Generate configs from unified registry
# All 6 Activity Domains are in UNIFIED_REGISTRY - assert non-None
_GENERATED_TASK_CONFIG = generate_relationship_config(Domain.TASKS)
_GENERATED_GOAL_CONFIG = generate_relationship_config(Domain.GOALS)
_GENERATED_HABIT_CONFIG = generate_relationship_config(Domain.HABITS)
_GENERATED_EVENT_CONFIG = generate_relationship_config(Domain.EVENTS)
_GENERATED_CHOICE_CONFIG = generate_relationship_config(Domain.CHOICES)
_GENERATED_PRINCIPLE_CONFIG = generate_relationship_config(Domain.PRINCIPLES)

# Type narrowing: all 6 Activity Domains are guaranteed in registry
assert _GENERATED_TASK_CONFIG is not None, "TASKS domain must be in registry"
assert _GENERATED_GOAL_CONFIG is not None, "GOALS domain must be in registry"
assert _GENERATED_HABIT_CONFIG is not None, "HABITS domain must be in registry"
assert _GENERATED_EVENT_CONFIG is not None, "EVENTS domain must be in registry"
assert _GENERATED_CHOICE_CONFIG is not None, "CHOICES domain must be in registry"
assert _GENERATED_PRINCIPLE_CONFIG is not None, "PRINCIPLES domain must be in registry"

# Use generated configs in the registry
ACTIVITY_DOMAIN_CONFIGS: dict[Domain, RelationshipConfig] = {
    Domain.TASKS: _GENERATED_TASK_CONFIG,
    Domain.GOALS: _GENERATED_GOAL_CONFIG,
    Domain.HABITS: _GENERATED_HABIT_CONFIG,
    Domain.EVENTS: _GENERATED_EVENT_CONFIG,
    Domain.CHOICES: _GENERATED_CHOICE_CONFIG,
    Domain.PRINCIPLES: _GENERATED_PRINCIPLE_CONFIG,
}

# Re-export with standard names for backward compatibility
# These now point to generated configs
TASK_CONFIG = _GENERATED_TASK_CONFIG
GOAL_CONFIG = _GENERATED_GOAL_CONFIG
HABIT_CONFIG = _GENERATED_HABIT_CONFIG
EVENT_CONFIG = _GENERATED_EVENT_CONFIG
CHOICE_CONFIG = _GENERATED_CHOICE_CONFIG
PRINCIPLE_CONFIG = _GENERATED_PRINCIPLE_CONFIG


def get_config_for_domain(domain: Domain) -> RelationshipConfig | None:
    """
    Get RelationshipConfig for a domain.

    Args:
        domain: Domain enum value

    Returns:
        RelationshipConfig or None if domain not configured

    Note:
        Returns generated configs for Activity Domains, manual configs for Curriculum.
    """
    if domain in ACTIVITY_DOMAIN_CONFIGS:
        return ACTIVITY_DOMAIN_CONFIGS[domain]
    return CURRICULUM_DOMAIN_CONFIGS.get(domain)


# =============================================================================
# CURRICULUM DOMAIN CONFIGS (January 2026 - Unified Architecture)
# =============================================================================
# Manual configs with ordering/edge metadata support for curriculum patterns.
# These support:
# - Ordered relationships (HAS_STEP with sequence)
# - Edge metadata (sequence, completed properties)
# - Hierarchical traversal (LP → LS → KU)

# Lazy imports to avoid circular dependencies
_lp_dto_class = None
_lp_model_class = None
_ls_dto_class = None
_ls_model_class = None
_ku_dto_class = None
_ku_model_class = None
# NOTE: _moc_dto_class, _moc_model_class removed (January 2026) - MOC is KU-based


def _get_lp_classes() -> tuple[type, type]:
    """Lazy load LP DTO and model classes."""
    global _lp_dto_class, _lp_model_class
    if _lp_dto_class is None:
        from core.models.lp.lp import Lp
        from core.models.lp.lp_dto import LpDTO

        _lp_dto_class = LpDTO
        _lp_model_class = Lp
    return _lp_dto_class, _lp_model_class


def _get_ls_classes() -> tuple[type, type]:
    """Lazy load LS DTO and model classes."""
    global _ls_dto_class, _ls_model_class
    if _ls_dto_class is None:
        from core.models.ls.ls import Ls
        from core.models.ls.ls_dto import LearningStepDTO

        _ls_dto_class = LearningStepDTO
        _ls_model_class = Ls
    return _ls_dto_class, _ls_model_class


def _get_ku_classes() -> tuple[type, type]:
    """Lazy load KU DTO and model classes."""
    global _ku_dto_class, _ku_model_class
    if _ku_dto_class is None:
        from core.models.ku.ku import Ku
        from core.models.ku.ku_dto import KuDTO

        _ku_dto_class = KuDTO
        _ku_model_class = Ku
    return _ku_dto_class, _ku_model_class


# NOTE: _get_moc_classes removed (January 2026) - MOC is now KU-based


def _create_lp_config() -> RelationshipConfig:
    """
    Create LP (Learning Path) config.

    Key features:
    - HAS_STEP relationship with sequence ordering
    - Edge metadata (sequence, completed)
    - Cross-domain links to Goals, Principles
    """
    dto_class, model_class = _get_lp_classes()

    return RelationshipConfig(
        domain=Domain.LEARNING,
        entity_label="Lp",
        dto_class=dto_class,
        model_class=model_class,
        backend_get_method="get",
        use_semantic_helper=False,
        ownership_relationship=None,  # Shared content
        outgoing_relationships={
            "steps": RelationshipSpec(
                relationship=RelationshipName.HAS_STEP,
                direction="outgoing",
                order_by_property="sequence",
                order_direction="ASC",
                include_edge_properties=("sequence", "completed"),
            ),
            "prerequisites": RelationshipSpec(
                relationship=RelationshipName.REQUIRES_KNOWLEDGE,
                direction="outgoing",
            ),
            "goals": RelationshipSpec(
                relationship=RelationshipName.ALIGNED_WITH_GOAL,
                direction="outgoing",
            ),
            "principles": RelationshipSpec(
                relationship=RelationshipName.EMBODIES_PRINCIPLE,
                direction="outgoing",
            ),
            "milestones": RelationshipSpec(
                relationship=RelationshipName.HAS_MILESTONE_EVENT,
                direction="outgoing",
            ),
        },
        incoming_relationships={
            "in_mocs": RelationshipSpec(
                relationship=RelationshipName.CONTAINS_PATH,
                direction="incoming",
            ),
        },
    )


def _create_ls_config() -> RelationshipConfig:
    """
    Create LS (Learning Step) config.

    Key features:
    - Knowledge relationships (contains, requires)
    - Practice pattern relationships (habits, tasks, events)
    - Guidance relationships (principles, choices)
    """
    dto_class, model_class = _get_ls_classes()

    return RelationshipConfig(
        domain=Domain.LEARNING,
        entity_label="Ls",
        dto_class=dto_class,
        model_class=model_class,
        backend_get_method="get",
        use_semantic_helper=False,
        ownership_relationship=None,  # Shared content
        outgoing_relationships={
            "knowledge": RelationshipSpec(
                relationship=RelationshipName.CONTAINS_KNOWLEDGE,
                direction="outgoing",
            ),
            "prerequisite_steps": RelationshipSpec(
                relationship=RelationshipName.REQUIRES_STEP,
                direction="outgoing",
            ),
            "prerequisite_knowledge": RelationshipSpec(
                relationship=RelationshipName.REQUIRES_KNOWLEDGE,
                direction="outgoing",
            ),
            "principles": RelationshipSpec(
                relationship=RelationshipName.GUIDED_BY_PRINCIPLE,
                direction="outgoing",
            ),
            "choices": RelationshipSpec(
                relationship=RelationshipName.INFORMS_CHOICE,
                direction="outgoing",
            ),
            "practice_habits": RelationshipSpec(
                relationship=RelationshipName.BUILDS_HABIT,
                direction="outgoing",
            ),
            "practice_tasks": RelationshipSpec(
                relationship=RelationshipName.ASSIGNS_TASK,
                direction="outgoing",
            ),
            "practice_events": RelationshipSpec(
                relationship=RelationshipName.SCHEDULES_EVENT,
                direction="outgoing",
            ),
        },
        incoming_relationships={
            "in_paths": RelationshipSpec(
                relationship=RelationshipName.HAS_STEP,
                direction="incoming",
            ),
        },
    )


def _create_ku_config() -> RelationshipConfig:
    """
    Create KU (Knowledge Unit) config.

    Key features:
    - Knowledge graph relationships (enables, requires)
    - MOC organizational relationships (organizes) - A KU can organize other KUs
    - Semantic relationship support

    MOC Architecture (January 2026):
    - MOC is NOT a separate entity - it IS a KU that organizes other KUs
    - A KU "is" a MOC when it has outgoing ORGANIZES relationships
    - ORGANIZES relationship has {order: int} for sequencing within MOC
    """
    dto_class, model_class = _get_ku_classes()

    return RelationshipConfig(
        domain=Domain.KNOWLEDGE,
        entity_label="Ku",
        dto_class=dto_class,
        model_class=model_class,
        backend_get_method="get",
        use_semantic_helper=True,  # KU uses semantic relationships
        ownership_relationship=None,  # Shared content
        outgoing_relationships={
            "enables": RelationshipSpec(
                relationship=RelationshipName.ENABLES_KNOWLEDGE,
                direction="outgoing",
            ),
            "requires": RelationshipSpec(
                relationship=RelationshipName.REQUIRES_KNOWLEDGE,
                direction="outgoing",
            ),
            # MOC organizational relationship - KU organizing other KUs
            "organizes": RelationshipSpec(
                relationship=RelationshipName.ORGANIZES,
                direction="outgoing",
                order_by_property="order",
                order_direction="ASC",
                include_edge_properties=("order",),
            ),
        },
        incoming_relationships={
            "in_steps": RelationshipSpec(
                relationship=RelationshipName.CONTAINS_KNOWLEDGE,
                direction="incoming",
            ),
            "enabled_by": RelationshipSpec(
                relationship=RelationshipName.ENABLES_KNOWLEDGE,
                direction="incoming",
            ),
            "required_by": RelationshipSpec(
                relationship=RelationshipName.REQUIRES_KNOWLEDGE,
                direction="incoming",
            ),
            # MOC organizational relationship - KU organized by another KU
            "organized_by": RelationshipSpec(
                relationship=RelationshipName.ORGANIZES,
                direction="incoming",
            ),
        },
    )


# NOTE: _create_moc_config and _create_moc_section_config removed (January 2026)
# MOC is now KU-based - use KU config with ORGANIZES relationship instead


# Create curriculum configs lazily to avoid import cycles
_LP_CONFIG: RelationshipConfig | None = None
_LS_CONFIG: RelationshipConfig | None = None
_KU_CONFIG: RelationshipConfig | None = None
# NOTE: _MOC_CONFIG and _MOC_SECTION_CONFIG removed (January 2026) - MOC is KU-based


def get_lp_config() -> RelationshipConfig:
    """Get LP config (lazy initialization)."""
    global _LP_CONFIG
    if _LP_CONFIG is None:
        _LP_CONFIG = _create_lp_config()
    return _LP_CONFIG


def get_ls_config() -> RelationshipConfig:
    """Get LS config (lazy initialization)."""
    global _LS_CONFIG
    if _LS_CONFIG is None:
        _LS_CONFIG = _create_ls_config()
    return _LS_CONFIG


def get_ku_config() -> RelationshipConfig:
    """Get KU config (lazy initialization)."""
    global _KU_CONFIG
    if _KU_CONFIG is None:
        _KU_CONFIG = _create_ku_config()
    return _KU_CONFIG


# NOTE: get_moc_config and get_moc_section_config removed (January 2026) - MOC is KU-based


# Public exports - initialized lazily on first access
# Usage: from core.services.relationships.domain_configs import get_lp_config
#        lp_config = get_lp_config()
#
# Or for direct usage after module fully loads:
# from core.services.relationships.domain_configs import LP_CONFIG


class _LazyConfig:
    """Lazy config wrapper to defer initialization until first access."""

    _config: RelationshipConfig | None
    _getter: Callable[[], RelationshipConfig]

    def __init__(self, getter: Callable[[], RelationshipConfig]) -> None:
        self._getter = getter
        self._config = None

    def __call__(self) -> RelationshipConfig:
        if self._config is None:
            self._config = self._getter()
        assert self._config is not None  # Guaranteed by lazy init above
        return self._config


# These can be called as functions: LP_CONFIG() or used via getters
LP_CONFIG = _LazyConfig(get_lp_config)
LS_CONFIG = _LazyConfig(get_ls_config)
KU_CONFIG = _LazyConfig(get_ku_config)
# NOTE: MOC_CONFIG and MOC_SECTION_CONFIG removed (January 2026) - MOC is KU-based


# Registry for curriculum domains
CURRICULUM_DOMAIN_CONFIGS: dict[Domain, RelationshipConfig] = {}


def _init_curriculum_configs() -> None:
    """Initialize curriculum configs into registry (call after imports resolve)."""
    global CURRICULUM_DOMAIN_CONFIGS
    CURRICULUM_DOMAIN_CONFIGS = {
        Domain.LEARNING: get_lp_config(),  # LP uses LEARNING domain
        Domain.KNOWLEDGE: get_ku_config(),  # KU uses KNOWLEDGE domain
        # Note: LS shares domain with LP. Access via get_ls_config()
        # MOC is now KU-based (January 2026) - use KU config with ORGANIZES relationship
    }


# Combined registry for all domains
def get_all_domain_configs() -> dict[Domain, RelationshipConfig]:
    """Get all domain configs (Activity + Curriculum)."""
    if not CURRICULUM_DOMAIN_CONFIGS:
        _init_curriculum_configs()
    return {**ACTIVITY_DOMAIN_CONFIGS, **CURRICULUM_DOMAIN_CONFIGS}
