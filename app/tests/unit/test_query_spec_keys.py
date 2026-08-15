"""Registry-coverage guard for the domain ``*_QUERY_SPECS`` read path.

Each activity domain declares a ``*_QUERY_SPECS`` list of
``(dataclass_field, relationship_method_key)`` pairs. ``fetch_relationships_parallel``
hands each key to ``UnifiedRelationshipService.get_related_uids``, which fails closed
with ``Errors.validation("Unknown relationship key ...")`` on a key that isn't in the
domain's config — and then ``generic_fetcher`` maps *any* failed Result to ``[]``
(``core/utils/generic_fetcher.py``). A key that doesn't resolve therefore produces an
empty list for every entity, corpus-wide, with no error surfaced anywhere.

That is how ``("required_knowledge_uids", "required_knowledge")`` on Choices and
``("milestone_uids", "milestones")`` / ``"aligned_learning_paths"`` on Goals all sat
undetected: the field is *typed correctly* and *always empty*, so scoring silently
reads a 0 that looks like real data.

This is the read-side twin of ``test_cross_domain_link_keys.py`` (which guards the
*write* keys facades pass to ``create_relationship``). Mocked unit tests cannot catch
this class of bug — an ``AsyncMock`` accepts any key — so the guard lives at the
registry layer.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from core.models.relationship_registry import (
    CHOICES_CONFIG,
    EVENTS_CONFIG,
    GOALS_CONFIG,
    HABITS_CONFIG,
    PRINCIPLES_CONFIG,
    TASKS_CONFIG,
    DomainRelationshipConfig,
)
from core.services.choices.choice_relationships import CHOICE_QUERY_SPECS
from core.services.events.event_relationships import EVENT_QUERY_SPECS
from core.services.goals.goal_relationships import GOAL_QUERY_SPECS
from core.services.habits.habit_relationships import HABIT_QUERY_SPECS
from core.services.principles.principle_relationships import PRINCIPLE_QUERY_SPECS
from core.services.tasks.task_relationships import TASK_QUERY_SPECS

# (constant name, specs, owning domain config). The constant name is carried so the
# completeness test below can prove this table covers every *_QUERY_SPECS in the tree.
DOMAIN_QUERY_SPECS: list[tuple[str, list[tuple[str, str]], DomainRelationshipConfig]] = [
    ("CHOICE_QUERY_SPECS", CHOICE_QUERY_SPECS, CHOICES_CONFIG),
    ("EVENT_QUERY_SPECS", EVENT_QUERY_SPECS, EVENTS_CONFIG),
    ("GOAL_QUERY_SPECS", GOAL_QUERY_SPECS, GOALS_CONFIG),
    ("HABIT_QUERY_SPECS", HABIT_QUERY_SPECS, HABITS_CONFIG),
    ("PRINCIPLE_QUERY_SPECS", PRINCIPLE_QUERY_SPECS, PRINCIPLES_CONFIG),
    ("TASK_QUERY_SPECS", TASK_QUERY_SPECS, TASKS_CONFIG),
]

_SPEC_ROWS = [
    pytest.param(const, field_name, method_key, config, id=f"{const}-{method_key}")
    for const, specs, config in DOMAIN_QUERY_SPECS
    for field_name, method_key in specs
]


@pytest.mark.parametrize(("const", "field_name", "method_key", "config"), _SPEC_ROWS)
def test_query_spec_key_resolves_in_domain_config(
    const: str,
    field_name: str,
    method_key: str,
    config: DomainRelationshipConfig,
) -> None:
    """Every ``*_QUERY_SPECS`` method key must resolve to a real relationship."""
    assert config.get_relationship_by_method(method_key) is not None, (
        f"{const} maps field {field_name!r} to method key {method_key!r}, which is not "
        f"defined in {config.domain} config. get_related_uids would fail closed and "
        f"generic_fetcher would swallow it into [], making {field_name} empty for every "
        f"entity. Valid keys: {sorted(config.get_all_relationship_methods())}"
    )


def test_unknown_method_key_is_actually_rejected() -> None:
    """Positive control: the assertion above can fail.

    Without this, a ``get_relationship_by_method`` that returned a truthy value for
    everything would make the whole guard vacuous.
    """
    assert CHOICES_CONFIG.get_relationship_by_method("knowledge") is not None
    assert CHOICES_CONFIG.get_relationship_by_method("definitely_not_a_method") is None


def test_every_query_specs_constant_in_tree_is_covered() -> None:
    """No ``*_QUERY_SPECS`` may exist in core/services/ without a row above.

    The parametrized test can only check specs this module imports. A new domain that
    adds its own specs would otherwise inherit the exact silent-empty bug this guard
    exists to prevent, while the suite stayed green.
    """
    services_root = Path(__file__).resolve().parents[2] / "core" / "services"
    assert services_root.is_dir(), f"expected services tree at {services_root}"

    discovered: set[str] = set()
    for path in services_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:  # module level only — specs are module constants
            targets = (
                [node.target] if isinstance(node, ast.AnnAssign) else getattr(node, "targets", [])
            )
            discovered.update(
                t.id for t in targets if isinstance(t, ast.Name) and t.id.endswith("_QUERY_SPECS")
            )

    covered = {const for const, _, _ in DOMAIN_QUERY_SPECS}
    assert discovered, "discovery found no *_QUERY_SPECS at all — the scan is broken"
    assert discovered == covered, (
        f"*_QUERY_SPECS constants not guarded: {sorted(discovered - covered)}; "
        f"guarded but no longer present: {sorted(covered - discovered)}. "
        f"Add the new domain's specs to DOMAIN_QUERY_SPECS."
    )
