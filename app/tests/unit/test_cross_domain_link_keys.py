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
    GOALS_CONFIG,
    HABITS_CONFIG,
    PRINCIPLES_CONFIG,
    PS_CONFIG,
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
    ("link_goal_to_knowledge", GOALS_CONFIG, "knowledge"),
    ("link_goal_to_principle", GOALS_CONFIG, "principles"),
    ("link_goal_to_habit", GOALS_CONFIG, "supporting_habits"),
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


# (call site, domain config, method_key passed to get_related_uids / delete_relationship).
# The READ side of the same contract: event handlers, dual-track signal calculators, and
# intelligence services call `service.get_related_uids("<key>", uid)` (2-arg — the service
# resolves the key against the registry). Passing a raw RelationshipName.value (e.g.
# "ALIGNED_WITH_PRINCIPLE") or the 3-arg backend signature silently returns nothing, so
# these reads need the same coverage guard as the writes above.
HANDLER_READ_KEYS: list[tuple[str, DomainRelationshipConfig, str]] = [
    ("choices behavioral signal: principle alignment", CHOICES_CONFIG, "principles"),
    ("choice event handler: principles", CHOICES_CONFIG, "principles"),
    ("event handler: goal alignment", EVENTS_CONFIG, "goals"),
    ("events_service: celebrated_goals", EVENTS_CONFIG, "celebrated_goals"),
    ("habit event handler: knowledge reinforcement", HABITS_CONFIG, "knowledge"),
    ("habit enrichment: prerequisite_habits", HABITS_CONFIG, "prerequisite_habits"),
    ("habit enrichment: principles", HABITS_CONFIG, "principles"),
    ("habit enrichment: supported_goals", HABITS_CONFIG, "supported_goals"),
    ("task handler: principle alignment", TASKS_CONFIG, "principles"),
    ("tasks_service: knowledge", TASKS_CONFIG, "knowledge"),
    ("viz aggregation: prerequisite_tasks", TASKS_CONFIG, "prerequisite_tasks"),
    ("goal handler: principle alignment", GOALS_CONFIG, "principles"),
    ("goal relationship: supporting_habits", GOALS_CONFIG, "supporting_habits"),
    ("principle handler/alignment: guided_goals", PRINCIPLES_CONFIG, "guided_goals"),
    ("principle handler/alignment: inspired_habits", PRINCIPLES_CONFIG, "inspired_habits"),
    ("ps_service: in_paths", PS_CONFIG, "in_paths"),
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
    ("call_site", "config", "key"),
    HANDLER_READ_KEYS,
    ids=[row[0] for row in HANDLER_READ_KEYS],
)
def test_handler_read_key_resolves_in_config(
    call_site: str, config: DomainRelationshipConfig, key: str
) -> None:
    """Each method_key a handler/intelligence read passes to get_related_uids resolves.

    Guards the ``RelationshipName.value``-as-method-key class of bug (e.g. passing
    "ALIGNED_WITH_PRINCIPLE" where "principles" is expected) that silently returned
    nothing in event handlers and dual-track signal calculators.
    """
    spec = config.get_relationship_by_method(key)
    assert spec is not None, (
        f"{call_site} reads get_related_uids({key!r}, ...) but "
        f"{config.entity_label}'s config has no '{key}' method_key — the read would "
        f"silently return nothing. Available: {sorted(config.get_all_relationship_methods())}"
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
