"""
KnowledgeCarrier Protocol - Unified Knowledge Integration
==========================================================

Protocol defining entities that carry, apply, or reference knowledge.

Design Philosophy (from SKUEL):
- "Everything is a KU" - Every domain can be a knowledge carrier
- "Applied knowledge, not pure theory" - Substance measures lived experience
- "KU is a building block for LS" - Curriculum flows from KU → LS → LP → MOC

Protocol Tiers:
1. KnowledgeCarrier - Base protocol (all 10 domains implement)
2. SubstantiatedKnowledge - Extended with substance_score() (KU + Curriculum)
3. ActivityCarrier - Activity domains with learning integration

Architecture:
    SKUEL organizes knowledge through 10 domains that all implement
    KnowledgeCarrier protocol:

    Curriculum Domains (4) - ARE knowledge:
    - KU: Knowledge Units (atomic content)
    - LS: Learning Steps (sequences of KUs)
    - LP: Learning Paths (sequences of LSs)
    - MOC: Maps of Content (graphs of knowledge)

    Activity Domains (6) - CARRY/APPLY knowledge:
    - Task: Work items that apply knowledge
    - Event: Calendar items that practice knowledge
    - Habit: Recurring behaviors that embody knowledge
    - Goal: Objectives requiring knowledge
    - Choice: Decisions informed by knowledge
    - Principle: Values grounded in knowledge

Usage:
    # Type-safe dispatch for knowledge operations
    def process_knowledge(entity: KnowledgeCarrier) -> float:
        relevance = entity.knowledge_relevance()
        knowledge_uids = entity.get_knowledge_uids()
        return relevance

    # Runtime type checking
    if isinstance(task, KnowledgeCarrier):
        score = task.knowledge_relevance()

See Also:
- ADR-027: Knowledge Carrier Protocol
- CLAUDE.md § Knowledge Substance Philosophy
- domain_model_protocol.py - Base domain model protocol
"""

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from core.models.enums import Domain


@runtime_checkable
class KnowledgeCarrier(Protocol):
    """
    Base protocol for any entity that carries knowledge context.

    All 10 SKUEL domains implement this protocol:
    - Curriculum (KU, LS, LP, MOC): Full knowledge integration
    - Activity (Task, Event, Habit, Goal, Choice, Principle): Knowledge application

    This protocol enables unified knowledge intelligence operations:
    - Unified search across all knowledge carriers
    - Type-safe dispatch for learning recommendations
    - Consistent knowledge relevance scoring

    Required Attributes:
        uid: Unique identifier (e.g., "ku.python-basics", "task.123")

    Required Methods:
        knowledge_relevance: How relevant is knowledge to this entity (0.0-1.0)
        get_knowledge_uids: Get all knowledge UIDs this entity carries/references

    Example:
        # Check if entity is a knowledge carrier
        if isinstance(entity, KnowledgeCarrier):
            if entity.knowledge_relevance() > 0.5:
                knowledge_uids = entity.get_knowledge_uids()
                # Process high-relevance knowledge carrier
    """

    uid: str

    def knowledge_relevance(self) -> float:
        """
        How relevant is knowledge to this entity? (0.0-1.0)

        Returns:
            float: Knowledge relevance score
                - 1.0: Entity IS knowledge (KU, LS, LP, MOC)
                - 0.5-0.9: Entity is strongly connected to knowledge
                - 0.1-0.4: Entity has some knowledge connections
                - 0.0: Entity has no knowledge connections

        Curriculum domains (KU, LS, LP, MOC) always return 1.0.
        Activity domains return calculated relevance based on knowledge connections.

        Example:
            ku = Ku(uid="ku.python-basics", ...)
            ku.knowledge_relevance()  # → 1.0 (KU IS knowledge)

            task = Task(uid="task.123", source_learning_step_uid="ls.python.step1", ...)
            task.knowledge_relevance()  # → 0.8 (Task is connected to curriculum)

            task_no_learning = Task(uid="task.456", source_learning_step_uid=None, ...)
            task_no_learning.knowledge_relevance()  # → 0.0 (No learning connection)
        """
        ...

    def get_knowledge_uids(self) -> tuple[str, ...]:
        """
        Get all knowledge UIDs this entity carries or references.

        Returns:
            tuple[str, ...]: Tuple of ku-prefixed UIDs (e.g., ("ku.python", "ku.git"))
                            Empty tuple if no knowledge connections.

        For curriculum domains:
            - KU: Returns (self.uid,) - KU IS the knowledge
            - LS: Returns primary_knowledge_uids + supporting_knowledge_uids
            - LP: Aggregates from all steps
            - MOC: Returns all contained knowledge units

        For activity domains:
            - Returns knowledge UIDs from graph relationships
            - Uses existing relationships: APPLIES_KNOWLEDGE, PRACTICES_KNOWLEDGE, etc.

        Example:
            ku = Ku(uid="ku.python-basics", ...)
            ku.get_knowledge_uids()  # → ("ku.python-basics",)

            ls = Ls(uid="ls.python.step1", primary_knowledge_uids=("ku.python",), ...)
            ls.get_knowledge_uids()  # → ("ku.python", "ku.git")

            task = Task(uid="task.123", ...)  # with APPLIES_KNOWLEDGE relationships
            task.get_knowledge_uids()  # → ("ku.python",) via graph lookup
        """
        ...


@runtime_checkable
class SubstantiatedKnowledge(KnowledgeCarrier, Protocol):
    """
    Extended protocol for entities that track knowledge substantiation.

    Substance measures how well knowledge is LIVED, not just learned.
    This is SKUEL's "Applied knowledge, not pure theory" philosophy.

    Implemented by:
    - KU: Full substance tracking with time decay
    - LS: Aggregated substance from contained KUs
    - LP: Aggregated substance from steps
    - MOC: Aggregated substance from mapped content

    Substance Scale (from CLAUDE.md):
        - 0.0-0.2: Pure theory (read about it)
        - 0.3-0.5: Applied knowledge (tried it)
        - 0.6-0.7: Well-practiced (regular use)
        - 0.8-1.0: Lifestyle-integrated (embodied)

    Activity domains DO NOT implement this protocol directly.
    Instead, they CONTRIBUTE TO KU substance via event-driven updates:
        - TaskKnowledgeApplied → updates KU.times_applied_in_tasks
        - EventKnowledgePracticed → updates KU.times_practiced_in_events
        - HabitKnowledgeBuilt → updates KU.times_built_into_habits

    Example:
        if isinstance(entity, SubstantiatedKnowledge):
            score = entity.substance_score()
            if score < 0.3:
                # Knowledge is theoretical - suggest practice
                pass
    """

    def substance_score(self) -> float:
        """
        Calculate how well knowledge is applied in real life.

        Returns:
            float: Substance score 0.0-1.0

        KU Calculation (full implementation):
            Weighted sum with time decay:
            - times_applied_in_tasks * 0.05 (max 0.25)
            - times_practiced_in_events * 0.05 (max 0.25)
            - times_built_into_habits * 0.10 (max 0.30)
            - journal_reflections_count * 0.07 (max 0.20)
            - choices_informed_count * 0.07 (max 0.15)
            + exponential decay based on last_applied_date

        LS/LP/MOC Calculation (aggregated):
            avg(ku.substance_score() for ku in get_knowledge_uids())
        """
        ...


@runtime_checkable
class CurriculumCarrier(KnowledgeCarrier, Protocol):
    """
    Protocol for curriculum entities (KU, LS, LP, MOC).

    These entities ARE knowledge or directly aggregate knowledge.
    They form the curriculum spine: KU → LS → LP → MOC

    Curriculum entities:
    - Are shared content (no user ownership)
    - Always return knowledge_relevance() = 1.0
    - Have domain categorization (TECH, HEALTH, etc.)

    Attributes:
        domain: Subject categorization (from Domain enum)
    """

    domain: "Domain"  # Forward reference to avoid circular import


@runtime_checkable
class ActivityCarrier(KnowledgeCarrier, Protocol):
    """
    Protocol for activity entities (Task, Event, Habit, Goal, Choice, Principle).

    These entities APPLY or reference knowledge through graph relationships.
    They are user-owned and contribute to knowledge substance when completed.

    Activity entities:
    - Are user-owned (user_uid required)
    - Have optional learning integration (source_learning_step_uid)
    - Calculate knowledge_relevance() based on connections

    Attributes:
        user_uid: Owner of this entity
        source_learning_step_uid: Optional learning step that spawned this activity

    Methods:
        learning_impact_score: Calculate learning impact when activity completes
    """

    user_uid: str
    source_learning_step_uid: str | None

    def learning_impact_score(self) -> float:
        """
        Calculate learning impact when this activity completes.

        Returns:
            float: Impact score 0.0-1.0

        Higher impact for:
        - Activities directly linked to curriculum
        - Activities that complete learning objectives
        - Activities that practice knowledge repeatedly

        Used by event-driven updates to increment KU substance counters.
        """
        ...
