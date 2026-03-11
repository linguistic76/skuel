"""
GraphQL Structural Protocols
=============================

Protocol interfaces defining structural contracts for GraphQL resolvers.

Philosophy: "Duck typing with compile-time type safety"

Protocols enable structural typing - if an object has the required attributes,
it satisfies the protocol, regardless of inheritance hierarchy. This provides:
- Flexibility: Works with Ls, LsDTO, LearningStep, or any compatible type
- Type Safety: MyPy enforces protocol satisfaction at compile-time
- No Runtime Checks: No hasattr() needed - type checker guarantees attributes exist
- Loose Coupling: GraphQL layer depends on structure, not concrete types

See: https://peps.python.org/pep-0544/ (PEP 544 - Protocols: Structural subtyping)
"""

from typing import Any, Protocol


class LearningStepLike(Protocol):
    """
    Structural contract for learning step data in GraphQL.

    Any object satisfying this protocol can be used in GraphQL resolvers
    that need learning step data. This includes:
    - Ls (domain model)
    - LsDTO (data transfer object)
    - LearningStep (GraphQL type)
    - Any other object with these attributes

    MyPy will verify at compile-time that objects passed to functions
    expecting LearningStepLike have these attributes.

    Example:
        def build_blocker(step: LearningStepLike) -> Blocker:
            return Blocker(
                knowledge_uid=step.uid,
                knowledge_title=step.title,  # ✅ Protocol guarantees .title exists
            )
    """

    uid: str
    title: str


class CurriculumEntityLike(Protocol):
    """
    Structural contract for curriculum entity data in GraphQL.

    Any object satisfying this protocol can be used in GraphQL resolvers
    that need curriculum entity data. This includes:
    - Article, Ku (domain models)
    - EntityDTO (data transfer object)
    - Any other object with these attributes

    The metadata field is optional (can be None) to support various
    curriculum representations.

    Example:
        def check_deprecated(entity: CurriculumEntityLike) -> bool:
            if entity.metadata:
                return entity.metadata.get('deprecated', False)
            return False
    """

    uid: str
    title: str
    metadata: dict[str, Any] | None


class KnowledgeNodeLike(Protocol):
    """
    Structural contract for objects convertible to KnowledgeNode.

    Captures the implicit contract that KnowledgeNode.from_dto() relied on
    via ``Any``. Satisfied by Article, CurriculumDTO, EntityDTO, etc.
    """

    uid: str
    title: str
    summary: str | None
    domain: Any  # Domain enum — has .value
    tags: list[str] | None
    quality_score: float


class TaskLike(Protocol):
    """
    Structural contract for objects convertible to GraphQL Task.

    Satisfied by the Task domain model and TaskDTO.
    """

    uid: str
    title: str
    description: str | None
    status: Any  # EntityStatus enum — has .value
    priority: str | None


class LearningPathLike(Protocol):
    """
    Structural contract for objects convertible to GraphQL LearningPath.

    Satisfied by LP domain model and LpDTO.
    """

    uid: str
    title: str
    description: str | None
    estimated_hours: float | None


class LearningStepMappable(Protocol):
    """
    Richer contract for converting an Ls domain model to GraphQL LearningStep.

    Extends beyond LearningStepLike (uid/title only) with the additional
    fields needed by the mapper.
    """

    uid: str
    title: str
    primary_knowledge_uids: tuple[str, ...] | list[str]
    mastery_threshold: float
    estimated_hours: float


class PrerequisiteLike(Protocol):
    """
    Structural contract for prerequisite relationship data.

    Used in GraphQL resolvers that need to check prerequisites
    without depending on specific domain model types.
    """

    uid: str
    title: str


class ProgressLike(Protocol):
    """
    Structural contract for user progress data.

    Used in GraphQL resolvers that display progress information
    without depending on specific progress model types.
    """

    knowledge_uid: str
    progress: float  # 0.0 - 1.0
    mastery_score: float  # 0.0 - 1.0


class UserKnowledgeProfileLike(Protocol):
    """
    Structural contract for user knowledge profile data.

    Used in GraphQL resolvers that need to check user mastery
    without depending on specific profile model types.
    """

    mastered_uids: set[str]
    in_progress_uids: set[str]
