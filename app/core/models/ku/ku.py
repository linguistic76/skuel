"""
Ku - Atomic Knowledge Unit
===========================

A Ku is a single definable thing: a concept, state, principle, substance,
practice, or value. Small enough to appear in many PathSteps without dragging
narrative. Extends Entity directly (not Curriculum — no learning metadata).

Ku = Unit of Truth/Reference. PathStep = Unit for Learning.

Hierarchy:
    Entity (~29 fields)
    └── Ku(Entity) +6 fields  ← EntityType.KU (this file)

UID Format (flat, opaque — identity not classification, ADR-013):
    ku_{slug}_{random} (API-generated) or ku.{ns}.{slug} (vault-authored).
    e.g., ku_buzzing_a1b2c3d4 — never parse the UID to infer type or grouping.

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.entity_dto import EntityDTO
    from core.models.ku.ku_dto import KuDTO

from core.models.entity import Entity
from core.models.enums.curriculum_enums import PublicationState
from core.models.enums.entity_enums import EntityType
from core.models.enums.learning_enums import SELCategory


@dataclass(frozen=True)
class Ku(Entity):
    """
    Atomic Knowledge Unit — the smallest unit of knowledge in SKUEL.

    A Ku is a single definable thing: a concept (caffeine), a state (buzzing),
    a principle (truth_oriented_collaboration), a practice (meditation).

    Unlike PathSteps (which are units for learning with composed content),
    Kus are lightweight ontology/reference nodes. They don't carry
    full learning metadata (complexity, substance scores), but they
    do carry sel_category for SEL competency organization.

    PathSteps USES_KU to compose atoms into narrative.
    Learning Steps TRAINS_KU to declare learning objectives.
    """

    # Honest leaf identity (G6): defaults to its own type; __post_init__
    # rejects a mismatch instead of silently correcting it.
    entity_type: EntityType = field(default=EntityType.KU, kw_only=True)

    # =========================================================================
    # KU-SPECIFIC FIELDS
    # =========================================================================
    aliases: tuple[str, ...] = field(default_factory=tuple)  # alternative names
    sel_category: SELCategory | None = None  # SEL competency this Ku belongs to
    # Ku is NOT a Curriculum subclass, so this is declared here rather than
    # inherited — but Ku IS publication-controlled everywhere else: the PUBLIC
    # search gate applies to it and the health gauge counts it in
    # ``draft_curriculum_count``. Without the field the model silently dropped
    # a value ingestion had accepted and Cypher was already filtering on
    # (Codex #1006).
    publication_state: PublicationState = PublicationState.PUBLISHED
    # NOUS topic membership — which of the 11 official topic sections this Ku
    # belongs to (stories, body, self-awareness, ...). Multi-topic allowed;
    # empty = deliberately unassigned (rawness principle — content may exist
    # without a section). Authored in vault YAML as `nous:`.
    nous: tuple[str, ...] = field(default_factory=tuple)
    # NOUS sub-topic membership — the 2nd taxonomy level beneath `nous` (e.g.
    # body → nervous-system, sleep, movement). Mirrors `nous` exactly: multi-
    # valued, empty = deliberately unassigned. Authored in vault YAML as
    # `nous_subtopic:`. Flat for now — a nous→subtopic dependency awaits data.
    nous_subtopic: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        """Validate entity_type=KU, then delegate to Entity."""
        if self.entity_type != EntityType.KU:
            raise ValueError(
                f"Ku constructed with entity_type={self.entity_type!r} "
                f"(uid={self.uid!r}) — the writer persisted a wrong type (G6)"
            )
        # Normalize list-authored fields to tuples (frozen dataclass)
        if isinstance(self.aliases, list):
            object.__setattr__(self, "aliases", tuple(self.aliases))
        if isinstance(self.nous, list):
            object.__setattr__(self, "nous", tuple(self.nous))
        if isinstance(self.nous_subtopic, list):
            object.__setattr__(self, "nous_subtopic", tuple(self.nous_subtopic))
        super().__post_init__()

    # =========================================================================
    # CONVERSION
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: EntityDTO | KuDTO) -> Ku:
        """Create Ku from an EntityDTO or KuDTO."""
        return cls._from_dto(dto)

    def to_dto(self) -> KuDTO:
        """Convert Ku to domain-specific KuDTO."""
        from core.models.dto_helpers import domain_to_dto
        from core.models.ku.ku_dto import KuDTO

        return domain_to_dto(self, KuDTO)

    def __str__(self) -> str:
        return f"Ku(uid={self.uid}, title='{self.title}')"

    def __repr__(self) -> str:
        return f"Ku(uid='{self.uid}', title='{self.title}')"
