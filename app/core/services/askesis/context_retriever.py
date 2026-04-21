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
- Load PS bundles for Socratic tutoring (absorbed from LSContextLoader)

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
- Loads PS bundles for the Socratic pipeline

March 2026: Absorbed former LSContextLoader into ContextRetriever — single retrieval service.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from core.constants import GraphDepth
from core.models.askesis.ps_bundle import PsBundle
from core.models.query_types import QueryIntent
from core.models.type_hints import UserUID
from core.utils.decorators import with_error_handling
from core.utils.exception_types import DATA_CONVERSION_EXCEPTIONS, NEO4J_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.ku.ku import Ku
    from core.models.pathways.learning_path import LearningPath
    from core.models.pathways.path_step import PathStep
    from core.models.resource.resource import Resource
    from core.ports.query_types import RichPathStepItem
    from core.services.user import UserContext


@runtime_checkable
class EntityLookup(Protocol):
    """Minimal protocol for services used in PS bundle loading.

    Only requires async get(uid) -> Result[Any]. All BaseService subclasses
    satisfy this via CrudOperationsMixin.
    """

    async def get(self, uid: str) -> Result[Any]: ...


logger = get_logger(__name__)

_SENTINEL = object()


class ContextRetriever:
    """
    Retrieve domain-specific context and PS bundles.

    This service handles context retrieval:
    - Retrieve relevant context based on intent
    - Get complete learning context
    - Analyze knowledge gaps with prerequisite chains
    - Find semantically similar knowledge
    - Identify quick wins and high-impact gaps
    - Load PS bundles for Socratic tutoring

    Architecture:
    - Requires GraphIntelligenceService for graph queries
    - Requires EmbeddingsService for semantic search
    - Returns frozen dataclasses (LearningContext)

    March 2026: Both services required — no graceful degradation.
    March 2026: Absorbed LSContextLoader — all retrieval in one service.
    """

    def __init__(
        self,
        graph_intel: Any,  # boundary: GraphIntelligenceService protocol not yet extracted
        embeddings_service: Any,  # boundary: EmbeddingsService protocol not yet extracted
        vector_search_service: Any | None = None,  # boundary: Neo4jVectorSearchService
        # PS bundle dependencies — all required (fail-fast per SKUEL philosophy)
        ps_service: EntityLookup | None = None,
        ku_service: EntityLookup | None = None,
        habits_service: EntityLookup | None = None,
        tasks_service: EntityLookup | None = None,
        events_service: EntityLookup | None = None,
        principles_service: EntityLookup | None = None,
        lp_service: EntityLookup | None = None,
        # Backends for graph queries (migrated from inline Cypher)
        ku_backend: Any | None = None,  # boundary: KuBackend
        ps_backend: Any | None = None,  # boundary: PsBackend
    ) -> None:
        """
        Initialize context retriever.

        All entity services are required. ContextRetriever loads PS bundles
        that need full entity content — constructing without services would
        silently produce empty bundles at query time, which is harder to
        debug than a clear construction-time error.

        Args:
            graph_intel: GraphIntelligenceService for graph intelligence queries
            embeddings_service: EmbeddingsService for semantic search
            vector_search_service: Neo4jVectorSearchService for native vector index search
            ps_service: For fetching full PathStep content (PS bundle)
            ku_service: For fetching full Ku objects from trains_ku_uids (PS bundle)
            habits_service: For fetching full Habit objects from graph_context (PS bundle)
            tasks_service: For fetching full Task objects from graph_context (PS bundle)
            events_service: For fetching full Event objects from graph_context (PS bundle)
            principles_service: For fetching full Principle objects from graph_context (PS bundle)
            lp_service: For fetching full LearningPath from graph_context (PS bundle)
            ku_backend: KuBackend for prerequisite/dependency queries
            ps_backend: PsBackend for learning context and resource queries
        """
        self.graph_intel = graph_intel
        self.embeddings_service = embeddings_service
        self.vector_search_service = vector_search_service

        # PS bundle dependencies
        self.ps_service = ps_service
        self.ku_service = ku_service
        self.habits_service = habits_service
        self.tasks_service = tasks_service
        self.events_service = events_service
        self.principles_service = principles_service
        self.lp_service = lp_service

        # Backends for graph queries
        self.ku_backend = ku_backend
        self.ps_backend = ps_backend

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

        # Always include immediate recommendations (at_risk_habits is rich-context only)
        at_risk = (
            user_context.at_risk_habits
            if user_context.is_rich_context and user_context.at_risk_habits
            else []
        )
        if at_risk or user_context.overdue_task_uids:
            context["immediate_attention"] = {
                "at_risk_habits": len(at_risk),
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

    @with_error_handling("get_learning_context", error_type="system", uid_param="user_uid")
    async def get_learning_context(
        self, user_uid: UserUID, depth: int = 2
    ) -> Result[dict[str, Any]]:
        """
        Get user's complete learning context

        Retrieves in single query via PsBackend:
        - Current knowledge state (mastered, learning, blocked)
        - Active learning paths with progress
        - Related tasks and goals
        - Knowledge prerequisites and relationships

        Args:
            user_uid: Unique identifier of the user
            depth: Graph traversal depth (default: 2, unused — backend query uses fixed depth)

        Returns:
            Result containing complete learning context
        """
        if not self.ps_backend:
            return Result.fail(
                Errors.system(
                    message="PsBackend not available — learning context queries disabled",
                    operation="get_learning_context",
                )
            )

        result = await self.ps_backend.get_user_learning_context(user_uid)

        if result.is_error:
            return Result.fail(result)

        records = result.value or []
        if not records:
            return Result.ok(
                {
                    "user_uid": user_uid,
                    "knowledge_units": [],
                    "learning_paths": [],
                    "related_tasks": [],
                    "related_goals": [],
                    "knowledge_by_status": {"mastered": [], "learning": [], "blocked": []},
                    "graph_context": {},
                }
            )

        context = records[0].get("context", {})

        # Extract categorized knowledge (query pre-categorizes by mastery level)
        mastered = context.get("mastered_knowledge", [])
        learning_knowledge = context.get("learning_knowledge", [])
        blocked = context.get("blocked_knowledge", [])

        # Combine all knowledge units for the flat list
        knowledge_units = mastered + learning_knowledge + blocked

        return Result.ok(
            {
                "user_uid": user_uid,
                "knowledge_units": knowledge_units,
                "learning_paths": context.get("learning_paths", []),
                "related_tasks": context.get("active_tasks", []),
                "related_goals": context.get("active_goals", []),
                "knowledge_by_status": {
                    "mastered": mastered,
                    "learning": learning_knowledge,
                    "blocked": blocked,
                },
                "graph_context": context,
            }
        )

    @with_error_handling("analyze_knowledge_gaps", error_type="system", uid_param="user_uid")
    async def analyze_knowledge_gaps(self, user_uid: UserUID) -> Result[dict[str, Any]]:
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
    # PUBLIC API - PS BUNDLE LOADING
    # ========================================================================

    async def load_ps_bundle(
        self, user_uid: UserUID, user_context: UserContext
    ) -> Result[PsBundle]:
        """Load the complete PS bundle from UserContext + service lookups.

        Steps:
        1. Find the active PS from user_context.active_path_steps_rich
        2. Extract graph_context (habits, tasks, knowledge UIDs)
        3. Fetch full PathStep content for primary + supporting knowledge UIDs
        4. Fetch full Ku objects for trains_ku_uids
        5. Fetch full activity entities from graph_context UIDs
        6. Assemble into frozen PsBundle

        Args:
            user_uid: User's unique identifier
            user_context: Rich UserContext (must be build_rich() output)

        Returns:
            Result[PsBundle] — the complete bundle, or not_found error
        """
        # Step 1: Find active PathStep from rich context
        ps_rich = self._find_active_ps(user_context)
        if ps_rich is None:
            return Result.fail(Errors.not_found("path_step", "no_active_ps"))

        step_data: dict[str, Any] = dict(ps_rich.get("step") or ps_rich.get("entity", {}))  # type: ignore[call-overload]
        graph_context: dict[str, Any] = dict(ps_rich.get("graph_context", {}))  # type: ignore[call-overload]

        # Step 2: Build the PathStep domain model
        path_step = self._build_path_step(step_data)
        if path_step is None:
            return Result.fail(Errors.not_found("path_step", "malformed_ps_data"))

        # Step 3: Fetch full entities in parallel (partial failure tolerant)
        #
        # Each fetch can fail independently (network errors, malformed data).
        # We use return_exceptions=True so a single failure doesn't cancel
        # the others — a partial bundle (PS + whatever succeeded) is more
        # useful than no bundle at all.
        related_ps_coro = self._fetch_related_path_steps(path_step, graph_context)
        kus_coro = self._fetch_kus(path_step)
        lp_coro = self._fetch_learning_path(graph_context)
        habits_coro = self._fetch_entities_by_uid(
            graph_context.get("practice_habits", []), self.habits_service
        )
        tasks_coro = self._fetch_entities_by_uid(
            graph_context.get("practice_tasks", []), self.tasks_service
        )

        raw_results = await asyncio.gather(
            related_ps_coro,
            kus_coro,
            lp_coro,
            habits_coro,
            tasks_coro,
            return_exceptions=True,
        )

        fetch_labels = ("related_ps", "kus", "learning_path", "habits", "tasks")
        defaults: tuple[Any, ...] = ([], [], None, [], [])

        resolved: list[Any] = []
        for label, raw, default in zip(fetch_labels, raw_results, defaults, strict=True):
            if isinstance(raw, BaseException):
                logger.warning("PS bundle fetch failed for %s (user %s): %s", label, user_uid, raw)
                resolved.append(default)
            else:
                resolved.append(raw)

        related_ps, kus, learning_path, habits, tasks = resolved
        events: list[Any] = []  # Event templates not yet in graph_context
        principles: list[Any] = []  # Principles not yet in graph_context

        # Step 3b: Fetch Resources cited by bundle PathSteps/KUs (Ring 2 context)
        # Done after path_steps/kus resolve so we know which UIDs to traverse from.
        related_ps_uids = [a.uid for a in related_ps]
        ku_uids_list = [k.uid for k in kus]
        try:
            resources = await self._fetch_cited_resources(related_ps_uids + ku_uids_list)
        except NEO4J_EXCEPTIONS as exc:
            logger.warning("PS bundle fetch failed for resources (user %s): %s", user_uid, exc)
            resources = []
        except Exception as exc:  # safety-net: catch unexpected errors
            logger.warning(
                "PS bundle fetch failed for resources (user %s, %s): %s",
                user_uid,
                type(exc).__name__,
                exc,
            )
            resources = []

        # Step 4: Collect learning objectives from related path steps
        learning_objectives: list[str] = []
        for ps in related_ps:
            if ps.learning_objectives:
                learning_objectives.extend(ps.learning_objectives)

        # Step 5: Collect edges between bundle entities
        edges = self._extract_edges(graph_context)

        bundle = PsBundle(
            path_step=path_step,
            learning_path=learning_path,
            related_steps=tuple(related_ps),
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
            "Loaded PS bundle for user %s: %s",
            user_uid,
            bundle,
        )
        return Result.ok(bundle)

    # ========================================================================
    # PRIVATE - PS BUNDLE HELPERS
    # ========================================================================

    def _find_active_ps(self, user_context: UserContext) -> RichPathStepItem | None:
        """Find the first active (non-mastered) PathStep from rich context.

        UserContext.active_path_steps_rich contains PathStep items with:
        - entity/step: Full PathStep properties
        - graph_context: {prerequisite_steps, practice_habits, practice_tasks,
                          knowledge_relationships, learning_path}
        """
        for ps_item in user_context.active_path_steps_rich:
            step_data: dict[str, Any] = dict(ps_item.get("step") or ps_item.get("entity", {}))  # type: ignore[call-overload]
            if not step_data:
                continue

            # Check the PathStep is not already mastered
            current_mastery = step_data.get("current_mastery", 0.0) or 0.0
            mastery_threshold = step_data.get("mastery_threshold", 0.7) or 0.7
            if current_mastery < mastery_threshold:
                return ps_item

        # All steps mastered or no steps available
        return None

    def _build_path_step(self, step_data: dict[str, Any]) -> PathStep | None:
        """Build a PathStep from MEGA-QUERY properties dict."""
        from core.models.pathways.path_step import PathStep
        from core.models.pathways.path_step_dto import PathStepDTO

        uid = step_data.get("uid")
        if not uid:
            return None

        try:
            dto = PathStepDTO()
            for key, value in step_data.items():
                if getattr(dto, key, _SENTINEL) is not _SENTINEL:
                    setattr(dto, key, value)
            return PathStep.from_dto(dto)
        except DATA_CONVERSION_EXCEPTIONS:
            logger.warning("Failed to build PathStep from data: %s", uid)
            return None
        except Exception:  # safety-net: catch unexpected errors
            logger.warning("Failed to build PathStep from data (unexpected): %s", uid)
            return None

    async def _fetch_related_path_steps(
        self, path_step: PathStep, graph_context: dict[str, Any]
    ) -> list[PathStep]:
        """Fetch full PathSteps for knowledge UIDs.

        The PathStep has knowledge_uids pointing to PathSteps/KUs via CONTAINS_KNOWLEDGE.
        The graph_context also has knowledge_relationships with UIDs.
        We fetch full content so the Socratic engine can use it as curriculum context.
        """
        if not self.ps_service:
            return []

        ps_uids: set[str] = set()
        if path_step.knowledge_uids:
            ps_uids.update(path_step.knowledge_uids)

        # Also check graph_context knowledge_relationships for additional UIDs
        for kr in graph_context.get("knowledge_relationships", []):
            if isinstance(kr, dict) and kr.get("uid"):
                ps_uids.add(kr["uid"])

        results = await asyncio.gather(*(self.ps_service.get(uid) for uid in ps_uids))

        path_steps: list[PathStep] = []
        for uid, result in zip(ps_uids, results, strict=False):
            if result.is_ok and result.value:
                path_steps.append(result.value)
            else:
                logger.debug("Could not fetch path step %s for PS bundle", uid)

        return path_steps

    async def _fetch_kus(self, path_step: PathStep) -> list[Ku]:
        """Fetch full Ku objects for trains_ku_uids on the PS.

        Note: trains_ku_uids is not a field on PathStep model directly;
        it's derived from TRAINS_KU relationships. We check the PS's
        semantic_links and knowledge UIDs for KU-prefixed UIDs.
        """
        if not self.ku_service:
            return []

        ku_uids: set[str] = set()
        # KU UIDs start with "ku_"
        for uid in path_step.knowledge_uids:
            if uid.startswith("ku_"):
                ku_uids.add(uid)
        for uid in path_step.semantic_links or ():
            if uid.startswith("ku_"):
                ku_uids.add(uid)

        results = await asyncio.gather(*(self.ku_service.get(uid) for uid in ku_uids))

        kus: list[Ku] = []
        for uid, result in zip(ku_uids, results, strict=False):
            if result.is_ok and result.value:
                kus.append(result.value)
            else:
                logger.debug("Could not fetch KU %s for PS bundle", uid)

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
        """Fetch Resources cited by PathSteps/KUs via CITES_RESOURCE relationships.

        Traverses (PathStep/Ku)-[:CITES_RESOURCE]->(Resource) for the given
        source UIDs and builds Resource domain models from the results.

        Args:
            source_uids: UIDs of PathSteps/KUs to traverse from.

        Returns:
            List of Resource domain models (may be empty).
        """
        if not source_uids or not self.ps_backend:
            return []

        from core.models.resource.resource import Resource
        from core.models.resource.resource_dto import ResourceDTO

        result = await self.ps_backend.get_cited_resources(source_uids)
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
            except DATA_CONVERSION_EXCEPTIONS:
                logger.debug("Could not build Resource from graph data: %s", props.get("uid"))
            except Exception:  # safety-net: catch unexpected errors
                logger.debug(
                    "Could not build Resource from graph data (unexpected): %s", props.get("uid")
                )

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
        self, query: str, _user_uid: UserUID
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

    async def _analyze_blocked_knowledge_prerequisites(
        self, blocked_knowledge: list[Any], user_uid: UserUID, _knowledge_units: list[Any]
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
            ku_uid = getattr(blocked_ku, "uid", None) or (
                blocked_ku.get("uid", "") if isinstance(blocked_ku, dict) else ""
            )
            ku_title = getattr(blocked_ku, "title", None) or (
                blocked_ku.get("title", "Unknown") if isinstance(blocked_ku, dict) else "Unknown"
            )

            if not ku_uid:
                continue

            # Step 1: Get unmastered prerequisites (via KuBackend)
            prerequisites = []
            if self.ku_backend:
                prereq_result = await self.ku_backend.get_unmastered_prerequisites(ku_uid, user_uid)
                if prereq_result.is_ok and prereq_result.value:
                    record = prereq_result.value[0] if prereq_result.value else {}
                    prerequisites = [
                        p for p in record.get("prerequisites", []) if p and p.get("uid")
                    ]

            # Step 2: Calculate impact (via KuBackend)
            unlocks_count = 0
            if self.ku_backend:
                impact_result = await self.ku_backend.count_dependents(ku_uid)
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
