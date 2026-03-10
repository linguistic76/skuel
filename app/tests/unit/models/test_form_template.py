"""Tests for FormTemplate domain model."""

import json

from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.metadata_enums import Visibility
from core.models.forms.form_template import FormTemplate
from core.models.forms.form_template_dto import FormTemplateDTO


class TestFormTemplateConstruction:
    """Test FormTemplate frozen dataclass construction."""

    def test_basic_construction(self):
        ft = FormTemplate(
            uid="ft_test_123",
            title="Feedback Form",
            form_schema=[{"name": "q1", "type": "text", "label": "Question 1"}],
        )
        assert ft.uid == "ft_test_123"
        assert ft.title == "Feedback Form"
        assert ft.entity_type == EntityType.FORM_TEMPLATE
        assert ft.form_schema is not None
        assert len(ft.form_schema) == 1
        assert ft.form_schema[0]["name"] == "q1"

    def test_entity_type_forced(self):
        """entity_type is always FORM_TEMPLATE regardless of input."""
        ft = FormTemplate(
            uid="ft_test_456",
            title="Test",
            entity_type=EntityType.TASK,  # Wrong type — should be overridden
        )
        assert ft.entity_type == EntityType.FORM_TEMPLATE

    def test_default_status(self):
        ft = FormTemplate(uid="ft_test_789", title="Test")
        assert ft.status == EntityStatus.DRAFT

    def test_default_visibility_public(self):
        """FormTemplate is shared content — default visibility is PUBLIC."""
        ft = FormTemplate(uid="ft_test_pub", title="Test")
        assert ft.visibility == Visibility.PUBLIC

    def test_form_schema_from_json_string(self):
        """form_schema can be a JSON string (from Neo4j)."""
        schema_json = json.dumps([{"name": "q1", "type": "text", "label": "Q1"}])
        ft = FormTemplate(uid="ft_json", title="Test", form_schema=schema_json)
        assert isinstance(ft.form_schema, tuple)
        assert ft.form_schema[0]["name"] == "q1"

    def test_form_schema_from_list(self):
        """form_schema list gets converted to tuple (frozen)."""
        ft = FormTemplate(
            uid="ft_list",
            title="Test",
            form_schema=[{"name": "q1", "type": "text", "label": "Q1"}],
        )
        assert isinstance(ft.form_schema, tuple)

    def test_form_schema_invalid_json(self):
        """Invalid JSON string results in None form_schema."""
        ft = FormTemplate(uid="ft_bad", title="Test", form_schema="not json")
        assert ft.form_schema is None

    def test_form_schema_none(self):
        ft = FormTemplate(uid="ft_none", title="Test")
        assert ft.form_schema is None


class TestFormTemplateQueries:
    def test_has_form_schema(self):
        ft = FormTemplate(
            uid="ft_1",
            title="Test",
            form_schema=[{"name": "q1", "type": "text", "label": "Q1"}],
        )
        assert ft.has_form_schema() is True

    def test_has_form_schema_empty(self):
        ft = FormTemplate(uid="ft_2", title="Test", form_schema=())
        assert ft.has_form_schema() is False

    def test_has_form_schema_none(self):
        ft = FormTemplate(uid="ft_3", title="Test")
        assert ft.has_form_schema() is False

    def test_is_valid(self):
        ft = FormTemplate(
            uid="ft_4",
            title="Test",
            form_schema=[{"name": "q1", "type": "text", "label": "Q1"}],
        )
        assert ft.is_valid() is True

    def test_is_valid_no_title(self):
        ft = FormTemplate(
            uid="ft_5",
            title="",
            form_schema=[{"name": "q1", "type": "text", "label": "Q1"}],
        )
        assert ft.is_valid() is False

    def test_is_valid_no_schema(self):
        ft = FormTemplate(uid="ft_6", title="Test")
        assert ft.is_valid() is False


class TestFormTemplateConversion:
    def test_to_dto(self):
        ft = FormTemplate(
            uid="ft_conv",
            title="Test",
            form_schema=[{"name": "q1", "type": "text", "label": "Q1"}],
            instructions="Fill this out",
            tags=("tag1", "tag2"),
        )
        dto = ft.to_dto()
        assert isinstance(dto, FormTemplateDTO)
        assert dto.uid == "ft_conv"
        assert dto.form_schema == [{"name": "q1", "type": "text", "label": "Q1"}]
        assert dto.instructions == "Fill this out"
        assert dto.tags == ["tag1", "tag2"]

    def test_from_dto(self):
        dto = FormTemplateDTO(
            uid="ft_from_dto",
            title="From DTO",
            form_schema=[{"name": "q1", "type": "text", "label": "Q1"}],
            instructions="Instructions here",
        )
        ft = FormTemplate._from_dto(dto)
        assert ft.uid == "ft_from_dto"
        assert ft.entity_type == EntityType.FORM_TEMPLATE
        assert isinstance(ft.form_schema, tuple)
        assert ft.instructions == "Instructions here"


class TestFormTemplateDTOSerialization:
    def test_to_dict(self):
        dto = FormTemplateDTO(
            uid="ft_ser",
            title="Test",
            form_schema=[{"name": "q1", "type": "text", "label": "Q1"}],
        )
        d = dto.to_dict()
        assert d["uid"] == "ft_ser"
        # form_schema should be JSON string for Neo4j
        assert isinstance(d["form_schema"], str)
        parsed = json.loads(d["form_schema"])
        assert parsed[0]["name"] == "q1"

    def test_from_dict_json_string(self):
        data = {
            "uid": "ft_deser",
            "title": "Test",
            "form_schema": json.dumps([{"name": "q1", "type": "text", "label": "Q1"}]),
        }
        dto = FormTemplateDTO.from_dict(data)
        assert dto.uid == "ft_deser"
        assert isinstance(dto.form_schema, list)
        assert dto.form_schema[0]["name"] == "q1"


class TestFormTemplateSchemaFingerprint:
    def test_deterministic(self):
        """Same schema + instructions always produces the same hash."""
        ft = FormTemplate(
            uid="ft_1",
            title="Test",
            form_schema=[{"name": "q1", "type": "text", "label": "Q1"}],
            instructions="Fill this out",
        )
        assert ft.schema_fingerprint() == ft.schema_fingerprint()
        assert len(ft.schema_fingerprint()) == 64

    def test_changes_with_schema(self):
        """Different schemas produce different hashes."""
        ft1 = FormTemplate(
            uid="ft_1",
            title="Test",
            form_schema=[{"name": "q1", "type": "text"}],
        )
        ft2 = FormTemplate(
            uid="ft_1",
            title="Test",
            form_schema=[{"name": "q1", "type": "textarea"}],
        )
        assert ft1.schema_fingerprint() != ft2.schema_fingerprint()

    def test_changes_with_instructions(self):
        """Different instructions produce different hashes."""
        ft1 = FormTemplate(
            uid="ft_1",
            title="Test",
            form_schema=[{"name": "q1", "type": "text"}],
            instructions="Version 1",
        )
        ft2 = FormTemplate(
            uid="ft_1",
            title="Test",
            form_schema=[{"name": "q1", "type": "text"}],
            instructions="Version 2",
        )
        assert ft1.schema_fingerprint() != ft2.schema_fingerprint()

    def test_none_schema(self):
        """Works with None schema."""
        ft = FormTemplate(uid="ft_1", title="Test")
        h = ft.schema_fingerprint()
        assert len(h) == 64


class TestFormTemplateEntityType:
    """Test EntityType traits for FORM_TEMPLATE."""

    def test_shared_type(self):
        assert not EntityType.FORM_TEMPLATE.requires_user_uid()

    def test_not_activity(self):
        assert not EntityType.FORM_TEMPLATE.is_activity()

    def test_not_derived(self):
        assert not EntityType.FORM_TEMPLATE.is_derived()

    def test_content_origin(self):
        from core.models.enums.entity_enums import ContentOrigin

        assert EntityType.FORM_TEMPLATE.content_origin() == ContentOrigin.CURATED

    def test_from_string(self):
        assert EntityType.from_string("form_template") == EntityType.FORM_TEMPLATE
        assert EntityType.from_string("form") == EntityType.FORM_TEMPLATE
