"""Guards for the live-graph vocabulary audit.

The audit exists because SKUEL030/CYP011 check the vocabulary in *source* Cypher
while nothing checked the vocabulary in the *database* — and the gap is silent:
Neo4j answers an unknown label or relationship type with zero rows, never an
error. Its first run found a live ``SUPPORTS_HABIT`` edge that two code comments
asserted "was never written" (#1010).

The categorizer is pure so it can be tested without a database, which is also
what lets these tests pin the one judgement call in the script: a stray holding
ZERO rows is registry residue, not drift.
"""

from __future__ import annotations

import sys
from pathlib import Path

# scripts/ has no __init__.py — add it to sys.path for import (same as the
# sibling audit_graph_hygiene suite).
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from audit_graph_vocabulary import (  # type: ignore[import-not-found]
    Stray,
    classify_strays,
)

from core.models.enums import EntityType
from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName


def _canonical() -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
    """A live graph whose every value is enum-backed."""
    return (
        {NeoLabel.PATH_STEP.value: 25, NeoLabel.KU.value: 123},
        {RelationshipName.HAS_STEP.value: 40},
        {EntityType.PATH_STEP.value: 25, EntityType.KU.value: 123},
    )


def test_canonical_graph_yields_no_strays() -> None:
    assert classify_strays(*_canonical()) == []


def test_relationship_holding_data_is_drift() -> None:
    """The real find: an edge type no longer in the enum, still holding a row."""
    labels, rels, ets = _canonical()
    rels["SUPPORTS_HABIT"] = 1

    strays = classify_strays(labels, rels, ets)

    assert [(s.kind, s.value, s.count) for s in strays] == [("relationship", "SUPPORTS_HABIT", 1)]
    assert strays[0].holds_data, (
        "an edge type with rows is unreachable data, not residue — it must fail the audit"
    )


def test_zero_row_stray_is_residue_not_drift() -> None:
    """Neo4j keeps listing a name after its last row is deleted.

    Failing on that would make the audit permanently red for something harmless
    and outside the app's control — the guard has to be scored by what it KEEPS,
    not only by what it catches.
    """
    labels, rels, ets = _canonical()
    labels["Lesson"] = 0
    labels["Expense"] = 0

    strays = classify_strays(labels, rels, ets)

    assert {s.value for s in strays} == {"Lesson", "Expense"}
    assert not any(s.holds_data for s in strays)


def test_drift_and_residue_are_separable() -> None:
    """Both present: exactly one fails the run."""
    labels, rels, ets = _canonical()
    labels["Lesson"] = 0
    rels["SUPPORTS_HABIT"] = 1
    ets["learning_step"] = 3

    strays = classify_strays(labels, rels, ets)
    drift = [s for s in strays if s.holds_data]
    residue = [s for s in strays if not s.holds_data]

    assert {(s.kind, s.value) for s in drift} == {
        ("relationship", "SUPPORTS_HABIT"),
        ("entity_type", "learning_step"),
    }
    assert [s.value for s in residue] == ["Lesson"]


def test_non_entity_labels_are_not_reported() -> None:
    """Infrastructure labels are not entity vocabulary and never were.

    :Content is the chunk shadow (G13); :User/:Group/:Session predate NeoLabel.
    Reporting them would be noise that trains the reader to ignore the output.
    """
    labels, rels, ets = _canonical()
    labels.update({"Content": 400, "User": 3, "Session": 12, "IngestionMetadata": 550})

    assert classify_strays(labels, rels, ets) == []


def test_entity_type_stray_is_caught_even_with_a_valid_label() -> None:
    """The discriminator is checked independently of the label.

    ``audit_graph_hygiene``'s F1 compares entity_type AGAINST the domain label and
    skips any node without exactly one known label — so a bad value on an
    unlabelled or oddly-labelled node falls through it. This audit asks the
    simpler question: is the value in the enum at all?
    """
    labels, rels, ets = _canonical()
    ets["learning_step"] = 25

    strays = classify_strays(labels, rels, ets)

    assert [(s.kind, s.value, s.count) for s in strays] == [("entity_type", "learning_step", 25)]


def test_stray_ordering_is_stable() -> None:
    """Output order must not depend on dict insertion — diffs get read by humans."""
    labels, rels, ets = _canonical()
    labels.update({"Zeta": 0, "Alpha": 0})

    assert [s.value for s in classify_strays(labels, rels, ets)] == ["Alpha", "Zeta"]


def test_stray_is_frozen() -> None:
    """A finding is a record of what was observed; nothing should edit it in place."""
    stray = Stray("relationship", "SUPPORTS_HABIT", 1)
    try:
        stray.count = 0  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("Stray must be immutable")
