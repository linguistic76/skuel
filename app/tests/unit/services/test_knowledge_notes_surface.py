"""Knowledge chips — ``/submissions/knowledge`` and ``/journals/{uid}``.

Covers the read path behind ``/submissions/knowledge`` (service delegation
to the backend grounding-list query), the narrowing of collected chips, and
the chip renderer contract: an inferred chip shows its confidence and a remove
button that calls the remove route with both uids; a chip the owner named
shows neither; a PathStep chip opens its own reading page.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import to_xml

from core.models.enums.entity_enums import EntityType
from core.ports.query_types import (
    KnowledgeChip,
    KnowledgeEntryGroundingRow,
    to_knowledge_entry_grounding_rows,
)
from core.services.user_entry.user_entry_service import UserEntryService
from core.utils.result_simplified import Errors, Result
from ui.user_entry.knowledge_notes import EntryKnowledgeChips, render_knowledge_notes_list


def _make_service(backend: MagicMock) -> UserEntryService:
    return UserEntryService(backend=backend)


_EXPLICIT_CHIP = KnowledgeChip(
    uid="ku.mind.explicit",
    title="Explicit Ref",
    entity_type=EntityType.KU,
    confidence=None,
    inferred=None,
)
_INFERRED_CHIP = KnowledgeChip(
    uid="ku.mind.sel", title="Sel", entity_type=EntityType.KU, confidence=0.81, inferred=True
)
_PATH_STEP_CHIP = KnowledgeChip(
    uid="ps.mind.step",
    title="Step",
    entity_type=EntityType.PATH_STEP,
    confidence=None,
    inferred=None,
)


def _row(chips: list[KnowledgeChip] | None = None) -> KnowledgeEntryGroundingRow:
    return KnowledgeEntryGroundingRow(
        uid="ue_note_1",
        title="Mindfulness note",
        created_at="2026-07-10T09:00:00",
        chips=chips if chips is not None else [_INFERRED_CHIP, _EXPLICIT_CHIP],
    )


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


class TestToKnowledgeEntryGroundingRows:
    """Raw Neo4j records narrow to typed rows (Codex #611: no Any across the boundary)."""

    def test_narrows_and_casts(self):
        rows = to_knowledge_entry_grounding_rows(
            [
                {
                    "uid": "ue_1",
                    "title": "Note",
                    "created_at": "2026-07-10T09:00:00",
                    "chips": [
                        {
                            "uid": "ku.a",
                            "title": "A",
                            "entity_type": "ku",
                            "confidence": 0.9,
                            "inferred": True,
                        },
                        {
                            "uid": None,
                            "title": "uid-less chip dropped",
                            "entity_type": "ku",
                            "confidence": None,
                            "inferred": None,
                        },
                        {
                            "uid": "x.a",
                            "title": "unknown kind dropped",
                            "entity_type": "not_a_type",
                            "confidence": None,
                            "inferred": None,
                        },
                    ],
                },
                {"uid": None, "title": "uid-less row dropped"},
            ]
        )
        assert len(rows) == 1
        assert rows[0]["uid"] == "ue_1"
        assert len(rows[0]["chips"]) == 1
        chip = rows[0]["chips"][0]
        assert chip["entity_type"] is EntityType.KU
        assert chip["confidence"] == 0.9
        assert chip["inferred"] is True

    def test_explicit_chip_keeps_none_confidence(self):
        rows = to_knowledge_entry_grounding_rows(
            [
                {
                    "uid": "ue_1",
                    "title": None,
                    "created_at": None,
                    "chips": [
                        {
                            "uid": "ps.a",
                            "title": None,
                            "entity_type": "path_step",
                            "confidence": None,
                            "inferred": None,
                        }
                    ],
                }
            ]
        )
        chip = rows[0]["chips"][0]
        assert chip["entity_type"] is EntityType.PATH_STEP
        assert chip["confidence"] is None
        assert chip["inferred"] is None
        assert rows[0]["title"] is None


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
        row = _row(chips=[_EXPLICIT_CHIP])
        html = to_xml(render_knowledge_notes_list([row]))
        assert "%" not in html.split("Explicit Ref")[1].split("</span>")[0]
        assert "Explicit Ref" in html

    def test_chip_links_to_ku_reading_page(self):
        html = to_xml(render_knowledge_notes_list([_row()]))
        assert 'href="/explore/ku/ku.mind.sel"' in html

    def test_entry_without_chips_shows_muted_note(self):
        html = to_xml(render_knowledge_notes_list([_row(chips=[])]))
        assert "No grounded concepts yet." in html

    def test_empty_rows_render_empty_state(self):
        html = to_xml(render_knowledge_notes_list([]))
        assert "No knowledge notes yet" in html

    def test_only_an_inferred_chip_can_be_removed(self):
        html = to_xml(render_knowledge_notes_list([_row([_EXPLICIT_CHIP, _PATH_STEP_CHIP])]))

        assert "grounding/remove" not in html
        # Control: the inferred chip carries the remove button.
        assert "grounding/remove" in to_xml(render_knowledge_notes_list([_row([_INFERRED_CHIP])]))

    def test_a_path_step_chip_opens_its_reading_page(self):
        html = to_xml(render_knowledge_notes_list([_row([_PATH_STEP_CHIP])]))
        assert 'href="/explore/ps/ps.mind.step"' in html


class TestEntryKnowledgeChips:
    """The section under a periodic note's editor."""

    def test_renders_each_chip(self):
        html = to_xml(EntryKnowledgeChips("ue_note_1", [_INFERRED_CHIP, _PATH_STEP_CHIP]))
        assert "Knowledge in this note" in html
        assert "/api/user-entries/grounding/remove?uid=ue_note_1&amp;ku_uid=ku.mind.sel" in html
        assert 'href="/explore/ps/ps.mind.step"' in html

    def test_no_links_renders_nothing(self):
        assert EntryKnowledgeChips("ue_note_1", []) is None

    def test_a_failed_read_says_so(self):
        html = to_xml(EntryKnowledgeChips("ue_note_1", None))
        assert "Could not load this note's knowledge links." in html
