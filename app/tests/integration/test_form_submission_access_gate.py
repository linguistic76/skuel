"""The FormSubmission access gate, exercised against real Neo4j.

The route tests in ``routes/test_unscoped_uid_read_ownership.py`` fake the
backend, so they prove the *handler* asks the right question but cannot prove
the Cypher answers it. That gap matters here specifically: an unknown label or
relationship name makes Neo4j match **zero rows** rather than error, and a gate
that returns nothing reads as a confident refusal. Every route test would still
pass while the page refused everyone.

So these run the real queries over a seeded multi-classroom graph:

    Teacher A owns group X   ─┐
    Teacher B owns group Y   ─┼─ Student 1 is a member of BOTH X and Y
    Teacher C owns group Z   ─┘   (permitted — MAX_STUDENT_GROUPS is 4)

    fs_shared_x   SHARED_WITH_GROUP → X only
    fs_unshared   no audience at all

Teacher B is the case that matters: they genuinely teach Student 1, so a
student-granularity predicate admits them, and only an entity-level one does
not. Each assertion is paired with a positive control — a query that returns
nothing for everybody proves nothing.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.backends.forms_backends import FormSubmissionBackend
from core.models.enums.neo_labels import NeoLabel
from core.models.forms.form_submission import FormSubmission

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

PREFIX = "fsgate"
TEACHER_A, TEACHER_B, TEACHER_C = f"{PREFIX}_ta", f"{PREFIX}_tb", f"{PREFIX}_tc"
STUDENT_1 = f"{PREFIX}_s1"
GROUP_X, GROUP_Y, GROUP_Z = f"{PREFIX}_gx", f"{PREFIX}_gy", f"{PREFIX}_gz"
GROUP_INACTIVE = f"{PREFIX}_g_inactive"
TEMPLATE = f"{PREFIX}_ft"
PATH_STEP = f"{PREFIX}_ps"
STANDALONE_TEMPLATE = f"{PREFIX}_ft_standalone"
FS_SHARED_X = f"{PREFIX}_fs_shared_x"
FS_UNSHARED = f"{PREFIX}_fs_unshared"
FS_SHARED_INACTIVE = f"{PREFIX}_fs_shared_inactive"
# Audience-less, but answering a template no PathStep embeds — reachable only
# through the API, where an empty audience was the submitter's choice.
FS_STANDALONE = f"{PREFIX}_fs_standalone"

_SEED = """
CREATE (ta:User {uid: $ta}), (tb:User {uid: $tb}), (tc:User {uid: $tc}),
       (s1:User {uid: $s1}),
       (gx:Group {uid: $gx, is_active: true}),
       (gy:Group {uid: $gy, is_active: true}),
       (gz:Group {uid: $gz, is_active: true}),
       (gi:Group {uid: $gi, is_active: false}),
       (ft:Entity {uid: $ft, entity_type: 'form_template'}),
       (fs1:Entity {uid: $fs1, entity_type: 'form_submission', created_at: '2026-01-01'}),
       (fs2:Entity {uid: $fs2, entity_type: 'form_submission', created_at: '2026-01-02'}),
       (fs3:Entity {uid: $fs3, entity_type: 'form_submission', created_at: '2026-01-03'})
CREATE (ta)-[:OWNS]->(gx), (tb)-[:OWNS]->(gy), (tc)-[:OWNS]->(gz), (ta)-[:OWNS]->(gi)
// joined_at is a Neo4j datetime (GroupBackend.add_member), while a
// submission's created_at is an ISO *string* — the audience write compares
// them, so the seed has to carry both shapes faithfully or the test would
// exercise a comparison production never makes. Both memberships predate
// every submission below.
CREATE (s1)-[:MEMBER_OF {role: 'student', joined_at: datetime('2025-01-01T00:00:00')}]->(gx),
       (s1)-[:MEMBER_OF {role: 'student', joined_at: datetime('2025-01-01T00:00:00')}]->(gy)
CREATE (s1)-[:OWNS]->(fs1), (s1)-[:OWNS]->(fs2), (s1)-[:OWNS]->(fs3)
CREATE (fs1)-[:RESPONDS_TO_FORM]->(ft),
       (fs2)-[:RESPONDS_TO_FORM]->(ft),
       (fs3)-[:RESPONDS_TO_FORM]->(ft)
CREATE (fs1)-[:SHARED_WITH_GROUP]->(gx)
CREATE (fs3)-[:SHARED_WITH_GROUP]->(gi)
// The template is embedded in a PathStep, so its audience-less submissions are
// backfill candidates — the embedded route is the one that could not declare
// an audience. `_STANDALONE` below is the same template minus that edge.
CREATE (ps:Entity {uid: $ps, entity_type: 'path_step'})-[:EMBEDS_FORM]->(ft)
"""

# A template with no PathStep embedding it. An audience-less submission here can
# only have come through the API, where leaving the audience empty was a choice.
_STANDALONE = """
CREATE (ft2:Entity {uid: $ft2, entity_type: 'form_template'})
CREATE (fs:Entity {uid: $fs, entity_type: 'form_submission', created_at: '2026-01-04'})
CREATE (fs)-[:RESPONDS_TO_FORM]->(ft2)
WITH fs
MATCH (s1:User {uid: $s1})
CREATE (s1)-[:OWNS]->(fs)
"""

# `recipient_uids` on the submit API produces (teacher)-[:SHARES_WITH]->(entity)
# and nothing else — an explicitly chosen reader with no group edge anywhere.
_DIRECT_SHARE = """
MATCH (t:User {uid: $teacher}), (fs:Entity {uid: $fs})
CREATE (t)-[:SHARES_WITH {role: 'viewer'}]->(fs)
"""

_CLEANUP = f"MATCH (n) WHERE n.uid STARTS WITH '{PREFIX}' DETACH DELETE n"


@pytest_asyncio.fixture
async def gate_backend(neo4j_driver: Any):
    """Seed the multi-classroom graph and yield a real FormSubmissionBackend."""
    backend = FormSubmissionBackend(
        driver=neo4j_driver,
        label=NeoLabel.FORM_SUBMISSION,
        entity_class=FormSubmission,
        base_label=NeoLabel.ENTITY,
    )
    await backend.execute_query(_CLEANUP)
    await backend.execute_query(
        _SEED,
        {
            "ta": TEACHER_A,
            "tb": TEACHER_B,
            "tc": TEACHER_C,
            "s1": STUDENT_1,
            "gx": GROUP_X,
            "gy": GROUP_Y,
            "gz": GROUP_Z,
            "gi": GROUP_INACTIVE,
            "ft": TEMPLATE,
            "ps": PATH_STEP,
            "fs1": FS_SHARED_X,
            "fs2": FS_UNSHARED,
            "fs3": FS_SHARED_INACTIVE,
        },
    )
    await backend.execute_query(
        _STANDALONE,
        {"ft2": STANDALONE_TEMPLATE, "fs": FS_STANDALONE, "s1": STUDENT_1},
    )
    yield backend
    await backend.execute_query(_CLEANUP)


async def _granting_groups(backend: Any, submission_uid: str, teacher_uid: str) -> list[Any]:
    """The classrooms that granted the read — ``[]`` is the refusal.

    Values are returned unconverted: a direct share grants with a null
    ``group_uid``, and stringifying it would turn that grant into ``'None'``
    and read as a classroom name.
    """
    result = await backend.verify_teacher_submission_access(submission_uid, teacher_uid)
    assert result.is_ok, result.error
    return [row["group_uid"] for row in result.value or []]


async def _visible_uids(backend: Any, teacher_uid: str) -> list[str]:
    result = await backend.get_submissions_for_template(TEMPLATE, teacher_uid)
    assert result.is_ok, result.error
    return sorted(str(row["uid"]) for row in result.value or [])


class TestVerifyTeacherSubmissionAccess:
    """The detail page's gate."""

    async def test_teacher_holding_the_share_is_granted(self, gate_backend: Any) -> None:
        """The positive control. Without it, every refusal below is consistent
        with a query that simply never matches anything."""
        assert await _granting_groups(gate_backend, FS_SHARED_X, TEACHER_A) == [GROUP_X]

    async def test_second_teacher_of_the_same_student_is_refused(self, gate_backend: Any) -> None:
        """The residual hole. Teacher B owns group Y and Student 1 is in it, so
        ``verify_teacher_authority(TEACHER_B, STUDENT_1)`` would match — but the
        submission was shared with group X only."""
        assert await _granting_groups(gate_backend, FS_SHARED_X, TEACHER_B) == []

    async def test_unrelated_teacher_is_refused(self, gate_backend: Any) -> None:
        assert await _granting_groups(gate_backend, FS_SHARED_X, TEACHER_C) == []

    async def test_submission_with_no_audience_is_refused_even_to_its_teachers(
        self, gate_backend: Any
    ) -> None:
        """Why the write side had to change too: under this gate an unshared
        submission is readable by nobody, including the student's own teacher."""
        assert await _granting_groups(gate_backend, FS_UNSHARED, TEACHER_A) == []

    async def test_share_to_an_inactive_group_does_not_grant(self, gate_backend: Any) -> None:
        """Teacher A owns the inactive group and the submission is shared with
        it — only ``is_active`` separates this from the granted case."""
        assert await _granting_groups(gate_backend, FS_SHARED_INACTIVE, TEACHER_A) == []

    async def test_missing_submission_is_refused(self, gate_backend: Any) -> None:
        assert await _granting_groups(gate_backend, f"{PREFIX}_nope", TEACHER_A) == []

    async def test_a_refusal_returns_no_row_at_all(self, gate_backend: Any) -> None:
        """Refusals must be *empty*, not a row carrying a null.

        The service reads row presence as the grant, so a query shape that
        emits one null-valued row on no match fails **open** — it would admit
        every teacher to every submission. An unkeyed ``collect`` does exactly
        that (aggregation over zero input still yields a row), which is why the
        query keys its aggregation on ``fs``. Asserted on the raw rows, since
        ``[None]`` and ``[]`` are both falsy in a careless check.
        """
        for submission_uid, teacher in (
            (FS_SHARED_X, TEACHER_B),
            (FS_UNSHARED, TEACHER_A),
            (f"{PREFIX}_nope", TEACHER_A),
        ):
            result = await gate_backend.verify_teacher_submission_access(submission_uid, teacher)
            assert result.is_ok, result.error
            assert result.value == [], f"{submission_uid}/{teacher} returned {result.value!r}"

    async def test_direct_recipient_share_grants_without_any_group(self, gate_backend: Any) -> None:
        """``recipient_uids`` writes only ``SHARES_WITH``. A gate honouring the
        group edge alone would refuse the exact teacher the student picked.

        Teacher C is used precisely because they share no classroom with the
        submitter — the direct edge is the only thing that can grant this.
        """
        assert await _granting_groups(gate_backend, FS_UNSHARED, TEACHER_C) == []

        await gate_backend.execute_query(_DIRECT_SHARE, {"teacher": TEACHER_C, "fs": FS_UNSHARED})

        result = await gate_backend.verify_teacher_submission_access(FS_UNSHARED, TEACHER_C)
        assert result.is_ok, result.error
        rows = result.value or []
        assert len(rows) == 1
        # Granted, with no classroom to name.
        assert rows[0]["group_uid"] is None

    async def test_a_direct_share_to_someone_else_does_not_grant(self, gate_backend: Any) -> None:
        """The edge is per-recipient — sharing with Teacher C must not admit
        Teacher B, or the gate would be 'is this shared with anyone at all'."""
        await gate_backend.execute_query(_DIRECT_SHARE, {"teacher": TEACHER_C, "fs": FS_UNSHARED})
        assert await _granting_groups(gate_backend, FS_UNSHARED, TEACHER_B) == []

    async def test_group_grant_still_names_its_classroom(self, gate_backend: Any) -> None:
        """Adding the direct-share branch must not cost the group branch its
        logging column."""
        await gate_backend.execute_query(_DIRECT_SHARE, {"teacher": TEACHER_C, "fs": FS_SHARED_X})
        assert await _granting_groups(gate_backend, FS_SHARED_X, TEACHER_A) == [GROUP_X]


class TestTeacherScopedTemplateList:
    """The list page's gate — it must agree with the detail page's."""

    async def test_teacher_sees_only_what_is_shared_with_them(self, gate_backend: Any) -> None:
        assert await _visible_uids(gate_backend, TEACHER_A) == [FS_SHARED_X]

    async def test_second_teacher_of_the_same_student_sees_nothing(self, gate_backend: Any) -> None:
        assert await _visible_uids(gate_backend, TEACHER_B) == []

    async def test_unscoped_list_still_returns_everything(self, gate_backend: Any) -> None:
        """The admin view is unchanged — and this is the control proving the
        template and its three submissions really are in the graph, so the
        empty results above are refusals rather than a bad seed."""
        result = await gate_backend.get_submissions_for_template(TEMPLATE, None)
        assert result.is_ok, result.error
        assert sorted(str(row["uid"]) for row in result.value or []) == sorted(
            [FS_SHARED_X, FS_UNSHARED, FS_SHARED_INACTIVE]
        )

    async def test_rows_carry_the_submitter_columns(self, gate_backend: Any) -> None:
        """Both list queries share one row shaper; the page reads these keys."""
        result = await gate_backend.get_submissions_for_template(TEMPLATE, TEACHER_A)
        assert result.is_ok, result.error
        row = (result.value or [])[0]
        assert row["uid"] == FS_SHARED_X
        assert row["user_uid"] == STUDENT_1

    async def test_a_submission_shared_with_two_owned_groups_appears_once(
        self, gate_backend: Any
    ) -> None:
        """``EXISTS`` rather than a second ``MATCH`` — otherwise the row
        multiplies once per matching group and the page renders duplicates.

        Asserted as a count of *this* UID, not as the whole list: activating
        the second group also reveals the other submission shared with it, and
        an equality assertion would be measuring that instead.
        """
        await gate_backend.execute_query(
            "MATCH (g:Group {uid: $g}) SET g.is_active = true", {"g": GROUP_INACTIVE}
        )
        await gate_backend.execute_query(
            """
            MATCH (fs:Entity {uid: $fs}), (g:Group {uid: $g})
            CREATE (fs)-[:SHARED_WITH_GROUP]->(g)
            """,
            {"fs": FS_SHARED_X, "g": GROUP_INACTIVE},
        )

        visible = await _visible_uids(gate_backend, TEACHER_A)
        # Both of Teacher A's groups now grant this one submission.
        assert visible.count(FS_SHARED_X) == 1

    async def test_direct_recipient_sees_the_row(self, gate_backend: Any) -> None:
        """The list and the detail gate must admit the same set. If only the
        detail page honoured direct shares, a chosen teacher could open a
        submission they can never find."""
        assert await _visible_uids(gate_backend, TEACHER_C) == []

        await gate_backend.execute_query(_DIRECT_SHARE, {"teacher": TEACHER_C, "fs": FS_UNSHARED})

        assert await _visible_uids(gate_backend, TEACHER_C) == [FS_UNSHARED]

    async def test_a_row_granted_both_ways_appears_once(self, gate_backend: Any) -> None:
        """Two audience kinds on one submission is still one row."""
        await gate_backend.execute_query(_DIRECT_SHARE, {"teacher": TEACHER_A, "fs": FS_SHARED_X})
        assert (await _visible_uids(gate_backend, TEACHER_A)).count(FS_SHARED_X) == 1


class TestTeacherScopedSubmissionCount:
    """The card count on /teaching/forms — the third view of one dataset.

    It has to agree with the list it links to. A count that says 10 above a
    page showing 1 discloses how much activity exists in classrooms the caller
    cannot open, which is the same leak in aggregate form.
    """

    @pytest_asyncio.fixture
    async def template_backend(self, neo4j_driver: Any, gate_backend: Any):
        from adapters.persistence.neo4j.backends.forms_backends import FormTemplateBackend
        from core.models.forms.form_template import FormTemplate

        return FormTemplateBackend(
            driver=neo4j_driver,
            label=NeoLabel.FORM_TEMPLATE,
            entity_class=FormTemplate,
            base_label=NeoLabel.ENTITY,
        )

    async def _count(self, backend: Any, teacher_uid: str) -> int:
        result = await backend.count_submissions(TEMPLATE, teacher_uid)
        assert result.is_ok, result.error
        return int(result.value)

    async def test_counts_only_what_the_teacher_may_read(self, template_backend: Any) -> None:
        assert await self._count(template_backend, TEACHER_A) == 1

    async def test_second_teacher_of_the_same_student_counts_zero(
        self, template_backend: Any
    ) -> None:
        assert await self._count(template_backend, TEACHER_B) == 0

    async def test_the_count_matches_the_list(
        self, gate_backend: Any, template_backend: Any
    ) -> None:
        """Pinned as equality against the list rather than a literal, so the
        two cannot drift apart without a failure."""
        for teacher in (TEACHER_A, TEACHER_B, TEACHER_C):
            assert await self._count(template_backend, teacher) == len(
                await _visible_uids(gate_backend, teacher)
            )

    async def test_a_direct_share_is_counted(
        self, gate_backend: Any, template_backend: Any
    ) -> None:
        await gate_backend.execute_query(_DIRECT_SHARE, {"teacher": TEACHER_C, "fs": FS_UNSHARED})
        assert await self._count(template_backend, TEACHER_C) == 1

    async def test_the_unscoped_count_still_sees_everything(self, template_backend: Any) -> None:
        """The admin total is unchanged — and this is the control proving the
        zeroes above are refusals rather than an empty template."""
        result = await template_backend.count_submissions(TEMPLATE, None)
        assert result.is_ok, result.error
        assert result.value == 3


async def _share(backend: Any, submission_uid: str, group_uid: str) -> None:
    await backend.execute_query(
        """
        MATCH (fs:Entity {uid: $fs}), (g:Group {uid: $g})
        CREATE (fs)-[:SHARED_WITH_GROUP]->(g)
        """,
        {"fs": submission_uid, "g": group_uid},
    )


class TestFindSubmissionsWithoutAudience:
    """The backfill's work list — submissions carrying no share edges at all.

    The narrowness is the safety property: a submission that already names an
    audience was scoped deliberately, and widening it would hand the answers to
    teachers the submitter never picked. Staying narrow is affordable only
    because the write is atomic (see ``TestBackfillDefaultAudience``), so there
    is no half-migrated state for this predicate to miss.
    """

    async def _rows(self, backend: Any, after: str = "", limit: int = 1000) -> dict[str, str]:
        result = await backend.find_submissions_without_audience(after, limit)
        assert result.is_ok, result.error
        return {
            str(row["submission_uid"]): str(row["owner_uid"])
            for row in (result.value or [])
            if str(row["submission_uid"]).startswith(PREFIX)
        }

    async def test_selects_the_submission_with_no_audience(self, gate_backend: Any) -> None:
        rows = await self._rows(gate_backend)
        assert set(rows) == {FS_UNSHARED}
        assert rows[FS_UNSHARED] == STUDENT_1

    async def test_a_group_scoped_submission_is_left_alone(self, gate_backend: Any) -> None:
        """``fs_shared_x`` names group X only, and Student 1 also studies in Y.
        Selecting it would let the migration add Y and expose the answers to a
        teacher the submitter never chose — the exact leak this PR closes."""
        assert FS_SHARED_X not in await self._rows(gate_backend)

    async def test_a_directly_shared_submission_is_left_alone(self, gate_backend: Any) -> None:
        """A ``recipient_uids`` share is an explicit audience too, even though
        it involves no group at all."""
        await gate_backend.execute_query(_DIRECT_SHARE, {"teacher": TEACHER_C, "fs": FS_UNSHARED})
        assert FS_UNSHARED not in await self._rows(gate_backend)

    async def test_a_share_to_an_inactive_group_is_still_an_audience(
        self, gate_backend: Any
    ) -> None:
        """Reactivating a classroom is the operator's call, not the
        migration's — so this stays out of the work list."""
        assert FS_SHARED_INACTIVE not in await self._rows(gate_backend)

    async def test_a_submission_to_a_standalone_template_is_left_alone(
        self, gate_backend: Any
    ) -> None:
        """Audience-less is not evidence of intent to share.

        This submission answers a template no PathStep embeds, so it can only
        have come through the API — where ``group_uid`` and ``recipient_uids``
        are the caller's to set, and leaving both empty was a choice to stay
        private. It is otherwise identical to ``FS_UNSHARED``, which *is*
        selected, so the ``EMBEDS_FORM`` edge is the only thing separating
        them.
        """
        rows = await self._rows(gate_backend)
        assert FS_UNSHARED in rows
        assert FS_STANDALONE not in rows

    async def test_the_cursor_advances_past_a_row(self, gate_backend: Any) -> None:
        """Paging is by UID cursor, so a row whose write failed — or one left
        private forever — cannot pin the walk in place."""
        first = await self._rows(gate_backend, limit=1)
        assert len(first) == 1
        after = next(iter(first))
        assert after not in await self._rows(gate_backend, after=after)


class TestShareWithDefaultAudience:
    """The default-audience write, shared by submit and the backfill.

    One statement, so a submission's whole audience lands or none of it does,
    and the no-audience guard is re-evaluated *inside* it.
    """

    async def _shared_groups(self, backend: Any, submission_uid: str) -> list[str]:
        result = await backend.execute_query(
            """
            MATCH (fs:Entity {uid: $fs})-[:SHARED_WITH_GROUP]->(g:Group)
            RETURN g.uid AS group_uid
            """,
            {"fs": submission_uid},
        )
        assert result.is_ok, result.error
        return sorted(str(row["group_uid"]) for row in result.value or [])

    async def test_writes_every_active_student_group(self, gate_backend: Any) -> None:
        result = await gate_backend.share_with_default_audience(FS_UNSHARED)
        assert result.is_ok, result.error
        assert sorted(str(row["group_uid"]) for row in result.value or []) == sorted(
            [GROUP_X, GROUP_Y]
        )
        assert await self._shared_groups(gate_backend, FS_UNSHARED) == sorted([GROUP_X, GROUP_Y])

    async def test_the_whole_audience_lands_at_once(self, gate_backend: Any) -> None:
        """Atomicity is what lets the work list stay narrow: there is no state
        in which the submission holds one of its two classrooms, which the
        no-audience predicate would then be unable to see."""
        assert await self._shared_groups(gate_backend, FS_UNSHARED) == []
        await gate_backend.share_with_default_audience(FS_UNSHARED)
        assert len(await self._shared_groups(gate_backend, FS_UNSHARED)) == 2

    async def test_a_second_run_writes_nothing_new(self, gate_backend: Any) -> None:
        """Idempotent even if a row is somehow revisited."""
        await gate_backend.share_with_default_audience(FS_UNSHARED)
        first = await self._shared_groups(gate_backend, FS_UNSHARED)
        await gate_backend.share_with_default_audience(FS_UNSHARED)
        assert await self._shared_groups(gate_backend, FS_UNSHARED) == first

    async def test_a_group_share_landing_first_blocks_the_write(self, gate_backend: Any) -> None:
        """The time-of-check gap. The backfill selects an audience-less row,
        then the owner explicitly shares before the write runs. Re-checking
        inside the statement makes it a no-op instead of piling every classroom
        on top of the audience the owner just chose.

        Simulated by writing the explicit share *after* the caller would have
        selected the row and before the audience write — which is exactly the
        interleaving, since the two are separate transactions.
        """
        await _share(gate_backend, FS_UNSHARED, GROUP_X)

        result = await gate_backend.share_with_default_audience(FS_UNSHARED)

        assert result.is_ok, result.error
        assert result.value == []
        # Group Y must NOT have been added on top of the owner's choice.
        assert await self._shared_groups(gate_backend, FS_UNSHARED) == [GROUP_X]

    async def test_a_direct_share_landing_first_blocks_the_write(self, gate_backend: Any) -> None:
        """The same race via ``recipient_uids``, which writes no group edge at
        all — so a guard checking only SHARED_WITH_GROUP would miss it."""
        await gate_backend.execute_query(_DIRECT_SHARE, {"teacher": TEACHER_C, "fs": FS_UNSHARED})

        result = await gate_backend.share_with_default_audience(FS_UNSHARED)

        assert result.is_ok, result.error
        assert result.value == []
        assert await self._shared_groups(gate_backend, FS_UNSHARED) == []

    async def test_an_inactive_group_is_not_written(self, gate_backend: Any) -> None:
        """The audience is active classrooms only, matching what a fresh submit
        resolves. Teacher A owns the inactive group, so a leak here would be
        invisible to the granted-teacher assertions."""
        await gate_backend.execute_query(
            "MATCH (s:User {uid: $s}), (g:Group {uid: $g}) "
            "CREATE (s)-[:MEMBER_OF {role: 'student'}]->(g)",
            {"s": STUDENT_1, "g": GROUP_INACTIVE},
        )
        await gate_backend.share_with_default_audience(FS_UNSHARED)
        assert GROUP_INACTIVE not in await self._shared_groups(gate_backend, FS_UNSHARED)

    async def test_teacher_role_membership_is_not_an_audience(self, gate_backend: Any) -> None:
        """Only student-role memberships expand to "my teachers" — a teacher's
        own class must not become an audience for their own submissions."""
        await gate_backend.execute_query(
            """
            MATCH (ta:User {uid: $ta}), (gx:Group {uid: $gx})
            CREATE (fs:Entity {uid: $fs, entity_type: 'form_submission'})
            CREATE (ta)-[:OWNS]->(fs)
            CREATE (ta)-[:MEMBER_OF {role: 'teacher'}]->(gx)
            """,
            {"ta": TEACHER_A, "gx": GROUP_X, "fs": f"{PREFIX}_fs_by_teacher"},
        )
        result = await gate_backend.share_with_default_audience(f"{PREFIX}_fs_by_teacher")
        assert result.is_ok, result.error
        assert result.value == []

    async def test_a_classroom_joined_after_the_submission_is_not_written(
        self, gate_backend: Any
    ) -> None:
        """The audience is the one that existed when the answer was written.

        Submit-time resolution snapshots the student's groups at creation, so a
        migration running months later must not hand an old answer to a teacher
        the student only met afterwards.
        """
        await gate_backend.execute_query(
            """
            MATCH (s:User {uid: $s}), (g:Group {uid: $g})
            CREATE (s)-[:MEMBER_OF {role: 'student', joined_at: datetime($joined)}]->(g)
            """,
            {"s": STUDENT_1, "g": GROUP_Z, "joined": "2027-01-01T00:00:00"},
        )

        result = await gate_backend.share_with_default_audience(FS_UNSHARED)

        assert result.is_ok, result.error
        written = sorted(str(row["group_uid"]) for row in result.value or [])
        # X and Y were joined in 2025; Z in 2027, after the 2026 submission.
        assert written == sorted([GROUP_X, GROUP_Y])
        assert GROUP_Z not in await self._shared_groups(gate_backend, FS_UNSHARED)

    async def test_a_membership_with_no_join_date_is_not_written(self, gate_backend: Any) -> None:
        """Unknown ordering is not evidence the membership came first."""
        await gate_backend.execute_query(
            """
            MATCH (s:User {uid: $s}), (g:Group {uid: $g})
            CREATE (s)-[:MEMBER_OF {role: 'student'}]->(g)
            """,
            {"s": STUDENT_1, "g": GROUP_Z},
        )

        await gate_backend.share_with_default_audience(FS_UNSHARED)

        assert GROUP_Z not in await self._shared_groups(gate_backend, FS_UNSHARED)

    async def test_the_preview_matches_what_the_write_does(self, gate_backend: Any) -> None:
        """The dry run is the human's only check on this reconstruction, so it
        has to agree with the write exactly — not approximately."""
        preview = await gate_backend.preview_default_audience(FS_UNSHARED)
        assert preview.is_ok, preview.error
        previewed = sorted(str(row["group_uid"]) for row in preview.value or [])

        written = await gate_backend.share_with_default_audience(FS_UNSHARED)
        assert written.is_ok, written.error

        assert previewed == sorted(str(row["group_uid"]) for row in written.value or [])
        assert previewed == sorted([GROUP_X, GROUP_Y])

    async def test_the_preview_writes_nothing(self, gate_backend: Any) -> None:
        """It is a *dry* run — a preview that shared would be the worst possible
        bug in a command whose purpose is to be safe to run first."""
        result = await gate_backend.preview_default_audience(FS_UNSHARED)

        assert result.is_ok, result.error
        assert result.value  # non-empty, so the assertion below means something
        assert await self._shared_groups(gate_backend, FS_UNSHARED) == []

    async def test_the_preview_honours_the_same_join_date_cutoff(self, gate_backend: Any) -> None:
        """A preview that showed a classroom the write would skip would have
        the operator confirm something that never happens."""
        await gate_backend.execute_query(
            """
            MATCH (s:User {uid: $s}), (g:Group {uid: $g})
            CREATE (s)-[:MEMBER_OF {role: 'student', joined_at: datetime($joined)}]->(g)
            """,
            {"s": STUDENT_1, "g": GROUP_Z, "joined": "2027-01-01T00:00:00"},
        )

        preview = await gate_backend.preview_default_audience(FS_UNSHARED)

        assert preview.is_ok, preview.error
        assert GROUP_Z not in [str(row["group_uid"]) for row in preview.value or []]

    async def test_a_duplicate_enrolment_does_not_reset_the_join_date(
        self, gate_backend: Any, neo4j_driver: Any
    ) -> None:
        """Re-adding an existing member must not rewrite when they joined.

        ``add_member`` MERGEs, and ``GroupService`` still calls it for someone
        already in the group. If it re-stamped ``joined_at``, a membership that
        genuinely predates a submission would look newer than it and be dropped
        from the audience — the teacher would silently lose access to a
        response they were entitled to read.
        """
        from adapters.persistence.neo4j.backends.collab_backends import GroupBackend
        from core.models.group.group import Group

        groups = GroupBackend(driver=neo4j_driver, label=NeoLabel.GROUP, entity_class=Group)
        # Student 1 joined X in 2025; the submission is from 2026.
        await groups.add_member(
            group_uid=GROUP_X,
            user_uid=STUDENT_1,
            joined_at=datetime.now().isoformat(),
            role="student",
        )

        result = await gate_backend.share_with_default_audience(FS_UNSHARED)

        assert result.is_ok, result.error
        assert GROUP_X in sorted(str(row["group_uid"]) for row in result.value or [])

    async def test_the_two_timestamp_shapes_actually_compare(
        self, gate_backend: Any, neo4j_driver: Any
    ) -> None:
        """Written through the real paths, not the seed.

        ``created_at`` is persisted as an ISO string by the mapper and
        ``joined_at`` as a Neo4j datetime by ``add_member``. If those two did
        not compare, the predicate would silently match nothing and every
        default audience would come back empty — a failure that reads exactly
        like "this student has no classrooms".
        """
        from adapters.persistence.neo4j.backends.collab_backends import GroupBackend
        from core.models.enums.entity_enums import EntityStatus, EntityType
        from core.models.forms.form_submission import FormSubmission
        from core.models.group.group import Group

        groups = GroupBackend(driver=neo4j_driver, label=NeoLabel.GROUP, entity_class=Group)
        await groups.add_member(
            group_uid=GROUP_Z,
            user_uid=STUDENT_1,
            joined_at=datetime.now().isoformat(),
            role="student",
        )

        created = await gate_backend.create_with_relationships(
            FormSubmission(
                uid=f"{PREFIX}_fs_real",
                title="Real write path",
                entity_type=EntityType.FORM_SUBMISSION,
                user_uid=STUDENT_1,
                form_template_uid=TEMPLATE,
                form_data={"q": "a"},
                status=EntityStatus.COMPLETED,
            ),
            STUDENT_1,
            TEMPLATE,
        )
        assert created.is_ok, created.error

        result = await gate_backend.share_with_default_audience(f"{PREFIX}_fs_real")

        assert result.is_ok, result.error
        # Non-empty is the whole point: a type mismatch would yield [].
        assert GROUP_Z in sorted(str(row["group_uid"]) for row in result.value or [])

    async def test_a_submitter_in_no_group_gets_nothing(self, gate_backend: Any) -> None:
        """Left private, deliberately — there is no audience to infer, and
        inventing one would expose answers to a classroom they are not in."""
        await gate_backend.execute_query(
            """
            CREATE (u:User {uid: $u})
            CREATE (fs:Entity {uid: $fs, entity_type: 'form_submission'})
            CREATE (u)-[:OWNS]->(fs)
            """,
            {"u": f"{PREFIX}_loner", "fs": f"{PREFIX}_fs_loner"},
        )
        result = await gate_backend.share_with_default_audience(f"{PREFIX}_fs_loner")
        assert result.is_ok, result.error
        assert result.value == []

    async def test_the_backfill_makes_the_submission_readable(self, gate_backend: Any) -> None:
        """End to end: the migration's whole purpose is that the gate then
        grants the submitter's teachers."""
        assert await _granting_groups(gate_backend, FS_UNSHARED, TEACHER_A) == []
        await gate_backend.share_with_default_audience(FS_UNSHARED)
        assert await _granting_groups(gate_backend, FS_UNSHARED, TEACHER_A) == [GROUP_X]
        assert await _granting_groups(gate_backend, FS_UNSHARED, TEACHER_B) == [GROUP_Y]
