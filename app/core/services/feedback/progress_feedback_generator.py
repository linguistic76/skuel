"""
Progress Feedback Generator
============================

Generates AI-powered activity feedback by querying historical completions
from Neo4j, then sending those stats as LLM context for qualitative analysis.

Two-stage pipeline:
    1. Graph queries → activity stats dict (raw data)
    2. LLM call     → qualitative insights (interpreted data)

Result stored as ActivityReport entity (EntityType.ACTIVITY_REPORT):
    processed_content = LLM-generated qualitative feedback text
    metadata          = raw activity stats dict

When no LLM is configured, falls back to programmatic markdown (AUTOMATIC).

See: /docs/architecture/FEEDBACK_ARCHITECTURE.md
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.ports import QueryExecutor
    from core.services.ai_service import OpenAIService
    from core.services.feedback.activity_report_service import ActivityReportService
    from core.services.insight.insight_store import InsightStore
    from core.services.user.unified_user_context import UserContext
    from core.services.user.user_context_builder import UserContextBuilder

from core.constants import FeedbackTimePeriod
from core.events import publish_event
from core.events.submission_events import SubmissionCreated
from core.models.enums.entity_enums import EntityType, ProcessorType
from core.models.enums.submissions_enums import ProgressDepth
from core.models.feedback.activity_report import ActivityReport
from core.ports.infrastructure_protocols import EventBusOperations
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.services.feedback.progress_generator")

_PROMPT_TEMPLATE_PATH = Path(__file__).parent / "prompts" / "activity_feedback.md"


class ProgressFeedbackGenerator:
    """
    Generates activity feedback for users by querying historical completions
    and sending those stats as LLM context for qualitative analysis.

    Constructor dependencies:
        executor: QueryExecutor for Cypher queries (annotation lookup only)
        activity_report_service: ActivityReportService for persisting ActivityReport entities
        context_builder: UserContextBuilder — build_rich(window=) populates entities_rich
        openai_service: Optional OpenAI service (enables LLM generation)
        user_service: Optional UserOperations (reserved for future use)
        insight_store: Optional InsightStore for referencing active insights
        event_bus: Optional EventBusOperations for publishing events

    When openai_service is provided:
        processor_type = LLM, processed_content = LLM-generated text

    When openai_service is NOT provided:
        processor_type = AUTOMATIC, processed_content = programmatic markdown
    """

    def __init__(
        self,
        executor: "QueryExecutor",
        activity_report_service: "ActivityReportService",
        context_builder: "UserContextBuilder",
        openai_service: "OpenAIService | None" = None,
        user_service: Any | None = None,
        insight_store: "InsightStore | None" = None,
        event_bus: EventBusOperations | None = None,
    ) -> None:
        self.executor = executor
        self.activity_report_service = activity_report_service
        self.context_builder = context_builder
        self.openai_service = openai_service
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
        previous_annotation: str | None = None,
    ) -> Result[ActivityReport]:
        """
        Generate activity feedback for a user.

        Pipeline:
            1. Query activity stats from Neo4j (single round-trip via CALL {} subqueries)
            2. If LLM available: send stats as context → qualitative feedback text
               Else: build programmatic markdown summary
            3. Create and persist ActivityReport entity

        Args:
            user_uid: User to generate activity feedback for
            time_period: Time window (7d, 14d, 30d, 90d)
            domains: Domains to include (empty = all activity domains)
            depth: Detail level (summary, standard, detailed)
            include_insights: Whether to include active insights
            previous_annotation: User's self-reflection from their most recent prior
                report. When provided by a caller that already holds UserContext
                (context.latest_activity_report_user_annotation), the database
                lookup for the previous annotation is skipped entirely.

        Returns:
            Result[ActivityReport] — the created feedback entity
        """
        days = FeedbackTimePeriod.DAYS.get(time_period, FeedbackTimePeriod.DEFAULT_DAYS)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        progress_depth = ProgressDepth(depth) if depth else ProgressDepth.STANDARD

        logger.info(
            f"Generating activity feedback for {user_uid}: period={time_period}, depth={depth}"
        )

        try:
            # 1. Query historical completions (raw stats)
            completions = await self._query_completions(
                user_uid, start_date, end_date, domains, window=time_period
            )

            # 2. Get active insights if requested
            insights: list[Any] = []
            if include_insights and self.insight_store:
                insights_result = await self.insight_store.get_active_insights(user_uid, limit=10)
                if insights_result.is_ok:
                    insights = insights_result.value or []

            # 3. Build content — LLM when available, programmatic fallback
            processor_type = ProcessorType.AUTOMATIC
            processing_error: str | None = None

            # Use caller-supplied annotation when available (saves 1 round-trip);
            # otherwise fetch from the database.
            effective_annotation = (
                previous_annotation
                if previous_annotation is not None
                else await self._fetch_previous_annotation(user_uid, start_date)
            )

            if self.openai_service:
                llm_result = await self._generate_llm_feedback(
                    completions, insights, time_period, depth, effective_annotation
                )
                if llm_result.is_ok:
                    content = llm_result.value
                    processor_type = ProcessorType.LLM
                    logger.info(f"LLM feedback generated for {user_uid}: {len(content)} chars")
                else:
                    # LLM failed — fall back to programmatic, record the error
                    processing_error = f"LLM generation failed: {llm_result.expect_error()}"
                    logger.warning(f"LLM fallback for {user_uid}: {processing_error}")
                    content = self._build_report_content(
                        completions, insights, start_date, end_date, progress_depth
                    )
            else:
                content = self._build_report_content(
                    completions, insights, start_date, end_date, progress_depth
                )

            # 4. Build metadata stats (raw data — preserved regardless of LLM use)
            metadata = {
                "time_period": time_period,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "depth": depth,
                "tasks_completed": completions.get("tasks_completed", 0),
                "goals_progressed": completions.get("goals_progressed", 0),
                "habits_completed": completions.get("habits_completed", 0),
                "events_attended": completions.get("events_attended", 0),
                "choices_made": completions.get("choices_made", 0),
                "principles_reviewed": completions.get("principles_reviewed", 0),
                "insights_referenced": len(insights),
                "llm_generated": processor_type == ProcessorType.LLM,
            }

            # 5. Create ActivityReport entity
            report = ActivityReport.create(
                user_uid=user_uid,
                subject_uid=user_uid,
                content=content,
                processor_type=processor_type,
                period_start=start_date,
                period_end=end_date,
                time_period=time_period,
                domains=domains,
                depth=depth,
                processing_error=processing_error,
                insights_referenced=tuple(
                    getattr(i, "uid", "") for i in insights if getattr(i, "uid", None)
                ),
                metadata=metadata,
            )

            create_result = await self.activity_report_service.persist(report)
            if create_result.is_error:
                return Result.fail(create_result.expect_error())

            # 6. Publish event
            event = SubmissionCreated(
                submission_uid=report.uid,
                user_uid=user_uid,
                ku_type=EntityType.ACTIVITY_REPORT.value,
                processor_type=processor_type.value,
                occurred_at=datetime.now(),
            )
            await publish_event(self.event_bus, event, logger)

            logger.info(f"Generated progress Ku {report.uid} for {user_uid}")
            return Result.ok(report)

        except Exception as e:
            logger.error(f"Failed to generate progress Ku for {user_uid}: {e}")
            return Result.fail(Errors.system(f"Failed to generate progress Ku: {e}"))

    # =========================================================================
    # LLM GENERATION
    # =========================================================================

    async def _generate_llm_feedback(
        self,
        completions: dict[str, Any],
        insights: list[Any],
        time_period: str,
        depth: str,
        previous_annotation: str | None = None,
    ) -> Result[str]:
        """Send activity stats to LLM and return qualitative feedback text.

        Args:
            completions: Raw activity stats from _query_completions()
            insights: Active insights for the user
            time_period: e.g. "7d"
            depth: "summary" | "standard" | "detailed"
            previous_annotation: User's self-reflection from their most recent prior report

        Returns:
            Result[str] — LLM-generated feedback text
        """
        if not self.openai_service:
            return Result.fail(
                Errors.integration("OpenAI", "generate", "No LLM service configured")
            )

        prompt = self._build_llm_prompt(
            completions, insights, time_period, depth, previous_annotation
        )
        return await self.openai_service.generate_completion(
            prompt=prompt,
            max_tokens=2000 if depth == "detailed" else 1000,
            temperature=0.7,
            model="gpt-4o-mini",
        )

    def _build_llm_prompt(
        self,
        completions: dict[str, Any],
        insights: list[Any],
        time_period: str,
        depth: str,
        previous_annotation: str | None = None,
    ) -> str:
        """Build the LLM prompt from activity stats and prompt template.

        Loads the Markdown template, substitutes stats and configuration,
        returns the final prompt string.
        """
        try:
            template = _PROMPT_TEMPLATE_PATH.read_text()
        except FileNotFoundError:
            # Fallback inline template if file not found
            template = (
                "You are a personal development coach. Analyze this activity data "
                "from the past {time_period} and write a {depth} feedback report:\n\n"
                "Activity Data:\n{stats_json}\n\nActive Insights:\n{insights_section}"
            )

        # Serialize stats (exclude large detail lists for prompt efficiency)
        stats_summary = {
            "tasks_completed": completions.get("tasks_completed", 0),
            "tasks_total": completions.get("tasks_total", 0),
            "goals_progressed": completions.get("goals_progressed", 0),
            "habits_completed": completions.get("habits_completed", 0),
            "events_attended": completions.get("events_attended", 0),
            "choices_made": completions.get("choices_made", 0),
            "principles_reviewed": completions.get("principles_reviewed", 0),
            "goal_alignments": completions.get("goal_alignments", [])[:10],
            "knowledge_applications": completions.get("knowledge_applications", [])[:10],
            "task_titles": [t.get("title", "") for t in completions.get("tasks_details", [])[:10]],
            "goal_titles": [g.get("title", "") for g in completions.get("goals_details", [])[:10]],
            "habit_summary": [
                {"title": h.get("title", ""), "streak": h.get("streak", 0)}
                for h in completions.get("habits_details", [])[:10]
            ],
            "event_summary": [
                {
                    "title": e.get("title", ""),
                    "type": e.get("event_type", ""),
                    "milestone": e.get("is_milestone", False),
                }
                for e in completions.get("events_details", [])[:10]
            ],
            "principled_choices": [
                {"title": c.get("title", ""), "principles": c.get("principles", [])}
                for c in completions.get("choices_details", [])
                if c.get("principles")
            ][:5],
            "principle_summary": [
                {
                    "title": p.get("title", ""),
                    "alignment": p.get("alignment", ""),
                    "strength": p.get("strength", ""),
                }
                for p in completions.get("principles_details", [])[:10]
            ],
        }

        insights_section = "No active insights."
        if insights:
            insight_lines = []
            for insight in insights[:5]:
                title = getattr(insight, "title", "Untitled")
                impact = getattr(insight, "impact", "medium")
                insight_lines.append(f"- [{impact}] {title}")
            insights_section = "\n".join(insight_lines)

        rendered = template.format(
            time_period=time_period,
            depth=depth,
            stats_json=json.dumps(stats_summary, indent=2),
            insights_section=insights_section,
        )
        if previous_annotation:
            rendered += (
                f"\n\nUser's reflection from their previous activity report:\n"
                f"{previous_annotation}\n\n"
                f"Please acknowledge this reflection where the current data supports "
                f"or contradicts it."
            )
        return rendered

    # =========================================================================
    # GRAPH QUERIES
    # =========================================================================

    def _empty_completions(self) -> dict[str, Any]:
        """Return a zero-valued completions dict for error paths and empty results."""
        return {
            "tasks_completed": 0,
            "tasks_total": 0,
            "tasks_details": [],
            "goals_progressed": 0,
            "goals_details": [],
            "habits_completed": 0,
            "habits_details": [],
            "events_attended": 0,
            "events_details": [],
            "choices_made": 0,
            "choices_details": [],
            "principles_reviewed": 0,
            "principles_details": [],
            "goal_alignments": [],
            "knowledge_applications": [],
        }

    async def _query_completions(
        self,
        user_uid: str,
        start_date: datetime,
        end_date: datetime,
        domains: list[str] | None = None,
        window: str = "7d",
    ) -> dict[str, Any]:
        """Query historical completions via UserContextBuilder.build_rich().

        Delegates to context_builder.build_rich() with the given window, then maps
        context.entities_rich into the completions dict consumed by
        _build_report_content() and _build_llm_prompt().
        """
        ctx_result = await self.context_builder.build_rich(user_uid, window=window)
        if ctx_result.is_error:
            logger.warning(f"Failed to query activity completions: {ctx_result.error}")
            return self._empty_completions()

        return self._completions_from_context(ctx_result.value, domains)

    def _completions_from_context(
        self,
        context: "UserContext",
        domains: list[str] | None = None,
    ) -> dict[str, Any]:
        """Map context.entities_rich into the completions dict.

        Consumed by _build_report_content() and _build_llm_prompt().
        """
        include_all = domains is None
        result = self._empty_completions()

        # Tasks
        if include_all or "tasks" in (domains or []):
            for item in context.entities_rich.get("tasks", []):
                entity = item["entity"]
                graph_ctx = item.get("graph_context", {})
                result["tasks_total"] += 1
                if entity.get("status") == "completed":
                    result["tasks_completed"] += 1
                    for ref in graph_ctx.get("goal_refs", []):
                        if ref.get("title"):
                            result["goal_alignments"].append(ref["title"])
                    for ref in graph_ctx.get("ku_refs", []):
                        if ref.get("title"):
                            result["knowledge_applications"].append(ref["title"])
                result["tasks_details"].append({
                    "uid": entity["uid"],
                    "title": entity["title"],
                    "status": entity.get("status", ""),
                    "goals": [r["title"] for r in graph_ctx.get("goal_refs", []) if r.get("title")],
                    "reports": [r["title"] for r in graph_ctx.get("ku_refs", []) if r.get("title")],
                })

        # Goals
        if include_all or "goals" in (domains or []):
            for item in context.entities_rich.get("goals", []):
                entity = item["entity"]
                result["goals_progressed"] += 1
                result["goals_details"].append({
                    "uid": entity["uid"],
                    "title": entity["title"],
                    "status": entity.get("status", ""),
                    "progress": entity.get("progress"),
                })

        # Habits
        if include_all or "habits" in (domains or []):
            for item in context.entities_rich.get("habits", []):
                entity = item["entity"]
                if entity.get("status") == "completed":
                    result["habits_completed"] += 1
                result["habits_details"].append({
                    "uid": entity["uid"],
                    "title": entity["title"],
                    "status": entity.get("status", ""),
                    "streak": entity.get("streak", 0),
                })

        # Events
        if include_all or "events" in (domains or []):
            for item in context.entities_rich.get("events", []):
                entity = item["entity"]
                graph_ctx = item.get("graph_context", {})
                result["events_attended"] += 1
                result["events_details"].append({
                    "uid": entity["uid"],
                    "title": entity["title"],
                    "status": entity.get("status", ""),
                    "event_type": entity.get("event_type", ""),
                    "is_milestone": graph_ctx.get("is_milestone", False),
                })

        # Choices
        if include_all or "choices" in (domains or []):
            for item in context.entities_rich.get("choices", []):
                entity = item["entity"]
                graph_ctx = item.get("graph_context", {})
                result["choices_made"] += 1
                result["choices_details"].append({
                    "uid": entity["uid"],
                    "title": entity["title"],
                    "principles": [
                        r["title"] for r in graph_ctx.get("principle_refs", []) if r.get("title")
                    ],
                })

        # Principles
        if include_all or "principles" in (domains or []):
            for item in context.entities_rich.get("principles", []):
                entity = item["entity"]
                result["principles_reviewed"] += 1
                result["principles_details"].append({
                    "uid": entity["uid"],
                    "title": entity["title"],
                    "status": entity.get("status", ""),
                    "alignment": entity.get("alignment", ""),
                    "strength": entity.get("strength", ""),
                    "category": entity.get("category", ""),
                })

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

        # Events
        events_details = completions.get("events_details", [])
        if events_details:
            milestone_events = [e for e in events_details if e.get("is_milestone")]
            sections.append("## Events")
            sections.append(f"- **Events this period:** {len(events_details)}")
            if milestone_events:
                sections.append(f"- **Milestone events:** {len(milestone_events)}")
            if depth != ProgressDepth.SUMMARY:
                for event in events_details[:10]:
                    event_type = event.get("event_type") or "event"
                    milestone_marker = " ★" if event.get("is_milestone") else ""
                    sections.append(f"  - {event['title']} [{event_type}]{milestone_marker}")
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

        # Principles reviewed
        principles_details = completions.get("principles_details", [])
        if principles_details:
            well_aligned = [
                p for p in principles_details if p.get("alignment") in ("aligned", "flourishing")
            ]
            needs_attention = [
                p for p in principles_details if p.get("alignment") in ("drifting", "misaligned")
            ]
            sections.append("## Principles")
            sections.append(f"- **Principles active this period:** {len(principles_details)}")
            if well_aligned:
                sections.append(f"- **Well-aligned:** {len(well_aligned)}")
            if needs_attention:
                sections.append(f"- **Need attention:** {len(needs_attention)}")
            if depth != ProgressDepth.SUMMARY:
                for principle in principles_details[:10]:
                    alignment = principle.get("alignment") or "unknown"
                    strength = principle.get("strength") or ""
                    strength_label = f" ({strength})" if strength else ""
                    sections.append(f"  - {principle['title']}{strength_label} [{alignment}]")
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

    async def _fetch_previous_annotation(
        self, user_uid: str, current_period_start: datetime
    ) -> str | None:
        """Return the most recent user_annotation from a prior ActivityReport, or None.

        Uses period_end < current_period_start to avoid reading the annotation of the
        report currently being generated (which won't exist yet, but avoids ambiguity).
        """
        _QUERY = """
        MATCH (user:User {uid: $user_uid})-[:OWNS]->(ar:Entity)
        WHERE ar.entity_type = 'activity_report'
          AND ar.user_annotation IS NOT NULL
          AND ar.period_end < datetime($period_start)
        RETURN ar.user_annotation AS annotation
        ORDER BY ar.period_end DESC
        LIMIT 1
        """
        result = await self.executor.execute_query(
            _QUERY, {"user_uid": user_uid, "period_start": current_period_start.isoformat()}
        )
        if result.is_error or not result.value:
            return None
        return result.value[0].get("annotation") if result.value else None

