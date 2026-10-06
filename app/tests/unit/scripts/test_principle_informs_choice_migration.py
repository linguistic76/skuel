"""The principle-informs-choice migration's tracker-key rewrite — no graph.

``rewritten_keys`` in ``scripts/migrations/principle_informs_choice_2026_10.py`` names
each old tracker key (``{type}|{direction}|{uid}``) as the edge it became, one
``(Principle)-[:INFORMS_CHOICE]->(Choice)``:

- ``GUIDES_CHOICE|outgoing|<choice>`` → ``INFORMS_CHOICE|outgoing|<choice>``;
- ``GUIDES_CHOICE|incoming|<principle>`` → ``INFORMS_CHOICE|incoming|<principle>``;
- ``INFORMED_BY_PRINCIPLE|outgoing|<principle>`` → ``INFORMS_CHOICE|incoming|<principle>``;
- ``INFORMED_BY_PRINCIPLE|incoming|<choice>`` → ``INFORMS_CHOICE|outgoing|<choice>``.

Both old types retire whole, so no row kind is exempt. The result is sorted and
de-duplicated, the form ``authored_edge_fingerprint`` stores. The census and the write
run on a real graph in
tests/integration/migrations/test_principle_informs_choice_migration.py.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from core.models.relationship_names import RelationshipName
from core.services.ingestion.authored_edges import parse_authored_edge

SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "migrations"
    / "principle_informs_choice_2026_10.py"
)
_spec = importlib.util.spec_from_file_location("principle_informs_choice_2026_10", SCRIPT)
assert _spec is not None and _spec.loader is not None
migration = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = migration
_spec.loader.exec_module(migration)

rewritten_keys = migration.rewritten_keys

# (old key, the key it becomes)
MAPPINGS = [
    ("GUIDES_CHOICE|outgoing|choice.a.b", "INFORMS_CHOICE|outgoing|choice.a.b"),
    ("GUIDES_CHOICE|incoming|principle.a.b", "INFORMS_CHOICE|incoming|principle.a.b"),
    ("INFORMED_BY_PRINCIPLE|outgoing|principle.a.b", "INFORMS_CHOICE|incoming|principle.a.b"),
    ("INFORMED_BY_PRINCIPLE|incoming|choice.a.b", "INFORMS_CHOICE|outgoing|choice.a.b"),
]


@pytest.mark.parametrize(("old", "new"), MAPPINGS, ids=[old for old, _ in MAPPINGS])
def test_each_old_shape_becomes_the_informs_choice_key_for_its_side(old: str, new: str) -> None:
    assert rewritten_keys([old]) == [new]


@pytest.mark.parametrize(
    "kept",
    [
        "INFORMS_CHOICE|outgoing|choice.a.b",  # a PathStep's choice_uids, a principle's new field
        "INFORMS_CHOICE|incoming|principle.a.b",  # a choice's new field
        "INSPIRES_HABIT|outgoing|habit.a.b",
        "SUPPORTS_GOAL|outgoing|goal.a.b",
        "GUIDED_BY_PRINCIPLE|outgoing|principle.a.b",  # a PathStep's, not this link
    ],
)
def test_a_key_of_a_type_that_is_not_retired_is_kept(kept: str) -> None:
    assert rewritten_keys([kept]) == [kept]


@pytest.mark.parametrize(
    "malformed",
    [
        "GUIDES_CHOICE",
        "GUIDES_CHOICE|outgoing",
        "INFORMED_BY_PRINCIPLE|",
        "",
        "no separators at all",
    ],
)
def test_a_malformed_key_is_kept_as_it_is(malformed: str) -> None:
    assert rewritten_keys([malformed]) == [malformed]


def test_an_unknown_direction_is_kept_as_it_is() -> None:
    key = "GUIDES_CHOICE|sideways|choice.a.b"

    assert rewritten_keys([key]) == [key]


def test_a_uid_holding_the_separator_keeps_its_tail() -> None:
    """The key splits twice; whatever follows the second separator is the uid."""
    assert rewritten_keys(["INFORMED_BY_PRINCIPLE|outgoing|principle|odd"]) == [
        "INFORMS_CHOICE|incoming|principle|odd"
    ]


def test_an_old_key_and_the_new_key_for_the_same_edge_become_one() -> None:
    keys = [
        "INFORMED_BY_PRINCIPLE|outgoing|principle.a.b",
        "INFORMS_CHOICE|incoming|principle.a.b",
    ]

    assert rewritten_keys(keys) == ["INFORMS_CHOICE|incoming|principle.a.b"]


def test_both_old_shapes_of_one_principle_side_link_become_one_key() -> None:
    keys = [
        "GUIDES_CHOICE|outgoing|choice.a.b",
        "INFORMED_BY_PRINCIPLE|incoming|choice.a.b",
        "GUIDES_CHOICE|outgoing|choice.a.b",
    ]

    assert rewritten_keys(keys) == ["INFORMS_CHOICE|outgoing|choice.a.b"]


def test_the_result_is_sorted() -> None:
    keys = [
        "USES_KU|outgoing|ku.z.z",
        "GUIDES_CHOICE|outgoing|choice.b.b",
        "GUIDES_CHOICE|outgoing|choice.a.a",
        "AFFECTS_GOAL|outgoing|goal.a.a",
    ]

    assert rewritten_keys(keys) == [
        "AFFECTS_GOAL|outgoing|goal.a.a",
        "INFORMS_CHOICE|outgoing|choice.a.a",
        "INFORMS_CHOICE|outgoing|choice.b.b",
        "USES_KU|outgoing|ku.z.z",
    ]


def test_no_keys_is_no_keys() -> None:
    assert rewritten_keys([]) == []


@pytest.mark.parametrize(("old", "new"), MAPPINGS, ids=[old for old, _ in MAPPINGS])
def test_a_rewritten_key_decodes_to_the_edge_the_retraction_deletes(old: str, new: str) -> None:
    """The point of the rewrite: the ingestion can address the migrated edge."""
    (key,) = rewritten_keys([old])

    edge = parse_authored_edge(key)

    assert edge is not None
    assert (edge.rel_type, edge.direction) == (
        RelationshipName.INFORMS_CHOICE,
        new.split("|")[1],
    )
    assert edge.target_uid == old.rsplit("|", 1)[1]


@pytest.mark.parametrize(
    "retired",
    [
        "GUIDES_CHOICE|outgoing|choice.a.b",
        "INFORMED_BY_PRINCIPLE|outgoing|principle.a.b",
    ],
)
def test_a_retired_type_decodes_to_no_edge(retired: str) -> None:
    """Why the rewrite is needed: a key of a retired type addresses nothing."""
    assert parse_authored_edge(retired) is None
