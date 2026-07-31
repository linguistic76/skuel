"""Form backends: FormTemplate, FormSubmission."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.enums import GroupMemberRole, UserRole
from core.models.enums.entity_enums import EntityType
from core.models.relationship_names import RelationshipName
from core.models.type_hints import Neo4jProperties, UserUID
from core.ports.query_types import (
    BackfilledGroupRow,
    TeacherSubmissionAccessRow,
    UnaudiencedSubmissionRow,
)
from core.utils.result_simplified import Errors, Result


def _default_audience_match(owner_var: str, submission_var: str, *, only_prior: bool) -> str:
    """Cypher matching ``g`` — the groups a submission's default audience is.

    Shared by the write and by the dry run's preview so an operator reviewing
    what would be shared is reading the same selection that would run, not a
    second copy of it.

    ``only_prior`` restricts to memberships joined at or before the submission,
    and belongs **only to the backfill**. There, the audience is a
    *reconstruction* of a past moment, so a classroom the student joined later
    must not receive an older answer, and an unknown join date is excluded —
    unknown ordering is not evidence the membership came first.

    A live submit resolves the audience for a submission being created *now*,
    where every existing membership trivially qualifies. Applying the cutoff
    there would only ever exclude: a ``MEMBER_OF`` edge without ``joined_at``
    (older or hand-made data) would drop the classroom, the submission would
    land with no audience, and submit would report success on a response no
    teacher can open.

    Even with the cutoff the reconstruction is imperfect — ``MEMBER_OF`` records
    when the edge was created but not when its role last changed, so a role
    edited afterwards reads as if it always held. That is why the migration asks
    a human to confirm a listed set rather than deriving intent it cannot
    actually derive.
    """
    cutoff = (
        f"""
          AND m.joined_at IS NOT NULL
          AND m.joined_at <= datetime({submission_var}.created_at)"""
        if only_prior
        else ""
    )
    return f"""
        MATCH ({owner_var})-[m:{RelationshipName.MEMBER_OF}]->(g:Group)
        WHERE m.role = $student_role
          AND g.is_active = true{cutoff}
    """


def _teacher_audience_predicate(submission_var: str) -> str:
    """Cypher for "this submission's audience includes ``$teacher_uid``".

    One spelling shared by the three teacher-facing reads (detail gate, list,
    card count). They have to admit exactly the same set: a count that
    disagrees with the list leaks how much cross-classroom activity exists,
    and a list that disagrees with the detail gate indexes what it refuses.

    Both audience kinds ``_share_on_submit`` writes count — a
    ``SHARED_WITH_GROUP`` edge to an active group the teacher owns, or a direct
    ``SHARES_WITH`` from the teacher (``recipient_uids`` on the submit API).
    ``EXISTS`` rather than a ``MATCH`` so a submission reachable several ways
    is still one row.
    """
    return f"""
        EXISTS {{
            ({submission_var})-[:{RelationshipName.SHARED_WITH_GROUP}]->
                (g:Group {{is_active: true}})
                <-[:{RelationshipName.OWNS}]-(:User {{uid: $teacher_uid}})
        }}
        OR EXISTS {{
            (:User {{uid: $teacher_uid}})-[:{RelationshipName.SHARES_WITH}]->({submission_var})
        }}
    """


if TYPE_CHECKING:
    from core.models.exercises.revised_exercise import RevisedExercise  # noqa: F401
    from core.models.forms.form_submission import FormSubmission
    from core.models.forms.form_template import FormTemplate
    from core.models.group.group import Group  # noqa: F401
    from core.models.interaction.interaction import Interaction  # noqa: F401
    from core.models.report_schedule import ReportSchedule  # noqa: F401
    from core.models.resource.resource import Resource  # noqa: F401


class FormTemplateBackend(UniversalNeo4jBackend["FormTemplate"]):
    """
    Domain backend for FormTemplate entities.

    Provides:
    - get_forms_for_path_step — Query FormTemplates linked to a path step via EMBEDS_FORM
    - count_submissions    — Count submissions linked to a template via RESPONDS_TO_FORM
    """

    async def count_submissions(
        self, template_uid: str, teacher_uid: UserUID | None
    ) -> Result[int]:
        """Count submissions linked to a template via RESPONDS_TO_FORM.

        ``teacher_uid=None`` counts every classroom — required by the delete
        guard, which must see submissions the caller may not read. A teacher UID
        counts only submissions this count's reader may also open, so the number
        never discloses activity outside their classrooms.
        """
        params: dict[str, Any] = {
            "uid": template_uid,
            "entity_type": EntityType.FORM_SUBMISSION.value,
        }
        if teacher_uid is None:
            scope = ""
        else:
            scope = f"WHERE {_teacher_audience_predicate('fs')}"
            params["teacher_uid"] = teacher_uid
        result = await self.execute_query(
            f"""
            MATCH (fs:Entity {{entity_type: $entity_type}})
                  -[:{RelationshipName.RESPONDS_TO_FORM.value}]->
                  (ft:Entity {{uid: $uid}})
            {scope}
            RETURN count(fs) as count
            """,
            params,
        )
        return self._count_or_error(result)

    @staticmethod
    def _count_or_error(result: Result[list[Neo4jProperties]]) -> Result[int]:
        """Unwrap a ``count`` row, keeping a backend failure a failure.

        Collapsing an error to ``0`` would make an outage indistinguishable
        from a template nobody has answered — and on the scoped count, from a
        classroom with nothing shared to it. Zero is reserved for a successful
        empty result.
        """
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.ok(0)
        # Neo4j's count() is an integer, but the property type is a union —
        # narrow before arithmetic rather than trusting the driver's shape.
        raw = records[0].get("count", 0)
        return Result.ok(raw if isinstance(raw, int) else 0)

    async def get_forms_for_path_step(self, ps_uid: str) -> Result[list[FormTemplate]]:
        """Get all FormTemplates embedded in a path step as typed models."""
        from adapters.persistence.neo4j.neo4j_mapper import from_neo4j_node
        from core.models.forms.form_template import FormTemplate

        result = await self.execute_query(
            f"""
            MATCH (a:Entity {{uid: $ps_uid}})
                  -[:{RelationshipName.EMBEDS_FORM}]->
                  (ft:Entity {{entity_type: 'form_template'}})
            RETURN ft
            ORDER BY ft.title ASC
            """,
            {"ps_uid": ps_uid},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(
            [from_neo4j_node(dict(record["ft"]), FormTemplate) for record in (result.value or [])]
        )

    async def link_to_path_step(self, form_template_uid: str, ps_uid: str) -> Result[bool]:
        """Create EMBEDS_FORM relationship from path step to form template."""
        result = await self.execute_query(
            f"""
            MATCH (a:Entity {{uid: $ps_uid}})
            WHERE a.entity_type IN ['path_step', 'ku']
            MATCH (ft:Entity {{uid: $ft_uid, entity_type: 'form_template'}})
            MERGE (a)-[r:{RelationshipName.EMBEDS_FORM}]->(ft)
            ON CREATE SET r.created_at = datetime()
            RETURN true as success
            """,
            {"ps_uid": ps_uid, "ft_uid": form_template_uid},
        )
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.fail(
                Errors.not_found(
                    resource="PathStep or FormTemplate",
                    identifier=f"{ps_uid} -> {form_template_uid}",
                )
            )
        return Result.ok(True)

    async def unlink_from_path_step(self, form_template_uid: str, ps_uid: str) -> Result[bool]:
        """Remove EMBEDS_FORM relationship."""
        result = await self.execute_query(
            f"""
            MATCH (a:Entity {{uid: $ps_uid}})
                  -[r:{RelationshipName.EMBEDS_FORM}]->
                  (ft:Entity {{uid: $ft_uid}})
            DELETE r
            RETURN true as success
            """,
            {"ps_uid": ps_uid, "ft_uid": form_template_uid},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(True)


class FormSubmissionBackend(UniversalNeo4jBackend["FormSubmission"]):
    """
    Domain backend for FormSubmission entities.

    Provides:
    - get_submissions_for_template — Query all submissions for a template
    - get_submissions_for_template_for_teacher — the same list, Model B gated
    - verify_teacher_submission_access — Model B gate for one submission
    - list_by_user                 — Get user's form submissions
    - find_admin_user_uid          — Find the first admin user UID
    """

    async def find_admin_user_uid(self, admin_role: UserRole) -> Result[str | None]:
        """Find the first admin user UID by role value."""
        result = await self.execute_query(
            """
            MATCH (u:User) WHERE u.role = $admin_role
            RETURN u.uid as uid LIMIT 1
            """,
            {"admin_role": admin_role.value},
        )
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.ok(None)
        return Result.ok(result.value[0]["uid"])

    async def get_submissions_for_template(
        self, form_template_uid: str, teacher_uid: UserUID | None
    ) -> Result[list[dict[str, Any]]]:
        """Get submissions for a form template, including submitter info.

        Every row carries the submitter's identity and full node — including
        ``form_data`` — so the caller's reach is decided here, not by the page
        that renders it. ``teacher_uid=None`` returns all classrooms and is
        reserved for ADMIN.

        A teacher UID returns only submissions whose own audience includes that
        teacher — not merely ones whose *author* they teach. A student may
        study in several classrooms, so a response shared with one teacher's
        group is not thereby readable by another's. Same predicate as the
        detail gate, so a row listed here is exactly a row that opens there.
        """
        params: dict[str, Any] = {
            "ft_uid": form_template_uid,
            "entity_type": EntityType.FORM_SUBMISSION.value,
        }
        if teacher_uid is None:
            scope = ""
        else:
            scope = f"WHERE {_teacher_audience_predicate('fs')}"
            params["teacher_uid"] = teacher_uid
        result = await self.execute_query(
            f"""
            MATCH (fs:Entity {{entity_type: $entity_type}})
                  -[:{RelationshipName.RESPONDS_TO_FORM}]->
                  (ft:Entity {{uid: $ft_uid}})
            {scope}
            OPTIONAL MATCH (u:User)-[:{RelationshipName.OWNS}]->(fs)
            RETURN fs, u.uid AS user_uid, u.display_name AS user_name
            ORDER BY fs.created_at DESC
            """,
            params,
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(self._rows_with_submitter(result.value or []))

    @staticmethod
    def _rows_with_submitter(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Flatten ``fs`` nodes plus their submitter columns into row dicts.

        Shared by the scoped and unscoped branches so the two cannot drift into
        different shapes — the page renders whichever it is given.
        """
        rows: list[dict[str, Any]] = []
        for record in records:
            row = dict(record["fs"])
            row["user_uid"] = record.get("user_uid")
            row["user_name"] = record.get("user_name")
            rows.append(row)
        return rows

    async def find_submissions_without_audience(
        self, after_uid: str, limit: int
    ) -> Result[list[UnaudiencedSubmissionRow]]:
        """Submissions carrying no audience at all, with their owner.

        The migration surface for the Model B gate: a submission created before
        submit-time audience resolution existed has neither ``SHARES_WITH`` nor
        ``SHARED_WITH_GROUP``, so the gate hides it from every teacher.

        **"No audience at all" is the point, not a limitation.** A submission
        that already names an audience was scoped deliberately — by
        ``group_uid`` or ``recipient_uids`` on the submit API — and adding the
        submitter's other classrooms would expose their answers to teachers
        they did not pick. That is the very leak this gate exists to stop, so a
        migration must never widen an audience that already exists.

        **Restricted further, to templates embedded in a PathStep.** Having no
        audience is *not* by itself evidence a submission was meant to be seen:
        ``/api/form-submissions/submit`` takes ``group_uid`` and
        ``recipient_uids`` from the caller, both optional, so leaving them
        empty was a deliberate choice to stay private. Nothing on the node
        records which route created it. The ``EMBEDS_FORM`` restriction is the
        available proxy: the PathStep-embedded route can only submit templates
        embedded in a PathStep, so this keeps every submission that had no way
        to declare an audience while dropping API submissions of ordinary
        templates. It is a *narrowing*, not a proof — an API submission of an
        embedded template is still indistinguishable — which is why the script
        requires an explicit confirmation to write.

        This can be both narrow and retryable only because the write is atomic:
        ``share_with_default_audience`` creates a submission's whole audience in
        one statement, so there is no partial state for this predicate to miss.

        Paged by a ``fs.uid`` cursor rather than an offset, so the walk advances
        past a row whose write failed instead of returning it forever — the
        failure resurfaces on the next run, since nothing marks rows done.
        """
        result = await self.execute_query(
            f"""
            MATCH (u:User)-[:{RelationshipName.OWNS}]->(fs:Entity {{entity_type: $entity_type}})
            WHERE fs.uid > $after_uid
              AND NOT EXISTS {{ (fs)-[:{RelationshipName.SHARED_WITH_GROUP}]->(:Group) }}
              AND NOT EXISTS {{ (:User)-[:{RelationshipName.SHARES_WITH}]->(fs) }}
              AND EXISTS {{
                  (fs)-[:{RelationshipName.RESPONDS_TO_FORM}]->
                      (:Entity)<-[:{RelationshipName.EMBEDS_FORM}]-(:Entity)
              }}
            RETURN fs.uid AS submission_uid, u.uid AS owner_uid
            ORDER BY fs.uid ASC
            LIMIT $limit
            """,
            {
                "after_uid": after_uid,
                "limit": limit,
                "entity_type": EntityType.FORM_SUBMISSION.value,
            },
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(
            [
                UnaudiencedSubmissionRow(
                    submission_uid=str(record["submission_uid"]),
                    owner_uid=str(record["owner_uid"]),
                )
                for record in result.value or []
            ]
        )

    async def preview_default_audience(
        self, submission_uid: str
    ) -> Result[list[BackfilledGroupRow]]:
        """The groups the backfill would write for one submission, writing none.

        The dry run's whole job is to let a human check the migration's
        reconstruction before it happens, and a list of submission UIDs cannot
        be checked — the reviewable fact is *which classroom* each answer would
        go to. Runs the same selection as the backfill's write, cutoff included
        (see ``_default_audience_match``), so the preview cannot drift from it.
        """
        result = await self.execute_query(
            f"""
            MATCH (u:User)-[:{RelationshipName.OWNS}]->
                  (fs:Entity {{uid: $submission_uid, entity_type: $entity_type}})
            WHERE fs.created_at IS NOT NULL
            {_default_audience_match("u", "fs", only_prior=True)}
            RETURN g.uid AS group_uid
            """,
            {
                "submission_uid": submission_uid,
                "student_role": GroupMemberRole.STUDENT.value,
                "entity_type": EntityType.FORM_SUBMISSION.value,
            },
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(
            [
                BackfilledGroupRow(group_uid=str(record["group_uid"]))
                for record in result.value or []
            ]
        )

    async def share_with_default_audience(
        self, submission_uid: str, *, only_prior_memberships: bool = False
    ) -> Result[list[BackfilledGroupRow]]:
        """Give one submission the audience its owner's classrooms imply.

        Shared by the submit path and the backfill — the same operation in both
        places, so there is one implementation of "who are this student's
        teachers" rather than two that can disagree.

        Deliberately a **single statement**, for two reasons:

        - *Atomicity.* A submission's whole audience lands or none of it does.
          Writing the groups one at a time leaves a half-audienced submission
          that ``find_submissions_without_audience`` can no longer see, so the
          classroom whose write failed is stranded permanently.
        - *No time-of-check gap.* The no-audience guard is re-evaluated inside
          the write, so an explicit share landing between a caller's check and
          this call makes it a no-op rather than piling every classroom on top
          of an audience the owner had just chosen deliberately.

        That guard also defines the contract: this only ever *establishes* an
        audience, never widens one. Both callers want exactly that.

        ``only_prior_memberships`` is the backfill's flag, and is why the two
        callers are not quite identical. It restricts the audience to
        classrooms joined at or before ``fs.created_at``, so a migration running
        months later cannot hand an old answer to a teacher the student met
        afterwards — submit-time resolution snapshots the groups at creation and
        would never retroactively add one.

        A live submit leaves it off. Every existing membership trivially
        predates a submission being created now, so the cutoff could only ever
        *exclude*: a ``MEMBER_OF`` edge without ``joined_at`` would drop that
        classroom, the submission would land with no audience, and submit would
        report success on a response no teacher can open.

        Both timestamps trace back to ``datetime.now().isoformat()`` but are
        stored differently — ``joined_at`` as a Neo4j datetime (see
        ``GroupBackend.add_member``) and ``created_at`` as an ISO string (the
        mapper serialises every datetime field that way) — so the string is
        converted before comparing.

        Authorization holds by construction — the groups are reached through
        the owner's own ``MEMBER_OF`` edges, so this can only produce shares
        ``UnifiedSharingService.share_with_group`` would itself have allowed.
        Mirrors ``GroupBackend.get_user_groups``'s definition of a student
        membership (``MEMBER_OF.role`` + an active group).

        Returns the groups written — empty when the owner studies in none, or
        when the submission already had an audience. Neither is a failure.
        """
        result = await self.execute_query(
            f"""
            MATCH (u:User)-[:{RelationshipName.OWNS}]->
                  (fs:Entity {{uid: $submission_uid, entity_type: $entity_type}})
            // Take a write lock on `fs` BEFORE reading its audience. Neo4j
            // reads are read-committed and lock-free, so without this a share
            // committing between the WHERE and the MERGE would be invisible
            // here — and the MERGE does not re-evaluate the predicate, so every
            // classroom would land on top of the audience the owner just chose.
            // Writing a property back to itself changes nothing and is the
            // pure-Cypher way to acquire that lock (apoc.lock.* is out of
            // scope: APOC is restricted to apoc.meta.*).
            SET fs.uid = fs.uid
            WITH u, fs
            WHERE NOT EXISTS {{ (fs)-[:{RelationshipName.SHARED_WITH_GROUP}]->(:Group) }}
              AND NOT EXISTS {{ (:User)-[:{RelationshipName.SHARES_WITH}]->(fs) }}
              {"AND fs.created_at IS NOT NULL" if only_prior_memberships else ""}
            {_default_audience_match("u", "fs", only_prior=only_prior_memberships)}
            MERGE (fs)-[r:{RelationshipName.SHARED_WITH_GROUP}]->(g)
              ON CREATE SET r.shared_at = datetime($shared_at),
                            r.share_version = $share_version
            RETURN g.uid AS group_uid
            """,
            {
                "submission_uid": submission_uid,
                "student_role": GroupMemberRole.STUDENT.value,
                "shared_at": datetime.now().isoformat(),
                "share_version": "original",
                "entity_type": EntityType.FORM_SUBMISSION.value,
            },
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(
            [
                BackfilledGroupRow(group_uid=str(record["group_uid"]))
                for record in result.value or []
            ]
        )

    async def verify_teacher_submission_access(
        self, submission_uid: str, teacher_uid: str
    ) -> Result[list[TeacherSubmissionAccessRow]]:
        """Verify one submission's audience includes the requesting teacher.

        The entity-level half of the Model B gate, and the detail page's twin
        of ``get_submissions_for_template_for_teacher`` — the two must admit
        exactly the same set or the list becomes an index of what the detail
        page refuses.

        Granted by either audience kind ``_share_on_submit`` writes: a
        ``SHARED_WITH_GROUP`` edge to an active group the teacher owns, or a
        direct ``SHARES_WITH`` from the teacher (``recipient_uids`` on the
        submit API). ``group_uid`` names the classroom that granted the read
        and is null when a direct share did; an empty *result* is the refusal,
        which callers map to not-found.
        """
        result = await self.execute_query(
            f"""
            MATCH (fs:Entity {{uid: $submission_uid, entity_type: $entity_type}})
            WHERE {_teacher_audience_predicate("fs")}
            OPTIONAL MATCH (fs)-[:{RelationshipName.SHARED_WITH_GROUP}]->
                           (granting:Group {{is_active: true}})
                           <-[:{RelationshipName.OWNS}]-(:User {{uid: $teacher_uid}})
            // Aggregate keyed on `fs`, never bare. An unkeyed `collect` emits
            // one row even from zero input, so a refusal would come back as a
            // single null-valued row — and this gate reads row *presence* as
            // the grant. That failure is fail-open.
            WITH fs, collect(granting.uid) AS granting_groups
            RETURN granting_groups[0] AS group_uid
            """,
            {
                "submission_uid": submission_uid,
                "teacher_uid": teacher_uid,
                "entity_type": EntityType.FORM_SUBMISSION.value,
            },
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(
            [
                TeacherSubmissionAccessRow(
                    group_uid=None if record["group_uid"] is None else str(record["group_uid"])
                )
                for record in result.value or []
            ]
        )

    async def create_with_relationships(
        self,
        submission: FormSubmission,
        user_uid: UserUID,
        form_template_uid: str,
    ) -> Result[FormSubmission]:
        """Atomically create node + OWNS + RESPONDS_TO_FORM in one transaction."""
        from adapters.persistence.neo4j.neo4j_mapper import from_neo4j_node, to_neo4j_node

        node_data = to_neo4j_node(submission)
        node_data.update(self.default_filters)

        query = f"""
        MATCH (u:User {{uid: $user_uid}})
        MATCH (ft:Entity {{uid: $ft_uid, entity_type: 'form_template'}})
        CREATE (fs:{self._create_labels})
        SET fs = $props
        CREATE (u)-[:{RelationshipName.OWNS.value}]->(fs)
        CREATE (fs)-[r:{RelationshipName.RESPONDS_TO_FORM.value}]->(ft)
        SET r.created_at = datetime()
        RETURN fs
        """
        result = await self.execute_query(
            query,
            {"props": node_data, "user_uid": user_uid, "ft_uid": form_template_uid},
        )
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.fail(
                Errors.database("create_with_relationships", "User or template not found")
            )
        return Result.ok(from_neo4j_node(dict(records[0]["fs"]), self.entity_class))

    async def list_by_user(  # type: ignore[override]  # raw-props variant: callers expect node dicts, not models
        self, user_uid: UserUID, limit: int = 50
    ) -> Result[list[dict[str, Any]]]:
        """Get a user's form submissions (raw node properties, not domain models)."""
        result = await self.execute_query(
            """
            MATCH (fs:Entity {entity_type: 'form_submission', user_uid: $user_uid})
            RETURN fs
            ORDER BY fs.created_at DESC
            LIMIT $limit
            """,
            {"user_uid": user_uid, "limit": limit},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok([dict(record["fs"]) for record in (result.value or [])])
