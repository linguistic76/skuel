"""
LS Context Loader - Load Complete Learning Step Bundle
=======================================================

Loads the LSBundle for the user's active Learning Step by combining:
1. UserContext.active_learning_steps_rich (from MEGA-QUERY) — LS + graph_context
2. Full Article content fetched via ArticleService (MEGA-QUERY only has UIDs/titles)
3. Full Ku objects fetched via KuService (from trains_ku_uids)

The loader does NOT query Neo4j directly — it builds on what UserContext already
provides and fills in full content where needed.

See: /docs/architecture/ASKESIS_SOCRATIC_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.askesis.ls_bundle import LSBundle
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.article.article import Article
    from core.models.ku.ku import Ku
    from core.models.pathways.learning_path import LearningPath
    from core.models.pathways.learning_step import LearningStep
    from core.services.user import UserContext

logger = get_logger(__name__)

_SENTINEL = object()


class LSContextLoader:
    """Load the complete LS bundle for Socratic tutoring.

    Dependencies:
        article_service: For fetching full Article content (content field)
        ku_service: For fetching full Ku objects from trains_ku_uids
        habits_service: For fetching full Habit objects from graph_context
        tasks_service: For fetching full Task objects from graph_context
        events_service: For fetching full Event objects from graph_context
        principles_service: For fetching full Principle objects from graph_context
        lp_service: For fetching full LearningPath from graph_context
    """

    def __init__(
        self,
        article_service: Any,
        ku_service: Any,
        habits_service: Any = None,
        tasks_service: Any = None,
        events_service: Any = None,
        principles_service: Any = None,
        lp_service: Any = None,
    ) -> None:
        self.article_service = article_service
        self.ku_service = ku_service
        self.habits_service = habits_service
        self.tasks_service = tasks_service
        self.events_service = events_service
        self.principles_service = principles_service
        self.lp_service = lp_service
        logger.info("LSContextLoader initialized")

    async def load_bundle(
        self, user_uid: str, user_context: UserContext
    ) -> Result[LSBundle]:
        """Load the complete LS bundle from UserContext + service lookups.

        Steps:
        1. Find the active LS from user_context.active_learning_steps_rich
        2. Extract graph_context (habits, tasks, knowledge UIDs)
        3. Fetch full Article content for primary + supporting knowledge UIDs
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
            return Result.fail(
                Errors.not_found("learning_step", "no_active_ls")
            )

        step_data = ls_rich.get("entity", ls_rich.get("step", {}))
        graph_context = ls_rich.get("graph_context", {})

        # Step 2: Build the LearningStep domain model
        learning_step = self._build_learning_step(step_data)
        if learning_step is None:
            return Result.fail(
                Errors.not_found("learning_step", "malformed_ls_data")
            )

        # Step 3: Fetch full entities in parallel-ready fashion
        # (Could use asyncio.gather, but sequential is simpler and sufficient
        # since this runs once per Socratic turn)
        articles = await self._fetch_articles(learning_step, graph_context)
        kus = await self._fetch_kus(learning_step)
        learning_path = await self._fetch_learning_path(graph_context)
        habits = await self._fetch_entities_by_uid(
            graph_context.get("practice_habits", []), self.habits_service
        )
        tasks = await self._fetch_entities_by_uid(
            graph_context.get("practice_tasks", []), self.tasks_service
        )
        events: list[Any] = []  # Event templates not yet in graph_context
        principles: list[Any] = []  # Principles not yet in graph_context

        # Step 4: Collect learning objectives from articles
        learning_objectives: list[str] = []
        for article in articles:
            if article.learning_objectives:
                learning_objectives.extend(article.learning_objectives)

        # Step 5: Collect edges between bundle entities
        edges = self._extract_edges(graph_context)

        bundle = LSBundle(
            learning_step=learning_step,
            learning_path=learning_path,
            articles=tuple(articles),
            kus=tuple(kus),
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
    # PRIVATE — Finding the active LS
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

    # ========================================================================
    # PRIVATE — Building domain models from raw data
    # ========================================================================

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

    async def _fetch_articles(
        self, learning_step: LearningStep, graph_context: dict[str, Any]
    ) -> list[Article]:
        """Fetch full Articles for primary + supporting knowledge UIDs.

        The LS has primary_knowledge_uids and supporting_knowledge_uids pointing
        to Articles. The graph_context also has knowledge_relationships with UIDs.
        We fetch full content so the Socratic engine can use it as curriculum context.
        """
        article_uids: set[str] = set()
        if learning_step.primary_knowledge_uids:
            article_uids.update(learning_step.primary_knowledge_uids)
        if learning_step.supporting_knowledge_uids:
            article_uids.update(learning_step.supporting_knowledge_uids)

        # Also check graph_context knowledge_relationships for additional UIDs
        for kr in graph_context.get("knowledge_relationships", []):
            if isinstance(kr, dict) and kr.get("uid"):
                article_uids.add(kr["uid"])

        articles: list[Article] = []
        for uid in article_uids:
            result = await self.article_service.get(uid)
            if result.is_ok and result.value:
                articles.append(result.value)
            else:
                logger.debug("Could not fetch article %s for LS bundle", uid)

        return articles

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
        for uid in (learning_step.semantic_links or ()):
            if uid.startswith("ku_"):
                ku_uids.add(uid)

        kus: list[Ku] = []
        for uid in ku_uids:
            result = await self.ku_service.get(uid)
            if result.is_ok and result.value:
                kus.append(result.value)
            else:
                logger.debug("Could not fetch KU %s for LS bundle", uid)

        return kus

    async def _fetch_learning_path(
        self, graph_context: dict[str, Any]
    ) -> LearningPath | None:
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
        service: Any,
    ) -> list[Any]:
        """Fetch full entities from a list of {uid, title, ...} dicts.

        Used for habits, tasks, events, principles from graph_context.
        """
        if not service or not uid_dicts:
            return []

        entities: list[Any] = []
        for item in uid_dicts:
            uid = item.get("uid") if isinstance(item, dict) else None
            if not uid:
                continue
            result = await service.get(uid)
            if result.is_ok and result.value:
                entities.append(result.value)

        return entities

    def _extract_edges(self, graph_context: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract semantic relationship edges from graph_context.

        The knowledge_relationships list contains UIDs of related entities.
        We convert these to edge dicts for the SocraticEngine to surface.
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
