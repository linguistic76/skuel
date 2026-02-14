"""
Adaptive Learning Path Core Service
====================================

Generates dynamic learning paths based on user goals, learning style, and knowledge gaps.
Handles path generation, sequencing, and adaptation.
"""

import random
from collections import defaultdict
from datetime import datetime, timedelta
from operator import itemgetter
from typing import TYPE_CHECKING

from core.models.enums import KuStatus
from core.models.ku.ku_dto import KuDTO
from core.services.adaptive_lp.adaptive_lp_models import AdaptiveLp, LearningStyle
from core.services.adaptive_lp_types import KnowledgeState

if TYPE_CHECKING:
    from core.services.user import UserContext

# NOTE (November 2025): Removed Has* protocol imports - Goal model is well-typed
# - Goal.target_date: date | None (direct access)
# - Goal.success_criteria: str | None (direct access)
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator


class LpType(str):
    """Types of learning paths that can be generated."""

    GOAL_DRIVEN = "goal_driven"
    GAP_FILLING = "gap_filling"
    CROSS_DOMAIN = "cross_domain"
    REINFORCEMENT = "reinforcement"
    EXPLORATION = "exploration"
    PROJECT_BASED = "project_based"


class AdaptiveLpCoreService:
    """
    Core service for generating and managing adaptive learning paths.

    Focuses on:
    - Dynamic learning path generation based on user goals
    - Learning style detection
    - Knowledge sequencing and adaptation


    Source Tag: "adaptive_lp_core_service_explicit"
    - Format: "adaptive_lp_core_service_explicit" for user-created relationships
    - Format: "adaptive_lp_core_service_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from adaptive_lp_core metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (Phase 5 eliminated those)
    - Returns Result[T] for error handling
    - Logs operations with structured logging

    """

    def __init__(
        self, ku_service=None, learning_service=None, goals_service=None, tasks_service=None
    ) -> None:
        """
        Initialize the adaptive learning path core service.

        Args:
            ku_service: For accessing knowledge units,
            learning_service: For learning path management,
            goals_service: For user goals and progress,
            tasks_service: For task completion patterns
        """
        self.ku_service = ku_service
        self.learning_service = learning_service
        self.goals_service = goals_service
        self.tasks_service = tasks_service
        self.logger = get_logger("skuel.adaptive_lp_core")

        # Adaptation parameters
        self.min_confidence_threshold = 0.7
        self.max_path_steps = 20
        self.adaptation_frequency_days = 7

        # Learning style detection parameters
        self.style_detection_min_tasks = 5
        self.style_confidence_threshold = 0.6

    # ========================================================================
    # USER ANALYSIS (STUBS - TO BE IMPLEMENTED)
    # ========================================================================

    async def _detect_learning_style(self, user_uid: str) -> str:
        """
        TODO: Detect user's learning style from behavior patterns.

        Returns:
            str: Learning style identifier (default: 'balanced')
        """
        return "balanced"

    # ========================================================================
    # DYNAMIC LEARNING PATH GENERATION
    # ========================================================================

    @with_error_handling(error_type="system", uid_param="goal_uid")
    async def generate_goal_driven_learning_path(
        self, user_uid: str, goal_uid: str, learning_style_override: str | None = None
    ) -> Result[AdaptiveLp]:
        """
        Generate a dynamic learning path based on a specific user goal.

        Args:
            user_uid: User to generate path for,
            goal_uid: Specific goal to target,
            learning_style_override: Override detected learning style

        Returns:
            Result containing AdaptiveLp
        """
        # Get the target goal
        if not self.goals_service:
            return Result.fail(
                Errors.system(
                    message="Goals service not available",
                    operation="generate_goal_driven_learning_path",
                )
            )

        goal_result = await self.goals_service.get_goal(goal_uid)
        if goal_result.is_error:
            return goal_result

        goal = goal_result.value

        # Detect user's learning style
        if learning_style_override:
            learning_style = learning_style_override
        else:
            style_result = await self.detect_learning_style(user_uid)
            if style_result.is_error:
                return Result.fail(style_result.expect_error())
            learning_style = style_result.value

        # Analyze current knowledge state
        # NOTE: This internal method needs UserContext but receives user_uid
        # Create minimal context as temporary workaround until facade refactor
        from core.services.user import UserContext

        minimal_context = UserContext(user_uid=user_uid)
        self.logger.warning(
            "generate_from_goal_internal uses minimal UserContext - "
            "consider refactoring to accept context parameter"
        )
        knowledge_state_result = await self.analyze_user_knowledge_state(minimal_context)
        if knowledge_state_result.is_error:
            return Result.fail(knowledge_state_result.expect_error())
        knowledge_state = knowledge_state_result.value

        # Identify knowledge gaps for goal
        gaps_result = await self._identify_goal_knowledge_gaps(goal, knowledge_state)
        if gaps_result.is_error:
            return Result.fail(gaps_result.expect_error())

        gaps = gaps_result.value

        # Generate learning sequence based on style and gaps
        sequence_result = await self._generate_learning_sequence(
            goal, gaps, learning_style, knowledge_state
        )
        if sequence_result.is_error:
            return Result.fail(sequence_result.expect_error())

        knowledge_steps = sequence_result.value

        # Calculate adaptation factors
        adaptation_factors = await self._calculate_adaptation_factors(
            user_uid, goal, knowledge_steps
        )

        # Create adaptive learning path
        path = AdaptiveLp(
            path_id=UIDGenerator.generate_random_uid("adaptive_path"),
            title=f"Adaptive Path: {goal.title}",
            description=f"Personalized learning path to achieve {goal.title} based on your learning style and current knowledge",
            path_type=LpType.GOAL_DRIVEN,
            target_goals=[goal_uid],
            learning_outcomes=await self._derive_learning_outcomes(goal, knowledge_steps),
            estimated_duration_hours=await self._estimate_path_duration(knowledge_steps),
            difficulty_level=await self._calculate_path_difficulty(knowledge_steps),
            knowledge_steps=knowledge_steps,
            alternative_paths=await self._generate_alternative_sequences(
                knowledge_steps, learning_style
            ),
            prerequisites=await self._identify_path_prerequisites(knowledge_steps),
            unlocks=await self._identify_unlocked_knowledge(knowledge_steps),
            adaptation_factors=adaptation_factors,
            learning_style_match=await self._calculate_style_match(learning_style, knowledge_steps),
            confidence_score=await self._calculate_path_confidence(goal, knowledge_steps, gaps),
        )

        self.logger.info(
            f"Generated goal-driven learning path for user {user_uid}, goal {goal_uid}: "
            f"{len(knowledge_steps)} steps, {path.estimated_duration_hours}h, "
            f"difficulty {path.difficulty_level:.1f}/10"
        )

        return Result.ok(path)

    # ========================================================================
    # LEARNING STYLE DETECTION
    # ========================================================================

    @with_error_handling(error_type="system", uid_param="user_uid")
    async def detect_learning_style(self, user_uid: str) -> Result[str]:
        """Detect user's learning style from task completion patterns."""
        if not self.tasks_service:
            return Result.ok(LearningStyle.INDEPENDENT)

        # Get user's completed tasks
        tasks_result = await self.tasks_service.get_user_tasks(user_uid)
        if tasks_result.is_error or len(tasks_result.value) < self.style_detection_min_tasks:
            return Result.ok(LearningStyle.INDEPENDENT)

        tasks = [t for t in tasks_result.value if t.status == KuStatus.COMPLETED]

        # Analyze patterns to detect learning style
        style_scores = {
            LearningStyle.SEQUENTIAL: 0.0,
            LearningStyle.HOLISTIC: 0.0,
            LearningStyle.PRACTICAL: 0.0,
            LearningStyle.THEORETICAL: 0.0,
            LearningStyle.SOCIAL: 0.0,
            LearningStyle.INDEPENDENT: 0.0,
        }

        for task in tasks:
            # Sequential learners: consistent progression, step-by-step
            # GRAPH-NATIVE MIGRATION: prerequisite_task_uids removed from TaskDTO
            # Use parent_uid as proxy for hierarchical task structure
            if task.parent_uid:
                style_scores[LearningStyle.SEQUENTIAL] += 0.2

            # Practical learners: apply knowledge immediately
            # GRAPH-NATIVE MIGRATION: applies_knowledge_uids removed from TaskDTO
            # Use source_learning_step_uid or knowledge_mastery_check as proxy for learning tasks
            if task.source_learning_step_uid or task.knowledge_mastery_check:
                style_scores[LearningStyle.PRACTICAL] += 0.3

            # Theoretical learners: knowledge mastery checks
            if task.knowledge_mastery_check:
                style_scores[LearningStyle.THEORETICAL] += 0.2

            # Social learners: collaborative tags/projects
            if any(tag in ["team", "collaboration", "pair", "review"] for tag in task.tags):
                style_scores[LearningStyle.SOCIAL] += 0.1

            # Holistic learners: cross-domain connections
            # GRAPH-NATIVE MIGRATION: applies_knowledge_uids removed from TaskDTO
            # Cannot determine cross-domain knowledge connections without relationship data
            # This check is removed - requires relationship service access

            # Independent learners: self-directed, no prerequisites
            # GRAPH-NATIVE MIGRATION: prerequisite fields removed from TaskDTO
            # Use lack of parent_uid and learning_step as proxy for independent work
            if not task.parent_uid and not task.source_learning_step_uid:
                style_scores[LearningStyle.INDEPENDENT] += 0.1

        # Normalize scores
        total_score = sum(style_scores.values())
        if total_score > 0:
            for style in style_scores:
                style_scores[style] /= total_score

        # Return style with highest score
        detected_style = max(style_scores.items(), key=itemgetter(1))[0]

        self.logger.debug(f"Detected learning style for user {user_uid}: {detected_style}")
        return Result.ok(detected_style)

    # ========================================================================
    # KNOWLEDGE STATE ANALYSIS
    # ========================================================================

    @with_error_handling(error_type="system")
    async def analyze_user_knowledge_state(self, context: "UserContext") -> Result[KnowledgeState]:
        """
        Analyze user's current knowledge state from UserContext.

        **REFACTORED (2026-02-08):** Uses UserContext instead of re-querying tasks.
        UserContext already contains all knowledge state via MEGA-QUERY.

        Args:
            context: UserContext with complete user state (~240 fields)

        Returns:
            Result[KnowledgeState] with mastery, progress, and velocity data

        Note:
            This method now operates on pre-fetched UserContext data rather than
            querying tasks directly, eliminating duplicate queries and aligning
            with "UserContext as single source of truth" architecture.
        """
        # Use UserContext fields directly (populated by MEGA-QUERY)
        mastered_set = context.mastered_knowledge_uids
        in_progress_set = context.in_progress_knowledge_uids
        mastery_dict = context.knowledge_mastery  # uid -> mastery % (0.0-1.0)

        # Build knowledge strengths from mastery levels
        strengths_dict: dict[str, int] = {}
        for ku_uid, mastery_level in mastery_dict.items():
            # Convert mastery percentage to usage count proxy (reverse of old logic)
            if mastery_level >= 0.8:
                strengths_dict[ku_uid] = 5  # High mastery
            elif mastery_level >= 0.5:
                strengths_dict[ku_uid] = 3  # Medium mastery
            elif mastery_level > 0.0:
                strengths_dict[ku_uid] = 1  # Some mastery

        # Calculate applied knowledge from completed tasks with learning context
        # UserContext tracks completed_task_uids but not individual task details
        # For velocity, we use knowledge mastery changes as proxy
        applied_set = {ku_uid for ku_uid in mastered_set}  # Mastered = applied

        # Identify knowledge gaps (prerequisites needed but not completed)
        gaps_list: list[str] = []
        for ku_uid, prereqs in context.prerequisites_needed.items():
            if ku_uid not in mastered_set and prereqs:
                # Check if prerequisites are met
                missing_prereqs = [p for p in prereqs if p not in context.prerequisites_completed]
                if missing_prereqs:
                    gaps_list.append(ku_uid)

        # Calculate learning velocity from recently mastered knowledge
        # UserContext has recently_mastered_uids (last 30 days)
        recently_mastered = getattr(context, "recently_mastered_uids", set())
        velocity_score = len(recently_mastered) / 4.0  # KUs per week (30 days / 7 days)

        # Build immutable result using frozen dataclass
        knowledge_state = KnowledgeState(
            mastered_knowledge=mastered_set,
            in_progress_knowledge=in_progress_set,
            applied_knowledge=applied_set,
            knowledge_strengths=strengths_dict,
            knowledge_gaps=gaps_list,
            mastery_levels=mastery_dict,
            learning_velocity=velocity_score,
        )

        self.logger.debug(
            f"Analyzed knowledge state for user {context.user_uid}: "
            f"{len(knowledge_state.mastered_knowledge)} mastered, "
            f"{len(knowledge_state.applied_knowledge)} applied, "
            f"velocity {knowledge_state.learning_velocity:.1f}/week"
        )

        return Result.ok(knowledge_state)

    # ========================================================================
    # PRIVATE HELPER METHODS
    # ========================================================================

    @with_error_handling(error_type="system")
    async def _identify_goal_knowledge_gaps(
        self, goal: KuDTO, knowledge_state: KnowledgeState
    ) -> Result[list[str]]:
        """Identify knowledge gaps preventing goal achievement."""
        gaps = []

        # Analyze goal requirements
        goal_text = f"{goal.title} {goal.description}".lower()

        # Map common goal keywords to knowledge areas
        knowledge_mappings = {
            "python": ["ku.programming.python", "ku.programming.basics"],
            "web development": ["ku.web.html", "ku.web.css", "ku.web.javascript"],
            "data analysis": ["ku.data.analysis", "ku.data.visualization", "ku.statistics"],
            "machine learning": [
                "ku.ml.fundamentals",
                "ku.ml.algorithms",
                "ku.data.preprocessing",
            ],
            "api": ["ku.api.rest", "ku.api.design", "ku.programming.http"],
            "database": ["ku.database.sql", "ku.database.design", "ku.database.optimization"],
            "testing": ["ku.testing.unit", "ku.testing.integration", "ku.testing.automation"],
            "deployment": ["ku.devops.docker", "ku.devops.ci_cd", "ku.cloud.basics"],
        }

        # Find required knowledge for goal
        required_knowledge = set()
        for keyword, knowledge_uids in knowledge_mappings.items():
            if keyword in goal_text:
                required_knowledge.update(knowledge_uids)

        # Compare with user's current knowledge
        mastered = knowledge_state.mastered_knowledge
        applied = knowledge_state.applied_knowledge
        current_knowledge = mastered.union(applied)

        # Identify gaps
        gaps = list(required_knowledge - current_knowledge)

        self.logger.debug(f"Identified {len(gaps)} knowledge gaps for goal '{goal.title}': {gaps}")

        return Result.ok(gaps)

    @with_error_handling(error_type="system")
    async def _generate_learning_sequence(
        self,
        _goal: KuDTO,
        knowledge_gaps: list[str],
        learning_style: str,
        knowledge_state: KnowledgeState,
    ) -> Result[list[str]]:
        """Generate optimal learning sequence based on style and gaps."""
        if not knowledge_gaps:
            return Result.ok([])

        # Create dependency graph
        dependencies = await self._build_knowledge_dependencies(knowledge_gaps)

        # Generate sequence based on learning style
        if learning_style == LearningStyle.SEQUENTIAL:
            sequence = await self._topological_sort(knowledge_gaps, dependencies)
        elif learning_style == LearningStyle.HOLISTIC:
            sequence = await self._holistic_sequence(knowledge_gaps, dependencies)
        elif learning_style == LearningStyle.PRACTICAL:
            sequence = await self._practical_sequence(knowledge_gaps, knowledge_state)
        else:
            sequence = await self._balanced_sequence(knowledge_gaps, dependencies)

        # Limit sequence length
        sequence = sequence[: self.max_path_steps]

        self.logger.debug(
            f"Generated learning sequence for {learning_style}: {len(sequence)} steps"
        )

        return Result.ok(sequence)

    async def _build_knowledge_dependencies(
        self, knowledge_uids: list[str]
    ) -> dict[str, list[str]]:
        """Build a simplified dependency graph for knowledge units."""
        dependencies = {}

        for ku_uid in knowledge_uids:
            deps = []

            if "advanced" in ku_uid:
                basic_uid = ku_uid.replace("advanced", "basics")
                if basic_uid in knowledge_uids:
                    deps.append(basic_uid)

            if "optimization" in ku_uid:
                fundamental_uid = ku_uid.replace("optimization", "fundamentals")
                if fundamental_uid in knowledge_uids:
                    deps.append(fundamental_uid)

            if ku_uid.startswith("ku.ml."):
                if "ku.data.analysis" in knowledge_uids:
                    deps.append("ku.data.analysis")
                if "ku.programming.python" in knowledge_uids:
                    deps.append("ku.programming.python")

            if ku_uid.startswith("ku.web.") and "ku.programming.basics" in knowledge_uids:
                deps.append("ku.programming.basics")

            dependencies[ku_uid] = deps

        return dependencies

    async def _topological_sort(
        self, knowledge_uids: list[str], dependencies: dict[str, list[str]]
    ) -> list[str]:
        """Topological sort for sequential learning style."""
        result = []
        visited = set()
        temp_visited = set()

        def visit(uid) -> None:
            if uid in temp_visited:
                return
            if uid in visited:
                return

            temp_visited.add(uid)
            for dep in dependencies.get(uid, []):
                if dep in knowledge_uids:
                    visit(dep)
            temp_visited.remove(uid)
            visited.add(uid)
            result.append(uid)

        for uid in knowledge_uids:
            if uid not in visited:
                visit(uid)

        return result

    async def _holistic_sequence(
        self, knowledge_uids: list[str], dependencies: dict[str, list[str]]
    ) -> list[str]:
        """Generate sequence for holistic learners (overview first)."""
        domains = defaultdict(list)
        for uid in knowledge_uids:
            if "." in uid:
                domain = uid.split(".")[1]
                domains[domain].append(uid)

        sequence = []
        remaining = knowledge_uids.copy()

        # Add overview items first
        for domain_uids in domains.values():
            fundamental = None
            for uid in domain_uids:
                if "basics" in uid or "fundamentals" in uid:
                    fundamental = uid
                    break

            if fundamental and fundamental in remaining:
                sequence.append(fundamental)
                remaining.remove(fundamental)

        # Add remaining items by dependency
        sequence.extend(await self._topological_sort(remaining, dependencies))

        return sequence

    async def _practical_sequence(
        self, knowledge_uids: list[str], _knowledge_state: KnowledgeState
    ) -> list[str]:
        """Generate sequence for practical learners (application-focused)."""
        scored_knowledge = []

        for uid in knowledge_uids:
            practicality_score = 0.0

            if any(keyword in uid for keyword in ["api", "web", "database", "testing"]):
                practicality_score += 0.5

            if "programming" in uid:
                practicality_score += 0.3

            if any(keyword in uid for keyword in ["theory", "mathematics", "algorithm"]):
                practicality_score -= 0.2

            scored_knowledge.append((uid, practicality_score))

        scored_knowledge.sort(key=itemgetter(1), reverse=True)

        return [uid for uid, _ in scored_knowledge]

    async def _balanced_sequence(
        self, knowledge_uids: list[str], dependencies: dict[str, list[str]]
    ) -> list[str]:
        """Generate balanced sequence mixing approaches."""
        base_sequence = await self._topological_sort(knowledge_uids, dependencies)

        chunk_size = 3
        chunks = [
            base_sequence[i : i + chunk_size] for i in range(0, len(base_sequence), chunk_size)
        ]

        for chunk in chunks:
            random.shuffle(chunk)

        return [item for chunk in chunks for item in chunk]

    async def _calculate_adaptation_factors(
        self, user_uid: str, goal: KuDTO, knowledge_steps: list[str]
    ) -> dict[str, float]:
        """Calculate factors that influence path adaptation."""
        factors = {
            "goal_urgency": 0.5,
            "user_velocity": 0.5,
            "knowledge_complexity": 0.5,
            "prior_success_rate": 0.5,
            "time_availability": 0.5,
            "motivation_level": 0.5,
        }

        try:
            # Calculate goal urgency from target date
            if goal.target_date:
                days_to_target = (goal.target_date - datetime.now().date()).days
                if days_to_target > 0:
                    factors["goal_urgency"] = min(1.0, max(0.1, 1.0 - (days_to_target / 365)))

            # Estimate knowledge complexity
            if knowledge_steps:
                complexity_score = 0.0
                for step in knowledge_steps:
                    if "advanced" in step:
                        complexity_score += 0.8
                    elif "intermediate" in step:
                        complexity_score += 0.6
                    elif "basic" in step:
                        complexity_score += 0.4
                    else:
                        complexity_score += 0.5

                factors["knowledge_complexity"] = complexity_score / len(knowledge_steps)

            # Get user's learning velocity
            if self.tasks_service:
                tasks_result = await self.tasks_service.get_user_tasks(user_uid)
                if tasks_result.is_ok:
                    completed_tasks = [
                        t for t in tasks_result.value if t.status == KuStatus.COMPLETED
                    ]
                    if completed_tasks:
                        recent_date = datetime.now() - timedelta(weeks=4)
                        recent_completed = [
                            t
                            for t in completed_tasks
                            if t.completion_date
                            and datetime.combine(t.completion_date, datetime.min.time())
                            >= recent_date
                        ]
                        velocity = len(recent_completed) / 4.0
                        factors["user_velocity"] = min(1.0, velocity / 10.0)

            self.logger.debug(f"Calculated adaptation factors for user {user_uid}: {factors}")

        except Exception as e:
            self.logger.warning(f"Adaptation factor calculation failed: {e}")

        return factors

    async def _derive_learning_outcomes(self, goal: KuDTO, knowledge_steps: list[str]) -> list[str]:
        """Derive specific learning outcomes from goal and knowledge steps."""
        outcomes = []

        if goal.success_criteria:
            outcomes.append(goal.success_criteria)  # success_criteria is str, not list

        for step in knowledge_steps:
            if "programming" in step:
                outcomes.append(f"Demonstrate proficiency in {step.split('.')[-1]} programming")
            elif "database" in step:
                outcomes.append(f"Design and query databases using {step.split('.')[-1]}")
            elif "testing" in step:
                outcomes.append(f"Implement comprehensive {step.split('.')[-1]} testing")
            elif "api" in step:
                outcomes.append(f"Build and consume {step.split('.')[-1]} APIs")
            else:
                outcomes.append(f"Apply {step.split('.')[-1]} knowledge effectively")

        return outcomes[:8]

    async def _estimate_path_duration(self, knowledge_steps: list[str]) -> int:
        """Estimate total duration for learning path in hours."""
        total_hours = 0

        for step in knowledge_steps:
            if "basics" in step or "fundamentals" in step:
                total_hours += 4
            elif "advanced" in step:
                total_hours += 8
            elif "intermediate" in step:
                total_hours += 6
            else:
                total_hours += 5

        return total_hours

    async def _calculate_path_difficulty(self, knowledge_steps: list[str]) -> float:
        """Calculate overall difficulty level (0-10) for the learning path."""
        if not knowledge_steps:
            return 0.0

        difficulty_sum = 0.0

        for step in knowledge_steps:
            if "basics" in step or "fundamentals" in step:
                difficulty_sum += 3.0
            elif "intermediate" in step:
                difficulty_sum += 6.0
            elif "advanced" in step:
                difficulty_sum += 8.5
            elif any(keyword in step for keyword in ["optimization", "architecture", "algorithms"]):
                difficulty_sum += 7.5
            elif any(keyword in step for keyword in ["programming", "web", "database"]):
                difficulty_sum += 5.0
            else:
                difficulty_sum += 4.0

        return round(difficulty_sum / len(knowledge_steps), 1)

    async def _generate_alternative_sequences(
        self, main_sequence: list[str], _learning_style: str
    ) -> list[str]:
        """Generate alternative learning sequences for flexibility."""
        alternatives = []

        if len(main_sequence) <= 2:
            return alternatives

        reversed_sequence = main_sequence[::-1]
        alternatives.append(f"reverse:{','.join(reversed_sequence)}")

        if len(main_sequence) >= 4:
            chunk_size = 2
            chunks = [
                main_sequence[i : i + chunk_size] for i in range(0, len(main_sequence), chunk_size)
            ]
            chunked_sequence = [f"parallel:{','.join(chunk)}" for chunk in chunks]
            alternatives.append(f"chunked:{';'.join(chunked_sequence)}")

        return alternatives[:3]

    async def _identify_path_prerequisites(self, knowledge_steps: list[str]) -> list[str]:
        """Identify prerequisites that must be completed before starting the path."""
        prerequisites = []

        for step in knowledge_steps:
            if step.startswith("ku.programming.") and "basic" not in step:
                prerequisites.append("ku.programming.basics")

            if step.startswith("ku.ml."):
                prerequisites.extend(["ku.programming.python", "ku.data.basics"])

            if step.startswith("ku.web.") and "html" not in step:
                prerequisites.append("ku.web.html")

        return list(set(prerequisites) - set(knowledge_steps))

    async def _identify_unlocked_knowledge(self, knowledge_steps: list[str]) -> list[str]:
        """Identify knowledge that will be unlocked after completing this path."""
        unlocks = []

        domains = set()
        for step in knowledge_steps:
            if "." in step:
                domains.add(step.split(".")[1])

        for domain in domains:
            unlocks.extend(
                [f"ku.{domain}.advanced", f"ku.{domain}.expert", f"ku.{domain}.architecture"]
            )

        if "programming" in domains and "web" in domains:
            unlocks.append("ku.fullstack.development")

        if "data" in domains and "programming" in domains:
            unlocks.append("ku.data.engineering")

        return unlocks[:10]

    async def _calculate_style_match(
        self, learning_style: str, knowledge_steps: list[str]
    ) -> float:
        """Calculate how well the path matches the user's learning style."""
        if not knowledge_steps:
            return 0.5

        match_score = 0.5

        has_practical_steps = any(
            "programming" in step or "web" in step for step in knowledge_steps
        )
        has_theoretical_steps = any(
            "theory" in step or "algorithm" in step for step in knowledge_steps
        )
        has_sequential_deps = len(knowledge_steps) > 3

        if (learning_style == LearningStyle.PRACTICAL and has_practical_steps) or (
            learning_style == LearningStyle.THEORETICAL and has_theoretical_steps
        ):
            match_score += 0.3
        elif learning_style == LearningStyle.SEQUENTIAL and has_sequential_deps:
            match_score += 0.2
        elif learning_style == LearningStyle.HOLISTIC:
            domains = set(step.split(".")[1] for step in knowledge_steps if "." in step)
            if len(domains) > 2:
                match_score += 0.3

        return min(1.0, match_score)

    async def _calculate_path_confidence(
        self, goal: KuDTO, knowledge_steps: list[str], knowledge_gaps: list[str]
    ) -> float:
        """Calculate confidence in the path's effectiveness."""
        confidence = 0.5

        if knowledge_gaps:
            coverage = len(set(knowledge_steps) & set(knowledge_gaps)) / len(knowledge_gaps)
            confidence += coverage * 0.3

        if 3 <= len(knowledge_steps) <= 15:
            confidence += 0.1

        if goal.success_criteria:
            confidence += 0.1

        return min(1.0, confidence)
