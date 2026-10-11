"""
Learning-loop Cypher fragments — the derived review standing of a UserEntry.

The "reviewed" badges are derived, never stored (ADR-088 §1, Submit & Share arc
R2): an entry is *reviewed* when a report with an ``assessment_outcome``
stands on it, and *revised after feedback* when an earlier entry in the same
exchange — same owner, same ``turn_in_exercise_uid`` — carries such a report
older than this entry. One subquery authors both columns, and every reader
that badges an entry composes it: the two Shared-page list statements, the
GradeBook summaries statement (on the exchange's latest entry) and the
recipient card's one-entry read. A copy of the predicate is a second
derivation that drifts — compose, never restate.

Timestamp shapes differ by writer: ``UserEntry.created_at`` is an ISO string
(the mapper's ``isoformat()``), ``EntryReport.created_at`` a native
``datetime($now)``. A raw ``<`` between them is NULL — a never-matching
predicate — so the entry side is parsed with ``datetime()`` (which accepts a
string or a temporal alike). Both writers stamp naive local time, so the two
sides read as the same clock.
"""

from __future__ import annotations

from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName

from ._helpers import validate_identifier


def build_review_standing_subquery(entity_alias: str = "entity") -> str:
    """The ``CALL`` block deriving ``reviewed_by`` and ``revised_after_feedback`` for one entry.

    Composed after the statement has bound ``entity_alias`` to a UserEntry
    node; it introduces the two columns and no parameter. ``reviewed_by`` is
    the ``processor_type`` of the newest outcome-bearing report on the entry
    (NULL when none); ``revised_after_feedback`` is true when an earlier
    entry of the same owner in the same exchange has such a report older than
    this entry. An entry that is not a turn-in (no snapshot) is never
    "revised after feedback".
    """
    validate_identifier(entity_alias, context="entity alias")
    entity = NeoLabel.ENTITY.value
    report = f"{entity}:{NeoLabel.ENTRY_REPORT.value}"
    entry = f"{entity}:{NeoLabel.USER_ENTRY.value}"
    report_for = RelationshipName.REPORT_FOR.value
    a = entity_alias
    return f"""CALL ({a}) {{
        OPTIONAL MATCH (latest_report:{report})-[:{report_for}]->({a})
            WHERE latest_report.assessment_outcome IS NOT NULL
        WITH latest_report,
             {a}.uid AS self_uid,
             {a}.user_uid AS self_owner_uid,
             {a}.turn_in_exercise_uid AS self_exchange_uid,
             {a}.created_at AS self_created_at
        ORDER BY datetime(latest_report.created_at) DESC
        LIMIT 1
        RETURN latest_report.processor_type AS reviewed_by,
               EXISTS {{
                   MATCH (prior:{entry})<-[:{report_for}]-(prior_report:{report})
                   WHERE self_exchange_uid IS NOT NULL
                     AND prior.uid <> self_uid
                     AND prior.user_uid = self_owner_uid
                     AND prior.turn_in_exercise_uid = self_exchange_uid
                     AND prior_report.assessment_outcome IS NOT NULL
                     AND prior_report.created_at < datetime(self_created_at)
               }} AS revised_after_feedback
    }}"""


__all__ = ["asks_teacher", "build_review_standing_subquery", "feedback_requests_subquery"]


_OWNS = RelationshipName.OWNS.value
_SUBMITTED_TO_GROUP = RelationshipName.SUBMITTED_TO_GROUP.value
_SUBMITTED_TO_TEACHER = RelationshipName.SUBMITTED_TO_TEACHER.value
_FULFILLS_EXERCISE = RelationshipName.FULFILLS_EXERCISE.value
_GROUP = NeoLabel.GROUP.value


def asks_teacher(entry_alias: str, teacher_alias: str) -> str:
    """THE feedback-request predicate: does this entry ask this teacher for feedback?

    True when the entry was submitted to an ACTIVE group the teacher ``OWNS``
    (``SUBMITTED_TO_GROUP``), or submitted to the teacher directly
    (``SUBMITTED_TO_TEACHER`` — ADR-088 §9). Every teacher-side reader and writer
    of a feedback request composes this one predicate — the review queue, the
    review detail, the review writes' authority, the exercise and student lists
    and the supersede rule — so a teacher reads and acts on exactly the requests
    sent to them, whichever of the two targets carried it. Both aliases must be
    bound by the caller; a share (``SHARED_WITH_GROUP``) never satisfies it.
    """
    validate_identifier(entry_alias, context="entry alias")
    validate_identifier(teacher_alias, context="teacher alias")
    return (
        f"(EXISTS {{ MATCH ({entry_alias})-[:{_SUBMITTED_TO_GROUP}]->"
        f"(:{_GROUP} {{is_active: true}})<-[:{_OWNS}]-({teacher_alias}) }}"
        f" OR EXISTS {{ MATCH ({entry_alias})-[:{_SUBMITTED_TO_TEACHER}]->({teacher_alias}) }})"
    )


def feedback_requests_subquery(teacher_alias: str, entry_alias: str) -> str:
    """The ``CALL`` block enumerating every UserEntry that asks the bound teacher for feedback.

    The enumerating twin of ``asks_teacher``: one row per entry submitted to an
    active group the teacher ``OWNS`` or submitted to the teacher directly, each
    entry once (``UNION`` deduplicates an entry that reached the teacher both
    ways). Composed after the statement binds ``teacher_alias``; introduces
    ``entry_alias``. A teacher with no requests yields no rows — wrap it in an
    aggregating subquery where the statement must keep its row.
    """
    validate_identifier(teacher_alias, context="teacher alias")
    validate_identifier(entry_alias, context="entry alias")
    entry = f"{NeoLabel.ENTITY.value}:{NeoLabel.USER_ENTRY.value}"
    t, e = teacher_alias, entry_alias
    return f"""CALL ({t}) {{
        MATCH ({t})-[:{_OWNS}]->(:{_GROUP} {{is_active: true}})<-[:{_SUBMITTED_TO_GROUP}]-({e}:{entry})
        RETURN {e}
      UNION
        MATCH ({e}:{entry})-[:{_SUBMITTED_TO_TEACHER}]->({t})
        RETURN {e}
    }}"""


# THE supersede rule for pending feedback requests — one predicate, read by the
# review queue, its dashboard badge twin, the students summary and the teacher
# detail, and held by the review writers themselves (their write statements refuse a
# superseded copy), so no surface disagrees on what awaits review.
#
# A copy is superseded by a newer sibling the SAME teacher can see (a
# ``teacher_review`` entry of the same student that asks this teacher for
# feedback — ``asks_teacher``), in either of two lineages:
#
#   * the exercise lineage — the same turn-in snapshot ``turn_in_exercise_uid``
#     (the key that outlives the exercise, Submit & Share arc R12), newer by the
#     ``FULFILLS_EXERCISE`` edge revision where the edge still exists, else by
#     ``created_at``;
#   * the note lineage — frozen copies filed from the same vault note
#     (``submitted_from_uid``, R9), newer by ``created_at``.
#
# Whatever the newer copy's status (a reviewed rev 2 retires a pending rev 1).
# Siblings the teacher cannot see never supersede: a PRIVATE ``llm_summary``
# entry, a copy sent only to another teacher's group, one locked in a group this
# teacher deactivated. An entry in neither lineage always passes through.
#
# The caller binds, in a WITH before the predicate: ``teacher``, ``student``
# (the entry's owner), ``copy_uid``, ``copy_lineage`` (the entry's
# ``turn_in_exercise_uid``), ``copy_note`` (its ``submitted_from_uid``),
# ``copy_revision`` (its edge revision, 0 without one) and ``copy_created_at``.
SUPERSEDED_COPY = f"""EXISTS {{
    MATCH (student)-[:{_OWNS}]->(newer:Entity:UserEntry)
    WHERE newer.uid <> copy_uid
      AND newer.pipeline = $pipeline
      AND {asks_teacher("newer", "teacher")}
      AND ((copy_lineage IS NOT NULL
            AND newer.turn_in_exercise_uid = copy_lineage
            AND (coalesce(head([(newer)-[nr:{_FULFILLS_EXERCISE}]->(:Entity:Exercise) | nr.revision]), 0)
                   > copy_revision
                 OR (coalesce(head([(newer)-[nr:{_FULFILLS_EXERCISE}]->(:Entity:Exercise) | nr.revision]), 0)
                       = copy_revision
                     AND datetime(newer.created_at) > datetime(copy_created_at))))
           OR (copy_note IS NOT NULL
               AND newer.submitted_from_uid = copy_note
               AND datetime(newer.created_at) > datetime(copy_created_at)))
}}"""


def superseded_copy_bindings(entry_alias: str) -> str:
    """The ``copy_*`` projections ``SUPERSEDED_COPY`` reads, for one bound entry.

    Composed into a WITH beside ``teacher`` and ``student`` (the entry's owner);
    the edge revision is read by pattern comprehension, so the projection never
    multiplies rows.
    """
    validate_identifier(entry_alias)
    return (
        f"{entry_alias}.uid AS copy_uid, "
        f"{entry_alias}.turn_in_exercise_uid AS copy_lineage, "
        f"{entry_alias}.submitted_from_uid AS copy_note, "
        f"coalesce(head([({entry_alias})-[copy_edge:{_FULFILLS_EXERCISE}]->(:Entity:Exercise) "
        f"| copy_edge.revision]), 0) AS copy_revision, "
        f"{entry_alias}.created_at AS copy_created_at"
    )
