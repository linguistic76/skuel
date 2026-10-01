"""
Choice Cypher fragments — pending and decided, as the model defines them.

``Choice.is_decided`` / ``Choice.is_pending`` are the definition; these two
predicates are their one Cypher spelling. Decided and pending are not status
values — a Choice's statuses are DRAFT / ACTIVE / COMPLETED / ARCHIVED — so a
reader that compares ``status`` alone answers a different question. Every
statement that counts or lists pending or decided choices composes these: the
Choices backend's stats and list reads, and the user context's pending-choice
read. A copy of the predicate is a second definition that drifts — compose,
never restate.

``tests/integration/test_choice_pending_decided_reads.py`` holds each composing
read to the rows the model's methods select.
"""

from __future__ import annotations

from core.models.enums.entity_enums import EntityStatus

from ._helpers import validate_identifier


def build_choice_decided_predicate(alias: str) -> str:
    """``Choice.is_decided`` as a boolean Cypher expression on ``alias``.

    A decision is recorded (``decided_at``) or the choice is COMPLETED. A decided
    choice stays ACTIVE until it is completed.
    """
    validate_identifier(alias, "alias")
    return f"({alias}.decided_at IS NOT NULL OR {alias}.status = '{EntityStatus.COMPLETED.value}')"


def build_choice_pending_predicate(alias: str) -> str:
    """``Choice.is_pending`` as a boolean Cypher expression on ``alias``.

    Not decided and not ARCHIVED. A node with no status reads as pending, as the
    model defaults a missing status to DRAFT.
    """
    validate_identifier(alias, "alias")
    return (
        f"({alias}.decided_at IS NULL AND NOT coalesce({alias}.status, '') IN "
        f"['{EntityStatus.COMPLETED.value}', '{EntityStatus.ARCHIVED.value}'])"
    )
