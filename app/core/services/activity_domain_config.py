"""
Activity Domain Configuration Registry
======================================

Centralizes configuration for 6 Activity Domain facades.

Each domain has:
- core_class: CoreService class for CRUD operations
- search_class: SearchService class for discovery
- intelligence_class: IntelligenceService class for analytics, or None when the
  facade builds its own (5 of 6 do — they need domain-specific dependencies)
- event_handler_class / learning_class: always built
- relationship_config: UnifiedRelationshipService config

The registry holds **class references, not module-name strings**. It used to hold
strings resolved through ``importlib.import_module`` at call time, on the stated
grounds of avoiding circular imports; there is no such cycle (measured — no registry
target imports this module, directly or transitively), and every one of this
module's callers already imports both this module and its own domain package at
module level, so the lazy resolution deferred nothing. Naming the classes lets MyPy
check that each registered class is constructible the way the factory constructs it —
which two of them were not.

Usage:
    from core.services.activity_domain_config import ACTIVITY_DOMAIN_CONFIGS, create_common_sub_services

    # In facade __init__:
    common = create_common_sub_services(
        domain="tasks",
        backend=backend,
        graph_intel=graph_intel,
        event_bus=event_bus,
    )
    self.core = common.core
    self.search = common.search
    self.relationships = common.relationships
    self.intelligence = common.intelligence

Created: January 2026
Reason: Consolidate repetitive facade initialization (~480 lines reduction)
"""

from dataclasses import dataclass
from typing import Any, Generic, Protocol, TypeVar

from core.models.relationship_registry import (
    CHOICES_CONFIG,
    EVENTS_CONFIG,
    GOALS_CONFIG,
    HABITS_CONFIG,
    PRINCIPLES_CONFIG,
    TASKS_CONFIG,
)

# Domain configs (direct from registry — no intermediate translation)
from core.ports.base_protocols import BackendOperations
from core.services.choices import ChoicesCoreService, ChoicesSearchService
from core.services.choices.choice_event_handler_service import ChoiceEventHandlerService
from core.services.choices.choices_learning_service import ChoicesLearningService
from core.services.events import EventsCoreService, EventsSearchService
from core.services.events.event_event_handler_service import EventEventHandlerService
from core.services.events.events_learning_service import EventsLearningService
from core.services.goals import GoalsCoreService, GoalsSearchService
from core.services.goals.goal_event_handler_service import GoalEventHandlerService
from core.services.goals.goals_learning_service import GoalsLearningService
from core.services.habits import HabitsCoreService, HabitsSearchService
from core.services.habits.habit_event_handler_service import HabitEventHandlerService
from core.services.habits.habits_learning_service import HabitsLearningService
from core.services.principles import (
    PrinciplesCoreService,
    PrinciplesIntelligenceService,
    PrinciplesSearchService,
)
from core.services.principles.principle_event_handler_service import PrincipleEventHandlerService
from core.services.principles.principles_learning_service import PrinciplesLearningService
from core.services.relationships import UnifiedRelationshipService
from core.services.tasks import TasksCoreService, TasksSearchService
from core.services.tasks.task_event_handler_service import TaskEventHandlerService
from core.services.tasks.tasks_learning_service import TasksLearningService

# Type vars for generics
T_Core = TypeVar("T_Core")  # Core service type (domain-specific)
T_Search = TypeVar("T_Search")  # Search service/protocol type (domain-specific)
T_Intelligence = TypeVar("T_Intelligence")  # Intelligence service type


# Each registry slot is typed against the call ``create_common_sub_services`` actually
# makes, so registering a class the factory cannot construct is a MyPy error here
# rather than a TypeError at boot. Two entries did not survive that check.
#
# The parameter ``Any``s mirror the factory's own signature; narrowing them is a
# separate concern and was measured to buy nothing (see the arc contract, D11).
# The returns are tier C: a narrower ``BaseService[Any, Any]`` was tried first and
# rejects all 6 core services and both event handlers (8 errors; the same probe with
# ``-> Any`` is clean), because the slots hold unrelated concrete classes and the
# event handlers derive from ``object``.
class _CoreFactory(Protocol):
    def __call__(self, *, backend: Any, event_bus: Any) -> Any:  # boundary: service-registry
        ...


class _SearchFactory(Protocol):
    def __call__(self, *, backend: Any) -> Any:  # boundary: service-registry
        ...


class _IntelligenceFactory(Protocol):
    def __call__(
        self, *, backend: Any, graph_intel: Any, relationship_service: Any, insight_store: Any
    ) -> Any:  # boundary: service-registry
        ...


class _EventHandlerFactory(Protocol):
    def __call__(
        self, *, backend: Any, relationship_service: Any, insight_store: Any, event_bus: Any
    ) -> Any:  # boundary: service-registry
        ...


class _LearningFactory(Protocol):
    def __call__(
        self, *, backend: Any, event_bus: Any, relationship_service: Any
    ) -> Any:  # boundary: service-registry
        ...


@dataclass(frozen=True)
class ActivityDomainConfig:
    """Configuration for an Activity Domain's common sub-services."""

    # Service classes, referenced directly — see the module docstring on why these are
    # not module-name strings resolved through importlib.
    core_class: _CoreFactory
    search_class: _SearchFactory

    # None for every domain whose facade builds intelligence itself. Only Principles
    # is constructible from the four arguments this factory has; the other five need
    # domain-specific dependencies (Habits and Choices require ``cross_domain_query``,
    # which this factory has no way to supply).
    intelligence_class: _IntelligenceFactory | None

    # Event handler service (required for all 6 domains)
    event_handler_class: _EventHandlerFactory

    # Learning service (required for all 6 domains)
    learning_class: _LearningFactory

    # Relationship config
    relationship_config: Any

    # Domain metadata
    domain_name: str
    entity_label: str


# Registry of all 6 Activity Domain configurations
ACTIVITY_DOMAIN_CONFIGS: dict[str, ActivityDomainConfig] = {
    "tasks": ActivityDomainConfig(
        core_class=TasksCoreService,
        search_class=TasksSearchService,
        intelligence_class=None,  # TasksService builds it (needs ku_inference_service)
        event_handler_class=TaskEventHandlerService,
        learning_class=TasksLearningService,
        relationship_config=TASKS_CONFIG,
        domain_name="tasks",
        entity_label="Task",
    ),
    "goals": ActivityDomainConfig(
        core_class=GoalsCoreService,
        search_class=GoalsSearchService,
        intelligence_class=None,  # GoalsService builds it (needs progress_service)
        event_handler_class=GoalEventHandlerService,
        learning_class=GoalsLearningService,
        relationship_config=GOALS_CONFIG,
        domain_name="goals",
        entity_label="Goal",
    ),
    "habits": ActivityDomainConfig(
        core_class=HabitsCoreService,
        search_class=HabitsSearchService,
        intelligence_class=None,  # HabitsService builds it (needs cross_domain_query)
        event_handler_class=HabitEventHandlerService,
        learning_class=HabitsLearningService,
        relationship_config=HABITS_CONFIG,
        domain_name="habits",
        entity_label="Habit",
    ),
    "events": ActivityDomainConfig(
        core_class=EventsCoreService,
        search_class=EventsSearchService,
        intelligence_class=None,  # EventsService builds it (needs habit_integration)
        event_handler_class=EventEventHandlerService,
        learning_class=EventsLearningService,
        relationship_config=EVENTS_CONFIG,
        domain_name="events",
        entity_label="Event",
    ),
    "choices": ActivityDomainConfig(
        core_class=ChoicesCoreService,
        search_class=ChoicesSearchService,
        intelligence_class=None,  # ChoicesService builds it (needs cross_domain_query)
        event_handler_class=ChoiceEventHandlerService,
        learning_class=ChoicesLearningService,
        relationship_config=CHOICES_CONFIG,
        domain_name="choices",
        entity_label="Choice",
    ),
    "principles": ActivityDomainConfig(
        core_class=PrinciplesCoreService,
        search_class=PrinciplesSearchService,
        intelligence_class=PrinciplesIntelligenceService,
        event_handler_class=PrincipleEventHandlerService,
        learning_class=PrinciplesLearningService,
        relationship_config=PRINCIPLES_CONFIG,
        domain_name="principles",
        entity_label="Principle",
    ),
}


@dataclass
class CommonSubServices(Generic[T_Core, T_Search, T_Intelligence]):
    """
    Container for common sub-services created by the factory.

    Generic over T_Core, T_Search, and T_Intelligence to preserve concrete
    service/protocol types — so wiring mismatches (e.g., the registry returning
    the wrong class for a given domain key) are caught by mypy.

    Facades annotate the full three-arg form:

        common: CommonSubServices[
            TasksCoreService, TasksSearchOperations, TasksIntelligenceService
        ] = create_common_sub_services(...)

        self.search = common.search          # typed as TasksSearchOperations
        self.intelligence = common.intelligence  # typed as TasksIntelligenceService

    ``event_handler``, ``learning``, and ``knowledge_intelligence`` stay ``Any``
    for now — parametrizing every slot would require five more type vars with
    marginal benefit; the two most-called slots (``core``, ``search``) are
    where silent-cast bugs would hurt most.

    Fields may be None when the corresponding service name is in the ``skip`` set.
    ``event_handler`` and ``learning`` are always built (not skippable via ``skip``).
    ``knowledge_intelligence`` is None unless passed to the factory.
    """

    core: T_Core | None
    search: T_Search | None
    relationships: UnifiedRelationshipService | None
    intelligence: T_Intelligence | None
    event_handler: Any
    learning: Any
    knowledge_intelligence: Any  # None unless passed via activity_knowledge_intelligence


# "intelligence" is deliberately absent: whether it is built is a property of the
# domain (``ActivityDomainConfig.intelligence_class``), not a choice the caller makes.
_VALID_SKIP_NAMES = frozenset({"core", "search", "relationships"})


def create_common_sub_services(
    domain: str,
    # boundary: cross-domain-factory — the type ARGUMENT is genuinely
    # heterogeneous (this one factory builds sub-services for all 6 activity
    # domains, each with a different entity type). The protocol itself is NOT
    # Any: method names and arity are checked, and all 6 callers pass a typed
    # *Operations backend, verified by deliberate break.
    backend: BackendOperations[Any],
    graph_intel: Any,
    event_bus: Any = None,
    insight_store: Any = None,
    skip: set[str] | None = None,
    activity_knowledge_intelligence: Any = None,
) -> CommonSubServices[Any, Any, Any]:
    """
    Factory function to create common sub-services for Activity Domain facades.

    This eliminates ~80 lines of repetitive initialization code per facade.

    Args:
        domain: Domain name ("tasks", "goals", "habits", "events", "choices", "principles")
        backend: Domain backend operations (protocol-typed)
        graph_intel: GraphIntelligenceService for analytics
        event_bus: Event bus for domain events (optional)
        insight_store: InsightStore for persisting event-driven insights (optional)
        skip: Sub-service names to skip constructing (set to None in result).
            Valid names: "core", "search", "relationships".
            Use when the facade creates these manually with domain-specific parameters.
            ``intelligence`` is not skippable — it is built only for domains whose
            config declares an ``intelligence_class``.
        activity_knowledge_intelligence: Shared knowledge intelligence singleton (optional).
            Passed through to CommonSubServices.knowledge_intelligence unchanged.

    Returns:
        CommonSubServices dataclass. Skipped fields are None.
        ``event_handler`` and ``learning`` are always built (not in skip set).
        Callers annotate with the three-arg generic for type safety:

            common: CommonSubServices[
                TasksCoreService, TasksSearchOperations, TasksIntelligenceService
            ] = create_common_sub_services(...)

    Example:
        common: CommonSubServices[
            TasksCoreService, TasksSearchOperations, TasksIntelligenceService
        ] = create_common_sub_services(
            "tasks", backend, graph_intel, event_bus, insight_store,
            activity_knowledge_intelligence=knowledge_intelligence,
        )
        self.core = common.core                  # TasksCoreService
        self.search = common.search              # TasksSearchOperations
        self.relationships = common.relationships
        self.intelligence = common.intelligence  # TasksIntelligenceService
        self.event_handler = common.event_handler
        self.learning = common.learning
        self.knowledge_intelligence = common.knowledge_intelligence
    """
    skip = skip or set()
    invalid = skip - _VALID_SKIP_NAMES
    if invalid:
        msg = f"Invalid skip names: {invalid}. Valid: {_VALID_SKIP_NAMES}"
        raise ValueError(msg)

    config = ACTIVITY_DOMAIN_CONFIGS[domain]

    core = None
    if "core" not in skip:
        core = config.core_class(backend=backend, event_bus=event_bus)

    search = None
    if "search" not in skip:
        search = config.search_class(backend=backend)

    relationships: UnifiedRelationshipService[Any, Any, Any] | None = None
    if "relationships" not in skip:
        relationships = UnifiedRelationshipService(
            backend=backend,
            config=config.relationship_config,
            graph_intel=graph_intel,
        )

    # intelligence — built here only for the domains whose service takes exactly these
    # four arguments. The rest declare ``intelligence_class=None`` and build their own.
    intelligence = None
    if config.intelligence_class is not None:
        intelligence = config.intelligence_class(
            backend=backend,
            graph_intel=graph_intel,
            relationship_service=relationships,
            insight_store=insight_store,
        )

    # event_handler — all 6 domains have one; all accept the same keyword args after Step 1
    event_handler = config.event_handler_class(
        backend=backend,
        relationship_service=relationships,
        insight_store=insight_store,
        event_bus=event_bus,
    )

    # learning — all 6 domains have one
    learning = config.learning_class(
        backend=backend,
        event_bus=event_bus,
        relationship_service=relationships,
    )

    return CommonSubServices(
        core=core,
        search=search,
        relationships=relationships,
        intelligence=intelligence,
        event_handler=event_handler,
        learning=learning,
        knowledge_intelligence=activity_knowledge_intelligence,
    )
