"""
Cross-Domain Query Service
==========================

Read-side cross-domain queries that leverage the graph directly via Cypher.

The rule for this package: every method touches 2+ domain labels and runs
exactly one Cypher query. Single-domain queries belong in their domain's
own service. See the conversation summary (2026-04-09) for the rationale —
the goal is to stop the "fetch all of A, fetch all of B, loop in Python"
anti-pattern by letting the graph do the work.
"""

from core.services.cross_domain.cross_domain_query_service import CrossDomainQueryService
from core.services.cross_domain.cross_domain_types import (
    ActiveTaskCount,
    AlignedEntity,
    HabitKnowledgeReinforcement,
    KnowledgeApplyingTask,
    PrincipleAlignmentEvidence,
    TasksForKnowledge,
)

__all__ = [
    "ActiveTaskCount",
    "AlignedEntity",
    "CrossDomainQueryService",
    "HabitKnowledgeReinforcement",
    "KnowledgeApplyingTask",
    "PrincipleAlignmentEvidence",
    "TasksForKnowledge",
]
