"""The principle-supports-goal migration's tracker-key rewrite — no graph.

``rewritten_keys`` in ``scripts/migrations/principle_supports_goal_2026_10.py`` names
each old tracker key (``{type}|{direction}|{uid}``) as the edge it became:

- ``GUIDES_GOAL|outgoing|<goal>`` → ``SUPPORTS_GOAL|outgoing|<goal>``;
- ``GUIDED_BY_PRINCIPLE|outgoing|<principle>`` → ``SUPPORTS_GOAL|incoming|<principle>``,
  on a goal's row only — a PathStep's row names an edge that stays.

The result is sorted and de-duplicated, the form ``authored_edge_fingerprint`` stores.
The census and the write run on a real graph in
tests/integration/migrations/test_principle_supports_goal_migration.py.
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
    / "principle_supports_goal_2026_10.py"
)
_spec = importlib.util.spec_from_file_location("principle_supports_goal_2026_10", SCRIPT)
assert _spec is not None and _spec.loader is not None
migration = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = migration
_spec.loader.exec_module(migration)

rewritten_keys = migration.rewritten_keys


def test_a_principle_rows_guides_goal_key_becomes_supports_goal_outgoing() -> None:
    assert rewritten_keys(["GUIDES_GOAL|outgoing|goal.a.b"], entity_is_goal=False) == [
        "SUPPORTS_GOAL|outgoing|goal.a.b"
    ]


def test_a_goal_rows_guided_by_principle_key_becomes_supports_goal_incoming() -> None:
    assert rewritten_keys(["GUIDED_BY_PRINCIPLE|outgoing|principle.a.b"], entity_is_goal=True) == [
        "SUPPORTS_GOAL|incoming|principle.a.b"
    ]


def test_guided_by_principle_on_a_row_that_is_not_a_goals_is_kept() -> None:
    keys = ["GUIDED_BY_PRINCIPLE|outgoing|principle.a.b"]

    assert rewritten_keys(keys, entity_is_goal=False) == keys


def test_an_incoming_guided_by_principle_key_on_a_goals_row_is_kept() -> None:
    """Only the goal → principle direction was a principle-goal link."""
    keys = ["GUIDED_BY_PRINCIPLE|incoming|ps.a.b"]

    assert rewritten_keys(keys, entity_is_goal=True) == keys


@pytest.mark.parametrize(
    "malformed",
    ["GUIDES_GOAL", "GUIDES_GOAL|outgoing", "", "no separators at all"],
)
def test_a_malformed_key_is_kept_as_it_is(malformed: str) -> None:
    assert rewritten_keys([malformed], entity_is_goal=True) == [malformed]


def test_a_uid_holding_the_separator_keeps_its_tail() -> None:
    """The key splits twice; whatever follows the second separator is the uid."""
    assert rewritten_keys(["GUIDES_GOAL|outgoing|goal|odd"], entity_is_goal=False) == [
        "SUPPORTS_GOAL|outgoing|goal|odd"
    ]


def test_other_keys_are_kept() -> None:
    keys = ["INSPIRES_HABIT|outgoing|habit.a.b", "SUPPORTS_GOAL|incoming|habit.a.c"]

    assert rewritten_keys(keys, entity_is_goal=True) == keys


def test_an_old_key_and_the_new_key_for_the_same_edge_become_one() -> None:
    keys = [
        "GUIDED_BY_PRINCIPLE|outgoing|principle.a.b",
        "SUPPORTS_GOAL|incoming|principle.a.b",
    ]

    assert rewritten_keys(keys, entity_is_goal=True) == ["SUPPORTS_GOAL|incoming|principle.a.b"]


def test_both_old_keys_on_a_principles_row_become_one_with_the_new_one() -> None:
    keys = ["GUIDES_GOAL|outgoing|goal.a.b", "SUPPORTS_GOAL|outgoing|goal.a.b"]

    assert rewritten_keys(keys, entity_is_goal=False) == ["SUPPORTS_GOAL|outgoing|goal.a.b"]


def test_the_result_is_sorted() -> None:
    keys = [
        "USES_KU|outgoing|ku.z.z",
        "GUIDES_GOAL|outgoing|goal.b.b",
        "GUIDES_GOAL|outgoing|goal.a.a",
        "INSPIRES_HABIT|outgoing|habit.a.a",
    ]

    assert rewritten_keys(keys, entity_is_goal=False) == [
        "INSPIRES_HABIT|outgoing|habit.a.a",
        "SUPPORTS_GOAL|outgoing|goal.a.a",
        "SUPPORTS_GOAL|outgoing|goal.b.b",
        "USES_KU|outgoing|ku.z.z",
    ]


def test_no_keys_is_no_keys() -> None:
    assert rewritten_keys([], entity_is_goal=True) == []


@pytest.mark.parametrize(
    ("old", "entity_is_goal", "direction"),
    [
        ("GUIDES_GOAL|outgoing|goal.a.b", False, "outgoing"),
        ("GUIDED_BY_PRINCIPLE|outgoing|principle.a.b", True, "incoming"),
    ],
)
def test_a_rewritten_key_decodes_to_the_edge_the_retraction_deletes(
    old: str, entity_is_goal: bool, direction: str
) -> None:
    """The point of the rewrite: the ingestion can address the migrated edge."""
    (key,) = rewritten_keys([old], entity_is_goal=entity_is_goal)

    edge = parse_authored_edge(key)

    assert edge is not None
    assert (edge.rel_type, edge.direction) == (RelationshipName.SUPPORTS_GOAL, direction)
    assert edge.target_uid == old.rsplit("|", 1)[1]


def test_the_retired_type_itself_decodes_to_no_edge() -> None:
    """Why the rewrite is needed: the old principle-side key addresses nothing."""
    assert parse_authored_edge("GUIDES_GOAL|outgoing|goal.a.b") is None
