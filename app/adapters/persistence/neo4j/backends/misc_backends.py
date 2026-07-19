"""Miscellaneous backends: ActivityReport, Resource, Interaction, ReportSchedule, ActivityReportGenerator."""

from __future__ import annotations

from typing import TYPE_CHECKING

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.relationship_names import RelationshipName
from core.models.report.activity_report import ActivityReport
from core.models.type_hints import Neo4jProperties, UserUID
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
    from core.models.enums.interaction_enums import InteractionResult
    from core.models.exercises.revised_exercise import RevisedExercise  # noqa: F401
    from core.models.forms.form_template import FormTemplate  # noqa: F401
    from core.models.group.group import Group  # noqa: F401
    from core.models.interaction.interaction import Interaction  # noqa: F401
    from core.models.report_schedule import ReportSchedule  # noqa: F401
    from core.models.resource.resource import Resource  # noqa: F401


class ActivityReportBackend(UniversalNeo4jBackend[ActivityReport]):
    """
    Domain backend for ActivityReport entities.

    Moves inline Cypher from ActivityReportService into named backend methods.
    Methods: get_history, annotate, get_annotation, get_admin_snapshots,
    get_shares_granted, get_report_schedule.
    """

    async def get_for_user(self, uid: str, user_uid: str) -> Result[list[Neo4jProperties]]:
        """Get a single ActivityReport by UID, scoped to the owning user."""
        return await self.execute_query(
            """
            MATCH (n:Entity {uid: $uid, user_uid: $user_uid, entity_type: 'activity_report'})
            RETURN n
            """,
            {"uid": uid, "user_uid": user_uid},
        )

    async def get_history(self, subject_uid: str, limit: int = 20) -> Result[list[Neo4jProperties]]:
        """Get ActivityReport entities where subject_uid matches the user."""
        return await self.execute_query(
            """
            MATCH (n:Entity {entity_type: 'activity_report', subject_uid: $subject_uid})
            RETURN n
            ORDER BY n.created_at DESC
            LIMIT $limit
            """,
            {"subject_uid": subject_uid, "limit": limit},
        )

    async def annotate(
        self,
        uid: str,
        user_uid: UserUID,
        annotation_mode: str,
        now: str,
        user_annotation: str | None = None,
        user_revision: str | None = None,
    ) -> Result[list[Neo4jProperties]]:
        """Save annotation or revision to an owned ActivityReport."""
        return await self.execute_query(
            """
            MATCH (n:Entity {uid: $uid, user_uid: $user_uid, entity_type: 'activity_report'})
            SET n.annotation_mode = $annotation_mode,
                n.annotation_updated_at = datetime($now),
                n.user_annotation = $user_annotation,
                n.user_revision = $user_revision
            RETURN n.uid AS uid, n.annotation_mode AS annotation_mode,
                   n.user_annotation AS user_annotation, n.user_revision AS user_revision
            """,
            {
                "uid": uid,
                "user_uid": user_uid,
                "annotation_mode": annotation_mode,
                "now": now,
                "user_annotation": user_annotation,
                "user_revision": user_revision,
            },
        )

    async def get_annotation(self, uid: str, user_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """Get current annotation state for an owned ActivityReport."""
        return await self.execute_query(
            """
            MATCH (n:Entity {uid: $uid, user_uid: $user_uid, entity_type: 'activity_report'})
            RETURN n.uid AS uid, n.annotation_mode AS annotation_mode,
                   n.user_annotation AS user_annotation, n.user_revision AS user_revision,
                   n.annotation_updated_at AS annotation_updated_at
            """,
            {"uid": uid, "user_uid": user_uid},
        )

    async def get_admin_snapshots(
        self, user_uid: UserUID, limit: int = 50
    ) -> Result[list[Neo4jProperties]]:
        """Get admin-written ActivityReports received by this user (privacy audit)."""
        return await self.execute_query(
            """
            MATCH (n:Entity {entity_type: 'activity_report', subject_uid: $user_uid})
            WHERE n.processor_type = 'human'
            RETURN n.created_at AS accessed_at,
                   n.user_uid AS admin_uid,
                   n.time_period AS time_period
            ORDER BY n.created_at DESC
            LIMIT $limit
            """,
            {"user_uid": user_uid, "limit": limit},
        )

    async def get_shares_granted(
        self, user_uid: UserUID, limit: int = 100
    ) -> Result[list[Neo4jProperties]]:
        """Get users with active SHARES_WITH access to this user's entities."""
        return await self.execute_query(
            f"""
            MATCH (accessor:User)-[sw:{RelationshipName.SHARES_WITH.value}]->(e:Entity {{user_uid: $user_uid}})
            RETURN accessor.uid AS accessor_uid,
                   e.uid AS entity_uid,
                   e.title AS entity_title,
                   sw.role AS role,
                   sw.shared_at AS shared_at
            ORDER BY sw.shared_at DESC
            LIMIT $limit
            """,
            {"user_uid": user_uid, "limit": limit},
        )

    async def get_report_schedule(self, user_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """Get active report schedule for user (privacy audit)."""
        return await self.execute_query(
            """
            MATCH (u:User {uid: $user_uid})-[:HAS_SCHEDULE]->(s:ReportSchedule)
            WHERE s.is_active = true
            RETURN s.schedule_type AS schedule_type,
                   s.day_of_week AS day_of_week,
                   s.next_due_at AS next_due_at,
                   s.last_generated_at AS last_generated_at
            LIMIT 1
            """,
            {"user_uid": user_uid},
        )


class ResourceBackend(UniversalNeo4jBackend["Resource"]):
    """
    Domain backend for Resource entities (books, talks, films, podcasts).

    Resource is admin-curated shared content (ContentOrigin.CURATED).
    Inherits full CRUD + list from UniversalNeo4jBackend — no custom Cypher needed
    for basic library browsing. Query via NeoLabel.RESOURCE label.
    """

    async def get_citing_entities(self, resource_uid: str) -> Result[list[Neo4jProperties]]:
        """Find the Kus / PathSteps that cite this Resource (reverse CITES_RESOURCE).

        Reciprocal of the forward citation surface: powers the "Cited by" section
        on the Resource detail page. Each row carries the citing entity's uid,
        title, entity_type, and the citation edge's free-string locator (null for
        a whole-work citation). One row per citation edge — parallel edges from the
        same source (distinct locators) surface as distinct rows.
        """
        query = f"""
        MATCH (r:Resource {{uid: $resource_uid}})<-[cite:{RelationshipName.CITES_RESOURCE.value}]-(source:Entity)
        RETURN source.uid AS uid, source.title AS title,
               source.entity_type AS entity_type, cite.locator AS locator
        ORDER BY source.title
        """
        return await self.execute_query(query, {"resource_uid": resource_uid})


class InteractionBackend(UniversalNeo4jBackend["Interaction"]):
    """
    Domain backend for Interaction entities (User Interaction Contract).

    Records situated learning-loop events: who submitted what, while studying
    which PathStep, within which LearningPath.

    Inherits full CRUD + list from UniversalNeo4jBackend. Phase 2 adds the
    guarded ``result_status`` transition. Future ZPD integration will add
    traversal queries here.
    """

    async def update_result_status_for_entry(
        self,
        entry_uid: str,
        new_status: InteractionResult,
        allowed_from: tuple[InteractionResult, ...],
    ) -> Result[int]:
        """Transition ``result_status`` on the Interaction recording a UserEntry.

        Matches on ``source_entity_uid`` (always stamped at creation; the
        RECORDS edge is best-effort) and applies the transition only when the
        current status is in ``allowed_from`` — the forward-only guard runs
        server-side so concurrent events cannot interleave a demotion.

        Returns the number of transitioned records: 0 is a valid no-op
        (entry has no Interaction — e.g. a journal entry — or the guard
        rejected a stale transition).
        """
        result = await self.execute_query(
            """
            MATCH (i:Entity:Interaction {source_entity_uid: $entry_uid})
            WHERE i.result_status IN $allowed_from
            SET i.result_status = $new_status,
                i.updated_at = datetime()
            RETURN count(i) AS transitioned
            """,
            {
                "entry_uid": entry_uid,
                "new_status": new_status.value,
                "allowed_from": [status.value for status in allowed_from],
            },
        )
        if result.is_error:
            return Result.fail(result)
        rows = result.value or []
        transitioned = int(rows[0].get("transitioned", 0)) if rows else 0
        return Result.ok(transitioned)


class ReportScheduleBackend(UniversalNeo4jBackend["ReportSchedule"]):
    """
    Domain backend for ReportSchedule entities.

    Extends UniversalNeo4jBackend with schedule-specific queries:
    - create_user_schedule_relationship: HAS_SCHEDULE link
    - get_due_schedules: Active schedules past their next_due_at
    """

    async def create_user_schedule_relationship(
        self, user_uid: str, schedule_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Create HAS_SCHEDULE relationship between User and ReportSchedule."""
        return await self.execute_query(
            """
            MATCH (u:User {uid: $user_uid})
            MATCH (s:ReportSchedule {uid: $schedule_uid})
            MERGE (u)-[:HAS_SCHEDULE]->(s)
            RETURN true AS success
            """,
            {"user_uid": user_uid, "schedule_uid": schedule_uid},
        )

    async def get_due_schedules(self, min_interval_hours: int) -> Result[list[Neo4jProperties]]:
        """
        Get all active schedules that are due for generation.

        Enforces a minimum interval between automatic report generations.
        """
        return await self.execute_query(
            """
            MATCH (s:ReportSchedule)
            WHERE s.is_active = true
              AND datetime(s.next_due_at) <= datetime()
              AND (
                s.last_generated_at IS NULL
                OR datetime(s.last_generated_at) <= datetime() - duration({hours: $min_interval_hours})
              )
            RETURN s
            ORDER BY s.next_due_at ASC
            """,
            {"min_interval_hours": min_interval_hours},
        )


class ActivityReportGeneratorBackend:
    """
    Backend for ProgressReportGenerator queries.

    Encapsulates cooldown check and previous-annotation fetch queries.
    Uses raw Cypher via executor — these are cross-entity queries not
    suited for UniversalNeo4jBackend.
    """

    def __init__(self, executor: Neo4jQueryExecutor) -> None:
        self.executor = executor

    async def check_cooldown(
        self, user_uid: str, cooldown_minutes: int
    ) -> Result[list[Neo4jProperties]]:
        """Check if an ActivityReport was generated within cooldown_minutes."""
        return await self.executor.execute_query(
            """
            MATCH (user:User {uid: $user_uid})-[:OWNS]->(ar:Entity)
            WHERE ar.entity_type = 'activity_report'
              AND datetime(ar.created_at) >= datetime() - duration({minutes: $cooldown_minutes})
            RETURN count(ar) AS recent_count
            """,
            {"user_uid": user_uid, "cooldown_minutes": cooldown_minutes},
        )

    async def get_previous_annotation(
        self, user_uid: str, period_start: str
    ) -> Result[list[Neo4jProperties]]:
        """Get the most recent user_annotation from a prior ActivityReport."""
        return await self.executor.execute_query(
            """
            MATCH (user:User {uid: $user_uid})-[:OWNS]->(ar:Entity)
            WHERE ar.entity_type = 'activity_report'
              AND (ar.user_annotation IS NOT NULL OR ar.user_revision IS NOT NULL)
              AND datetime(ar.period_end) < datetime($period_start)
            RETURN COALESCE(ar.user_annotation, ar.user_revision) AS annotation
            ORDER BY ar.period_end DESC
            LIMIT 1
            """,
            {"user_uid": user_uid, "period_start": period_start},
        )
