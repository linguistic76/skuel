"""Structural guard for the cross-domain-context analytics path.

``BaseAnalyticsService._analyze_entity_with_context`` (used by the goals/habits/principles
intelligence dashboards) used to dispatch on a per-domain method *name*:

    context_fn = getattr(self.relationships, "get_goal_cross_domain_context", None)

The injected ``self.relationships`` is a :class:`UnifiedRelationshipService`, which only
exposes the generic, config-driven ``get_cross_domain_context`` — so the ``getattr``
resolved to ``None`` and the cross-domain context was silently never fetched. The template
now calls the generic method directly; this guard's first half locks that in (the per-domain
names must NOT resolve, and the generic one MUST — there is no ``__getattr__`` rescue).

Fixing the dispatch then exposed a second, latent bug: the typed ``*CrossContext.from_dict``
adapters read generic keys (``"habits"``, ``"tasks"``, ``"knowledge"`` …) that the
config-driven response never emits — it emits one bucket per config ``context_field_name``
(``contributing_habits``, ``required_knowledge`` …). Only ``sub_goals`` happened to match,
so every dashboard metric came back zero. This guard's second half makes the from_dict→config
key contract an enforced invariant: every bucket a from_dict reads MUST be a real
``context_field_name`` in that domain's config, or the typed context silently empties again.

Mocked unit tests can't catch either class (an ``AsyncMock`` resolves any attribute; a stale
key just yields an empty list), so the guards live at the class/registry layer.
"""

from __future__ import annotations

import pytest

from core.models.relationship_registry import (
    CHOICES_CONFIG,
    EVENTS_CONFIG,
    GOAPS_CONFIG,
    HABITS_CONFIG,
    KU_CONFIG,
    PRINCIPLES_CONFIG,
    TASKS_CONFIG,
    DomainRelationshipConfig,
)
from core.services.relationships.unified_relationship_service import UnifiedRelationshipService

# ---------------------------------------------------------------------------
# Half 1 — dispatch contract: the template calls the GENERIC method, by name,
# directly on UnifiedRelationshipService. The deleted per-domain names must not
# come back (and there is no __getattr__ to silently resolve them).
# ---------------------------------------------------------------------------

PER_DOMAIN_DISPATCH_NAMES = [
    "get_goal_cross_domain_context",
    "get_habit_cross_domain_context",
    "get_principle_cross_domain_context",
]

_MISSING = object()  # sentinel — getattr-based attribute probe (SKUEL011: no hasattr)


def _resolves(name: str) -> bool:
    """True iff ``name`` resolves on UnifiedRelationshipService.

    There is no ``__getattr__`` (asserted below), so a class-level ``getattr`` against a
    unique sentinel is an exact, sound presence check — no ``hasattr`` needed.
    """
    return getattr(UnifiedRelationshipService, name, _MISSING) is not _MISSING


def test_unified_relationship_service_exposes_generic_context_method() -> None:
    """The single method the analytics template now calls must exist."""
    assert _resolves("get_cross_domain_context")


def test_unified_relationship_service_has_no_getattr_rescue() -> None:
    """No __getattr__ — a missing method is a real AttributeError, not a silent None."""
    assert "__getattr__" not in dir(UnifiedRelationshipService)


@pytest.mark.parametrize("name", PER_DOMAIN_DISPATCH_NAMES)
def test_per_domain_dispatch_names_do_not_resolve(name: str) -> None:
    """The deleted getattr-by-name targets must stay gone on the injected type.

    If one reappears here, someone re-introduced a per-domain wrapper and the
    getattr-to-None silent-degradation trap is back.
    """
    assert not _resolves(name), (
        f"{name!r} resolves on UnifiedRelationshipService again — the analytics "
        f"template must call the generic get_cross_domain_context, not dispatch by name."
    )


# ---------------------------------------------------------------------------
# Half 2 — from_dict → config key contract. Every bucket a *CrossContext.from_dict
# reads must be a real context_field_name the config emits, or the typed context
# silently empties (the bug this campaign fixed). Mirror from_dict here; adding a
# new key to a from_dict means adding its row, or this test won't protect it.
# ---------------------------------------------------------------------------

# (description, domain config, context_field_name read by from_dict).
FROM_DICT_KEYS: list[tuple[str, DomainRelationshipConfig, str]] = [
    # GoalCrossContext.from_dict
    ("goal.supporting_task_uids", GOAPS_CONFIG, "contributing_tasks"),
    ("goal.supporting_habit_uids", GOAPS_CONFIG, "contributing_habits"),
    ("goal.supporting_habit_uids", GOAPS_CONFIG, "essential_habits"),
    ("goal.supporting_habit_uids", GOAPS_CONFIG, "critical_habits"),
    ("goal.supporting_habit_uids", GOAPS_CONFIG, "optional_habits"),
    ("goal.required_knowledge_uids", GOAPS_CONFIG, "required_knowledge"),
    ("goal.learning_path_uids", GOAPS_CONFIG, "aligned_paths"),
    ("goal.learning_path_uids", GOAPS_CONFIG, "required_paths"),
    ("goal.sub_goal_uids", GOAPS_CONFIG, "sub_goals"),
    ("goal.guiding_principle_uids", GOAPS_CONFIG, "aligned_principles"),
    ("goal.guiding_principle_uids", GOAPS_CONFIG, "guiding_principles_incoming"),
    # HabitCrossContext.from_dict
    ("habit.linked_goal_uids", HABITS_CONFIG, "supported_goals"),
    ("habit.knowledge_reinforcement_uids", HABITS_CONFIG, "reinforced_knowledge"),
    ("habit.aligned_principle_uids", HABITS_CONFIG, "embodied_principles"),
    ("habit.aligned_principle_uids", HABITS_CONFIG, "inspiring_principles"),
    ("habit.prerequisite_habit_uids", HABITS_CONFIG, "prerequisite_habits"),
    # PrincipleCrossContext.from_dict
    ("principle.guided_goal_uids", PRINCIPLES_CONFIG, "guided_goals"),
    ("principle.informed_choice_uids", PRINCIPLES_CONFIG, "guided_choices"),
    ("principle.grounding_knowledge_uids", PRINCIPLES_CONFIG, "grounding_knowledge"),
    ("principle.aligned_habit_uids", PRINCIPLES_CONFIG, "inspired_habits"),
    ("principle.aligned_habit_uids", PRINCIPLES_CONFIG, "embodying_habits"),
    # ChoiceCrossContext.from_dict — informing principles span both the outgoing
    # INFORMED_BY_PRINCIPLE and incoming GUIDES_CHOICE edges; goals come from the
    # single polarity-free AFFECTS_GOAL edge (no conflicting-goal bucket exists).
    ("choice.informing_principle_uids", CHOICES_CONFIG, "aligned_principles"),
    ("choice.informing_principle_uids", CHOICES_CONFIG, "guiding_principles"),
    ("choice.affected_goal_uids", CHOICES_CONFIG, "affected_goals"),
    ("choice.required_knowledge_uids", CHOICES_CONFIG, "informed_by_knowledge"),
    # EventCrossContext.from_dict — supporting goals span CONTRIBUTES_TO_GOAL and the
    # milestone CELEBRATES_GOAL; reinforcing habits span outgoing REINFORCES_HABIT and
    # incoming PRACTICED_AT_EVENT; practiced knowledge is APPLIES_KNOWLEDGE.
    ("event.supporting_goal_uids", EVENTS_CONFIG, "supported_goals"),
    ("event.supporting_goal_uids", EVENTS_CONFIG, "celebrated_goals"),
    ("event.reinforcing_habit_uids", EVENTS_CONFIG, "reinforced_habits"),
    ("event.reinforcing_habit_uids", EVENTS_CONFIG, "practiced_habits"),
    ("event.practicing_knowledge_uids", EVENTS_CONFIG, "applied_knowledge"),
    # TaskCrossContext.from_dict — prerequisite tasks are DEPENDS_ON; dependent tasks are
    # incoming BLOCKED_BY; contributing goals span CONTRIBUTES_TO_GOAL and the single
    # FULFILLS_GOAL; principles are ALIGNED_WITH_PRINCIPLE; knowledge spans
    # REQUIRES_KNOWLEDGE and APPLIES_KNOWLEDGE.
    ("task.prerequisite_task_uids", TASKS_CONFIG, "dependencies"),
    ("task.dependent_task_uids", TASKS_CONFIG, "dependents"),
    ("task.required_knowledge_uids", TASKS_CONFIG, "required_knowledge"),
    ("task.applied_knowledge_uids", TASKS_CONFIG, "applied_knowledge"),
    ("task.contributing_goal_uids", TASKS_CONFIG, "contributing_goals"),
    ("task.contributing_goal_uids", TASKS_CONFIG, "goal_context"),
    ("task.aligned_principle_uids", TASKS_CONFIG, "aligned_principles"),
    # KnowledgeCrossContext.from_dict — a Ku's only cross-domain reach is the PathSteps
    # composing (USES_KU) or training (TRAINS_KU) it; activity/goal/prerequisite fields
    # had no KU_CONFIG bucket and were dropped (see cross_domain_contexts.py).
    ("knowledge.path_step_uids", KU_CONFIG, "used_by_steps"),
    ("knowledge.path_step_uids", KU_CONFIG, "trained_by_steps"),
]


def _context_field_names(config: DomainRelationshipConfig) -> set[str]:
    """The buckets get_cross_domain_context() actually emits for a domain."""
    return {
        rel.context_field_name
        for rel in config.relationships
        if getattr(rel, "is_cross_domain_mapping", False)
    }


@pytest.mark.parametrize(
    ("description", "config", "key"),
    FROM_DICT_KEYS,
    ids=[f"{row[0]}<-{row[2]}" for row in FROM_DICT_KEYS],
)
def test_from_dict_key_is_emitted_by_config(
    description: str, config: DomainRelationshipConfig, key: str
) -> None:
    """Each context bucket a from_dict reads is a real config context_field_name."""
    emitted = _context_field_names(config)
    assert key in emitted, (
        f"{description} reads context_dict[{key!r}], but {config.domain.value}'s config "
        f"emits no such bucket — the typed context would silently empty. "
        f"Emitted buckets: {sorted(emitted)}"
    )
