"""Form backends: FormTemplate, FormSubmission."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.enums import UserRole
from core.models.relationship_names import RelationshipName
from core.models.type_hints import UserUID
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.exercises.revised_exercise import RevisedExercise  # noqa: F401
    from core.models.forms.form_submission import FormSubmission
    from core.models.forms.form_template import FormTemplate
    from core.models.group.group import Group  # noqa: F401
    from core.models.interaction.interaction import Interaction  # noqa: F401
    from core.models.report_schedule import ReportSchedule  # noqa: F401
    from core.models.resource.resource import Resource  # noqa: F401


# Restricts a submission to the caller's own classrooms: its author `u` must be a
# member of an active Group the teacher owns. Written as an EXISTS predicate, not
# an extra MATCH, so scoping can only ever REMOVE rows — a teacher in two groups
# with the same student would otherwise see that student's submission twice, and
# the row shape stays identical to the unscoped query.
#
# Mirrors _user_entry_assessment_mixin.verify_teacher_authority, which is the
# single-row form of this same predicate and gates the submission detail page.
# The two must agree: a row listed here has to be openable there.
_TEACHER_SHARES_ACTIVE_GROUP = f"""EXISTS {{
        MATCH (:User {{uid: $teacher_uid}})
              -[:{RelationshipName.OWNS.value}]->
              (g:Group)
              <-[:{RelationshipName.MEMBER_OF.value}]-
              (u)
        WHERE g.is_active = true
    }}"""


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
        if teacher_uid is None:
            result = await self.execute_query(
                f"""
                MATCH (fs:Entity)
                      -[:{RelationshipName.RESPONDS_TO_FORM.value}]->
                      (ft:Entity {{uid: $uid}})
                RETURN count(fs) as count
                """,
                {"uid": template_uid},
            )
        else:
            result = await self.execute_query(
                f"""
                MATCH (fs:Entity)
                      -[:{RelationshipName.RESPONDS_TO_FORM.value}]->
                      (ft:Entity {{uid: $uid}})
                MATCH (u:User)-[:{RelationshipName.OWNS.value}]->(fs)
                WHERE {_TEACHER_SHARES_ACTIVE_GROUP}
                RETURN count(fs) as count
                """,
                {"uid": template_uid, "teacher_uid": teacher_uid},
            )
        if result.is_error or not result.value:
            return Result.ok(0)
        return Result.ok(result.value[0].get("count", 0))

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
        `form_data` — so the caller's reach is decided here, not by the page that
        renders it. ``teacher_uid=None`` returns all classrooms and is reserved
        for ADMIN; a teacher UID returns only submissions authored by students in
        an active Group that teacher owns.
        """
        if teacher_uid is None:
            result = await self.execute_query(
                f"""
                MATCH (fs:Entity {{entity_type: 'form_submission'}})
                      -[:{RelationshipName.RESPONDS_TO_FORM}]->
                      (ft:Entity {{uid: $ft_uid}})
                OPTIONAL MATCH (u:User)-[:{RelationshipName.OWNS}]->(fs)
                RETURN fs, u.uid AS user_uid, u.display_name AS user_name
                ORDER BY fs.created_at DESC
                """,
                {"ft_uid": form_template_uid},
            )
        else:
            # Required MATCH, not OPTIONAL: a submission with no owner cannot be
            # shown to belong to this teacher's classroom, so it is not theirs to
            # read. The unscoped branch above keeps them for ADMIN.
            result = await self.execute_query(
                f"""
                MATCH (fs:Entity {{entity_type: 'form_submission'}})
                      -[:{RelationshipName.RESPONDS_TO_FORM}]->
                      (ft:Entity {{uid: $ft_uid}})
                MATCH (u:User)-[:{RelationshipName.OWNS}]->(fs)
                WHERE {_TEACHER_SHARES_ACTIVE_GROUP}
                RETURN fs, u.uid AS user_uid, u.display_name AS user_name
                ORDER BY fs.created_at DESC
                """,
                {"ft_uid": form_template_uid, "teacher_uid": teacher_uid},
            )
        if result.is_error:
            return Result.fail(result)
        rows: list[dict[str, Any]] = []
        for record in result.value or []:
            row = dict(record["fs"])
            row["user_uid"] = record.get("user_uid")
            row["user_name"] = record.get("user_name")
            rows.append(row)
        return Result.ok(rows)

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
