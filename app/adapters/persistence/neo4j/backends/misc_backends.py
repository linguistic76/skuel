"""Miscellaneous backends: ActivityReport, Resource, Interaction, ActivityReportGenerator."""

from __future__ import annotations

from typing import TYPE_CHECKING

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.enums.entity_enums import EntityType
from core.models.enums.pipeline import ReportSource
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
    from core.models.resource.resource import Resource  # noqa: F401


#: The ActivityReport discriminator, bound as a parameter — never a raw literal,
#: so an enum-value change cannot leave a report query silently matching nothing.
_ACTIVITY_REPORT = EntityType.ACTIVITY_REPORT.value
#: The processor_type of an admin-written report. A generated-report read
#: (cooldown, period reuse, annotation carry-forward, the comparison history)
#: excludes it: the subject owns it (Submit & Share arc R11), so the owner scope alone
#: would let an admin's review stand in for the user's own generation. The
#: predicate is null-safe — generated rows written before processor_type was
#: stamped carry none.
_HUMAN = ReportSource.HUMAN.value


class ActivityReportBackend(UniversalNeo4jBackend[ActivityReport]):
    """
    Domain backend for ActivityReport entities.

    Moves inline Cypher from ActivityReportService into named backend methods.
    Methods: get_for_user, find_by_period, get_history, annotate, get_annotation,
    get_admin_snapshots, get_shares_granted.

    ``created_at`` is a mixed column (ISO strings, a minority of zoned
    datetimes), and Neo4j orders values of different types by TYPE before
    value — so every "newest first" here orders by ``datetime(n.created_at)``,
    never the raw property, or a ``LIMIT 1`` could hand back a stale row.
    """

    async def get_for_user(self, uid: str, user_uid: str) -> Result[list[Neo4jProperties]]:
        """Get a single ActivityReport by UID, scoped to the owning user."""
        return await self.execute_query(
            """
            MATCH (n:Entity {uid: $uid, user_uid: $user_uid, entity_type: $entity_type})
            RETURN n
            """,
            {"entity_type": _ACTIVITY_REPORT, "uid": uid, "user_uid": user_uid},
        )

    async def find_by_period(
        self, user_uid: UserUID, subject_uid: str, time_period: str
    ) -> Result[list[Neo4jProperties]]:
        """The newest GENERATED ActivityReport the user OWNS about ``subject_uid``
        for one ``time_period`` token, at most one row — partial or final alike.

        An admin-written (HUMAN) report of the same period is the subject's
        too, but it is a review, not a generation: it never stands in for the
        period's report, so it is excluded here. Whether the row is reusable
        (a closed period's partial report is not) is the service's verdict.
        """
        return await self.execute_query(
            """
            MATCH (n:Entity {entity_type: $entity_type, user_uid: $user_uid,
                             subject_uid: $subject_uid, time_period: $time_period})
            WHERE coalesce(n.processor_type, '') <> $human
            RETURN n
            ORDER BY datetime(n.created_at) DESC
            LIMIT 1
            """,
            {
                "entity_type": _ACTIVITY_REPORT,
                "user_uid": user_uid,
                "subject_uid": subject_uid,
                "time_period": time_period,
                "human": _HUMAN,
            },
        )

    async def get_history(
        self, subject_uid: str, limit: int = 20, generated_only: bool = False
    ) -> Result[list[Neo4jProperties]]:
        """The subject's ActivityReports, newest first — admin-written ones
        included unless ``generated_only`` (the comparison read wants the
        subject's own generations only)."""
        return await self.execute_query(
            """
            MATCH (n:Entity {entity_type: $entity_type, subject_uid: $subject_uid})
            WHERE NOT $generated_only OR coalesce(n.processor_type, '') <> $human
            RETURN n
            ORDER BY datetime(n.created_at) DESC
            LIMIT $limit
            """,
            {
                "entity_type": _ACTIVITY_REPORT,
                "subject_uid": subject_uid,
                "limit": limit,
                "generated_only": generated_only,
                "human": _HUMAN,
            },
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
            MATCH (n:Entity {uid: $uid, user_uid: $user_uid, entity_type: $entity_type})
            SET n.annotation_mode = $annotation_mode,
                n.annotation_updated_at = datetime($now),
                n.user_annotation = $user_annotation,
                n.user_revision = $user_revision
            RETURN n.uid AS uid, n.annotation_mode AS annotation_mode,
                   n.user_annotation AS user_annotation, n.user_revision AS user_revision
            """,
            {
                "entity_type": _ACTIVITY_REPORT,
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
            MATCH (n:Entity {uid: $uid, user_uid: $user_uid, entity_type: $entity_type})
            RETURN n.uid AS uid, n.annotation_mode AS annotation_mode,
                   n.user_annotation AS user_annotation, n.user_revision AS user_revision,
                   n.annotation_updated_at AS annotation_updated_at
            """,
            {"entity_type": _ACTIVITY_REPORT, "uid": uid, "user_uid": user_uid},
        )

    async def get_admin_snapshots(
        self, user_uid: UserUID, limit: int = 50
    ) -> Result[list[Neo4jProperties]]:
        """Get admin-written ActivityReports received by this user (privacy audit).

        The user owns every report about them; the admin is ``created_by``.
        """
        return await self.execute_query(
            """
            MATCH (n:Entity {entity_type: $entity_type, subject_uid: $user_uid})
            WHERE n.processor_type = $human
            RETURN n.created_at AS accessed_at,
                   n.created_by AS admin_uid,
                   n.time_period AS time_period
            ORDER BY datetime(n.created_at) DESC
            LIMIT $limit
            """,
            {
                "entity_type": _ACTIVITY_REPORT,
                "user_uid": user_uid,
                "limit": limit,
                "human": _HUMAN,
            },
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
        self, user_uid: str, cooldown_minutes: int, time_period: str
    ) -> Result[list[Neo4jProperties]]:
        """Count the user's GENERATED ActivityReports for ``time_period`` written
        within ``cooldown_minutes`` — the cooldown is keyed per (user, period).
        An admin's report on the user is theirs but not a generation: it never
        puts them in cooldown."""
        return await self.executor.execute_query(
            """
            MATCH (user:User {uid: $user_uid})-[:OWNS]->(ar:Entity)
            WHERE ar.entity_type = $entity_type
              AND ar.time_period = $time_period
              AND coalesce(ar.processor_type, '') <> $human
              AND datetime(ar.created_at) >= datetime() - duration({minutes: $cooldown_minutes})
            RETURN count(ar) AS recent_count
            """,
            {
                "entity_type": _ACTIVITY_REPORT,
                "user_uid": user_uid,
                "cooldown_minutes": cooldown_minutes,
                "time_period": time_period,
                "human": _HUMAN,
            },
        )

    async def count_habit_completions(
        self, user_uid: str, start: str, end: str
    ) -> Result[list[Neo4jProperties]]:
        """Per-habit counts of the user's HabitCompletion rows completed in
        [``start``, ``end``] (ISO strings). One row per habit with at least one
        completion; ``completed_at`` is coerced since it is stored as a string."""
        return await self.executor.execute_query(
            """
            MATCH (user:User {uid: $user_uid})-[:OWNS]->(hc:HabitCompletion)
            WHERE hc.completed_at IS NOT NULL
              AND datetime(hc.completed_at) >= datetime($start)
              AND datetime(hc.completed_at) <= datetime($end)
            RETURN hc.habit_uid AS habit_uid, count(hc) AS completions
            """,
            {"user_uid": user_uid, "start": start, "end": end},
        )

    async def get_previous_annotation(
        self, user_uid: str, period_start: str
    ) -> Result[list[Neo4jProperties]]:
        """Get the most recent user_annotation from a prior GENERATED
        ActivityReport (an admin's report is not the user's own reflection)."""
        return await self.executor.execute_query(
            """
            MATCH (user:User {uid: $user_uid})-[:OWNS]->(ar:Entity)
            WHERE ar.entity_type = $entity_type
              AND coalesce(ar.processor_type, '') <> $human
              AND (ar.user_annotation IS NOT NULL OR ar.user_revision IS NOT NULL)
              AND datetime(ar.period_end) < datetime($period_start)
            RETURN COALESCE(ar.user_annotation, ar.user_revision) AS annotation
            ORDER BY ar.period_end DESC
            LIMIT 1
            """,
            {
                "entity_type": _ACTIVITY_REPORT,
                "user_uid": user_uid,
                "period_start": period_start,
                "human": _HUMAN,
            },
        )
