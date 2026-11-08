"""
Task-Grounding Backend
======================

The Task source of Ku grounding (``KnowledgeGroundingBackend``).

A task may ground unless it is cancelled: a cancelled task did not happen, so it
applied nothing. Any other status grounds, a completed task included, since doing
the task is what applies the knowledge. The judge reads the task's description.

The owner's links are written by the Tasks link doors through the guarded link
write (``build_guarded_link_query``): it promotes an inferred edge the owner names
to the owner's link, and a replace of the owner's set leaves inferred edges alone.

Protocol: core/ports/grounding_protocols.py KnowledgeGroundingBackendOperations
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from adapters.persistence.neo4j.knowledge_grounding_backend import KnowledgeGroundingBackend
from core.models.enums import EntityStatus
from core.models.enums.neo_labels import NeoLabel

if TYPE_CHECKING:
    from core.models.type_hints import Neo4jProperties

#: Statuses whose task never grounds.
UNGROUNDED_TASK_STATUSES: tuple[EntityStatus, ...] = (EntityStatus.CANCELLED,)


class TaskGroundingBackend(KnowledgeGroundingBackend):
    """Grounding statements over Tasks that are not cancelled."""

    label = NeoLabel.TASK
    content_expression = "coalesce(s.description, '')"

    def gate(self) -> tuple[str, Neo4jProperties]:
        """Not cancelled."""
        return (
            "NOT coalesce(s.status, '') IN $ungrounded_statuses",
            {"ungrounded_statuses": [status.value for status in UNGROUNDED_TASK_STATUSES]},
        )
