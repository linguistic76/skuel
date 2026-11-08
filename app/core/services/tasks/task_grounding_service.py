"""
Task-Grounding Service
======================

Grounds Tasks to the Kus they apply, by the task's stored embedding. The pass is
``KnowledgeGroundingService``'s, the one UserEntries run: candidates from the
vector, the LLM judge in FULL, an eager
``(task)-[:APPLIES_KNOWLEDGE {inferred: true, confidence, grounded_at}]->(ku)`` to a
published Ku, a removal recorded and never re-inferred.

Trigger: ``EmbeddingStored`` for a task. The embedding worker stores a task's
vector after its create or an update that changed its embedded text
(``TaskEmbeddingRequested``), and announces it; this service grounds that one task.
The worker drops a request whose text is unchanged, so unchanged text never
re-grounds, and the pending read is hash-based besides. The worker runs in FULL
only, so in CORE a task carries only the knowledge its owner links.

Substance: each NEW inferred edge publishes ``KnowledgeAppliedInTask``, the event
a task's own link publishes at create.

Backend: TaskGroundingBackend (a cancelled task never grounds). Removal:
``POST /api/tasks/grounding/remove``. Backfill: ``scripts/ground_knowledge.py
--source tasks``.
See: /docs/architecture/knowledge_substance_philosophy.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.events import publish_event
from core.events.knowledge_substance_events import KnowledgeAppliedInTask
from core.models.enums.entity_enums import EntityType
from core.models.type_hints import UserUID
from core.services.knowledge_grounding_service import KnowledgeGroundingService
from core.utils.error_boundary import safe_event_handler

if TYPE_CHECKING:
    from core.events.embedding_events import EmbeddingStored
    from core.ports.query_types import GroundingSourceRow


class TaskGroundingService(KnowledgeGroundingService):
    """The Task source of Ku grounding."""

    source = "task"
    judge_template = "task_ku_grounding_judge"

    def judge_fields(self, row: GroundingSourceRow, excerpt: str) -> dict[str, str]:
        """The task's title and an excerpt of its description."""
        return {"task_title": row["title"], "task_excerpt": excerpt}

    async def _publish_substance(self, row: GroundingSourceRow, ku_uid: str) -> None:
        """``KnowledgeAppliedInTask``, the event a task's own knowledge link publishes."""
        await publish_event(
            self._event_bus,
            KnowledgeAppliedInTask(
                knowledge_uid=ku_uid,
                task_uid=row["uid"],
                user_uid=UserUID(row["user_uid"]),
                task_title=row["title"],
            ),
            self.logger,
        )

    @safe_event_handler("embedding.stored")
    async def handle_embedding_stored(self, event: EmbeddingStored) -> None:
        """Ground the task whose embedding the worker just stored; other types pass."""
        if event.entity_type != EntityType.TASK.value:
            return
        result = await self.ground_pending(source_uid=event.entity_uid)
        if result.is_error:
            self.logger.warning(
                f"Task grounding after embedding failed for {event.entity_uid}: "
                f"{result.expect_error()}"
            )
