"""
Entry-Grounding Backend
=======================

The UserEntry source of Ku grounding (``KnowledgeGroundingBackend``).

An entry may ground when it is on a grounded pipeline
(``Pipeline.knowledge_grounded`` — knowledge notes and activity notes, periodic
notes included) and is not ``private: true``: excluded here by name, not only
because the embedding writer skips a private entry. A note that opts out loses its
inferred edges on the re-sync that says so (``UserEntryBackend.upsert``); the gate
is what keeps a pass that read it ahead of the opt-out from linking anything.

The owner's ``@ku`` writer (``UserEntryBackend.write_applied_knowledge``) takes the
entry's write-lock in the order the grounding write does, so the two writers of
one pair serialize on the entry instead of deadlocking.

Protocol: core/ports/grounding_protocols.py KnowledgeGroundingBackendOperations
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from adapters.persistence.neo4j.knowledge_grounding_backend import KnowledgeGroundingBackend
from core.models.enums.neo_labels import NeoLabel
from core.models.enums.pipeline import Pipeline

if TYPE_CHECKING:
    from core.models.type_hints import Neo4jProperties


class EntryGroundingBackend(KnowledgeGroundingBackend):
    """Grounding statements over UserEntries on a grounded pipeline."""

    label = NeoLabel.USER_ENTRY
    content_expression = "coalesce(s.content, s.processed_content, '')"

    def gate(self) -> tuple[str, Neo4jProperties]:
        """On a grounded pipeline, and not private."""
        return (
            "s.pipeline IN $pipelines AND coalesce(s.private, false) = false",
            {"pipelines": [pipeline.value for pipeline in Pipeline.knowledge_grounded()]},
        )
