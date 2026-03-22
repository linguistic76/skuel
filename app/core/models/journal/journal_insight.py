"""
JournalInsight — ZPD signal extracted from a processed journal entry.

Phase 2 stub: shape defined, extraction logic deferred pending
JournalOutputGenerator extension and ZPDService implementation.

See: /docs/architecture/ASKESIS_PEDAGOGICAL_ARCHITECTURE.md
See: /docs/roadmap/zpd-service-deferred.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime


@dataclass(frozen=True)
class JournalInsight:
    """Pedagogical signals extracted from a processed journal entry.

    Populated by JournalOutputGenerator (Phase 2) after the formatting pass.
    Consumed by AskesisService.answer_user_question() when building
    scaffold_entry context — passively, when the user opens a conversation.

    Fields are empty lists until extraction is implemented.
    """

    journal_uid: str
    extracted_at: datetime

    open_questions: list[str] = field(default_factory=list)
    # Questions the user left unresolved — prime conversation starters

    concepts_mentioned: list[str] = field(default_factory=list)
    # Concepts that appeared — link to KUs via semantic search (Phase 2)

    struggles: list[str] = field(default_factory=list)
    # Expressed uncertainty or difficulty — scaffolding targets

    insights_crystallized: list[str] = field(default_factory=list)
    # Things that clicked — mastery signals (update graph, Phase 2)

    related_ku_uids: list[str] = field(default_factory=list)
    # _Placeholder: KU links via semantic search — populated in Phase 2
