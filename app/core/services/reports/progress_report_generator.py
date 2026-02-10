"""
Progress Ku Generator
==========================

Generates system-created progress Ku by querying historical
completions from Neo4j, cross-referencing with UserContext, and
building structured markdown content.

Progress Ku are stored as Ku nodes with ku_type=AI_REPORT.
"""

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.services.insight.insight_store import InsightStore

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.events import publish_event
from core.events.report_events import ReportSubmitted
from core.models.enums.ku_enums import KuStatus, KuType, ProcessorType, ProgressDepth
from core.models.ku import Ku
from core.services.protocols.infrastructure_protocols import EventBusOperations
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator

logger = get_logger("skuel.services.ku.progress_generator")

# Time period mapping
TIME_PERIOD_DAYS = {
    "7d": 7,
    "14d": 14,
    "30d": 30,
    "90d": 90,
}


class ProgressKuGenerator:
    """
    Generates progress Ku by querying historical activity completions.

    Constructor dependencies:
        driver: Neo4j async driver for direct Cypher queries
        ku_backend: UniversalNeo4jBackend[Ku] for creating Ku nodes
        user_service: UserOperations for building UserContext
        insight_store: InsightStore for referencing active insights
        event_bus: EventBusOperations for publishing events
    """

    def __init__(
        self,
        driver: Any,
        ku_backend: UniversalNeo4jBackend[Ku],
        user_service: Any | None = None,
        insight_store: "InsightStore | None" = None,
        event_bus: EventBusOperations | None = None,
    ) -> None:
        self.driver = driver
        self.ku_backend = ku_backend
        self.user_service = user_service
        self.insight_store = insight_store
        self.event_bus = event_bus

    async def generate(
        self,
        user_uid: str,
        time_period: str = "7d",
        domains: list[str] | None = None,
        depth: str = "standard",
        include_insights: bool = True,
    ) -> Result[Ku]:
        """
        Generate a progress Ku for a user.

        Args:
            user_uid: User to generate progress Ku for
            time_period: Time window (7d, 14d, 30d, 90d)
            domains: Domains to include (empty = all activity domains)
            depth: Detail level (summary, standard, detailed)
            include_insights: Whether to include active insights

        Returns:
            Result containing the created Ku
        """
        days = TIME_PERIOD_DAYS.get(time_period, 7)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        progress_depth = ProgressDepth(depth) if depth else ProgressDepth.STANDARD

        logger.info(
            f"Generating progress Ku for {user_uid}: period={time_period}, depth={depth}"
        )

        try:
            # 1. Query historical completions
            completions = await self._query_completions(user_uid, start_date, end_date, domains)

            # 2. Get active insights if requested
            insights: list[Any] = []
            if include_insights and self.insight_store:
                insights_result = await self.insight_store.get_active_insights(user_uid, limit=10)
                if insights_result.is_ok:
                    insights = insights_result.value or []

            # 3. Build content
            title = f"Progress Report — {start_date.strftime('%b %d')} to {end_date.strftime('%b %d, %Y')}"
            content = self._build_report_content(
                completions, insights, start_date, end_date, progress_depth
            )

            # 4. Build metadata stats
            metadata = {
                "time_period": time_period,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "depth": depth,
                "tasks_completed": completions.get("tasks_completed", 0),
                "goals_progressed": completions.get("goals_progressed", 0),
                "habits_completed": completions.get("habits_completed", 0),
                "insights_referenced": len(insights),
            }

            # 5. Create Ku node
            uid = UIDGenerator.generate_uid("ku")
            ku = Ku(
                uid=uid,
                title=title,
                ku_type=KuType.AI_REPORT,
                user_uid=user_uid,
                status=KuStatus.COMPLETED,
                processor_type=ProcessorType.AUTOMATIC,
                processed_content=content,
                subject_uid=user_uid,
                metadata=metadata,
            )

            create_result = await self.ku_backend.create(ku)
            if create_result.is_error:
                return Result.fail(create_result.expect_error())

            # 6. Create BASED_ON_INSIGHT relationships
            if insights:
                await self._create_insight_relationships(uid, insights)

            # 7. Publish event
            event = ReportSubmitted(
                report_uid=uid,
                user_uid=user_uid,
                report_type=KuType.AI_REPORT.value,
                processor_type=ProcessorType.AUTOMATIC.value,
                occurred_at=datetime.now(),
            )
            await publish_event(self.event_bus, event, logger)

            logger.info(f"Generated progress Ku {uid} for {user_uid}")
            return Result.ok(ku)

        except Exception as e:
            logger.error(f"Failed to generate progress Ku for {user_uid}: {e}")
            return Result.fail(Errors.system(f"Failed to generate progress Ku: {e}"))

    async def _query_completions(
        self,
        user_uid: str,
        start_date: datetime,
        end_date: datetime,
        domains: list[str] | None = None,
    ) -> dict[str, Any]:
        """Query historical completions across domains within the time window."""
        result: dict[str, Any] = {
            "tasks_completed": 0,
            "tasks_total": 0,
            "tasks_details": [],
            "goals_progressed": 0,
            "goals_details": [],
            "habits_completed": 0,
            "habits_details": [],
            "choices_made": 0,
            "choices_details": [],
            "goal_alignments": [],
            "knowledge_applications": [],
        }

        include_all = not domains

        # Tasks completed in period
        if include_all or "tasks" in domains:
            try:
                records, _, _ = await self.driver.execute_query(
                    """
                    MATCH (u:User {uid: $user_uid})-[:OWNS]->(t:Task)
                    WHERE t.updated_at >= datetime($start) AND t.updated_at <= datetime($end)
                    WITH t, t.status = 'completed' AS is_completed
                    OPTIONAL MATCH (t)-[:FULFILLS_GOAL]->(g:Goal)
                    OPTIONAL MATCH (t)-[:APPLIES_KNOWLEDGE]->(ku:Ku)
                    RETURN t.uid AS uid, t.title AS title, t.status AS status,
                           is_completed,
                           collect(DISTINCT g.title) AS goal_titles,
                           collect(DISTINCT ku.title) AS ku_titles
                    ORDER BY t.updated_at DESC
                    """,
                    user_uid=user_uid,
                    start=start_date.isoformat(),
                    end=end_date.isoformat(),
                )
                completed = [r for r in records if r["is_completed"]]
                result["tasks_completed"] = len(completed)
                result["tasks_total"] = len(records)
                result["tasks_details"] = [
                    {
                        "uid": r["uid"],
                        "title": r["title"],
                        "status": r["status"],
                        "goals": r["goal_titles"],
                        "kus": r["ku_titles"],
                    }
                    for r in records
                ]
                for r in completed:
                    for gt in r["goal_titles"]:
                        if gt:
                            result["goal_alignments"].append(gt)
                for r in completed:
                    for ku in r["ku_titles"]:
                        if ku:
                            result["knowledge_applications"].append(ku)
            except Exception as e:
                logger.warning(f"Failed to query task completions: {e}")

        # Goals progressed in period
        if include_all or "goals" in domains:
            try:
                records, _, _ = await self.driver.execute_query(
                    """
                    MATCH (u:User {uid: $user_uid})-[:OWNS]->(g:Goal)
                    WHERE g.updated_at >= datetime($start) AND g.updated_at <= datetime($end)
                    RETURN g.uid AS uid, g.title AS title, g.status AS status,
                           g.progress AS progress
                    ORDER BY g.updated_at DESC
                    """,
                    user_uid=user_uid,
                    start=start_date.isoformat(),
                    end=end_date.isoformat(),
                )
                result["goals_progressed"] = len(records)
                result["goals_details"] = [
                    {
                        "uid": r["uid"],
                        "title": r["title"],
                        "status": r["status"],
                        "progress": r["progress"],
                    }
                    for r in records
                ]
            except Exception as e:
                logger.warning(f"Failed to query goal progress: {e}")

        # Habits completed in period
        if include_all or "habits" in domains:
            try:
                records, _, _ = await self.driver.execute_query(
                    """
                    MATCH (u:User {uid: $user_uid})-[:OWNS]->(h:Habit)
                    WHERE h.updated_at >= datetime($start) AND h.updated_at <= datetime($end)
                    RETURN h.uid AS uid, h.title AS title, h.status AS status,
                           h.streak_count AS streak
                    ORDER BY h.updated_at DESC
                    """,
                    user_uid=user_uid,
                    start=start_date.isoformat(),
                    end=end_date.isoformat(),
                )
                result["habits_completed"] = len([r for r in records if r["status"] == "completed"])
                result["habits_details"] = [
                    {
                        "uid": r["uid"],
                        "title": r["title"],
                        "status": r["status"],
                        "streak": r["streak"],
                    }
                    for r in records
                ]
            except Exception as e:
                logger.warning(f"Failed to query habit completions: {e}")

        # Choices made in period
        if include_all or "choices" in domains:
            try:
                records, _, _ = await self.driver.execute_query(
                    """
                    MATCH (u:User {uid: $user_uid})-[:OWNS]->(c:Choice)
                    WHERE c.created_at >= datetime($start) AND c.created_at <= datetime($end)
                    OPTIONAL MATCH (c)-[:INFORMED_BY_PRINCIPLE]->(p:Principle)
                    RETURN c.uid AS uid, c.title AS title,
                           collect(DISTINCT p.title) AS principle_titles
                    ORDER BY c.created_at DESC
                    """,
                    user_uid=user_uid,
                    start=start_date.isoformat(),
                    end=end_date.isoformat(),
                )
                result["choices_made"] = len(records)
                result["choices_details"] = [
                    {
                        "uid": r["uid"],
                        "title": r["title"],
                        "principles": r["principle_titles"],
                    }
                    for r in records
                ]
            except Exception as e:
                logger.warning(f"Failed to query choices: {e}")

        return result

    def _build_report_content(
        self,
        completions: dict[str, Any],
        insights: list[Any],
        start_date: datetime,
        end_date: datetime,
        depth: ProgressDepth,
    ) -> str:
        """Build markdown report content from completions data."""
        sections: list[str] = []
        period_label = f"{start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')}"

        sections.append(f"# Progress Report: {period_label}\n")

        # Task Completion Summary
        tasks_completed = completions.get("tasks_completed", 0)
        tasks_total = completions.get("tasks_total", 0)
        if tasks_total > 0:
            rate = (tasks_completed / tasks_total * 100) if tasks_total else 0
            sections.append("## Task Completion Summary")
            sections.append(f"- **Completed:** {tasks_completed} / {tasks_total} ({rate:.0f}%)")
            if depth != ProgressDepth.SUMMARY:
                for task in completions.get("tasks_details", [])[:10]:
                    status_icon = "done" if task["status"] == "completed" else task["status"]
                    sections.append(f"  - {task['title']} [{status_icon}]")
            sections.append("")

        # Goal Alignment
        goal_alignments = completions.get("goal_alignments", [])
        goals_progressed = completions.get("goals_progressed", 0)
        if goals_progressed > 0 or goal_alignments:
            sections.append("## Goal Alignment")
            sections.append(f"- **Goals touched:** {goals_progressed}")
            if goal_alignments:
                unique_goals = list(set(goal_alignments))
                sections.append(f"- **Tasks served goals:** {', '.join(unique_goals[:5])}")
            if depth != ProgressDepth.SUMMARY:
                for goal in completions.get("goals_details", [])[:10]:
                    progress = goal.get("progress") or "—"
                    sections.append(
                        f"  - {goal['title']} [{goal['status']}] (progress: {progress})"
                    )
            sections.append("")

        # Knowledge Application
        ku_apps = completions.get("knowledge_applications", [])
        if ku_apps:
            sections.append("## Knowledge Application")
            unique_kus = list(set(ku_apps))
            sections.append(f"- **KUs applied:** {len(unique_kus)} ({', '.join(unique_kus[:5])})")
            sections.append("")

        # Habits
        habits_completed = completions.get("habits_completed", 0)
        habits_details = completions.get("habits_details", [])
        if habits_details:
            sections.append("## Habit Activity")
            sections.append(f"- **Habits active:** {len(habits_details)}")
            sections.append(f"- **Completed this period:** {habits_completed}")
            if depth != ProgressDepth.SUMMARY:
                for habit in habits_details[:10]:
                    streak = habit.get("streak") or 0
                    sections.append(f"  - {habit['title']} [{habit['status']}] (streak: {streak})")
            sections.append("")

        # Principle Alignment (from choices)
        choices_details = completions.get("choices_details", [])
        if choices_details:
            principled_choices = [c for c in choices_details if c.get("principles")]
            sections.append("## Principle Alignment")
            sections.append(f"- **Choices made:** {len(choices_details)}")
            sections.append(f"- **Guided by principles:** {len(principled_choices)}")
            if depth != ProgressDepth.SUMMARY and principled_choices:
                for choice in principled_choices[:5]:
                    principles = ", ".join(p for p in choice["principles"] if p)
                    sections.append(f"  - {choice['title']} (guided by: {principles})")
            sections.append("")

        # Active Insights
        if insights:
            sections.append("## Active Insights")
            for insight in insights[:5]:
                title = getattr(insight, "title", "Untitled")
                impact = getattr(insight, "impact", "medium")
                sections.append(f"- **[{impact}]** {title}")
            sections.append("")

        # Empty report fallback
        if len(sections) <= 1:
            sections.append("No activity recorded in this period.")

        return "\n".join(sections)

    async def _create_insight_relationships(self, ku_uid: str, insights: list[Any]) -> None:
        """Create BASED_ON_INSIGHT relationships between Ku and insights."""
        for insight in insights:
            insight_uid = getattr(insight, "uid", None)
            if not insight_uid:
                continue
            try:
                await self.driver.execute_query(
                    """
                    MATCH (k:Ku {uid: $ku_uid})
                    MATCH (i:Insight {uid: $insight_uid})
                    MERGE (k)-[:BASED_ON_INSIGHT]->(i)
                    """,
                    ku_uid=ku_uid,
                    insight_uid=insight_uid,
                )
            except Exception as e:
                logger.warning(f"Failed to create BASED_ON_INSIGHT for {insight_uid}: {e}")
