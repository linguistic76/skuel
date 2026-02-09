"""
Learning Alignment Helper - Generic Learning Operations Pattern
================================================================

Eliminates duplication across learning services by providing generic
implementations for learning alignment operations.

**The Problem:**
All learning services (Goals, Habits, Events, Choices) had identical
implementations of learning alignment methods:
- create_X_with_learning_alignment() (~65 lines each)
- get_learning_supporting_X() (~57 lines each)
- suggest_learning_aligned_X() (~72 lines each)
- assess_X_learning_alignment() (~55 lines each)

Total duplication: ~723 LOC across 4 services

**The Solution:**
Single generic helper that handles the common pattern, reducing
each learning service's methods from ~267 LOC → ~12 LOC.

Version: 1.0.0
Date: October 16, 2025
Phase: 4
"""

from collections.abc import Callable
from operator import itemgetter
from typing import Any, TypeVar

from pydantic import BaseModel

from core.models.enums import Domain, Priority
from core.models.lp.lp_position import LpPosition
from core.services.base_service import BaseService
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

# Generic type variables
T = TypeVar("T")  # Domain model type (Goal, Habit, Event, Choice)
DTO = TypeVar("DTO")  # DTO type (GoalDTO, HabitDTO, etc.)
Request = TypeVar("Request")  # Request type (GoalCreateRequest, etc.)


class LearningAlignmentHelper[T, DTO, Request]:
    """
    Generic helper for learning alignment operations across all domains.

    This helper eliminates ~267 lines of duplicated code in each
    learning service's learning alignment methods.

    **Pattern Before (Goals, Habits, etc. all identical):**
    ```python
    async def create_X_with_learning_alignment(self, request, learning_position):
        # Create DTO from request (20 lines)
        dto = XDTO.create(...)
        dto.field1 = request.field1
        # ... 15 more fields

        # Create via backend (5 lines)
        result = await self.backend.create_X(dto.to_dict())
        if result.is_error:
            return result

        # Convert to domain model (5 lines)
        created_dto = XDTO.from_dict(result.value)
        entity = X.from_dto(created_dto)

        # Apply learning alignment (20 lines)
        if learning_position:
            alignment = learning_position.assess_X_alignment(...)
            self.logger.info(...)

        return Result.ok(entity)
    ```

    **Pattern After (Using Helper):**
    ```python
    async def create_X_with_learning_alignment(self, request, learning_position):
        return await self.learning_helper.create_with_learning_alignment(
            request=request, learning_position=learning_position
        )
    ```

    **65 lines → 3 lines (95% reduction)**

    SKUEL Architecture:
    - Uses BaseService for DTO conversion
    - Returns Result[T] for error handling
    - Logs operations with structured logging
    - Leverages LpPosition for alignment assessment
    """

    def __init__(
        self,
        service: BaseService,
        backend_get_method: str,
        backend_get_user_method: str,
        backend_create_method: str,
        dto_class: type[DTO],
        model_class: type[T],
        domain: Domain,
        entity_name: str,  # "goal", "habit", "event", "choice"
        # Optional custom hooks for domain-specific logic
        alignment_scorer: Callable[[T, LpPosition], float] | None = None,
        prerequisite_validator: Callable[[Request, Any], Result[None]] | None = None,
        suggestion_filter: Callable[[dict[str, Any], Any], bool] | None = None,
        embodiment_scorer: Callable[[T, LpPosition], dict[str, Any]] | None = None,
    ) -> None:
        """
        Initialize learning alignment helper with service-specific configuration.

        Args:
            service: The learning service (provides backend, BaseService helpers),
            backend_get_method: Name of backend method to get single entity (e.g., "get_goal"),
            backend_get_user_method: Name of backend method to get user's entities (e.g., "get_user_goals"),
            backend_create_method: Name of backend method to create entity (e.g., "create_goal"),
            dto_class: DTO class for conversion (e.g., GoalDTO),
            model_class: Domain model class (e.g., Goal),
            domain: Domain enum for categorization (e.g., Domain.GOALS),
            entity_name: Human-readable entity name for logging
            alignment_scorer: Optional custom scorer for learning alignment (replaces calculate_learning_score)
            prerequisite_validator: Optional validator for prerequisites (called before creation)
            suggestion_filter: Optional filter for suggestions (applied to generated suggestions)
            embodiment_scorer: Optional scorer for embodiment data (merged into assessment)
        """
        self.service = service
        self.backend = service.backend
        self.backend_get_method = backend_get_method
        self.backend_get_user_method = backend_get_user_method
        self.backend_create_method = backend_create_method
        self.dto_class = dto_class
        self.model_class = model_class
        self.domain = domain
        self.entity_name = entity_name
        self.logger = get_logger(f"skuel.services.infrastructure.learning_helper.{entity_name}")

        # Custom hooks for domain-specific logic
        self._alignment_scorer = alignment_scorer
        self._prerequisite_validator = prerequisite_validator
        self._suggestion_filter = suggestion_filter
        self._embodiment_scorer = embodiment_scorer

    async def create_with_learning_alignment(
        self,
        request: Request,
        learning_position: LpPosition | None = None,
        context: Any = None,
        custom_fields: dict[str, Any] | None = None,
    ) -> Result[T]:
        """
        Generic implementation of create_X_with_learning_alignment() pattern.

        Handles the complete learning-aligned entity creation flow:
        1. Validate prerequisites (if custom validator provided)
        2. Create DTO from request
        3. Merge custom fields (if provided)
        4. Create entity via backend
        5. Convert to domain model
        6. Apply learning position alignment if provided
        7. Return domain model

        This single implementation replaces identical code in:
        - GoalsLearningService.create_goal_with_learning_integration()
        - HabitsLearningService.create_habit_with_learning_alignment()

        Args:
            request: Entity creation request (GoalCreateRequest, HabitCreateRequest, etc.),
            learning_position: Optional user's learning path position
            context: Additional context for custom validators (e.g., UserContext for Tasks)
            custom_fields: Optional domain-specific fields to merge into request dict

        Returns:
            Result containing created domain model with learning alignment,

        Example:
            ```python
            # In GoalsLearningService.__init__:
            self.learning_helper = LearningAlignmentHelper[
                Goal, GoalDTO, GoalCreateRequest
            ](
                service=self,
                backend_get_method="get_goal",
                backend_get_user_method="get_user_goals",
                backend_create_method="create_goal",
                dto_class=GoalDTO,
                model_class=Goal,
                domain=Domain.GOALS,
                entity_name="goal",
            )

            # In create_goal_with_learning_integration():
            return await self.learning_helper.create_with_learning_alignment(
                request=goal_request, learning_position=learning_position
            )
            ```
        """
        self.logger.debug(f"Creating {self.entity_name} with learning alignment")

        # Step 0: Call prerequisite validator if provided (sync function)
        if self._prerequisite_validator:
            validation_result = self._prerequisite_validator(request, context)
            if validation_result.is_error:
                return Result.fail(validation_result.expect_error())

        # Step 1: Create entity via backend (delegate to service's existing creation logic)
        # NOTE: We rely on the service to have a standard create method that accepts the request
        # For now, services will need to handle DTO creation internally or we extract that too
        create_method = getattr(self.backend, self.backend_create_method, None)
        if not create_method:
            return Result.fail(
                Errors.system(
                    message=f"Backend method '{self.backend_create_method}' not found",
                    operation="create_with_learning_alignment",
                )
            )

        # Convert request to dict for backend
        # Pydantic models have model_dump(), fallback to __dict__ for other types
        request_dict = request.model_dump() if isinstance(request, BaseModel) else request.__dict__

        # Merge custom fields if provided
        if custom_fields:
            request_dict.update(custom_fields)

        create_result = await create_method(request_dict)
        if create_result.is_error:
            return create_result

        # Step 2: Convert to domain model using BaseService helper
        entity = self.service._to_domain_model(
            create_result.value, self.dto_class, self.model_class
        )

        # Step 3: Apply learning position alignment if provided
        if learning_position:
            # Get entity description for alignment assessment
            entity_desc = (
                getattr(entity, "description", None)
                or getattr(entity, "title", "")
                or getattr(entity, "name", "")
            )
            entity_title = getattr(entity, "title", "") or getattr(entity, "name", "")

            # Assess alignment using appropriate learning position method
            try:
                # Try goal-style assessment
                alignment = learning_position.assess_goal_alignment(
                    entity_desc, str(getattr(entity, "domain", self.domain).value)
                )

                self.logger.info(
                    f"{self.entity_name.capitalize()} '{entity_title}' created with learning integration: "
                    f"support={alignment.get('learning_path_support', 0.0):.2f}, "
                    f"timeline={alignment.get('recommended_timeline', 'N/A')}, "
                    f"paths={len(alignment.get('supporting_paths', []))}"
                )
            except (AttributeError, KeyError):
                # Fallback to habit-style suggestions
                try:
                    alignment_suggestions = learning_position.suggest_habit_alignment(entity_desc)
                    self.logger.info(
                        f"{self.entity_name.capitalize()} '{entity_title}' created with learning alignment: "
                        f"{len(alignment_suggestions)} suggestions from {len(learning_position.active_paths)} paths"
                    )
                except Exception as e:
                    self.logger.warning(f"Could not assess learning alignment: {e}")

        return Result.ok(entity)

    async def create_batch_with_learning_alignment(
        self,
        requests: list[Request],
        learning_position: LpPosition | None = None,
        context: Any = None,
        custom_fields_per_request: list[dict[str, Any]] | None = None,
    ) -> Result[list[T]]:
        """
        Create multiple entities with learning alignment in batch.

        Useful for batch operations like creating multiple events for a learning path schedule.

        Args:
            requests: List of creation requests
            learning_position: Optional learning path position
            context: Optional context for validation
            custom_fields_per_request: Optional list of custom fields per request (must match requests length)

        Returns:
            Result containing list of created entities

        Example:
            ```python
            # In EventsLearningService:
            requests = [EventCreateRequest(...) for _ in range(12)]
            custom_fields = [{"source_learning_path_uid": lp_uid} for _ in range(12)]

            result = await self.learning_helper.create_batch_with_learning_alignment(
                requests=requests,
                custom_fields_per_request=custom_fields,
            )
            ```
        """
        self.logger.debug(
            f"Creating batch of {len(requests)} {self.entity_name}s with learning alignment"
        )

        # Validate that custom_fields_per_request matches requests if provided
        if custom_fields_per_request and len(custom_fields_per_request) != len(requests):
            return Result.fail(
                Errors.validation(
                    f"custom_fields_per_request length ({len(custom_fields_per_request)}) "
                    f"must match requests length ({len(requests)})"
                )
            )

        # Create each entity using single creation method
        created_entities = []
        for i, request in enumerate(requests):
            custom_fields = custom_fields_per_request[i] if custom_fields_per_request else None

            result = await self.create_with_learning_alignment(
                request, learning_position, context, custom_fields
            )

            if result.is_error:
                # Return error on first failure
                self.logger.warning(
                    f"Batch creation failed at index {i}/{len(requests)}: {result.error}"
                )
                return Result.fail(result.expect_error())

            created_entities.append(result.value)

        self.logger.info(
            f"Created {len(created_entities)} {self.entity_name}s in batch with learning alignment"
        )

        return Result.ok(created_entities)

    async def get_learning_supporting_entities(
        self, user_uid: str, learning_position: LpPosition
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
        get_user_method = getattr(self.backend, self.backend_get_user_method, None)
        if not get_user_method:
            return Result.fail(
                Errors.system(
                    message=f"Backend method '{self.backend_get_user_method}' not found",
                    operation="get_learning_supporting_entities",
                )
            )

        entities_result = await get_user_method(user_uid)
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

    async def suggest_learning_aligned_entities(
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
                if current_step.primary_knowledge_uids:
                    step_knowledge = current_step.primary_knowledge_uids[0]
                    step_description = step_knowledge

                mastery_suggestion = {
                    "title": f"Master {step_description}",
                    "name": f"Master {step_description}",  # For habits
                    "description": f"Achieve mastery in {step_description} from {path.name}",
                    "domain": path.domain,
                    "priority": Priority.HIGH,
                    "learning_alignment_score": 0.95,
                    "supporting_path": path.name,
                    "suggested_timeline": f"{int(current_step.estimated_hours)} hours",
                    "suggestion_reason": f"Current step in {path.name} learning path",
                }
                suggestions.append(mastery_suggestion)

            # Suggest path completion entity
            remaining_steps = len(
                [s for s in path.steps if s.uid not in learning_position.completed_step_uids]
            )
            if remaining_steps > 0:
                completion_suggestion = {
                    "title": f"Complete {path.name} Learning Path",
                    "name": f"Complete {path.name}",  # For habits
                    "description": f"Complete all {remaining_steps} remaining steps in {path.name}",
                    "domain": path.domain,
                    "priority": Priority.MEDIUM,
                    "learning_alignment_score": 0.9,
                    "supporting_path": path.name,
                    "suggested_timeline": f"{remaining_steps} weeks",
                    "suggestion_reason": f"Path completion with {remaining_steps} steps remaining",
                }
                suggestions.append(completion_suggestion)

            # Suggest outcome-based entities
            for outcome in path.outcomes[:2]:  # Limit to 2 outcomes per path
                outcome_suggestion = {
                    "title": f"Achieve: {outcome}",
                    "name": f"Practice: {outcome}",  # For habits
                    "description": f"Learning outcome from {path.name}: {outcome}",
                    "domain": path.domain,
                    "priority": Priority.MEDIUM,
                    "learning_alignment_score": 0.8,
                    "supporting_path": path.name,
                    "suggested_timeline": "1-2 months",
                    "suggestion_reason": f"Learning outcome from {path.name}",
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
        self, entity_uid: str, learning_position: LpPosition
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
        get_method = getattr(self.backend, self.backend_get_method, None)
        if not get_method:
            return Result.fail(
                Errors.system(
                    message=f"Backend method '{self.backend_get_method}' not found",
                    operation="assess_learning_alignment",
                )
            )

        entity_result = await get_method(entity_uid)
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
        except (AttributeError, KeyError):
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
                    if current_step.primary_knowledge_uids:
                        step_description = current_step.primary_knowledge_uids[0]

                    assessment["learning_milestones"].append(
                        {
                            "path": path.name,
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
            if path.name.lower() in entity_text:
                learning_score += 0.3
                break  # Only count once per entity

        return learning_score
