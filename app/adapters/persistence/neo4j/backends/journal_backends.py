"""Journal backends: JournalInput (JeInput), JournalOutput (JeOutput)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.relationship_names import RelationshipName
from core.models.type_hints import Neo4jProperties, UserUID
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.exercises.revised_exercise import RevisedExercise  # noqa: F401
    from core.models.forms.form_template import FormTemplate  # noqa: F401
    from core.models.group.group import Group  # noqa: F401
    from core.models.interaction.interaction import Interaction  # noqa: F401
    from core.models.journal.je_input import JeInput  # noqa: F401
    from core.models.journal.je_output import JeOutput  # noqa: F401
    from core.models.resource.resource import Resource  # noqa: F401
    from core.models.submissions.report_schedule import ReportSchedule  # noqa: F401


class JournalInputBackend(UniversalNeo4jBackend["JeInput"]):
    """
    Domain backend for JeInput entities (journal entry inputs).

    Standalone journal backend — NOT part of SubmissionsBackend.
    Uses NeoLabel.JE_INPUT with base_label=NeoLabel.ENTITY.
    """

    async def count_je_inputs_for_date(self, user_uid: UserUID, entry_date: str) -> Result[int]:
        """Count journal entries for a user on a specific date."""
        query = """
        MATCH (u:User {uid: $user_uid})-[:OWNS]->(ji:JeInput)
        WHERE ji.metadata IS NOT NULL
          AND ji.metadata CONTAINS $date_str
        RETURN count(ji) AS count
        """
        result = await self.execute_query(query, {"user_uid": user_uid, "date_str": entry_date})
        if result.is_error:
            return Result.fail(result)
        record = result.value[0] if result.value else {}
        return Result.ok(record.get("count", 0))

    async def get_ephemeral_je_inputs(
        self, user_uid: UserUID, limit: int = 100
    ) -> Result[list[Neo4jProperties]]:
        """Get journal entries with FIFO cleanup enabled (max_retention is not null)."""
        query = """
        MATCH (u:User {uid: $user_uid})-[:OWNS]->(ji:JeInput)
        WHERE ji.max_retention IS NOT NULL
        RETURN ji
        ORDER BY ji.created_at DESC
        LIMIT $limit
        """
        result = await self.execute_query(query, {"user_uid": user_uid, "limit": limit})
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["ji"] for record in (result.value or [])])

    async def get_je_inputs_by_date_range(
        self, user_uid: UserUID, start_date: str, end_date: str
    ) -> Result[list[Neo4jProperties]]:
        """Get journal entries for a user within a date range (by created_at)."""
        query = """
        MATCH (u:User {uid: $user_uid})-[:OWNS]->(ji:JeInput)
        WHERE ji.created_at >= $start_date AND ji.created_at <= $end_date
        RETURN ji
        ORDER BY ji.created_at DESC
        """
        result = await self.execute_query(
            query,
            {"user_uid": user_uid, "start_date": start_date, "end_date": end_date},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["ji"] for record in (result.value or [])])


class JournalOutputBackend(UniversalNeo4jBackend["JeOutput"]):
    """
    Domain backend for JeOutput entities (journal entry outputs).

    Standalone journal backend — NOT part of ExerciseReport infrastructure.
    Uses NeoLabel.JE_OUTPUT with base_label=NeoLabel.ENTITY.
    """

    async def get_je_output_for_input(self, je_input_uid: str) -> Result[Neo4jProperties | None]:
        """Get the je_output that transforms a specific je_input."""
        query = """
        MATCH (jo:JeOutput)-[:TRANSFORMS]->(ji:JeInput {uid: $je_input_uid})
        RETURN jo
        LIMIT 1
        """
        result = await self.execute_query(query, {"je_input_uid": je_input_uid})
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.ok(None)
        return Result.ok(result.value[0]["jo"])

    async def create_with_transforms(
        self,
        properties: Neo4jProperties,
        user_uid: UserUID,
        je_input_uid: str,
    ) -> Result[Neo4jProperties]:
        """Atomically create JeOutput node with OWNS + TRANSFORMS relationships.

        Single Cypher transaction: MATCH User + JeInput, CREATE JeOutput:Entity,
        CREATE (User)-[:OWNS]->(JeOutput)-[:TRANSFORMS]->(JeInput).
        """
        query = f"""
        MATCH (u:User {{uid: $user_uid}})
        MATCH (ji:JeInput {{uid: $je_input_uid}})
        CREATE (jo:{self._create_labels})
        SET jo = $props
        CREATE (u)-[:{RelationshipName.OWNS.value}]->(jo)
        CREATE (jo)-[:{RelationshipName.TRANSFORMS.value}]->(ji)
        RETURN jo
        """
        result = await self.execute_query(
            query,
            {"props": properties, "user_uid": user_uid, "je_input_uid": je_input_uid},
        )
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.fail(
                Errors.database("create_with_transforms", "User or JeInput not found")
            )
        return Result.ok(result.value[0]["jo"])
