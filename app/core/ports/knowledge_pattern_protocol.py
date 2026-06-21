"""
KnowledgeLinkedRelationships Protocol
======================================

Structural protocol satisfied by any *Relationships dataclass that exposes
Ku links. Adding the three property/methods to an existing frozen dataclass
is sufficient — no explicit registration.

See: core/services/knowledge/knowledge_pattern_analyzer.py
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class KnowledgeLinkedRelationships(Protocol):
    """
    Structural protocol for domain relationship containers that expose Ku links.

    Each *Relationships class (TaskRelationships, GoalRelationships, etc.)
    satisfies this protocol by defining three members:

    - primary_knowledge_uids   — the domain's main Ku relationship
                                 (APPLIES, REINFORCES, INFORMED_BY, GROUNDED_IN, …)
    - secondary_knowledge_uids — supplemental Ku links
                                 (REQUIRES_KNOWLEDGE, inferred, etc.) — may be []
    - knowledge_intensity()    — 0-1 score for how knowledge-rich this entity is,
                                 derived from relationship counts alone
    """

    @property
    def primary_knowledge_uids(self) -> list[str]: ...

    @property
    def secondary_knowledge_uids(self) -> list[str]: ...

    def has_any_knowledge(self) -> bool: ...

    def knowledge_intensity(self) -> float: ...
