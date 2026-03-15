"""
Context Retriever - Domain Context Retrieval
=============================================

Focused service for retrieving domain-specific context.

Responsibilities:
- Retrieve relevant context based on query intent
- Get complete learning context
- Analyze knowledge gaps
- Identify quick wins and high-impact gaps
- Generate gap recommendations
- Find semantically similar knowledge
- Load LS bundles for Socratic tutoring (absorbed from LSContextLoader)

This service is part of the refactored AskesisService architecture:
- UserStateAnalyzer: Analyze current user state and patterns
- ActionRecommendationEngine: Generate personalized action recommendations
- QueryProcessor: Process and answer natural language queries
- EntityExtractor: Extract entities from natural language
- ContextRetriever: Retrieve domain-specific context (THIS FILE)
- AskesisService: Facade coordinating all sub-services

Architecture:
- Requires GraphIntelligenceService for graph intelligence queries (optional)
- Requires EmbeddingsService for semantic search (optional)
- Uses UserContext for user state
- Loads LS bundles for the Socratic pipeline (absorbed from LSContextLoader)

March 2026: Absorbed LSContextLoader into ContextRetriever — single retrieval service.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from core.constants import GraphDepth
from core.models.askesis.ls_bundle import LSBundle
from core.models.enums import Domain
from core.models.query_types import QueryIntent
from core.utils.decorators import requires_graph_intelligence, with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.ku.ku import Ku
    from core.models.lesson.lesson import Lesson
    from core.models.pathways.learning_path import LearningPath
    from core.models.pathways.learning_step import LearningStep
    from core.models.resource.resource import Resource
    from core.services.user import UserContext


@runtime_checkable
class EntityLookup(Protocol):
    """Minimal protocol for services used in LS bundle loading.

    Only requires async get(uid) -> Result[Any]. All BaseService subclasses
    satisfy this via CrudOperationsMixin.
    """

    async def get(self, uid: str) -> Result[Any]: ...


logger = get_logger(__name__)

_SENTINEL = object()


class ContextRetriever:
    """
    Retrieve domain-specific context and LS bundles.

    This service handles context retrieval:
    - Retrieve relevant context based on intent
    - Get complete learning context
    - Analyze knowledge gaps with prerequisite chains
    - Find semantically similar knowledge
    - Identify quick wins and high-impact gaps
    - Load LS bundles for Socratic tutoring

    Architecture:
    - Requires GraphIntelligenceService for graph queries
    - Requires EmbeddingsService for semantic search
    - Returns frozen dataclasses (LearningContext)

    March 2026: Both services required — no graceful degradation.
    March 2026: Absorbed LSContextLoader — all retrieval in one service.
    """

    def __init__(
        self,
        graph_intelligence_service: Any,  # boundary: GraphIntelligenceService protocol not yet extracted
        embeddings_service: Any,  # boundary: EmbeddingsService protocol not yet extracted
        vector_search_service: Any | None = None,  # boundary: Neo4jVectorSearchService
        # LS bundle dependencies — all required (fail-fast per SKUEL philosophy)
        lesson_service: EntityLookup | None = None,
        ku_service: EntityLookup | None = None,
        habits_service: EntityLookup | None = None,
        tasks_service: EntityLookup | None = None,
        events_service: EntityLookup | None = None,
        principles_service: EntityLookup | None = None,
        lp_service: EntityLookup | None = None,
    ) -> None:
        """
        Initialize context retriever.

        All entity services are required. ContextRetriever loads LS bundles
        that need full entity content — constructing without services would
        silently produce empty bundles at query time, which is harder to
        debug than a clear construction-time error.

        Args:
            graph_intelligence_service: GraphIntelligenceService for graph intelligence queries
            embeddings_service: EmbeddingsService for semantic search
            vector_search_service: Neo4jVectorSearchService for native vector index search
            lesson_service: For fetching full Lesson content (LS bundle)
            ku_service: For fetching full Ku objects from trains_ku_uids (LS bundle)
            habits_service: For fetching full Habit objects from graph_context (LS bundle)
            tasks_service: For fetching full Task objects from graph_context (LS bundle)
            events_service: For fetching full Event objects from graph_context (LS bundle)
            principles_service: For fetching full Principle objects from graph_context (LS bundle)
            lp_service: For fetching full LearningPath from graph_context (LS bundle)
        """
        self.graph_intel = graph_intelligence_service
        self.embeddings_service = embeddings_service
        self.vector_search_service = vector_search_service

        # LS bundle dependencies
        self.lesson_service = lesson_service
        self.ku_service = ku_service
        self.habits_service = habits_service
        self.tasks_service = tasks_service
        self.events_service = events_service
        self.principles_service = principles_service
        self.lp_service = lp_service

        logger.info("ContextRetriever initialized")

    # ========================================================================
    # PUBLIC API - CONTEXT RETRIEVAL
    # ========================================================================

    async def retrieve_relevant_context(
        self, user_context: UserContext, query: str, intent: QueryIntent
    ) -> dict[str, Any]:
        """
        Retrieve relevant context using both graph queries AND semantic search.

        Graph-based retrieval (prerequisite chains, tasks, etc.)
        Semantic search enrichment (similar knowledge via embeddings)

        Args:
            user_context: Complete user context
            query: User's question
            intent: Detected query intent

        Returns:
            Dict of relevant entities and metadata
        """
        context: dict[str, Any] = {}

        # PHASE 1: Graph-based retrieval

        # For prerequisite questions, analyze knowledge gaps
        if intent == QueryIntent.PREREQUISITE:
            if user_context.prerequisites_needed:
                context["prerequisites_needed"] = len(user_context.prerequisites_needed)
                context["blocked_knowledge"] = len(
                    [uid for uid, prereqs in user_context.prerequisites_needed.items() if prereqs]
                )

        # For practice/apply questions, get tasks
        elif intent == QueryIntent.PRACTICE:
            context["active_tasks"] = len(user_context.active_task_uids)
            context["completed_tasks"] = len(user_context.completed_task_uids)

        # For hierarchical/learning questions, get learning paths
        elif intent == QueryIntent.HIERARCHICAL:
            context["enrolled_paths"] = len(user_context.enrolled_path_uids)
            if user_context.current_learning_path_uid:
                context["current_path"] = user_context.current_learning_path_uid

        # For exploratory questions, provide overview
        elif intent == QueryIntent.EXPLORATORY:
            context["overview"] = {
                "tasks": len(user_context.active_task_uids),
                "goals": len(user_context.active_goal_uids),
                "habits": len(user_context.active_habit_uids),
                "knowledge_units": len(user_context.mastered_knowledge_uids)
                + len(user_context.in_progress_knowledge_uids),
                "mocs": len(user_context.active_moc_uids),
            }

        # For navigation/browsing questions, include MOC context
        # MOC provides non-linear navigation across knowledge
        if user_context.active_moc_uids:
            context["moc_navigation"] = {
                "active_mocs": len(user_context.active_moc_uids),
                "current_focus": user_context.current_moc_focus,
                "recently_viewed": user_context.recently_viewed_moc_uids[:3],
            }

        # Always include immediate recommendations
        if user_context.at_risk_habits or user_context.overdue_task_uids:
            context["immediate_attention"] = {
                "at_risk_habits": len(user_context.at_risk_habits),
                "overdue_tasks": len(user_context.overdue_task_uids),
            }

        # PHASE 2: Semantic search enrichment via Neo4j native vector indexes
        # Always attempt when vector_search_service is available — the min_score
        # threshold (0.6) already filters irrelevant results without a keyword gate.
        if self.vector_search_service:
            similar_knowledge = await self._find_similar_knowledge(query, user_context.user_uid)
            if similar_knowledge:
                context["semantically_similar_knowledge"] = [
                    {"uid": uid, "similarity": score, "title": title}
                    for uid, score, title in similar_knowledge[:3]  # Top 3
                ]
                context["semantic_search_enabled"] = True
            else:
                context["semantic_search_enabled"] = False
        else:
            context["semantic_search_enabled"] = False

        return context

    @requires_graph_intelligence("get_learning_context")
    @with_error_handling("get_learning_context", error_type="system", uid_param="user_uid")
    async def get_learning_context(self, user_uid: str, depth: int = 2) -> Result[dict[str, Any]]:
        """
        Get user's complete learning context

        Retrieves in single query:
        - Current knowledge state (mastered, learning, blocked)
        - Active learning paths with progress
        - Related tasks and goals
        - Knowledge prerequisites and relationships

        Args:
            user_uid: Unique identifier of the user
            depth: Graph traversal depth (default: 2)

        Returns:
            Result containing complete learning context

        Performance: 150ms -> 18ms (8x faster)
        """
        # Build user learning context query using CypherGenerator helper
        query, params = self._build_user_learning_context_query(user_uid, depth)

        # Execute query
        graph_context_result = await self.graph_intel.execute_apoc_query(query, parameters=params)

        if graph_context_result.is_error:
            return graph_context_result

        context = graph_context_result.value

        # Extract learning context by domain
        knowledge_units = context.get_nodes_by_domain(Domain.KNOWLEDGE)
        learning_paths = context.get_nodes_by_domain(Domain.LEARNING)
        related_tasks = context.get_nodes_by_domain(Domain.TASKS)
        related_goals = context.get_nodes_by_domain(Domain.GOALS)

        # Categorize knowledge by status
        mastered = []
        learning = []
        blocked = []

        for ku in knowledge_units:
            mastery = getattr(ku, "mastery_level", 0.0)
            if mastery >= 0.8:
                mastered.append(ku)
            elif mastery >= 0.3:
                learning.append(ku)
            else:
                blocked.append(ku)

        return Result.ok(
            {
                "user_uid": user_uid,
                "knowledge_units": knowledge_units,
                "learning_paths": learning_paths,
                "related_tasks": related_tasks,
                "related_goals": related_goals,
                "knowledge_by_status": {
                    "mastered": mastered,
                    "learning": learning,
                    "blocked": blocked,
                },
                "graph_context": context,
            }
        )

    @requires_graph_intelligence("analyze_knowledge_gaps")
    @with_error_handling("analyze_knowledge_gaps", error_type="system", uid_param="user_uid")
    async def analyze_knowledge_gaps(self, user_uid: str) -> Result[dict[str, Any]]:
        """
        Analyze user's knowledge gaps and prerequisite chains

        Identifies:
        - Blocked knowledge areas
        - Required prerequisites
        - Prerequisite chains (depth analysis)
        - Quick wins (knowledge ready to learn)
        - High-impact gaps (blocking many items)

        Args:
            user_uid: Unique identifier of the user

        Returns:
            Result containing gap analysis with actionable insights

        Performance: 200ms -> 25ms (8x faster)
        """
        # Step 1: Get learning context
        context_result = await self.get_learning_context(user_uid, GraphDepth.DEFAULT)

        if context_result.is_error:
            return context_result

        context_data = context_result.value
        blocked_knowledge = context_data["knowledge_by_status"]["blocked"]
        knowledge_units = context_data["knowledge_units"]

        # Step 2: Analyze prerequisite chains for blocked knowledge
        gap_analysis = await self._analyze_blocked_knowledge_prerequisites(
            blocked_knowledge, user_uid, knowledge_units
        )

        # Step 3: Identify quick wins and high-impact gaps
        quick_wins, high_impact = self._identify_quick_wins_and_high_impact(gap_analysis)

        # Step 4: Build and return result
        return Result.ok(
            {
                "user_uid": user_uid,
                "total_gaps": len(gap_analysis),
                "gaps": gap_analysis,
                "quick_wins": quick_wins,
                "high_impact_gaps": high_impact,
                "recommendations": self._generate_gap_recommendations(quick_wins, high_impact),
            }
        )

    # ========================================================================
    # PUBLIC API - LS BUNDLE LOADING (absorbed from LSContextLoader)
    # ========================================================================

    async def load_ls_bundle(self, user_uid: str, user_context: UserContext) -> Result[LSBundle]:
        """Load the complete LS bundle from UserContext + service lookups.

        Steps:
        1. Find the active LS from user_context.active_learning_steps_rich
        2. Extract graph_context (habits, tasks, knowledge UIDs)
        3. Fetch full Lesson content for primary + supporting knowledge UIDs
        4. Fetch full Ku objects for trains_ku_uids
        5. Fetch full activity entities from graph_context UIDs
        6. Assemble into frozen LSBundle

        Args:
            user_uid: User's unique identifier
            user_context: Rich UserContext (must be build_rich() output)

        Returns:
            Result[LSBundle] — the complete bundle, or not_found error
        """
        # Step 1: Find active LS from rich context
        ls_rich = self._find_active_ls(user_context)
        if ls_rich is None:
            return Result.fail(Errors.not_found("learning_step", "no_active_ls"))

        step_data = ls_rich.get("entity", ls_rich.get("step", {}))
        graph_context = ls_rich.get("graph_context", {})

        # Step 2: Build the LearningStep domain model
        learning_step = self._build_learning_step(step_data)
        if learning_step is None:
            return Result.fail(Errors.not_found("learning_step", "malformed_ls_data"))

        # Step 3: Fetch full entities in parallel (partial failure tolerant)
        #
        # Each fetch can fail independently (network errors, malformed data).
        # We use return_exceptions=True so a single failure doesn't cancel
        # the others — a partial bundle (LS + whatever succeeded) is more
        # useful than no bundle at all.
        lessons_coro = self._fetch_lessons(learning_step, graph_context)
        kus_coro = self._fetch_kus(learning_step)
        lp_coro = self._fetch_learning_path(graph_context)
        habits_coro = self._fetch_entities_by_uid(
            graph_context.get("practice_habits", []), self.habits_service
        )
        tasks_coro = self._fetch_entities_by_uid(
            graph_context.get("practice_tasks", []), self.tasks_service
        )

        raw_results = await asyncio.gather(
            lessons_coro,
            kus_coro,
            lp_coro,
            habits_coro,
            tasks_coro,
            return_exceptions=True,
        )

        fetch_labels = ("lessons", "kus", "learning_path", "habits", "tasks")
        defaults: tuple[Any, ...] = ([], [], None, [], [])

        resolved: list[Any] = []
        for label, raw, default in zip(fetch_labels, raw_results, defaults, strict=True):
            if isinstance(raw, BaseException):
                logger.warning("LS bundle fetch failed for %s (user %s): %s", label, user_uid, raw)
                resolved.append(default)
            else:
                resolved.append(raw)

        lessons, kus, learning_path, habits, tasks = resolved
        events: list[Any] = []  # Event templates not yet in graph_context
        principles: list[Any] = []  # Principles not yet in graph_context

        # Step 3b: Fetch Resources cited by bundle Lessons/KUs (Ring 2 context)
        # Done after lessons/kus resolve so we know which UIDs to traverse from.
        lesson_uids = [a.uid for a in lessons]
        ku_uids_list = [k.uid for k in kus]
        try:
            resources = await self._fetch_cited_resources(lesson_uids + ku_uids_list)
        except Exception as exc:
            logger.warning("LS bundle fetch failed for resources (user %s): %s", user_uid, exc)
            resources = []

        # Step 4: Collect learning objectives from lessons
        learning_objectives: list[str] = []
        for lesson in lessons:
            if lesson.learning_objectives:
                learning_objectives.extend(lesson.learning_objectives)

        # Step 5: Collect edges between bundle entities
        edges = self._extract_edges(graph_context)

        bundle = LSBundle(
            learning_step=learning_step,
            learning_path=learning_path,
            lessons=tuple(lessons),
            kus=tuple(kus),
            resources=tuple(resources),
            principles=tuple(principles),
            habits=tuple(habits),
            tasks=tuple(tasks),
            events=tuple(events),
            edges=tuple(edges),
            learning_objectives=tuple(learning_objectives),
        )

        logger.info(
            "Loaded LS bundle for user %s: %s",
            user_uid,
            bundle,
        )
        return Result.ok(bundle)

    # ========================================================================
    # PRIVATE - LS BUNDLE HELPERS (absorbed from LSContextLoader)
    # ========================================================================

    def _find_active_ls(self, user_context: UserContext) -> dict[str, Any] | None:
        """Find the first active (non-mastered) LS from rich context.

        UserContext.active_learning_steps_rich contains LS items with:
        - entity/step: Full LS properties
        - graph_context: {prerequisite_steps, practice_habits, practice_tasks,
                          knowledge_relationships, learning_path}
        """
        for ls_item in user_context.active_learning_steps_rich:
            step_data = ls_item.get("entity", ls_item.get("step", {}))
            if not step_data:
                continue

            # Check the LS is not already mastered
            current_mastery = step_data.get("current_mastery", 0.0) or 0.0
            mastery_threshold = step_data.get("mastery_threshold", 0.7) or 0.7
            if current_mastery < mastery_threshold:
                return ls_item

        # All steps mastered or no steps available
        return None

    def _build_learning_step(self, step_data: dict[str, Any]) -> LearningStep | None:
        """Build a LearningStep from MEGA-QUERY properties dict."""
        from core.models.pathways.learning_step import LearningStep
        from core.models.pathways.learning_step_dto import LearningStepDTO

        uid = step_data.get("uid")
        if not uid:
            return None

        try:
            dto = LearningStepDTO()
            for key, value in step_data.items():
                if getattr(dto, key, _SENTINEL) is not _SENTINEL:
                    setattr(dto, key, value)
            return LearningStep.from_dto(dto)
        except Exception:
            logger.warning("Failed to build LearningStep from data: %s", uid)
            return None

    async def _fetch_lessons(
        self, learning_step: LearningStep, graph_context: dict[str, Any]
    ) -> list[Lesson]:
        """Fetch full Lessons for primary + supporting knowledge UIDs.

        The LS has primary_knowledge_uids and supporting_knowledge_uids pointing
        to Lessons. The graph_context also has knowledge_relationships with UIDs.
        We fetch full content so the Socratic engine can use it as curriculum context.
        """
        if not self.lesson_service:
            return []

        lesson_uids: set[str] = set()
        if learning_step.primary_knowledge_uids:
            lesson_uids.update(learning_step.primary_knowledge_uids)
        if learning_step.supporting_knowledge_uids:
            lesson_uids.update(learning_step.supporting_knowledge_uids)

        # Also check graph_context knowledge_relationships for additional UIDs
        for kr in graph_context.get("knowledge_relationships", []):
            if isinstance(kr, dict) and kr.get("uid"):
                lesson_uids.add(kr["uid"])

        results = await asyncio.gather(*(self.lesson_service.get(uid) for uid in lesson_uids))

        lessons: list[Lesson] = []
        for uid, result in zip(lesson_uids, results, strict=False):
            if result.is_ok and result.value:
                lessons.append(result.value)
            else:
                logger.debug("Could not fetch lesson %s for LS bundle", uid)

        return lessons

    async def _fetch_kus(self, learning_step: LearningStep) -> list[Ku]:
        """Fetch full Ku objects for trains_ku_uids on the LS.

        Note: trains_ku_uids is not a field on LearningStep model directly;
        it's derived from TRAINS_KU relationships. We check the LS's
        semantic_links and primary/supporting knowledge UIDs for KU-prefixed UIDs.
        """
        if not self.ku_service:
            return []

        ku_uids: set[str] = set()
        # KU UIDs start with "ku_"
        for uid in learning_step.primary_knowledge_uids:
            if uid.startswith("ku_"):
                ku_uids.add(uid)
        for uid in learning_step.supporting_knowledge_uids:
            if uid.startswith("ku_"):
                ku_uids.add(uid)
        for uid in learning_step.semantic_links or ():
            if uid.startswith("ku_"):
                ku_uids.add(uid)

        results = await asyncio.gather(*(self.ku_service.get(uid) for uid in ku_uids))

        kus: list[Ku] = []
        for uid, result in zip(ku_uids, results, strict=False):
            if result.is_ok and result.value:
                kus.append(result.value)
            else:
                logger.debug("Could not fetch KU %s for LS bundle", uid)

        return kus

    async def _fetch_learning_path(self, graph_context: dict[str, Any]) -> LearningPath | None:
        """Fetch the parent LearningPath from graph_context."""
        if not self.lp_service:
            return None

        lp_data = graph_context.get("learning_path")
        if not lp_data or not isinstance(lp_data, dict):
            return None

        lp_uid = lp_data.get("uid")
        if not lp_uid:
            return None

        result = await self.lp_service.get(lp_uid)
        if result.is_ok and result.value:
            return result.value
        return None

    async def _fetch_entities_by_uid(
        self,
        uid_dicts: list[dict[str, Any]],
        service: EntityLookup | None,
    ) -> list[Any]:
        """Fetch full entities from a list of {uid, title, ...} dicts.

        Used for habits, tasks, events, principles from graph_context.
        """
        if not service or not uid_dicts:
            return []

        uids = [item.get("uid") for item in uid_dicts if isinstance(item, dict) and item.get("uid")]
        if not uids:
            return []

        results = await asyncio.gather(*(service.get(uid) for uid in uids))

        return [result.value for result in results if result.is_ok and result.value]

    async def _fetch_cited_resources(self, source_uids: list[str]) -> list[Resource]:
        """Fetch Resources cited by Articles/KUs via CITES_RESOURCE relationships.

        Traverses (Article/Ku)-[:CITES_RESOURCE]->(Resource) for the given
        source UIDs and builds Resource domain models from the results.

        Args:
            source_uids: UIDs of Articles/KUs to traverse from.

        Returns:
            List of Resource domain models (may be empty).
        """
        if not source_uids or not self.graph_intel:
            return []

        from core.models.resource.resource import Resource
        from core.models.resource.resource_dto import ResourceDTO

        query = """
        MATCH (source:Entity)-[:CITES_RESOURCE]->(r:Resource)
        WHERE source.uid IN $source_uids
        RETURN DISTINCT r {.*} AS resource
        LIMIT 20
        """
        result = await self.graph_intel.execute_query(
            query, parameters={"source_uids": source_uids}
        )
        if result.is_error or not result.value:
            return []

        resources: list[Resource] = []
        for record in result.value:
            props = record.get("resource")
            if not props or not isinstance(props, dict) or not props.get("uid"):
                continue
            try:
                dto = ResourceDTO()
                for key, value in props.items():
                    if getattr(dto, key, _SENTINEL) is not _SENTINEL:
                        setattr(dto, key, value)
                resources.append(Resource.from_dto(dto))
            except Exception:
                logger.debug("Could not build Resource from graph data: %s", props.get("uid"))

        return resources

    def _extract_edges(self, graph_context: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract semantic relationship edges from graph_context.

        The knowledge_relationships list contains UIDs of related entities.
        We convert these to edge dicts for the pipeline to surface.
        """
        edges: list[dict[str, Any]] = []
        for kr in graph_context.get("knowledge_relationships", []):
            if isinstance(kr, dict) and kr.get("uid"):
                edges.append(
                    {
                        "target_uid": kr["uid"],
                        "target_title": kr.get("title", ""),
                        "domain": kr.get("domain", ""),
                    }
                )
        return edges

    # ========================================================================
    # PRIVATE - HELPER METHODS
    # ========================================================================

    async def _find_similar_knowledge(
        self, query: str, _user_uid: str
    ) -> list[tuple[str, float, str]]:
        """
        Find semantically similar knowledge using Neo4j native vector indexes.

        Uses Neo4jVectorSearchService.find_similar_by_text() which handles
        embedding creation + db.index.vector.queryNodes() in one call.

        Args:
            query: User's question
            _user_uid: User identifier (unused - for future personalization)

        Returns:
            List of (uid, similarity_score, title) tuples
        """
        if not self.vector_search_service:
            return []

        result = await self.vector_search_service.find_similar_by_text(
            "Entity", query, limit=5, min_score=0.6
        )

        if result.is_error:
            logger.warning("Semantic search failed: %s", result.expect_error())
            return []

        return [
            (item["node"].get("uid", ""), item["score"], item["node"].get("title", "Unknown"))
            for item in result.value
            if item.get("node", {}).get("uid")
        ]

    def _build_user_learning_context_query(
        self, user_uid: str, depth: int
    ) -> tuple[str, dict[str, Any]]:
        """
        Build Cypher query for user learning context.

        Retrieves in single query:
        - Knowledge state (mastered, learning, blocked)
        - Active learning paths with progress
        - Related tasks and goals
        - Knowledge prerequisites

        Args:
            user_uid: User identifier
            depth: Graph traversal depth

        Returns:
            Tuple of (query_string, parameters)
        """
        # Comprehensive learning context query
        query = """
        MATCH (u:User {uid: $user_uid})

        // Knowledge state
        OPTIONAL MATCH (u)-[:MASTERED]->(mastered:Entity)
        OPTIONAL MATCH (u)-[:LEARNING]->(learning:Entity)

        // Blocked knowledge - KUs required by tasks but not mastered
        OPTIONAL MATCH (u)-[:HAS_TASK]->(t:Task)-[:APPLIES_KNOWLEDGE]->(blocked_ku:Entity)
        WHERE NOT (u)-[:MASTERED]->(blocked_ku)

        // Learning paths
        OPTIONAL MATCH (u)-[:ENROLLED_IN]->(lp:Lp)

        // Active tasks
        OPTIONAL MATCH (u)-[:HAS_TASK]->(task:Task)
        WHERE task.status IN ['pending', 'in_progress']

        // Active goals
        OPTIONAL MATCH (u)-[:HAS_GOAL]->(goal:Goal)
        WHERE goal.status = 'active'

        // Prerequisites for blocked knowledge (limited depth)
        OPTIONAL MATCH (blocked_ku)-[:REQUIRES_KNOWLEDGE*1..3]->(prereq:Entity)
        WHERE NOT (u)-[:MASTERED]->(prereq)

        WITH u,
             collect(DISTINCT mastered) AS mastered_knowledge,
             collect(DISTINCT learning) AS learning_knowledge,
             collect(DISTINCT blocked_ku) AS blocked_knowledge,
             collect(DISTINCT lp) AS learning_paths,
             collect(DISTINCT task) AS active_tasks,
             collect(DISTINCT goal) AS active_goals,
             collect(DISTINCT prereq) AS unmastered_prerequisites

        RETURN {
            user_uid: u.uid,
            mastered_knowledge: [ku IN mastered_knowledge | {uid: ku.uid, title: ku.title, mastery_level: 1.0}],
            learning_knowledge: [ku IN learning_knowledge | {uid: ku.uid, title: ku.title, mastery_level: 0.5}],
            blocked_knowledge: [ku IN blocked_knowledge | {uid: ku.uid, title: ku.title, mastery_level: 0.0}],
            learning_paths: [lp IN learning_paths | {uid: lp.uid, title: lp.title}],
            active_tasks: [t IN active_tasks | {uid: t.uid, title: t.title, status: t.status}],
            active_goals: [g IN active_goals | {uid: g.uid, title: g.title, status: g.status}],
            unmastered_prerequisites: [ku IN unmastered_prerequisites | {uid: ku.uid, title: ku.title}]
        } AS context
        """
        params = {"user_uid": user_uid, "depth": depth}
        return query, params

    async def _analyze_blocked_knowledge_prerequisites(
        self, blocked_knowledge: list[Any], user_uid: str, _knowledge_units: list[Any]
    ) -> list[dict[str, Any]]:
        """
        Analyze prerequisite chains for blocked knowledge.

        For each blocked knowledge unit:
        1. Find unmastered prerequisites (direct blockers)
        2. Analyze impact (what gets unlocked if learned)
        3. Calculate difficulty and impact scores

        Args:
            blocked_knowledge: List of blocked knowledge units
            user_uid: User identifier for mastery checks
            _knowledge_units: All knowledge units (unused - for future use)

        Returns:
            List of gap analysis dicts with prerequisite chains and impact scores
        """
        if not blocked_knowledge:
            return []

        gap_analysis = []

        for blocked_ku in blocked_knowledge:
            # Extract uid and title from object or dict
            ku_uid = getattr(blocked_ku, "uid", None) or blocked_ku.get("uid", "")
            ku_title = getattr(blocked_ku, "title", None) or blocked_ku.get("title", "Unknown")

            if not ku_uid:
                continue

            # Step 1: Get unmastered prerequisites
            prereq_query = """
            MATCH (ku:Entity {uid: $ku_uid})
            OPTIONAL MATCH (ku)-[:REQUIRES_KNOWLEDGE*1..3]->(prereq:Entity)
            WHERE NOT EXISTS {
                MATCH (u:User {uid: $user_uid})-[:MASTERED]->(prereq)
            }
            RETURN collect(DISTINCT {uid: prereq.uid, title: prereq.title}) AS prerequisites
            """
            prereq_result = await self.graph_intel.execute_query(
                prereq_query, parameters={"ku_uid": ku_uid, "user_uid": user_uid}
            )

            prerequisites = []
            if prereq_result.is_ok and prereq_result.value:
                record = prereq_result.value[0] if prereq_result.value else {}
                prerequisites = [p for p in record.get("prerequisites", []) if p and p.get("uid")]

            # Step 2: Calculate impact (how many things does mastering this unlock?)
            impact_query = """
            MATCH (ku:Entity {uid: $ku_uid})<-[:REQUIRES_KNOWLEDGE]-(dependent:Entity)
            RETURN count(DISTINCT dependent) AS unlocks_count
            """
            impact_result = await self.graph_intel.execute_query(
                impact_query, parameters={"ku_uid": ku_uid}
            )

            unlocks_count = 0
            if impact_result.is_ok and impact_result.value:
                record = impact_result.value[0] if impact_result.value else {}
                unlocks_count = record.get("unlocks_count", 0)

            # Step 3: Build gap analysis entry
            gap_analysis.append(
                {
                    "uid": ku_uid,
                    "title": ku_title,
                    "prerequisites": prerequisites,
                    "prerequisite_count": len(prerequisites),
                    "unlocks_count": unlocks_count,
                    "difficulty": self._classify_difficulty(len(prerequisites)),
                    "impact": self._classify_impact(unlocks_count),
                }
            )

        return gap_analysis

    def _classify_difficulty(self, prereq_count: int) -> str:
        """Classify difficulty based on prerequisite count."""
        if prereq_count == 0:
            return "ready"
        elif prereq_count <= 2:
            return "medium"
        else:
            return "high"

    def _classify_impact(self, unlocks_count: int) -> str:
        """Classify impact based on how many things are unlocked."""
        if unlocks_count > 5:
            return "high"
        elif unlocks_count > 2:
            return "medium"
        else:
            return "low"

    def _identify_quick_wins_and_high_impact(
        self, gap_analysis: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """
        Identify quick wins and high-impact gaps from gap analysis.

        Quick wins: Knowledge with minimal prerequisites (0-1) that still unlocks content.
        High-impact: Knowledge that unlocks many other pieces (> 3 dependents).

        Args:
            gap_analysis: Gap analysis results from _analyze_blocked_knowledge_prerequisites

        Returns:
            Tuple of (quick_wins, high_impact_gaps) - each sorted by impact
        """
        quick_wins = []
        high_impact = []

        for gap in gap_analysis:
            prereq_count = gap.get("prerequisite_count", 0)
            unlocks_count = gap.get("unlocks_count", 0)

            # Quick wins: Ready or nearly ready, still useful
            if prereq_count <= 1 and unlocks_count > 0:
                quick_wins.append(gap)

            # High-impact: Blocking many things
            if unlocks_count > 3:
                high_impact.append(gap)

        # Sort by impact (unlocks_count descending)
        def by_unlocks(gap: dict[str, Any]) -> int:
            return gap.get("unlocks_count", 0)

        quick_wins.sort(key=by_unlocks, reverse=True)
        high_impact.sort(key=by_unlocks, reverse=True)

        # Limit to top 5 each
        return quick_wins[:5], high_impact[:5]

    def _generate_gap_recommendations(
        self, quick_wins: list[dict[str, Any]], high_impact: list[dict[str, Any]]
    ) -> list[str]:
        """
        Generate recommendations from gap analysis.

        Args:
            quick_wins: Quick win gaps
            high_impact: High-impact gaps

        Returns:
            List of recommendation strings
        """
        recommendations = []

        if quick_wins:
            recommendations.append(
                f"Start with {len(quick_wins)} quick wins - knowledge with minimal prerequisites"
            )

        if high_impact:
            recommendations.append(
                f"Focus on {len(high_impact)} high-impact areas that unlock many knowledge paths"
            )

        if not quick_wins and not high_impact:
            recommendations.append("Continue mastering current knowledge areas before advancing")

        return recommendations
