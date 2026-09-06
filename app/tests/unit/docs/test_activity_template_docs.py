"""Pin every documented Activity-Template authoring table to the live code.

Why this exists
---------------
The templates' only authoring reference — ``YAML_AUTHORING_GUIDE``'s TaskTemplate
field table — documented a ``priority`` field, with a "Copied to spawned Task"
purpose, that has never existed anywhere in the templates stack: not on the
dataclass, not on the DTO, not on the request model, not on the web form. Two
worked examples POSTed it. Nothing checked, so it read as authoritative for as
long as the table existed.

That table is now the authoring surface for a vault door, so the cost of a wrong
row went up: an author writes the field, ingestion drops it silently (unknown keys
are not persisted), and the template spawns without it.

So the tables are *derived-checked* — adding a field to a template, renaming one,
or inventing one in prose breaks the build until the docs agree.

The corpus is discovered, not enumerated
----------------------------------------
A hard-coded "the one doc with template tables" list has the failure mode it is
meant to prevent. This module globs first-party docs and picks up any table that
(a) has a ``Field`` column and (b) sits under a heading naming one of the six
template classes. A table added to a new doc tomorrow is covered on arrival.

Known limits
------------
Only tables are checked. The field-name column is pinned exhaustively; the *Type*
column is pinned only where the cell spells a vocabulary out (``a``/``b``/``c``),
which is the case worth pinning — ``event_type`` is typed ``str | None`` on the
dataclass but enum-checked at the ingest door, so the doc is the only place an
author learns the accepted values and the only place they can go stale. A *Purpose*
cell, and prose naming a field in a sentence, have no structural signal.
"""

from __future__ import annotations

import re
from dataclasses import fields
from pathlib import Path

import pytest

from core.models.entity import Entity
from core.models.enum_field_registry import ENUM_FIELD_TYPES
from core.models.enums.entity_enums import EntityType
from core.models.relationship_registry import PS_CONFIG
from core.models.templates import (
    ChoiceTemplate,
    EventTemplate,
    GoalTemplate,
    HabitTemplate,
    PrincipleTemplate,
    TaskTemplate,
)
from core.models.templates.offset_helpers import TEMPLATE_OFFSET_FIELDS
from core.services.ingestion.config import ENTITY_CONFIGS
from core.services.ingestion.detector import TYPE_MAPPING
from core.services.ps_engagement._spawn_orchestrator import SPAWN_REGISTRY

APP_ROOT = Path(__file__).resolve().parents[3]
DOC_DIRS = ("docs",)

TEMPLATE_CLASSES: dict[str, type] = {
    cls.__name__: cls
    for cls in (
        TaskTemplate,
        GoalTemplate,
        HabitTemplate,
        EventTemplate,
        ChoiceTemplate,
        PrincipleTemplate,
    )
}

# Fields every template inherits. A table documents what its own class *adds*;
# the shared Entity surface is documented once, in prose, in the guide.
ENTITY_FIELDS: frozenset[str] = frozenset(f.name for f in fields(Entity))

# ``entity_type`` is a leaf-identity default (G6), not an authorable field — it is
# implied by ``type:`` and rejected if it disagrees, so no table lists it.
_NOT_AUTHORABLE: frozenset[str] = frozenset({"entity_type"})


def _entity_type_of(cls: type) -> EntityType:
    """The EntityType a template class defaults its leaf identity to (G6)."""
    return EntityType(next(f for f in fields(cls) if f.name == "entity_type").default)


def _own_fields(cls: type) -> frozenset[str]:
    """The authorable fields a template class adds beyond ``Entity``."""
    return frozenset(f.name for f in fields(cls)) - ENTITY_FIELDS - _NOT_AUTHORABLE


def _doc_files() -> list[Path]:
    return sorted(
        path
        for directory in DOC_DIRS
        for path in (APP_ROOT / directory).rglob("*.md")
        if path.is_file()
    )


_HEADING = re.compile(r"^#{2,4}\s+(?P<text>.+?)\s*$")
_ROW = re.compile(r"^\s*\|(?P<cells>.+)\|\s*$")


def _split_row(line: str) -> list[str]:
    match = _ROW.match(line)
    if match is None:
        return []
    return [cell.strip() for cell in match.group("cells").split("|")]


def _is_separator(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def _field_tables(path: Path) -> list[tuple[str, str, dict[str, str]]]:
    """Every ``Field``-column table in ``path``, as (heading, class name, field → Type cell).

    A table is attributed to the template class its nearest preceding heading
    names. Tables under a heading naming no template class are skipped — this
    module only claims the six.
    """
    found: list[tuple[str, str, dict[str, str]]] = []
    heading = ""
    lines = path.read_text(encoding="utf-8").splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        heading_match = _HEADING.match(line)
        if heading_match:
            heading = heading_match.group("text")
            index += 1
            continue

        header_cells = _split_row(line)
        if not header_cells or header_cells[0].strip("`*") != "Field":
            index += 1
            continue
        if index + 1 >= len(lines) or not _is_separator(_split_row(lines[index + 1])):
            index += 1
            continue

        named = [name for name in TEMPLATE_CLASSES if name in heading]
        index += 2
        rows: dict[str, str] = {}
        while index < len(lines):
            cells = _split_row(lines[index])
            if not cells:
                break
            rows[cells[0].strip().strip("`*")] = cells[1] if len(cells) > 1 else ""
            index += 1
        if len(named) == 1:
            found.append((heading, named[0], rows))
    return found


ALL_TABLES = [(path, *table) for path in _doc_files() for table in _field_tables(path)]


def test_template_field_tables_are_discovered() -> None:
    """Guard the discovery itself: all six classes must be covered somewhere.

    Without this, a rename that stops a heading matching would make every check
    below vacuously pass — the table would simply stop being found.
    """
    covered = {class_name for _path, _heading, class_name, _rows in ALL_TABLES}
    assert covered == set(TEMPLATE_CLASSES), (
        f"Documented template field tables cover {sorted(covered)}; "
        f"expected all six of {sorted(TEMPLATE_CLASSES)}. A heading that no longer "
        "names its class silently drops that table from every check in this module."
    )


@pytest.mark.parametrize(
    ("path", "heading", "class_name", "rows"),
    ALL_TABLES,
    ids=[f"{path.name}::{heading}" for path, heading, _cls, _rows in ALL_TABLES],
)
def test_documented_fields_exist(
    path: Path, heading: str, class_name: str, rows: dict[str, str]
) -> None:
    """Every row names a real field on the class its heading names."""
    live = _own_fields(TEMPLATE_CLASSES[class_name])
    invented = [name for name in rows if name not in live]
    assert not invented, (
        f"{path.relative_to(APP_ROOT)} § {heading}: {invented} are not fields of "
        f"{class_name}. Ingestion drops unknown keys silently, so a documented "
        "field that does not exist is authored and then lost."
    )


@pytest.mark.parametrize(
    ("path", "heading", "class_name", "rows"),
    ALL_TABLES,
    ids=[f"{path.name}::{heading}" for path, heading, _cls, _rows in ALL_TABLES],
)
def test_documented_fields_are_complete(
    path: Path, heading: str, class_name: str, rows: dict[str, str]
) -> None:
    """The table covers every field the class adds beyond ``Entity``."""
    missing = sorted(_own_fields(TEMPLATE_CLASSES[class_name]) - set(rows))
    assert not missing, (
        f"{path.relative_to(APP_ROOT)} § {heading}: {missing} exist on {class_name} "
        "but are not documented. A field reference that is not complete sends the "
        "author to the dataclass."
    )


def _table_rows(path: Path, first_header_cell: str) -> dict[str, list[str]]:
    """Rows of the one table in ``path`` whose header starts with ``first_header_cell``.

    Anchoring on the header, not on "a row whose first cell names a template",
    keeps the two class-keyed tables in this guide apart — both start their rows
    with a class name.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    rows: dict[str, list[str]] = {}
    for index, line in enumerate(lines):
        cells = _split_row(line)
        if not cells or cells[0].strip("`* ") != first_header_cell:
            continue
        if index + 1 >= len(lines) or not _is_separator(_split_row(lines[index + 1])):
            continue
        for body in lines[index + 2 :]:
            body_cells = _split_row(body)
            if not body_cells:
                break
            rows[body_cells[0].strip("`* ")] = [cell.strip() for cell in body_cells[1:]]
        break
    return rows


def _cell_names(cell: str) -> list[str]:
    """Backticked identifiers in one table cell, in order. ``—`` yields nothing."""
    return re.findall(r"`([a-z_]+)`", cell)


ATA_GUIDE = APP_ROOT / "docs/guides/ACTIVITY_TEMPLATE_AUTHORING.md"


def test_documented_type_prefix_and_attachment_rows_match_the_code() -> None:
    """Pin the ``type:`` / UID-prefix / attachment-field table to its three sources.

    Each column asserts against a different authority — the detector's TYPE_MAPPING,
    the ingest config's uid_prefix, and the relationship registry's yaml_field_path
    — so a row cannot go stale without one of the three moving.
    """
    rows = _table_rows(ATA_GUIDE, "Kind")
    assert set(rows) == set(TEMPLATE_CLASSES), (
        f"{ATA_GUIDE.name} documents kinds {sorted(rows)}; expected {sorted(TEMPLATE_CLASSES)}."
    )

    yaml_fields = {
        definition.relationship: definition.yaml_field_path
        for definition in PS_CONFIG.relationships
    }
    for class_name, cls in TEMPLATE_CLASSES.items():
        entity_type = _entity_type_of(cls)
        type_value, uid_prefix, attach_field = (cell.strip("`* ") for cell in rows[class_name][:3])
        assert TYPE_MAPPING[type_value] is entity_type, (
            f"{ATA_GUIDE.name}: `type: {type_value}` does not resolve to {entity_type!r}."
        )
        assert ENTITY_CONFIGS[entity_type].uid_prefix == uid_prefix.rstrip("."), (
            f"{ATA_GUIDE.name}: {class_name} UID prefix is documented as {uid_prefix!r} "
            f"but ENTITY_CONFIGS says {ENTITY_CONFIGS[entity_type].uid_prefix!r}."
        )
        edge = next(name for name in yaml_fields if name.value == f"HAS_{entity_type.name}")
        assert yaml_fields[edge] == attach_field.rstrip(":"), (
            f"{ATA_GUIDE.name}: {class_name} is documented as attaching via "
            f"{attach_field!r} but the registry says {yaml_fields[edge]!r}."
        )


def test_documented_offset_rows_match_the_spawn_registry() -> None:
    """Pin the offset table to ``TEMPLATE_OFFSET_FIELDS`` and the spawn rewrites.

    Both columns are derived: which fields are offsets (the write-side gate reads
    this list) and what each resolves to on the spawned instance.
    """
    rows = _table_rows(ATA_GUIDE, "Template")
    assert set(rows) == set(TEMPLATE_CLASSES), (
        f"{ATA_GUIDE.name} offset table covers {sorted(rows)}; expected {sorted(TEMPLATE_CLASSES)}."
    )
    rewrites = {spec.template_cls.__name__: spec.offset_rewrites for spec in SPAWN_REGISTRY}
    for class_name, cls in TEMPLATE_CLASSES.items():
        entity_type = _entity_type_of(cls)
        documented_fields = _cell_names(rows[class_name][0])
        documented_targets = _cell_names(rows[class_name][1])
        assert documented_fields == list(TEMPLATE_OFFSET_FIELDS.get(entity_type, ())), (
            f"{ATA_GUIDE.name}: {class_name} offset fields are documented as "
            f"{documented_fields} but TEMPLATE_OFFSET_FIELDS says "
            f"{list(TEMPLATE_OFFSET_FIELDS.get(entity_type, ()))}."
        )
        assert documented_targets == [dst for _src, dst, _kind in rewrites[class_name]], (
            f"{ATA_GUIDE.name}: {class_name} offsets are documented as resolving to "
            f"{documented_targets} but the spawn registry says "
            f"{[dst for _src, dst, _kind in rewrites[class_name]]}."
        )


def _vocabulary(cell: str) -> list[str] | None:
    """The slash-separated backticked vocabulary in a Type cell, or None.

    A cell of backticked lowercase values joined by slashes is a vocabulary; a cell
    naming a UID prefix, ``offset map``, ``int`` or ``bool`` is not.
    """
    parts = cell.split("/")
    if len(parts) < 2:
        return None
    values = [part.strip() for part in parts]
    if not all(re.fullmatch(r"`[a-z][a-z_]*`", value) for value in values):
        return None
    return [value.strip("`") for value in values]


@pytest.mark.parametrize(
    ("path", "heading", "class_name", "rows"),
    ALL_TABLES,
    ids=[f"{path.name}::{heading}" for path, heading, _cls, _rows in ALL_TABLES],
)
def test_documented_enum_vocabularies_match_the_registry(
    path: Path, heading: str, class_name: str, rows: dict[str, str]
) -> None:
    """A spelled-out Type vocabulary must be that field's enum, in the enum's order.

    ``ENUM_FIELD_TYPES`` is what the ingest door validates against — the same map the
    preparer canonicalizes through — so a documented value it does not contain is a
    value that fails the file.
    """
    for field_name, cell in rows.items():
        documented = _vocabulary(cell)
        if documented is None:
            continue
        enum_cls = ENUM_FIELD_TYPES.get(field_name)
        assert enum_cls is not None, (
            f"{path.relative_to(APP_ROOT)} § {heading}: `{field_name}` documents a "
            f"vocabulary {documented} but no enum governs it at the ingest door."
        )
        assert documented == [member.value for member in enum_cls], (
            f"{path.relative_to(APP_ROOT)} § {heading}: `{field_name}` documents "
            f"{documented} but {enum_cls.__name__} is "
            f"{[member.value for member in enum_cls]}."
        )


def test_documented_json_api_path_matches_the_route_configs() -> None:
    """The guide's second-door path must match the six route configs' ``domain_name``.

    The guide it replaced named ``POST /api/task-templates/`` and
    ``POST /api/ps/{ps_uid}/task-templates/{uid}/attach``. Neither route has ever
    existed — the factory builds ``/api/{domain_name}`` and every template config
    names itself ``pathstep-{domain}-templates``. Same failure class as the
    ``priority`` field: prose naming a surface nobody checked.
    """
    from adapters.inbound.pathstep_choice_templates_routes import (
        PATHSTEP_CHOICE_TEMPLATES_CONFIG,
    )
    from adapters.inbound.pathstep_event_templates_routes import (
        PATHSTEP_EVENT_TEMPLATES_CONFIG,
    )
    from adapters.inbound.pathstep_goal_templates_routes import PATHSTEP_GOAL_TEMPLATES_CONFIG
    from adapters.inbound.pathstep_habit_templates_routes import (
        PATHSTEP_HABIT_TEMPLATES_CONFIG,
    )
    from adapters.inbound.pathstep_principle_templates_routes import (
        PATHSTEP_PRINCIPLE_TEMPLATES_CONFIG,
    )
    from adapters.inbound.pathstep_task_templates_routes import PATHSTEP_TASK_TEMPLATES_CONFIG

    configs = (
        PATHSTEP_TASK_TEMPLATES_CONFIG,
        PATHSTEP_GOAL_TEMPLATES_CONFIG,
        PATHSTEP_HABIT_TEMPLATES_CONFIG,
        PATHSTEP_EVENT_TEMPLATES_CONFIG,
        PATHSTEP_CHOICE_TEMPLATES_CONFIG,
        PATHSTEP_PRINCIPLE_TEMPLATES_CONFIG,
    )
    documented = "/api/pathstep-{domain}-templates/"
    guide = ATA_GUIDE.read_text(encoding="utf-8")
    assert documented in guide, (
        f"{ATA_GUIDE.name} no longer documents the second door as {documented!r}."
    )
    # Expected names come from the six EntityTypes, not from the configs, so the
    # check is a derivation rather than a round trip through the value under test.
    expected = {
        documented.format(domain=entity_type.value.removesuffix("_template"))
        .strip("/")
        .removeprefix("api/")
        for entity_type in (_entity_type_of(cls) for cls in TEMPLATE_CLASSES.values())
    }
    assert {config.domain_name for config in configs} == expected, (
        f"Route configs name themselves {sorted(config.domain_name for config in configs)}; "
        f"{ATA_GUIDE.name} documents {documented!r}, i.e. {sorted(expected)}."
    )
