"""Knowledge-notes surface (Entry-Enrichment PR 4).

Covers the read path behind ``/submissions/knowledge`` (service delegation
to the backend grounding-list query) and the chip renderer contract: the
per-chip remove button must call PR 3's remove route with both uids, inferred chips
show confidence, explicit chips (no ``confidence`` property) don't.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import to_xml

from core.services.user_entry.user_entry_service import UserEntryService
from core.utils.result_simplified import Errors, Result
from ui.user_entry.knowledge_notes import render_knowledge_notes_list


def _make_service(backend: MagicMock) -> UserEntryService:
    return UserEntryService(backend=backend)


def _row(**overrides) -> dict:
    row = {
        "uid": "ue_note_1",
        "title": "Mindfulness note",
        "created_at": "2026-07-10T09:00:00",
        "grounded_kus": [
            {
                "ku_uid": "ku.mind.sel",
                "ku_title": "Sel",
                "confidence": 0.81,
                "inferred": True,
            },
            {
                "ku_uid": "ku.mind.explicit",
                "ku_title": "Explicit Ref",
                "confidence": None,
                "inferred": None,
            },
        ],
    }
    row.update(overrides)
    return row


class TestListKnowledgeEntriesWithGrounding:
    """Service delegation to the backend grounding-list query."""

    @pytest.mark.asyncio
    async def test_delegates_and_returns_rows(self):
        backend = MagicMock()
        backend.get_knowledge_entries_with_grounding = AsyncMock(return_value=Result.ok([_row()]))
        service = _make_service(backend)

        result = await service.list_knowledge_entries_with_grounding("user_1", limit=42)

        assert result.is_ok
        assert result.value[0]["uid"] == "ue_note_1"
        backend.get_knowledge_entries_with_grounding.assert_awaited_once_with("user_1", 42)

    @pytest.mark.asyncio
    async def test_propagates_backend_error(self):
        backend = MagicMock()
        backend.get_knowledge_entries_with_grounding = AsyncMock(
            return_value=Result.fail(Errors.database("q", "boom"))
        )
        service = _make_service(backend)

        result = await service.list_knowledge_entries_with_grounding("user_1")

        assert result.is_error

    @pytest.mark.asyncio
    async def test_none_value_normalizes_to_empty_list(self):
        backend = MagicMock()
        backend.get_knowledge_entries_with_grounding = AsyncMock(return_value=Result.ok(None))
        service = _make_service(backend)

        result = await service.list_knowledge_entries_with_grounding("user_1")

        assert result.is_ok
        assert result.value == []


class TestKnowledgeNotesRenderer:
    """Chip contract: remove route wiring + confidence display."""

    def test_chip_wires_remove_route_with_both_uids(self):
        html = to_xml(render_knowledge_notes_list([_row()]))
        assert "/api/user-entries/grounding/remove?uid=ue_note_1&amp;ku_uid=ku.mind.sel" in html
        assert 'hx-swap="none"' in html
        assert "data-grounding-chip" in html

    def test_inferred_chip_shows_confidence_percent(self):
        html = to_xml(render_knowledge_notes_list([_row()]))
        assert "81%" in html

    def test_explicit_chip_shows_no_percent(self):
        row = _row(
            grounded_kus=[
                {
                    "ku_uid": "ku.mind.explicit",
                    "ku_title": "Explicit Ref",
                    "confidence": None,
                    "inferred": None,
                }
            ]
        )
        html = to_xml(render_knowledge_notes_list([row]))
        assert "%" not in html.split("Explicit Ref")[1].split("</span>")[0]
        assert "Explicit Ref" in html

    def test_chip_links_to_ku_reading_page(self):
        html = to_xml(render_knowledge_notes_list([_row()]))
        assert 'href="/explore/ku/ku.mind.sel"' in html

    def test_entry_without_chips_shows_muted_note(self):
        html = to_xml(render_knowledge_notes_list([_row(grounded_kus=[])]))
        assert "No grounded concepts yet." in html

    def test_empty_rows_render_empty_state(self):
        html = to_xml(render_knowledge_notes_list([]))
        assert "No knowledge notes yet" in html
