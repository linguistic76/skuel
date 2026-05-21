"""Tests for PrincipleTemplate domain model + DTO."""

from __future__ import annotations

from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.metadata_enums import Visibility
from core.models.enums.principle_enums import (
    PrincipleCategory,
    PrincipleSource,
    PrincipleStrength,
)
from core.models.principle.principle_types import PrincipleExpression
from core.models.templates.principle_template import PrincipleTemplate
from core.models.templates.principle_template_dto import PrincipleTemplateDTO


class TestPrincipleTemplateConstruction:
    def test_basic_construction(self):
        pt = PrincipleTemplate(uid="ptpl_basic", title="Honesty")
        assert pt.entity_type == EntityType.PRINCIPLE_TEMPLATE
        assert pt.statement is None
        assert pt.expressions == ()

    def test_entity_type_forced(self):
        pt = PrincipleTemplate(uid="ptpl_force", title="x", entity_type=EntityType.PRINCIPLE)
        assert pt.entity_type == EntityType.PRINCIPLE_TEMPLATE

    def test_default_status_is_draft(self):
        assert PrincipleTemplate(uid="ptpl_s", title="t").status == EntityStatus.DRAFT

    def test_default_visibility_public(self):
        assert PrincipleTemplate(uid="ptpl_v", title="t").visibility == Visibility.PUBLIC

    def test_classification_and_philosophy(self):
        pt = PrincipleTemplate(
            uid="ptpl_p",
            title="Honesty",
            statement="Always speak truth",
            principle_category=PrincipleCategory.ETHICAL,
            principle_source=PrincipleSource.PHILOSOPHICAL,
            strength=PrincipleStrength.CORE,
            tradition="Stoicism",
            key_behaviors=("Speak plainly", "Don't deceive"),
        )
        assert pt.statement == "Always speak truth"
        assert pt.principle_category == PrincipleCategory.ETHICAL
        assert pt.strength == PrincipleStrength.CORE
        assert pt.key_behaviors == ("Speak plainly", "Don't deceive")

    def test_expressions(self):
        pt = PrincipleTemplate(
            uid="ptpl_e",
            title="Honesty",
            expressions=(
                PrincipleExpression(context="work", behavior="give direct feedback"),
                PrincipleExpression(context="family", behavior="don't hide difficult news"),
            ),
        )
        assert len(pt.expressions) == 2
        assert pt.expressions[0].context == "work"


class TestPrincipleTemplateConversion:
    def test_dto_roundtrip(self):
        original = PrincipleTemplate(
            uid="ptpl_rt",
            title="Honesty",
            statement="Always speak truth",
            principle_category=PrincipleCategory.ETHICAL,
            potential_conflicts=("efficiency",),
            resolution_strategies=("favor truth over speed",),
        )
        rt = PrincipleTemplate._from_dto(original.to_dto())
        assert rt.statement == "Always speak truth"
        assert rt.principle_category == PrincipleCategory.ETHICAL
        assert rt.potential_conflicts == ("efficiency",)
        assert rt.resolution_strategies == ("favor truth over speed",)


class TestPrincipleTemplateDTOSerialization:
    def test_to_dict_basic(self):
        dto = PrincipleTemplateDTO(
            uid="ptpl_ser",
            title="t",
            principle_category=PrincipleCategory.ETHICAL,
        )
        data = dto.to_dict()
        assert data["principle_category"] == PrincipleCategory.ETHICAL.value

    def test_from_dict_basic(self):
        dto = PrincipleTemplateDTO.from_dict(
            {
                "uid": "ptpl_de",
                "title": "t",
                "principle_category": "ethical",
                "key_behaviors": ["a", "b"],
            }
        )
        assert dto.principle_category == PrincipleCategory.ETHICAL
        assert dto.key_behaviors == ["a", "b"]
