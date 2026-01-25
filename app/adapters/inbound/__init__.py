"""
SKUEL Inbound Adapters - HTTP/Web Interface Layer
=================================================

This package contains the inbound adapters implementing HTTP routes and web interfaces
following the hexagonal architecture pattern.

Structure - Consolidated Route Modules:
- system_routes.py     - Main dashboard, health, operations, sync
- core_routes.py       - Tasks, habits, timeline (core productivity)
- content_routes.py    - Journals, audio transcription (content creation)
- knowledge_routes.py  - Discovery, hierarchical search, askesis (knowledge management)
- finance_routes.py    - Financial tracking and analysis

Key Principles:
- Routes are pure adapters - no business logic
- Services injected explicitly via parameters (no service locators)
- Clean separation between HTTP concerns and domain logic
- Consistent error handling and response patterns

Architecture:
- Each route module exports a single `create_*_routes(app, rt, services...)` function
- Services are explicitly injected - no hidden dependencies
- Routes delegate to services and return HTTP responses
- UI rendering handled by specialized UI adapters

Example:
    from adapters.inbound.system_routes import create_system_routes
    from adapters.inbound.core_routes import create_core_routes

    # Services explicitly injected
    create_system_routes(app, rt, services, sync_service)
    create_core_routes(app, rt, tasks_service, habits_service)
"""

__version__ = "1.0"


# Consolidated route factory exports
# Note: content_routes and core_routes removed (functionality moved to other modules)
__all__ = [
    "create_finance_routes",
    "create_system_routes",
]

# Import route factory functions for convenience
try:
    from .finance_routes import create_finance_routes
    from .system_routes import create_system_routes
except ImportError:
    # Graceful fallback if route modules aren't available
    pass
