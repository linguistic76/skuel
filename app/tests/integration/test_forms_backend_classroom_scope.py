"""The classroom scope on the forms backend, executed against a real Neo4j.

``test_unscoped_uid_read_ownership.py`` proves the *wiring* — that the route
threads a scope through the service into the backend — using a Python stand-in
for the query. That stand-in cannot fail the way Cypher fails, so it says nothing
about the predicate itself. These tests run the real
``get_submissions_for_template`` / ``count_submissions`` against the graph.

Each case pairs with a **positive control**: the unscoped call must return the
row the scoped call withholds. Without it a query that matched nothing at all —
a mistyped label, a reversed MEMBER_OF direction, a property that is never set —
would satisfy every "must not see" assertion and read as a working boundary.

The scope is **entity-level**: a teacher reaches a submission because *that
submission* was shared into a classroom they own, not because they happen to
teach its author. A student may study in several classrooms, so the two are not
the same question — see ``test_form_submission_access_gate.py``, which pins that
distinction directly.

Covers the shapes the Python stand-in structurally cannot reach:

- a submission shared with TWO active groups the same teacher owns, which is why
  the predicate is ``EXISTS { ... }`` rather than an extra ``MATCH`` (a join
  would return it once per group);
- an INACTIVE group, whose exclusion lives entirely in the Cypher;
- the direction of the OWNS edge, which no Python stub would get wrong.
"""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.backends.forms_backends import (
    FormSubmissionBackend,
    FormTemplateBackend,
)
from core.models.enums.neo_labels import NeoLabel
from core.models.forms.form_submission import FormSubmission
from core.models.forms.form_template import FormTemplate

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

P = "fcs_"  # namespace for every node this module creates

TEACHER_A = f"{P}teacher_a"
TEACHER_B = f"{P}teacher_b"
STUDENT_1 = f"{P}student_1"  # in TWO active groups Teacher A owns
STUDENT_2 = f"{P}student_2"  # in Teacher B's group
STUDENT_3 = f"{P}student_3"  # in an INACTIVE group Teacher A owns
TEMPLATE = f"{P}ft"
SUB_1, SUB_2, SUB_3, SUB_ORPHAN = f"{P}fs1", f"{P}fs2", f"{P}fs3", f"{P}fs4"

_CLEANUP = "MATCH (n) WHERE n.uid STARTS WITH $prefix DETACH DELETE n"

_SEED = """
CREATE (ta:User {uid: $teacher_a, display_name: 'Teacher A'})
CREATE (tb:User {uid: $teacher_b, display_name: 'Teacher B'})
CREATE (s1:User {uid: $student_1, display_name: 'Student One'})
CREATE (s2:User {uid: $student_2, display_name: 'Student Two'})
CREATE (s3:User {uid: $student_3, display_name: 'Student Three'})
CREATE (g1:Group {uid: $g1, is_active: true})
CREATE (g2:Group {uid: $g2, is_active: true})
CREATE (g3:Group {uid: $g3, is_active: false})
CREATE (g4:Group {uid: $g4, is_active: true})
CREATE (ta)-[:OWNS]->(g1)
CREATE (ta)-[:OWNS]->(g2)
CREATE (ta)-[:OWNS]->(g3)
CREATE (tb)-[:OWNS]->(g4)
CREATE (s1)-[:MEMBER_OF]->(g1)
CREATE (s1)-[:MEMBER_OF]->(g2)
CREATE (s3)-[:MEMBER_OF]->(g3)
CREATE (s2)-[:MEMBER_OF]->(g4)
CREATE (ft:Entity {uid: $template, entity_type: 'form_template', title: 'Survey'})
CREATE (f1:Entity {uid: $sub_1, entity_type: 'form_submission', title: 'S1',
                   created_at: '2026-07-01T10:00:00'})
CREATE (f2:Entity {uid: $sub_2, entity_type: 'form_submission', title: 'S2',
                   created_at: '2026-07-02T10:00:00'})
CREATE (f3:Entity {uid: $sub_3, entity_type: 'form_submission', title: 'S3',
                   created_at: '2026-07-03T10:00:00'})
CREATE (f4:Entity {uid: $sub_orphan, entity_type: 'form_submission', title: 'Orphan',
                   created_at: '2026-07-04T10:00:00'})
CREATE (s1)-[:OWNS]->(f1)
CREATE (s2)-[:OWNS]->(f2)
CREATE (s3)-[:OWNS]->(f3)
CREATE (f1)-[:RESPONDS_TO_FORM]->(ft)
CREATE (f2)-[:RESPONDS_TO_FORM]->(ft)
CREATE (f3)-[:RESPONDS_TO_FORM]->(ft)
CREATE (f4)-[:RESPONDS_TO_FORM]->(ft)
// The audience each submission carries — what a teacher's reach is decided by.
// Membership alone grants nothing: the scope asks whether *this submission* was
// shared into a classroom the teacher owns, so each answer is shared with its
// author's groups exactly as submit-time resolution would have done. f4 has no
// owner and so no audience.
CREATE (f1)-[:SHARED_WITH_GROUP]->(g1)
CREATE (f1)-[:SHARED_WITH_GROUP]->(g2)
CREATE (f2)-[:SHARED_WITH_GROUP]->(g4)
CREATE (f3)-[:SHARED_WITH_GROUP]->(g3)
"""

_SEED_PARAMS = {
    "teacher_a": TEACHER_A,
    "teacher_b": TEACHER_B,
    "student_1": STUDENT_1,
    "student_2": STUDENT_2,
    "student_3": STUDENT_3,
    "g1": f"{P}g1",
    "g2": f"{P}g2",
    "g3": f"{P}g3",
    "g4": f"{P}g4",
    "template": TEMPLATE,
    "sub_1": SUB_1,
    "sub_2": SUB_2,
    "sub_3": SUB_3,
    "sub_orphan": SUB_ORPHAN,
}


@pytest_asyncio.fixture
async def forms_graph(neo4j_driver: Any) -> Any:
    """Seed one template with four submissions across three classrooms."""
    async with neo4j_driver.session() as session:
        await session.run(_CLEANUP, {"prefix": P})
        await session.run(_SEED, _SEED_PARAMS)
    yield neo4j_driver
    async with neo4j_driver.session() as session:
        await session.run(_CLEANUP, {"prefix": P})


@pytest.fixture
def submissions(forms_graph: Any) -> FormSubmissionBackend:
    return FormSubmissionBackend(
        forms_graph, NeoLabel.ENTITY, FormSubmission, base_label=NeoLabel.ENTITY
    )


@pytest.fixture
def templates(forms_graph: Any) -> FormTemplateBackend:
    return FormTemplateBackend(
        forms_graph, NeoLabel.ENTITY, FormTemplate, base_label=NeoLabel.ENTITY
    )


async def _uids(backend: FormSubmissionBackend, teacher: str | None) -> list[str]:
    result = await backend.get_submissions_for_template(TEMPLATE, teacher)
    assert not result.is_error, result.error
    return [row["uid"] for row in result.value]


class TestUnscopedReadIsTheControl:
    """ADMIN keeps the whole corpus — the control every other case rests on."""

    async def test_unscoped_returns_every_submission(
        self, submissions: FormSubmissionBackend
    ) -> None:
        assert sorted(await _uids(submissions, None)) == sorted([SUB_1, SUB_2, SUB_3, SUB_ORPHAN])

    async def test_unscoped_count_matches(self, templates: FormTemplateBackend) -> None:
        result = await templates.count_submissions(TEMPLATE, None)
        assert not result.is_error
        assert result.value == 4

    async def test_unscoped_orders_newest_first(self, submissions: FormSubmissionBackend) -> None:
        """Scoping must not disturb the ordering contract."""
        assert await _uids(submissions, None) == [SUB_ORPHAN, SUB_3, SUB_2, SUB_1]


class TestScopedReadStopsAtTheClassroom:
    async def test_teacher_sees_only_their_own_students_submission(
        self, submissions: FormSubmissionBackend
    ) -> None:
        assert await _uids(submissions, TEACHER_A) == [SUB_1]

    async def test_scope_is_symmetric(self, submissions: FormSubmissionBackend) -> None:
        """Teacher B is confined the other way — not a blanket empty result."""
        assert await _uids(submissions, TEACHER_B) == [SUB_2]

    async def test_scoped_count_matches_scoped_rows(
        self, submissions: FormSubmissionBackend, templates: FormTemplateBackend
    ) -> None:
        """The badge and the list must not disagree."""
        result = await templates.count_submissions(TEMPLATE, TEACHER_A)
        assert not result.is_error
        assert result.value == len(await _uids(submissions, TEACHER_A)) == 1

    async def test_unknown_teacher_sees_nothing(self, submissions: FormSubmissionBackend) -> None:
        assert await _uids(submissions, f"{P}no_such_teacher") == []

    async def test_scoped_read_preserves_submitter_columns(
        self, submissions: FormSubmissionBackend
    ) -> None:
        """The scoped branch must return the same row shape as the unscoped one.

        The page reads `user_name` and `form_data` off these rows; a scoped query
        that dropped a column would render "Unknown" for a legitimate student.
        """
        result = await submissions.get_submissions_for_template(TEMPLATE, TEACHER_A)
        assert not result.is_error
        row = result.value[0]
        assert row["user_uid"] == STUDENT_1
        assert row["user_name"] == "Student One"
        assert row["uid"] == SUB_1


class TestPredicateShape:
    """The two cases only real Cypher can decide."""

    async def test_two_active_groups_yield_one_row(
        self, submissions: FormSubmissionBackend
    ) -> None:
        """Student 1's submission is shared with g1 AND g2, both Teacher A's.

        An extra MATCH instead of EXISTS would return this submission twice —
        the page would show the same student's answers as two rows and the count
        badge would read 2. Positive control: the unscoped read sees it once.
        """
        assert await _uids(submissions, TEACHER_A) == [SUB_1]
        assert (await _uids(submissions, None)).count(SUB_1) == 1

    async def test_inactive_group_does_not_grant_access(
        self, submissions: FormSubmissionBackend
    ) -> None:
        """Student 3's submission is shared with a group Teacher A owns —
        but that group is not active.

        Paired with its control: the submission does exist and is readable
        unscoped, so an empty scoped result is the predicate working rather than
        a seed that never landed.
        """
        assert SUB_3 not in await _uids(submissions, TEACHER_A)
        assert SUB_3 in await _uids(submissions, None)

    async def test_ownerless_submission_is_not_attributable(
        self, submissions: FormSubmissionBackend
    ) -> None:
        """A submission with no owner carries no audience, so no teacher reaches it.

        Under an entity-level scope this follows from the *audience*, not from
        the missing OWNS edge: nothing was ever shared into a classroom. The
        unscoped branch keeps it (OPTIONAL MATCH) for ADMIN — asserted here so
        the scoped exclusion is shown to be the scope, not a lost row.
        """
        assert SUB_ORPHAN not in await _uids(submissions, TEACHER_A)
        assert SUB_ORPHAN not in await _uids(submissions, TEACHER_B)
        assert SUB_ORPHAN in await _uids(submissions, None)

    async def test_membership_direction_is_not_reversible(
        self, forms_graph: Any, submissions: FormSubmissionBackend
    ) -> None:
        """A teacher who is a MEMBER_OF a group does not thereby own it.

        Pins the predicate's direction: the grant runs SHARED_WITH_GROUP from
        the submission to a group the teacher OWNS. A predicate that accepted
        any edge to the group would let Teacher B — made a member of Teacher A's
        group here — read Student 1's answers.
        """
        async with forms_graph.session() as session:
            await session.run(
                "MATCH (t:User {uid: $teacher}), (g:Group {uid: $group}) "
                "CREATE (t)-[:MEMBER_OF]->(g)",
                {"teacher": TEACHER_B, "group": f"{P}g1"},
            )

        assert await _uids(submissions, TEACHER_B) == [SUB_2]
        assert SUB_1 not in await _uids(submissions, TEACHER_B)
