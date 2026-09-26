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
        ORDER BY latest_report.created_at DESC
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


__all__ = ["build_review_standing_subquery"]
