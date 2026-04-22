"""
Interaction - User Interaction Contract Domain Model
=====================================================

Frozen dataclass for situated learning-loop events (EntityType.INTERACTION).
Records who did what, to which target, in which curriculum context, with what result.

This is the 22nd entity type in SKUEL. It materialises the "User Interaction
Contract" design concept: a first-class, YAML-ingestible, graph-queryable record
of every meaningful user-curriculum interaction.

Learning context at interaction time — the critical gap this fills:
    UserEntry records WHAT was submitted but not WHERE in the curriculum
    the user was when they submitted. Interaction bridges that gap, enabling
    ZPD and Askesis to reason about situated learning events.

Hierarchy:
    Entity (~19 fields)
    └── UserOwnedEntity(Entity) +2 fields (user_uid, priority)
        └── Interaction(UserOwnedEntity) +6 fields

Graph relationships:
    (Interaction)-[:RECORDS]->(UserEntry | ...)            source artifact
    (Interaction)-[:INTERACTION_DURING]->(PathStep)        curriculum context
    (Interaction)-[:INTERACTION_WITHIN]->(LearningPath)    path context

YAML ingestion:
    type: interaction
    interaction_type: exercise_submission
    target_uid: ex.body-check-30s
    context_path_step_uid: ps.notice-the-loop      # optional
    context_learning_path_uid: lp.game-of-life     # optional
    result_status: pending
    source_entity_uid: es.abc123                   # optional

See: /home/mike/0bsidian/0design/layers - architecture 0.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.models.enums.entity_enums import EntityType
from core.models.enums.interaction_enums import InteractionResult, InteractionType
from core.models.type_hints import EntityUID
from core.models.user_owned_entity import UserOwnedEntity

if TYPE_CHECKING:
    from core.models.entity_dto import EntityDTO
    from core.models.interaction.interaction_dto import InteractionDTO


@dataclass(frozen=True, kw_only=True)
class Interaction(UserOwnedEntity):
    """
    Immutable domain model for situated learning-loop events (EntityType.INTERACTION).

    An Interaction records a meaningful user-curriculum event with its full context:
    who (user_uid), what (interaction_type + target_uid), where in the curriculum
    (context_path_step_uid + context_learning_path_uid), and the outcome (result_status).

    Fields (6 interaction-specific):
    - interaction_type:           What kind of interaction (EXERCISE_SUBMISSION, KU_VIEW, ...)
    - target_uid:                 UID of the entity being interacted with (exercise, ps, ku, ...)
    - context_path_step_uid:      PathStep the user was studying when this occurred (nullable)
    - context_learning_path_uid:  LearningPath the user was enrolled in (nullable)
    - source_entity_uid:          UID of the artifact this interaction created (nullable)
    - result_status:              What happened as a result (PENDING, REPORT_GENERATED, ...)
    """

    def __post_init__(self) -> None:
        """Force entity_type=INTERACTION, then delegate to UserOwnedEntity."""
        if self.entity_type != EntityType.INTERACTION:
            object.__setattr__(self, "entity_type", EntityType.INTERACTION)
        super().__post_init__()

    # =========================================================================
    # INTERACTION-SPECIFIC FIELDS (6)
    # =========================================================================

    interaction_type: InteractionType = InteractionType.EXERCISE_SUBMISSION
    # What kind of interaction this records.

    target_uid: str = ""
    # UID of the entity being interacted with.
    # For EXERCISE_SUBMISSION: the Exercise UID (ex.body-check-30s).
    # For KU_VIEW: the Ku UID. For PATH_STEP_COMPLETION: the PathStep UID.

    context_path_step_uid: str | None = None
    # PathStep the user was actively studying at interaction time.
    # Captured from UserContext.current_ps_uids at submission moment.

    context_learning_path_uid: str | None = None
    # LearningPath the user was enrolled in at interaction time.
    # Captured from UserContext.current_learning_path_uid.

    source_entity_uid: str | None = None
    # UID of the artifact this interaction generated or relates to.
    # For EXERCISE_SUBMISSION: the UserEntry UID (back-pointer, ADR-054).

    result_status: InteractionResult = InteractionResult.PENDING
    # What happened as a result of this interaction.
    # Updated by the submission processing pipeline when a report is generated.

    # =========================================================================
    # METHODS
    # =========================================================================

    def is_exercise_submission(self) -> bool:
        """Check if this records an exercise submission interaction."""
        return self.interaction_type == InteractionType.EXERCISE_SUBMISSION

    def has_curriculum_context(self) -> bool:
        """Check if this interaction has PathStep or LearningPath context."""
        return self.context_path_step_uid is not None or self.context_learning_path_uid is not None

    def to_dto(self) -> InteractionDTO:
        """Convert to mutable InteractionDTO for service layer operations."""
        from core.models.dto_helpers import domain_to_dto
        from core.models.interaction.interaction_dto import InteractionDTO

        return domain_to_dto(self, InteractionDTO)

    @classmethod
    def from_dto(cls, dto: EntityDTO | InteractionDTO) -> Interaction:
        """Create Interaction from an EntityDTO or InteractionDTO."""
        return cls._from_dto(dto)

    @classmethod
    def from_interaction_dto(cls, dto: InteractionDTO) -> Interaction:
        """Create immutable Interaction from mutable InteractionDTO.

        Note: Entity.from_dto dispatcher uses _from_dto() for generic construction.
        This method is available for explicit InteractionDTO → Interaction conversion
        in the interaction service layer.
        """
        return cls(
            uid=EntityUID(dto.uid or ""),
            entity_type=EntityType.INTERACTION,
            title=dto.title or "",
            description=dto.description,
            content=dto.content,
            status=dto.status,
            tags=tuple(dto.tags) if dto.tags else (),
            metadata=dict(dto.metadata) if dto.metadata else {},
            user_uid=dto.user_uid,
            priority=dto.priority,
            created_at=dto.created_at,
            updated_at=dto.updated_at,
            interaction_type=dto.interaction_type or InteractionType.EXERCISE_SUBMISSION,
            target_uid=dto.target_uid or "",
            context_path_step_uid=dto.context_path_step_uid,
            context_learning_path_uid=dto.context_learning_path_uid,
            source_entity_uid=dto.source_entity_uid,
            result_status=dto.result_status or InteractionResult.PENDING,
        )
