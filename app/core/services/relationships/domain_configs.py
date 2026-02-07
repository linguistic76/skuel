"""
Domain Configurations - RelationshipConfig Definitions for Searchable Domains
=============================================================================

**February 2026 Unified Architecture:**

ALL domains (Activity + Curriculum) use generated configs from RelationshipRegistry.
Finance is standalone (no relationship configuration).

**Activity Domains (6):** Generated via generate_relationship_config(Domain.*)
- Tasks, Goals, Habits, Events, Choices, Principles

**Curriculum Domains (4):** Generated via generate_relationship_config_by_label()
- LP (Learning Path), LS (Learning Step), KU (Knowledge Unit), MOC (KU-based)

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

Version: 4.0.0
Date: 2026-02-07
"""

from core.models.shared_enums import Domain

# =============================================================================
# CONFIGURATION REGISTRY - Generated from RelationshipRegistry
# =============================================================================
from core.models.relationship_registry import (
    generate_relationship_config,
    generate_relationship_config_by_label,
)
from core.services.relationships.relationship_config import RelationshipConfig

# =============================================================================
# ACTIVITY DOMAIN CONFIGS (6 domains - User-owned entities)
# =============================================================================
# All configs are GENERATED from RelationshipRegistry (ADR-026).
# Note: Finance is standalone bookkeeping (not in unified architecture)

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

ACTIVITY_DOMAIN_CONFIGS: dict[Domain, RelationshipConfig] = {
    Domain.TASKS: _GENERATED_TASK_CONFIG,
    Domain.GOALS: _GENERATED_GOAL_CONFIG,
    Domain.HABITS: _GENERATED_HABIT_CONFIG,
    Domain.EVENTS: _GENERATED_EVENT_CONFIG,
    Domain.CHOICES: _GENERATED_CHOICE_CONFIG,
    Domain.PRINCIPLES: _GENERATED_PRINCIPLE_CONFIG,
}

# Re-export with standard names
TASK_CONFIG = _GENERATED_TASK_CONFIG
GOAL_CONFIG = _GENERATED_GOAL_CONFIG
HABIT_CONFIG = _GENERATED_HABIT_CONFIG
EVENT_CONFIG = _GENERATED_EVENT_CONFIG
CHOICE_CONFIG = _GENERATED_CHOICE_CONFIG
PRINCIPLE_CONFIG = _GENERATED_PRINCIPLE_CONFIG

# =============================================================================
# CURRICULUM DOMAIN CONFIGS (4 configs - Shared content)
# =============================================================================
# Generated from RelationshipRegistry via label-based lookup.
# Supports ordering (HAS_STEP with sequence) and edge metadata.

_GENERATED_KU_CONFIG = generate_relationship_config_by_label("Ku")
_GENERATED_LS_CONFIG = generate_relationship_config_by_label("Ls")
_GENERATED_LP_CONFIG = generate_relationship_config_by_label("Lp")

assert _GENERATED_KU_CONFIG is not None, "KU must be in registry"
assert _GENERATED_LS_CONFIG is not None, "LS must be in registry"
assert _GENERATED_LP_CONFIG is not None, "LP must be in registry"

KU_CONFIG = _GENERATED_KU_CONFIG
LS_CONFIG = _GENERATED_LS_CONFIG
LP_CONFIG = _GENERATED_LP_CONFIG


def get_lp_config() -> RelationshipConfig:
    """Get LP (Learning Path) relationship config."""
    return LP_CONFIG


def get_ls_config() -> RelationshipConfig:
    """Get LS (Learning Step) relationship config."""
    return LS_CONFIG


def get_ku_config() -> RelationshipConfig:
    """Get KU (Knowledge Unit) relationship config."""
    return KU_CONFIG


def get_moc_config() -> RelationshipConfig:
    """Get MOC relationship config (MOC is KU-based)."""
    return KU_CONFIG


# =============================================================================
# COMBINED REGISTRIES
# =============================================================================

CURRICULUM_DOMAIN_CONFIGS: dict[Domain, RelationshipConfig] = {
    Domain.LEARNING: LP_CONFIG,  # LP uses LEARNING domain
    Domain.KNOWLEDGE: KU_CONFIG,  # KU uses KNOWLEDGE domain
    # Note: LS shares domain with LP. Access via get_ls_config()
    # MOC is KU-based - use KU config with ORGANIZES relationship
}


def get_config_for_domain(domain: Domain) -> RelationshipConfig | None:
    """
    Get RelationshipConfig for a domain.

    Args:
        domain: Domain enum value

    Returns:
        RelationshipConfig or None if domain not configured
    """
    if domain in ACTIVITY_DOMAIN_CONFIGS:
        return ACTIVITY_DOMAIN_CONFIGS[domain]
    return CURRICULUM_DOMAIN_CONFIGS.get(domain)


def get_all_domain_configs() -> dict[Domain, RelationshipConfig]:
    """Get all domain configs (Activity + Curriculum)."""
    return {**ACTIVITY_DOMAIN_CONFIGS, **CURRICULUM_DOMAIN_CONFIGS}
