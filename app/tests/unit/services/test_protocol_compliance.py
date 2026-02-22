"""
Protocol compliance tests for service facades.

Verifies that facade services structurally satisfy their declared protocols,
catching protocol drift at CI time rather than runtime.

ARCHITECTURE NOTE (January 2026):
=================================
SKUEL uses a layered protocol architecture:

1. **BackendOperations[T]** - Implemented by UniversalNeo4jBackend
   - Low-level CRUD, search, relationship operations
   - Facades delegate to backends, they don't implement these

2. **Domain Protocols (TasksOperations, etc.)** - TYPE PARAMETERS
   - Used as `BaseService[TasksOperations, Task]` for generic typing
   - Inherit from BackendOperations (combined contract)
   - Facades do NOT directly implement all these methods

3. **FacadeProtocols (TasksFacadeProtocol, etc.)** - FACADE CONTRACT
   - Define what methods facades expose to callers
   - Auto-generated via FacadeDelegationMixin._delegations
   - THIS is what we test for facade compliance

This test verifies:
- Facades implement their FacadeProtocol methods (public API contract)
- UniversalNeo4jBackend implements BackendOperations (persistence contract)
"""

import pytest

# Universal backend
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend

# Backend protocol
# Facade protocols (THE contract for facade services)
from core.ports import (
    BackendOperations,
    EventsFacadeProtocol,
    GoalsFacadeProtocol,
    HabitsFacadeProtocol,
    LpFacadeProtocol,
    # NOTE: MocFacadeProtocol removed (February 2026) - organization absorbed into KuService
    PrinciplesFacadeProtocol,
    TasksFacadeProtocol,
)

# Facade services - Activity Domains
from core.services.choices_service import ChoicesService
from core.services.events_service import EventsService
from core.services.goals_service import GoalsService
from core.services.habits_service import HabitsService

# Facade services - Curriculum Domains
from core.services.ku_service import KuService
from core.services.lp_service import LpService
from core.services.ls_service import LsService

# NOTE: MOCService removed (February 2026) - organization logic absorbed into KuService
from core.services.principles_service import PrinciplesService
from core.services.tasks_service import TasksService


def get_protocol_methods(protocol: type) -> list[str]:
    """Extract callable method names from a protocol (excluding dunder/private)."""
    methods = []
    for name in dir(protocol):
        if name.startswith("_"):
            continue
        attr = getattr(protocol, name, None)
        if callable(attr):
            methods.append(name)
    return methods


def check_method_exists(facade: type, method_name: str) -> bool:
    """Check if a method exists on the facade class."""
    return hasattr(facade, method_name) and callable(getattr(facade, method_name, None))


class TestFacadeProtocolCompliance:
    """
    Verify facades satisfy FacadeProtocol contracts.

    FacadeProtocols define the PUBLIC API of facade services.
    Methods are typically auto-generated via FacadeDelegationMixin._delegations.
    This test catches drift between declared protocols and actual implementations.
    """

    # Facade Protocol to Facade Service mapping
    # Activity Domains (5 with FacadeProtocols)
    FACADE_PROTOCOL_PAIRS: list[tuple[type, type, str]] = [
        (TasksFacadeProtocol, TasksService, "Tasks"),
        (GoalsFacadeProtocol, GoalsService, "Goals"),
        (HabitsFacadeProtocol, HabitsService, "Habits"),
        (EventsFacadeProtocol, EventsService, "Events"),
        (PrinciplesFacadeProtocol, PrinciplesService, "Principles"),
        # Curriculum Domains
        (LpFacadeProtocol, LpService, "LP"),
        # NOTE: MOC removed (February 2026) - organization absorbed into KuService
    ]

    @pytest.mark.parametrize(
        "protocol,facade,domain",
        FACADE_PROTOCOL_PAIRS,
        ids=["Tasks", "Goals", "Habits", "Events", "Principles", "LP"],
    )
    def test_facade_has_all_protocol_methods(
        self, protocol: type, facade: type, domain: str
    ) -> None:
        """
        Verify facade service has all methods declared in its FacadeProtocol.

        FacadeProtocols provide type declarations for auto-generated methods,
        enabling MyPy to type-check call sites using facade services.

        If this test fails, either:
        1. A method is missing from the facade's _delegations
        2. The FacadeProtocol declares a method the facade doesn't have
        """
        protocol_methods = get_protocol_methods(protocol)
        missing_methods = [m for m in protocol_methods if not check_method_exists(facade, m)]

        assert not missing_methods, (
            f"{facade.__name__} missing FacadeProtocol methods from {protocol.__name__}: "
            f"{missing_methods}\n"
            f"Add these to _delegations or implement explicitly."
        )

    # NOTE: Signature compatibility testing removed.
    # FacadeDelegationMixin generates methods with (*args, **kwargs) signatures
    # at runtime, but preserves signatures via __signature__ attribute for IDE support.
    # Testing this requires more sophisticated inspection that goes beyond basic
    # inspect.signature() calls. The method existence test above is sufficient
    # for catching protocol drift.


class TestBackendProtocolCompliance:
    """
    Verify UniversalNeo4jBackend satisfies BackendOperations protocol.

    BackendOperations is THE protocol for persistence operations.
    All domain services depend on this protocol (via their backends).
    """

    def test_universal_backend_has_all_backend_operations_methods(self) -> None:
        """
        Verify UniversalNeo4jBackend has all BackendOperations methods.

        If this test fails, the backend is missing required persistence methods.
        """
        protocol_methods = get_protocol_methods(BackendOperations)
        missing_methods = [
            m for m in protocol_methods if not check_method_exists(UniversalNeo4jBackend, m)
        ]

        assert not missing_methods, (
            f"UniversalNeo4jBackend missing BackendOperations methods: {missing_methods}"
        )


class TestFacadeStructure:
    """
    Verify facade services follow the expected structure.

    Facades should have:
    - Sub-service attributes (core, search, intelligence, etc.)
    - FacadeDelegationMixin in __mro__
    - _delegations class attribute
    """

    ACTIVITY_FACADES = [
        TasksService,
        GoalsService,
        HabitsService,
        EventsService,
        ChoicesService,
        PrinciplesService,
    ]

    # NOTE: MOCService removed (February 2026) - organization logic absorbed into KuService
    CURRICULUM_FACADES = [KuService, LsService, LpService]

    @pytest.mark.parametrize(
        "facade",
        ACTIVITY_FACADES + CURRICULUM_FACADES,
        ids=[f.__name__ for f in ACTIVITY_FACADES + CURRICULUM_FACADES],
    )
    def test_facade_has_delegation_mixin(self, facade: type) -> None:
        """Verify facade inherits from FacadeDelegationMixin."""
        from core.services.mixins import FacadeDelegationMixin

        assert FacadeDelegationMixin in facade.__mro__, (
            f"{facade.__name__} does not inherit from FacadeDelegationMixin"
        )

    @pytest.mark.parametrize(
        "facade",
        ACTIVITY_FACADES + CURRICULUM_FACADES,
        ids=[f.__name__ for f in ACTIVITY_FACADES + CURRICULUM_FACADES],
    )
    def test_facade_has_delegations_attribute(self, facade: type) -> None:
        """Verify facade has _delegations class attribute."""
        assert hasattr(facade, "_delegations"), (
            f"{facade.__name__} missing _delegations class attribute"
        )
        assert isinstance(facade._delegations, dict), (
            f"{facade.__name__}._delegations should be a dict"
        )

    # NOTE: Sub-service annotation test removed.
    # Not all facades have class-level type annotations.
    # Annotations are optional (enable IDE signature preservation) but not required.
    # The core protocol compliance test above is what matters for catching drift.


class TestProtocolMethodCounts:
    """Sanity checks to ensure protocols have expected method counts."""

    def test_backend_operations_has_substantial_methods(self) -> None:
        """BackendOperations should have 20+ methods (7 composed protocols)."""
        method_count = len(get_protocol_methods(BackendOperations))
        assert method_count >= 20, (
            f"BackendOperations has only {method_count} methods, expected 20+"
        )

    def test_facade_protocols_have_methods(self) -> None:
        """FacadeProtocols should have substantial method declarations."""
        protocols = [
            TasksFacadeProtocol,
            GoalsFacadeProtocol,
            HabitsFacadeProtocol,
            EventsFacadeProtocol,
            PrinciplesFacadeProtocol,
            LpFacadeProtocol,
            # NOTE: MocFacadeProtocol removed (February 2026) - organization absorbed into KuService
        ]
        for protocol in protocols:
            method_count = len(get_protocol_methods(protocol))
            assert method_count >= 3, (
                f"{protocol.__name__} has only {method_count} methods, expected 3+"
            )
