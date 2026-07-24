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
from core.models.enums.entity_enums import EntityType
from core.models.query_types import QueryIntent
from core.models.relationship_names import RelationshipName
from core.models.type_hints import UserUID
from core.utils.decorators import with_error_handling
from core.utils.exception_types import DATA_CONVERSION_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.ku.ku import Ku
    from core.models.pathways.learning_path import LearningPath
    from core.models.pathways.path_step import PathStep
    from core.models.resource.resource import Resource
    from core.models.search_request import SearchRequest
    from core.ports.query_types import RichPathStepItem
    from core.services.ps_engagement.engagement import Engagement
    from core.services.user import UserContext


@runtime_checkable
class EntityLookup(Protocol):
    """Minimal protocol for services used in PS bundle loading.

    Only requires async get(uid) -> Result[Any]. All BaseService subclasses
    satisfy this via CrudOperationsMixin.
    """

    async def get(self, uid: str) -> Result[Any]: ...


@runtime_checkable
class KuLookup(Protocol):
    """Minimal protocol for the Ku facade in PS bundle loading.

    KuService exposes ``get_ku`` (not the BaseService ``get``), so it needs
    its own lookup slice — typing it as EntityLookup hid a crash behind the
    ``Any``-typed deps container until the first real KU fetch.
    """

    async def get_ku(self, uid: str) -> Result[Any]: ...


logger = get_logger(__name__)

_SENTINEL = object()


# Intent → preferred ContentChunk types. The chunker classifies passages into
# semantic types (DEFINITION, EXAMPLE, EXERCISE, ...) — different question
# intents are best answered by different passage types. An absent key means
# 'no filter' (search all chunk types).
#
# Unmapped on purpose:
#   AGGREGATION       — pure graph/count query; chunk text doesn't help.
#   SPECIFIC          — catch-all default; any chunk type may answer.
#   GOAL_ACHIEVEMENT  — domain query served from user activity data, not curriculum.
_INTENT_CHUNK_TYPES: dict[QueryIntent, list[str]] = {
    QueryIntent.PREREQUISITE: ["DEFINITION", "EXPLANATION"],
    QueryIntent.PRACTICE: ["EXERCISE", "EXAMPLE"],
    QueryIntent.HIERARCHICAL: ["DEFINITION", "EXPLANATION"],
    QueryIntent.EXPLORATORY: ["INTRODUCTION", "SUMMARY", "DEFINITION"],
    QueryIntent.RELATIONSHIP: ["EXPLANATION", "DEFINITION"],
}


def _intent_to_chunk_types(intent: QueryIntent) -> list[str] | None:
    """Pick the chunk types most likely to answer a given intent.

    Returning None means 'no filter' — used for catch-all (SPECIFIC),
    aggregate, or user-data queries where any chunk type is fair game.
    """
    return _INTENT_CHUNK_TYPES.get(intent)


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
    - Chunk (RAG) retrieval flows through SearchRouter.retrieve_scoped_chunks —
      the single path for external search access, so a facet scope narrows Ask's
      passages exactly as it narrows Find's cards.
    - Returns frozen dataclasses (LearningContext)

    March 2026: Both services required — no graceful degradation.
    March 2026: Absorbed LSContextLoader — all retrieval in one service.
    July 2026: Chunk retrieval routed through SearchRouter (PR2 — Scoped Ask).
    """

    def __init__(
        self,
        graph_intel: Any,  # boundary: GraphIntelligenceService protocol not yet extracted
        embeddings_service: Any,  # boundary: EmbeddingsService protocol not yet extracted
        # PS bundle dependencies — all required (fail-fast per SKUEL philosophy)
        ps_service: EntityLookup | None = None,
        ku_service: KuLookup | None = None,
        habits_service: EntityLookup | None = None,
        tasks_service: EntityLookup | None = None,
        events_service: EntityLookup | None = None,
        principles_service: EntityLookup | None = None,
        lp_service: EntityLookup | None = None,
        # Backends for graph queries (migrated from inline Cypher)
        ku_backend: Any | None = None,  # boundary: KuBackend
        ps_backend: Any | None = None,  # boundary: PsBackend
        # Engagement service — None falls back to legacy (unengaged) selection.
        # Always wired in production (FULL tier); optional only for unit-test
        # construction without a full engagement-service mock.
        ps_engagement_service: Any | None = None,  # boundary: PsEngagementService
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

        # SearchRouter — THE single path for external chunk (RAG) retrieval.
        # Post-wired in compose after the router is built (it is constructed
        # after Askesis in bootstrap), never a constructor param.
        self.search_router: Any = None  # boundary: SearchRouter — post-wired in compose

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

        # Engagement service for lifecycle-aware bundle loading (ADR-059)
        self.ps_engagement_service = ps_engagement_service

        logger.info("ContextRetriever initialized")

    # ========================================================================
    # PUBLIC API - CONTEXT RETRIEVAL
    # ========================================================================

    async def retrieve_relevant_context(  # skuel-lint: disable=SKUEL005 -- fail-soft context enrichment: Askesis composes best-effort context, degraded sections omitted
        self,
        user_context: UserContext,
        query: str,
        intent: QueryIntent,
        scope: SearchRequest | None = None,
    ) -> dict[str, Any]:
        """
        Retrieve relevant context using both graph queries AND semantic search.

        Graph-based retrieval (prerequisite chains, tasks, etc.)
        Semantic search enrichment (similar knowledge via embeddings)

        Args:
            user_context: Complete user context
            query: User's question
            intent: Detected query intent
            scope: Optional facet scope (e.g. a ``nous`` topic from the Askesis
                composer). When set, its facets scope the retrieved passages so
                the answer draws only from that topic's lesson bodies.

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

        # For navigation/browsing questions, include organizer context
        # (emergent MOCs — owned entities with ORGANIZES edges provide
        # non-linear navigation across knowledge)
        if user_context.active_moc_uids:
            context["moc_navigation"] = {
                "active_mocs": len(user_context.active_moc_uids),
                "recently_viewed": user_context.recently_viewed_moc_uids[:3],
            }

        # Always include immediate recommendations (at_risk_habits is rich-context only)
        at_risk = user_context.at_risk_habits_or_empty()
        if at_risk or user_context.overdue_task_uids:
            context["immediate_attention"] = {
                "at_risk_habits": len(at_risk),
                "overdue_tasks": len(user_context.overdue_task_uids),
            }

        # PHASE 2: Chunk-level semantic search via Neo4j native vector indexes.
        # We target :ContentChunk (not :Entity) so the LLM grounds answers in the
        # actual passage that matched, with the owning PathStep surfaced via the
        # chunk → content → entity join for citation.
        chunk_types = _intent_to_chunk_types(intent)
        relevant_chunks = await self._find_similar_chunks(
            query, user_context.user_uid, chunk_types=chunk_types, scope=scope
        )
        if relevant_chunks:
            context["relevant_chunks"] = relevant_chunks[:3]  # Top 3

        return context

    @with_error_handling("get_learning_context", error_type="system", uid_param="user_context")
    async def get_learning_context(  # skuel-lint: disable=SKUEL029 -- facade-delegated: askesis_service awaits via delegation
        self, user_context: UserContext, depth: int = 2
    ) -> Result[dict[str, Any]]:
        """
        Get user's complete learning context, served from UserContext.

        UserContext (built once via MEGA-QUERY) already carries every field this
        method previously re-queried via PsBackend. Serving from it eliminates
        one Cypher round-trip per Askesis turn.

        Returns the same dict shape as before so existing consumers
        (query_processor, analyze_knowledge_gaps) keep working without change.

        Args:
            user_context: Rich UserContext (entities_rich/knowledge_units_rich
                populated). Standard-depth contexts produce empty lists.
            depth: Graph traversal depth (kept for signature compatibility; the
                MEGA-QUERY upstream chose the depth).

        Returns:
            Result containing complete learning context
        """
        del depth  # honored upstream by the MEGA-QUERY; preserved for signature stability

        knowledge_units = [
            {"uid": uid, "title": item.get("ku", {}).get("title", ""), "mastery_level": level}
            for uids, level in (
                (user_context.mastered_knowledge_uids, 1.0),
                (user_context.in_progress_knowledge_uids, 0.5),
                (user_context.blocked_knowledge_uids, 0.0),
            )
            for uid in uids
            for item in (user_context.knowledge_units_rich.get(uid, {}),)
        ]

        learning_paths = [
            {"uid": item["path"].get("uid", ""), "title": item["path"].get("title", "")}
            for item in user_context.enrolled_paths_rich
            if "path" in item
        ]

        related_tasks = [
            {
                "uid": item["entity"].get("uid", ""),
                "title": item["entity"].get("title", ""),
                "status": item["entity"].get("status", ""),
            }
            for item in user_context.entities_rich.get("tasks", [])
            if "entity" in item
        ]

        related_goals = [
            {
                "uid": item["entity"].get("uid", ""),
                "title": item["entity"].get("title", ""),
                "status": item["entity"].get("status", ""),
            }
            for item in user_context.entities_rich.get("goals", [])
            if "entity" in item
        ]

        # Partition knowledge_units by mastery level for the by-status view.
        # Compare against the float we set above so this stays in lock-step
        # with the projection (no string status to drift).
        knowledge_by_status = {
            "mastered": [k for k in knowledge_units if k["mastery_level"] == 1.0],
            "in_progress": [k for k in knowledge_units if k["mastery_level"] == 0.5],
            "blocked": [k for k in knowledge_units if k["mastery_level"] == 0.0],
        }

        return Result.ok(
            {
                "user_uid": user_context.user_uid,
                "knowledge_units": knowledge_units,
                "learning_paths": learning_paths,
                "related_tasks": related_tasks,
                "related_goals": related_goals,
                "knowledge_by_status": knowledge_by_status,
                "graph_context": {},
            }
        )

    @with_error_handling("analyze_knowledge_gaps", error_type="system", uid_param="user_context")
    async def analyze_knowledge_gaps(self, user_context: UserContext) -> Result[dict[str, Any]]:
        """
        Analyze user's knowledge gaps and prerequisite chains.

        Identifies:
        - Blocked knowledge areas
        - Required prerequisites
        - Prerequisite chains (depth analysis)
        - Quick wins (knowledge ready to learn)
        - High-impact gaps (blocking many items)

        Args:
            user_context: Rich UserContext

        Returns:
            Result containing gap analysis with actionable insights
        """
        context_result = await self.get_learning_context(user_context, GraphDepth.DEFAULT)
        if context_result.is_error:
            return context_result

        context_data = context_result.value
        blocked_knowledge = context_data["knowledge_by_status"]["blocked"]
        knowledge_units = context_data["knowledge_units"]

        gap_analysis = await self._analyze_blocked_knowledge_prerequisites(
            blocked_knowledge, user_context.user_uid, knowledge_units
        )

        quick_wins, high_impact = self._identify_quick_wins_and_high_impact(gap_analysis)

        return Result.ok(
            {
                "user_uid": user_context.user_uid,
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
        4. Fetch full Ku objects composed by the PS (knowledge edges)
        5. Fetch full activity entities from graph_context UIDs, cited
           Resources, and Ku↔Ku lateral edges (with authored evidence)
        6. Assemble into frozen PsBundle

        Args:
            user_uid: User's unique identifier
            user_context: Rich UserContext (must be build_rich() output)

        Returns:
            Result[PsBundle] — the complete bundle, or not_found error
        """
        # Step 1: Find active PathStep from rich context (engagement-aware)
        ps_rich, engagement = await self._find_active_ps(user_uid, user_context)
        if ps_rich is None:
            return Result.fail(Errors.not_found("path_step", "no_active_ps"))

        step_data: dict[str, Any] = dict(ps_rich.get("step") or ps_rich.get("entity", {}))  # type: ignore[call-overload]
        graph_context: dict[str, Any] = dict(ps_rich.get("graph_context", {}))

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
        kus_coro = self._fetch_kus(graph_context)
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

        # Step 3b: Fetch Ring 2 context — Resources cited by bundle PathSteps/KUs
        # and real Ku↔Ku lateral edges touching the bundle's KUs. Done after
        # path_steps/kus resolve so we know which UIDs to traverse from.
        # The anchor PS leads the resource list — its own citations are the most
        # relevant resources in the bundle (first live data: Arc D, 2026-07-03).
        related_ps_uids = [a.uid for a in related_ps]
        ku_uids_list = [k.uid for k in kus]
        ring2_raw = await asyncio.gather(
            self._fetch_cited_resources([path_step.uid, *related_ps_uids, *ku_uids_list]),
            self._fetch_ku_lateral_edges(ku_uids_list),
            return_exceptions=True,
        )

        ring2_labels = ("resources", "lateral_edges")
        ring2_defaults: tuple[Any, ...] = ([], [])
        ring2_resolved: list[Any] = []
        for label, raw, default in zip(ring2_labels, ring2_raw, ring2_defaults, strict=True):
            if isinstance(raw, BaseException):
                logger.warning("PS bundle fetch failed for %s (user %s): %s", label, user_uid, raw)
                ring2_resolved.append(default)
            else:
                ring2_resolved.append(raw)
        resources, edges = ring2_resolved

        # Step 4: Collect learning objectives from related path steps
        learning_objectives: list[str] = []
        for ps in related_ps:
            if ps.learning_objectives:
                learning_objectives.extend(ps.learning_objectives)

        bundle = PsBundle(
            path_step=path_step,
            learning_path=learning_path,
            engagement=engagement,
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

    async def _find_active_ps(
        self, user_uid: UserUID, user_context: UserContext
    ) -> tuple[RichPathStepItem | None, Engagement | None]:
        """Find the active (non-mastered) PathStep, preferring engaged candidates.

        UserContext.active_path_steps_rich contains PathStep items with:
        - entity/step: Full PathStep properties
        - graph_context: {prerequisite_steps, practice_habits, practice_tasks,
                          knowledge_relationships, learning_path}

        Selection rule (ADR-059):
        1. Walk the non-mastered candidates in order.
        2. If `ps_engagement_service` is available, prefer the first whose
           ``ENGAGED_WITH`` edge has ``state == "engaged"``.
        3. Fall back to the first non-mastered candidate without an engagement
           (published-but-not-engaged) so Askesis still works pre-engagement.

        Returns:
            (ps_item, engagement) — engagement is None when the chosen PS has
            no active engagement edge.
        """
        candidates: list[tuple[RichPathStepItem, dict[str, Any]]] = []
        for ps_item in user_context.active_path_steps_rich:
            step_data: dict[str, Any] = dict(ps_item.get("step") or ps_item.get("entity", {}))  # type: ignore[call-overload]
            if not step_data:
                continue
            current_mastery = step_data.get("current_mastery", 0.0) or 0.0
            mastery_threshold = step_data.get("mastery_threshold", 0.7) or 0.7
            if current_mastery >= mastery_threshold:
                continue
            candidates.append((ps_item, step_data))

        if not candidates:
            return None, None

        # Legacy path (unit tests construct without engagement service)
        if self.ps_engagement_service is None:
            return candidates[0][0], None

        # Look up engagement for each candidate in parallel — single edge
        # lookup per candidate, indexed on (user_uid, ps_uid).
        results = await asyncio.gather(
            *[
                self.ps_engagement_service.find_active(user_uid, step_data["uid"])
                for _, step_data in candidates
            ],
            return_exceptions=True,
        )

        engaged_match: tuple[RichPathStepItem, Engagement] | None = None
        unengaged_match: RichPathStepItem | None = None
        for (ps_item, step_data), res in zip(candidates, results, strict=True):
            if isinstance(res, BaseException):
                logger.warning(
                    "Engagement lookup failed for ps=%s user=%s: %s",
                    step_data.get("uid"),
                    user_uid,
                    res,
                )
                continue
            engagement = res.value if not res.is_error else None
            if engagement is not None and engagement.state == "engaged":
                if engaged_match is None:
                    engaged_match = (ps_item, engagement)
            elif engagement is None and unengaged_match is None:
                unengaged_match = ps_item

        if engaged_match is not None:
            return engaged_match[0], engaged_match[1]
        return unengaged_match, None

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
        """Fetch full PathSteps related to this step's knowledge neighborhood.

        graph_context.knowledge_relationships (MEGA-QUERY ps_knowledge block)
        carries every knowledge-edge target with its entity_type; we take the
        path_step-typed entries. path_step.knowledge_uids entries are resolved
        via lookup — entity kind comes from the store, never from UID spelling
        (ADR-013 never-sniff rule).
        """
        if not self.ps_service:
            return []

        ps_uids: set[str] = set()
        if path_step.knowledge_uids:
            ps_uids.update(path_step.knowledge_uids)

        for kr in graph_context.get("knowledge_relationships", []):
            if (
                isinstance(kr, dict)
                and kr.get("uid")
                and kr.get("entity_type") == EntityType.PATH_STEP.value
            ):
                ps_uids.add(kr["uid"])

        results = await asyncio.gather(*(self.ps_service.get(uid) for uid in ps_uids))

        path_steps: list[PathStep] = []
        for uid, result in zip(ps_uids, results, strict=False):
            if result.is_ok and result.value:
                path_steps.append(result.value)
            else:
                logger.debug("Could not fetch path step %s for PS bundle", uid)

        return path_steps

    async def _fetch_kus(self, graph_context: dict[str, Any]) -> list[Ku]:
        """Fetch full Ku objects composed by the PS.

        Derived from the PS's COMPOSITION edges (USES_KU/TRAINS_KU/
        CONTAINS_KNOWLEDGE) via graph_context.knowledge_relationships, whose
        entries carry the target's entity_type and rel_type from the MEGA-QUERY
        ps_knowledge block. Prerequisite/enabled KU neighbors (REQUIRES_KNOWLEDGE/
        ENABLES_KNOWLEDGE) stay out of ``bundle.kus`` — they are neighborhood
        context, not this step's target knowledge. Entity kind comes from the
        graph label, never from UID prefix — both sanctioned KU UID forms
        (authored ``ku.{ns}.{slug}`` and generated ``ku_{slug}_{random}``)
        pass through here (ADR-013 never-sniff rule).
        """
        if not self.ku_service:
            return []

        composition_rel_types = {
            RelationshipName.USES_KU.value,
            RelationshipName.TRAINS_KU.value,
            RelationshipName.CONTAINS_KNOWLEDGE.value,
        }
        ku_uids: set[str] = {
            kr["uid"]
            for kr in graph_context.get("knowledge_relationships", [])
            if isinstance(kr, dict)
            and kr.get("uid")
            and kr.get("entity_type") == EntityType.KU.value
            and kr.get("rel_type") in composition_rel_types
        }

        results = await asyncio.gather(*(self.ku_service.get_ku(uid) for uid in ku_uids))

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

        uids = [
            uid
            for item in uid_dicts
            if isinstance(item, dict) and isinstance((uid := item.get("uid")), str) and uid
        ]
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

    async def _fetch_ku_lateral_edges(self, ku_uids: list[str]) -> list[dict[str, Any]]:
        """Fetch real Ku↔Ku lateral edges touching the bundle's KUs.

        These are authored curriculum connections (RELATED_TO, PREREQUISITE_FOR,
        COMPLEMENTARY_TO, ...) with the Edge-file ``evidence`` text — the
        material SURFACE_CONNECTION prompts surface. This replaced the former
        pseudo-edges derived from graph_context.knowledge_relationships, which
        carried no source, no relationship type, and no evidence (the step→KU
        composition list still drives ``_fetch_kus``/``_fetch_related_path_steps``).

        Backend: _KnowledgeContextMixin.get_ku_lateral_edges — either endpoint
        in ``ku_uids``; an authored connection can point INTO the bundle.

        Returns:
            Edge dicts with source_uid, source_title, target_uid, target_title,
            relationship_type, evidence ("" when the edge was authored without
            evidence). Same-fact duplicates (symmetric edges stored both ways,
            asymmetric inverse pairs) are collapsed, preferring the copy that
            carries evidence.
        """
        if not ku_uids or not self.ps_backend:
            return []

        result = await self.ps_backend.get_ku_lateral_edges(ku_uids)
        if result.is_error or not result.value:
            return []

        edges: list[dict[str, Any]] = []
        seen: dict[tuple[str, str, str], int] = {}
        for record in result.value:
            source_uid = record.get("source_uid")
            target_uid = record.get("target_uid")
            rel_type = record.get("relationship_type")
            if not source_uid or not target_uid or not rel_type:
                continue
            edge = {
                "source_uid": source_uid,
                "source_title": record.get("source_title") or "",
                "target_uid": target_uid,
                "target_title": record.get("target_title") or "",
                "relationship_type": rel_type,
                "evidence": record.get("evidence") or "",
            }
            key = self._lateral_edge_key(source_uid, target_uid, rel_type)
            if key in seen:
                if edge["evidence"] and not edges[seen[key]]["evidence"]:
                    edges[seen[key]] = edge
                continue
            seen[key] = len(edges)
            edges.append(edge)
        return edges

    @staticmethod
    def _lateral_edge_key(source_uid: str, target_uid: str, rel_type: str) -> tuple[str, str, str]:
        """Canonical dedupe key for a lateral edge.

        A symmetric edge stored in both directions, or an asymmetric pair
        stored as both the primary and its inverse (BLOCKS + BLOCKED_BY), is
        ONE fact — canonicalize on the unordered endpoint pair plus the
        lexicographically smaller of {type, inverse type}.
        """
        rel = RelationshipName.from_string(rel_type)
        inverse = rel.get_lateral_inverse() if rel else None
        canonical_rel = min(rel_type, inverse.value) if inverse else rel_type
        lo, hi = sorted((source_uid, target_uid))
        return (lo, hi, canonical_rel)

    # ========================================================================
    # PRIVATE - HELPER METHODS
    # ========================================================================

    async def _find_similar_chunks(
        self,
        query: str,
        _user_uid: UserUID,
        chunk_types: list[str] | None = None,
        scope: SearchRequest | None = None,
    ) -> list[dict[str, Any]]:
        """
        Find the most relevant :ContentChunk nodes for the user's question.

        Routes through SearchRouter.retrieve_scoped_chunks (the single path for
        external search access) so a facet ``scope`` narrows the passages to that
        topic — Ask and Find share one facet→scope path.

        Returns the chunk_uid, chunk_type, text, context_window (the 100-word
        pre/post buffer designed for LLM grounding), similarity score, and the
        owning entity's uid + title — so a downstream prompt can both quote the
        passage AND cite the PathStep it came from.

        Args:
            query: User's question
            _user_uid: User identifier (forwarded to the router; reserved for
                future owner-scoped chunk visibility).
            chunk_types: Optional filter (e.g. ["DEFINITION", "EXAMPLE"]) derived
                from the classified intent.
            scope: Optional facet scope; its facets (e.g. ``nous``) scope the
                :ContentChunk hits to the owning entities. When None, an
                unscoped SearchRequest is built from the query alone.

        Returns:
            List of dicts shaped like SemanticSearchChunkResult; empty on search error.
        """
        from core.models.search_request import SearchRequest

        request = (
            scope.model_copy(update={"query_text": query, "limit": 5})
            if scope is not None
            else SearchRequest(query_text=query, limit=5)
        )
        result = await self.search_router.retrieve_scoped_chunks(
            request,
            chunk_types=chunk_types,
            min_score=0.6,
            user_uid=_user_uid,
        )

        if result.is_error:
            logger.warning("Chunk semantic search failed: %s", result.expect_error())
            return []

        return [
            {
                "chunk_uid": hit.get("chunk_uid", ""),
                "chunk_type": hit.get("chunk_type", ""),
                "text": hit.get("text", ""),
                "context_window": hit.get("context_window") or hit.get("text", ""),
                "similarity": hit.get("similarity_score", 0.0),
                "parent_uid": hit.get("parent_uid", ""),
                "parent_title": hit.get("parent_title") or "Unknown",
            }
            for hit in result.value
            if hit.get("chunk_uid")
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
