"""Pin YAML_AUTHORING_GUIDE's per-type status table to the live code.

Why this exists
---------------
The table's claim — "using a status not in the valid set for that entity type
will fail validation during ingestion" — was aspirational until the ingestion
validator grew its status-legality gate: the vocabulary gate checked enum
MEMBERSHIP only, so ``type: principle, status: completed`` passed the door.
Now the door enforces it, which turns every cell of this table into a rule an
author is held to.

At the moment the table became enforceable it was also wrong: Knowledge Unit's
default read ``draft`` where the code says ``completed``, and eight ingestible
types (Resource, Exercise, Interaction, the six Activity Templates) had no row
at all — an author looking up a template's legal statuses found nothing and
guessed.

So the table is derived-checked. Adding an ingestible type, widening a type's
valid statuses, or changing a door default breaks the build until the guide
agrees. ``app/docs/guides/YAML_AUTHORING_GUIDE.md`` is in CI's ``py`` path
filter so a docs-only edit to the table still runs this module.
"""

from __future__ import annotations

import re
from pathlib import Path

from core.models.enums.entity_enums import EntityType
from core.services.ingestion.config import ENTITY_CONFIGS

_GUIDE = Path(__file__).resolve().parents[3] / "docs" / "guides" / "YAML_AUTHORING_GUIDE.md"
_HEADING = "**Valid statuses and defaults per ingestible entity type**"


def _documented_rows() -> dict[str, tuple[frozenset[str], str, str]]:
    """Parse the guide's table into {display name: (valid, type default, door)}."""
    text = _GUIDE.read_text(encoding="utf-8")
    start = text.index(_HEADING)
    body = text[start:]
    rows: dict[str, tuple[frozenset[str], str, str]] = {}
    for line in body.splitlines():
        if not line.startswith("|"):
            if rows:
                break  # the table ended
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 4 or cells[0] in {"Type", ""} or set(cells[1]) <= {"-"}:
            continue
        valid = frozenset(m.strip("`") for m in re.findall(r"`[^`]+`", cells[1]))
        rows[cells[0]] = (valid, cells[2].strip("`"), cells[3].strip("`"))
    return rows


def _code_rows() -> dict[str, tuple[frozenset[str], str, str]]:
    rows: dict[str, tuple[frozenset[str], str, str]] = {}
    for entity_type in ENTITY_CONFIGS:
        if not isinstance(entity_type, EntityType):
            continue  # NonKuDomain has no EntityStatus lifecycle
        door = (ENTITY_CONFIGS[entity_type].default_values or {}).get("status")
        rows[entity_type.get_display_name()] = (
            frozenset(s.value for s in entity_type.valid_statuses()),
            entity_type.default_status().value,
            str(door) if door else "—",
        )
    return rows


def test_table_covers_exactly_the_ingestible_types() -> None:
    documented, code = set(_documented_rows()), set(_code_rows())
    assert documented == code, (
        f"missing rows: {sorted(code - documented)}; stale rows: {sorted(documented - code)}"
    )


def test_every_documented_cell_matches_the_code() -> None:
    documented, code = _documented_rows(), _code_rows()
    for name, (valid, type_default, door) in code.items():
        assert documented[name][0] == valid, (
            f"{name}: valid statuses documented as {sorted(documented[name][0])}, "
            f"code says {sorted(valid)}"
        )
        assert documented[name][1] == type_default, (
            f"{name}: type default documented as {documented[name][1]!r}, code says {type_default!r}"
        )
        assert documented[name][2] == door, (
            f"{name}: ingest-door stamp documented as {documented[name][2]!r}, code says {door!r}"
        )


def test_the_parser_actually_found_a_table() -> None:
    # A rename of the heading would empty the parse and pass both tests above
    # vacuously — the failure mode a derivation test exists to prevent.
    assert len(_documented_rows()) >= 20
