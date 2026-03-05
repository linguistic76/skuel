"""
ZPD Protocol
============

Protocol interface for ZPDService — the pedagogical core of Askesis that
computes a user's Zone of Proximal Development from the Neo4j curriculum graph.

See: core/services/zpd/zpd_service.py — implementation
See: docs/roadmap/zpd-service-deferred.md — design rationale
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from core.models.zpd.zpd_assessment import ZPDAssessment
    from core.utils.result_simplified import Result


@runtime_checkable
class ZPDOperations(Protocol):
    """Pure graph computation protocol for Zone of Proximal Development.

    ZPDService implements this protocol. It is stateless — every call
    traverses the live Neo4j curriculum graph. No ZPD state is stored.

    Consumed by:
    - UserContextIntelligence.get_optimal_next_learning_steps()
    - AskesisService.analyze_user_state() — ZPDAssessment in state snapshot
    """

    async def assess_zone(self, user_uid: str) -> Result[ZPDAssessment]:
        """Compute the user's full ZPD from the curriculum graph.

        2-hop traversal: current zone → proximal zone → readiness scores.
        Returns an empty ZPDAssessment (not an error) when the curriculum
        graph has fewer than 3 KUs.

        Args:
            user_uid: User's unique identifier (e.g. "user_alice")

        Returns:
            Result[ZPDAssessment]: Full ZPD snapshot including current zone,
                proximal zone, readiness scores, blocking gaps, and
                behavioral readiness.
        """
        ...

    async def get_proximal_ku_uids(self, user_uid: str) -> Result[list[str]]:
        """Get only the proximal zone KU UIDs for lightweight callers.

        Convenience wrapper over assess_zone() that extracts just the
        proximal_zone list. Use when only the candidate KU list is needed
        and the full ZPDAssessment is not required.

        Args:
            user_uid: User's unique identifier

        Returns:
            Result[list[str]]: ku_uids in the user's proximal zone,
                ordered by readiness score descending.
        """
        ...

    async def get_readiness_score(self, user_uid: str, ku_uid: str) -> Result[float]:
        """Get the readiness score for a specific KU.

        Calls assess_zone() and extracts the score for the given KU.
        Returns 0.0 for KUs not in the proximal zone.

        Args:
            user_uid: User's unique identifier
            ku_uid: Knowledge Unit to score

        Returns:
            Result[float]: Readiness score 0.0–1.0. 1.0 means all
                prerequisites are met; 0.0 means none are.
        """
        ...
