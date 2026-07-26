"""
KnowledgeLinkedRelationships Protocol
======================================

Structural protocol satisfied by any *Relationships dataclass that exposes
Ku links. Adding the three property/methods to an existing frozen dataclass
is sufficient — no explicit registration.

``compute_knowledge_intensity`` lives here too: the contract says the score is
"derived from relationship counts alone", so the one formula that satisfies it
belongs beside the contract rather than copied into each implementer.

See: core/services/knowledge/knowledge_pattern_analyzer.py
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from core.constants import KnowledgeIntensityWeight


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


def compute_knowledge_intensity(
    primary: Sequence[str],
    secondary: Sequence[str],
) -> float:
    """
    Score how knowledge-rich an entity is from its Ku edge counts alone.

    Weighted count of the two Ku tiers, clamped to 1.0. Domains with no
    secondary tier pass an empty sequence and land on the primary-only curve
    (7 primary edges saturate the score).

    Args:
        primary: The domain's main Ku links (APPLIES, REINFORCES, …).
        secondary: Supplemental Ku links (REQUIRES, inferred, …); may be empty.

    Returns:
        0.0-1.0 intensity score.
    """
    return min(
        1.0,
        len(primary) * KnowledgeIntensityWeight.PRIMARY
        + len(secondary) * KnowledgeIntensityWeight.SECONDARY,
    )
