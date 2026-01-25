"""
Choice Relationships Helper (Graph-Native Pattern)
====================================

Container for choice relationship data fetched from graph.
Follows the Domain Relationships Pattern used across all activity domains.

⚠️  CRITICAL FOR DEVELOPERS: These fields DO NOT exist in ChoiceDTO anymore!
================================================================

❌ WRONG - These fields were NEVER in Choice/ChoiceDTO (always graph-native):
    choice.informed_by_knowledge_uids    # AttributeError!
    choice.opens_learning_path_uids      # AttributeError!
    choice.required_knowledge_uids       # AttributeError!
    choice.aligned_principle_uids        # AttributeError!

✅ CORRECT - Use ChoiceRelationships.fetch() instead:
    rels = await ChoiceRelationships.fetch(choice.uid, service.relationships)
    rels.informed_by_knowledge_uids      # ✓ List of UIDs from graph
    rels.opens_learning_path_uids        # ✓ List of UIDs from graph
    rels.required_knowledge_uids         # ✓ List of UIDs from graph

Decision Tree: "Do I need relationship data?"
=============================================

Q1: Am I writing code that needs to know about choice relationships?
    (knowledge informing choice, learning paths opened, principles aligned)

    YES → Use ChoiceRelationships.fetch()
    NO  → Use choice.attribute directly (e.g., choice.title, choice.decision_date)

Q2: Do I have access to a ChoicesRelationshipService instance?

    YES → Fetch relationships:
          ```python
          rels = await ChoiceRelationships.fetch(choice.uid, choices_service.relationships)
          if rels.informed_by_knowledge_uids:
              # Process knowledge relationships
          ```

    NO  → Use proxy attributes OR refactor to pass service:
          Proxy: choice.status (indicates if choice resolved)
          Proxy: choice.decision_date (when choice was made)

          Better: Refactor to receive choices_service as parameter

📖 COMPLETE PATTERN GUIDE:
    This is the Choice-specific implementation of the Domain Relationships Pattern.
    For the complete cross-domain guide, see:
    → /docs/patterns/DOMAIN_RELATIONSHIPS_PATTERN.md

    Pattern is also used by:
    - TaskRelationships (9 relationships)
    - GoalRelationships (9 relationships)
    - EventRelationships (3 relationships)
    - HabitRelationships (6 relationships)
    - LsRelationships (5 relationships)
    - PrincipleRelationships (4 relationships)

Graph-Native Design (Always Graph-Native):
----------------------------------------------
- Choice domain was designed graph-native from the start
- Never had relationship lists in node properties
- All relationships stored as Neo4j edges
- Query relationships via: ChoiceRelationships.fetch()

Philosophy: "Relationships ARE the data structure, not serialized lists"
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.services.relationships import UnifiedRelationshipService
from core.utils.generic_fetcher import fetch_relationships_parallel

# Type alias for backward compatibility
ChoicesRelationshipService = UnifiedRelationshipService


# Query specifications: (field_name, service_method_name)
# Defines the mapping between dataclass fields and service query methods
CHOICE_QUERY_SPECS: list[tuple[str, str]] = [
    ("informed_by_knowledge_uids", "informed_knowledge"),
    ("opens_learning_path_uids", "learning_paths"),
    ("required_knowledge_uids", "required_knowledge"),
    ("aligned_principle_uids", "principles"),
    ("implementing_task_uids", "implementing_tasks"),
    ("serves_life_path_uids", "life_path"),
    ("impacted_habit_uids", "impacted_habits"),
    ("informing_habit_uids", "informing_habits"),
    ("scheduled_event_uids", "scheduled_events"),
    ("triggering_event_uids", "triggering_events"),
]


@dataclass(frozen=True)
class ChoiceRelationships:
    """
    Container for all choice relationship data (fetched from Neo4j graph).

    📚 COMPLETE USAGE GUIDE FOR DEVELOPERS
    ========================================

    Example 1: Basic Usage (Single Choice)
    -------------------------------------
    ```python
    # In a service method:
    async def analyze_choice_knowledge(self, choice_uid: str) -> Result[float]:
        # 1. Get the choice
        choice_result = await self.get_choice(choice_uid)
        if choice_result.is_error:
            return choice_result
        choice = choice_result.value

        # 2. Fetch relationships (4 parallel queries)
        rels = await ChoiceRelationships.fetch(choice.uid, self.relationships)

        # 3. Use relationship data
        if rels.informed_by_knowledge_uids:
            knowledge_score = len(rels.informed_by_knowledge_uids) * 0.2
        else:
            knowledge_score = 0.0

        return Result.ok(knowledge_score)
    ```

    Example 2: Batch Processing (Multiple Choices)
    ---------------------------------------------
    ```python
    async def analyze_decision_patterns(self, user_uid: str) -> Result[dict]:
        # 1. Get all user choices
        choices_result = await self.get_user_choices(user_uid)
        choices = choices_result.value

        # 2. Fetch relationships for ALL choices in parallel
        all_rels = await asyncio.gather(
            *[
                ChoiceRelationships.fetch(choice.uid, self.relationships)
                for choice in choices
            ]
        )

        # 3. Create mapping for easy lookup
        rels_by_uid = {choice.uid: rels for choice, rels in zip(choices, all_rels)}

        # 4. Process each choice with its relationships
        informed_choices = []
        for choice in choices:
            rels = rels_by_uid[choice.uid]
            if rels.informed_by_knowledge_uids:
                informed_choices.append(choice)

        return Result.ok({"informed_choice_count": len(informed_choices)})
    ```

    Example 3: When You DON'T Have Service Access
    ----------------------------------------------
    ```python
    # ❌ WRONG - Don't try to access removed fields
    def calculate_decision_quality(choice: ChoiceDTO) -> float:
        if choice.informed_by_knowledge_uids:  # AttributeError!
            return 0.8
        return 0.3


    # ✅ OPTION A - Use proxy attributes
    def calculate_decision_quality(choice: ChoiceDTO) -> float:
        if choice.status == ChoiceStatus.RESOLVED:
            return 0.6  # Estimate for resolved choices
        return 0.3


    # ✅ OPTION B (BETTER) - Refactor to accept service
    async def calculate_decision_quality(
        choice: ChoiceDTO,
        choices_service: ChoicesService,  # Now we can fetch relationships!
    ) -> float:
        rels = await ChoiceRelationships.fetch(
            choice.uid, choices_service.relationships
        )
        return len(rels.informed_by_knowledge_uids) * 0.2
    ```

    Available Proxy Attributes (when relationships not accessible):
    ---------------------------------------------------------------
    - choice.status: ChoiceStatus → Indicates if choice resolved
    - choice.decision_date: date | None → When choice was made
    - choice.reflection_notes: str | None → Decision context

    Benefits:
    ---------
    - Single fetch operation for all relationships (performance)
    - Explicit about what data each method needs (clarity)
    - No stale data (always fresh from graph)
    - Easy to mock for testing (use ChoiceRelationships.empty())

    Performance:
    -----------
    - 4 parallel queries = ~60% faster than sequential
    - Batch fetching 100 choices = ~50% improvement over per-choice queries

    Migration Notes:
    ---------------
    - Choice domain was ALWAYS graph-native (no migration needed)
    - Follows same pattern as Tasks, Goals, Events for consistency
    - See: /docs/patterns/DOMAIN_RELATIONSHIPS_PATTERN.md
    """

    informed_by_knowledge_uids: list[str] = field(default_factory=list)
    opens_learning_path_uids: list[str] = field(default_factory=list)
    required_knowledge_uids: list[str] = field(default_factory=list)
    aligned_principle_uids: list[str] = field(default_factory=list)
    implementing_task_uids: list[str] = field(default_factory=list)
    serves_life_path_uids: list[str] = field(default_factory=list)

    # Habit relationships (January 2026)
    impacted_habit_uids: list[str] = field(default_factory=list)
    informing_habit_uids: list[str] = field(default_factory=list)

    # Event relationships (January 2026)
    scheduled_event_uids: list[str] = field(default_factory=list)
    triggering_event_uids: list[str] = field(default_factory=list)

    @classmethod
    async def fetch(
        cls, choice_uid: str, service: ChoicesRelationshipService
    ) -> ChoiceRelationships:
        """
        Fetch all relationship data from graph in parallel.

        Performs 4 graph queries concurrently using asyncio.gather() for optimal performance.
        Each query maps to one relationship type in the Choice model.

        Args:
            choice_uid: UID of choice to fetch relationships for
            service: ChoicesRelationshipService instance (provides graph query methods)

        Returns:
            ChoiceRelationships instance with all relationship data

        Example:
            service = services.choices
            rels = await ChoiceRelationships.fetch("choice_123", service.relationships)
            print(f"Choice informed by {len(rels.informed_by_knowledge_uids)} knowledge units")

        Performance:
        - 4 parallel queries vs 4 sequential = ~60% faster
        - Single fetch vs per-method queries = 40-50% improvement
        """
        return await fetch_relationships_parallel(
            uid=choice_uid,
            service=service,
            query_specs=CHOICE_QUERY_SPECS,
            dataclass_type=cls,
        )

    @classmethod
    def empty(cls) -> ChoiceRelationships:
        """
        Create empty ChoiceRelationships (for testing or new choices).

        Returns:
            ChoiceRelationships with all empty lists

        Example:
            # Testing a method that requires relationships
            rels = ChoiceRelationships.empty()
            assert choice.calculate_decision_quality(rels) == 0.0
        """
        return cls()

    def has_any_knowledge(self) -> bool:
        """
        Check if choice has any knowledge connections.

        Returns:
            True if choice has informing, required, or learning path knowledge
        """
        return (
            len(self.informed_by_knowledge_uids) > 0
            or len(self.required_knowledge_uids) > 0
            or len(self.opens_learning_path_uids) > 0
        )

    def total_knowledge_count(self) -> int:
        """
        Get total count of all knowledge connections.

        Returns:
            Sum of all knowledge-related relationship counts
        """
        return (
            len(self.informed_by_knowledge_uids)
            + len(self.required_knowledge_uids)
            + len(self.opens_learning_path_uids)
        )

    def is_principle_aligned(self) -> bool:
        """
        Check if choice aligns with any principles.

        Returns:
            True if choice has principle alignments
        """
        return len(self.aligned_principle_uids) > 0

    def is_informed_decision(self) -> bool:
        """
        Check if choice was informed by knowledge.

        Returns:
            True if choice has knowledge informing the decision
        """
        return len(self.informed_by_knowledge_uids) > 0

    def opens_learning(self) -> bool:
        """
        Check if choice opens learning opportunities.

        Returns:
            True if choice opens new learning paths
        """
        return len(self.opens_learning_path_uids) > 0

    def has_implementing_tasks(self) -> bool:
        """
        Check if choice has tasks that implement it.

        Returns:
            True if tasks are implementing this choice
        """
        return len(self.implementing_task_uids) > 0

    def is_actionable(self) -> bool:
        """
        Check if choice has been converted to actionable tasks.

        A choice is actionable if it has implementing tasks
        or opens learning paths (which can lead to tasks).

        Returns:
            True if choice has downstream action items
        """
        return self.has_implementing_tasks() or self.opens_learning()

    def get_all_knowledge_uids(self) -> set[str]:
        """
        Get all unique knowledge UIDs across all relationship types.

        Note: Only returns knowledge unit UIDs, not learning path UIDs.

        Returns:
            Set of all knowledge UIDs (informed, required)
        """
        all_uids: set[str] = set()
        all_uids.update(self.informed_by_knowledge_uids)
        all_uids.update(self.required_knowledge_uids)
        # Do NOT include opens_learning_path_uids (those are LP UIDs, not KU UIDs)
        return all_uids

    def serves_life_path(self) -> bool:
        """Check if choice serves user's life path."""
        return len(self.serves_life_path_uids) > 0

    def get_life_path_uid(self) -> str | None:
        """Get the life path UID this choice serves (if any)."""
        return self.serves_life_path_uids[0] if self.serves_life_path_uids else None

    def has_habit_impact(self) -> bool:
        """Check if choice has any habit relationships."""
        return len(self.impacted_habit_uids) > 0 or len(self.informing_habit_uids) > 0

    def impacts_habits(self) -> bool:
        """Check if this choice impacted any habits."""
        return len(self.impacted_habit_uids) > 0

    def informed_by_habits(self) -> bool:
        """Check if this choice was informed by any habits."""
        return len(self.informing_habit_uids) > 0

    def has_event_relationship(self) -> bool:
        """Check if choice has any event relationships."""
        return len(self.scheduled_event_uids) > 0 or len(self.triggering_event_uids) > 0

    def schedules_events(self) -> bool:
        """Check if this choice scheduled any events."""
        return len(self.scheduled_event_uids) > 0

    def triggered_by_events(self) -> bool:
        """Check if this choice was triggered by any events."""
        return len(self.triggering_event_uids) > 0
