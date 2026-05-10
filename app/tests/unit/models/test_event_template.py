"""Tests for EventTemplate domain model + DTO."""

from __future__ import annotations

import json
from datetime import time

from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.metadata_enums import Visibility
from core.models.templates import RelativeOffset
from core.models.templates.event_template import EventTemplate
from core.models.templates.event_template_dto import EventTemplateDTO


class TestEventTemplateConstruction:
    def test_basic_construction(self):
        et = EventTemplate(uid="etpl_basic", title="Weekly review")
        assert et.entity_type == EntityType.EVENT_TEMPLATE
        assert et.event_offset is None
        assert et.is_online is False
        assert et.is_milestone_event is False

    def test_entity_type_forced(self):
        et = EventTemplate(uid="etpl_force", title="x", entity_type=EntityType.EVENT)
        assert et.entity_type == EntityType.EVENT_TEMPLATE

    def test_default_status_for_event_template(self):
        # _TEMPLATE_STATUSES allows DRAFT; default is DRAFT (not SCHEDULED like Event)
        assert EventTemplate(uid="etpl_s", title="t").status == EntityStatus.DRAFT

    def test_default_visibility_public(self):
        assert EventTemplate(uid="etpl_v", title="t").visibility == Visibility.PUBLIC

    def test_offset_and_time_fields(self):
        et = EventTemplate(
            uid="etpl_off",
            title="t",
            event_offset=RelativeOffset(days=14),
            start_time=time(16, 0),
            end_time=time(17, 0),
            duration_minutes=60,
        )
        assert et.event_offset == RelativeOffset(days=14)
        assert et.start_time == time(16, 0)
        assert et.end_time == time(17, 0)

    def test_cross_template_refs(self):
        et = EventTemplate(
            uid="etpl_x",
            title="t",
            reinforces_habit_template_uid="htpl_x",
            milestone_celebration_for_goal_template_uid="gtpl_y",
        )
        assert et.reinforces_habit_template_uid == "htpl_x"
        assert et.milestone_celebration_for_goal_template_uid == "gtpl_y"


class TestEventTemplateConversion:
    def test_dto_roundtrip(self):
        original = EventTemplate(
            uid="etpl_rt",
            title="t",
            event_offset=RelativeOffset(days=14),
            recurrence_end_offset=RelativeOffset(days=90),
            start_time=time(9, 30),
            location="Online",
            is_online=True,
        )
        rt = EventTemplate._from_dto(original.to_dto())
        assert rt.event_offset == original.event_offset
        assert rt.recurrence_end_offset == original.recurrence_end_offset
        assert rt.start_time == time(9, 30)
        assert rt.is_online is True


class TestEventTemplateDTOSerialization:
    def test_to_dict_offsets_as_json(self):
        dto = EventTemplateDTO(
            uid="etpl_ser",
            title="t",
            event_offset=RelativeOffset(days=14),
            recurrence_end_offset=RelativeOffset(days=60),
        )
        data = dto.to_dict()
        assert json.loads(data["event_offset"])["days"] == 14
        assert json.loads(data["recurrence_end_offset"])["days"] == 60

    def test_from_dict_offsets_parse(self):
        dto = EventTemplateDTO.from_dict(
            {
                "uid": "etpl_de",
                "title": "t",
                "event_offset": json.dumps({"days": 7, "hours": 0, "minutes": 0}),
                "recurrence_end_offset": None,
                "start_time": "09:30:00",
            }
        )
        assert dto.event_offset == RelativeOffset(days=7)
        assert dto.start_time == time(9, 30)
