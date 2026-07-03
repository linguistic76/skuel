"""Tests for ChoiceTemplate domain model + DTO."""

from __future__ import annotations

import json

import pytest

from core.models.choice.choice_option import ChoiceOption
from core.models.enums.choice_enums import ChoiceType
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.metadata_enums import Visibility
from core.models.templates import RelativeOffset
from core.models.templates.choice_template import ChoiceTemplate
from core.models.templates.choice_template_dto import ChoiceTemplateDTO


class TestChoiceTemplateConstruction:
    def test_basic_construction(self):
        ct = ChoiceTemplate(uid="ctpl_basic", title="Pick a path")
        assert ct.entity_type == EntityType.CHOICE_TEMPLATE
        assert ct.options == ()
        assert ct.expands_possibilities is False

    def test_entity_type_mismatch_raises(self):
        """G6: a wrong entity_type fails loudly instead of being silently corrected."""
        with pytest.raises(ValueError, match="entity_type"):
            ChoiceTemplate(uid="ctpl_force", title="x", entity_type=EntityType.CHOICE)

    def test_default_status_is_draft(self):
        assert ChoiceTemplate(uid="ctpl_s", title="t").status == EntityStatus.DRAFT

    def test_default_visibility_public(self):
        assert ChoiceTemplate(uid="ctpl_v", title="t").visibility == Visibility.PUBLIC

    def test_options_and_decision_frame(self):
        ct = ChoiceTemplate(
            uid="ctpl_opt",
            title="t",
            choice_type=ChoiceType.BINARY,
            options=(
                ChoiceOption(uid="opt_a", title="Option A"),
                ChoiceOption(uid="opt_b", title="Option B"),
            ),
            decision_criteria=("clarity", "feasibility"),
        )
        assert ct.choice_type == ChoiceType.BINARY
        assert len(ct.options) == 2
        assert ct.options[0].uid == "opt_a"
        assert ct.decision_criteria == ("clarity", "feasibility")

    def test_offset_field(self):
        ct = ChoiceTemplate(
            uid="ctpl_off",
            title="t",
            decision_deadline_offset=RelativeOffset(days=3),
        )
        assert ct.decision_deadline_offset == RelativeOffset(days=3)


class TestChoiceTemplateConversion:
    def test_dto_roundtrip_preserves_offset(self):
        original = ChoiceTemplate(
            uid="ctpl_rt",
            title="t",
            decision_deadline_offset=RelativeOffset(days=3),
            decision_criteria=("a", "b"),
            stakeholders=("self", "team"),
        )
        rt = ChoiceTemplate._from_dto(original.to_dto())
        assert rt.decision_deadline_offset == RelativeOffset(days=3)
        assert rt.decision_criteria == ("a", "b")
        assert rt.stakeholders == ("self", "team")


class TestChoiceTemplateDTOSerialization:
    def test_to_dict_offset_as_json(self):
        dto = ChoiceTemplateDTO(
            uid="ctpl_ser",
            title="t",
            decision_deadline_offset=RelativeOffset(days=3),
        )
        data = dto.to_dict()
        assert json.loads(data["decision_deadline_offset"])["days"] == 3

    def test_from_dict_offset_parses(self):
        dto = ChoiceTemplateDTO.from_dict(
            {
                "uid": "ctpl_de",
                "title": "t",
                "decision_deadline_offset": json.dumps({"days": 5, "hours": 0, "minutes": 0}),
            }
        )
        assert dto.decision_deadline_offset == RelativeOffset(days=5)
