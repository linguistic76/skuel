"""HXML element builders for Hyperview mobile responses.

Hyperview (hyperview.org) is a server-driven mobile framework using HXML —
a purpose-built XML format for native mobile UIs. HXML is to native mobile
what HTML is to web browsers.

Content negotiation (is_hyperview_client) lives in adapters/inbound/negotiation.py —
it is a boundary concern, not a core HXML element.

Phase: Groundwork — basic elements for future React Native client.

See: /docs/decisions/ADR-039-hyperview-mobile-strategy.md
See: /docs/architecture/HYPERVIEW_STRATEGY.md
"""

from core.hxml.elements import Behavior, Doc, Screen, Style, Text, View

__all__ = [
    "Behavior",
    "Doc",
    "Screen",
    "Style",
    "Text",
    "View",
]
