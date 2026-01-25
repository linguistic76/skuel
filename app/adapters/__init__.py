"""
SKUEL Adapters Layer - Clean Architecture
==========================================

This package contains the web layer adapters implementing the Inbound Adapters pattern.

Architecture Structure:
- inbound/    - HTTP/Web adapters (FastHTML routes, API controllers)

Key Principles:
- Inbound adapters handle HTTP requests and delegate to domain services
- All outbound adapters moved to domain-specific locations in core/
- Clean separation between web layer and business logic
- Domain services injected via dependency injection at startup

Migration Notes:
- outbound/ → Moved to core/ (database adapters, external services)
- Legacy knowledge adapters → Replaced by domain services
- Ports → Co-located with their domain services in core/services/

Example Usage:
    # Infrastructure adapters now in core/
    from adapters.persistence.neo4j_adapter import Neo4jAdapter
    from adapters.events_adapters import InMemoryEventBus

    # Web routes in adapters/inbound/
    from adapters.inbound.tasks_routes import create_tasks_routes
"""

__version__ = "1.0"


# Exports - core infrastructure adapters
__all__ = [
    "InMemoryEventBus",
    # V2 Infrastructure (relocated to core/)
    "Neo4jAdapter",
]

# Import V2 adapters from their new locations
try:
    # Infrastructure adapters
    from adapters.infrastructure.event_bus import InMemoryEventBus
    from adapters.persistence.neo4j_adapter import Neo4jAdapter

except ImportError:
    # Development environments may not have all adapters available
    pass
