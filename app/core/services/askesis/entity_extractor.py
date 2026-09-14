"""
Entity Extractor - Entity Extraction from Natural Language
===========================================================

Focused service for extracting entities mentioned in natural language queries —
from the rich context, in memory. A question never reads the graph to find out
what it names.

Responsibilities:
- Extract knowledge and activity entities from a question (global pipeline)
- Extract KU UIDs from a PS bundle (scoped, Socratic pipeline)
- Fuzzy match entity titles against query text

This service is part of the refactored AskesisService architecture:
- UserStateAnalyzer: Analyze current user state and patterns
- ActionRecommendationEngine: Generate personalized action recommendations
- QueryProcessor: Process and answer natural language queries
- EntityExtractor: Extract entities from natural language (THIS FILE)
- ContextRetriever: Retrieve domain-specific context
- AskesisService: Facade coordinating all sub-services

Architecture:
- Matches against the titles ``RichUserContext`` already carries —
  ``entities_rich`` for the six activity domains, ``knowledge_units_rich`` for
  every MASTERED | IN_PROGRESS target — which the MEGA-QUERY fetched once and
  the context cache holds. Zero graph reads per question, whatever the learner's
  size; the pipeline's 30 s budget is spent on the answer, not on re-fetching
  titles one uid at a time.
- Uses fuzzy matching for flexible entity recognition
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable

    from core.models.askesis.ps_bundle import PsBundle
    from core.ports.query_types import RichEntityItem
    from core.services.user.unified_user_context import RichUserContext


logger = get_logger(__name__)


class EntityExtractor:
    """
    Extract entities mentioned in natural language queries.

    This service handles entity extraction:
    - Extract entities from queries (knowledge, tasks, goals, habits, events,
      principles, choices)
    - Fuzzy match entity titles against query text
    - Link natural language references to Neo4j UIDs
    - Support for acronyms and partial word matching

    Architecture:
    - Reads titles from the rich context it is handed; holds no service handles
    - Fuzzy matching with multiple strategies
    """

    # ========================================================================
    # PUBLIC API - ENTITY EXTRACTION
    # ========================================================================

    def extract_entities_from_query(
        self, query: str, user_context: RichUserContext
    ) -> dict[str, list[dict[str, str]]]:
        """
        Extract and link entities mentioned in query to Neo4j UIDs.

        Identifies specific entities (knowledge, tasks, goals, habits, events,
        principles, choices) that the user is asking about, enabling more
        targeted responses. Every candidate title is read from the context —
        ``entities_rich`` for the activity domains, ``knowledge_units_rich`` for
        knowledge — so this is pure computation over a context the pipeline has
        already built; the parameter is typed ``RichUserContext`` because a
        standard-depth context carries those fields empty.

        Each domain is scoped to the uids the standard context marks live:
        open tasks, active goals and habits, today's and upcoming events, the
        core principles, pending choices, and — for knowledge — everything the
        learner is engaged with (``known_or_engaged_ku_uids``: mastered and
        in-progress targets, a Ku or a PathStep alike). Every match carries the
        node's ``entity_type``, which is how a reader tells a Ku from a PathStep
        under the one "knowledge" key — by the label-derived field, never by the
        uid's spelling (ADR-013).

        Args:
            query: User's question
            user_context: The rich context the question is answered against

        Returns:
            Dict of entity types to list of matched entities, each
            ``{"uid", "title", "entity_type"}``

        Examples:
            "What do I need to learn before async programming?"
            → {"knowledge": [{"uid": "ku.async_programming", "title": "Async Programming",
                              "entity_type": "ku"}]}

            "How's my REST API goal going?"
            → {"goals": [{"uid": "goal.rest_api", "title": "Build REST API", "entity_type": "goal"}]}
        """
        query_lower = query.lower()
        rich = user_context.entities_rich
        event_uids = set(user_context.today_event_uids) | set(user_context.upcoming_event_uids)

        entities = {
            "knowledge": self._match_titles(
                query_lower,
                (
                    (uid, item.get("ku") or {})
                    for uid, item in user_context.knowledge_units_rich.items()
                ),
                user_context.known_or_engaged_ku_uids(),
            ),
            "tasks": self._match_activities(
                query_lower, rich.get("tasks", []), user_context.active_task_uids
            ),
            "goals": self._match_activities(
                query_lower, rich.get("goals", []), user_context.active_goal_uids
            ),
            "habits": self._match_activities(
                query_lower, rich.get("habits", []), user_context.active_habit_uids
            ),
            "events": self._match_activities(query_lower, rich.get("events", []), event_uids),
            "principles": self._match_activities(
                query_lower, rich.get("principles", []), user_context.core_principle_uids
            ),
            "choices": self._match_activities(
                query_lower, rich.get("choices", []), user_context.pending_choice_uids
            ),
        }

        total_matches = sum(len(ent_list) for ent_list in entities.values())
        logger.info(f"Extracted {total_matches} entities from query: {query[:50]}")

        return entities

    # ========================================================================
    # SOCRATIC PIPELINE — BUNDLE-SCOPED EXTRACTION
    # ========================================================================

    def extract_from_bundle(self, question: str, ps_bundle: PsBundle) -> list[str]:
        """Extract KU UIDs from the bundle that the question references.

        Uses fuzzy matching against bundle KU titles and aliases. Returns
        only UIDs that are part of the PS bundle — no global search.

        This is the scoped equivalent of extract_entities_from_query() for
        the Socratic pipeline: the bundle already holds the entities, as the
        rich context holds them for the global pipeline, so neither fetches.

        Args:
            question: User's natural language question
            ps_bundle: Complete PS bundle with all entities

        Returns:
            List of KU UIDs from the bundle that match the question
        """
        question_lower = question.lower()
        matched_uids: list[str] = []

        for ku in ps_bundle.kus:
            if self._fuzzy_match(ku.title, question_lower):
                matched_uids.append(ku.uid)
                continue

            # Check KU aliases
            for alias in getattr(ku, "aliases", ()):
                if self._fuzzy_match(alias, question_lower):
                    matched_uids.append(ku.uid)
                    break

        # Also check related PathStep titles — if a question references one,
        # match it to the KUs that PathStep teaches
        for related_step in ps_bundle.related_steps:
            if self._fuzzy_match(related_step.title, question_lower):
                # Find KUs linked to this PathStep
                for ku in ps_bundle.kus:
                    if ku.uid not in matched_uids:
                        # If the PathStep's semantic_links reference this KU
                        if ku.uid in (related_step.semantic_links or ()):
                            matched_uids.append(ku.uid)

        # If no specific KU matched but the question is clearly about the PS topic,
        # return all KUs in the bundle (the question is about the PS as a whole)
        if not matched_uids and ps_bundle.kus:
            ls_title = ps_bundle.path_step.title or ""
            ls_intent = ps_bundle.path_step.intent or ""
            if self._fuzzy_match(ls_title, question_lower) or self._fuzzy_match(
                ls_intent, question_lower
            ):
                matched_uids = [ku.uid for ku in ps_bundle.kus]

        return matched_uids

    # ========================================================================
    # PRIVATE - ENTITY MATCHING (IN MEMORY)
    # ========================================================================

    def _match_activities(
        self,
        query_lower: str,
        items: Iterable[RichEntityItem],
        scope: Collection[str],
    ) -> list[dict[str, str]]:
        """Match one activity domain's rich items, scoped to the uids the context marks live."""
        return self._match_titles(
            query_lower,
            ((str(entity.get("uid")), entity) for item in items if (entity := item.get("entity"))),
            scope,
        )

    def _match_titles(
        self,
        query_lower: str,
        # boundary: node properties exactly as the rich items carry them —
        # RichEntityItem.entity and RichKnowledgeUnitItem.ku are dict[str, Any]
        candidates: Iterable[tuple[str, dict[str, Any]]],
        scope: Collection[str],
    ) -> list[dict[str, str]]:
        """Return ``{"uid", "title", "entity_type"}`` for every in-scope node whose title fuzzy-matches.

        Args:
            query_lower: Lowercase query string
            candidates: ``(uid, node properties)`` pairs from the rich context
            scope: The uids eligible for matching (a domain's live set)
        """
        eligible = set(scope)
        matched: list[dict[str, str]] = []
        for uid, node in candidates:
            if uid not in eligible:
                continue
            title = node.get("title")
            if not isinstance(title, str) or not title:
                continue
            if self._fuzzy_match(title, query_lower):
                match = {"uid": uid, "title": title}
                entity_type = node.get("entity_type")
                if isinstance(entity_type, str) and entity_type:
                    match["entity_type"] = entity_type
                matched.append(match)
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
