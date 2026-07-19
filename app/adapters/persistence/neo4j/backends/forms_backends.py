"""Form backends: FormTemplate, FormSubmission."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.enums import UserRole
from core.models.relationship_names import RelationshipName
from core.models.type_hints import Neo4jProperties, UserUID
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.exercises.revised_exercise import RevisedExercise  # noqa: F401
    from core.models.forms.form_submission import FormSubmission
    from core.models.forms.form_template import FormTemplate  # noqa: F401
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

    async def count_submissions(self, template_uid: str) -> Result[int]:
        """Count submissions linked to a template via RESPONDS_TO_FORM."""
        result = await self.execute_query(
            f"""
            MATCH (fs:Entity)-[:{RelationshipName.RESPONDS_TO_FORM.value}]->(ft:Entity {{uid: $uid}})
            RETURN count(fs) as count
            """,
            {"uid": template_uid},
        )
        if result.is_error or not result.value:
            return Result.ok(0)
        return Result.ok(result.value[0].get("count", 0))

    async def get_forms_for_path_step(self, ps_uid: str) -> Result[list[Neo4jProperties]]:
        """Get all FormTemplates embedded in a path step."""
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
        return Result.ok([dict(record["ft"]) for record in (result.value or [])])

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
        self, form_template_uid: str
    ) -> Result[list[dict[str, Any]]]:
        """Get all submissions for a form template, including submitter info."""
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
        from core.utils.neo4j_mapper import from_neo4j_node, to_neo4j_node

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
