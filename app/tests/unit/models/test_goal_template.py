"""Tests for GoalTemplate domain model + DTO."""

from __future__ import annotations

import pytest

import json

from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.goal_enums import GoalTimeframe, GoalType, MeasurementType
from core.models.enums.metadata_enums import Visibility
from core.models.templates import RelativeOffset
from core.models.templates.goal_template import GoalTemplate
from core.models.templates.goal_template_dto import GoalTemplateDTO


class TestGoalTemplateConstruction:
    def test_basic_construction(self):
        gt = GoalTemplate(uid="gtpl_basic", title="Master integration")
        assert gt.uid == "gtpl_basic"
        assert gt.entity_type == EntityType.GOAL_TEMPLATE
        assert gt.target_value is None
        assert gt.start_offset is None

    def test_entity_type_mismatch_raises(self):
        """G6: a wrong entity_type fails loudly instead of being silently corrected."""
        with pytest.raises(ValueError, match="entity_type"):
            GoalTemplate(uid="gtpl_force", title="x", entity_type=EntityType.GOAL)

    def test_default_status_is_draft(self):
        assert GoalTemplate(uid="gtpl_s", title="t").status == EntityStatus.DRAFT

    def test_default_visibility_public(self):
        assert GoalTemplate(uid="gtpl_v", title="t").visibility == Visibility.PUBLIC

    def test_classification_fields(self):
        gt = GoalTemplate(
            uid="gtpl_cl",
            title="t",
            goal_type=GoalType.OUTCOME,
            timeframe=GoalTimeframe.QUARTERLY,
            measurement_type=MeasurementType.NUMERIC,
        )
        assert gt.goal_type == GoalType.OUTCOME
        assert gt.timeframe == GoalTimeframe.QUARTERLY
        assert gt.measurement_type == MeasurementType.NUMERIC

    def test_offset_fields(self):
        gt = GoalTemplate(
            uid="gtpl_off",
            title="t",
            start_offset=RelativeOffset(days=0),
            target_offset=RelativeOffset(days=90),
        )
        assert gt.start_offset == RelativeOffset(days=0)
        assert gt.target_offset == RelativeOffset(days=90)

    def test_cross_template_refs(self):
        gt = GoalTemplate(
            uid="gtpl_x",
            title="t",
            fulfills_goal_template_uid="gtpl_parent",
            inspired_by_choice_template_uid="ctpl_x",
            selected_choice_option_template_uid="opt_y",
        )
        assert gt.fulfills_goal_template_uid == "gtpl_parent"
        assert gt.inspired_by_choice_template_uid == "ctpl_x"
        assert gt.selected_choice_option_template_uid == "opt_y"


class TestGoalTemplateConversion:
    def test_dto_roundtrip(self):
        original = GoalTemplate(
            uid="gtpl_rt",
            title="t",
            target_value=100.0,
            start_offset=RelativeOffset(days=0),
            target_offset=RelativeOffset(days=90),
            potential_obstacles=("a", "b"),
            strategies=("x",),
        )
        rt = GoalTemplate._from_dto(original.to_dto())
        assert rt.target_value == 100.0
        assert rt.start_offset == original.start_offset
        assert rt.target_offset == original.target_offset
        assert rt.potential_obstacles == ("a", "b")
        assert rt.strategies == ("x",)


class TestGoalTemplateDTOSerialization:
    def test_to_dict_serializes_offsets_as_json(self):
        dto = GoalTemplateDTO(
            uid="gtpl_ser",
            title="t",
            target_offset=RelativeOffset(days=30),
        )
        data = dto.to_dict()
        assert data["start_offset"] is None
        assert isinstance(data["target_offset"], str)
        assert json.loads(data["target_offset"])["days"] == 30

    def test_from_dict_parses_offsets(self):
        dto = GoalTemplateDTO.from_dict(
            {
                "uid": "gtpl_de",
                "title": "t",
                "start_offset": json.dumps({"days": 0, "hours": 0, "minutes": 0}),
                "target_offset": json.dumps({"days": 60, "hours": 0, "minutes": 0}),
            }
        )
        assert dto.start_offset == RelativeOffset(days=0)
        assert dto.target_offset == RelativeOffset(days=60)
