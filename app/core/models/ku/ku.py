"""
Ku - Atomic Knowledge Unit
===========================

A Ku is a single definable thing: a concept, state, principle, substance,
practice, or value. Small enough to appear in many Lessons without dragging
narrative. Extends Entity directly (not Curriculum — no learning metadata).

Ku = Unit of Truth/Reference. Lesson = Unit for Learning.

Hierarchy:
    Entity (~29 fields)
    └── Ku(Entity) +5 fields  ← EntityType.KU (this file)

UID Format: ku_{namespace}-{slug}_{random}
    e.g., ku_attention-buzzing_a1b2c3d4
    Namespace derived from middle segment at first hyphen.

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.models.entity_dto import EntityDTO
    from core.models.ku.ku_dto import KuDTO

from core.models.entity import Entity
from core.models.enums.entity_enums import EntityType
from core.models.enums.learning_enums import SELCategory


@dataclass(frozen=True)
class Ku(Entity):
    """
    Atomic Knowledge Unit — the smallest unit of knowledge in SKUEL.

    A Ku is a single definable thing: a concept (caffeine), a state (buzzing),
    a principle (truth_oriented_collaboration), a practice (meditation).

    Unlike Lessons (which are units for learning with composed content),
    Kus are lightweight ontology/reference nodes. They don't carry
    full learning metadata (complexity, substance scores), but they
    do carry sel_category for SEL competency organization.

    Lessons USES_KU to compose atoms into narrative.
    Learning Steps TRAINS_KU to declare learning objectives.
    """

    # =========================================================================
    # KU-SPECIFIC FIELDS
    # =========================================================================
    namespace: str | None = None  # primary grouping (attention, emotion, body, ...)
    ku_category: str | None = None  # state/concept/principle/intake/substance/practice/value
    aliases: tuple[str, ...] = field(default_factory=tuple)  # alternative names
    source: str | None = None  # self_observation/research/teacher
    sel_category: SELCategory | None = None  # SEL competency this Ku belongs to

    def __post_init__(self) -> None:
        """Force entity_type=KU, then delegate to Entity."""
        if self.entity_type != EntityType.KU:
            object.__setattr__(self, "entity_type", EntityType.KU)
        # Normalize aliases from list to tuple (frozen dataclass)
        if isinstance(self.aliases, list):
            object.__setattr__(self, "aliases", tuple(self.aliases))
        super().__post_init__()

    # =========================================================================
    # CONVERSION
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: EntityDTO | KuDTO) -> Ku:
        """Create Ku from an EntityDTO or KuDTO."""
        return cls._from_dto(dto)

    def to_dto(self) -> KuDTO:  # type: ignore[override]
        """Convert Ku to domain-specific KuDTO."""
        from core.models.ku.ku_dto import KuDTO

        dto_field_names = {f.name for f in dataclasses.fields(KuDTO)}
        kwargs: dict[str, Any] = {}
        for f in dataclasses.fields(self):
            if f.name.startswith("_") or f.name not in dto_field_names:
                continue
            value = getattr(self, f.name)
            if isinstance(value, tuple):
                value = list(value)
            kwargs[f.name] = value
        return KuDTO(**kwargs)

    def __str__(self) -> str:
        ns = f" [{self.namespace}]" if self.namespace else ""
        return f"Ku(uid={self.uid}, title='{self.title}'{ns})"

    def __repr__(self) -> str:
        return (
            f"Ku(uid='{self.uid}', title='{self.title}', "
            f"namespace={self.namespace}, ku_category={self.ku_category})"
        )
