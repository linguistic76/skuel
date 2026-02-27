"""
Ku - Atomic Knowledge Unit (Leaf Class)
========================================

The fundamental unit of SKUEL's curriculum domain. A Ku is a discrete,
self-contained piece of knowledge — a lecture, book chapter, talk, document,
or any single educational artifact.

Rooted in SKUEL's philosophy: every entity is a Knowledge Unit. The Ku is
the purest expression of this — a single point of knowledge in the graph.

Part of the 4-part educational loop:
    Ku → Exercise → Submission → Feedback

Hierarchy:
    Entity (~29 fields)
    └── Curriculum(Entity) +21 fields  ← BASE CLASS
        └── Ku(Curriculum)              ← EntityType.KU (this file)

Grouping patterns (Ku is the point, LS is the edge, LP is the path):
    Ku  → atomic knowledge unit
    LS  → a step in a learning path (ordered sequence of Kus)
    LP  → a learning path (ordered sequence of steps)

See: /docs/architecture/CURRICULUM_GROUPING_PATTERNS.md
See: /docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.models.curriculum.curriculum_dto import CurriculumDTO
    from core.models.curriculum.ku_dto import KuDTO
    from core.models.entity_dto import EntityDTO

from core.models.curriculum.curriculum import Curriculum
from core.models.enums.entity_enums import EntityType


@dataclass(frozen=True)
class Ku(Curriculum):
    """
    Atomic Knowledge Unit — the fundamental unit of SKUEL's curriculum domain.

    A Ku is a discrete piece of knowledge: a lecture, book, talk, document,
    or any single educational artifact. It is the leaf node in the curriculum
    hierarchy — it organizes nothing by itself, but can be organized into
    LearningSteps and LearningPaths.

    The 4-part educational loop:
        Ku (atomic knowledge) → Exercise (instruction template)
          → Submission (student work) → Feedback (teacher/AI response)

    Any Ku can also organize other Kus via ORGANIZES relationships
    (emergent MOC identity — no separate type needed).

    See: /docs/architecture/CURRICULUM_GROUPING_PATTERNS.md
    """

    def __post_init__(self) -> None:
        object.__setattr__(self, "ku_type", EntityType.KU)
        super().__post_init__()

    @classmethod
    def from_dto(cls, dto: EntityDTO | CurriculumDTO | KuDTO) -> Ku:
        """Create Ku from an EntityDTO, CurriculumDTO, or KuDTO."""
        return cls._from_dto(dto)

    def to_dto(self) -> KuDTO:  # type: ignore[override]
        """Convert Ku to domain-specific KuDTO."""
        from core.models.curriculum.ku_dto import KuDTO

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
        return f"Ku(uid={self.uid}, title='{self.title}')"

    def __repr__(self) -> str:
        return (
            f"Ku(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, domain={self.domain}, "
            f"complexity={self.complexity})"
        )
