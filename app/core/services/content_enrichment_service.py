"""
Content Enrichment Service
===========================

Enriches submitted content (audio transcripts, text) into formatted documents
using AI and Neo4j context.

Pipeline:
Submit (voice or text) → Extract (transcribe if audio) → Enrich (LLM + instructions)

The power comes from Neo4j context awareness:
- Recent entries, active goals, habits, tasks
- UserContext for personalized editing
- Processing instructions stored as Exercise Entity nodes in Neo4j

Renamed from ContentEnrichmentService to ContentEnrichmentService
"""

from contextlib import suppress
from dataclasses import asdict
from datetime import date, datetime
from typing import Any

from core.events import publish_event
from core.models.entity import Entity
from core.models.submissions.journal import Journal
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.relationship_names import RelationshipName
from core.models.submissions.submission import Submission
from core.models.submissions.submission_dto import SubmissionDTO
from core.ports import BackendOperations, BaseUpdatePayload
from core.services.base_service import BaseService
from core.services.domain_config import DomainConfig
from core.services.submissions.submission_processing_types import (
    SubmissionAIInsights,
    SubmissionProcessingContext,
)
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result


class ContentEnrichmentService(BaseService[BackendOperations[Entity], Entity]):
    """
    Transcript processor service - transforms raw transcripts into formatted documents.

    Core Capabilities:
    - Process transcript → formatted document (via AI pipeline)
    - Apply formatting instructions from Neo4j
    - Edit transcript using UserContext intelligence
    - Basic CRUD for storing processed documents

    NOT included (removed bloat):
    - ❌ Analytics (streaks, statistics, mood trends)
    - ❌ Category management
    - ❌ Tag management
    - ❌ Advanced search
    - ❌ Mood/energy tracking

    ARCHITECTURE NOTE:
    =================
    This service processes transcripts according to instruction sets stored in Neo4j.
    The output is stored in Report.processed_content (Option A architecture).

    Semantic Types Used:
    - APPLIES_KNOWLEDGE: Processed documents apply knowledge units practically
    - REQUIRES_KNOWLEDGE: Processed documents require prerequisite knowledge

    Source Tag: "content_enrichment_explicit"
    - Format: "content_enrichment_explicit" for user-created relationships
    - Format: "content_enrichment_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from document metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (uses pure Cypher)
    - Returns Result[T] for error handling
    - Logs operations with structured logging

    """

    # =========================================================================
    # DomainConfig (January 2026)
    # =========================================================================
    _config = DomainConfig(
        dto_class=SubmissionDTO,
        model_class=Entity,
        entity_label="Entity",
        search_fields=("title", "content", "processed_content"),
        search_order_by="created_at",
        user_ownership_relationship=RelationshipName.OWNS,  # User-owned content
    )

    def __init__(
        self,
        backend: BackendOperations[Entity] | None = None,
        transcription_service=None,
        ai_service=None,  # For intelligent editing (OpenAI/Anthropic)
        event_bus=None,  # For publishing domain events
    ) -> None:
        """
        Initialize transcript processor service.

        Args:
            backend: Backend for Ku storage,
            transcription_service: TranscriptionService for audio → text,
            ai_service: AI service for intelligent editing (e.g., OpenAI),
            event_bus: Event bus for publishing domain events (optional)
        """
        super().__init__(backend, "ContentEnrichmentService")
        self.transcription_service = transcription_service
        self.ai_service = ai_service
        self.event_bus = event_bus
        self.logger = get_logger("skuel.services.content_enrichment")

    # ========================================================================
    # DOMAIN-SPECIFIC CONTRACT
    # ========================================================================

    @property
    def entity_label(self) -> str:
        """Return the graph label for Entity nodes."""
        return "Entity"

    # ========================================================================
    # CORE PURPOSE: TRANSCRIPT PROCESSING
    # ========================================================================

    @with_error_handling("process_transcript")
    async def process_transcript(
        self,
        raw_transcript: str,
        instructions_uid: str | None = None,
        user_uid: str | None = None,
    ) -> Result[SubmissionAIInsights]:
        """
        Process raw transcript into formatted journal using Neo4j context.

        This is the PRIMARY method - the core purpose of this service.

        REFACTORED (November 10, 2025) - Option A Implementation:
        - No longer creates or stores entities directly
        - Returns SubmissionAIInsights (formatted data only)
        - SubmissionsProcessingService stores insights in Report.processed_content
        - SubmissionsRelationshipService creates graph relationships

        Steps:
        1. Pull relevant context from Neo4j (UserContext, recent journals, goals, tasks)
        2. Load formatting instructions (from Neo4j markdown)
        3. Apply AI-powered editing with context awareness
        4. Return formatted insights (NO entity creation)

        Args:
            raw_transcript: Raw text from transcription service,
            instructions_uid: UID of instruction set in Neo4j (default: use standard),
            user_uid: User identifier (optional, enables context-aware processing)

        Returns:
            Result containing SubmissionAIInsights (formatted content, title, summary, themes, actions)
        """
        # Step 1: Pull context from Neo4j (optional, but improves quality)
        context_obj = await self._gather_context(user_uid) if user_uid else None
        context = asdict(context_obj) if context_obj else None

        # Step 2: Load formatting instructions
        instructions = await self._load_instructions(instructions_uid)
        if instructions.is_error:
            return Result.fail(instructions)

        # Step 3: Apply intelligent editing
        insights_result = await self._apply_intelligent_editing(
            raw_transcript=raw_transcript, instructions=instructions.value, context=context
        )

        if insights_result.is_error:
            return insights_result

        insights = insights_result.value

        self.logger.info(
            f"Processed transcript: {len(raw_transcript)} chars → {len(insights.formatted_content)} chars formatted"
        )

        # Return formatted insights (NO entity creation)
        return Result.ok(insights)

    @with_error_handling("process_audio")
    async def process_audio(
        self,
        audio_file_path: str,
        instructions_uid: str | None = None,
        user_uid: str | None = None,
    ) -> Result[SubmissionAIInsights]:
        """
        Process audio file into formatted journal insights (full pipeline).

        Pipeline: Audio → Transcription → Processing → SubmissionAIInsights

        Args:
            audio_file_path: Path to audio file,
            instructions_uid: UID of instruction set,
            user_uid: User identifier (REQUIRED for context-aware processing)

        Returns:
            Result containing SubmissionAIInsights (formatted content, title, summary, themes)
        """
        if not user_uid:
            return Result.fail(
                Errors.validation(
                    "user_uid is REQUIRED for journal creation (fail-fast)", field="user_uid"
                )
            )
        if not self.transcription_service:
            return Result.fail(
                Errors.system(
                    "Transcription service not available - cannot process audio",
                    operation="process_audio",
                )
            )

        # Step 1: Transcribe audio → raw text
        transcription_result = await self.transcription_service.transcribe_file(audio_file_path)

        if transcription_result.is_error:
            return Result.fail(transcription_result.expect_error())

        raw_transcript = transcription_result.value.get("text") or transcription_result.value.get(
            "transcript"
        )

        # Step 2: Process transcript → formatted insights
        return await self.process_transcript(
            raw_transcript=raw_transcript,
            instructions_uid=instructions_uid,
            user_uid=user_uid,
        )

    # ========================================================================
    # CONTEXT GATHERING (Neo4j Intelligence)
    # ========================================================================

    @with_error_handling(
        "get_journal_context_for_processing", error_type="database", uid_param="user_uid"
    )
    async def get_journal_context_for_processing(
        self, user_uid: str
    ) -> Result[SubmissionProcessingContext]:
        """
        Get comprehensive context for intelligent journal processing.

        Step 3 Implementation (November 2025): Single Query Context Retrieval
        UPDATED (January 2026): Queries Report nodes instead of Journal nodes

        This single Cypher query replaces multiple separate queries, gathering:
        - Recent journal-type reports (last 7 days)
        - Active goals for progress tracking
        - Trending topics (last 30 days) for thematic continuity
        - Recent mood averages for emotional awareness

        Updated February 2026: Queries Entity nodes with ku_type="submission"
        (Journal→Report merge, assignment→submission rename).

        Args:
            user_uid: User identifier

        Returns:
            Result containing SubmissionProcessingContext with all contextual data
        """
        cypher = """
        MATCH (u:User {uid: $user_uid})

        // Recent journal-type reports (last 7 days)
        OPTIONAL MATCH (u)-[:OWNS]->(recent:Entity)
        WHERE recent.ku_type = 'submission'
          AND recent.created_at >= datetime() - duration('P7D')
        WITH u, collect({
            uid: recent.uid,
            title: recent.title,
            content: recent.content,
            entry_date: toString(date(recent.entry_date)),
            mood: recent.mood,
            energy_level: recent.energy_level,
            key_topics: recent.key_topics
        }) as recent_journals

        // Active goals
        OPTIONAL MATCH (u)-[:OWNS]->(g:Goal)
        WHERE g.status = 'active'
        WITH u, recent_journals, collect({
            uid: g.uid,
            title: g.title,
            description: g.description
        }) as active_goals

        // Recent topics (from last 30 days) - journal-type reports
        OPTIONAL MATCH (u)-[:OWNS]->(j:Entity)
        WHERE j.ku_type = 'submission'
          AND j.created_at >= datetime() - duration('P30D')
          AND j.key_topics IS NOT NULL
        WITH u, recent_journals, active_goals,
             collect(j.key_topics) as all_topics_raw,
             collect(j.energy_level) as all_energy_levels

        RETURN {
            recent_entries: recent_journals,
            active_goals: active_goals,
            all_topics_json: all_topics_raw,
            recent_mood_avg:
                CASE
                    WHEN size([e IN all_energy_levels WHERE e IS NOT NULL]) > 0
                    THEN reduce(sum = 0.0, e IN [x IN all_energy_levels WHERE x IS NOT NULL] | sum + e) /
                         size([e IN all_energy_levels WHERE e IS NOT NULL])
                    ELSE 0.0
                END,
            data_points: size(all_energy_levels)
        } as context
        """

        query_result = await self.backend.execute_query(cypher, {"user_uid": user_uid})

        if query_result.is_error:
            return Result.fail(query_result.expect_error())

        records = query_result.value or []
        if not records:
            # No data found - return empty context
            return Result.ok(
                SubmissionProcessingContext(
                    user_uid=user_uid,
                    gathered_at=datetime.now().isoformat(),
                    recent_journals=[],
                    active_goals=[],
                    recent_topics=[],
                    mood_trends=None,
                )
            )

        record = records[0]
        context_data = record["context"]

        # Process recent journals
        import json

        recent_journals_list = []
        for j in context_data.get("recent_entries", []):
            if j and j.get("uid"):
                # Parse key_topics from JSON string if needed
                key_topics = []
                if j.get("key_topics"):
                    with suppress(json.JSONDecodeError, TypeError):
                        key_topics = (
                            json.loads(j["key_topics"])
                            if isinstance(j["key_topics"], str)
                            else j["key_topics"]
                        )

                recent_journals_list.append(
                    {
                        "uid": j["uid"],
                        "title": j.get("title", ""),
                        "content_excerpt": j.get("content", "")[:200] if j.get("content") else "",
                        "date": j.get("entry_date", ""),
                        "mood": j.get("mood") or "not specified",
                        "energy_level": j.get("energy_level") or 0,
                        "key_topics": key_topics,
                    }
                )

        # Process active goals
        active_goals_list = [
            {
                "uid": g["uid"],
                "title": g.get("title", ""),
                "description": g.get("description", ""),
            }
            for g in context_data.get("active_goals", [])
            if g and g.get("uid")
        ]

        # Process topics - aggregate and count
        from collections import Counter

        all_topics = []
        for topics_json in context_data.get("all_topics_json", []):
            if topics_json:
                try:
                    topics = (
                        json.loads(topics_json) if isinstance(topics_json, str) else topics_json
                    )
                    if isinstance(topics, list):
                        all_topics.extend(topics)
                except (json.JSONDecodeError, TypeError):
                    pass

        # Get top 10 trending topics
        topic_counts = Counter(all_topics)
        trending_topics = [topic for topic, count in topic_counts.most_common(10)]

        # Build mood trends
        avg_energy = context_data.get("recent_mood_avg", 0.0)
        data_points = context_data.get("data_points", 0)

        # Simple trend detection (comparing first half vs second half of recent journals)
        trend = "stable"
        if len(recent_journals_list) >= 4:
            mid_point = len(recent_journals_list) // 2
            recent_half = [
                j["energy_level"] for j in recent_journals_list[:mid_point] if j["energy_level"]
            ]
            older_half = [
                j["energy_level"] for j in recent_journals_list[mid_point:] if j["energy_level"]
            ]

            if recent_half and older_half:
                recent_avg = sum(recent_half) / len(recent_half)
                older_avg = sum(older_half) / len(older_half)

                if recent_avg > older_avg + 1:
                    trend = "improving"
                elif recent_avg < older_avg - 1:
                    trend = "declining"

        mood_trends = {
            "average_energy": round(avg_energy, 1),
            "recent_moods": [
                j["mood"]
                for j in recent_journals_list[:5]
                if j["mood"] and j["mood"] != "not specified"
            ],
            "trend": trend,
            "data_points": data_points,
        }

        return Result.ok(
            SubmissionProcessingContext(
                user_uid=user_uid,
                gathered_at=datetime.now().isoformat(),
                recent_journals=recent_journals_list,
                active_goals=active_goals_list,
                recent_topics=trending_topics,
                mood_trends=mood_trends,
            )
        )

    async def _gather_context(self, user_uid: str) -> SubmissionProcessingContext:
        """
        Gather relevant context from Neo4j for intelligent editing.

        Step 3 Implementation (November 2025): Uses optimized single-query approach
        via get_journal_context_for_processing() instead of multiple separate queries.

        This is a convenience wrapper that returns SubmissionProcessingContext directly (not Result[T])
        for backward compatibility with existing code.

        Legacy multi-query helpers (_get_recent_journals, etc.) are kept for
        potential future use but no longer called by default.

        Args:
            user_uid: User identifier

        Returns:
            Context dataclass for AI editing with enhanced intelligence
        """
        result = await self.get_journal_context_for_processing(user_uid)

        if result.is_error:
            self.logger.warning(f"Failed to gather context: {result.error}")
            # Return empty context on error
            return SubmissionProcessingContext(
                user_uid=user_uid,
                gathered_at=datetime.now().isoformat(),
                recent_journals=[],
                active_goals=[],
                recent_topics=[],
                mood_trends=None,
            )

        return result.value

    async def _get_recent_journals(self, user_uid: str, days: int = 7) -> list[dict[str, str]]:
        """
        Get recent journal entries for context awareness.

        Updated February 2026: Queries Entity nodes with ku_type="submission".

        Args:
            user_uid: User identifier
            days: Number of days to look back (default: 7)

        Returns:
            List of journal dictionaries with title, content excerpt, date, mood, topics
        """
        from datetime import timedelta

        cutoff_datetime = datetime.now() - timedelta(days=days)

        cypher = """
        MATCH (j:Report {user_uid: $user_uid, report_type: 'journal'})
        WHERE j.created_at >= datetime($cutoff_datetime)
        RETURN j.uid as uid,
               j.title as title,
               j.content as content,
               date(j.entry_date) as entry_date,
               j.mood as mood,
               j.energy_level as energy_level,
               j.key_topics as key_topics
        ORDER BY j.created_at DESC
        LIMIT 10
        """

        result = await self.backend.execute_query(
            cypher, {"user_uid": user_uid, "cutoff_datetime": cutoff_datetime.isoformat()}
        )

        if result.is_error:
            self.logger.warning(f"Failed to get recent journals: {result.error}")
            return []

        journals = []
        for record in result.value or []:
            # Parse key_topics from JSON string or list
            import json

            key_topics = []
            if record["key_topics"]:
                with suppress(json.JSONDecodeError):
                    key_topics = (
                        json.loads(record["key_topics"])
                        if isinstance(record["key_topics"], str)
                        else record["key_topics"]
                    )

            journals.append(
                {
                    "uid": record["uid"],
                    "title": record["title"] or "Untitled",
                    "content_excerpt": record["content"][:200] if record["content"] else "",
                    "date": str(record["entry_date"]) if record["entry_date"] else "",
                    "mood": record["mood"] or "not specified",
                    "energy_level": record["energy_level"] or 0,
                    "key_topics": key_topics,
                }
            )

        return journals

    async def _get_active_goals(self, user_uid: str) -> list[dict[str, str]]:
        """
        Get active goals for the user.

        Args:
            user_uid: User identifier

        Returns:
            List of goal dictionaries with title and description
        """
        cypher = """
        MATCH (g:Goal {user_uid: $user_uid})
        WHERE g.status = 'active'
        RETURN g.uid as uid, g.title as title, g.description as description
        ORDER BY g.created_at DESC
        LIMIT 10
        """

        result = await self.backend.execute_query(cypher, {"user_uid": user_uid})

        if result.is_error:
            self.logger.warning(f"Failed to get active goals: {result.error}")
            return []

        return [
            {
                "uid": record["uid"],
                "title": record["title"],
                "description": record["description"] or "",
            }
            for record in result.value or []
        ]

    async def _get_recent_topics(self, user_uid: str, days: int = 30) -> list[str]:
        """
        Extract recurring topics from recent journals.

        Updated February 2026: Queries Entity nodes with ku_type="submission".

        Args:
            user_uid: User identifier
            days: Number of days to look back (default: 30)

        Returns:
            List of unique topics sorted by frequency
        """
        import json
        from collections import Counter
        from datetime import timedelta

        cutoff_datetime = datetime.now() - timedelta(days=days)

        cypher = """
        MATCH (j:Report {user_uid: $user_uid, report_type: 'journal'})
        WHERE j.created_at >= datetime($cutoff_datetime)
        RETURN j.key_topics as key_topics
        """

        result = await self.backend.execute_query(
            cypher, {"user_uid": user_uid, "cutoff_datetime": cutoff_datetime.isoformat()}
        )

        if result.is_error:
            self.logger.warning(f"Failed to get recent topics: {result.error}")
            return []

        # Aggregate all topics
        all_topics = []
        for record in result.value or []:
            if record["key_topics"]:
                try:
                    topics = (
                        json.loads(record["key_topics"])
                        if isinstance(record["key_topics"], str)
                        else record["key_topics"]
                    )
                    if isinstance(topics, list):
                        all_topics.extend(topics)
                except json.JSONDecodeError:
                    pass

        # Count frequency and return top 10
        topic_counts = Counter(all_topics)
        return [topic for topic, count in topic_counts.most_common(10)]

    async def _summarize_mood_trends(self, journals: list[dict[str, str]]) -> dict[str, Any]:
        """
        Analyze mood patterns from recent journals.

        Args:
            journals: List of journal dictionaries with mood and energy data

        Returns:
            Dictionary with mood trend summary
        """
        if not journals:
            return {"average_energy": 0, "recent_moods": [], "trend": "insufficient data"}

        # Extract energy levels and moods
        energy_levels = [j["energy_level"] for j in journals if j["energy_level"]]
        moods = [j["mood"] for j in journals if j["mood"] and j["mood"] != "not specified"]

        avg_energy = sum(energy_levels) / len(energy_levels) if energy_levels else 0

        # Simple trend detection
        trend = "stable"
        if len(energy_levels) >= 3:
            recent_avg = sum(energy_levels[:3]) / 3
            older_avg = (
                sum(energy_levels[3:]) / len(energy_levels[3:])
                if len(energy_levels) > 3
                else recent_avg
            )
            if recent_avg > older_avg + 1:
                trend = "improving"
            elif recent_avg < older_avg - 1:
                trend = "declining"

        return {
            "average_energy": round(avg_energy, 1),
            "recent_moods": moods[:5],  # Last 5 moods
            "trend": trend,
            "data_points": len(journals),
        }

    # ========================================================================
    # GRAPH RELATIONSHIP CREATION (Step 2 - November 2025)
    # ========================================================================

    @with_error_handling("create_journal_relationships", error_type="database")
    async def _create_journal_relationships(
        self, journal: Journal, context: SubmissionProcessingContext | None
    ) -> Result[dict[str, int]]:
        """
        Create graph relationships connecting journal to context.

        Step 2 Implementation (November 2025): Graph-Native Context Layer

        Creates relationships:
        1. FOLLOWS → Previous journal (temporal continuity)
        2. RELATED_TO → Journals with shared topics (thematic connections)
        3. SUPPORTS_GOAL → Goals mentioned in content (goal progress tracking)

        Args:
            journal: The newly created Journal
            context: SubmissionProcessingContext with recent data

        Returns:
            Result containing counts of relationships created
        """
        relationships_created = {"temporal": 0, "thematic": 0, "goal_support": 0}

        # 1. Temporal Relationship: FOLLOWS (previous journal)
        temporal_result = await self._create_temporal_relationship(journal.uid, journal.user_uid)
        relationships_created["temporal"] = temporal_result

        # 2. Thematic Relationships: RELATED_TO (shared topics)
        if context and context.recent_topics:
            thematic_result = await self._create_thematic_relationships(
                journal, context.recent_topics
            )
            relationships_created["thematic"] = thematic_result

        # 3. Goal Support Relationships: SUPPORTS_GOAL
        if context and context.active_goals:
            goal_result = await self._create_goal_relationships(journal, context.active_goals)
            relationships_created["goal_support"] = goal_result

        self.logger.info(
            f"Created journal relationships: {relationships_created['temporal']} temporal, "
            f"{relationships_created['thematic']} thematic, {relationships_created['goal_support']} goal_support"
        )

        return Result.ok(relationships_created)

    async def _create_temporal_relationship(self, journal_uid: str, user_uid: str) -> int:
        """Create FOLLOWS relationship to most recent previous journal-type report."""
        cypher = """
        MATCH (new:Entity {uid: $journal_uid})
        MATCH (prev:Entity {user_uid: $user_uid, report_type: 'journal'})
        WHERE prev.uid <> $journal_uid
          AND prev.entry_date <= new.entry_date
        WITH new, prev
        ORDER BY prev.entry_date DESC, prev.created_at DESC
        LIMIT 1
        MERGE (new)-[r:FOLLOWS]->(prev)
        RETURN count(r) as count
        """

        result = await self.backend.execute_query(
            cypher, {"journal_uid": journal_uid, "user_uid": user_uid}
        )
        if result.is_error:
            return 0
        records = result.value or []
        return records[0]["count"] if records else 0

    async def _create_thematic_relationships(
        self, journal: Journal, recent_topics: list[str]
    ) -> int:
        """Create RELATED_TO relationships for journal reports sharing topics."""

        # Get journal's topics (key_topics is only on Submission)
        journal_topics = getattr(journal, "key_topics", None) or []
        if not journal_topics:
            return 0

        # Find overlap with recent topics
        shared_topics = [t for t in journal_topics if t in recent_topics[:10]]
        if not shared_topics:
            return 0

        cypher = """
        MATCH (new:Entity {uid: $journal_uid})
        MATCH (other:Entity {user_uid: $user_uid, report_type: 'journal'})
        WHERE other.uid <> $journal_uid
          AND other.key_topics IS NOT NULL
        WITH new, other, other.key_topics as other_topics_json
        WHERE any(topic IN $shared_topics WHERE other_topics_json CONTAINS topic)
        WITH new, other
        LIMIT 5
        MERGE (new)-[r:RELATED_TO {shared_topics: $shared_topics_str}]->(other)
        RETURN count(r) as count
        """

        result = await self.backend.execute_query(
            cypher,
            {
                "journal_uid": journal.uid,
                "user_uid": journal.user_uid,
                "shared_topics": shared_topics,
                "shared_topics_str": ", ".join(shared_topics[:3]),
            },
        )
        if result.is_error:
            return 0
        records = result.value or []
        return records[0]["count"] if records else 0

    async def _create_goal_relationships(
        self, journal: Journal, active_goals: list[dict[str, str]]
    ) -> int:
        """Create SUPPORTS_GOAL relationships for mentioned goals."""
        # Extract goal mentions from journal content
        content_text = journal.content or getattr(journal, "processed_content", None) or ""
        if not content_text:
            return 0
        content_lower = content_text.lower()
        mentioned_goal_uids = []

        for goal in active_goals:
            goal_title_lower = goal["title"].lower()
            # Check if goal title appears in content
            if goal_title_lower in content_lower:
                mentioned_goal_uids.append(goal["uid"])

        if not mentioned_goal_uids:
            return 0

        cypher = """
        MATCH (j:Report {uid: $journal_uid})
        UNWIND $goal_uids as goal_uid
        MATCH (g:Goal {uid: goal_uid})
        MERGE (j)-[r:SUPPORTS_GOAL]->(g)
        RETURN count(r) as count
        """

        result = await self.backend.execute_query(
            cypher, {"journal_uid": journal.uid, "goal_uids": mentioned_goal_uids}
        )
        if result.is_error:
            return 0
        records = result.value or []
        return records[0]["count"] if records else 0

    # ========================================================================
    # INSTRUCTION SET MANAGEMENT
    # ========================================================================

    async def _load_instructions(self, instructions_uid: str | None = None) -> Result[str]:
        """
        Load formatting instructions from Neo4j.

        Instructions are stored as markdown files in Neo4j.
        Each set is ~8000 characters with formatting rules.

        Args:
            instructions_uid: UID of instruction set (None = default),

        Returns:
            Result containing instruction text
        """
        if not instructions_uid:
            instructions_uid = "instructions:default-report-formatting"

        # Load from Neo4j (instructions stored as Exercise Entity nodes)
        query = """
        MATCH (i:Entity {uid: $uid, ku_type: 'exercise'})
        RETURN i.instructions as instructions, i.name as name
        """

        result = await self.backend.execute_query(query, {"uid": instructions_uid})

        if result.is_error:
            self.logger.warning(f"Failed to load instructions, using default: {result.error}")
            return Result.ok(self._get_default_instructions())

        records = result.value or []
        if not records:
            # Return default instructions if not found
            return Result.ok(self._get_default_instructions())

        record = records[0]
        instructions = record["instructions"]
        self.logger.info(f"Loaded instructions: {record['name']} ({len(instructions)} chars)")

        return Result.ok(instructions)

    def _get_default_instructions(self) -> str:
        """
        Default formatting instructions.

        These are used when no custom instruction set is specified.
        """
        return """
# Journal Formatting Instructions

## Purpose
Transform raw transcript into well-formatted, flowing journal entry.

## Formatting Rules
1. **Structure**: Organize into coherent paragraphs
2. **Flow**: Remove verbal fillers ("um", "uh", "like")
3. **Clarity**: Improve sentence structure while preserving meaning
4. **Themes**: Identify main themes and group related content
5. **Action Items**: Extract concrete action items mentioned
6. **Title**: Generate concise, descriptive title

## Context Integration
- Reference active goals, tasks, habits when relevant
- Link to recent journal themes for continuity
- Identify learning opportunities from current paths

## Output Format
- Title (concise, descriptive)
- Summary (2-3 sentences)
- Main content (well-formatted paragraphs)
- Key themes (bullet list)
- Action items (if any)

Preserve the author's voice and authenticity while improving readability.
"""

    @with_error_handling("create_instruction_set", error_type="database", uid_param="uid")
    async def create_instruction_set(
        self, name: str, content: str, uid: str | None = None
    ) -> Result[dict[str, Any]]:
        """
        Create new instruction set in Neo4j.

        Args:
            name: Instruction set name,
            content: Markdown instructions (~8000 chars),
            uid: Optional custom UID

        Returns:
            Result containing created instruction set
        """
        if not uid:
            uid = f"instructions:{name.lower().replace(' ', '-')}"

        query = """
        CREATE (i:Entity:Exercise {
            uid: $uid,
            name: $name,
            ku_type: 'exercise',
            instructions: $instructions,
            created_at: datetime(),
            char_count: size($instructions)
        })
        RETURN i
        """

        result = await self.backend.execute_query(
            query, {"uid": uid, "name": name, "instructions": content}
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        return Result.ok({"uid": uid, "name": name, "char_count": len(content)})

    @with_error_handling("list_instruction_sets", error_type="database")
    async def list_instruction_sets(self) -> Result[list[dict[str, Any]]]:
        """List all available exercise instruction sets."""
        query = """
        MATCH (i:Entity {ku_type: 'exercise'})
        RETURN i.uid as uid, i.name as name, i.char_count as char_count
        ORDER BY i.name
        """

        result = await self.backend.execute_query(query)

        if result.is_error:
            return Result.fail(result.expect_error())

        instruction_sets = [
            {"uid": record["uid"], "name": record["name"], "char_count": record["char_count"]}
            for record in result.value or []
        ]

        return Result.ok(instruction_sets)

    # ========================================================================
    # AI-POWERED INTELLIGENT EDITING
    # ========================================================================

    @with_error_handling("apply_intelligent_editing", error_type="integration")
    async def _apply_intelligent_editing(
        self, raw_transcript: str, instructions: str, context: dict[str, Any] | None = None
    ) -> Result[SubmissionAIInsights]:
        """
        Apply AI-powered editing with context awareness.

        This is where the magic happens:
        1. Combines raw transcript + instructions + Neo4j context
        2. Sends to AI (OpenAI/Anthropic) for intelligent editing
        3. Returns formatted, context-aware insights

        REFACTORED (November 10, 2025) - Option A Implementation:
        - Returns SubmissionAIInsights directly (not dict)
        - No entity creation

        Args:
            raw_transcript: Raw text from transcription,
            instructions: Formatting instructions,
            context: Neo4j context (goals, tasks, recent journals)

        Returns:
            Result containing SubmissionAIInsights (formatted content, metadata)
        """
        # Fail-fast: AI service is required for journal formatting
        if not self.ai_service:
            return Result.fail(
                Errors.system(
                    message="AI service is required for journal formatting - "
                    "ensure OPENAI_API_KEY is configured",
                    operation="format_with_llm",
                )
            )

        # Build AI prompt with context
        prompt = self._build_editing_prompt(raw_transcript, instructions, context)

        # Call AI service for intelligent editing
        ai_result = await self.ai_service.generate_completion(
            prompt=prompt,
            max_tokens=8000,
            temperature=0.3,  # Lower temperature for consistent formatting
        )

        if ai_result.is_error:
            self.logger.error(f"AI generation failed: {ai_result.error}")
            return ai_result

        # Debug logging
        self.logger.info(
            f"AI result value type: {type(ai_result.value)}, value: {ai_result.value[:100] if ai_result.value else 'None'}"
        )

        # Parse AI response
        insights = self._parse_ai_response(ai_result.value)

        # Debug logging
        self.logger.info(
            f"Parsed AI response: title={insights.title[:50] if insights.title else 'None'}"
        )

        # Return SubmissionAIInsights directly (not dict)
        return Result.ok(insights)

    def _build_editing_prompt(
        self, raw_transcript: str, instructions: str, context: dict[str, Any] | None
    ) -> str:
        """Build comprehensive prompt for AI editing."""
        # COMPREHENSIVE ERROR TRACING - Find the exact .get() on None location
        self.logger.info(
            f"_build_editing_prompt called with context type: {type(context)}, context is None: {context is None}"
        )

        try:
            prompt_parts = [
                "# Journal Transcript Editing Task",
                "",
                "## Instructions",
                instructions,
                "",
            ]

            # Add enhanced context if available (Step 1 implementation)
            if context:
                prompt_parts.extend(
                    [
                        "## User Context (Enhanced Intelligence)",
                        "Use this context to provide intelligent, personalized, context-aware editing:",
                        "",
                    ]
                )

                # Active Goals
                self.logger.info("Processing active_goals context section")
                if context.get("active_goals"):
                    prompt_parts.append("**Active Goals**:")
                    prompt_parts.extend(
                        f"  - {goal.get('title', 'Untitled')}: {goal.get('description', '')[:100]}"
                        for goal in context["active_goals"]
                        if goal and isinstance(goal, dict)  # Defensive check
                    )
                    prompt_parts.append("")

                # Recent Topics (thematic continuity)
                self.logger.info("Processing recent_topics context section")
                if context.get("recent_topics"):
                    topics_str = ", ".join(context["recent_topics"][:10])
                    prompt_parts.append(f"**Recent Themes** (last 30 days): {topics_str}")
                    prompt_parts.append("")

                # Mood Trends
                self.logger.info("Processing mood_trends context section")
                if context.get("mood_trends"):
                    trends = context["mood_trends"]
                    if trends and isinstance(trends, dict):  # Defensive check
                        prompt_parts.append("**Recent Mood Patterns**:")
                        prompt_parts.append(
                            f"  - Average Energy: {trends.get('average_energy', 0)}/10"
                        )
                        prompt_parts.append(f"  - Trend: {trends.get('trend', 'stable')}")
                        if trends.get("recent_moods"):
                            prompt_parts.append(
                                f"  - Recent Moods: {', '.join(trends['recent_moods'][:3])}"
                            )
                        prompt_parts.append("")

                # Recent Journals (for continuity)
                self.logger.info("Processing recent_journals context section")
                if context.get("recent_journals"):
                    prompt_parts.append("**Recent Journal Themes** (last 7 days, for continuity):")
                    for j in context["recent_journals"][:5]:
                        if j and isinstance(j, dict):  # Defensive check
                            mood_info = (
                                f" (Mood: {j.get('mood', '')}, Energy: {j.get('energy_level', 0)}/10)"
                                if j.get("mood")
                                else ""
                            )
                            prompt_parts.append(
                                f"  - {j.get('title', 'Untitled')}: {j.get('content_excerpt', '')[:80]}{mood_info}"
                            )
                            if j.get("key_topics"):
                                topics = (
                                    ", ".join(j["key_topics"][:3])
                                    if isinstance(j["key_topics"], list)
                                    else ""
                                )
                                if topics:
                                    prompt_parts.append(f"    Topics: {topics}")
                    prompt_parts.append("")

                # Extraction guidance - with defensive None handling
                self.logger.info("Building extraction guidance")
                try:
                    recent_themes = (
                        ", ".join(context.get("recent_topics", [])[:5])
                        if context.get("recent_topics")
                        else "none"
                    )
                except Exception as e:
                    self.logger.error(
                        f"Error building recent_themes: {e}, context.get('recent_topics') = {context.get('recent_topics')}"
                    )
                    recent_themes = "none"

                try:
                    mood_trends_data = context.get("mood_trends") or {}
                    trend_text = (
                        mood_trends_data.get("trend", "stable")
                        if isinstance(mood_trends_data, dict)
                        else "stable"
                    )
                except Exception as e:
                    self.logger.error(
                        f"Error building trend_text: {e}, mood_trends_data = {mood_trends_data}"
                    )
                    trend_text = "stable"

                try:
                    active_goals_list = context.get("active_goals", []) or []
                    goal_titles = ", ".join(
                        [
                            g.get("title", "")
                            for g in active_goals_list[:3]
                            if g and isinstance(g, dict) and g.get("title")
                        ]
                    )
                except Exception as e:
                    self.logger.error(
                        f"Error building goal_titles: {e}, active_goals_list = {active_goals_list}"
                    )
                    goal_titles = "none"

                prompt_parts.extend(
                    [
                        "**Extract from this transcript**:",
                        f"1. **Key topics** (connecting to recent themes: {recent_themes})",
                        f"2. **Mood and energy level** (context: recent trend is {trend_text})",
                        "3. **Knowledge applications** (which concepts are being used/practiced?)",
                        f"4. **Goal progress** (which goals mentioned: {goal_titles if goal_titles else 'none'})",
                        "5. **Action items** (specific next steps mentioned)",
                        "6. **Connections to previous entries** (themes, emotions, topics)",
                        "",
                    ]
                )

            # Add raw transcript
            self.logger.info("Adding raw transcript to prompt")
            prompt_parts.extend(
                [
                    "## Raw Transcript",
                    "```",
                    raw_transcript,
                    "```",
                    "",
                    "## Task",
                    "Format this transcript according to instructions above, using context for intelligent editing.",
                    "",
                    "**Output Format: Return ONLY Markdown in this exact structure:**",
                    "",
                    "```markdown",
                    "# [Descriptive Title]",
                    "",
                    "**Summary**: [1-2 sentence summary of key points]",
                    "",
                    "## Journal Entry",
                    "",
                    "[Formatted journal content with proper markdown - use headings, lists, emphasis as appropriate]",
                    "",
                    "## Key Themes",
                    "- Theme 1",
                    "- Theme 2",
                    "- Theme 3",
                    "",
                    "## Action Items",
                    "- [ ] Action item 1",
                    "- [ ] Action item 2",
                    "```",
                    "",
                    "Do NOT wrap the output in code fences. Return the raw Markdown directly.",
                ]
            )

            result = "\n".join(prompt_parts)
            self.logger.info(f"Successfully built prompt: {len(result)} chars")
            return result

        except Exception as e:
            self.logger.error(f"CRITICAL ERROR in _build_editing_prompt: {e}", exc_info=True)
            self.logger.error(f"Context type: {type(context)}, context value: {context}")
            # Return minimal prompt on error
            return f"""
# Journal Transcript Editing Task

## Instructions
{instructions}

## Raw Transcript
```
{raw_transcript}
```

## Task
Format this transcript according to instructions above.

Return ONLY Markdown in this structure:
# [Title]
**Summary**: [Summary]
## Journal Entry
[Content]
## Key Themes
- Theme 1
## Action Items
- [ ] Action 1
"""

    def _parse_ai_response(self, ai_response: str) -> SubmissionAIInsights:
        """
        Parse AI response from Markdown format into structured format.

        Expected Markdown structure:
        # Title
        **Summary**: Summary text
        ## Journal Entry
        [content]
        ## Key Themes
        - Theme 1
        ## Action Items
        - [ ] Action 1
        """
        import re

        # Defensive check: handle None or empty response
        if not ai_response:
            self.logger.warning("AI response is None or empty")
            return SubmissionAIInsights(
                title="Journal Entry",
                formatted_content="",
                summary="AI response was empty",
                themes=[],
                action_items=[],
                edits_summary="AI response empty",
                context_summary=None,
            )

        # Strip code fences if present (in case AI wraps in ```markdown)
        content = ai_response.strip()
        if content.startswith("```markdown"):
            content = content[len("```markdown") :].strip()
        if content.startswith("```"):
            content = content[3:].strip()
        if content.endswith("```"):
            content = content[:-3].strip()

        try:
            # Extract title (first # heading)
            title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
            title = title_match.group(1).strip() if title_match else "Journal Entry"

            # Extract summary (**Summary**: text)
            summary_match = re.search(r"\*\*Summary\*\*:\s*(.+?)(?:\n|$)", content, re.IGNORECASE)
            summary = summary_match.group(1).strip() if summary_match else ""

            # Extract journal entry content (between ## Journal Entry and ## Key Themes)
            journal_match = re.search(
                r"##\s+Journal Entry\s*\n(.+?)(?=##\s+Key Themes|##\s+Action Items|$)",
                content,
                re.DOTALL | re.IGNORECASE,
            )
            formatted_content = journal_match.group(1).strip() if journal_match else content

            # Extract themes (bullet points under ## Key Themes)
            themes = []
            themes_section = re.search(
                r"##\s+Key Themes\s*\n(.+?)(?=##\s+Action Items|$)",
                content,
                re.DOTALL | re.IGNORECASE,
            )
            if themes_section:
                theme_lines = themes_section.group(1).strip().split("\n")
                themes = [
                    re.sub(r"^[-*]\s*", "", line.strip())
                    for line in theme_lines
                    if line.strip()
                    and (line.strip().startswith("-") or line.strip().startswith("*"))
                ]

            # Extract action items (checkbox items under ## Action Items)
            action_items = []
            actions_section = re.search(
                r"##\s+Action Items\s*\n(.+?)$", content, re.DOTALL | re.IGNORECASE
            )
            if actions_section:
                action_lines = actions_section.group(1).strip().split("\n")
                action_items = [
                    re.sub(r"^[-*]\s*\[\s*\]\s*", "", line.strip())
                    for line in action_lines
                    if line.strip() and ("[ ]" in line or "[x]" in line or "[X]" in line)
                ]

            self.logger.info(
                f"Parsed Markdown: title='{title[:50]}', themes={len(themes)}, actions={len(action_items)}"
            )

            return SubmissionAIInsights(
                title=title,
                formatted_content=formatted_content,
                summary=summary if summary else formatted_content[:200] + "...",
                themes=themes,
                action_items=action_items,
                edits_summary="AI editing applied successfully (Markdown)",
                context_summary="Context-aware editing completed",
            )

        except Exception as e:
            self.logger.error(f"Error parsing Markdown response: {e}", exc_info=True)
            # Fallback: treat entire response as formatted content
            return SubmissionAIInsights(
                title="Journal Entry",
                formatted_content=ai_response,
                summary=ai_response[:200] + "..." if len(ai_response) > 200 else ai_response,
                themes=[],
                action_items=[],
                edits_summary="AI editing applied (Markdown parse error)",
                context_summary=None,
            )

    # ========================================================================
    # BASIC CRUD (Minimal - for storing processed journals)
    # ========================================================================

    async def create(self, ku: Entity) -> Result[Entity]:
        """Create Entity and publish event."""
        result = await super().create(ku)

        if result.is_ok:
            from core.events.submission_events import SubmissionCreated

            ku_created = result.value
            event = SubmissionCreated(
                submission_uid=ku_created.uid,
                user_uid=ku_created.user_uid,
                ku_type=ku_created.ku_type.value,
                occurred_at=datetime.now(),
            )
            await publish_event(self.event_bus, event, self.logger)

        return result

    async def get(self, uid: str) -> Result[Entity]:
        """Get Entity by UID."""
        return await super().get(uid)

    async def update(self, uid: str, updates: BaseUpdatePayload | dict[str, Any]) -> Result[Entity]:
        """Update entity."""
        return await super().update(uid, updates)

    async def delete(self, uid: str, cascade: bool = False) -> Result[bool]:
        """Delete Entity and publish event."""
        # Get entity before deletion for event data
        ku_result = await self.get(uid)
        ku_user_uid = "unknown"

        if ku_result.is_ok:
            ku = ku_result.value
            from core.models.user_owned_entity import UserOwnedEntity

            ku_user_uid = ku.user_uid if isinstance(ku, UserOwnedEntity) else "unknown"

        result = await super().delete(uid, cascade=cascade)

        if result.is_ok:
            from core.events.submission_events import SubmissionDeleted

            event = SubmissionDeleted(
                submission_uid=uid,
                user_uid=ku_user_uid,
                ku_type="submission",
                occurred_at=datetime.now(),
            )
            await publish_event(self.event_bus, event, self.logger)

        return result

    async def list_kus(self, limit: int = 100, offset: int = 0) -> Result[list[Entity]]:
        """List entities with pagination."""
        result = await self.backend.list(
            limit=limit, offset=offset, sort_by="entry_date", sort_order="desc"
        )
        # backend.list() returns tuple[list, int], extract just the list
        if result.is_error:
            return Result.fail(result)
        reports, _total = result.value
        return Result.ok(reports)

    # ========================================================================
    # ESSENTIAL QUERY METHODS
    # ========================================================================

    async def process_raw_transcript(
        self,
        raw_transcript: str,
        user_uid: str,
        instructions_uid: str | None = None,
        store_result: bool = True,
    ) -> Result[Entity]:
        """
        Process raw transcript text into a formatted journal report.

        This is a convenience wrapper around process_transcript that also
        creates and stores the report entity.

        Args:
            raw_transcript: Raw text from transcription
            user_uid: User identifier (REQUIRED)
            instructions_uid: Optional instruction set UID
            store_result: Whether to store the result (default: True)

        Returns:
            Result containing the created Report entity
        """
        # Process transcript to get insights
        insights_result = await self.process_transcript(
            raw_transcript=raw_transcript,
            instructions_uid=instructions_uid,
            user_uid=user_uid,
        )

        if insights_result.is_error:
            return Result.fail(insights_result.expect_error())

        insights = insights_result.value

        from core.utils.uid_generator import UIDGenerator

        ku = Submission(
            uid=UIDGenerator.generate_uid("ku"),
            user_uid=user_uid,
            ku_type=EntityType.SUBMISSION,
            status=EntityStatus.PROCESSING,
            title=insights.title,
            content=insights.formatted_content,
            metadata={
                "summary": insights.summary,
                "content_type": "audio_transcript",
                "key_topics": insights.themes,
                "entry_date": date.today().isoformat(),
                "source_type": "transcript",
            },
        )

        if store_result:
            return await self.create(ku)

        return Result.ok(ku)

    async def search_journal_reports(
        self,
        query: str,
        user_uid: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Result[tuple[list[Entity], int]]:
        """
        Search journal-type reports by content text.

        Args:
            query: Search query string
            user_uid: Optional user filter
            limit: Max results
            offset: Pagination offset

        Returns:
            Tuple of (matching reports, total_count)
        """
        # Get journal-type reports
        filters: dict[str, Any] = {"ku_type": EntityType.SUBMISSION.value}
        if user_uid:
            filters["user_uid"] = user_uid

        result = await self.backend.find_by(**filters, limit=1000)

        if result.is_error:
            return Result.fail(result.expect_error())

        reports = result.value or []

        # Filter by query string (case-insensitive)
        query_lower = query.lower()

        def _get_summary(r: Entity) -> str:
            fn = getattr(r, "get_summary", None)
            return fn().lower() if fn else ""

        matching = [
            r
            for r in reports
            if query_lower in (r.title or "").lower()
            or query_lower in (r.content or "").lower()
            or query_lower in _get_summary(r)
        ]

        # Apply pagination
        total_count = len(matching)
        paginated = matching[offset : offset + limit]

        return Result.ok((paginated, total_count))

    async def create_report_from_transcription(
        self,
        transcription_result: dict[str, Any],
        user_uid: str,
        instructions_uid: str | None = None,
    ) -> Result[Entity]:
        """
        Create a journal report from a transcription result.

        This processes the transcription through the AI formatter
        and stores the resulting report.

        Args:
            transcription_result: Dict with 'text' or 'transcript' key
            user_uid: User identifier
            instructions_uid: Optional instruction set UID

        Returns:
            Result containing the created report
        """
        # Extract transcript text
        raw_transcript = transcription_result.get("text") or transcription_result.get(
            "transcript", ""
        )

        if not raw_transcript:
            return Result.fail(
                Errors.validation(
                    "Transcription result must contain 'text' or 'transcript' field",
                    field="transcription_result",
                )
            )

        return await self.process_raw_transcript(
            raw_transcript=raw_transcript,
            user_uid=user_uid,
            instructions_uid=instructions_uid,
            store_result=True,
        )
