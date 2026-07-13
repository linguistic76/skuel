"""
Understanding-wall guard tests — persisted discussion sessions (ADR-078 §7).

The wall is enforced by ABSENCE: ``:ConversationSession`` / ``:ConversationTurn``
are NeoLabels only, never EntityTypes, so every EntityType-keyed understanding
surface (embeddings, SearchRouter, the context builder) is structurally blind to
them. These are the CI-runnable UNIT forms of guards 3/4/5 plus the load-bearing
non-membership check. Guards 1/2/6 (owner-visibility, delete-completeness, no
enrichment edges) are integration — run locally against Docker Neo4j.

Each test fails LOUDLY if a future change registers these labels on an
understanding surface — that is the point.
"""

from __future__ import annotations

import inspect

from core.models.enums.entity_enums import EntityType
from core.models.enums.neo_labels import NeoLabel

_SESSION = NeoLabel.CONVERSATION_SESSION.value
_TURN = NeoLabel.CONVERSATION_TURN.value


# ---------------------------------------------------------------------------
# The load-bearing wall: NeoLabels, but NOT EntityTypes.
# ---------------------------------------------------------------------------
def test_conversation_labels_are_neolabels_not_entity_types() -> None:
    # They exist as node labels...
    assert NeoLabel.is_valid(_SESSION)
    assert NeoLabel.is_valid(_TURN)
    # ...but are absent from EntityType. This non-membership IS the wall: the
    # embedding/search/context surfaces are all EntityType-keyed, so they can
    # never resolve these labels. Adding either to EntityType breaks the ADR-078
    # guarantee — this assertion is the tripwire.
    entity_values = {e.value for e in EntityType}
    assert _SESSION not in entity_values
    assert _TURN not in entity_values
    assert EntityType.from_string(_SESSION) is None
    assert EntityType.from_string(_TURN) is None


# ---------------------------------------------------------------------------
# Guard 4 (unit) — no embeddings.
# ---------------------------------------------------------------------------
def test_conversation_labels_have_no_embedding_registration() -> None:
    from core.events.embedding_publisher import (
        EMBEDDING_EVENT_TYPES,
        EMBEDDING_NODE_LABELS,
    )

    # No embedding node-label maps to the conversation labels, and no EntityType
    # key could (they are not EntityTypes) — so no *EmbeddingRequested event is
    # ever published for a session/turn.
    assert _SESSION not in EMBEDDING_NODE_LABELS.values()
    assert _TURN not in EMBEDDING_NODE_LABELS.values()
    # EMBEDDING_EVENT_TYPES is EntityType-keyed; confirm the wall holds there too.
    assert all(key in EntityType for key in EMBEDDING_EVENT_TYPES)


# ---------------------------------------------------------------------------
# Guard 5 (unit) — search invisibility.
# ---------------------------------------------------------------------------
def test_conversation_labels_are_not_searchable_domains() -> None:
    from core.models.search.search_router import SearchRouter

    # The searchable-domain registry is EntityType-keyed; since the conversation
    # labels are not EntityTypes, they cannot be registered as a searchable
    # domain. Assert every searchable domain is a real EntityType (so nothing
    # smuggled the labels in via a string) and the labels are absent.
    searchable_values = {d.value for d in SearchRouter._SEARCHABLE_DOMAINS}
    assert _SESSION not in searchable_values
    assert _TURN not in searchable_values
    assert all(isinstance(d, EntityType) for d in SearchRouter._SEARCHABLE_DOMAINS)


# ---------------------------------------------------------------------------
# Guard 3 (unit, source-inspection) — the context builder never reads them.
# ---------------------------------------------------------------------------
def test_context_builder_does_not_reference_conversation_labels() -> None:
    from core.services.journal.journal_service import JournalService

    source = inspect.getsource(JournalService._build_context_summary)
    assert _SESSION not in source, (
        "_build_context_summary references ConversationSession — the journal "
        "context builder must never read the discussion store (ADR-078 §2)."
    )
    assert _TURN not in source


def test_vault_context_read_does_not_reference_conversation_labels() -> None:
    from adapters.persistence.neo4j._user_entry_content_mixin import _UserEntryContentMixin

    source = inspect.getsource(_UserEntryContentMixin.get_vault_notes_for_context)
    assert _SESSION not in source and _TURN not in source, (
        "get_vault_notes_for_context references a conversation label — the "
        "doorway/periodic read is the ONLY channel into context (ADR-078 §2)."
    )
