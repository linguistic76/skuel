"""Tests for HabitTemplate domain model + DTO."""

from __future__ import annotations

import json

from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.habit_enums import HabitCategory, HabitDifficulty, HabitPolarity
from core.models.enums.metadata_enums import Visibility
from core.models.templates import RelativeOffset
from core.models.templates.habit_template import HabitTemplate
from core.models.templates.habit_template_dto import HabitTemplateDTO


class TestHabitTemplateConstruction:
    def test_basic_construction(self):
        ht = HabitTemplate(uid="htpl_basic", title="Daily review")
        assert ht.entity_type == EntityType.HABIT_TEMPLATE
        assert ht.recurrence_end_offset is None
        assert ht.is_identity_habit is False

    def test_entity_type_forced(self):
        ht = HabitTemplate(uid="htpl_force", title="x", entity_type=EntityType.HABIT)
        assert ht.entity_type == EntityType.HABIT_TEMPLATE

    def test_default_status_is_draft(self):
        assert HabitTemplate(uid="htpl_s", title="t").status == EntityStatus.DRAFT

    def test_default_visibility_public(self):
        assert HabitTemplate(uid="htpl_v", title="t").visibility == Visibility.PUBLIC

    def test_classification_and_behavior_design(self):
        ht = HabitTemplate(
            uid="htpl_b",
            title="Read every day",
            polarity=HabitPolarity.BUILD,
            habit_category=HabitCategory.HEALTH,
            habit_difficulty=HabitDifficulty.EASY,
            cue="After breakfast",
            routine="Read 10 pages",
            reward="Coffee",
        )
        assert ht.polarity == HabitPolarity.BUILD
        assert ht.habit_category == HabitCategory.HEALTH
        assert ht.cue == "After breakfast"
        assert ht.routine == "Read 10 pages"
        assert ht.reward == "Coffee"

    def test_offset_field(self):
        ht = HabitTemplate(
            uid="htpl_off",
            title="t",
            recurrence_end_offset=RelativeOffset(days=60),
        )
        assert ht.recurrence_end_offset == RelativeOffset(days=60)


class TestHabitTemplateConversion:
    def test_dto_roundtrip(self):
        original = HabitTemplate(
            uid="htpl_rt",
            title="t",
            polarity=HabitPolarity.BUILD,
            recurrence_end_offset=RelativeOffset(days=30),
            target_days_per_week=5,
            reminder_days=("mon", "wed", "fri"),
        )
        rt = HabitTemplate._from_dto(original.to_dto())
        assert rt.polarity == HabitPolarity.BUILD
        assert rt.recurrence_end_offset == RelativeOffset(days=30)
        assert rt.target_days_per_week == 5
        assert rt.reminder_days == ("mon", "wed", "fri")


class TestHabitTemplateDTOSerialization:
    def test_to_dict_offset_as_json(self):
        dto = HabitTemplateDTO(
            uid="htpl_ser",
            title="t",
            recurrence_end_offset=RelativeOffset(days=14),
        )
        data = dto.to_dict()
        assert isinstance(data["recurrence_end_offset"], str)
        assert json.loads(data["recurrence_end_offset"])["days"] == 14

    def test_from_dict_offset_parses(self):
        dto = HabitTemplateDTO.from_dict(
            {
                "uid": "htpl_de",
                "title": "t",
                "recurrence_end_offset": json.dumps({"days": 7, "hours": 0, "minutes": 0}),
            }
        )
        assert dto.recurrence_end_offset == RelativeOffset(days=7)
