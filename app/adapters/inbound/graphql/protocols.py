"""
GraphQL Structural Protocols
=============================

Protocol interfaces defining structural contracts for GraphQL resolvers.

Philosophy: "Duck typing with compile-time type safety"

Protocols enable structural typing - if an object has the required attributes,
it satisfies the protocol, regardless of inheritance hierarchy. This provides:
- Flexibility: Works with Ls, LsDTO, PathStep, or any compatible type
- Type Safety: MyPy enforces protocol satisfaction at compile-time
- No Runtime Checks: No hasattr() needed - type checker guarantees attributes exist
- Loose Coupling: GraphQL layer depends on structure, not concrete types

See: https://peps.python.org/pep-0544/ (PEP 544 - Protocols: Structural subtyping)
"""

from collections.abc import Sequence
from typing import Any, Protocol


class PathStepLike(Protocol):
    """
    Structural contract for path step data in GraphQL.

    Any object satisfying this protocol can be used in GraphQL resolvers
    that need path step data. This includes:
    - Ls (domain model)
    - LsDTO (data transfer object)
    - PathStep (GraphQL type)
    - Any other object with these attributes

    Members are read-only (``@property``) so frozen domain dataclasses
    (PathStep, LearningPath) satisfy the protocol — these are mapper *inputs*
    that are only ever read. Read-only members are covariant, so ``EntityUID``
    (a ``NewType`` over ``str``) satisfies ``uid: str``.

    MyPy will verify at compile-time that objects passed to functions
    expecting PathStepLike have these attributes.

    Example:
        def build_blocker(step: PathStepLike) -> Blocker:
            return Blocker(
                knowledge_uid=step.uid,
                knowledge_title=step.title,  # ✅ Protocol guarantees .title exists
            )
    """

    @property
    def uid(self) -> str: ...
    @property
    def title(self) -> str: ...


class CurriculumEntityLike(Protocol):
    """
    Structural contract for curriculum entity data in GraphQL.

    Any object satisfying this protocol can be used in GraphQL resolvers
    that need curriculum entity data. This includes:
    - PathStep, Ku (domain models)
    - EntityDTO (data transfer object)
    - Any other object with these attributes

    The metadata field is optional (can be None) to support various
    curriculum representations. Members are read-only (``@property``) — these
    are consumer inputs read by resolvers, never mutated.

    Example:
        def check_deprecated(entity: CurriculumEntityLike) -> bool:
            if entity.metadata:
                return entity.metadata.get('deprecated', False)
            return False
    """

    @property
    def uid(self) -> str: ...
    @property
    def title(self) -> str: ...
    @property
    def metadata(self) -> dict[str, Any] | None: ...


class KnowledgeNodeLike(Protocol):
    """
    Structural contract for objects convertible to KnowledgeNode.

    Captures the implicit contract that KnowledgeNode.from_dto() relied on
    via ``Any``. Satisfied by PathStep, CurriculumDTO, EntityDTO, etc.

    Members are read-only (``@property``) and covariant: ``summary: str``
    satisfies ``str | None``, and a ``tuple[str, ...]`` satisfies
    ``Sequence[str] | None``.
    """

    @property
    def uid(self) -> str: ...
    @property
    def title(self) -> str: ...
    @property
    def summary(self) -> str | None: ...
    @property
    def domain(self) -> Any: ...  # Domain enum — has .value
    @property
    def tags(self) -> Sequence[str] | None: ...
    @property
    def quality_score(self) -> float: ...


class TaskLike(Protocol):
    """
    Structural contract for objects convertible to GraphQL Task.

    Satisfied by the Task domain model and TaskDTO. Members are read-only
    (``@property``) — frozen-model-friendly consumer inputs.
    """

    @property
    def uid(self) -> str: ...
    @property
    def title(self) -> str: ...
    @property
    def description(self) -> str | None: ...
    @property
    def status(self) -> Any: ...  # EntityStatus enum — has .value
    @property
    def priority(self) -> str | None: ...


class LearningPathLike(Protocol):
    """
    Structural contract for objects convertible to GraphQL LearningPath.

    Satisfied by LP domain model and LpDTO. Members are read-only
    (``@property``) so the frozen LearningPath dataclass conforms.
    """

    @property
    def uid(self) -> str: ...
    @property
    def title(self) -> str: ...
    @property
    def description(self) -> str | None: ...
    @property
    def estimated_hours(self) -> float | None: ...


class PathStepMappable(Protocol):
    """
    Richer contract for converting an Ls domain model to GraphQL PathStep.

    Extends beyond PathStepLike (uid/title only) with the additional
    fields needed by the mapper. Members are read-only (``@property``) so the
    frozen PathStep dataclass conforms; ``estimated_hours`` is ``float | None``
    to match the model (the mapper None-guards it).
    """

    @property
    def uid(self) -> str: ...
    @property
    def title(self) -> str: ...
    @property
    def knowledge_uids(self) -> tuple[str, ...] | list[str]: ...
    @property
    def mastery_threshold(self) -> float: ...
    @property
    def estimated_hours(self) -> float | None: ...


class PrerequisiteLike(Protocol):
    """
    Structural contract for prerequisite relationship data.

    Used in GraphQL resolvers that need to check prerequisites
    without depending on specific domain model types. Members are read-only
    (``@property``) consumer inputs.
    """

    @property
    def uid(self) -> str: ...
    @property
    def title(self) -> str: ...


class ProgressLike(Protocol):
    """
    Structural contract for user progress data.

    Used in GraphQL resolvers that display progress information
    without depending on specific progress model types. Members are read-only
    (``@property``) consumer inputs.
    """

    @property
    def knowledge_uid(self) -> str: ...
    @property
    def progress(self) -> float: ...  # 0.0 - 1.0
    @property
    def mastery_score(self) -> float: ...  # 0.0 - 1.0


class UserKnowledgeProfileLike(Protocol):
    """
    Structural contract for user knowledge profile data.

    Used in GraphQL resolvers that need to check user mastery
    without depending on specific profile model types. Members are read-only
    (``@property``) consumer inputs.
    """

    @property
    def mastered_uids(self) -> set[str]: ...
    @property
    def in_progress_uids(self) -> set[str]: ...
