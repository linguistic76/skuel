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
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

# scripts/ has no __init__.py — add it to sys.path for import (same as the
# sibling audit_graph_hygiene suite).
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from audit_graph_vocabulary import (  # type: ignore[import-not-found]
    SchemaHolder,
    Stray,
    classify_strays,
    normalize_entity_type,
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


def test_non_string_entity_type_is_reported_not_crashed() -> None:
    """A corrupt value is what this audit exists to catch — it must not kill it.

    ``entity_type`` is a free-form property, so a bad write can leave a list, a
    number or a boolean. A raw dict key would be unhashable for a list and would
    break ``sorted()`` on mixed types, so the audit would crash on precisely the
    input it was built to surface (Codex P2, #1010).
    """
    assert normalize_entity_type("ku") == "ku"

    for corrupt in ([1, 2], 42, True, 3.5):
        rendered = normalize_entity_type(corrupt)
        assert isinstance(rendered, str)
        assert rendered.startswith("<non-string ")
        # It must be unable to collide with a real member, so it lands in strays.
        assert rendered not in {t.value for t in EntityType}

    labels, rels, ets = _canonical()
    ets[normalize_entity_type([1, 2])] = 1
    ets[normalize_entity_type(42)] = 1

    strays = classify_strays(labels, rels, ets)
    assert len(strays) == 2
    assert all(s.kind == "entity_type" and s.holds_data for s in strays)


def test_entity_type_scan_is_scoped_to_domain_nodes_exactly() -> None:
    """The scan must be neither narrower nor wider than "domain nodes".

    NARROWER (`MATCH (n:Entity)`) misses the realistic corruption: the backfill
    migrations key on DOMAIN labels (``MATCH (n:Task) ... SET n.entity_type``),
    so ``(:Task {entity_type: 'x'})`` with no base label would exit clean.

    WIDER (every node with the property) is a false positive: an
    :IngestionError records which entity type a failed FILE was about, and an
    edge-YAML failure stores the literal "edge". That is metadata, not
    vocabulary, and would turn the audit red on a clean domain graph.

    Both directions were live findings on this PR (Codex P2, twice, #1010), which is
    why the scope is pinned on the query text — a behavioural test on the
    current corpus passes against every one of the three versions.
    """
    import inspect

    import audit_graph_vocabulary  # type: ignore[import-not-found]

    source = inspect.getsource(audit_graph_vocabulary.fetch_live_vocabulary)
    assert "n:Entity OR any(lbl IN labels(n) WHERE lbl IN $domain_labels)" in source, (
        "the entity_type scan must cover :Entity plus EntityType-backed domain labels"
    )

    # The label set is enum-sourced, so a new EntityType widens the scan for free.
    domain_labels = audit_graph_vocabulary.domain_label_values()
    assert NeoLabel.from_entity_type(EntityType.TASK).value in domain_labels
    assert NeoLabel.from_entity_type(EntityType.PATH_STEP).value in domain_labels
    assert "IngestionError" not in domain_labels, (
        "an ingestion-metadata label must never be treated as domain vocabulary"
    )
    assert domain_labels == sorted(set(domain_labels)), "deduped and ordered"


def test_live_names_are_parameterized_never_interpolated() -> None:
    """Identifiers must be bound as parameters, not quoted into the query text.

    Backtick-quoting is NOT sufficient: Cypher decodes ``\\uXXXX`` escapes inside
    a quoted identifier, so a label whose literal characters are
    ``Esc\\u0060Probe`` is re-read as a backtick and closes the identifier early.
    The audit crashed with CypherSyntaxError on exactly that name — reproduced by
    creating it with a dynamic-label CREATE (Codex P2, #1010).

    Doubling backticks cannot fix it, and decode-then-double would resolve to a
    DIFFERENT label than the one on disk. Parameters remove the question, which
    is also what CYP003 asks of every other query in this repo.
    """
    import inspect

    import audit_graph_vocabulary  # type: ignore[import-not-found]

    source = inspect.getsource(audit_graph_vocabulary.fetch_live_vocabulary)
    assert "MATCH (n:$($label)) RETURN count(n) AS c" in source
    assert "MATCH ()-[r:$($rel_type)]->() RETURN count(r) AS c" in source
    # No f-string may build a MATCH here: that is the only way a live name can
    # reach the query text instead of the parameter map.
    assert 'f"MATCH' not in source and "f'MATCH" not in source, (
        "a live name must never be interpolated into a MATCH — bind it instead"
    )
    assert not hasattr(audit_graph_vocabulary, "escape_identifier"), (
        "the escaping helper is gone — parameters replace it, and leaving a "
        "second path invites someone to reach for the broken one"
    )


def test_stray_is_frozen() -> None:
    """A finding is a record of what was observed; nothing should edit it in place.

    Asserts the SPECIFIC FrozenInstanceError: a broad ``except Exception`` would
    let an unrelated error masquerade as immutability and pass the test
    (SKUEL017's rule applies to tests too).
    """
    stray = Stray("relationship", "SUPPORTS_HABIT", 1)
    with pytest.raises(FrozenInstanceError):
        stray.count = 0  # type: ignore[misc]


def test_zero_row_stray_held_by_an_index_is_actionable(capsys: pytest.CaptureFixture[str]) -> None:
    """A zero-row stray is usually CLEANABLE, not inert — #1010 said otherwise.

    #1010 shipped "Neo4j lists a name until the store is compacted. Nothing to
    do." Both halves were false: an index or constraint keeps a label in
    db.labels() at ZERO rows, and dropping it removes the label immediately
    (measured: dropping exercise_report_uid_idx erased :ExerciseReport, and
    retiring five such indexes took the graph from 41 labels to 37).

    There is no DROP LABEL, so naming the holding index IS the fix instruction.
    """
    from audit_graph_vocabulary import report  # type: ignore[import-not-found]

    code = report(
        [Stray("label", "Lesson", 0)],
        verbose=False,
        live_labels={"Lesson": 0},
        live_relationships={},
        live_entity_types={},
        schema_holders={
            ("label", "Lesson"): [SchemaHolder("lesson_uid_idx", "INDEX", ("Lesson",))]
        },
    )
    # Schema hygiene, not data corruption: nothing is unreachable, so exit stays 0.
    assert code == 0
    # ...which is exactly why the exit code CANNOT be the assertion: both the
    # held and unheld paths return 0, so only the OUTPUT distinguishes them
    # (Codex P2, #1011 — the original version of this test was vacuous).
    out = capsys.readouterr().out
    assert "held alive by a stale INDEX/CONSTRAINT" in out
    assert "DROP INDEX `lesson_uid_idx` IF EXISTS;" in out


def test_report_accepts_absent_schema_holders() -> None:
    """The holder map is optional — a stray with no schema object is true residue."""
    from audit_graph_vocabulary import report  # type: ignore[import-not-found]

    code = report(
        [Stray("label", "Ghost", 0)],
        verbose=False,
        live_labels={"Ghost": 0},
        live_relationships={},
        live_entity_types={},
    )
    assert code == 0


def test_a_stray_holding_data_still_fails_regardless_of_holders() -> None:
    """The exit code means "is the data reachable" — holders must not soften it."""
    from audit_graph_vocabulary import report  # type: ignore[import-not-found]

    code = report(
        [Stray("relationship", "SUPPORTS_HABIT", 1)],
        verbose=False,
        live_labels={},
        live_relationships={"SUPPORTS_HABIT": 1},
        live_entity_types={},
        schema_holders={
            ("relationship", "SUPPORTS_HABIT"): [
                SchemaHolder("some_idx", "INDEX", ("SUPPORTS_HABIT",))
            ]
        },
    )
    assert code == 1


def test_holder_reports_the_correct_drop_command_per_kind() -> None:
    """A constraint needs DROP CONSTRAINT — DROP INDEX would just fail.

    Collapsing the two kinds hands the reader an instruction that does not work
    (Codex P2, #1011). The repo already has the constraint case on record:
    scripts/migrations/drop_stale_bootstrap_constraints_2026_07.cypher.
    """
    assert (
        SchemaHolder("lesson_uid_idx", "INDEX", tokens=("Lesson",)).remediation("Lesson")
        == "DROP INDEX `lesson_uid_idx` IF EXISTS;"
    )
    assert (
        SchemaHolder("document_uid_unique", "CONSTRAINT", tokens=("Document",)).remediation(
            "Document"
        )
        == "DROP CONSTRAINT `document_uid_unique` IF EXISTS;"
    )


def test_holders_are_keyed_by_token_namespace_not_name_alone(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A label and a relationship type may share a spelling.

    A RELATIONSHIP index on `Legacy` does not hold a `:Legacy` LABEL alive, so
    blaming it would send the reader to drop something that cannot fix their
    problem (Codex P2, #1011). The live graph does carry a relationship index,
    so the namespaces genuinely coexist.
    """
    from audit_graph_vocabulary import report  # type: ignore[import-not-found]

    holders = {("relationship", "Legacy"): [SchemaHolder("legacy_rel_idx", "INDEX", ("Legacy",))]}

    # The stray is a LABEL of the same name — it must NOT be attributed to the
    # relationship index, so it falls into the unheld (true residue) bucket.
    report(
        [Stray("label", "Legacy", 0)],
        verbose=False,
        live_labels={"Legacy": 0},
        live_relationships={},
        live_entity_types={},
        schema_holders=holders,
    )
    label_out = capsys.readouterr().out
    assert "legacy_rel_idx" not in label_out, (
        "a RELATIONSHIP index must never be offered as the fix for a LABEL"
    )
    assert "no schema object" in label_out

    # ...and the matching relationship stray IS attributed to it.
    report(
        [Stray("relationship", "Legacy", 0)],
        verbose=False,
        live_labels={},
        live_relationships={"Legacy": 0},
        live_entity_types={},
        schema_holders=holders,
    )
    assert "DROP INDEX `legacy_rel_idx` IF EXISTS;" in capsys.readouterr().out


def test_constraint_backed_index_is_not_reported_separately() -> None:
    """A uniqueness CONSTRAINT owns a backing INDEX of the same name.

    Reporting both advises `DROP INDEX` on it, which Neo4j REFUSES ("index
    belongs to constraint") — an instruction that errors is worse than none.
    `owningConstraint` is the discriminator, and the query filters on it, so the
    constraint row speaks for the pair. Found by this PR's own positive control,
    not by review.
    """
    import inspect

    import audit_graph_vocabulary  # type: ignore[import-not-found]

    source = inspect.getsource(audit_graph_vocabulary.fetch_schema_holders)
    assert "WHERE owningConstraint IS NULL" in source, (
        "constraint-backed indexes must be excluded, or the audit prints a DROP "
        "INDEX that Neo4j rejects"
    )


def test_mixed_index_is_never_recommended_for_dropping() -> None:
    """A fulltext index may span several labels — DROP would kill live search.

    If the object also covers a valid label, the remediation must be
    "recreate without", not "drop" (Codex P2, #1011). Advice that destroys
    working coverage is worse than the stray it removes.
    """
    stray_only = SchemaHolder("ghost_idx", "INDEX", tokens=("GhostProbe",))
    assert stray_only.covers_only("GhostProbe")
    assert stray_only.remediation("GhostProbe") == "DROP INDEX `ghost_idx` IF EXISTS;"

    mixed = SchemaHolder("mixed_ft", "INDEX", tokens=("GhostProbe", "PathStep"))
    assert not mixed.covers_only("GhostProbe")
    advice = mixed.remediation("GhostProbe")
    assert "do NOT drop" in advice and "PathStep" in advice
    assert not advice.startswith("DROP"), "a mixed index must never read as a DROP command"


def test_schema_names_are_quoted_in_the_generated_command() -> None:
    """Schema names may legally contain spaces or backticks (verified live).

    An unquoted name yields an invalid statement someone will paste and puzzle
    over; a name bearing a semicolon could change what the paste means.
    """
    assert (
        SchemaHolder("weird name idx", "INDEX", tokens=("X",)).remediation("X")
        == "DROP INDEX `weird name idx` IF EXISTS;"
    )
    assert (
        SchemaHolder("we`ird", "CONSTRAINT", tokens=("X",)).remediation("X")
        == "DROP CONSTRAINT `we``ird` IF EXISTS;"
    )


def test_escape_bearing_name_yields_manual_guidance_not_a_command() -> None:
    """Quoting cannot express a name Cypher will re-decode — so do not pretend.

    Cypher decodes escape sequences INSIDE a quoted identifier (#1010), so
    backtick-quoting `Esc\\u0060Probe` prints a command that targets a DIFFERENT
    object. `DROP INDEX` has no parameterized form to fall back on. #1011
    documented that caveat and still emitted the command; Codex was right that
    documenting a hazard is not removing it.

    Verified reachable: an index named `back\\slash` creates without complaint.
    """
    holder = SchemaHolder("back\\slash", "INDEX", tokens=("BsProbe",))
    advice = holder.remediation("BsProbe")

    assert advice.startswith("MANUAL:"), "must not read as a runnable command"
    assert "DROP INDEX `" not in advice, (
        "a name Cypher re-decodes must never be rendered as a pasteable DROP"
    )

    # A normal name still gets a real command.
    assert SchemaHolder("plain_idx", "INDEX", tokens=("X",)).remediation("X").startswith("DROP ")
