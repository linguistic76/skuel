"""Registry-coverage guard for cross-domain facade link methods.

The Activity/Curriculum facades wire entities into the semantic graph by calling
``relationships.create_relationship("<method_key>", ...)`` with an *explicit* key
(e.g. ``link_task_to_goal`` -> ``"contributes_to_goal"``). ``create_relationship``
fails closed on an unknown key, so a typo or a config rename would turn a link into
a silent ``Result.fail`` at runtime — exactly the latent fragility that the deleted
``link_to_goal``/``link_to_knowledge``/``link_to_principle`` candidate-list wrappers used
to hide.

This test makes that coverage an enforced, compile-time-ish invariant: every key a
facade hands to ``create_relationship`` MUST resolve in its domain's config. Add a new
facade link method -> add its (config, key) row here, or this test (correctly) won't
know to protect it.

Mocked unit tests can't catch this class of bug (an ``AsyncMock`` accepts any key), so
the guard lives at the registry layer instead.
"""

from __future__ import annotations

import pytest

from core.models.relationship_registry import (
    CHOICES_CONFIG,
    EVENTS_CONFIG,
    GOAPS_CONFIG,
    HABITS_CONFIG,
    PRINCIPLES_CONFIG,
    TASKS_CONFIG,
    DomainRelationshipConfig,
)
from core.services.principles._gravity_mixin import _GravityMixin

# (facade method, domain config, method_key passed to create_relationship).
# Mirrors the explicit keys in each domain's relationship mixin — keep in sync when
# adding/altering a facade link method.
FACADE_LINK_KEYS: list[tuple[str, DomainRelationshipConfig, str]] = [
    ("link_task_to_knowledge", TASKS_CONFIG, "knowledge"),
    ("link_task_to_goal", TASKS_CONFIG, "contributes_to_goal"),
    ("link_goal_to_knowledge", GOAPS_CONFIG, "knowledge"),
    ("link_goal_to_principle", GOAPS_CONFIG, "principles"),
    ("link_goal_to_habit", GOAPS_CONFIG, "supporting_habits"),
    ("link_habit_to_knowledge", HABITS_CONFIG, "knowledge"),
    ("link_habit_to_principle", HABITS_CONFIG, "principles"),
    ("link_event_to_goal", EVENTS_CONFIG, "goals"),
    ("link_event_to_habit", EVENTS_CONFIG, "habits"),
    ("link_event_to_knowledge", EVENTS_CONFIG, "knowledge"),
    ("link_choice_to_goal", CHOICES_CONFIG, "goals"),
    ("link_choice_to_habit", CHOICES_CONFIG, "impacted_habits"),
    ("link_choice_to_principle", CHOICES_CONFIG, "principles"),
    ("link_principle_to_knowledge", PRINCIPLES_CONFIG, "knowledge"),
]


@pytest.mark.parametrize(
    ("method_name", "config", "key"),
    FACADE_LINK_KEYS,
    ids=[row[0] for row in FACADE_LINK_KEYS],
)
def test_facade_link_key_resolves_in_config(
    method_name: str, config: DomainRelationshipConfig, key: str
) -> None:
    """Each explicit key a facade passes to create_relationship resolves in its config."""
    spec = config.get_relationship_by_method(key)
    assert spec is not None, (
        f"{method_name} writes create_relationship({key!r}, ...) but "
        f"{config.entity_label}'s config has no '{key}' method_key — the link would "
        f"silently fail. Available: {sorted(config.get_all_relationship_methods())}"
    )


@pytest.mark.parametrize(
    ("link_type", "key"),
    list(_GravityMixin._LINK_TYPE_MAP.items()),
    ids=list(_GravityMixin._LINK_TYPE_MAP),
)
def test_principle_link_type_map_keys_resolve(link_type: str, key: str) -> None:
    """Every link_type in create_principle_link/get_principle_links maps to a real key.

    Guards the ``grounding_knowledge`` -> ``knowledge`` class of bug: a link_type whose
    mapped config key doesn't exist makes that whole link type silently dead.
    """
    spec = PRINCIPLES_CONFIG.get_relationship_by_method(key)
    assert spec is not None, (
        f"principle link_type {link_type!r} maps to '{key}', which is not a method_key "
        f"in PRINCIPLES_CONFIG. Available: "
        f"{sorted(PRINCIPLES_CONFIG.get_all_relationship_methods())}"
    )
