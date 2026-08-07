"""
Learning Alignment Bridge - Generic Learning Operations Pattern
================================================================

Eliminates duplication across learning services by providing generic
implementations for learning alignment READ operations.

**The Problem:**
All learning services (Goals, Habits, Events, Choices) had identical
implementations of learning alignment methods:
- get_learning_supporting_X() (~57 lines each)
- suggest_learning_aligned_X() (~72 lines each)
- assess_X_learning_alignment() (~55 lines each)

**The Solution:**
Single generic helper that handles the common pattern once.

**Deliberately absent: creation.** The bridge once carried
``create_with_learning_alignment`` (+ a batch variant), wired to dict-based
``backend.create_{domain}`` doors. Those doors resolve through
``UniversalNeo4jBackend.__getattr__`` to ``create(entity)`` — which expects a
DOMAIN MODEL — so every call persisted a corrupt uid-less node and then errored
on the read-back; no route ever reached the seven wrappers that called it, and
its create-time "alignment" was a log line. Deleted 2026-08-06. Creation
belongs to each domain's core primitive (``TasksCoreService.create_task`` et
al.), which publishes events, requests embeddings, and admission-guards link
edges — see /docs/roadmap/learning-aligned-create-verb.md for the create-verb
ideas this half carried and where to build them instead.
"""

from collections.abc import Awaitable, Callable
from operator import itemgetter
from typing import Any, TypeVar

from core.models.enums import Domain, Priority
from core.models.pathways.lp_position import LpPosition
from core.models.type_hints import EntityUID, UserUID
from core.services.base_service import BaseService
from core.utils.logging import get_logger
from core.utils.neo4j_props import coerce_int
from core.utils.result_simplified import Errors, Result

# Generic type variables
T = TypeVar("T")  # Domain model type (Goal, Habit, Event, Choice)
DTO = TypeVar("DTO")  # DTO type (GoalDTO, HabitDTO, etc.)
Request = TypeVar("Request")  # Request type (GoalCreateRequest, etc.)


class LearningAlignmentBridge[T, DTO, Request]:
    """
    Generic helper for learning alignment READ operations across all domains.

    Three shared operations, each replacing a near-identical copy in every
    learning service:

    - ``get_learning_supporting_entities`` — the user's entities, filtered and
      sorted by learning relevance against their LpPosition
    - ``suggest_learning_aligned_entities`` — suggestion dicts generated from
      the active learning paths (current step, path completion, outcomes)
    - ``assess_learning_alignment`` — a structured alignment assessment for
      one existing entity

    **Pattern (Goals, Habits, etc. all identical):**
    ```python
    async def assess_X_learning_alignment(self, x_uid, learning_position):
        return await self.learning_helper.assess_learning_alignment(
            entity_uid=x_uid, learning_position=learning_position
        )
    ```

    SKUEL Architecture:
    - Uses BaseService for DTO conversion
    - Leverages LpPosition for alignment assessment
    - Reads and assesses ONLY — creation goes through each domain's core
      primitive (see the module docstring for why the create half was deleted)
    """

    def __init__(
        self,
        service: BaseService,
        backend_get: Callable[[EntityUID], Awaitable[Result[Any]]],
        backend_get_user: Callable[[UserUID], Awaitable[Result[Any]]],
        domain: Domain,
        entity_name: str,  # "goal", "habit", "event", "choice"
        # Optional custom hooks for domain-specific logic
        alignment_scorer: Callable[[T, LpPosition], float] | None = None,
        suggestion_filter: Callable[[dict[str, Any], Any], bool] | None = None,
        embodiment_scorer: Callable[[T, LpPosition], dict[str, Any]] | None = None,
    ) -> None:
        """
        Initialize learning alignment helper with service-specific configuration.

        Args:
            service: The learning service (provides backend, BaseService helpers).
            backend_get: Backend method to fetch a single entity by UID.
            backend_get_user: Backend method to fetch all entities for a user.
            domain: Domain enum for categorization (e.g., Domain.GOALS).
            entity_name: Human-readable entity name for logging (e.g., "goal").
            alignment_scorer: Optional custom scorer for learning alignment.
            suggestion_filter: Optional filter for suggestions (applied to generated suggestions).
            embodiment_scorer: Optional scorer for embodiment data (merged into assessment).

        Note:
            dto_class and model_class are derived from service._config to avoid repetition
            at each call site.
        """
        self.service = service
        self.backend = service.backend
        self._backend_get = backend_get
        self._backend_get_user = backend_get_user

        # Derive dto_class and model_class from service config (fail-fast)
        dto_class = service.dto_class
        model_class = service.model_class
        if dto_class is None or model_class is None:
            raise ValueError(
                f"Service '{service.service_name}' must have dto_class and model_class "
                "in its _config to use LearningAlignmentBridge."
            )
        self.dto_class = dto_class
        self.model_class = model_class

        self.domain = domain
        self.entity_name = entity_name
        self.logger = get_logger(f"skuel.services.infrastructure.learning_helper.{entity_name}")

        # Custom hooks for domain-specific logic
        self._alignment_scorer = alignment_scorer
        self._suggestion_filter = suggestion_filter
        self._embodiment_scorer = embodiment_scorer

    async def get_learning_supporting_entities(
        self, user_uid: UserUID, learning_position: LpPosition
    ) -> Result[list[T]]:
        """
        Generic implementation of get_learning_supporting_X() pattern.

        Handles the complete learning support filtering flow:
        1. Get user's entities from backend
        2. Convert to domain models
        3. Calculate learning score for each entity
        4. Filter by minimum learning score threshold (0.3)
        5. Sort by learning relevance
        6. Return filtered list

        This single implementation replaces identical code in:
        - GoalsLearningService.get_learning_supporting_goals()
        - HabitsLearningService.get_learning_reinforcing_habits()

        Args:
            user_uid: User identifier,
            learning_position: User's learning path position

        Returns:
            Result containing list of entities that support learning progression,

        Example:
            ```python
            # In GoalsLearningService:
            async def get_learning_supporting_goals(self, user_uid, learning_position):
                return await self.learning_helper.get_learning_supporting_entities(
                    user_uid=user_uid, learning_position=learning_position
                )
            ```
        """
        self.logger.debug(f"Getting learning-supporting {self.entity_name}s for user {user_uid}")

        # Step 1: Get user's entities
        entities_result = await self._backend_get_user(user_uid)
        if entities_result.is_error:
            return entities_result

        # Step 2: Convert to domain models using BaseService helper
        entities = self.service._to_domain_models(
            entities_result.value, self.dto_class, self.model_class
        )

        # Step 3: Filter by learning alignment
        learning_supporting = []

        for entity in entities:
            learning_score = self.calculate_learning_score(entity, learning_position)

            # Include entities with meaningful learning support (threshold: 0.3)
            if learning_score > 0.3:
                learning_supporting.append(entity)

        # Step 4: Sort by learning relevance
        # Use knowledge count as primary sort key
        def _knowledge_count(entity: T) -> int:
            """Get linked knowledge count for sorting."""
            knowledge_uids = getattr(entity, "linked_knowledge_uids", None) or []
            return len(knowledge_uids)

        learning_supporting.sort(key=_knowledge_count, reverse=True)

        self.logger.info(
            f"Found {len(learning_supporting)} learning-supporting {self.entity_name}s "
            f"for user {user_uid} (from {len(entities)} total)"
        )

        return Result.ok(learning_supporting)

    async def suggest_learning_aligned_entities(  # skuel-lint: disable=SKUEL029 -- cross-domain bridge: awaited by suggest_learning_aligned_{tasks,goals,choices,habits} across 4 domains
        self,
        learning_position: LpPosition,
        filter_param: Any = None,
        max_suggestions: int = 8,
        custom_suggestions: list[dict[str, Any]] | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Generic implementation of suggest_learning_aligned_X() pattern.

        Handles the complete learning-aligned suggestion generation flow:
        1. Start with custom suggestions if provided
        2. Generate suggestions based on learning paths
        3. For each active path:
           - Suggest mastery-based entity for current step
           - Suggest path completion entity
           - Suggest outcome-based entities
        4. Apply custom filter if provided
        5. Sort by learning alignment score
        6. Return top N suggestions

        This single implementation replaces identical code in:
        - GoalsLearningService.suggest_learning_aligned_goals()
        - HabitsLearningService.suggest_learning_supporting_habits()

        Args:
            learning_position: User's learning path position,
            filter_param: Optional domain or category filter,
            max_suggestions: Maximum number of suggestions to return
            custom_suggestions: Optional domain-specific suggestions to inject

        Returns:
            Result containing list of suggestion dicts with learning alignment,

        Example:
            ```python
            # In GoalsLearningService:
            async def suggest_learning_aligned_goals(
                self, learning_position, goal_domain=None
            ):
                return await self.learning_helper.suggest_learning_aligned_entities(
                    learning_position=learning_position,
                    filter_param=goal_domain,
                    max_suggestions=8,
                )
            ```
        """
        self.logger.debug(f"Generating learning-aligned {self.entity_name} suggestions")

        # Start with custom suggestions if provided
        suggestions = custom_suggestions.copy() if custom_suggestions else []

        # Generate suggestions based on learning paths
        for path in learning_position.active_paths:
            # Skip if domain filter doesn't match
            if filter_param and isinstance(filter_param, Domain) and path.domain != filter_param:
                continue

            current_step = learning_position.current_steps.get(path.uid)
            if current_step:
                # Suggest mastery entity for current step
                # Use step title or first primary knowledge UID as description
                step_description = current_step.title
                if current_step.knowledge_uids:
                    step_knowledge = current_step.knowledge_uids[0]
                    step_description = step_knowledge

                mastery_suggestion = {
                    "title": f"Master {step_description}",
                    "name": f"Master {step_description}",  # For habits
                    "description": f"Achieve mastery in {step_description} from {path.title}",
                    "domain": path.domain,
                    "priority": Priority.HIGH,
                    "learning_alignment_score": 0.95,
                    "supporting_path": path.title,
                    "suggested_timeline": f"{coerce_int(current_step.estimated_hours)} hours",
                    "suggestion_reason": f"Current step in {path.title} learning path",
                }
                suggestions.append(mastery_suggestion)

            # Suggest path completion entity
            remaining_steps = len(
                [s for s in path.steps if s.uid not in learning_position.completed_step_uids]
            )
            if remaining_steps > 0:
                completion_suggestion = {
                    "title": f"Complete {path.title} Learning Path",
                    "name": f"Complete {path.title}",  # For habits
                    "description": f"Complete all {remaining_steps} remaining steps in {path.title}",
                    "domain": path.domain,
                    "priority": Priority.MEDIUM,
                    "learning_alignment_score": 0.9,
                    "supporting_path": path.title,
                    "suggested_timeline": f"{remaining_steps} weeks",
                    "suggestion_reason": f"Path completion with {remaining_steps} steps remaining",
                }
                suggestions.append(completion_suggestion)

            # Suggest outcome-based entities
            for outcome in path.outcomes[:2]:  # Limit to 2 outcomes per path
                outcome_suggestion = {
                    "title": f"Achieve: {outcome}",
                    "name": f"Practice: {outcome}",  # For habits
                    "description": f"Learning outcome from {path.title}: {outcome}",
                    "domain": path.domain,
                    "priority": Priority.MEDIUM,
                    "learning_alignment_score": 0.8,
                    "supporting_path": path.title,
                    "suggested_timeline": "1-2 months",
                    "suggestion_reason": f"Learning outcome from {path.title}",
                }
                suggestions.append(outcome_suggestion)

        # Apply custom filter if provided
        if self._suggestion_filter:
            suggestions = [s for s in suggestions if self._suggestion_filter(s, filter_param)]

        # Sort by learning alignment score
        suggestions.sort(key=itemgetter("learning_alignment_score"), reverse=True)

        self.logger.info(
            f"Generated {len(suggestions)} learning-aligned {self.entity_name} suggestions "
            f"from {len(learning_position.active_paths)} active paths"
        )

        return Result.ok(suggestions[:max_suggestions])

    async def assess_learning_alignment(
        self, entity_uid: EntityUID, learning_position: LpPosition
    ) -> Result[dict[str, Any]]:
        """
        Generic implementation of assess_X_learning_alignment() pattern.

        Handles the complete learning alignment assessment flow:
        1. Get entity from backend
        2. Convert to domain model
        3. Assess alignment via learning position
        4. Build structured assessment dict
        5. Generate recommendations based on alignment score
        6. Return assessment

        This single implementation replaces identical code in:
        - GoalsLearningService.assess_goal_learning_alignment()
        - HabitsLearningService.assess_habit_learning_impact()

        Args:
            entity_uid: Entity UID to assess,
            learning_position: User's learning path position

        Returns:
            Result containing learning alignment assessment dict,

        Example:
            ```python
            # In GoalsLearningService:
            async def assess_goal_learning_alignment(self, goal_uid, learning_position):
                return await self.learning_helper.assess_learning_alignment(
                    entity_uid=goal_uid, learning_position=learning_position
                )
            ```
        """
        self.logger.debug(f"Assessing learning alignment for {self.entity_name} {entity_uid}")

        # Step 1: Get the entity
        entity_result = await self._backend_get(entity_uid)
        if entity_result.is_error:
            return entity_result

        if not entity_result.value:
            return Result.fail(
                Errors.not_found(resource=self.model_class.__name__, identifier=entity_uid)
            )

        # Step 2: Convert to domain model
        entity = self.service._to_domain_model(
            entity_result.value, self.dto_class, self.model_class
        )

        # Step 3: Get entity details for assessment
        entity_title = getattr(entity, "title", "") or getattr(entity, "name", "")
        entity_desc = getattr(entity, "description", None) or entity_title
        entity_domain_value = str(getattr(entity, "domain", self.domain).value)

        # Step 4: Assess learning alignment
        try:
            alignment = learning_position.assess_goal_alignment(entity_desc, entity_domain_value)
        except (AttributeError, KeyError):  # fmt: skip
            # Fallback for entities without goal-style assessment
            alignment = {
                "learning_path_support": 0.0,
                "supporting_paths": [],
                "outcome_alignment": [],
                "recommended_timeline": "N/A",
                "prerequisite_steps": [],
            }

        # Step 5: Build assessment dict
        assessment = {
            f"{self.entity_name}_uid": entity_uid,
            f"{self.entity_name}_title": entity_title,
            "learning_path_support_score": alignment.get("learning_path_support", 0.0),
            "supporting_learning_paths": alignment.get("supporting_paths", []),
            "outcome_alignment": alignment.get("outcome_alignment", []),
            "recommended_timeline": alignment.get("recommended_timeline", "N/A"),
            "prerequisite_steps": alignment.get("prerequisite_steps", []),
            "learning_milestones": [],
            "knowledge_gaps": [],
            "recommendations": [],
        }

        # Step 6: Identify learning milestones
        for path in learning_position.active_paths:
            if path.uid in assessment["supporting_learning_paths"]:
                current_step = learning_position.current_steps.get(path.uid)
                if current_step:
                    # Use step title or first primary knowledge UID
                    step_description = current_step.title
                    if current_step.knowledge_uids:
                        step_description = current_step.knowledge_uids[0]

                    assessment["learning_milestones"].append(
                        {
                            "path": path.title,
                            "current_step": step_description,
                            "milestone": f"Complete {step_description} mastery",
                        }
                    )

        # Step 7: Generate recommendations
        support_score = assessment["learning_path_support_score"]
        if support_score > 0.7:
            assessment["recommendations"].append(
                f"{self.entity_name.capitalize()} is well-aligned with current learning - proceed with confidence"
            )
        elif support_score > 0.4:
            assessment["recommendations"].append(
                f"{self.entity_name.capitalize()} has moderate learning support - consider adding learning-specific milestones"
            )
        else:
            assessment["recommendations"].append(
                f"{self.entity_name.capitalize()} may benefit from stronger learning path integration"
            )

        if len(assessment["supporting_learning_paths"]) == 0:
            assessment["recommendations"].append(
                f"Consider connecting {self.entity_name} to active learning paths for better support"
            )

        # Step 8: Merge embodiment data if scorer provided
        if self._embodiment_scorer:
            embodiment_data = self._embodiment_scorer(entity, learning_position)
            assessment.update(embodiment_data)

        self.logger.info(
            f"Assessed learning alignment for {self.entity_name} {entity_uid}: "
            f"support={support_score:.2f}, paths={len(assessment['supporting_learning_paths'])}"
        )

        return Result.ok(assessment)

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    def calculate_learning_score(self, entity: T, learning_position: LpPosition) -> float:
        """
        Calculate learning alignment score for an entity.

        Uses custom scorer if provided, otherwise uses default scoring algorithm:
        - Domain alignment: +0.4 per matching path
        - Knowledge alignment: +0.5 per matching knowledge unit
        - Text alignment: +0.3 per path name match in entity text

        Args:
            entity: Domain model entity to score,
            learning_position: User's learning path position

        Returns:
            Float learning score (0.0 to infinity, typically 0.0-1.5)
        """
        # Use custom scorer if provided
        if self._alignment_scorer:
            return self._alignment_scorer(entity, learning_position)

        # Default scoring algorithm
        learning_score = 0.0

        # Get entity domain
        entity_domain = getattr(entity, "domain", None)
        if entity_domain:
            entity_domain_str = str(entity_domain.value)

            # Check domain alignment (0.4 weight)
            for path in learning_position.active_paths:
                path_domain = str(path.domain.value)
                if entity_domain_str == path_domain:
                    learning_score += 0.4
                    break  # Only count once per entity

        # Check knowledge alignment (0.5 weight)
        entity_knowledge = getattr(entity, "linked_knowledge_uids", None) or []
        if entity_knowledge:
            for path in learning_position.active_paths:
                current_step = learning_position.current_steps.get(path.uid)
                if current_step:
                    # Check if any of the step's knowledge UIDs match entity knowledge
                    step_knowledge = current_step.get_all_knowledge_uids()
                    if any(ku in entity_knowledge for ku in step_knowledge):
                        learning_score += 0.5
                        break  # Only count once per entity

        # Check text alignment (0.3 weight)
        entity_title = getattr(entity, "title", "") or getattr(entity, "name", "")
        entity_desc = getattr(entity, "description", "")
        entity_text = f"{entity_title} {entity_desc}".lower()

        for path in learning_position.active_paths:
            if path.title.lower() in entity_text:
                learning_score += 0.3
                break  # Only count once per entity

        return learning_score
