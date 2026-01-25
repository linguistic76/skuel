"""
Infrastructure Adapters
=======================

Infrastructure components for the application.
"""

from .event_bus import InMemoryEventBus

__all__ = [
    "InMemoryEventBus",
]
