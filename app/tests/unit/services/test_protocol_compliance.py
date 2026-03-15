"""
Protocol compliance tests for service facades.

Verifies that facade services structurally satisfy their declared protocols,
catching protocol drift at CI time rather than runtime.

ARCHITECTURE NOTE (February 2026):
===================================
SKUEL uses a layered protocol architecture:

1. **BackendOperations[T]** - Implemented by UniversalNeo4jBackend
   - Low-level CRUD, search, relationship operations
   - Facades delegate to backends, they don't implement these

2. **Domain Protocols (TasksOperations, etc.)** - TYPE PARAMETERS
   - Used as `BaseService[TasksOperations, Task]` for generic typing
   - Inherit from BackendOperations (combined contract)
   - Facades do NOT directly implement all these methods

3. **Explicit Delegation (February 2026)** - FACADE PATTERN
   - All facades expose their full API as explicit `async def` methods
   - Methods are fully visible to MyPy (no dynamic generation)
   - FacadeDelegationMixin and FacadeProtocols deleted February 2026

This test verifies:
- UniversalNeo4jBackend implements BackendOperations (persistence contract)
- All facade services use explicit delegation (no FacadeDelegationMixin)
- BackendOperations has sufficient methods (sanity check)
"""

import pytest

# Universal backend
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend

# Backend protocol
from core.ports import BackendOperations

# Facade services - Activity Domains
from core.services.choices_service import ChoicesService
from core.services.events_service import EventsService
from core.services.goals_service import GoalsService
from core.services.habits_service import HabitsService

# Facade services - Curriculum Domains
from core.services.lesson_service import LessonService
from core.services.lp_service import LpService
from core.services.ls_service import LsService

# NOTE: MOCService removed (February 2026) - organization logic absorbed into LessonService
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

    All facades use explicit delegation methods (static, fully MyPy-visible).
    Migration from FacadeDelegationMixin completed February 2026.
    """

    # All facades now use explicit delegation (static methods, fully MyPy-visible)
    # NOTE: Migration from FacadeDelegationMixin completed February 2026
    EXPLICIT_FACADES = [
        TasksService,
        GoalsService,
        HabitsService,
        EventsService,
        ChoicesService,
        PrinciplesService,
        LessonService,
        LsService,
        LpService,
    ]

    @pytest.mark.parametrize(
        "facade",
        EXPLICIT_FACADES,
        ids=[f.__name__ for f in EXPLICIT_FACADES],
    )
    def test_explicit_facade_has_no_delegations_attribute(self, facade: type) -> None:
        """Verify explicit facade does NOT have a _delegations class attribute."""
        assert not hasattr(facade, "_delegations"), (
            f"{facade.__name__} still has _delegations attribute — "
            f"migrate to explicit delegation methods"
        )

    @pytest.mark.parametrize(
        "facade",
        EXPLICIT_FACADES,
        ids=[f.__name__ for f in EXPLICIT_FACADES],
    )
    def test_explicit_facade_has_explicit_methods(self, facade: type) -> None:
        """Verify facade has callable methods beyond the base class minimum."""
        # Explicit facades should expose many methods (delegations + domain-specific)
        methods = [
            name
            for name in dir(facade)
            if not name.startswith("_") and callable(getattr(facade, name, None))
        ]
        assert len(methods) >= 5, (
            f"{facade.__name__} has only {len(methods)} public methods, "
            f"expected 5+ from explicit delegations"
        )


class TestProtocolMethodCounts:
    """Sanity checks to ensure protocols have expected method counts."""

    def test_backend_operations_has_substantial_methods(self) -> None:
        """BackendOperations should have 20+ methods (7 composed protocols)."""
        method_count = len(get_protocol_methods(BackendOperations))
        assert method_count >= 20, (
            f"BackendOperations has only {method_count} methods, expected 20+"
        )
