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
    from core.utils.activity_domain_config import ACTIVITY_DOMAIN_CONFIGS, create_common_sub_services

    # In facade __init__:
    common = create_common_sub_services(
        domain="tasks",
        backend=backend,
        graph_intel=graph_intelligence_service,
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
    GOALS_CONFIG,
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
        relationship_config=GOALS_CONFIG,
        domain_name="goals",
        entity_label="Goal",
    ),
    "habits": ActivityDomainConfig(
        core_module="core.services.habits",
        core_class="HabitsCoreService",
        search_module="core.services.habits",
        search_class="HabitSearchService",
        intelligence_module="core.services.habits",
        intelligence_class="HabitsIntelligenceService",
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
        relationship_config=PRINCIPLES_CONFIG,
        domain_name="principles",
        entity_label="Principle",
    ),
}


@dataclass
class CommonSubServices(Generic[T_Intelligence]):
    """
    Container for the 4 common sub-services created by the factory.

    Generic over T_Intelligence to preserve the concrete intelligence service type.
    Facades should annotate the assignment to get proper type checking:

        common: CommonSubServices[TasksIntelligenceService] = create_common_sub_services(...)
        self.intelligence = common.intelligence  # MyPy knows this is TasksIntelligenceService
    """

    core: Any
    search: Any
    relationships: UnifiedRelationshipService
    intelligence: T_Intelligence


def create_common_sub_services(
    domain: str,
    backend: Any,
    graph_intel: Any,
    event_bus: Any = None,
    insight_store: Any = None,
) -> CommonSubServices[Any]:
    """
    Factory function to create the 4 common sub-services for Activity Domain facades.

    This eliminates ~80 lines of repetitive initialization code per facade.

    Args:
        domain: Domain name ("tasks", "goals", "habits", "events", "choices", "principles")
        backend: Domain backend operations (protocol-typed)
        graph_intel: GraphIntelligenceService for analytics
        event_bus: Event bus for domain events (optional)
        insight_store: InsightStore for persisting event-driven insights (optional, Phase 1 - January 2026)

    Returns:
        CommonSubServices dataclass with core, search, relationships, intelligence.
        Callers should annotate with specific intelligence type for type safety:

            common: CommonSubServices[TasksIntelligenceService] = create_common_sub_services(...)

    Example:
        common: CommonSubServices[TasksIntelligenceService] = create_common_sub_services(
            "tasks", backend, graph_intel, event_bus, insight_store
        )
        self.core = common.core
        self.search = common.search
        self.relationships = common.relationships
        self.intelligence = common.intelligence  # Typed as TasksIntelligenceService
    """
    import importlib

    config = ACTIVITY_DOMAIN_CONFIGS[domain]

    # Dynamically import service classes to avoid circular imports
    core_module = importlib.import_module(config.core_module)
    core_class = getattr(core_module, config.core_class)

    search_module = importlib.import_module(config.search_module)
    search_class = getattr(search_module, config.search_class)

    intel_module = importlib.import_module(config.intelligence_module)
    intel_class = getattr(intel_module, config.intelligence_class)

    # Create core service (all take backend + optional event_bus)
    core = core_class(backend=backend, event_bus=event_bus)

    # Create search service (just backend)
    search = search_class(backend=backend)

    # Create relationships service (backend + config + graph_intel)
    relationships = UnifiedRelationshipService(
        backend=backend,
        config=config.relationship_config,
        graph_intel=graph_intel,
    )

    # Create intelligence service (backend + graph_intel + relationships + insight_store)
    # Note: Not all intelligence services support insight_store yet - pass if available
    try:
        intelligence = intel_class(
            backend=backend,
            graph_intelligence_service=graph_intel,
            relationship_service=relationships,
            insight_store=insight_store,
        )
    except TypeError:
        # Fallback for intelligence services that don't have insight_store parameter yet
        intelligence = intel_class(
            backend=backend,
            graph_intelligence_service=graph_intel,
            relationship_service=relationships,
        )

    return CommonSubServices(
        core=core,
        search=search,
        relationships=relationships,
        intelligence=intelligence,
    )
