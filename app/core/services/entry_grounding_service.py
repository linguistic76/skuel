"""
Entry-Grounding Service
=======================

Grounds UserEntries to Kus so the substance entries-channel and ZPD's
``entry_application`` signal light up for the notes a user syncs: knowledge
notes ("teach SKUEL about me", knowledge/ and je_pro/ doors alike) and activity
notes, periodic notes included — the pipelines ``Pipeline.knowledge_grounded``
names. A ``private: true`` entry is never grounded.

The pass is ``KnowledgeGroundingService``'s (candidates from the entry's stored
embedding, the LLM judge in FULL, eager inferred edges, hash-based re-grounding).
Entries run it in CORE too: an entry the FULL tier embedded earlier grounds
vector-only.

Removal: the chips live in ``ui/user_entry/knowledge_notes.py``, shown to the
owner on three pages: the knowledge-notes list ``/submissions/knowledge``, a
periodic note's ``/journals/{uid}`` and the entry's ``/gradebook/{uid}``, the last
two for an entry on a grounded pipeline; each posts to
``POST /api/user-entries/grounding/remove``. A note that opts out — turns
``private: true``, or leaves the grounded pipelines — loses every inferred edge on
the re-sync that says so (``UserEntryBackend.upsert``), recorded the same way, and
its ``grounded_text_hash`` is cleared; the links its owner named stay.

Substance: each NEW edge publishes ``KnowledgeReflectedInEntry`` — the same
writer-agnostic event the EXTRACT_ACTIVITIES pipeline publishes (handler:
KuBackend.increment_substance with PathStep fan-out, 0.07/entry credit). The
owner's ``@ku`` writer takes the entry's write-lock too, so neither writer
double-counts a pair.

Backend: EntryGroundingBackend. Triggers: the post-sync pass of a personal-vault
sync (its routes in ``vault_routes.py`` and ``scripts/vault_bridge_sync.py``)
+ ``scripts/ground_knowledge.py`` backfill (dry-run default).
See: /docs/architecture/knowledge_substance_philosophy.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.events import publish_event
from core.events.knowledge_substance_events import KnowledgeReflectedInEntry
from core.models.type_hints import UserUID
from core.services.knowledge_grounding_service import KnowledgeGroundingService

if TYPE_CHECKING:
    from core.ports.query_types import GroundingSourceRow


class EntryGroundingService(KnowledgeGroundingService):
    """The UserEntry source of Ku grounding."""

    source = "entry"
    judge_template = "entry_ku_grounding_judge"

    def judge_fields(self, row: GroundingSourceRow, excerpt: str) -> dict[str, str]:
        """The note's title and an excerpt of its body."""
        return {"entry_title": row["title"], "entry_excerpt": excerpt}

    async def _publish_substance(self, row: GroundingSourceRow, ku_uid: str) -> None:
        """``KnowledgeReflectedInEntry``, the event an entry's ``@ku`` link publishes."""
        await publish_event(
            self._event_bus,
            KnowledgeReflectedInEntry(
                knowledge_uid=ku_uid,
                entry_uid=row["uid"],
                user_uid=UserUID(row["user_uid"]),
            ),
            self.logger,
        )
