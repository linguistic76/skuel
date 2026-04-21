"""
Activity Domain Configuration Registry
======================================

Centralizes configuration for 6 Activity Domain facades.

Each domain has:
- core_class: CoreService class for CRUD operations
- search_class: SearchService class for discovery
- intelligence_class: IntelligenceService class for analytics
- relationship_config: UnifiedRelationshipService config

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
from typing import Any, Generic, TypeVar

# Domain configs (direct from registry — no intermediate translation)
from core.models.relationship_registry import (
    CHOICES_CONFIG,
    EVENTS_CONFIG,
    GOAPS_CONFIG,
    HABITS_CONFIG,
    PRINCIPLES_CONFIG,
    TASKS_CONFIG,
)
from core.services.relationships import UnifiedRelationshipService

# Type vars for generics
T = TypeVar("T")  # Domain model type
B = TypeVar("B")  # Backend operations protocol
T_Intelligence = TypeVar("T_Intelligence")  # Intelligence service type


@dataclass(frozen=True)
class ActivityDomainConfig:
    """Configuration for an Activity Domain's common sub-services."""

    # Service classes (imported lazily to avoid circular imports)
    core_module: str
    core_class: str
    search_module: str
    search_class: str
    intelligence_module: str
    intelligence_class: str

    # Event handler service (required for all 6 domains)
    event_handler_module: str
    event_handler_class: str

    # Learning service (None for Tasks, which uses learning_metrics instead)
    learning_module: str | None
    learning_class: str | None

    # Relationship config
    relationship_config: Any

    # Domain metadata
    domain_name: str
    entity_label: str


# Registry of all 6 Activity Domain configurations
ACTIVITY_DOMAIN_CONFIGS: dict[str, ActivityDomainConfig] = {
    "tasks": ActivityDomainConfig(
        core_module="core.services.tasks",
        core_class="TasksCoreService",
        search_module="core.services.tasks",
        search_class="TasksSearchService",
        intelligence_module="core.services.tasks",
        intelligence_class="TasksIntelligenceService",
        event_handler_module="core.services.tasks.task_event_handler_service",
        event_handler_class="TaskEventHandlerService",
        learning_module=None,
        learning_class=None,
        relationship_config=TASKS_CONFIG,
        domain_name="tasks",
        entity_label="Task",
    ),
    "goals": ActivityDomainConfig(
        core_module="core.services.goals",
        core_class="GoalsCoreService",
        search_module="core.services.goals",
        search_class="GoalsSearchService",
        intelligence_module="core.services.goals",
        intelligence_class="GoalsIntelligenceService",
        event_handler_module="core.services.goals.goal_event_handler_service",
        event_handler_class="GoalEventHandlerService",
        learning_module="core.services.goals.goals_learning_service",
        learning_class="GoalsLearningService",
        relationship_config=GOAPS_CONFIG,
        domain_name="goals",
        entity_label="Goal",
    ),
    "habits": ActivityDomainConfig(
        core_module="core.services.habits",
        core_class="HabitsCoreService",
        search_module="core.services.habits",
        search_class="HabitsSearchService",
        intelligence_module="core.services.habits",
        intelligence_class="HabitsIntelligenceService",
        event_handler_module="core.services.habits.habit_event_handler_service",
        event_handler_class="HabitEventHandlerService",
        learning_module="core.services.habits.habits_learning_service",
        learning_class="HabitsLearningService",
        relationship_config=HABITS_CONFIG,
        domain_name="habits",
        entity_label="Habit",
    ),
    "events": ActivityDomainConfig(
        core_module="core.services.events",
        core_class="EventsCoreService",
        search_module="core.services.events",
        search_class="EventsSearchService",
        intelligence_module="core.services.events",
        intelligence_class="EventsIntelligenceService",
        event_handler_module="core.services.events.event_event_handler_service",
        event_handler_class="EventEventHandlerService",
        learning_module="core.services.events.events_learning_service",
        learning_class="EventsLearningService",
        relationship_config=EVENTS_CONFIG,
        domain_name="events",
        entity_label="Event",
    ),
    "choices": ActivityDomainConfig(
        core_module="core.services.choices",
        core_class="ChoicesCoreService",
        search_module="core.services.choices",
        search_class="ChoicesSearchService",
        intelligence_module="core.services.choices",
        intelligence_class="ChoicesIntelligenceService",
        event_handler_module="core.services.choices.choice_event_handler_service",
        event_handler_class="ChoiceEventHandlerService",
        learning_module="core.services.choices.choices_learning_service",
        learning_class="ChoicesLearningService",
        relationship_config=CHOICES_CONFIG,
        domain_name="choices",
        entity_label="Choice",
    ),
    "principles": ActivityDomainConfig(
        core_module="core.services.principles",
        core_class="PrinciplesCoreService",
        search_module="core.services.principles",
        search_class="PrinciplesSearchService",
        intelligence_module="core.services.principles",
        intelligence_class="PrinciplesIntelligenceService",
        event_handler_module="core.services.principles.principle_event_handler_service",
        event_handler_class="PrincipleEventHandlerService",
        learning_module="core.services.principles.principles_learning_service",
        learning_class="PrinciplesLearningService",
        relationship_config=PRINCIPLES_CONFIG,
        domain_name="principles",
        entity_label="Principle",
    ),
}


@dataclass
class CommonSubServices(Generic[T_Intelligence]):
    """
    Container for common sub-services created by the factory.

    Generic over T_Intelligence to preserve the concrete intelligence service type.
    Facades should annotate the assignment to get proper type checking:

        common: CommonSubServices[TasksIntelligenceService] = create_common_sub_services(...)
        self.intelligence = common.intelligence # MyPy knows this is TasksIntelligenceService

    Fields may be None when the corresponding service name is in the ``skip`` set.
    ``event_handler`` and ``learning`` are always built (not skippable via ``skip``).
    ``knowledge_intelligence`` is None unless passed to the factory.
    """

    core: Any
    search: Any
    relationships: UnifiedRelationshipService | None
    intelligence: T_Intelligence | None
    event_handler: Any
    learning: Any  # None for Tasks (no learning service)
    knowledge_intelligence: Any  # None unless passed via activity_knowledge_intelligence


_VALID_SKIP_NAMES = frozenset({"core", "search", "relationships", "intelligence"})


def create_common_sub_services(
    domain: str,
    backend: Any,
    graph_intel: Any,
    event_bus: Any = None,
    insight_store: Any = None,
    skip: set[str] | None = None,
    activity_knowledge_intelligence: Any = None,
) -> CommonSubServices[Any]:
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
            Valid names: "core", "search", "relationships", "intelligence".
            Use when the facade creates these manually with domain-specific parameters.
        activity_knowledge_intelligence: Shared knowledge intelligence singleton (optional).
            Passed through to CommonSubServices.knowledge_intelligence unchanged.

    Returns:
        CommonSubServices dataclass. Skipped fields are None.
        ``event_handler`` and ``learning`` are always built (not in skip set).
        Callers should annotate with specific intelligence type for type safety:

            common: CommonSubServices[TasksIntelligenceService] = create_common_sub_services(...)

    Example:
        common: CommonSubServices[TasksIntelligenceService] = create_common_sub_services(
            "tasks", backend, graph_intel, event_bus, insight_store,
            activity_knowledge_intelligence=knowledge_intelligence,
        )
        self.core = common.core
        self.search = common.search
        self.relationships = common.relationships
        self.intelligence = common.intelligence  # Typed as TasksIntelligenceService
        self.event_handler = common.event_handler
        self.learning = common.learning        # None for Tasks
        self.knowledge_intelligence = common.knowledge_intelligence
    """
    import importlib

    skip = skip or set()
    invalid = skip - _VALID_SKIP_NAMES
    if invalid:
        msg = f"Invalid skip names: {invalid}. Valid: {_VALID_SKIP_NAMES}"
        raise ValueError(msg)

    config = ACTIVITY_DOMAIN_CONFIGS[domain]

    # Dynamically import service classes to avoid circular imports
    # (only import what we need)
    core = None
    if "core" not in skip:
        core_module = importlib.import_module(config.core_module)
        core_class = getattr(core_module, config.core_class)
        core = core_class(backend=backend, event_bus=event_bus)

    search = None
    if "search" not in skip:
        search_module = importlib.import_module(config.search_module)
        search_class = getattr(search_module, config.search_class)
        search = search_class(backend=backend)

    relationships = None
    if "relationships" not in skip:
        relationships = UnifiedRelationshipService(
            backend=backend,
            config=config.relationship_config,
            graph_intel=graph_intel,
        )

    intelligence = None
    if "intelligence" not in skip:
        intel_module = importlib.import_module(config.intelligence_module)
        intel_class = getattr(intel_module, config.intelligence_class)
        intelligence = intel_class(
            backend=backend,
            graph_intel=graph_intel,
            relationship_service=relationships,
            insight_store=insight_store,
        )

    # event_handler — all 6 domains have one; all accept the same keyword args after Step 1
    eh_module = importlib.import_module(config.event_handler_module)
    eh_class = getattr(eh_module, config.event_handler_class)
    event_handler = eh_class(
        backend=backend,
        relationship_service=relationships,
        insight_store=insight_store,
        event_bus=event_bus,
    )

    # learning — 5 domains have one; Tasks (learning_module=None) skips
    learning = None
    if config.learning_module is not None:
        learn_module = importlib.import_module(config.learning_module)
        learn_class = getattr(learn_module, config.learning_class)
        learning = learn_class(
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
