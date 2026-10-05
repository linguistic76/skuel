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
from core.services.relationships._keyed_read import resolve_keyed_read
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
    """Every ``*_QUERY_SPECS`` method key must resolve to a keyed read.

    ``resolve_keyed_read`` is the lookup ``get_related_uids`` makes: it refuses a key
    the config does not declare, and a shared-neighbour definition, whose one-hop
    read would return the shared neighbours rather than the peers it names.
    """
    read = resolve_keyed_read(config, method_key)
    assert read.is_ok, (
        f"{const} maps field {field_name!r} to method key {method_key!r}, which "
        f"get_related_uids refuses ({read.expect_error().message}); generic_fetcher "
        f"would swallow it into [], making {field_name} empty for every entity. "
        f"Valid keys: {sorted(config.get_all_relationship_methods())}"
    )


def test_unknown_method_key_is_actually_rejected() -> None:
    """Positive controls: the assertion above can fail, both ways it refuses.

    Without these, a resolver that accepted everything would make the whole guard
    vacuous.
    """
    assert resolve_keyed_read(CHOICES_CONFIG, "knowledge").is_ok
    assert resolve_keyed_read(CHOICES_CONFIG, "definitely_not_a_method").is_error
    shared_neighbour = EVENTS_CONFIG.get_relationship_by_method("related_events")
    assert shared_neighbour is not None
    assert shared_neighbour.shared_neighbor_config is not None
    assert resolve_keyed_read(EVENTS_CONFIG, "related_events").is_error


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
