"""SKUEL Service Bootstrap Package — composition root for all domain services.

Decomposes the service wiring into domain-specific modules while maintaining
a single entry point via compose_services(). All external callers continue
to use ``from services_bootstrap import Services, compose_services``.

Modules:
    _container.py         — Services dataclass + cleanup
    _backends.py          — UniversalNeo4jBackend instantiation
    _core_services.py     — Finance, Transcription, Orchestration, Advanced
    _activity_services.py — 6 Activity Domain facades
    _learning_services.py — PS, KU, LP, embeddings
    _ai_wiring.py         — Conditional AI service wiring (FULL tier)
    _event_wiring.py      — 45+ event bus subscriptions
    _intelligence_hub.py  — UserContextIntelligence, ZPD, Askesis
    _system_health.py     — SystemService component health-checker registration
    compose.py            — compose_services() orchestration
"""

from core.ports import EventBusOperations
from services_bootstrap._container import Services
from services_bootstrap._system_health import initialize_system_service
from services_bootstrap.compose import compose_services

__all__ = [
    "EventBusOperations",
    "Services",
    "compose_services",
    "initialize_system_service",
]
