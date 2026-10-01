"""An orchestration factory whose routes take a uid registers only with its verifier.

Four of the orchestration factories register routes that take a goal or habit
uid; each is handed the facade that owner-verifies that uid. Handed ``None``,
the factory raises and registers no route — a uid-taking route with no verifier
behind it would read for any caller.

The HTTP contract of the registered routes is pinned over a real graph in
``tests/integration/routes/test_orchestration_route_ownership.py``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from adapters.inbound.orchestration_routes import (
    create_goal_task_routes,
    create_goals_intelligence_routes,
    create_habit_event_routes,
    create_principle_alignment_routes,
)

if TYPE_CHECKING:
    from core.ports.service_protocols import OwnershipVerifier

type Verifiers = dict[str, OwnershipVerifier | None]
type Factory = Callable[..., None]

# (factory, the verifiers it is handed — one of them missing)
_REFUSED: tuple[tuple[Factory, Verifiers], ...] = (
    (create_goal_task_routes, {"goals": None}),
    (create_habit_event_routes, {"habits": None}),
    (create_goals_intelligence_routes, {"goals": None}),
    (create_principle_alignment_routes, {"goals": None, "habits": MagicMock()}),
    (create_principle_alignment_routes, {"goals": MagicMock(), "habits": None}),
)

# (factory, its verifiers, the routes it registers)
_REGISTERED: tuple[tuple[Factory, Verifiers, int], ...] = (
    (create_goal_task_routes, {"goals": MagicMock()}, 2),
    (create_habit_event_routes, {"habits": MagicMock()}, 2),
    (create_goals_intelligence_routes, {"goals": MagicMock()}, 3),
    (create_principle_alignment_routes, {"goals": MagicMock(), "habits": MagicMock()}, 5),
)


def _missing(verifiers: Verifiers) -> str:
    return "-".join(name for name, verifier in verifiers.items() if verifier is None)


@pytest.mark.parametrize(
    ("factory", "verifiers"),
    _REFUSED,
    ids=[f"{factory.__name__}-without-{_missing(verifiers)}" for factory, verifiers in _REFUSED],
)
def test_factory_refuses_to_register_without_its_verifier(
    factory: Factory, verifiers: Verifiers
) -> None:
    rt = MagicMock()

    with pytest.raises(ValueError, match="without the service that verifies its owner"):
        factory(MagicMock(), rt, MagicMock(), **verifiers)

    rt.assert_not_called()


@pytest.mark.parametrize(
    ("factory", "verifiers", "routes"),
    _REGISTERED,
    ids=[factory.__name__ for factory, _, _ in _REGISTERED],
)
def test_factory_registers_its_routes_with_its_verifier(
    factory: Factory, verifiers: Verifiers, routes: int
) -> None:
    rt = MagicMock()
    factory(MagicMock(), rt, MagicMock(), **verifiers)
    assert rt.call_count == routes
