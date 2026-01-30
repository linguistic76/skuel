"""
Service Introspection Utilities
================================

Generic utilities for introspecting and validating BaseService instances.

These functions demonstrate the value of BaseServiceInterface protocol:
- Type-safe generic operations across any domain service
- IDE autocomplete for all BaseService methods
- Runtime validation of service capabilities

Usage:
    from core.utils.service_introspection import get_service_capabilities

    capabilities = await get_service_capabilities(tasks_service)
    # Returns: {"has_categories": True, "has_user_progress": True, ...}
"""

from typing import Any

from core.services.protocols.base_service_interface import BaseServiceInterface
from core.utils.logging import get_logger

logger = get_logger(__name__)


async def get_service_capabilities(
    service: BaseServiceInterface[Any, Any],
    domain_name: str | None = None,
) -> dict[str, Any]:
    """
    Analyze service capabilities using BaseService protocol methods.

    Demonstrates BaseServiceInterface value:
    - Works with ANY BaseService (Tasks, Goals, Habits, KU, etc.)
    - IDE autocompletes all available methods
    - Type-safe access to common BaseService operations

    Args:
        service: Any service implementing BaseServiceInterface
        domain_name: Optional domain name for logging

    Returns:
        Dictionary of service capabilities and statistics

    Example:
        capabilities = await get_service_capabilities(tasks_service, "tasks")
        # {
        #     "has_categories": True,
        #     "category_count": 5,
        #     "has_user_progress": True,
        #     "supports_graph_context": True,
        # }
    """
    domain = domain_name or "unknown"
    capabilities = {}

    # Check category support (BaseService.list_categories from SearchMixin)
    categories_result = await service.list_categories()
    capabilities["has_categories"] = not categories_result.is_error
    if not categories_result.is_error and categories_result.value:
        capabilities["category_count"] = len(categories_result.value)
        logger.debug(f"{domain} has {len(categories_result.value)} categories")

    # Check user progress support (BaseService from UserProgressMixin)
    # Note: has_user_progress is a property on the service's _config
    try:
        config = getattr(service, "_config", None)
        if config:
            capabilities["has_user_progress"] = getattr(config, "supports_user_progress", False)
    except AttributeError:
        capabilities["has_user_progress"] = False

    # Check graph context support
    capabilities["supports_graph_context"] = True  # All BaseService instances support this

    logger.info(f"Service capabilities for {domain}: {capabilities}")
    return capabilities


def validate_service_for_analytics(
    service: BaseServiceInterface[Any, Any],
    required_methods: list[str] | None = None,
) -> tuple[bool, list[str]]:
    """
    Validate that a service has required methods for analytics.

    Demonstrates protocol-based capability checking.

    Args:
        service: Any service implementing BaseServiceInterface
        required_methods: List of method names to check (default: common analytics methods)

    Returns:
        Tuple of (is_valid, missing_methods)

    Example:
        is_valid, missing = validate_service_for_analytics(
            service,
            required_methods=["search", "get_by_status", "list_categories"]
        )
        if not is_valid:
            logger.warning(f"Service missing methods: {missing}")
    """
    if required_methods is None:
        # Default analytics methods from BaseService
        required_methods = [
            "search",  # SearchMixin
            "get_by_status",  # SearchMixin
            "list_categories",  # SearchMixin
            "convert_to_dto",  # ConversionHelpersMixin
        ]

    missing_methods = [
        method_name for method_name in required_methods if not hasattr(service, method_name)
    ]

    is_valid = len(missing_methods) == 0
    return is_valid, missing_methods


async def get_domain_health_report(
    services: dict[str, BaseServiceInterface[Any, Any]],
) -> dict[str, dict[str, Any]]:
    """
    Generate health report across multiple domain services.

    Demonstrates using BaseServiceInterface for cross-domain operations.

    Args:
        services: Dictionary of {domain_name: service} pairs

    Returns:
        Health report with statistics for each domain

    Example:
        services = {
            "tasks": tasks_service,
            "goals": goals_service,
            "habits": habits_service,
        }
        report = await get_domain_health_report(services)
        # {
        #     "tasks": {"categories": 5, "healthy": True},
        #     "goals": {"categories": 3, "healthy": True},
        #     ...
        # }
    """
    health_report = {}

    for domain_name, service in services.items():
        logger.debug(f"Analyzing {domain_name} service health")

        # Use BaseService methods (IDE autocompletes these!)
        capabilities = await get_service_capabilities(service, domain_name)
        is_valid, missing = validate_service_for_analytics(service)

        health_report[domain_name] = {
            "healthy": is_valid,
            "capabilities": capabilities,
            "missing_methods": missing,
        }

    logger.info(f"Health report generated for {len(services)} domains")
    return health_report


# Example: Service registry using BaseServiceInterface
class ServiceRegistry:
    """
    Generic service registry demonstrating BaseServiceInterface usage.

    All services must implement BaseServiceInterface to be registered.
    This provides type safety and IDE autocomplete for registry operations.
    """

    def __init__(self) -> None:
        self._services: dict[str, BaseServiceInterface[Any, Any]] = {}
        logger.info("ServiceRegistry initialized")

    def register(
        self,
        domain_name: str,
        service: BaseServiceInterface[Any, Any],
    ) -> None:
        """
        Register a service by domain name.

        Args:
            domain_name: Domain identifier (e.g., "tasks", "goals")
            service: Service implementing BaseServiceInterface
        """
        self._services[domain_name] = service
        logger.info(f"Registered {domain_name} service")

    async def get_all_categories(self) -> dict[str, list[str]]:
        """
        Get categories from all registered services.

        Demonstrates cross-domain operations using common BaseService methods.
        """
        all_categories = {}

        for domain_name, service in self._services.items():
            # IDE autocompletes list_categories() because of BaseServiceInterface!
            result = await service.list_categories()
            if not result.is_error and result.value:
                all_categories[domain_name] = result.value

        return all_categories

    def get_service(self, domain_name: str) -> BaseServiceInterface[Any, Any] | None:
        """Get service by domain name."""
        return self._services.get(domain_name)


__all__ = [
    "get_service_capabilities",
    "validate_service_for_analytics",
    "get_domain_health_report",
    "ServiceRegistry",
]
