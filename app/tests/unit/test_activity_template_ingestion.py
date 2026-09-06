"""
Unit Tests for the Activity Template vault door (PR-1)
=======================================================

The 6 Activity Templates became vault-ingestible: template ``.md`` files carry
their frontmatter (``type: task_template``, …), and ``{domain}_template_uids:``
on PathStep YAML creates the ``HAS_*_TEMPLATE`` edges ``PsEngagementService``
walks at spawn time.

Test Categories:
1. Type detection (explicit ``type: <domain>_template``; never sniff)
2. ENTITY_CONFIGS schema (uid prefixes, required fields, the ACTIVE default)
3. Registry edge wiring (PS ``{domain}_template_uids`` → HAS_*_TEMPLATE, and
   the freed ``event_uids`` instance channel)
4. RelativeOffset authoring — canonical storage shape, and the loud rejection
   of a value the reader would silently rebuild as a zero offset

See: /docs/roadmap/activity-templates-vault-door.md
"""

from __future__ import annotations

from pathlib import Path

import pytest

from adapters.persistence.neo4j.neo4j_mapper import to_neo4j_node
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.templates.offset_helpers import (
    TEMPLATE_OFFSET_FIELDS,
    jsonable_to_offset,
)
from core.models.templates.relative_offset import RelativeOffset
from core.models.templates.task_template_dto import TaskTemplateDTO
from core.services.ingestion.config import (
    ENTITY_CONFIGS,
    generate_ingestion_relationship_config,
)
from core.services.ingestion.detector import detect_entity_type
from core.services.ingestion.preparer import prepare_entity_data
from core.services.ingestion.validator import validate_entity_data, validate_uid_format

_TEMPLATE_TYPES: tuple[EntityType, ...] = (
    EntityType.TASK_TEMPLATE,
    EntityType.GOAL_TEMPLATE,
    EntityType.HABIT_TEMPLATE,
    EntityType.EVENT_TEMPLATE,
    EntityType.CHOICE_TEMPLATE,
    EntityType.PRINCIPLE_TEMPLATE,
)

_EXPECTED_PREFIXES: dict[EntityType, str] = {
    EntityType.TASK_TEMPLATE: "tt",
    EntityType.GOAL_TEMPLATE: "gt",
    EntityType.HABIT_TEMPLATE: "ht",
    EntityType.EVENT_TEMPLATE: "et",
    EntityType.CHOICE_TEMPLATE: "ct",
    EntityType.PRINCIPLE_TEMPLATE: "pt",
}

_FILE = Path("tt_daily-practice-log_tmpl.md")


# ============================================================================
# 1. TYPE DETECTION
# ============================================================================


@pytest.mark.parametrize("entity_type", _TEMPLATE_TYPES)
def test_explicit_template_type_detected(entity_type: EntityType) -> None:
    assert detect_entity_type({"type": entity_type.value}, _FILE) is entity_type


def test_template_without_type_rejected() -> None:
    """Never-sniff: the filename says nothing — only an explicit ``type:`` opts in."""
    with pytest.raises(ValueError, match="no 'type:' field"):
        detect_entity_type({}, _FILE)


# ============================================================================
# 2. ENTITY_CONFIGS SCHEMA
# ============================================================================


@pytest.mark.parametrize("entity_type", _TEMPLATE_TYPES)
def test_template_config_shape(entity_type: EntityType) -> None:
    config = ENTITY_CONFIGS[entity_type]
    assert config.uid_prefix == _EXPECTED_PREFIXES[entity_type]
    assert config.required_fields == ("title",)  # matches TemplateCreateRequest
    assert config.base_label == "Entity"  # :Entity:TaskTemplate, as _backends.py builds
    assert config.requires_user_uid is False  # PS-owned curriculum, no OWNS edge
    assert config.embeddable is False  # no EMBEDDING_FIELD_MAPS entry for templates


@pytest.mark.parametrize("entity_type", _TEMPLATE_TYPES)
def test_template_entity_label_matches_backend(entity_type: EntityType) -> None:
    """The ingest door writes the label the CRUD backend reads."""
    from core.models.relationship_registry import ENTITY_TYPE_TO_LABEL

    assert ENTITY_CONFIGS[entity_type].entity_label == ENTITY_TYPE_TO_LABEL[entity_type]


@pytest.mark.parametrize("entity_type", _TEMPLATE_TYPES)
def test_absent_status_defaults_to_active(entity_type: EntityType) -> None:
    """A vault template with no ``status:`` must still be spawnable.

    ``PsEngagementService`` refuses to spawn from a non-ACTIVE template, and
    ingestion applies no model defaults — without this the node would carry no
    status at all and every vault-authored template would silently never spawn.
    """
    prepared = prepare_entity_data(
        entity_type, {"type": entity_type.value, "title": "T"}, None, _FILE
    )
    assert prepared["status"] == EntityStatus.ACTIVE.value


@pytest.mark.parametrize("entity_type", _TEMPLATE_TYPES)
def test_authored_status_wins(entity_type: EntityType) -> None:
    prepared = prepare_entity_data(
        entity_type, {"type": entity_type.value, "title": "T", "status": "draft"}, None, _FILE
    )
    assert prepared["status"] == EntityStatus.DRAFT.value


@pytest.mark.parametrize("entity_type", _TEMPLATE_TYPES)
def test_uid_prefix_enforced(entity_type: EntityType) -> None:
    prefix = _EXPECTED_PREFIXES[entity_type]
    ok = validate_uid_format(entity_type, {"uid": f"{prefix}.daily-practice"}, _FILE)
    assert not ok.is_error
    wrong = validate_uid_format(entity_type, {"uid": "ku.daily-practice"}, _FILE)
    assert wrong.is_error


def test_generated_uid_uses_prefix() -> None:
    prepared = prepare_entity_data(
        EntityType.TASK_TEMPLATE, {"type": "task_template", "title": "T"}, None, _FILE
    )
    assert prepared["uid"] == "tt.tt_daily-practice-log_tmpl"
    assert prepared["entity_type"] == "task_template"


# ============================================================================
# 3. REGISTRY EDGE WIRING
# ============================================================================


def test_pathstep_attaches_every_template_kind() -> None:
    config = generate_ingestion_relationship_config(EntityType.PATH_STEP)
    assert config is not None
    for field, rel_type, target_label in (
        ("task_template_uids", "HAS_TASK_TEMPLATE", "TaskTemplate"),
        ("goal_template_uids", "HAS_GOAL_TEMPLATE", "GoalTemplate"),
        ("habit_template_uids", "HAS_HABIT_TEMPLATE", "HabitTemplate"),
        ("event_template_uids", "HAS_EVENT_TEMPLATE", "EventTemplate"),
        ("choice_template_uids", "HAS_CHOICE_TEMPLATE", "ChoiceTemplate"),
        ("principle_template_uids", "HAS_PRINCIPLE_TEMPLATE", "PrincipleTemplate"),
    ):
        assert config[field]["rel_type"] == rel_type
        assert config[field]["target_label"] == target_label


def test_event_instance_channel_no_longer_claims_the_template_name() -> None:
    """``event_template_uids`` targets an EventTemplate; the Event instance
    channel is ``event_uids``. Before the template door landed the instance
    channel held the template-shaped name and a uid followed from it matched
    nothing (the naming hazard recorded in the ContextRetriever case file)."""
    config = generate_ingestion_relationship_config(EntityType.PATH_STEP)
    assert config is not None
    assert config["event_uids"]["rel_type"] == "SCHEDULES_EVENT"
    assert config["event_uids"]["target_label"] == "Event"
    assert config["event_template_uids"]["target_label"] == "EventTemplate"


def test_templates_author_no_outgoing_edges() -> None:
    """Attachment is authored on the PS side; a template file declares no edges."""
    for entity_type in _TEMPLATE_TYPES:
        assert ENTITY_CONFIGS[entity_type].relationship_config is None


# ============================================================================
# 4. RELATIVEOFFSET AUTHORING
# ============================================================================


def test_offset_field_registry_covers_every_template_type() -> None:
    assert set(TEMPLATE_OFFSET_FIELDS) == set(_TEMPLATE_TYPES)


def test_authored_offset_canonicalized_to_storage_shape() -> None:
    prepared = prepare_entity_data(
        EntityType.TASK_TEMPLATE,
        {"type": "task_template", "title": "T", "due_offset": {"days": 7}},
        None,
        _FILE,
    )
    assert prepared["due_offset"] == {"days": 7, "hours": 0, "minutes": 0}


def test_ingested_offset_matches_the_dto_write_path_byte_for_byte() -> None:
    """Both doors must persist one shape — the vault and the JSON API.

    The mapper is the single ``json.dumps``; the preparer only normalizes the
    value it serializes.
    """
    prepared = prepare_entity_data(
        EntityType.TASK_TEMPLATE,
        {"type": "task_template", "title": "T", "due_offset": {"days": 7}},
        None,
        _FILE,
    )
    from_vault = to_neo4j_node(prepared)["due_offset"]

    dto = TaskTemplateDTO(uid="tt.x", title="T", due_offset=RelativeOffset(days=7))
    from_api = to_neo4j_node(dto.to_dict())["due_offset"]

    assert from_vault == from_api
    assert jsonable_to_offset(from_vault) == RelativeOffset(days=7)


@pytest.mark.parametrize(
    "authored",
    [
        7,  # a bare int — the reader rebuilds nothing
        [7],  # a list
        "seven days",  # unparseable string
        {"day": 7},  # mistyped key — would silently become a ZERO offset
        {"days": "seven"},  # non-integer — ``int()`` raises inside the reader
        {"days": 1.5},  # fractional day
    ],
)
def test_unauthorable_offset_rejected_loudly(authored: object) -> None:
    data = {"type": "task_template", "title": "T", "due_offset": authored}
    prepared = prepare_entity_data(EntityType.TASK_TEMPLATE, dict(data), None, _FILE)
    # Left verbatim by the preparer so the validator owns the message.
    assert prepared["due_offset"] == authored

    result = validate_entity_data(EntityType.TASK_TEMPLATE, prepared, _FILE)
    assert result.is_error
    assert "due_offset" in result.expect_error().message


def test_absent_offset_is_not_a_violation() -> None:
    prepared = prepare_entity_data(
        EntityType.TASK_TEMPLATE, {"type": "task_template", "title": "T"}, None, _FILE
    )
    assert not validate_entity_data(EntityType.TASK_TEMPLATE, prepared, _FILE).is_error


def test_json_string_offset_accepted_like_the_reader() -> None:
    """The write gate mirrors the READ boundary's tolerance stack (#1003)."""
    prepared = prepare_entity_data(
        EntityType.TASK_TEMPLATE,
        {"type": "task_template", "title": "T", "due_offset": '{"days": 2}'},
        None,
        _FILE,
    )
    assert prepared["due_offset"] == {"days": 2, "hours": 0, "minutes": 0}
    assert not validate_entity_data(EntityType.TASK_TEMPLATE, prepared, _FILE).is_error
