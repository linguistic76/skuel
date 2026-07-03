"""Tests for TaskTemplate domain model + DTO."""

from __future__ import annotations

import json

import pytest

from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.metadata_enums import Visibility
from core.models.templates import RelativeOffset
from core.models.templates.task_template import TaskTemplate
from core.models.templates.task_template_dto import TaskTemplateDTO


class TestTaskTemplateConstruction:
    """Frozen dataclass construction + entity-type forcing + defaults."""

    def test_basic_construction(self):
        tt = TaskTemplate(uid="ttpl_basic", title="Practice integration")
        assert tt.uid == "ttpl_basic"
        assert tt.title == "Practice integration"
        assert tt.entity_type == EntityType.TASK_TEMPLATE
        assert tt.due_offset is None
        assert tt.fulfills_goal_template_uid is None
        assert tt.goal_progress_contribution == 0.0

    def test_entity_type_mismatch_raises(self):
        """G6: a wrong entity_type fails loudly instead of being silently corrected."""
        with pytest.raises(ValueError, match="entity_type"):
            TaskTemplate(uid="ttpl_force", title="Coerce", entity_type=EntityType.TASK)

    def test_default_status_is_draft(self):
        tt = TaskTemplate(uid="ttpl_status", title="t")
        assert tt.status == EntityStatus.DRAFT

    def test_default_visibility_public(self):
        """Templates are shared content; visibility defaults to PUBLIC like FormTemplate."""
        tt = TaskTemplate(uid="ttpl_vis", title="t")
        assert tt.visibility == Visibility.PUBLIC

    def test_offset_fields_carry_relative_offset(self):
        tt = TaskTemplate(
            uid="ttpl_off",
            title="t",
            due_offset=RelativeOffset(days=7),
            scheduled_offset=RelativeOffset(days=2, hours=10),
            recurrence_end_offset=RelativeOffset(days=30),
        )
        assert tt.due_offset == RelativeOffset(days=7)
        assert tt.scheduled_offset == RelativeOffset(days=2, hours=10)
        assert tt.recurrence_end_offset == RelativeOffset(days=30)

    def test_cross_template_refs(self):
        tt = TaskTemplate(
            uid="ttpl_xref",
            title="t",
            fulfills_goal_template_uid="gtpl_x",
            reinforces_habit_template_uid="htpl_y",
            scheduled_event_template_uid="etpl_z",
            parent_template_uid="ttpl_parent",
        )
        assert tt.fulfills_goal_template_uid == "gtpl_x"
        assert tt.reinforces_habit_template_uid == "htpl_y"
        assert tt.scheduled_event_template_uid == "etpl_z"
        assert tt.parent_template_uid == "ttpl_parent"

    def test_frozen_immutability(self):
        tt = TaskTemplate(uid="ttpl_im", title="t")
        try:
            tt.title = "changed"  # type: ignore[misc]
        except Exception as exc:
            assert "frozen" in str(exc).lower() or "cannot assign" in str(exc).lower()
        else:
            raise AssertionError("Frozen dataclass should reject attribute assignment")


class TestTaskTemplateConversion:
    """Round-trip between TaskTemplate (frozen) and TaskTemplateDTO (mutable)."""

    def test_to_dto(self):
        tt = TaskTemplate(
            uid="ttpl_dto1",
            title="t",
            due_offset=RelativeOffset(days=7),
            duration_minutes=30,
            fulfills_goal_template_uid="gtpl_x",
            knowledge_mastery_check=True,
        )
        dto = tt.to_dto()
        assert isinstance(dto, TaskTemplateDTO)
        assert dto.uid == "ttpl_dto1"
        assert dto.due_offset == RelativeOffset(days=7)
        assert dto.duration_minutes == 30
        assert dto.fulfills_goal_template_uid == "gtpl_x"
        assert dto.knowledge_mastery_check is True

    def test_from_dto(self):
        dto = TaskTemplateDTO(
            uid="ttpl_dto2",
            title="t",
            scheduled_offset=RelativeOffset(days=1),
            project="prj-1",
        )
        tt = TaskTemplate._from_dto(dto)
        assert tt.uid == "ttpl_dto2"
        assert tt.entity_type == EntityType.TASK_TEMPLATE
        assert tt.scheduled_offset == RelativeOffset(days=1)
        assert tt.project == "prj-1"

    def test_dto_roundtrip_preserves_offset_fields(self):
        original = TaskTemplate(
            uid="ttpl_rt",
            title="t",
            due_offset=RelativeOffset(days=7),
            scheduled_offset=RelativeOffset(days=1, hours=12),
            recurrence_end_offset=RelativeOffset(days=30),
        )
        roundtripped = TaskTemplate._from_dto(original.to_dto())
        assert roundtripped.due_offset == original.due_offset
        assert roundtripped.scheduled_offset == original.scheduled_offset
        assert roundtripped.recurrence_end_offset == original.recurrence_end_offset


class TestTaskTemplateDTOSerialization:
    """to_dict / from_dict for the Neo4j boundary."""

    def test_to_dict_serializes_offsets_as_json_strings(self):
        dto = TaskTemplateDTO(
            uid="ttpl_ser",
            title="t",
            due_offset=RelativeOffset(days=7),
        )
        data = dto.to_dict()
        assert data["uid"] == "ttpl_ser"
        assert isinstance(data["due_offset"], str)
        parsed = json.loads(data["due_offset"])
        assert parsed == {"days": 7, "hours": 0, "minutes": 0}
        # Untouched offset fields serialize as None
        assert data["scheduled_offset"] is None
        assert data["recurrence_end_offset"] is None

    def test_from_dict_parses_offset_json_string(self):
        data = {
            "uid": "ttpl_de",
            "title": "t",
            "due_offset": json.dumps({"days": 7, "hours": 0, "minutes": 0}),
            "scheduled_offset": None,
            "recurrence_end_offset": None,
        }
        dto = TaskTemplateDTO.from_dict(data)
        assert dto.uid == "ttpl_de"
        assert dto.due_offset == RelativeOffset(days=7)
        assert dto.scheduled_offset is None
        assert dto.recurrence_end_offset is None

    def test_from_dict_accepts_dict_payload_for_offset(self):
        """Round-trip through asdict() (dict, not JSON string) should also parse."""
        data = {
            "uid": "ttpl_dict_off",
            "title": "t",
            "due_offset": {"days": 3, "hours": 0, "minutes": 0},
        }
        dto = TaskTemplateDTO.from_dict(data)
        assert dto.due_offset == RelativeOffset(days=3)

    def test_from_dict_accepts_invalid_offset_as_none(self):
        data = {"uid": "ttpl_bad", "title": "t", "due_offset": "not json"}
        dto = TaskTemplateDTO.from_dict(data)
        assert dto.due_offset is None


class TestTaskTemplateDTOUpdate:
    def test_update_from_with_offset_dict(self):
        dto = TaskTemplateDTO(uid="ttpl_up", title="t")
        dto.update_from(
            {
                "title": "renamed",
                "due_offset": {"days": 5, "hours": 0, "minutes": 0},
                "knowledge_mastery_check": True,
            }
        )
        assert dto.title == "renamed"
        assert dto.due_offset == RelativeOffset(days=5)
        assert dto.knowledge_mastery_check is True

    def test_update_from_passes_relative_offset_through(self):
        dto = TaskTemplateDTO(uid="ttpl_up2", title="t")
        dto.update_from({"due_offset": RelativeOffset(days=2)})
        assert dto.due_offset == RelativeOffset(days=2)


class TestTaskTemplateEntityTypeTraits:
    """EntityType-level traits for TASK_TEMPLATE (Phase 1 wiring)."""

    def test_template_is_shared(self):
        assert not EntityType.TASK_TEMPLATE.requires_user_uid()

    def test_template_default_status_is_draft(self):
        assert EntityType.TASK_TEMPLATE.default_status() == EntityStatus.DRAFT

    def test_from_string(self):
        assert EntityType.from_string("task_template") == EntityType.TASK_TEMPLATE
