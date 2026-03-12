"""
Entity Extractor - Entity Extraction from Natural Language
===========================================================

Focused service for extracting entities mentioned in natural language queries.

Responsibilities:
- Extract knowledge entities from queries (global, legacy pipeline)
- Extract activity entities from queries (global, legacy pipeline)
- Extract KU UIDs from LS bundle (scoped, Socratic pipeline)
- Fuzzy match entity titles against query text

This service is part of the refactored EnhancedAskesisService architecture:
- UserStateAnalyzer: Analyze current user state and patterns
- ActionRecommendationEngine: Generate personalized action recommendations
- QueryProcessor: Process and answer natural language queries
- EntityExtractor: Extract entities from natural language (THIS FILE)
- ContextRetriever: Retrieve domain-specific context
- EnhancedAskesisService: Facade coordinating all sub-services

Architecture:
- Requires domain services (knowledge, tasks, goals, habits, events) for entity lookup
- Uses fuzzy matching for flexible entity recognition

March 2026: All domain services required — no graceful degradation.
March 2026: Added extract_from_bundle() for LS-scoped Socratic pipeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.utils.logging import get_logger

if TYPE_CHECKING:
    from core.models.askesis.ls_bundle import LSBundle
    from core.ports import (
        ArticleOperations,
        EventsOperations,
        GoalsOperations,
        HabitsOperations,
        TasksOperations,
    )
    from core.services.user import UserContext

logger = get_logger(__name__)


class EntityExtractor:
    """
    Extract entities mentioned in natural language queries.

    This service handles entity extraction:
    - Extract entities from queries (knowledge, tasks, goals, habits, events)
    - Fuzzy match entity titles against query text
    - Link natural language references to Neo4j UIDs
    - Support for acronyms and partial word matching

    Architecture:
    - Requires domain services for entity lookup (injected)
    - Uses UserContext for entity UID lists
    - Fuzzy matching with multiple strategies
    """

    def __init__(
        self,
        knowledge_service: ArticleOperations,
        tasks_service: TasksOperations,
        goals_service: GoalsOperations,
        habits_service: HabitsOperations,
        events_service: EventsOperations,
    ) -> None:
        """
        Initialize entity extractor.

        Args:
            knowledge_service: ArticleOperations for knowledge entity lookup
            tasks_service: TasksOperations for task entity lookup
            goals_service: GoalsOperations for goal entity lookup
            habits_service: HabitsOperations for habit entity lookup
            events_service: EventsOperations for event entity lookup
        """
        self.knowledge_service: ArticleOperations = knowledge_service
        self.tasks_service: TasksOperations = tasks_service
        self.goals_service: GoalsOperations = goals_service
        self.habits_service: HabitsOperations = habits_service
        self.events_service: EventsOperations = events_service

        logger.info("EntityExtractor initialized")

    # ========================================================================
    # PUBLIC API - ENTITY EXTRACTION
    # ========================================================================

    async def extract_entities_from_query(
        self, query: str, user_context: UserContext
    ) -> dict[str, list[dict[str, str]]]:
        """
        Extract and link entities mentioned in query to Neo4j UIDs.

        Identifies specific entities (knowledge, tasks, goals, habits, events)
        that the user is asking about, enabling more targeted responses.

        Args:
            query: User's question
            user_context: Complete user context with entity UIDs

        Returns:
            Dict of entity types to list of matched entities with UIDs and titles

        Examples:
            "What do I need to learn before async programming?"
            → {"knowledge": [{"uid": "ku.async_programming", "title": "Async Programming"}]}

            "How's my REST API goal going?"
            → {"goals": [{"uid": "goal.rest_api", "title": "Build REST API"}]}

            "Should I work on the Python task?"
            → {"tasks": [{"uid": "task.python_project", "title": "Python Project"}]}
        """
        query_lower = query.lower()

        entities = {
            "knowledge": await self._extract_knowledge_entities(query_lower, user_context),
            "tasks": await self._extract_task_entities(query_lower, user_context),
            "goals": await self._extract_goal_entities(query_lower, user_context),
            "habits": await self._extract_habit_entities(query_lower, user_context),
            "events": await self._extract_event_entities(query_lower, user_context),
            "principles": [],
            "choices": [],
        }

        total_matches = sum(len(ent_list) for ent_list in entities.values())
        logger.info(f"Extracted {total_matches} entities from query: {query[:50]}")

        return entities

    # ========================================================================
    # SOCRATIC PIPELINE — BUNDLE-SCOPED EXTRACTION
    # ========================================================================

    def extract_from_bundle(self, question: str, ls_bundle: LSBundle) -> list[str]:
        """Extract KU UIDs from the bundle that the question references.

        Uses fuzzy matching against bundle KU titles and aliases. Returns
        only UIDs that are part of the LS bundle — no global search.

        This is the scoped equivalent of extract_entities_from_query() for
        the Socratic pipeline. It's synchronous because it doesn't need
        to fetch entities — the bundle already has them.

        Args:
            question: User's natural language question
            ls_bundle: Complete LS bundle with all entities

        Returns:
            List of KU UIDs from the bundle that match the question
        """
        question_lower = question.lower()
        matched_uids: list[str] = []

        for ku in ls_bundle.kus:
            if self._fuzzy_match(ku.title, question_lower):
                matched_uids.append(ku.uid)
                continue

            # Check KU aliases
            for alias in getattr(ku, "aliases", ()):
                if self._fuzzy_match(alias, question_lower):
                    matched_uids.append(ku.uid)
                    break

        # Also check Article titles — if a question references an Article,
        # match it to the KUs that Article teaches
        for article in ls_bundle.articles:
            if self._fuzzy_match(article.title, question_lower):
                # Find KUs linked to this Article
                for ku in ls_bundle.kus:
                    if ku.uid not in matched_uids:
                        # If the Article's semantic_links reference this KU
                        if ku.uid in (article.semantic_links or ()):
                            matched_uids.append(ku.uid)

        # If no specific KU matched but the question is clearly about the LS topic,
        # return all KUs in the bundle (the question is about the LS as a whole)
        if not matched_uids and ls_bundle.kus:
            ls_title = ls_bundle.learning_step.title or ""
            ls_intent = ls_bundle.learning_step.intent or ""
            if self._fuzzy_match(ls_title, question_lower) or self._fuzzy_match(
                ls_intent, question_lower
            ):
                matched_uids = [ku.uid for ku in ls_bundle.kus]

        return matched_uids

    # ========================================================================
    # PRIVATE - ENTITY TYPE EXTRACTION
    # ========================================================================

    async def _extract_knowledge_entities(
        self, query_lower: str, user_context: UserContext
    ) -> list[dict[str, str]]:
        """
        Extract knowledge units mentioned in query.

        Args:
            query_lower: Lowercase query string
            user_context: User's complete context

        Returns:
            List of dicts with 'uid' and 'title' keys for matched knowledge units
        """
        matched = []

        # Get all knowledge UIDs from context
        all_knowledge_uids = (
            user_context.mastered_knowledge_uids
            | user_context.in_progress_knowledge_uids
            | user_context.blocked_knowledge_uids
        )

        # Match against each knowledge unit
        for ku_uid in all_knowledge_uids:
            try:
                ku_result = await self.knowledge_service.get(ku_uid)
                if ku_result.is_ok and ku_result.value:
                    ku = ku_result.value
                    # Check if title appears in query (case-insensitive)
                    if self._fuzzy_match(ku.title, query_lower):
                        matched.append({"uid": ku_uid, "title": ku.title})
            except Exception:
                continue

        return matched

    async def _extract_task_entities(
        self, query_lower: str, user_context: UserContext
    ) -> list[dict[str, str]]:
        """
        Extract tasks mentioned in query.

        Process:
        1. Get all task UIDs from UserContext
        2. For each task, fetch full details
        3. Check if title appears in query (fuzzy matching)
        4. Return matched UIDs and titles

        Args:
            query_lower: Lowercase query string
            user_context: User's complete context

        Returns:
            List of dicts with 'uid' and 'title' keys for matched tasks
        """
        matched = []
        all_task_uids = user_context.active_task_uids

        for task_uid in all_task_uids:
            try:
                # Get task details
                result = await self.tasks_service.get(task_uid)
                if result.is_ok and result.value:
                    task = result.value
                    # Check if task title appears in query
                    if self._fuzzy_match(task.title, query_lower):
                        matched.append({"uid": task_uid, "title": task.title})
            except Exception:
                continue

        return matched

    async def _extract_goal_entities(
        self, query_lower: str, user_context: UserContext
    ) -> list[dict[str, str]]:
        """
        Extract goals mentioned in query.

        Process:
        1. Get all goal UIDs from UserContext
        2. For each goal, fetch full details
        3. Check if title appears in query (fuzzy matching)
        4. Return matched UIDs and titles

        Args:
            query_lower: Lowercase query string
            user_context: User's complete context

        Returns:
            List of dicts with 'uid' and 'title' keys for matched goals
        """
        matched = []
        all_goal_uids = user_context.active_goal_uids

        for goal_uid in all_goal_uids:
            try:
                # Get goal details
                result = await self.goals_service.get(goal_uid)
                if result.is_ok and result.value:
                    goal = result.value
                    # Check if goal title appears in query
                    if self._fuzzy_match(goal.title, query_lower):
                        matched.append({"uid": goal_uid, "title": goal.title})
            except Exception:
                continue

        return matched

    async def _extract_habit_entities(
        self, query_lower: str, user_context: UserContext
    ) -> list[dict[str, str]]:
        """
        Extract habits mentioned in query.

        Process:
        1. Get all habit UIDs from UserContext
        2. For each habit, fetch full details
        3. Check if title appears in query (fuzzy matching)
        4. Return matched UIDs and titles

        Args:
            query_lower: Lowercase query string
            user_context: User's complete context

        Returns:
            List of dicts with 'uid' and 'title' keys for matched habits
        """
        matched = []
        all_habit_uids = user_context.active_habit_uids

        for habit_uid in all_habit_uids:
            try:
                # Get habit details
                result = await self.habits_service.get(habit_uid)
                if result.is_ok and result.value:
                    habit = result.value
                    # Check if habit title appears in query
                    if self._fuzzy_match(habit.title, query_lower):
                        matched.append({"uid": habit_uid, "name": habit.title})
            except Exception:
                continue

        return matched

    async def _extract_event_entities(
        self, query_lower: str, user_context: UserContext
    ) -> list[dict[str, str]]:
        """
        Extract events mentioned in query.

        Process:
        1. Get all event UIDs from UserContext
        2. For each event, fetch full details
        3. Check if title appears in query (fuzzy matching)
        4. Return matched UIDs and titles

        Args:
            query_lower: Lowercase query string
            user_context: User's complete context

        Returns:
            List of dicts with 'uid' and 'title' keys for matched events
        """
        matched = []
        # Combine today + upcoming events, preserving order and removing duplicates
        seen = set()
        all_event_uids = []
        for uid in user_context.today_event_uids + user_context.upcoming_event_uids:
            if uid not in seen:
                seen.add(uid)
                all_event_uids.append(uid)

        for event_uid in all_event_uids:
            try:
                # Get event details
                result = await self.events_service.get(event_uid)
                if result.is_ok and result.value:
                    event = result.value
                    # Check if event title appears in query
                    if self._fuzzy_match(event.title, query_lower):
                        matched.append({"uid": event_uid, "title": event.title})
            except Exception:
                continue

        return matched

    # ========================================================================
    # PRIVATE - FUZZY MATCHING
    # ========================================================================

    def _fuzzy_match(self, entity_title: str, query_lower: str) -> bool:
        """
        Check if entity title appears in query using fuzzy matching.

        Strategies:
        1. Exact match (case-insensitive)
        2. Partial word match (e.g., "async" matches "async programming")
        3. Acronym match (e.g., "REST API" matches "rest")

        Args:
            entity_title: Title of entity (e.g., "Async Programming")
            query_lower: Lowercased query string

        Returns:
            True if entity likely mentioned in query
        """
        title_lower = entity_title.lower()

        # Strategy 1: Exact match
        if title_lower in query_lower:
            return True

        # Strategy 2: Partial word match (match significant words)
        # Split title into words and check if any significant word appears
        title_words = [w for w in title_lower.split() if len(w) > 3]  # Ignore short words
        for word in title_words:
            if word in query_lower:
                return True

        # Strategy 3: Acronym match (e.g., "REST" from "REST API")
        if len(title_words) > 1:
            acronym = "".join(w[0] for w in title_words)
            if acronym in query_lower:
                return True

        return False
